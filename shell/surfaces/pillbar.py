"""The idle surface: the status bar itself.

Left to right: battery, volume, workspaces, network, clock -- the original's
order, at its spacing (13 * paddingScale) and margins (28 either side).  There
is no centring and no stretch; the row is its natural width and the pill sizes
itself around it, which is what makes the idle width formula in `shell.state`
depend on this widget's size hint.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from shell.config import Config
from shell.modules.base import ModuleRegistry
from shell.state import PillState, PillStateMachine
from shell.surfaces.base import Surface
from shell.theme import (
    FONTS,
    GLYPHS,
    PALETTE,
    battery_color,
    battery_glyph,
    padding_scale,
    volume_glyph,
    wifi_glyph,
)
from shell.widgets import IconLabel, TextLabel, WorkspaceButton

#: The original's `Layout.maximumWidth` on the SSID label, before pillScale.
SSID_MAX_WIDTH = 90


class WorkspaceStrip(QWidget):
    """`maxWorkspaces` numbered squares; click one to switch."""

    switch_requested = pyqtSignal(int)

    def __init__(self, count: int, pill_scale: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pill_scale = pill_scale
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(int(round(4 * padding_scale(pill_scale))))
        self._buttons: list[WorkspaceButton] = []
        self.set_count(count)

    def set_count(self, count: int) -> None:
        while len(self._buttons) < count:
            button = WorkspaceButton(len(self._buttons) + 1, self._pill_scale, parent=self)
            button.activated.connect(self.switch_requested)
            self._layout.addWidget(button)
            self._buttons.append(button)
        while len(self._buttons) > count:
            button = self._buttons.pop()
            self._layout.removeWidget(button)
            button.deleteLater()

    def set_scale(self, pill_scale: float) -> None:
        self._pill_scale = pill_scale
        self._layout.setSpacing(int(round(4 * padding_scale(pill_scale))))
        for button in self._buttons:
            button.set_pill_scale(pill_scale)

    def set_state(self, current: int, occupied: int) -> None:
        """`occupied` is how many desktops exist; the rest render as empty."""
        for index, button in enumerate(self._buttons, start=1):
            if index == current:
                button.set_state("active")
            elif index <= occupied:
                button.set_state("used")
            else:
                button.set_state("empty")


class PillBar(Surface):
    state = PillState.IDLE
    uses = ("clock", "battery", "volume", "network", "workspaces", "timer")
    #: The bar is what the pill falls back to, so its modules never stop.
    retain_modules = True

    #: A click asked for a surface (the app decides whether to honour it).
    surface_requested = pyqtSignal(object)  # PillState

    def __init__(self, registry: ModuleRegistry, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        self._config = config

        row = QHBoxLayout(self)
        self._row = row

        self.battery_icon = IconLabel(parent=self)
        self.battery_text = TextLabel("", parent=self)
        self.volume_icon = IconLabel(parent=self)
        self.volume_text = TextLabel("", parent=self)
        self.workspaces = WorkspaceStrip(config.max_workspaces, config.pill_scale, parent=self)
        self.network_icon = IconLabel(GLYPHS.wifi_none, parent=self)
        self.network_text = TextLabel("", parent=self)
        self.timer_text = TextLabel("", parent=self)
        self.clock = TextLabel("--:--", parent=self)

        for widget in (
            self.battery_icon,
            self.battery_text,
            self.volume_icon,
            self.volume_text,
            self.workspaces,
            self.network_icon,
            self.network_text,
            self.timer_text,
            self.clock,
        ):
            row.addWidget(widget)

        self.timer_text.hide()
        self.workspaces.switch_requested.connect(self._switch_workspace)
        self.volume_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.volume_icon.mouseReleaseEvent = self._on_volume_click  # type: ignore[assignment]

        self.setMouseTracking(True)
        self.apply_config(config)

    # -- wiring ------------------------------------------------------------

    def bind(self) -> None:
        for name in self.uses:
            self.module(name).changed.connect(self.refresh)

    def refresh(self) -> None:
        self._refresh_battery()
        self._refresh_volume()
        self._refresh_workspaces()
        self._refresh_network()
        self._refresh_timer()
        self.clock.setText(str(self.module("clock").get("text", "--:--")))
        self.geometry_hint_changed.emit()

    def _refresh_battery(self) -> None:
        battery = self.module("battery")
        present = bool(battery.get("present", False))
        percent = int(battery.get("percent", 0))
        charging = bool(battery.get("charging", False))
        self.battery_icon.set_glyph(battery_glyph(percent, charging, present))
        # A machine with no battery shows a green plug and no number.
        self.battery_icon.set_color(battery_color(percent, charging) if present else PALETTE.battery_good)
        self.battery_text.setVisible(present)
        if present:
            self.battery_text.setText(f"{percent}%")

    def _refresh_volume(self) -> None:
        volume = self.module("volume")
        percent = int(volume.get("percent", 0))
        muted = bool(volume.get("muted", False))
        self.volume_icon.set_glyph(volume_glyph(percent, muted))
        self.volume_icon.set_color(PALETTE.volume_muted if muted else PALETTE.fg)
        self.volume_text.setText("muted" if muted else f"{percent}%")

    def _refresh_workspaces(self) -> None:
        workspaces = self.module("workspaces")
        if not workspaces.get("enabled", False):
            self.workspaces.hide()
            return
        self.workspaces.show()
        self.workspaces.set_state(
            current=int(workspaces.get("current", 1)),
            occupied=int(workspaces.get("total", 0)),
        )

    def _refresh_network(self) -> None:
        network = self.module("network")
        kind = str(network.get("kind", "none"))
        connected = kind != "none"
        signal = int(network.get("signal", 0))
        ssid = str(network.get("ssid", ""))

        self.network_icon.set_glyph(wifi_glyph(signal, connected=kind == "wifi"))
        self.network_icon.set_color(PALETTE.wifi_on if connected else PALETTE.wifi_off)
        if not connected:
            self.network_text.setText("off")
        elif kind == "ethernet":
            self.network_text.setText("wired")
        else:
            self.network_text.setText(ssid or "N/A")

    def _refresh_timer(self) -> None:
        timer = self.module("timer")
        running = bool(timer.get("running", False))
        self.timer_text.setVisible(running)
        if running:
            self.timer_text.setText(f"{GLYPHS.timer_running} {timer.get('text', '')}")

    # -- geometry ----------------------------------------------------------

    def contribute_context(self, machine: PillStateMachine) -> None:
        """Feed the measured row size into the idle geometry formula."""
        hint = self._row.sizeHint()
        machine.update_context(
            row_width=float(hint.width()),
            row_height=float(max(hint.height(), 24)),
            pill_scale=self._config.pill_scale,
        )

    def apply_config(self, config: Config) -> None:
        self._config = config
        scale = config.pill_scale
        padding = padding_scale(scale)

        self._row.setContentsMargins(int(round(28 * padding)), 0, int(round(28 * padding)), 0)
        self._row.setSpacing(int(round(13 * padding)))

        text_size = max(6, int(round(FONTS.bar_text * scale)))
        icon_size = max(6, int(round(FONTS.bar_icon * scale)))
        for label in (self.battery_text, self.volume_text, self.network_text, self.timer_text, self.clock):
            label.set_size(text_size, weight=500)
        # The clock is tracked slightly tighter, as in the original.
        self.clock.set_size(text_size, weight=500, letter_spacing=-0.5)
        for icon in (self.battery_icon, self.volume_icon, self.network_icon):
            icon.set_size(icon_size)

        self.network_text.setMaximumWidth(int(round(SSID_MAX_WIDTH * scale)))
        self.workspaces.set_scale(scale)
        self.workspaces.set_count(config.max_workspaces)
        self.timer_text.set_color(PALETTE.fg)
        self.refresh()

    # -- interaction -------------------------------------------------------

    def _on_volume_click(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.module("volume").toggle_mute()  # type: ignore[attr-defined]

    def _switch_workspace(self, number: int) -> None:
        self.module("workspaces").switch_to(number)  # type: ignore[attr-defined]

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        """Left opens the control center, right the dashboard, middle the clipboard.

        The same three buttons the original binds, so muscle memory carries over.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.surface_requested.emit(PillState.CONTROL_CENTER)
        elif event.button() == Qt.MouseButton.RightButton:
            self.surface_requested.emit(PillState.DASHBOARD)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.surface_requested.emit(PillState.CLIPBOARD)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override
        self.module("volume").step(5 if event.angleDelta().y() > 0 else -5)  # type: ignore[attr-defined]
