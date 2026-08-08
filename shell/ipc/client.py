r"""Named pipe client: write one JSON line, read one back."""

from __future__ import annotations

import json
import time
from typing import Any

from shell.ipc.protocol import Command
from shell.ipc.server import PIPE_NAME
from shell.platform import IS_WINDOWS

ERROR_PIPE_BUSY = 231
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1


class NotRunningError(RuntimeError):
    """No shell is listening on the pipe."""


def send(command: Command, timeout: float = 5.0) -> dict[str, Any]:
    """Send a command and return the parsed reply."""
    raw = send_raw(command.to_json(), timeout=timeout)
    try:
        reply = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"malformed reply from the shell: {raw!r}") from exc
    if not isinstance(reply, dict):
        raise RuntimeError(f"malformed reply from the shell: {raw!r}")
    return reply


def send_raw(line: str, timeout: float = 5.0) -> str:
    """Low-level write/read.  Raises NotRunningError when the pipe is absent."""
    if not IS_WINDOWS:
        raise NotRunningError("named pipe IPC is Windows-only")

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    deadline = time.monotonic() + timeout

    while True:
        handle = kernel32.CreateFileW(PIPE_NAME, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
        if handle != INVALID_HANDLE_VALUE and handle:
            break
        error = kernel32.GetLastError()
        if error != ERROR_PIPE_BUSY or time.monotonic() > deadline:
            raise NotRunningError("ChillPill is not running (no listener on the pipe)")
        # Another client is mid-command; the server is single-instance so wait.
        kernel32.WaitNamedPipeW(PIPE_NAME, 200)

    try:
        payload = (line.rstrip("\n") + "\n").encode("utf-8")
        written = wintypes.DWORD()
        if not kernel32.WriteFile(handle, payload, len(payload), ctypes.byref(written), None):
            raise RuntimeError("could not write to the shell's pipe")
        kernel32.FlushFileBuffers(handle)

        chunks: list[bytes] = []
        buffer = ctypes.create_string_buffer(8192)
        read = wintypes.DWORD()
        while True:
            if not kernel32.ReadFile(handle, buffer, 8192, ctypes.byref(read), None) or read.value == 0:
                break
            chunks.append(buffer.raw[: read.value])
            if b"\n" in chunks[-1]:
                break
        return b"".join(chunks).decode("utf-8", errors="replace").strip()
    finally:
        kernel32.CloseHandle(handle)


def is_running() -> bool:
    """True when a shell answers a ping."""
    try:
        return bool(send(Command(cmd="ping"), timeout=1.0).get("ok"))
    except (NotRunningError, RuntimeError):
        return False
