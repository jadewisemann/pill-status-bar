"""Mini dashboard: 420x155, three rows.

    [avatar]  user (hostname)              [battery] 85%
              up 35 minutes

    [ip] 192.168.1.38                      ↓ 407.2 MB
         wlp2s0                            ↑ 46.0 MB

    [lock][sleep]  06:52 pm Sun, 12 Jul   [weather] 37°C   [restart][power]

Fixed size, so everything here is laid out to fit that box rather than to grow.
The bottom strip is a separate rounded bar at #212121, which is what separates
"information" from "things that will end your session".
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDateTime, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from shell.config import Config
from shell.modules.base import ModuleRegistry
from shell.modules.network import format_bytes
from shell.platform.system import account_picture, format_uptime, hostname, uptime_seconds, username
from shell.state import PillState
from shell.surfaces.base import Surface
from shell.theme import FONTS, GLYPHS, PALETTE, battery_color, battery_glyph, weather_glyph
from shell.widgets import Avatar, IconLabel, TextLabel, icon_font

AVATAR_SIZE = 44
ACTION_BUTTON_SIZE = 22


class ActionButton(QWidget):
    """A small square in the dashboard's bottom strip."""

    clicked = pyqtSignal()

    def __init__(self, glyph: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glyph = glyph
        self._hovered = False
        self.setFixedSize(ACTION_BUTTON_SIZE, ACTION_BUTTON_SIZE)
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
        painter.setBrush(QColor(PALETTE.surface_hover if self._hovered else PALETTE.surface))
        painter.drawRoundedRect(QRectF(self.rect()), 6, 6)
        painter.setPen(QColor(PALETTE.fg if self._hovered else PALETTE.accent))
        painter.setFont(icon_font(size=FONTS.dash_value + 2))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._glyph)
        painter.end()


class ActionStrip(QWidget):
    """The rounded #212121 bar along the bottom."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE.dash_bar_bg))
        painter.drawRoundedRect(QRectF(self.rect()), 8, 8)
        painter.end()


class Dashboard(Surface):
    state = PillState.DASHBOARD
    uses = ("battery", "network", "bandwidth", "weather", "clock")

    power_action = pyqtSignal(str)  # lock | sleep | reboot | shutdown | logout

    def __init__(self, registry: ModuleRegistry, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        self._config = config

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)
        outer.addLayout(self._build_identity_row())
        outer.addLayout(self._build_network_row())
        outer.addWidget(self._build_action_strip())

    # -- construction ------------------------------------------------------

    def _build_identity_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        self.avatar = Avatar(self._picture_path(), diameter=AVATAR_SIZE, parent=self)
        row.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        names = QVBoxLayout()
        names.setSpacing(1)
        self.name = TextLabel(f"{username()} ({hostname()})", size=FONTS.dash_name, parent=self)
        self.name.set_size(FONTS.dash_name, weight=600)
        self.uptime = TextLabel("", size=FONTS.dash_subtitle, color=PALETTE.dash_subtitle, parent=self)
        names.addWidget(self.name)
        names.addWidget(self.uptime)
        row.addLayout(names, 1)

        self.battery_icon = IconLabel(parent=self)
        self.battery_icon.set_size(FONTS.dash_name)
        self.battery_text = TextLabel("", size=FONTS.dash_name, parent=self)
        self.battery_text.set_size(FONTS.dash_name, weight=600)
        row.addWidget(self.battery_icon)
        row.addWidget(self.battery_text)
        return row

    def _build_network_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        icon = IconLabel(GLYPHS.ip, parent=self)
        icon.set_size(FONTS.dash_subtitle + 1)
        icon.set_color(PALETTE.wifi_on)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        addresses = QVBoxLayout()
        addresses.setSpacing(1)
        self.ip = TextLabel("", size=FONTS.dash_subtitle + 1, parent=self)
        self.interface = TextLabel("", size=FONTS.dash_value, color=PALETTE.dash_subtitle, parent=self)
        addresses.addWidget(self.ip)
        addresses.addWidget(self.interface)
        row.addLayout(addresses, 1)

        traffic = QVBoxLayout()
        traffic.setSpacing(1)
        self.down = TextLabel("", size=FONTS.dash_subtitle, parent=self)
        self.up = TextLabel("", size=FONTS.dash_subtitle, parent=self)
        for label in (self.down, self.up):
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        traffic.addWidget(self.down)
        traffic.addWidget(self.up)
        row.addLayout(traffic)
        return row

    def _build_action_strip(self) -> QWidget:
        strip = ActionStrip(self)
        row = QHBoxLayout(strip)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(6)

        for glyph, action in ((GLYPHS.lock, "lock"), (GLYPHS.sleep, "sleep")):
            button = ActionButton(glyph, parent=strip)
            button.clicked.connect(lambda _=False, a=action: self.power_action.emit(a))
            row.addWidget(button)

        row.addStretch(1)
        self.datetime = TextLabel("", size=FONTS.dash_subtitle, parent=strip)
        row.addWidget(self.datetime)
        row.addStretch(1)

        self.weather_icon = IconLabel(GLYPHS.weather_cloudy, parent=strip)
        self.weather_icon.set_size(FONTS.dash_subtitle + 2)
        self.weather_text = TextLabel("", size=FONTS.dash_subtitle, parent=strip)
        row.addWidget(self.weather_icon)
        row.addWidget(self.weather_text)
        row.addStretch(1)

        for glyph, action in ((GLYPHS.restart, "reboot"), (GLYPHS.power, "shutdown")):
            button = ActionButton(glyph, parent=strip)
            button.clicked.connect(lambda _=False, a=action: self.power_action.emit(a))
            row.addWidget(button)
        return strip

    def _picture_path(self) -> str:
        configured = self._config.display_picture
        if configured and Path(configured).is_file():
            return configured
        return account_picture() or ""

    # -- wiring ------------------------------------------------------------

    def bind(self) -> None:
        for name in ("battery", "network", "bandwidth", "weather", "clock"):
            self.module(name).changed.connect(self.refresh)

    def refresh(self) -> None:
        self.uptime.setText(f"up {format_uptime(uptime_seconds())}")

        battery = self.module("battery")
        present = bool(battery.get("present", False))
        percent = int(battery.get("percent", 0))
        charging = bool(battery.get("charging", False))
        self.battery_icon.set_glyph(battery_glyph(percent, charging, present))
        self.battery_icon.set_color(battery_color(percent, charging) if present else PALETTE.battery_good)
        self.battery_text.setVisible(present)
        if present:
            self.battery_text.setText(f"{percent}%")

        network = self.module("network")
        self.ip.setText(str(network.get("ip", "0.0.0.0")))
        self.interface.setText(str(network.get("ssid", "")) or str(network.get("kind", "")))

        bandwidth = self.module("bandwidth")
        self.down.setText(f"{GLYPHS.download} {format_bytes(float(bandwidth.get('down_total', 0)))}")
        self.up.setText(f"{GLYPHS.upload} {format_bytes(float(bandwidth.get('up_total', 0)))}")

        self.datetime.setText(QDateTime.currentDateTime().toString("hh:mm ap ddd, d MMM yyyy"))

        weather = self.module("weather")
        glyph, colour = weather_glyph(str(weather.get("label", "cloudy")))
        self.weather_icon.set_glyph(glyph)
        self.weather_icon.set_color(colour)
        self.weather_text.setText(str(weather.get("temperature_text", "--")))

    def apply_config(self, config: Config) -> None:
        self._config = config
        self.avatar.set_path(self._picture_path())
