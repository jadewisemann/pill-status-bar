"""Control center: media card, three toggles, two sliders, notification card.

Laid out to the original's measurements -- a 118px media card at radius 12 with
a 2px border, 110x35 toggles at radius 10, 4px sliders, and a notification card
whose 35px header carries the count and a "Clear all" pill.

The only surface whose height is computed rather than constant: 118 without
media, 240 with it, plus the notification bump (spec §1.2).  Both inputs are
reported back through `contribute_context`.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from shell.config import Config
from shell.modules.base import ModuleRegistry
from shell.modules.notifications import Notification
from shell.state import PillState, PillStateMachine
from shell.surfaces.base import Surface
from shell.theme import (
    FONTS,
    GLYPHS,
    PALETTE,
    brightness_glyph,
    volume_glyph,
)
from shell.widgets import (
    Artwork,
    IconLabel,
    MarqueeLabel,
    ProgressBar,
    Slider,
    TextLabel,
    ToggleButton,
    TransportButton,
    icon_font,
    scrollbar_stylesheet,
    text_font,
)

MEDIA_CARD_HEIGHT = 118
MEDIA_CARD_RADIUS = 12
MEDIA_CARD_BORDER = 2
ARTWORK_SIZE = 47
NOTIF_HEADER_HEIGHT = 35
NOTIF_ROW_HEIGHT = 44
#: The original caps the list at 97px, which is two rows and their separators.
NOTIF_MAX_HEIGHT = 97
MAX_VISIBLE_NOTIFICATIONS = 2


class MediaCard(QWidget):
    """Album art, title, artist, transport controls, seekable position."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(MEDIA_CARD_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(15, 12, 15, 12)
        outer.setSpacing(15)

        top = QHBoxLayout()
        top.setSpacing(15)
        self.artwork = Artwork(size=ARTWORK_SIZE, radius=7, parent=self)
        top.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignTop)

        meta = QVBoxLayout()
        meta.setSpacing(4)
        self.title = MarqueeLabel("", size=FONTS.media_title, color=PALETTE.media_title, parent=self)
        self.artist = MarqueeLabel("", size=FONTS.media_artist, color=PALETTE.accent, parent=self)
        meta.addWidget(self.title)
        meta.addWidget(self.artist)
        top.addLayout(meta, 1)

        controls = QHBoxLayout()
        controls.setSpacing(14)
        self.previous = TransportButton(GLYPHS.previous, parent=self)
        self.play_pause = TransportButton(GLYPHS.play, parent=self)
        self.next = TransportButton(GLYPHS.next, parent=self)
        for button in (self.previous, self.play_pause, self.next):
            controls.addWidget(button)
        top.addLayout(controls, 0)
        outer.addLayout(top)

        self.progress = ProgressBar(height=3, parent=self)
        outer.addWidget(self.progress)

        times = QHBoxLayout()
        self.elapsed = TextLabel("0:00", size=FONTS.media_time, color=PALETTE.media_time, parent=self)
        self.total = TextLabel("0:00", size=FONTS.media_time, color=PALETTE.media_time, parent=self)
        times.addWidget(self.elapsed)
        times.addStretch(1)
        times.addWidget(self.total)
        outer.addLayout(times)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inset = MEDIA_CARD_BORDER / 2
        painter.setBrush(QColor(PALETTE.cc_media_bg))
        painter.setPen(QPen(QColor(PALETTE.cc_media_border), MEDIA_CARD_BORDER))
        painter.drawRoundedRect(
            QRectF(inset, inset, self.width() - MEDIA_CARD_BORDER, self.height() - MEDIA_CARD_BORDER),
            MEDIA_CARD_RADIUS,
            MEDIA_CARD_RADIUS,
        )
        painter.end()


class NotificationRow(QWidget):
    """One notification: title and time on the first line, body under it."""

    dismissed = pyqtSignal(int)

    def __init__(self, notification: Notification, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._id = notification.id
        self.setFixedHeight(NOTIF_ROW_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 5, 8, 5)
        outer.setSpacing(1)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = notification.title or notification.app or "Notification"
        head.addWidget(TextLabel(title, size=FONTS.notif_title, bold=True, parent=self), 1)
        head.addWidget(
            TextLabel(
                notification.received.strftime("%H:%M"),
                size=FONTS.notif_time,
                color=PALETTE.notif_time,
                parent=self,
            )
        )
        self.dismiss = _DismissButton(parent=self)
        self.dismiss.clicked.connect(lambda: self.dismissed.emit(self._id))
        head.addWidget(self.dismiss)
        outer.addLayout(head)

        body = notification.body.replace("\n", " ")
        outer.addWidget(TextLabel(body[:80], size=FONTS.notif_body, color=PALETTE.notif_body, parent=self))


class _DismissButton(QWidget):
    """The × on a notification row: invisible until hovered."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hovered = False
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def enterEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = False
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(PALETTE.notif_separator))
            painter.drawEllipse(self.rect())
        painter.setPen(QColor(PALETTE.notif_dismiss_hover if self._hovered else PALETTE.notif_dismiss))
        painter.setFont(icon_font(size=11))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, GLYPHS.close)
        painter.end()


class NotificationCard(QWidget):
    """Header with the count and a Clear all pill, then the scrollable list."""

    clear_requested = pyqtSignal()
    dismissed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[NotificationRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget(self)
        header.setFixedHeight(NOTIF_HEADER_HEIGHT)
        header.setStyleSheet(
            f"background: {PALETTE.notif_header_bg};border-top-left-radius: 10px; border-top-right-radius: 10px;"
        )
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(12, 0, 8, 0)
        self.count = TextLabel(
            "Notifications (0)", size=FONTS.notif_header, color=PALETTE.notif_header_fg, parent=header
        )
        header_row.addWidget(self.count, 1)
        self.clear = _ClearAllButton(parent=header)
        self.clear.clicked.connect(self.clear_requested)
        header_row.addWidget(self.clear)
        outer.addWidget(header)

        self.area = QScrollArea(self)
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area.setStyleSheet(scrollbar_stylesheet() + f"QScrollArea {{ background: {PALETTE.notif_card_bg}; }}")
        self.area.setMaximumHeight(NOTIF_MAX_HEIGHT)
        holder = QWidget()
        holder.setStyleSheet(f"background: {PALETTE.notif_card_bg};")
        self._list = QVBoxLayout(holder)
        self._list.setContentsMargins(0, 2, 0, 2)
        self._list.setSpacing(0)
        self._list.addStretch(1)
        self.area.setWidget(holder)
        outer.addWidget(self.area)

    def set_notifications(self, notifications: list[Notification]) -> None:
        for row in self._rows:
            self._list.removeWidget(row)
            row.deleteLater()
        self._rows = []
        for notification in notifications:
            row = NotificationRow(notification, parent=self)
            row.dismissed.connect(self.dismissed)
            self._list.insertWidget(self._list.count() - 1, row)
            self._rows.append(row)
        self.count.setText(f"Notifications ({len(notifications)})")


class _ClearAllButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hovered = False
        self.setFixedSize(58, 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def enterEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = False
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE.notif_clear_bg_hover if self._hovered else PALETTE.notif_clear_bg))
        painter.drawRoundedRect(QRectF(self.rect()), 10, 10)
        painter.setPen(QColor(PALETTE.cc_button_label))
        painter.setFont(text_font(size=FONTS.notif_clear))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Clear all")
        painter.end()


class ControlCenter(Surface):
    state = PillState.CONTROL_CENTER
    uses = ("volume", "brightness", "media", "network", "notifications", "timer")

    #: A power action was chosen; the app confirms and performs it.
    power_action = pyqtSignal(str)

    def __init__(self, registry: ModuleRegistry, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        self._config = config

        outer = QVBoxLayout(self)
        outer.setContentsMargins(5, 5, 5, 5)
        outer.setSpacing(8)

        self.media = MediaCard(self)
        outer.addWidget(self.media)
        outer.addLayout(self._build_toggles())
        outer.addLayout(self._build_sliders())

        self.notifications = NotificationCard(self)
        outer.addWidget(self.notifications)
        self.notifications.hide()
        outer.addStretch(1)

    # -- construction ------------------------------------------------------

    def _build_toggles(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.wifi = ToggleButton(GLYPHS.wifi_panel, "Off", icon_on_color=PALETTE.cc_wifi_icon_on, parent=self)
        self.dnd = ToggleButton(
            GLYPHS.dnd, "", on_color=PALETTE.cc_dnd_bg_on, icon_on_color=PALETTE.cc_dnd_icon_on, parent=self
        )
        self.timer = ToggleButton(GLYPHS.timer_idle, "1m", icon_on_color=PALETTE.cc_timer_icon_on, parent=self)
        row.addWidget(self.wifi)
        row.addStretch(1)
        row.addWidget(self.dnd)
        row.addStretch(1)
        row.addWidget(self.timer)
        return row

    def _build_sliders(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setContentsMargins(10, 0, 2, 0)
        box.setSpacing(5)

        volume_row = QHBoxLayout()
        volume_row.setSpacing(14)
        self.volume_icon = IconLabel(GLYPHS.volume_high, size=FONTS.cc_slider_icon, parent=self)
        self.volume_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.volume_icon.mouseReleaseEvent = lambda _e: self._toggle_mute()  # type: ignore[assignment]
        self.volume_slider = Slider(parent=self)
        self.volume_value = TextLabel("0%", size=FONTS.cc_slider_value, parent=self)
        self.volume_value.setMinimumWidth(35)
        volume_row.addWidget(self.volume_icon)
        volume_row.addWidget(self.volume_slider, 1)
        volume_row.addWidget(self.volume_value)
        box.addLayout(volume_row)

        brightness_row = QHBoxLayout()
        brightness_row.setSpacing(14)
        self.brightness_icon = IconLabel(GLYPHS.brightness_ramp[2], size=FONTS.cc_slider_icon, parent=self)
        self.brightness_slider = Slider(parent=self)
        self.brightness_value = TextLabel("0%", size=FONTS.cc_slider_value, parent=self)
        self.brightness_value.setMinimumWidth(35)
        brightness_row.addWidget(self.brightness_icon)
        brightness_row.addWidget(self.brightness_slider, 1)
        brightness_row.addWidget(self.brightness_value)
        box.addLayout(brightness_row)
        return box

    # -- wiring ------------------------------------------------------------

    def bind(self) -> None:
        volume = self.module("volume")
        brightness = self.module("brightness")
        media = self.module("media")
        notifications = self.module("notifications")
        timer = self.module("timer")

        volume.changed.connect(self._sync_volume)
        brightness.changed.connect(self._sync_brightness)
        media.changed.connect(self._sync_media)
        media.artwork_ready.connect(self.media.artwork.set_pixmap)  # type: ignore[attr-defined]
        notifications.stack_changed.connect(self._sync_notifications)  # type: ignore[attr-defined]
        notifications.changed.connect(self._sync_toggles)
        self.module("network").changed.connect(self._sync_toggles)
        timer.changed.connect(self._sync_toggles)

        self.volume_slider.value_changed.connect(volume.set_percent)  # type: ignore[attr-defined]
        # Brightness writes are slow (DDC/CI), so only commit on release.
        self.brightness_slider.released.connect(brightness.set_percent)  # type: ignore[attr-defined]

        self.media.play_pause.clicked.connect(media.play_pause)  # type: ignore[attr-defined]
        self.media.next.clicked.connect(media.next_track)  # type: ignore[attr-defined]
        self.media.previous.clicked.connect(media.previous_track)  # type: ignore[attr-defined]
        self.media.progress.seeked.connect(self._seek)

        self.wifi.clicked.connect(self._open_networks)
        self.dnd.clicked.connect(self._toggle_dnd)
        self.timer.clicked.connect(self._toggle_timer)
        self.timer.right_clicked.connect(self._cycle_preset)
        self.timer.middle_clicked.connect(lambda: self.module("timer").cancel())  # type: ignore[attr-defined]

        self.notifications.clear_requested.connect(notifications.clear)  # type: ignore[attr-defined]
        self.notifications.dismissed.connect(notifications.dismiss)  # type: ignore[attr-defined]

    # -- refresh -----------------------------------------------------------

    def refresh(self) -> None:
        self._sync_volume()
        self._sync_brightness()
        self._sync_media()
        self._sync_toggles()
        self._sync_notifications()

    def _sync_volume(self) -> None:
        volume = self.module("volume")
        percent = int(volume.get("percent", 0))
        muted = bool(volume.get("muted", False))
        self.volume_slider.set_value(percent)
        self.volume_value.setText("muted" if muted else f"{percent}%")
        self.volume_icon.set_glyph(volume_glyph(percent, muted))
        self.volume_icon.set_color(PALETTE.slider_muted_icon if muted else PALETTE.fg)

    def _sync_brightness(self) -> None:
        brightness = self.module("brightness")
        percent = int(brightness.get("percent", 0))
        self.brightness_slider.set_value(percent)
        self.brightness_value.setText(f"{percent}%")
        self.brightness_icon.set_glyph(brightness_glyph(percent))
        usable = brightness.get("backend", "none") != "none"
        self.brightness_slider.setEnabled(usable)
        self.brightness_icon.set_color(PALETTE.fg if usable else PALETTE.cc_button_fg_off)

    def _sync_media(self) -> None:
        media = self.module("media")
        active = bool(media.get("active", False))
        self.media.setVisible(active)
        if not active:
            self.media.artwork.clear()
            self.geometry_hint_changed.emit()
            return

        self.media.title.set_text(str(media.get("title", "")) or "Unknown track")
        self.media.artist.set_text(str(media.get("artist", "")))
        self.media.play_pause.set_glyph(GLYPHS.pause if media.get("playing") else GLYPHS.play)

        position = float(media.get("position", 0.0))
        duration = float(media.get("duration", 0.0))
        self.media.progress.set_fraction(position / duration if duration else 0.0)
        self.media.elapsed.setText(_clock(position))
        self.media.total.setText(_clock(duration))
        self.geometry_hint_changed.emit()

    def _sync_toggles(self) -> None:
        network = self.module("network")
        connected = str(network.get("kind", "none")) != "none"
        self.wifi.set_active(connected)
        self.wifi.set_label(str(network.get("ssid", "")) or ("Connected" if connected else "Off"))

        notifications = self.module("notifications")
        dnd = bool(notifications.get("dnd", False))
        self.dnd.set_active(dnd)

        timer = self.module("timer")
        running = bool(timer.get("running", False))
        paused = bool(timer.get("paused", False))
        self.timer.set_active(running)
        if running:
            self.timer.set_glyph(GLYPHS.timer_running)
            self.timer.set_label(str(timer.get("text", "")))
        elif paused:
            self.timer.set_glyph(GLYPHS.timer_paused)
            self.timer.set_label(str(timer.get("text", "")))
        else:
            presets = self._config.timer_presets or [1]
            self.timer.set_glyph(GLYPHS.timer_idle)
            self.timer.set_label(f"{self._preset()}m" if presets else "")

    def _sync_notifications(self) -> None:
        notifications = self.module("notifications")
        stack = notifications.stack[:MAX_VISIBLE_NOTIFICATIONS]  # type: ignore[attr-defined]
        self.notifications.set_notifications(stack)
        self.notifications.setVisible(bool(stack))
        self._sync_toggles()
        self.geometry_hint_changed.emit()

    # -- context -----------------------------------------------------------

    def contribute_context(self, machine: PillStateMachine) -> None:
        notifications = self.module("notifications")
        count = min(int(notifications.get("count", 0)), MAX_VISIBLE_NOTIFICATIONS)
        list_height = min(NOTIF_MAX_HEIGHT, count * NOTIF_ROW_HEIGHT) + (NOTIF_HEADER_HEIGHT if count else 0)
        machine.update_context(
            media_active=bool(self.module("media").get("active", False)),
            notification_count=count,
            notification_list_height=float(list_height),
        )

    # -- actions -----------------------------------------------------------

    def _preset(self) -> int:
        presets = self._config.timer_presets or [1]
        return presets[self._preset_index % len(presets)]

    _preset_index = 0

    def _cycle_preset(self) -> None:
        timer = self.module("timer")
        if timer.get("running") or timer.get("paused"):
            return
        self._preset_index += 1
        self._sync_toggles()

    def _toggle_timer(self) -> None:
        timer = self.module("timer")
        if timer.get("running"):
            timer.pause()  # type: ignore[attr-defined]
        elif timer.get("paused"):
            timer.resume()  # type: ignore[attr-defined]
        else:
            timer.start_minutes(self._preset())  # type: ignore[attr-defined]
        self._sync_toggles()

    def _toggle_mute(self) -> None:
        self.module("volume").toggle_mute()  # type: ignore[attr-defined]

    def _toggle_dnd(self) -> None:
        self.module("notifications").toggle_dnd()  # type: ignore[attr-defined]
        self._sync_toggles()

    def _open_networks(self) -> None:
        from shell.modules.network import NetworkModule

        NetworkModule.open_network_flyout()

    def _seek(self, fraction: float) -> None:
        media = self.module("media")
        duration = float(media.get("duration", 0.0))
        if duration:
            media.seek(fraction * duration)  # type: ignore[attr-defined]

    def set_artwork(self, pixmap: QPixmap) -> None:
        self.media.artwork.set_pixmap(pixmap)

    def apply_config(self, config: Config) -> None:
        self._config = config
        self._sync_toggles()


def _clock(seconds: float) -> str:
    total = int(max(0.0, seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
