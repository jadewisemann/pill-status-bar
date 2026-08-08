"""Flow Launcher plugin for ChillPill.

Flow owns app launching, file search and the calculator; this plugin adds the
other direction -- driving the shell from Flow's query box.  Everything it does
is one JSON line down the shell's named pipe, so the plugin has no dependency
on the shell's Python packages and can live outside the repo once installed.

Protocol: Flow hands a JSON-RPC request in as `argv[1]` and reads the reply
from stdout.  Some builds pipe the request on stdin instead, so both are
accepted.

    {"method": "query", "parameters": ["vol 40"]}
      -> {"result": [{"Title": ..., "JsonRPCAction": {...}}]}
"""

from __future__ import annotations

import json
import sys
import time

PIPE_NAME = r"\\.\pipe\chillpill_ipc"
ICON = "Images/chillpill.png"

ERROR_PIPE_BUSY = 231
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1


# --------------------------------------------------------------------------
# Talking to the shell
# --------------------------------------------------------------------------


def send(payload: dict, timeout: float = 3.0) -> dict:
    """Write one command to the pipe and read the reply."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    deadline = time.monotonic() + timeout

    while True:
        handle = kernel32.CreateFileW(PIPE_NAME, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
        if handle != INVALID_HANDLE_VALUE and handle:
            break
        if kernel32.GetLastError() != ERROR_PIPE_BUSY or time.monotonic() > deadline:
            return {"ok": False, "error": "ChillPill is not running"}
        kernel32.WaitNamedPipeW(PIPE_NAME, 200)

    try:
        data = (json.dumps(payload) + "\n").encode("utf-8")
        written = wintypes.DWORD()
        kernel32.WriteFile(handle, data, len(data), ctypes.byref(written), None)
        kernel32.FlushFileBuffers(handle)

        buffer = ctypes.create_string_buffer(8192)
        read = wintypes.DWORD()
        chunks = []
        while kernel32.ReadFile(handle, buffer, 8192, ctypes.byref(read), None) and read.value:
            chunks.append(buffer.raw[: read.value])
            if b"\n" in chunks[-1]:
                break
        raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
        return json.loads(raw) if raw else {"ok": False, "error": "no reply"}
    except Exception as exc:  # a dead shell must not crash Flow's query
        return {"ok": False, "error": str(exc)}
    finally:
        kernel32.CloseHandle(handle)


def shell_status() -> dict | None:
    reply = send({"cmd": "status", "target": "", "args": {}})
    return reply.get("result") if reply.get("ok") else None


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


def result(title: str, subtitle: str, cmd: str, target: str = "", args: dict | None = None) -> dict:
    return {
        "Title": title,
        "SubTitle": subtitle,
        "IcoPath": ICON,
        "JsonRPCAction": {
            "method": "run",
            "parameters": [json.dumps({"cmd": cmd, "target": target, "args": args or {}})],
        },
    }


def message(title: str, subtitle: str = "") -> dict:
    """A result that does nothing when chosen."""
    return {"Title": title, "SubTitle": subtitle, "IcoPath": ICON}


def build_results(query: str) -> list[dict]:
    """Turn what the user has typed so far into Flow results.

    Prefix order matters: the first one that matches wins, and an unrecognised
    query falls back to filtering the default list by title so `cp dash` still
    finds the dashboard.
    """
    query = query.strip()
    parts = query.split()
    head = parts[0].lower() if parts else ""
    rest = parts[1:]

    if not query:
        return default_results()

    if head in ("vol", "volume"):
        return volume_results(rest)
    if head in ("bri", "brightness"):
        return level_results("brightness", "Brightness", rest)
    if head == "timer":
        return timer_results(rest)
    if head == "dnd":
        return [
            result("Do not disturb: on", "suppress notification popups", "dnd", args={"value": "on"}),
            result("Do not disturb: off", "let notifications pop again", "dnd", args={"value": "off"}),
        ]
    if head in ("wall", "wallpaper"):
        return [result("Open the wallpaper switcher", "browse the wallpaper folder", "show", "wallpapers")]
    if head in ("clip", "clipboard"):
        return [result("Open clipboard history", "search what you have copied", "show", "clipboard")]

    return [entry for entry in default_results() if query.lower() in entry["Title"].lower()] or [
        message("No ChillPill command matches that", "try: vol, bri, timer, dnd, wall, clip")
    ]


def default_results() -> list[dict]:
    status = shell_status()
    if status is None:
        return [message("ChillPill is not running", "start the shell, then try again")]

    modules = status.get("modules", {})
    volume = modules.get("volume", {})
    open_surface = status.get("open") or "nothing"

    return [
        result("Control center", f"currently open: {open_surface}", "toggle", "controlCenter"),
        result("Dashboard", "uptime, network, weather, power", "toggle", "dashboard"),
        result("Clipboard history", "search what you have copied", "toggle", "clipboard"),
        result("Wallpapers", "browse and apply a background", "toggle", "wallpapers"),
        result("Close everything", "collapse the pill back to the bar", "hide", "*"),
        result(
            "Mute / unmute",
            f"volume is {volume.get('percent', '?')}%{' (muted)' if volume.get('muted') else ''}",
            "volume",
            args={"value": "0" if not volume.get("muted") else "50"},
        ),
    ]


def volume_results(rest: list[str]) -> list[dict]:
    if rest:
        return level_results("volume", "Volume", rest)
    return [
        result("Volume 0%", "mute", "volume", args={"value": "0"}),
        result("Volume 25%", "", "volume", args={"value": "25"}),
        result("Volume 50%", "", "volume", args={"value": "50"}),
        result("Volume 75%", "", "volume", args={"value": "75"}),
        result("Volume 100%", "", "volume", args={"value": "100"}),
    ]


def level_results(cmd: str, label: str, rest: list[str]) -> list[dict]:
    raw = rest[0]
    if raw.startswith(("+", "-")):
        return [result(f"{label} {raw}", "step from the current value", cmd, args={"value": raw})]
    try:
        value = max(0, min(100, int(float(raw))))
    except ValueError:
        return [message(f"{label} takes 0-100, or +N / -N", f"got {raw!r}")]
    return [result(f"{label} {value}%", "", cmd, args={"value": str(value)})]


def timer_results(rest: list[str]) -> list[dict]:
    if rest and rest[0].lower() in ("cancel", "stop"):
        return [result("Cancel the timer", "", "timer", args={"value": "cancel"})]
    if rest:
        try:
            minutes = float(rest[0])
        except ValueError:
            return [message("Timer takes a number of minutes", f"got {rest[0]!r}")]
        return [result(f"Timer: {minutes:g} minutes", "", "timer", args={"value": str(minutes)})]
    return [
        result(f"Timer: {minutes} minutes", "", "timer", args={"value": str(minutes)}) for minutes in (1, 5, 10, 15, 30)
    ] + [result("Cancel the timer", "", "timer", args={"value": "cancel"})]


# --------------------------------------------------------------------------
# JSON-RPC entry point
# --------------------------------------------------------------------------


def read_request() -> dict:
    """Flow passes the request as argv[1]; some builds use stdin instead."""
    if len(sys.argv) > 1 and sys.argv[1].strip().startswith("{"):
        return json.loads(sys.argv[1])
    raw = sys.stdin.read().strip()
    return json.loads(raw) if raw else {}


def main() -> int:
    try:
        request = read_request()
    except json.JSONDecodeError as exc:
        print(json.dumps({"result": [message("ChillPill plugin: bad request", str(exc))]}))
        return 0

    method = request.get("method", "query")
    parameters = request.get("parameters") or []

    if method == "query":
        query = str(parameters[0]) if parameters else ""
        print(json.dumps({"result": build_results(query)}))
        return 0

    if method == "run":
        payload = json.loads(parameters[0]) if parameters else {}
        reply = send(payload)
        # Flow shows nothing for a successful action; a failure is worth saying.
        if not reply.get("ok"):
            print(
                json.dumps(
                    {
                        "result": [],
                        "method": "Flow.Launcher.ShowMsg",
                        "parameters": ["ChillPill", str(reply.get("error", "command failed")), ""],
                    }
                )
            )
        else:
            print(json.dumps({"result": []}))
        return 0

    print(json.dumps({"result": [message(f"ChillPill plugin: unknown method {method!r}")]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
