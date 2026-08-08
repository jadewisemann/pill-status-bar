"""Wall clock and calendar facts."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QDateTime, QTime

from shell.modules.base import Module


class ClockModule(Module):
    name = "clock"
    #: Once a second regardless of format -- a seconds-less format still needs
    #: to flip on the minute boundary, and a 1s tick is cheaper than the
    #: arithmetic to schedule the exact boundary.
    poll_interval_ms = 1000

    def __init__(self, clock_format: str = "hh:mm", parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._format = clock_format

    def set_format(self, clock_format: str) -> None:
        self._format = clock_format
        self.refresh()

    def refresh(self) -> None:
        now = QDateTime.currentDateTime()
        self.update(
            text=now.time().toString(self._format),
            date=now.date().toString("dddd, d MMMM"),
            date_short=now.date().toString("ddd d MMM"),
            iso=now.toString("yyyy-MM-dd hh:mm:ss"),
            hour=now.time().hour(),
            minute=now.time().minute(),
        )

    @staticmethod
    def format_now(clock_format: str) -> str:
        """Format the current time without instantiating a module."""
        return QTime.currentTime().toString(clock_format)

    @staticmethod
    def now() -> datetime:
        return datetime.now()
