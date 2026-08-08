"""Application wiring.

Everything else in the package is deliberately unaware of everything else; this
is where they are introduced to each other.  Roughly:

    config  ->  modules  ->  surfaces  ->  pill
                   |            |
                   +-> app <----+  (timers, IPC, hotkeys, tray, power)
"""

from __future__ import annotations

import logging
import queue
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtGui import QAction, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from shell import modules as modules_pkg
from shell.config import Config, ConfigStore, config_path, write_default_config
from shell.ipc.protocol import (
    Command,
    ProtocolError,
    parse_switch,
    parse_value,
    resolve_target,
)
from shell.ipc.server import IpcServer, reply_error, reply_ok
from shell.modules.notifications import Notification
from shell.pill import Pill
from shell.platform import IS_WINDOWS, flow
from shell.platform.hotkeys import HotkeyManager, bindings_from_config
from shell.platform.system import (
    lock_session,
    log_off,
    open_path,
    reboot,
    shut_down,
    suspend,
)
from shell.platform.window import AppBar, foreground_is_fullscreen
from shell.state import PillState, PillStateMachine
from shell.surfaces import (
    ClipboardHistory,
    ControlCenter,
    Dashboard,
    FullscreenToast,
    Launcher,
    MediaPopup,
    NotificationPopup,
    Osd,
    PillBar,
    WallpaperSwitcher,
)

logger = logging.getLogger(__name__)

FULLSCREEN_CHECK_MS = 1500
TOPMOST_REASSERT_MS = 5000


class ChillPillApp(QObject):
    """The shell process."""

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self._app = app
        self._store = ConfigStore()
        self._config: Config = self._store.config
        self._machine = PillStateMachine()
        self._registry = modules_pkg.build_registry(self._config, self)
        self._launcher_backend = flow.resolve_backend(self._config.launcher_backend)

        self._pill = Pill(self._config, self._machine)
        self._build_surfaces()
        self._build_timers()
        self._build_tray()

        self._appbar = AppBar()
        self._ipc = IpcServer(self)
        self._hotkeys = HotkeyManager(self)

        self._store.changed.connect(self._on_config_changed)
        self._ipc.command_received.connect(self._on_command)
        self._hotkeys.triggered.connect(self._run_command_line)

    # -- construction ------------------------------------------------------

    def _build_surfaces(self) -> None:
        registry = self._registry
        self.pill_bar = PillBar(registry, self._config)
        self.control_center = ControlCenter(registry, self._config)
        self.dashboard = Dashboard(registry, self._config)
        self.osd = Osd(registry)
        self.notification_popup = NotificationPopup(registry)
        self.media_popup = MediaPopup(registry)
        self.launcher = Launcher(registry)
        self.clipboard = ClipboardHistory(registry)
        self.wallpapers = WallpaperSwitcher(registry, self._config)

        for surface in (
            self.pill_bar,
            self.control_center,
            self.dashboard,
            self.osd,
            self.notification_popup,
            self.media_popup,
            self.launcher,
            self.clipboard,
            self.wallpapers,
        ):
            self._pill.add_surface(surface)

        self.toast = FullscreenToast()

        self.pill_bar.surface_requested.connect(self._toggle_state)
        self.control_center.power_action.connect(self._on_power_action)
        self.dashboard.power_action.connect(self._on_power_action)
        self.media_popup.expand_requested.connect(lambda: self._open_state(PillState.CONTROL_CENTER))
        self.notification_popup.activated.connect(lambda _id: self._open_state(PillState.CONTROL_CENTER))
        self.toast.activated.connect(lambda _id: self._open_state(PillState.CONTROL_CENTER))
        for surface in (self.launcher, self.clipboard, self.wallpapers):
            surface.dismissed.connect(self._close_all)

        # The pill bar's modules stay live for the whole session; the rest are
        # acquired when their surface is shown.
        self.pill_bar.on_shown()
        self._connect_transients()

    def _connect_transients(self) -> None:
        """Hook the events that pop the pill open on their own."""
        volume = self._registry.get("volume")
        brightness = self._registry.get("brightness")
        media = self._registry.get("media")
        notifications = self._registry.get("notifications")
        timer = self._registry.get("timer")

        volume.changed.connect(self._on_volume_changed)
        brightness.changed.connect(self._on_brightness_changed)
        media.track_started.connect(self._on_track_started)  # type: ignore[attr-defined]
        media.artwork_ready.connect(self.media_popup.set_artwork)  # type: ignore[attr-defined]
        media.artwork_ready.connect(self.control_center.set_artwork)  # type: ignore[attr-defined]
        media.changed.connect(self._sync_media_context)
        notifications.arrived.connect(self._on_notification)  # type: ignore[attr-defined]
        notifications.failed.connect(self._on_notification_problem)
        timer.finished.connect(self._on_timer_finished)  # type: ignore[attr-defined]

    def _build_timers(self) -> None:
        self._osd_timer = QTimer(self)
        self._osd_timer.setSingleShot(True)
        self._osd_timer.timeout.connect(lambda: self._machine.close(PillState.OSD))

        self._notification_timer = QTimer(self)
        self._notification_timer.setSingleShot(True)
        self._notification_timer.timeout.connect(lambda: self._machine.close(PillState.NOTIFICATION))

        self._media_timer = QTimer(self)
        self._media_timer.setSingleShot(True)
        self._media_timer.timeout.connect(lambda: self._machine.close(PillState.MEDIA_POPUP))

        self._fullscreen_timer = QTimer(self)
        self._fullscreen_timer.setInterval(FULLSCREEN_CHECK_MS)
        self._fullscreen_timer.timeout.connect(self._check_fullscreen)

        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(TOPMOST_REASSERT_MS)
        self._topmost_timer.timeout.connect(self._pill.reassert_topmost)

    def _build_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(_pill_icon())
        self._tray.setToolTip("ChillPill")

        menu = QMenu()
        for label, slot in (
            ("Control center", lambda: self._toggle_state(PillState.CONTROL_CENTER)),
            ("Dashboard", lambda: self._toggle_state(PillState.DASHBOARD)),
            ("Open config", lambda: open_path(str(config_path()))),
            ("Reload config", self._store.reload),
            ("Quit", self.quit),
        ):
            action = QAction(label, menu)
            action.triggered.connect(slot)  # type: ignore[arg-type]
            menu.addAction(action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        write_default_config()
        self._pill.show()
        self._pill.attach_to_windows()
        self._pill.apply_morph(animated=False)
        self._tray.show()

        if IS_WINDOWS:
            screen = self._pill.target_screen()
            if screen is not None:
                reserved = self._config.pill_top_margin + self._pill.height() + self._config.pill_bottom_margin
                self._appbar.create(int(self._pill.winId()), screen, reserved, edge=AppBar.EDGE_TOP)

        self._ipc.start()
        registered = self._hotkeys.start(bindings_from_config(None))
        if registered:
            logger.info("registered %d global hotkeys", registered)
        self._store.start_watching()
        if self._launcher_backend == "flow" and not flow.plugin_installed():
            logger.info(
                "Flow Launcher is installed but the ChillPill plugin is not; see integrations/flow_plugin/README.md"
            )
        self._fullscreen_timer.start()
        self._topmost_timer.start()
        logger.info("ChillPill started; config at %s", self._store.path)

    def quit(self) -> None:
        logger.info("shutting down")
        self._fullscreen_timer.stop()
        self._topmost_timer.stop()
        self._store.stop_watching()
        self._hotkeys.stop()
        self._ipc.stop()
        self._appbar.remove()  # never leave the desktop working area shrunk
        self._registry.stop_all()
        self._tray.hide()
        self.toast.close()
        self._pill.close()
        self._app.quit()

    # -- state helpers -----------------------------------------------------

    def _open_state(self, state: PillState) -> None:
        if self._delegate_to_flow(state):
            return
        self._machine.open(state)
        self._after_exclusive_change(state)

    def _toggle_state(self, state: PillState) -> None:
        if self._delegate_to_flow(state):
            return
        opened = self._machine.toggle(state)
        self._after_exclusive_change(state if opened else None)

    def _delegate_to_flow(self, state: PillState) -> bool:
        """Hand the launcher and clipboard to Flow when it is in charge.

        Returns True when Flow took the request, in which case the pill stays
        as it is.  Falling back to the built-in surface on a failed launch
        matters: an uninstalled-but-still-configured Flow should not leave the
        user with a key that does nothing.
        """
        if state not in (PillState.LAUNCHER, PillState.CLIPBOARD):
            return False
        if self._launcher_backend != "flow":
            return False
        if flow.show():
            self._close_all()
            return True
        logger.warning("Flow Launcher did not start; using the built-in surface")
        return False

    def _close_all(self) -> None:
        self._machine.close_all()
        self._after_exclusive_change(None)

    def _after_exclusive_change(self, opened: PillState | None) -> None:
        """The launcher and clipboard need the keyboard; nothing else does.

        The pill is normally WS_EX_NOACTIVATE so clicking it never disturbs the
        focused app.  Two surfaces have a text field, so for those -- and only
        while they are open -- the window takes the foreground (spec §8 R7).
        """
        needs_focus = opened in (PillState.LAUNCHER, PillState.CLIPBOARD)
        if not IS_WINDOWS:
            return
        from shell.platform.window import force_foreground, set_focusable

        hwnd = int(self._pill.winId())
        set_focusable(hwnd, needs_focus)
        if needs_focus:
            force_foreground(hwnd)
            surface = self._pill.surface(opened) if opened else None
            if surface is not None:
                surface.setFocus(Qt.FocusReason.OtherFocusReason)

    # -- transient triggers ------------------------------------------------

    def _flash(self, state: PillState, duration_ms: int, timer: QTimer) -> None:
        """Show a transient state for `duration_ms`, restarting if re-triggered."""
        self._machine.open(state)
        timer.start(max(1, duration_ms))

    def _on_volume_changed(self) -> None:
        if not self._config.osd_enabled:
            return
        volume = self._registry.get("volume")
        self.osd.show_volume(int(volume.get("percent", 0)), bool(volume.get("muted", False)))
        self._flash(PillState.OSD, self._config.osd_duration, self._osd_timer)

    def _on_brightness_changed(self) -> None:
        if not self._config.osd_enabled:
            return
        self.osd.show_brightness(int(self._registry.get("brightness").get("percent", 0)))
        self._flash(PillState.OSD, self._config.osd_duration, self._osd_timer)

    def _on_track_started(self) -> None:
        if not self._config.media_popup_duration:
            return
        if self._machine.exclusive is not None:
            return  # a panel is open and already shows the player
        self._flash(PillState.MEDIA_POPUP, self._config.media_popup_duration, self._media_timer)

    def _sync_media_context(self) -> None:
        self._machine.update_context(media_active=bool(self._registry.get("media").get("active", False)))

    def _on_notification(self, notification: Notification) -> None:
        if self._pill.isHidden():
            # Over a fullscreen app the pill is gone, so the toast slides in.
            self.toast.present(notification, self._config.notification_display_time)
            return
        self.notification_popup.show_notification(notification)
        self._flash(PillState.NOTIFICATION, self._config.notification_display_time, self._notification_timer)

    def _on_notification_problem(self, message: str) -> None:
        """Surface a permission problem where the user will actually see it."""
        logger.warning("notifications: %s", message)
        if "denied" in message:
            self._tray.showMessage(
                "ChillPill needs notification access",
                "Settings > Privacy & security > Notifications > let apps access notifications",
                QSystemTrayIcon.MessageIcon.Warning,
                8000,
            )

    def _on_timer_finished(self) -> None:
        self.osd.show_timer(0)
        self._flash(PillState.OSD, 2000, self._osd_timer)
        self._tray.showMessage("Timer finished", "", QSystemTrayIcon.MessageIcon.Information, 4000)

    def _check_fullscreen(self) -> None:
        self._pill.set_hidden_for_fullscreen(foreground_is_fullscreen())

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_state(PillState.CONTROL_CENTER)

    # -- power -------------------------------------------------------------

    def _on_power_action(self, action: str) -> None:
        if action == "menu":
            self._toggle_state(PillState.DASHBOARD)
            return
        if action == "timer":
            presets = self._config.timer_presets
            self._registry.get("timer").start_minutes(presets[0] if presets else 5)  # type: ignore[attr-defined]
            return
        handlers = {
            "lock": lambda: lock_session(self._config.screen_lock_app_command),
            "sleep": suspend,
            "reboot": reboot,
            "shutdown": shut_down,
            "logout": log_off,
        }
        handler = handlers.get(action)
        if handler is None:
            logger.warning("unknown power action %r", action)
            return
        self._close_all()
        if not handler():
            self._tray.showMessage(
                "ChillPill", f"could not {action} this machine", QSystemTrayIcon.MessageIcon.Warning, 4000
            )

    # -- IPC ---------------------------------------------------------------

    def _run_command_line(self, line: str) -> None:
        """Run a shorthand command string (used by the hotkey manager)."""
        from shell.ipc.protocol import parse_argv

        try:
            command = parse_argv(line.split())
        except ProtocolError as exc:
            logger.error("bad hotkey command %r: %s", line, exc)
            return
        self._handle(command)

    def _on_command(self, command: Command, replies: queue.Queue) -> None:
        try:
            reply = self._handle(command)
        except Exception as exc:  # never let a bad command kill the shell
            logger.exception("command %s failed", command.cmd)
            reply = reply_error(str(exc))
        with suppress(queue.Full):  # the queue holds exactly one slot
            replies.put_nowait(reply)

    def _handle(self, command: Command) -> dict[str, Any]:
        cmd = command.cmd

        if cmd == "ping":
            return reply_ok("pong")
        if cmd == "quit":
            QTimer.singleShot(0, self.quit)
            return reply_ok("stopping")
        if cmd == "reload":
            self._store.reload()
            return reply_ok("reloaded")
        if cmd == "status":
            return reply_ok(self._status())

        if cmd in ("toggle", "show", "hide"):
            return self._handle_surface(cmd, command)

        if cmd == "volume":
            volume = self._registry.get("volume")
            value = parse_value(command.args.get("value"), int(volume.get("percent", 0)))
            volume.set_percent(value)  # type: ignore[attr-defined]
            return reply_ok({"volume": value})

        if cmd == "brightness":
            brightness = self._registry.get("brightness")
            value = parse_value(command.args.get("value"), int(brightness.get("percent", 0)))
            brightness.set_percent(value)  # type: ignore[attr-defined]
            return reply_ok({"brightness": value})

        if cmd == "dnd":
            notifications = self._registry.get("notifications")
            state = parse_switch(command.args.get("value", "toggle"), bool(notifications.get("dnd", False)))
            notifications.set_dnd(state)  # type: ignore[attr-defined]
            return reply_ok({"dnd": state})

        if cmd == "timer":
            return self._handle_timer(command)

        if cmd == "wallpaper":
            path = Path(str(command.args.get("path", "")))
            wallpaper = self._registry.get("wallpaper")
            if not wallpaper.apply(path):  # type: ignore[attr-defined]
                return reply_error(f"could not set {path}")
            return reply_ok({"wallpaper": str(path)})

        if cmd == "notify":
            notifications = self._registry.get("notifications")
            notification = Notification(
                id=-abs(hash((command.args.get("title"), command.args.get("body")))) % 10**9,
                app="ChillPill",
                title=str(command.args.get("title", "")),
                body=str(command.args.get("body", "")),
            )
            notifications.push(notification)  # type: ignore[attr-defined]
            return reply_ok({"id": notification.id})

        return reply_error(f"unhandled command {cmd!r}")

    def _handle_surface(self, cmd: str, command: Command) -> dict[str, Any]:
        target = resolve_target(command.target)
        if target == "*":
            if cmd == "show":
                return reply_error("'*' only makes sense with hide or toggle")
            self._close_all()
            return reply_ok({"open": None})

        state = command.state
        if state is None:
            return reply_error(f"unknown target {command.target!r}")
        if cmd == "toggle":
            self._toggle_state(state)
        elif cmd == "show":
            self._open_state(state)
        else:
            self._machine.close(state)
            self._after_exclusive_change(None)
        return reply_ok({"open": self._machine.exclusive.value if self._machine.exclusive else None})

    def _handle_timer(self, command: Command) -> dict[str, Any]:
        timer = self._registry.get("timer")
        raw = str(command.args.get("value", "")).strip().lower()
        if raw in ("cancel", "stop", "0"):
            timer.cancel()  # type: ignore[attr-defined]
            return reply_ok({"timer": None})
        try:
            minutes = float(raw)
        except ValueError:
            return reply_error(f"timer needs minutes or 'cancel', got {raw!r}")
        timer.start_minutes(minutes)  # type: ignore[attr-defined]
        return reply_ok({"timer": minutes})

    def _status(self) -> dict[str, Any]:
        morph = self._machine.morph()
        return {
            "state": self._machine.state.value,
            "open": self._machine.exclusive.value if self._machine.exclusive else None,
            "geometry": {"width": morph.width, "height": morph.height, "radius": morph.radius},
            "modules": {module.name: module.state for module in self._registry},
        }

    # -- config ------------------------------------------------------------

    def _on_config_changed(self, config: Config) -> None:
        self._config = config
        self._launcher_backend = flow.resolve_backend(config.launcher_backend)
        modules_pkg.apply_config(self._registry, config)
        self._pill.apply_config(config)
        for surface in (self.pill_bar, self.control_center, self.dashboard, self.wallpapers):
            apply = getattr(surface, "apply_config", None)
            if callable(apply):
                apply(config)
        if IS_WINDOWS:
            screen = self._pill.target_screen()
            if screen is not None:
                reserved = config.pill_top_margin + self._pill.height() + config.pill_bottom_margin
                self._appbar.reposition(screen, reserved)
        logger.info("configuration applied")


def _pill_icon() -> QIcon:
    """Draw the tray icon rather than shipping one.

    The original shell's logo is GPLv3 artwork and is deliberately not reused
    (spec §4.4), and a 32px rounded rectangle is a fair likeness of the product.
    """
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(Qt.GlobalColor.white)
    painter.drawRoundedRect(3, 10, 26, 12, 6, 6)
    painter.end()
    return QIcon(pixmap)


def run() -> int:
    """Entry point used by `main.py` and `python -m shell`."""
    from shell.platform.window import set_app_user_model_id, set_dpi_awareness

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Both must happen before any window exists.
    set_dpi_awareness()

    app = QApplication(sys.argv)
    app.setApplicationName("ChillPill")
    app.setQuitOnLastWindowClosed(False)  # the pill hides; the shell stays up
    set_app_user_model_id()

    shell = ChillPillApp(app)
    shell.start()
    return app.exec()
