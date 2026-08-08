"""On-screen display: 220x40, one glyph and one bar.

Ships disabled by default.  Windows has no supported way to suppress its own
volume overlay, so two OSDs would appear for one key press (spec §8 R1); the
config key `osdEnabled` turns ours on for people who have removed the system
one with a third-party tool.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QWidget

from shell.modules.base import ModuleRegistry
from shell.modules.timer import format_remaining
from shell.state import PillState
from shell.surfaces.base import Surface
from shell.theme import GLYPHS, PALETTE, battery_color, battery_glyph, volume_glyph
from shell.widgets import IconLabel, Slider, TextLabel


class Osd(Surface):
    """Shows whichever value moved last."""

    state = PillState.OSD
    uses = ()

    def __init__(self, registry: ModuleRegistry, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(10)

        self.icon = IconLabel(GLYPHS.volume_high, size=14, parent=self)
        self.bar = Slider(height=6, parent=self)
        self.bar.setEnabled(False)  # the OSD reports, it does not control
        self.value = TextLabel("0%", size=9, color=PALETTE.text_muted, parent=self)
        self.value.setFixedWidth(34)

        row.addWidget(self.icon)
        row.addWidget(self.bar, 1)
        row.addWidget(self.value)

    # -- content -----------------------------------------------------------

    def show_volume(self, percent: int, muted: bool) -> None:
        self.icon.set_glyph(volume_glyph(percent, muted))
        self.icon.set_color(PALETTE.text_muted if muted else PALETTE.text)
        self.bar.set_value(percent)
        self.bar.set_fill(PALETTE.text_dim if muted else PALETTE.slider_fill)
        self.value.setText("muted" if muted else f"{percent}%")

    def show_brightness(self, percent: int) -> None:
        self.icon.set_glyph(GLYPHS.brightness if percent > 40 else GLYPHS.brightness_low)
        self.icon.set_color(PALETTE.text)
        self.bar.set_value(percent)
        self.bar.set_fill(PALETTE.slider_fill)
        self.value.setText(f"{percent}%")

    def show_battery(self, percent: int, charging: bool) -> None:
        color = battery_color(percent, charging)
        self.icon.set_glyph(battery_glyph(percent, charging))
        self.icon.set_color(color)
        self.bar.set_value(percent)
        self.bar.set_fill(color)
        self.value.setText(f"{percent}%")

    def show_timer(self, remaining: float) -> None:
        self.icon.set_glyph(GLYPHS.timer)
        self.icon.set_color(PALETTE.accent)
        self.bar.set_value(0)
        self.bar.set_fill(PALETTE.accent)
        self.value.setText(format_remaining(remaining))
