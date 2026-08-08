"""System output volume via pycaw / IAudioEndpointVolume.

Callback-driven, not polled: the endpoint pushes a change whenever anything on
the machine moves the master volume, so pressing the hardware volume key shows
up here immediately and the OSD can be genuinely instant.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

from shell.modules.base import Module
from shell.platform import IS_WINDOWS

logger = logging.getLogger(__name__)


class VolumeModule(Module):
    name = "volume"
    poll_interval_ms = None  # event-driven

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._endpoint: Any = None
        self._callback: Any = None
        self._notifier: Any = None

    # -- lifecycle ---------------------------------------------------------

    def on_start(self) -> None:
        if not IS_WINDOWS:
            self.available = False
            self.update(percent=0, muted=True, device="")
            return
        self._acquire_endpoint()

    def on_stop(self) -> None:
        self._release_endpoint()

    def _acquire_endpoint(self) -> None:
        try:
            from ctypes import POINTER, cast

            import comtypes
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            comtypes.CoInitialize()
            speakers = AudioUtilities.GetSpeakers()
            interface = speakers.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
            self._endpoint = cast(interface, POINTER(IAudioEndpointVolume))
            self._register_callback()
            self.update(device=self._device_name())
        except Exception as exc:
            self.available = False
            logger.error("no audio endpoint: %s", exc)
            self.failed.emit("audio device unavailable")

    def _register_callback(self) -> None:
        """Subscribe to endpoint volume notifications.

        pycaw's callback fires on a COM thread, so it only touches `refresh`,
        which in turn only calls `update` -- Qt marshals the resulting signal.
        """
        try:
            from comtypes import COMObject
            from pycaw.pycaw import IAudioEndpointVolumeCallback

            module = self

            class _Callback(COMObject):
                _com_interfaces_ = [IAudioEndpointVolumeCallback]

                def OnNotify(self, notify_data: Any) -> None:  # noqa: N802 - COM vtable name
                    del notify_data
                    module.refresh()

            self._callback = _Callback()
            self._endpoint.RegisterControlChangeNotify(self._callback)
        except Exception as exc:
            # Fall back to polling; a stale-by-half-a-second slider beats no slider.
            logger.warning("volume callback unavailable (%s); polling instead", exc)
            self._callback = None
            self.poll_interval_ms = 500  # instance attribute; read by Module.start()

    def _release_endpoint(self) -> None:
        if self._endpoint is not None and self._callback is not None:
            with suppress(Exception):
                self._endpoint.UnregisterControlChangeNotify(self._callback)
        self._callback = None
        self._endpoint = None
        with suppress(Exception):
            import comtypes

            comtypes.CoUninitialize()

    def _device_name(self) -> str:
        try:
            from pycaw.pycaw import AudioUtilities

            device = AudioUtilities.GetSpeakers()
            return str(AudioUtilities.CreateDevice(device).FriendlyName or "")
        except Exception:
            return ""

    # -- reads -------------------------------------------------------------

    def refresh(self) -> None:
        if self._endpoint is None:
            return
        try:
            scalar = self._endpoint.GetMasterVolumeLevelScalar()
            muted = bool(self._endpoint.GetMute())
        except Exception as exc:  # device yanked mid-session
            logger.warning("volume read failed (%s); re-acquiring endpoint", exc)
            self._release_endpoint()
            self._acquire_endpoint()
            return
        self.update(percent=int(round(scalar * 100)), muted=muted)

    # -- writes ------------------------------------------------------------

    def set_percent(self, percent: int) -> None:
        if self._endpoint is None:
            return
        clamped = max(0, min(100, int(percent)))
        try:
            self._endpoint.SetMasterVolumeLevelScalar(clamped / 100.0, None)
        except Exception as exc:
            logger.error("could not set volume: %s", exc)
            return
        self.update(percent=clamped)

    def step(self, delta: int) -> None:
        self.set_percent(int(self.get("percent", 0)) + delta)

    def set_muted(self, muted: bool) -> None:
        if self._endpoint is None:
            return
        try:
            self._endpoint.SetMute(bool(muted), None)
        except Exception as exc:
            logger.error("could not set mute: %s", exc)
            return
        self.update(muted=bool(muted))

    def toggle_mute(self) -> bool:
        new_state = not bool(self.get("muted", False))
        self.set_muted(new_state)
        return new_state
