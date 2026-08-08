"""IPC command grammar.

Wire format: one UTF-8 JSON object per line, newline-framed, over the named
pipe `\\\\.\\pipe\\chillpill_ipc`.

Request:  {"cmd": "toggle", "target": "controlCenter", "args": {...}}
Response: {"ok": true, "result": ...}  or  {"ok": false, "error": "..."}

The CLI also accepts a shorthand -- `chillpillc toggle controlCenter` -- which
`parse_argv` turns into the same object, so scripting the shell never requires
hand-writing JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from shell.state import PillState

#: CLI/IPC target name -> the state it opens.
TARGETS: dict[str, PillState] = {
    "controlCenter": PillState.CONTROL_CENTER,
    "dashboard": PillState.DASHBOARD,
    "clipboard": PillState.CLIPBOARD,
    "launcher": PillState.LAUNCHER,
    "wallpapers": PillState.WALLPAPERS,
}

#: Aliases kept for parity with the original shell's IPC names.
ALIASES: dict[str, str] = {
    "cliphist": "clipboard",
    "miniDashboard": "dashboard",
    "appLauncher": "launcher",
    "wallpaperSwitcher": "wallpapers",
}

SURFACE_COMMANDS = ("toggle", "show", "hide")
VALUE_COMMANDS = ("volume", "brightness", "timer", "dnd", "wallpaper", "notify")
QUERY_COMMANDS = ("status", "ping", "quit", "reload")

COMMANDS = SURFACE_COMMANDS + VALUE_COMMANDS + QUERY_COMMANDS


class ProtocolError(ValueError):
    """The message was not a command this shell understands."""


@dataclass
class Command:
    cmd: str
    target: str = ""
    args: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"cmd": self.cmd, "target": self.target, "args": self.args})

    @property
    def state(self) -> PillState | None:
        """The surface this command addresses, if any."""
        return TARGETS.get(resolve_target(self.target))


def resolve_target(target: str) -> str:
    return ALIASES.get(target, target)


def parse_message(line: str) -> Command:
    """Parse one wire line into a Command."""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("expected a JSON object")
    cmd = str(payload.get("cmd", "")).strip()
    if cmd not in COMMANDS:
        raise ProtocolError(f"unknown command {cmd!r}; expected one of {', '.join(COMMANDS)}")
    args = payload.get("args") or {}
    if not isinstance(args, dict):
        raise ProtocolError("args must be an object")
    command = Command(cmd=cmd, target=str(payload.get("target", "")), args=args)
    _validate(command)
    return command


def _validate(command: Command) -> None:
    if command.cmd in SURFACE_COMMANDS:
        target = resolve_target(command.target)
        if target != "*" and target not in TARGETS:
            known = ", ".join(sorted(TARGETS) + ["*"])
            raise ProtocolError(f"unknown target {command.target!r}; expected one of {known}")
    if command.cmd in ("volume", "brightness") and "value" not in command.args:
        raise ProtocolError(f"{command.cmd} needs an args.value (0-100, or +N / -N to step)")


def parse_argv(argv: list[str]) -> Command:
    """Turn `["toggle", "controlCenter"]` into a Command.

    Value commands take their argument positionally: `volume 40`, `volume +5`,
    `timer 10`, `dnd on`, `wallpaper C:\\path\\to.png`.
    """
    if not argv:
        raise ProtocolError("no command given")
    cmd, rest = argv[0], argv[1:]
    if cmd not in COMMANDS:
        raise ProtocolError(f"unknown command {cmd!r}; expected one of {', '.join(COMMANDS)}")

    if cmd in SURFACE_COMMANDS:
        target = rest[0] if rest else ""
        if not target:
            raise ProtocolError(f"{cmd} needs a target: {', '.join(sorted(TARGETS))} or *")
        command = Command(cmd=cmd, target=target)
    elif cmd in ("volume", "brightness"):
        if not rest:
            raise ProtocolError(f"{cmd} needs a value (0-100, or +N / -N to step)")
        command = Command(cmd=cmd, args={"value": rest[0]})
    elif cmd == "timer":
        if not rest:
            raise ProtocolError("timer needs minutes, or 'cancel'")
        command = Command(cmd=cmd, args={"value": rest[0]})
    elif cmd == "dnd":
        command = Command(cmd=cmd, args={"value": rest[0] if rest else "toggle"})
    elif cmd == "wallpaper":
        if not rest:
            raise ProtocolError("wallpaper needs a file path")
        command = Command(cmd=cmd, args={"path": " ".join(rest)})
    elif cmd == "notify":
        if not rest:
            raise ProtocolError("notify needs a message")
        command = Command(cmd=cmd, args={"title": rest[0], "body": " ".join(rest[1:])})
    else:
        command = Command(cmd=cmd)

    _validate(command)
    return command


def parse_value(raw: Any, current: int) -> int:
    """`"+5"` steps from `current`; `"40"` is absolute.  Result is clamped."""
    text = str(raw).strip()
    if text.startswith(("+", "-")):
        try:
            return max(0, min(100, current + int(text)))
        except ValueError as exc:
            raise ProtocolError(f"not a step: {raw!r}") from exc
    try:
        return max(0, min(100, int(float(text))))
    except ValueError as exc:
        raise ProtocolError(f"not a number: {raw!r}") from exc


def parse_switch(raw: Any, current: bool) -> bool:
    """`on`/`off`/`toggle` -> bool."""
    text = str(raw).strip().lower()
    if text in ("on", "true", "1", "yes"):
        return True
    if text in ("off", "false", "0", "no"):
        return False
    if text in ("toggle", ""):
        return not current
    raise ProtocolError(f"expected on, off or toggle, got {raw!r}")


USAGE = """chillpillc -- talk to the running ChillPill shell

  toggle|show|hide <surface>   controlCenter, dashboard, clipboard,
                               launcher, wallpapers, or * for all
  volume <0-100|+N|-N>         set or step the output volume
  brightness <0-100|+N|-N>     set or step display brightness
  timer <minutes|cancel>       start or cancel the countdown
  dnd [on|off|toggle]          suppress notification popups
  wallpaper <path>             set the desktop background
  notify <title> [body]        push a notification into the stack
  status                       dump the current state as JSON
  ping                         check the shell is alive
  reload                       re-read the config file
  quit                         stop the shell
"""
