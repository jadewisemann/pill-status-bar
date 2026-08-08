"""Minimal stand-in for yasb's `core.events.service.EventService`.

`vendor/win32/hotkeys.py` is vendored verbatim and dispatches hotkey presses
through yasb's application-wide event bus.  ChillPill does not have that bus, so
this module provides the two-method surface hotkeys.py touches
(`EventService()` construction and `emit_event`) backed by a Qt signal.

Nothing else should import this directly -- use `shell.platform.hotkeys`.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class _Bus(QObject):
    event = pyqtSignal(str, tuple)


class EventService:
    """Process-wide singleton event bus.

    Signature-compatible with the yasb class for the subset hotkeys.py uses:
    `emit_event(name, *args)`.  Subscribe with `EventService().bus.event`.
    """

    _bus: _Bus | None = None

    def __new__(cls) -> "EventService":
        instance = super().__new__(cls)
        if EventService._bus is None:
            EventService._bus = _Bus()
        return instance

    @property
    def bus(self) -> _Bus:
        assert EventService._bus is not None
        return EventService._bus

    def emit_event(self, event_name: str, *args: object) -> None:
        self.bus.event.emit(event_name, tuple(args))

    def register_event(self, *_args: object, **_kwargs: object) -> None:  # pragma: no cover - API parity
        """yasb widgets call this to declare interest; ChillPill filters on receive."""

    def clear(self) -> None:  # pragma: no cover - API parity
        """yasb tears the bus down on reload; ChillPill never does."""
