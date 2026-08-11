"""Battery state via GetSystemPowerStatus."""

from __future__ import annotations

import logging

from shell.modules.base import Module
from shell.platform import IS_WINDOWS

logger = logging.getLogger(__name__)

BATTERY_FLAG_NO_BATTERY = 128
UNKNOWN_PERCENT = 255
UNKNOWN_TIME = 0xFFFFFFFF


class BatteryModule(Module):
    name = "battery"
    #: No change notification worth wiring up -- the value moves once a minute
    #: at most, and a 30s poll is invisible in a task manager.
    poll_interval_ms = 30_000

    def on_start(self) -> None:
        self.available = IS_WINDOWS
        if not self.available:
            self.update(present=False, percent=0, charging=False)

    def refresh(self) -> None:
        if not IS_WINDOWS:
            return
        # The vendored binding, not a local struct and not `ctypes.windll`.
        # `windll.kernel32` is a process-wide singleton and prototypes are
        # cached on it, so vendor/win32/bindings/kernel32.py -- imported the
        # moment anything touches the pipe or the AppBar -- has already set
        # `GetSystemPowerStatus.argtypes` to a pointer to *its*
        # SYSTEM_POWER_STATUS. A second, identical struct declared here is a
        # different type to ctypes, and the call raises ArgumentError rather
        # than returning a wrong answer. Two definitions of one Win32 struct in
        # one process is the bug; using the vendored one is the fix.
        try:
            import ctypes

            from vendor.win32.bindings.kernel32 import kernel32
            from vendor.win32.structs import SYSTEM_POWER_STATUS
        except Exception as exc:
            logger.debug("kernel32 power status unavailable: %s", exc)
            self.update(present=False)
            return

        status = SYSTEM_POWER_STATUS()
        if not kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            self.update(present=False)
            return

        flag = status.BatteryFlag & 0xFF
        percent = status.BatteryLifePercent & 0xFF
        present = flag != BATTERY_FLAG_NO_BATTERY and percent != UNKNOWN_PERCENT
        on_ac = (status.ACLineStatus & 0xFF) == 1
        remaining = status.BatteryLifeTime
        self.update(
            present=present,
            percent=percent if percent != UNKNOWN_PERCENT else 0,
            charging=on_ac and present and percent < 100,
            on_ac=on_ac,
            seconds_left=None if remaining == UNKNOWN_TIME else int(remaining),
        )

    # -- derived views -----------------------------------------------------

    @property
    def time_left_text(self) -> str:
        seconds = self.get("seconds_left")
        if not seconds:
            return "plugged in" if self.get("on_ac") else ""
        hours, minutes = divmod(int(seconds) // 60, 60)
        return f"{hours}h {minutes:02d}m left" if hours else f"{minutes}m left"
