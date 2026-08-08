"""Notification listening via WinRT UserNotificationListener.

The riskiest module in the shell (spec §8 R2/R3).  Two things can go wrong and
both are the user's to fix, so both are reported rather than swallowed:

* the listener needs an explicit permission grant in Settings -> Privacy
* an unpackaged process needs an AUMID before WinRT will associate with it
  (`shell.platform.window.set_app_user_model_id` covers that at startup)

When access is denied the module stays alive and reports `access="denied"`, so
the control center can show a "grant access" button instead of an empty list.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from PyQt6.QtCore import pyqtSignal

from shell.modules.base import Module
from shell.platform import IS_WINDOWS

logger = logging.getLogger(__name__)

ACCESS_ALLOWED = 1  # UserNotificationListenerAccessStatus.ALLOWED
NOTIFICATION_KIND_TOAST = 0


@dataclass
class Notification:
    """One entry in the stack."""

    id: int
    app: str
    title: str
    body: str
    received: datetime = field(default_factory=datetime.now)

    @property
    def dedupe_key(self) -> str:
        return f"{self.app}\x00{self.title}\x00{self.body}"

    @property
    def age_text(self) -> str:
        seconds = (datetime.now() - self.received).total_seconds()
        if seconds < 60:
            return "now"
        if seconds < 3600:
            return f"{int(seconds // 60)}m ago"
        if seconds < 86400:
            return f"{int(seconds // 3600)}h ago"
        return f"{int(seconds // 86400)}d ago"


class NotificationsModule(Module):
    name = "notifications"
    poll_interval_ms = None  # listener pushes; see _on_changed

    #: A notification the UI has not shown yet -- drives the popup state.
    arrived = pyqtSignal(object)  # Notification
    #: The stack changed for any reason (arrival, dismissal, clear).
    stack_changed = pyqtSignal()

    def __init__(
        self,
        max_stack: int = 20,
        avoid_duplicates: bool = True,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._max_stack = max_stack
        self._avoid_duplicates = avoid_duplicates
        self._stack: list[Notification] = []
        self._seen_ids: set[int] = set()
        self._listener: Any = None
        self._token: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._dnd = False

    # -- configuration -----------------------------------------------------

    def configure(self, max_stack: int, avoid_duplicates: bool) -> None:
        self._max_stack = max_stack
        self._avoid_duplicates = avoid_duplicates
        self._trim()

    # -- lifecycle ---------------------------------------------------------

    def on_start(self) -> None:
        self.update(access="unknown", count=0, dnd=False)
        if not IS_WINDOWS:
            self.available = False
            self.update(access="unsupported")
            return
        try:
            import winrt.windows.ui.notifications.management  # noqa: F401
        except ImportError as exc:
            self.available = False
            self.update(access="missing-package")
            self.failed.emit("winrt notification package not installed")
            logger.error("notifications unavailable: %s", exc)
            return

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="chillpill-notify", daemon=True)
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._connect(), self._loop)

    def on_stop(self) -> None:
        if self._listener is not None and self._token is not None:
            with suppress(Exception):
                self._listener.remove_notification_changed(self._token)
        self._listener = None
        self._token = None
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._loop = None
        self._thread = None

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _connect(self) -> None:
        from winrt.windows.ui.notifications.management import UserNotificationListener

        try:
            listener = UserNotificationListener.current
            status = await listener.request_access_async()
        except Exception as exc:
            logger.error("notification listener unavailable: %s", exc)
            self.update(access="error")
            self.failed.emit("notification listener unavailable")
            return

        if int(status) != ACCESS_ALLOWED:
            logger.warning("notification access denied by the user")
            self.update(access="denied")
            self.failed.emit("notification access denied")
            return

        self._listener = listener
        self.update(access="allowed")
        try:
            self._token = listener.add_notification_changed(lambda *_: self._schedule_sync())
        except Exception as exc:
            # Some builds refuse the event registration but still allow reads;
            # a slow poll keeps the stack roughly current in that case.
            logger.warning("notification events unavailable (%s); polling", exc)
            self.poll_interval_ms = 5000
        await self._sync()

    def _schedule_sync(self) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._sync(), self._loop)

    def refresh(self) -> None:
        if self._listener is not None:
            self._schedule_sync()

    async def _sync(self) -> None:
        listener = self._listener
        if listener is None:
            return
        try:
            current = await listener.get_notifications_async(NOTIFICATION_KIND_TOAST)
        except Exception as exc:
            logger.debug("could not read notifications: %s", exc)
            return

        for item in current:
            try:
                self._ingest(item)
            except Exception as exc:  # a single malformed toast must not stop the rest
                logger.debug("skipping unreadable notification: %s", exc)

    def _ingest(self, item: Any) -> None:
        notification_id = int(item.id)
        if notification_id in self._seen_ids:
            return
        self._seen_ids.add(notification_id)

        app = ""
        with suppress(Exception):
            app = item.app_info.display_info.display_name or ""

        title, body = "", ""
        with suppress(Exception):
            text_elements = list(item.notification.visual.get_binding("ToastGeneric").get_text_elements())
            if text_elements:
                title = text_elements[0].text or ""
                body = "\n".join(element.text or "" for element in text_elements[1:]).strip()

        self.push(Notification(id=notification_id, app=app, title=title, body=body))

    # -- stack -------------------------------------------------------------

    def push(self, notification: Notification) -> None:
        """Add to the stack.  Public so the IPC `notify` command can use it."""
        if self._avoid_duplicates and any(n.dedupe_key == notification.dedupe_key for n in self._stack):
            return
        self._stack.insert(0, notification)
        self._trim()
        self.update(count=len(self._stack))
        self.stack_changed.emit()
        if not self._dnd:
            self.arrived.emit(notification)

    def dismiss(self, notification_id: int) -> None:
        before = len(self._stack)
        self._stack = [n for n in self._stack if n.id != notification_id]
        if len(self._stack) == before:
            return
        if self._listener is not None:
            try:
                self._listener.remove_notification(notification_id)
            except Exception as exc:  # pragma: no cover
                logger.debug("could not remove notification %s: %s", notification_id, exc)
        self.update(count=len(self._stack))
        self.stack_changed.emit()

    def clear(self) -> None:
        if self._listener is not None:
            for notification in self._stack:
                with suppress(Exception):
                    self._listener.remove_notification(notification.id)
        self._stack.clear()
        self.update(count=0)
        self.stack_changed.emit()

    def _trim(self) -> None:
        if len(self._stack) > self._max_stack:
            del self._stack[self._max_stack :]

    @property
    def stack(self) -> list[Notification]:
        return list(self._stack)

    # -- do not disturb ----------------------------------------------------

    @property
    def dnd(self) -> bool:
        return self._dnd

    def set_dnd(self, enabled: bool) -> None:
        """Suppress popups.  Notifications still stack, they just do not pop."""
        self._dnd = bool(enabled)
        self.update(dnd=self._dnd)

    def toggle_dnd(self) -> bool:
        self.set_dnd(not self._dnd)
        return self._dnd

    # -- permission --------------------------------------------------------

    @staticmethod
    def open_permission_settings() -> bool:
        """Deep-link to Settings so a denied user has somewhere to go."""
        from shell.platform.system import open_settings

        return open_settings("privacy-notifications")
