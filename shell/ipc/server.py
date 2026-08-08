r"""Named pipe server.

Runs `CreateNamedPipe` / `ConnectNamedPipe` on its own thread and marshals each
received command onto the GUI thread through a Qt signal.  One client at a
time, connection per command -- the CLI writes a line, reads the reply and
disconnects, so there is nothing to multiplex.

Access control is the default DACL, which grants the creating user and denies
everyone else.  That matters: this pipe can set the wallpaper and quit the
shell.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from shell.ipc.protocol import Command, ProtocolError, parse_message
from shell.platform import IS_WINDOWS

logger = logging.getLogger(__name__)

PIPE_NAME = r"\\.\pipe\chillpill_ipc"

PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_BYTE = 0x00000000
PIPE_READMODE_BYTE = 0x00000000
PIPE_WAIT = 0x00000000
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
INVALID_HANDLE_VALUE = -1
ERROR_PIPE_CONNECTED = 535
ERROR_BROKEN_PIPE = 109
BUFFER_SIZE = 8192


class IpcServer(QObject):
    """Owns the pipe thread and forwards commands to the app."""

    #: (command, reply queue).  The handler puts a JSON-serialisable reply on
    #: the queue; the pipe thread is blocked waiting for it.
    command_received = pyqtSignal(object, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        if not IS_WINDOWS:
            logger.info("named pipe IPC is Windows-only; not listening")
            return False
        if self._thread is not None:
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name="chillpill-ipc", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        # Unblock ConnectNamedPipe by connecting to ourselves once.
        try:
            from shell.ipc.client import send_raw

            send_raw('{"cmd": "ping"}', timeout=0.5)
        except Exception:  # pragma: no cover - shutdown is best-effort
            pass
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    # -- pipe loop ---------------------------------------------------------

    def _serve(self) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        while not self._stop.is_set():
            handle = kernel32.CreateNamedPipeW(
                PIPE_NAME,
                PIPE_ACCESS_DUPLEX,
                PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
                1,  # one instance: commands are serialised anyway
                BUFFER_SIZE,
                BUFFER_SIZE,
                0,
                None,  # default DACL -- current user only
            )
            if handle == INVALID_HANDLE_VALUE or not handle:
                error = ctypes.get_last_error()
                logger.error("could not create %s (error %s); IPC disabled", PIPE_NAME, error)
                return

            connected = kernel32.ConnectNamedPipe(handle, None)
            if not connected and kernel32.GetLastError() != ERROR_PIPE_CONNECTED:
                kernel32.CloseHandle(handle)
                continue
            if self._stop.is_set():
                kernel32.DisconnectNamedPipe(handle)
                kernel32.CloseHandle(handle)
                break

            try:
                request = self._read_line(kernel32, handle, wintypes)
                if request:
                    reply = self._dispatch(request)
                    self._write(kernel32, handle, wintypes, reply + "\n")
            except Exception:
                logger.exception("IPC request failed")
            finally:
                kernel32.FlushFileBuffers(handle)
                kernel32.DisconnectNamedPipe(handle)
                kernel32.CloseHandle(handle)

    @staticmethod
    def _read_line(kernel32: Any, handle: Any, wintypes: Any) -> str:
        import ctypes

        chunks: list[bytes] = []
        buffer = ctypes.create_string_buffer(BUFFER_SIZE)
        read = wintypes.DWORD()
        while True:
            ok = kernel32.ReadFile(handle, buffer, BUFFER_SIZE, ctypes.byref(read), None)
            if not ok or read.value == 0:
                break
            chunks.append(buffer.raw[: read.value])
            if b"\n" in chunks[-1]:
                break
        return b"".join(chunks).decode("utf-8", errors="replace").split("\n", 1)[0].strip()

    @staticmethod
    def _write(kernel32: Any, handle: Any, wintypes: Any, text: str) -> None:
        import ctypes

        payload = text.encode("utf-8")
        written = wintypes.DWORD()
        kernel32.WriteFile(handle, payload, len(payload), ctypes.byref(written), None)

    def _dispatch(self, line: str) -> str:
        try:
            command = parse_message(line)
        except ProtocolError as exc:
            return json.dumps({"ok": False, "error": str(exc)})

        replies: queue.Queue = queue.Queue(maxsize=1)
        self.command_received.emit(command, replies)
        try:
            result = replies.get(timeout=5)
        except queue.Empty:
            return json.dumps({"ok": False, "error": "the shell did not answer in time"})
        return json.dumps(result)


def reply_ok(result: Any = None) -> dict[str, Any]:
    return {"ok": True, "result": result}


def reply_error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def command_summary(command: Command) -> str:
    """For log lines."""
    return f"{command.cmd} {command.target}".strip()
