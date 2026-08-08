"""Global hotkeys.

Thin adapter over vendor's `RegisterHotKey` listener thread.  ChillPill binds
whole IPC commands rather than yasb-style widget actions, so a binding's
"action" is simply the command string the pill will run.

Default bindings mirror the original shell's Hyprland keys (spec §1.5), with
`super` standing in for the Hyprland `SUPER` modifier.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSignal

from shell.platform import IS_WINDOWS

logger = logging.getLogger(__name__)

#: hotkey string -> IPC command, mirroring the original Hyprland binds.
DEFAULT_BINDINGS: dict[str, str] = {
    "super+c": "toggle controlCenter",
    "super+v": "toggle clipboard",
    "super+d": "toggle dashboard",
    "super+space": "toggle launcher",
    "super+w": "toggle wallpapers",
    "super+shift+n": "toggle dnd",
    "super+escape": "hide *",
}

#: Marker put in the vendored binding's `widget_name` slot so the dispatcher can
#: tell our events apart from anything else on the shared bus.
_WIDGET = "chillpill"


class HotkeyManager(QObject):
    """Registers hotkeys and re-emits them as IPC command strings."""

    triggered = pyqtSignal(str)  # command

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener: object | None = None
        self._dispatcher: object | None = None

    def start(self, bindings: dict[str, str] | None = None) -> int:
        """Register `bindings`; returns how many were accepted by Windows.

        A hotkey already owned by another app fails individually and is logged
        by the listener -- the rest still register, which is the behaviour you
        want when e.g. PowerToys already owns super+space.
        """
        if not IS_WINDOWS:
            logger.info("global hotkeys are Windows-only; skipping")
            return 0
        if self._listener is not None:
            return 0

        bindings = bindings if bindings is not None else DEFAULT_BINDINGS
        try:
            from vendor.compat.events import EventService
            from vendor.win32.hotkeys import HotkeyBinding, HotkeyDispatcher, HotkeyListener, parse_hotkey
        except ImportError as exc:  # pragma: no cover
            logger.error("hotkey support unavailable: %s", exc)
            return 0

        parsed: list[object] = []
        for keys, command in bindings.items():
            combo = parse_hotkey(keys)
            if combo is None:
                logger.warning("unparseable hotkey %r, skipped", keys)
                continue
            modifiers, vk = combo
            parsed.append(
                HotkeyBinding(
                    hotkey=keys,
                    widget_name=_WIDGET,
                    action=command,
                    vk=vk,
                    modifiers=modifiers,
                    screen="cursor",
                )
            )
        if not parsed:
            return 0

        EventService().bus.event.connect(self._on_bus_event)
        self._dispatcher = HotkeyDispatcher()
        self._listener = HotkeyListener(parsed, self._dispatcher, bar_screens=set())
        self._listener.start()  # type: ignore[attr-defined]
        return len(parsed)

    def stop(self) -> None:
        if self._listener is None:
            return
        try:
            self._listener.stop()  # type: ignore[attr-defined]
            self._listener.wait(2000)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover
            logger.debug("hotkey listener shutdown: %s", exc)
        self._listener = None
        self._dispatcher = None

    def _on_bus_event(self, name: str, args: tuple) -> None:
        if name != "handle_widget_hotkey" or not args:
            return
        widget_name = args[0] if args else ""
        if widget_name != _WIDGET:
            return
        command = args[1] if len(args) > 1 else ""
        if command:
            self.triggered.emit(str(command))


def bindings_from_config(raw: dict[str, str] | None) -> dict[str, str]:
    """Merge user-supplied bindings over the defaults; empty value disables one."""
    merged = dict(DEFAULT_BINDINGS)
    for keys, command in (raw or {}).items():
        if command:
            merged[keys] = command
        else:
            merged.pop(keys, None)
    return merged


def describe(bindings: dict[str, str]) -> str:
    """Human-readable dump used by `chillpillc keys`."""
    width = max((len(k) for k in bindings), default=0)
    return "\n".join(f"{k.ljust(width)}  {v}" for k, v in sorted(bindings.items()))
