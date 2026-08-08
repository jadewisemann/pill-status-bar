"""Mini dashboard: who you are, what the machine is doing, and the power menu.

Fixed at 420x155 (spec §1.2), so everything here is laid out to fit that box
exactly rather than to grow.
"""

from __future__ import annotations

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from shell.config import Config
from shell.modules.base import ModuleRegistry
from shell.modules.network import format_bytes
from shell.platform.system import account_picture, format_uptime, hostname, uptime_seconds, username
from shell.state import PillState
from shell.surfaces.base import Surface
from shell.theme import GLYPHS, PALETTE, battery_color
from shell.widgets import Avatar, GlyphButton, IconLabel, TextLabel


class Stat(QWidget):
    """Glyph + value + caption, the dashboard's unit of content."""

    def __init__(self, glyph: str, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.icon = IconLabel(glyph, size=12, parent=self)
        self.icon.set_color(PALETTE.text_muted)
        row.addWidget(self.icon)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.value = TextLabel("--", size=10, parent=self)
        self.caption = TextLabel(caption, size=8, color=PALETTE.text_dim, parent=self)
        text.addWidget(self.value)
        text.addWidget(self.caption)
        row.addLayout(text)
        row.addStretch(1)

    def set_value(self, value: str, color: str | None = None) -> None:
        self.value.setText(value)
        if color:
            self.value.set_color(color)


class Dashboard(Surface):
    state = PillState.DASHBOARD
    uses = ("battery", "network", "bandwidth", "weather", "clock")

    power_action = pyqtSignal(str)  # lock | sleep | reboot | shutdown | logout

    def __init__(self, registry: ModuleRegistry, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        self._config = config

        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(16)

        outer.addLayout(self._build_identity())
        outer.addLayout(self._build_stats(), 1)

    # -- construction ------------------------------------------------------

    def _build_identity(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(8)
        column.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.avatar = Avatar(self._picture_path(), diameter=52, parent=self)
        column.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(
            TextLabel(username(), size=10, bold=True, parent=self), alignment=Qt.AlignmentFlag.AlignHCenter
        )
        column.addWidget(
            TextLabel(hostname(), size=8, color=PALETTE.text_dim, parent=self),
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        column.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        for glyph, action in (
            (GLYPHS.lock, "lock"),
            (GLYPHS.sleep, "sleep"),
            (GLYPHS.restart, "reboot"),
            (GLYPHS.power, "shutdown"),
        ):
            button = GlyphButton(glyph, diameter=24, parent=self)
            button.clicked.connect(lambda _=False, a=action: self.power_action.emit(a))
            buttons.addWidget(button)
        column.addLayout(buttons)
        return column

    def _build_stats(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)

        self.uptime = Stat(GLYPHS.clock, "uptime", self)
        self.battery = Stat(GLYPHS.battery_ramp[-1], "battery", self)
        self.address = Stat(GLYPHS.wifi, "network", self)
        self.traffic = Stat(GLYPHS.download, "this session", self)
        self.weather = Stat(GLYPHS.weather_clear, "weather", self)
        self.calendar = Stat(GLYPHS.calendar, "today", self)

        grid.addWidget(self.uptime, 0, 0)
        grid.addWidget(self.battery, 0, 1)
        grid.addWidget(self.address, 1, 0)
        grid.addWidget(self.traffic, 1, 1)
        grid.addWidget(self.weather, 2, 0)
        grid.addWidget(self.calendar, 2, 1)
        return grid

    def _picture_path(self) -> str:
        from pathlib import Path

        configured = self._config.display_picture
        if configured and Path(configured).is_file():
            return configured
        return account_picture() or ""

    # -- wiring ------------------------------------------------------------

    def bind(self) -> None:
        for name in ("battery", "network", "bandwidth", "weather"):
            self.module(name).changed.connect(self.refresh)

    def refresh(self) -> None:
        self.uptime.set_value(format_uptime(uptime_seconds()))

        battery = self.module("battery")
        if battery.get("present", False):
            percent = int(battery.get("percent", 0))
            charging = bool(battery.get("charging", False))
            self.battery.set_value(f"{percent}%", battery_color(percent, charging))
            self.battery.caption.setText(battery.time_left_text or "battery")  # type: ignore[attr-defined]
        else:
            self.battery.set_value("no battery", PALETTE.text_muted)

        network = self.module("network")
        self.address.set_value(str(network.get("ip", "0.0.0.0")))
        ssid = str(network.get("ssid", ""))
        self.address.caption.setText(ssid or str(network.get("kind", "network")))

        bandwidth = self.module("bandwidth")
        down = float(bandwidth.get("down_total", 0))
        up = float(bandwidth.get("up_total", 0))
        self.traffic.set_value(f"{format_bytes(down)} ↓ / {format_bytes(up)} ↑")

        weather = self.module("weather")
        self.weather.set_value(str(weather.get("temperature_text", "--")))
        self.weather.caption.setText(f"{weather.get('label', '')} · {weather.get('location', '')}".strip(" ·"))
        self.weather.icon.set_glyph(str(weather.get("glyph", GLYPHS.weather_clear)))

        today = QDate.currentDate()
        self.calendar.set_value(today.toString("ddd d MMM"))
        self.calendar.caption.setText(f"week {today.weekNumber()[0]}")

    def apply_config(self, config: Config) -> None:
        self._config = config
        self.avatar.set_path(self._picture_path())
