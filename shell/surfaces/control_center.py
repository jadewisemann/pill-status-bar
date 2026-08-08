"""Control center: media, toggles, sliders, notification stack.

The tallest of the fixed surfaces and the only one whose height is computed
rather than constant -- 118 without media, 240 with it, plus the notification
bump (spec §1.2).  Both inputs are reported back through `contribute_context`.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from shell.config import Config
from shell.modules.base import ModuleRegistry
from shell.modules.notifications import Notification
from shell.state import PillState, PillStateMachine
from shell.surfaces.base import Surface
from shell.theme import GLYPHS, PALETTE, volume_glyph
from shell.widgets import (
    Artwork,
    Card,
    GlyphButton,
    IconLabel,
    MarqueeLabel,
    ProgressBar,
    Slider,
    TextLabel,
    scrollbar_stylesheet,
)

MEDIA_SECTION_HEIGHT = 112
NOTIFICATION_ROW_HEIGHT = 44
#: `notif_bump` saturates at 130, i.e. 90px of list; two rows plus the gaps.
MAX_VISIBLE_NOTIFICATIONS = 2


class MediaPanel(QWidget):
    """Album art, scrolling title, transport controls, seekable position."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(MEDIA_SECTION_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.artwork = Artwork(size=64, radius=10, parent=self)
        top.addWidget(self.artwork)

        meta = QVBoxLayout()
        meta.setSpacing(2)
        meta.addStretch(1)
        self.title = MarqueeLabel("Nothing playing", size=12, parent=self)
        self.artist = MarqueeLabel("", size=10, color=PALETTE.text_muted, parent=self)
        meta.addWidget(self.title)
        meta.addWidget(self.artist)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.previous = GlyphButton(GLYPHS.prev_track, diameter=26, parent=self)
        self.play_pause = GlyphButton(GLYPHS.play, diameter=30, parent=self)
        self.next = GlyphButton(GLYPHS.next_track, diameter=26, parent=self)
        controls.addWidget(self.previous)
        controls.addWidget(self.play_pause)
        controls.addWidget(self.next)
        controls.addStretch(1)
        meta.addLayout(controls)
        meta.addStretch(1)
        top.addLayout(meta, 1)
        outer.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.elapsed = TextLabel("0:00", size=9, color=PALETTE.text_dim, parent=self)
        self.remaining = TextLabel("0:00", size=9, color=PALETTE.text_dim, parent=self)
        self.progress = ProgressBar(parent=self)
        bottom.addWidget(self.elapsed)
        bottom.addWidget(self.progress, 1)
        bottom.addWidget(self.remaining)
        outer.addLayout(bottom)


class NotificationRow(Card):
    """One notification in the stack."""

    dismissed = pyqtSignal(int)

    def __init__(self, notification: Notification, parent: QWidget | None = None) -> None:
        super().__init__(radius=10, hoverable=True, parent=parent)
        self._id = notification.id
        self.setFixedHeight(NOTIFICATION_ROW_HEIGHT)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 6, 8, 6)
        row.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(0)
        title = notification.title or notification.app or "Notification"
        text.addWidget(TextLabel(title, size=10, bold=True, parent=self))
        body = notification.body.replace("\n", " ")
        text.addWidget(TextLabel(body[:64], size=9, color=PALETTE.text_muted, parent=self))
        row.addLayout(text, 1)

        row.addWidget(TextLabel(notification.age_text, size=8, color=PALETTE.text_dim, parent=self))
        close = GlyphButton("\U000f0156", diameter=20, parent=self)  # nf-md-close
        close.clicked.connect(lambda: self.dismissed.emit(self._id))
        row.addWidget(close)


class ControlCenter(Surface):
    """The main panel."""

    state = PillState.CONTROL_CENTER
    uses = ("volume", "brightness", "media", "network", "notifications")

    #: A power action was chosen; the app confirms and performs it.
    power_action = pyqtSignal(str)

    def __init__(self, registry: ModuleRegistry, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        self._config = config
        self._rows: list[NotificationRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        self.media = MediaPanel(self)
        outer.addWidget(self.media)

        outer.addLayout(self._build_sliders())
        outer.addLayout(self._build_toggles())

        self.notification_area = QScrollArea(self)
        self.notification_area.setWidgetResizable(True)
        self.notification_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notification_area.setStyleSheet(scrollbar_stylesheet())
        self.notification_area.setFrameShape(QScrollArea.Shape.NoFrame)
        holder = QWidget()
        self._notification_layout = QVBoxLayout(holder)
        self._notification_layout.setContentsMargins(0, 0, 0, 0)
        self._notification_layout.setSpacing(6)
        self._notification_layout.addStretch(1)
        self.notification_area.setWidget(holder)
        outer.addWidget(self.notification_area)
        self.notification_area.hide()

    # -- construction ------------------------------------------------------

    def _build_sliders(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(8)

        volume_row = QHBoxLayout()
        volume_row.setSpacing(10)
        self.volume_icon = IconLabel(GLYPHS.volume_high, size=12, parent=self)
        self.volume_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.volume_icon.mouseReleaseEvent = lambda _e: self._toggle_mute()  # type: ignore[assignment]
        self.volume_slider = Slider(parent=self)
        self.volume_value = TextLabel("0%", size=9, color=PALETTE.text_muted, parent=self)
        self.volume_value.setFixedWidth(34)
        volume_row.addWidget(self.volume_icon)
        volume_row.addWidget(self.volume_slider, 1)
        volume_row.addWidget(self.volume_value)
        box.addLayout(volume_row)

        brightness_row = QHBoxLayout()
        brightness_row.setSpacing(10)
        self.brightness_icon = IconLabel(GLYPHS.brightness, size=12, parent=self)
        self.brightness_slider = Slider(parent=self)
        self.brightness_value = TextLabel("0%", size=9, color=PALETTE.text_muted, parent=self)
        self.brightness_value.setFixedWidth(34)
        brightness_row.addWidget(self.brightness_icon)
        brightness_row.addWidget(self.brightness_slider, 1)
        brightness_row.addWidget(self.brightness_value)
        box.addLayout(brightness_row)
        return box

    def _build_toggles(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.wifi_toggle = GlyphButton(GLYPHS.wifi, diameter=32, parent=self)
        self.dnd_toggle = GlyphButton(GLYPHS.bell, diameter=32, parent=self)
        self.timer_toggle = GlyphButton(GLYPHS.timer, diameter=32, parent=self)
        self.lock_button = GlyphButton(GLYPHS.lock, diameter=32, parent=self)
        self.power_button = GlyphButton(GLYPHS.power, diameter=32, parent=self)
        for button in (self.wifi_toggle, self.dnd_toggle, self.timer_toggle):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(self.lock_button)
        row.addWidget(self.power_button)
        return row

    # -- wiring ------------------------------------------------------------

    def bind(self) -> None:
        volume = self.module("volume")
        brightness = self.module("brightness")
        media = self.module("media")
        notifications = self.module("notifications")

        volume.changed.connect(self._sync_volume)
        brightness.changed.connect(self._sync_brightness)
        media.changed.connect(self._sync_media)
        media.artwork_ready.connect(self._set_artwork)  # type: ignore[attr-defined]
        notifications.stack_changed.connect(self._sync_notifications)  # type: ignore[attr-defined]

        self.volume_slider.value_changed.connect(lambda value: volume.set_percent(value))  # type: ignore[attr-defined]
        # Brightness writes are slow (DDC/CI), so only commit on release.
        self.brightness_slider.released.connect(lambda value: brightness.set_percent(value))  # type: ignore[attr-defined]

        self.media.play_pause.clicked.connect(media.play_pause)  # type: ignore[attr-defined]
        self.media.next.clicked.connect(media.next_track)  # type: ignore[attr-defined]
        self.media.previous.clicked.connect(media.previous_track)  # type: ignore[attr-defined]
        self.media.progress.seeked.connect(self._seek)

        self.wifi_toggle.clicked.connect(self._open_networks)
        self.dnd_toggle.clicked.connect(self._toggle_dnd)
        self.lock_button.clicked.connect(lambda: self.power_action.emit("lock"))
        self.power_button.clicked.connect(lambda: self.power_action.emit("menu"))
        self.timer_toggle.clicked.connect(lambda: self.power_action.emit("timer"))

    # -- refresh -----------------------------------------------------------

    def refresh(self) -> None:
        self._sync_volume()
        self._sync_brightness()
        self._sync_media()
        self._sync_notifications()

    def _sync_volume(self) -> None:
        volume = self.module("volume")
        percent = int(volume.get("percent", 0))
        muted = bool(volume.get("muted", False))
        self.volume_slider.set_value(percent)
        self.volume_slider.set_fill(PALETTE.text_dim if muted else PALETTE.slider_fill)
        self.volume_value.setText(f"{percent}%")
        self.volume_icon.set_glyph(volume_glyph(percent, muted))
        self.volume_icon.set_color(PALETTE.text_muted if muted else PALETTE.text)

    def _sync_brightness(self) -> None:
        brightness = self.module("brightness")
        percent = int(brightness.get("percent", 0))
        self.brightness_slider.set_value(percent)
        self.brightness_value.setText(f"{percent}%")
        usable = brightness.get("backend", "none") != "none"
        self.brightness_slider.setEnabled(usable)
        self.brightness_icon.set_color(PALETTE.text if usable else PALETTE.text_dim)

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
        playing = bool(media.get("playing", False))
        self.media.play_pause.set_glyph(GLYPHS.pause if playing else GLYPHS.play)

        position = float(media.get("position", 0.0))
        duration = float(media.get("duration", 0.0))
        self.media.progress.set_fraction(position / duration if duration else 0.0)
        self.media.elapsed.setText(_clock(position))
        self.media.remaining.setText(_clock(duration))
        self.geometry_hint_changed.emit()

    def _set_artwork(self, pixmap: QPixmap) -> None:
        self.media.artwork.set_pixmap(pixmap)

    def _sync_notifications(self) -> None:
        notifications = self.module("notifications")
        stack = notifications.stack[:MAX_VISIBLE_NOTIFICATIONS]  # type: ignore[attr-defined]

        for row in self._rows:
            self._notification_layout.removeWidget(row)
            row.deleteLater()
        self._rows = []

        for notification in stack:
            row = NotificationRow(notification, parent=self)
            row.dismissed.connect(notifications.dismiss)  # type: ignore[attr-defined]
            self._notification_layout.insertWidget(self._notification_layout.count() - 1, row)
            self._rows.append(row)

        self.notification_area.setVisible(bool(stack))
        self.dnd_toggle.set_active(bool(notifications.get("dnd", False)))
        self.dnd_toggle.set_glyph(GLYPHS.bell_off if notifications.get("dnd") else GLYPHS.bell)
        self.geometry_hint_changed.emit()

    # -- context -----------------------------------------------------------

    def contribute_context(self, machine: PillStateMachine) -> None:
        notifications = self.module("notifications")
        count = min(int(notifications.get("count", 0)), MAX_VISIBLE_NOTIFICATIONS)
        list_height = count * NOTIFICATION_ROW_HEIGHT + max(0, count - 1) * 6
        machine.update_context(
            media_active=bool(self.module("media").get("active", False)),
            notification_count=count,
            notification_list_height=float(list_height),
        )

    # -- actions -----------------------------------------------------------

    def _toggle_mute(self) -> None:
        self.module("volume").toggle_mute()  # type: ignore[attr-defined]

    def _toggle_dnd(self) -> None:
        self.module("notifications").toggle_dnd()  # type: ignore[attr-defined]
        self._sync_notifications()

    def _open_networks(self) -> None:
        from shell.modules.network import NetworkModule

        NetworkModule.open_network_flyout()

    def _seek(self, fraction: float) -> None:
        media = self.module("media")
        duration = float(media.get("duration", 0.0))
        if duration:
            media.seek(fraction * duration)  # type: ignore[attr-defined]

    def apply_config(self, config: Config) -> None:
        self._config = config


def _clock(seconds: float) -> str:
    total = int(max(0.0, seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
