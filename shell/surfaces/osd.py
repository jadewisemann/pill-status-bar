"""On-screen display: 220x40, one glyph, a thin bar, one value.

Bar geometry is the original's: 120px wide by 3.7px tall at radius 2, narrowed
to 110 for volume and 100 for brightness, and dropped entirely for the battery
and timer messages which are text-only.

Ships disabled by default.  Windows has no supported way to suppress its own
volume overlay, so two OSDs would appear for one key press (spec §8 R1); the
config key `osdEnabled` turns ours on for people who have removed the system
one with a third-party tool.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from shell.anim import NOTIFICATION_FADE
from shell.modules.base import ModuleRegistry
from shell.modules.timer import format_remaining
from shell.state import PillState
from shell.surfaces.base import Surface
from shell.theme import FONTS, GLYPHS, PALETTE, battery_color, battery_glyph, brightness_glyph, volume_glyph
from shell.widgets import IconLabel, TextLabel

BAR_HEIGHT = 3.7
BAR_RADIUS = 2.0
BAR_WIDTH_VOLUME = 110
BAR_WIDTH_VOLUME_MUTED = 90
BAR_WIDTH_BRIGHTNESS = 100


class OsdMeter(QWidget):
    """The thin filled bar.  Width is set per reading; zero hides it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fraction = 0.0
        self._fill = QColor(PALETTE.fg)
        self.setFixedHeight(int(BAR_HEIGHT) + 4)
        self.set_bar_width(BAR_WIDTH_VOLUME)

    def set_bar_width(self, width: int) -> None:
        self.setFixedWidth(max(0, width))
        self.setVisible(width > 0)

    def set_fraction(self, fraction: float, fill: str | None = None) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        if fill:
            self._fill = QColor(fill)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        if self.width() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        top = (self.height() - BAR_HEIGHT) / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE.osd_track))
        painter.drawRoundedRect(QRectF(0, top, self.width(), BAR_HEIGHT), BAR_RADIUS, BAR_RADIUS)
        filled = self.width() * self._fraction
        if filled > 0:
            painter.setBrush(self._fill)
            painter.drawRoundedRect(QRectF(0, top, filled, BAR_HEIGHT), BAR_RADIUS, BAR_RADIUS)
        painter.end()


class Osd(Surface):
    """Shows whichever value moved last."""

    state = PillState.OSD
    fade = NOTIFICATION_FADE
    uses = ()

    def __init__(self, registry: ModuleRegistry, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addStretch(1)

        self.icon = IconLabel(GLYPHS.volume_high, size=FONTS.osd_icon, parent=self)
        self.meter = OsdMeter(self)
        self.value = TextLabel("", size=FONTS.osd_value, parent=self)
        self.value.set_size(FONTS.osd_value, weight=600)

        row.addWidget(self.icon)
        row.addWidget(self.meter)
        row.addWidget(self.value)
        row.addStretch(1)

    # -- content -----------------------------------------------------------

    def show_volume(self, percent: int, muted: bool) -> None:
        self.icon.set_glyph(volume_glyph(percent, muted))
        self.icon.set_color(PALETTE.volume_muted if muted else PALETTE.fg)
        self.meter.set_bar_width(BAR_WIDTH_VOLUME_MUTED if muted else BAR_WIDTH_VOLUME)
        self.meter.set_fraction(percent / 100, PALETTE.fg)
        self.value.setText("muted" if muted else f"{percent}%")
        self.value.set_color(PALETTE.volume_muted if muted else PALETTE.fg)

    def show_brightness(self, percent: int) -> None:
        self.icon.set_glyph(brightness_glyph(percent))
        self.icon.set_color(PALETTE.fg)
        self.meter.set_bar_width(BAR_WIDTH_BRIGHTNESS)
        self.meter.set_fraction(percent / 100, PALETTE.fg)
        self.value.setText(f"{percent}%")
        self.value.set_color(PALETTE.fg)

    def show_battery(self, percent: int, charging: bool) -> None:
        """Battery has no bar -- it reports a state change, not a level."""
        self.icon.set_glyph(battery_glyph(percent, charging))
        self.icon.set_color(battery_color(percent, charging))
        self.meter.set_bar_width(0)
        self.value.setText("Charging" if charging else "Charging stopped")
        self.value.set_color(PALETTE.fg)

    def show_timer(self, remaining: float) -> None:
        self.icon.set_glyph(GLYPHS.timer_done)
        self.icon.set_color(PALETTE.osd_timer_icon)
        self.meter.set_bar_width(0)
        self.value.setText("Timer finished" if remaining <= 0 else format_remaining(remaining))
        self.value.set_color(PALETTE.fg)
