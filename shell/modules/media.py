"""Now-playing state via WinRT GlobalSystemMediaTransportControlsSessionManager.

The Windows equivalent of MPRIS.  Everything here is async on the WinRT side,
so the module drives a small asyncio loop on a worker thread and pushes results
back through `update()`.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import suppress
from typing import Any

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

from shell.modules.base import Module
from shell.platform import IS_WINDOWS

logger = logging.getLogger(__name__)

PLAYBACK_PLAYING = 4  # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING


class MediaModule(Module):
    name = "media"
    poll_interval_ms = None  # WinRT pushes session/property/timeline events

    #: Emitted when a *different* track starts playing, which is what drives the
    #: auto-popup.  Kept separate from `changed` so a pause/resume on the same
    #: track does not re-pop the pill.
    track_started = pyqtSignal()
    #: New album art is ready (decoding happens off the GUI thread).
    artwork_ready = pyqtSignal(QPixmap)

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._manager: Any = None
        self._manager_token: Any = None
        self._session: Any = None
        self._tokens: list[tuple[Any, str, Any]] = []
        self._last_track_key: str | None = None
        self._position_timer: QTimer | None = None

    # -- lifecycle ---------------------------------------------------------

    def on_start(self) -> None:
        if not IS_WINDOWS:
            self.available = False
            self.update(active=False)
            return
        try:
            import winrt.windows.media.control  # noqa: F401
        except ImportError as exc:
            self.available = False
            self.failed.emit("winrt media package not installed")
            logger.error("media unavailable: %s", exc)
            return

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="chillpill-media", daemon=True)
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._connect(), self._loop)

        # Position has no change event; tick it while something is playing.
        self._position_timer = QTimer(self)
        self._position_timer.setInterval(1000)
        self._position_timer.timeout.connect(self._tick_position)
        self._position_timer.start()

    def on_stop(self) -> None:
        """Release the WinRT objects on the thread that owns them, then stop.

        Every object here belongs to the COM apartment of the thread that
        created it -- this module's loop thread.  Dropping the last reference
        from another thread marshals the release back to that apartment, so it
        has to happen while the loop is still turning.  Releasing after the
        loop stops means waiting on a reply nobody is left to send: the shell
        hangs on quit rather than shutting down slowly.
        """
        if self._position_timer is not None:
            self._position_timer.stop()
            self._position_timer = None

        loop, thread = self._loop, self._thread
        self._loop = None
        self._thread = None

        if loop is None or thread is None or not thread.is_alive():
            # Never started, or the thread is already gone: nothing was
            # marshalled, so releasing here is safe.
            self._release_manager()
            return

        released = threading.Event()

        def release_and_stop() -> None:
            try:
                self._release_manager()
            finally:
                released.set()
                loop.stop()

        loop.call_soon_threadsafe(release_and_stop)
        if not released.wait(timeout=2):
            # The loop is wedged. Deliberately leave `_manager` set: clearing
            # it here is the deadlock this method exists to avoid, and a
            # reference held until the process exits costs nothing.
            logger.warning("media loop did not release its WinRT objects; leaving them to process exit")
            loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)

    def _release_manager(self) -> None:
        """Unhook and drop the session manager.

        The event registration keeps the manager pointing back at this module;
        left in place, a manager the system still holds can call into a module
        that no longer exists.
        """
        self._detach_session()
        if self._manager is not None and self._manager_token is not None:
            with suppress(Exception):
                self._manager.remove_current_session_changed(self._manager_token)
        self._manager_token = None
        self._manager = None

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro: Any) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    # -- WinRT wiring ------------------------------------------------------

    async def _connect(self) -> None:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        )

        try:
            self._manager = await SessionManager.request_async()
        except Exception as exc:
            logger.error("could not get media session manager: %s", exc)
            self.failed.emit("media session manager unavailable")
            return
        self._manager_token = self._manager.add_current_session_changed(
            lambda *_: self._submit(self._attach_current_session())
        )
        await self._attach_current_session()

    async def _attach_current_session(self) -> None:
        self._detach_session()
        try:
            session = self._manager.get_current_session() if self._manager else None
        except Exception:
            session = None
        self._session = session
        if session is None:
            self.update(active=False, title="", artist="", album="", playing=False, app_id="")
            return
        self._tokens = [
            (
                session,
                "media_properties_changed",
                session.add_media_properties_changed(lambda *_: self._submit(self._read_properties())),
            ),
            (session, "playback_info_changed", session.add_playback_info_changed(lambda *_: self._read_playback())),
            (
                session,
                "timeline_properties_changed",
                session.add_timeline_properties_changed(lambda *_: self._read_timeline()),
            ),
        ]
        await self._read_properties()
        self._read_playback()
        self._read_timeline()

    def _detach_session(self) -> None:
        for session, event, token in self._tokens:
            with suppress(Exception):
                getattr(session, f"remove_{event}")(token)
        self._tokens = []
        self._session = None

    # -- reads -------------------------------------------------------------

    async def _read_properties(self) -> None:
        session = self._session
        if session is None:
            return
        try:
            props = await session.try_get_media_properties_async()
        except Exception as exc:
            logger.debug("media properties unavailable: %s", exc)
            return
        title = props.title or ""
        artist = props.artist or props.album_artist or ""
        album = props.album_title or ""
        app_id = ""
        with suppress(Exception):
            app_id = session.source_app_user_model_id or ""
        self.update(active=True, title=title, artist=artist, album=album, app_id=app_id)

        key = f"{app_id}\x00{title}\x00{artist}"
        if key != self._last_track_key:
            self._last_track_key = key
            self.track_started.emit()
        if props.thumbnail is not None:
            await self._read_thumbnail(props.thumbnail)

    async def _read_thumbnail(self, reference: Any) -> None:
        """Pull the album art stream into a QPixmap."""
        try:
            from winrt.windows.storage.streams import Buffer, InputStreamOptions

            stream = await reference.open_read_async()
            size = int(stream.size)
            if not size:
                return
            buffer = Buffer(size)
            await stream.read_async(buffer, size, InputStreamOptions.NONE)
            data = bytes(buffer)
        except Exception as exc:
            logger.debug("album art unavailable: %s", exc)
            return
        image = QImage.fromData(data)
        if image.isNull():
            return
        self.artwork_ready.emit(QPixmap.fromImage(image))

    def _read_playback(self) -> None:
        session = self._session
        if session is None:
            return
        try:
            info = session.get_playback_info()
            playing = int(info.playback_status) == PLAYBACK_PLAYING
            controls = info.controls
            self.update(
                playing=playing,
                can_play_pause=bool(controls.is_play_enabled or controls.is_pause_enabled),
                can_next=bool(controls.is_next_enabled),
                can_previous=bool(controls.is_previous_enabled),
            )
        except Exception as exc:
            logger.debug("playback info unavailable: %s", exc)

    def _read_timeline(self) -> None:
        session = self._session
        if session is None:
            return
        try:
            timeline = session.get_timeline_properties()
            self.update(
                position=_ticks_to_seconds(timeline.position),
                duration=_ticks_to_seconds(timeline.end_time) - _ticks_to_seconds(timeline.start_time),
            )
        except Exception as exc:
            logger.debug("timeline unavailable: %s", exc)

    def _tick_position(self) -> None:
        if not self.get("playing"):
            return
        position = float(self.get("position", 0.0)) + 1.0
        duration = float(self.get("duration", 0.0))
        self.update(position=min(position, duration) if duration else position)

    # -- controls ----------------------------------------------------------

    def _control(self, method: str) -> None:
        session = self._session
        if session is None:
            return

        async def call() -> None:
            try:
                await getattr(session, method)()
            except Exception as exc:
                logger.debug("media control %s failed: %s", method, exc)

        self._submit(call())

    def play_pause(self) -> None:
        self._control("try_toggle_play_pause_async")

    def next_track(self) -> None:
        self._control("try_skip_next_async")

    def previous_track(self) -> None:
        self._control("try_skip_previous_async")

    def seek(self, seconds: float) -> None:
        """Jump to an absolute position; drives the scrubbable progress bar."""
        session = self._session
        if session is None:
            return
        ticks = int(max(0.0, seconds) * 10_000_000)

        async def call() -> None:
            try:
                await session.try_change_playback_position_async(ticks)
            except Exception as exc:
                logger.debug("seek failed: %s", exc)

        self._submit(call())
        self.update(position=max(0.0, seconds))


def _ticks_to_seconds(value: Any) -> float:
    """WinRT TimeSpan -> seconds.  Accepts both timedelta and raw-tick shapes."""
    if value is None:
        return 0.0
    total = getattr(value, "total_seconds", None)
    if callable(total):
        return float(total())
    duration = getattr(value, "duration", value)
    try:
        return float(duration) / 10_000_000.0
    except (TypeError, ValueError):
        return 0.0
