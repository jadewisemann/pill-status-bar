"""Display brightness: WMI for internal panels, DDC/CI for external monitors.

Two completely different mechanisms behind one percentage.  Laptop panels
answer to WmiMonitorBrightnessMethods; desktop monitors only answer to DDC/CI
over the video cable, which is slow (tens of milliseconds per call) and
sometimes lies, so every DDC call runs off the GUI thread.
"""

from __future__ import annotations

import logging
from typing import Any

from shell.modules.base import Module
from shell.platform import IS_WINDOWS

logger = logging.getLogger(__name__)

VCP_LUMINANCE = 0x10


class BrightnessModule(Module):
    name = "brightness"
    #: WMI pushes changes through WmiMonitorBrightnessEvent, but subscribing
    #: costs a permanent COM sink; a slow poll covers the same ground.
    poll_interval_ms = 10_000

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._backend: str = "none"
        self._ddc_handles: list[Any] = []

    # -- lifecycle ---------------------------------------------------------

    def on_start(self) -> None:
        if not IS_WINDOWS:
            self.available = False
            self.update(percent=0, backend="none")
            return
        if self._try_wmi():
            self._backend = "wmi"
        elif self._open_ddc_handles():
            self._backend = "ddc"
        else:
            self._backend = "none"
            self.available = False
            self.failed.emit("no controllable display found")
        self.update(backend=self._backend)

    def on_stop(self) -> None:
        self._close_ddc_handles()

    # -- WMI (internal panel) ----------------------------------------------

    def _wmi_namespace(self) -> Any:
        import wmi

        return wmi.WMI(namespace="wmi")

    def _try_wmi(self) -> bool:
        try:
            monitors = self._wmi_namespace().WmiMonitorBrightness()
            return bool(monitors)
        except Exception as exc:
            logger.debug("WMI brightness unavailable: %s", exc)
            return False

    def _read_wmi(self) -> int | None:
        try:
            monitors = self._wmi_namespace().WmiMonitorBrightness()
            return int(monitors[0].CurrentBrightness) if monitors else None
        except Exception as exc:
            logger.debug("WMI brightness read failed: %s", exc)
            return None

    def _write_wmi(self, percent: int) -> bool:
        try:
            methods = self._wmi_namespace().WmiMonitorBrightnessMethods()
            for method in methods:
                method.WmiSetBrightness(percent, 0)  # 0 = apply immediately
            return bool(methods)
        except Exception as exc:
            logger.error("WMI brightness write failed: %s", exc)
            return False

    # -- DDC/CI (external monitors) ----------------------------------------

    def _open_ddc_handles(self) -> bool:
        try:
            import ctypes
            from ctypes.wintypes import DWORD

            import win32api

            from vendor.win32.bindings.dxva2 import PHYSICAL_MONITOR, dxva2
        except Exception as exc:
            logger.debug("DDC/CI unavailable: %s", exc)
            return False

        handles: list[Any] = []
        try:
            for monitor, _dc, _rect in win32api.EnumDisplayMonitors():
                hmonitor = int(monitor)
                count = DWORD()
                if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmonitor, ctypes.byref(count)):
                    continue
                array = (PHYSICAL_MONITOR * count.value)()
                if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmonitor, count.value, array):
                    continue
                handles.extend(array[i].hPhysicalMonitor for i in range(count.value))
        except Exception as exc:
            logger.debug("could not enumerate physical monitors: %s", exc)
            return False
        self._ddc_handles = handles
        return bool(handles)

    def _close_ddc_handles(self) -> None:
        if not self._ddc_handles:
            return
        try:
            import ctypes

            from vendor.win32.bindings.dxva2 import PHYSICAL_MONITOR, dxva2

            array = (PHYSICAL_MONITOR * len(self._ddc_handles))()
            for index, handle in enumerate(self._ddc_handles):
                array[index].hPhysicalMonitor = handle
            # Not bound in vendor/; called straight off the same DLL handle.
            dxva2.DestroyPhysicalMonitors(len(self._ddc_handles), ctypes.byref(array))
        except Exception:  # pragma: no cover
            pass
        self._ddc_handles = []

    def _read_ddc(self) -> int | None:
        if not self._ddc_handles:
            return None
        try:
            import ctypes
            from ctypes.wintypes import DWORD

            from vendor.win32.bindings.dxva2 import dxva2

            current = DWORD()
            maximum = DWORD()
            ok = dxva2.GetVCPFeatureAndVCPFeatureReply(
                self._ddc_handles[0], VCP_LUMINANCE, None, ctypes.byref(current), ctypes.byref(maximum)
            )
            if not ok or not maximum.value:
                return None
            return int(round(current.value * 100 / maximum.value))
        except Exception as exc:
            logger.debug("DDC read failed: %s", exc)
            return None

    def _write_ddc(self, percent: int) -> bool:
        if not self._ddc_handles:
            return False
        try:
            import ctypes
            from ctypes.wintypes import DWORD

            from vendor.win32.bindings.dxva2 import dxva2

            maximum = DWORD()
            current = DWORD()
            written = False
            for handle in self._ddc_handles:
                if not dxva2.GetVCPFeatureAndVCPFeatureReply(
                    handle, VCP_LUMINANCE, None, ctypes.byref(current), ctypes.byref(maximum)
                ):
                    continue
                value = int(round(percent * maximum.value / 100))
                written |= bool(dxva2.SetVCPFeature(handle, VCP_LUMINANCE, value))
            return written
        except Exception as exc:
            logger.error("DDC write failed: %s", exc)
            return False

    # -- public surface ----------------------------------------------------

    def refresh(self) -> None:
        if self._backend == "none":
            return
        reader = self._read_wmi if self._backend == "wmi" else self._read_ddc
        self.run_async(reader, self._apply_read)

    def _apply_read(self, percent: int | None) -> None:
        if percent is not None:
            self.update(percent=int(percent))

    def set_percent(self, percent: int) -> None:
        if self._backend == "none":
            return
        clamped = max(0, min(100, int(percent)))
        # Show the new value immediately; the write confirms it a moment later.
        self.update(percent=clamped)
        writer = self._write_wmi if self._backend == "wmi" else self._write_ddc
        self.run_async(lambda: writer(clamped))

    def step(self, delta: int) -> None:
        self.set_percent(int(self.get("percent", 50)) + delta)
