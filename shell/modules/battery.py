"""Battery state via GetSystemPowerStatus."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from shell.modules.base import Module
from shell.platform import IS_WINDOWS

BATTERY_FLAG_NO_BATTERY = 128
UNKNOWN_PERCENT = 255
UNKNOWN_TIME = 0xFFFFFFFF


class SYSTEM_POWER_STATUS(ctypes.Structure):  # noqa: N801 - Win32 struct name
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


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
        status = SYSTEM_POWER_STATUS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):  # type: ignore[attr-defined]
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
