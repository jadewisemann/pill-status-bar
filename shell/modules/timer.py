"""Countdown timer.

Small, but it earns a module: the pill bar shows the remaining time, the OSD
shows it while it is being set, and the control center offers the presets --
three surfaces, one countdown.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import pyqtSignal

from shell.modules.base import Module


class TimerModule(Module):
    name = "timer"
    poll_interval_ms = 1000

    finished = pyqtSignal()

    def __init__(self, presets: list[int] | None = None, parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._presets = presets or [1, 5, 10, 15, 30]
        self._deadline: float | None = None
        self._paused_remaining: float | None = None

    @property
    def presets(self) -> list[int]:
        return list(self._presets)

    def set_presets(self, presets: list[int]) -> None:
        self._presets = list(presets)

    # -- control -----------------------------------------------------------

    def start_minutes(self, minutes: float) -> None:
        self._deadline = time.monotonic() + minutes * 60
        self._paused_remaining = None
        self.refresh()

    def cancel(self) -> None:
        self._deadline = None
        self._paused_remaining = None
        self.update(running=False, remaining=0, text="")

    def pause(self) -> None:
        if self._deadline is None:
            return
        self._paused_remaining = max(0.0, self._deadline - time.monotonic())
        self._deadline = None
        self.update(running=False, paused=True)

    def resume(self) -> None:
        if self._paused_remaining is None:
            return
        self._deadline = time.monotonic() + self._paused_remaining
        self._paused_remaining = None
        self.update(paused=False)
        self.refresh()

    # -- state -------------------------------------------------------------

    def refresh(self) -> None:
        if self._deadline is None:
            return
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            self._deadline = None
            self.update(running=False, remaining=0, text="")
            self.finished.emit()
            return
        self.update(running=True, paused=False, remaining=remaining, text=format_remaining(remaining))

    @property
    def running(self) -> bool:
        return self._deadline is not None


def format_remaining(seconds: float) -> str:
    """`90` -> "1:30", `3700` -> "1:01:40"."""
    total = int(seconds + 0.5)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
