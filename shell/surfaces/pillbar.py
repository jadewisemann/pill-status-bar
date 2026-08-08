"""The idle surface: the status bar itself.

This is the only surface whose size feeds back into the morph table -- the idle
width is `row.width + 12*ps + 56*ps`, where `row` is this widget's natural
content width, so it measures itself and pushes the number into the context.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from shell.config import Config
from shell.modules.base import ModuleRegistry
from shell.state import PillState, PillStateMachine
from shell.surfaces.base import Surface
from shell.theme import GLYPHS, PALETTE, battery_color, battery_glyph, volume_glyph
from shell.widgets import IconLabel, TextLabel


class WorkspaceDots(QWidget):
    """One dot per virtual desktop; click to switch."""

    switch_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._dots: list[IconLabel] = []

    def set_state(self, count: int, current: int) -> None:
        while len(self._dots) < count:
            dot = IconLabel(GLYPHS.workspace_inactive, size=8, parent=self)
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            index = len(self._dots) + 1
            dot.mouseReleaseEvent = lambda _event, n=index: self.switch_requested.emit(n)  # type: ignore[assignment]
            self._layout.addWidget(dot)
            self._dots.append(dot)
        while len(self._dots) > count:
            dot = self._dots.pop()
            self._layout.removeWidget(dot)
            dot.deleteLater()
        for index, dot in enumerate(self._dots, start=1):
            active = index == current
            dot.set_glyph(GLYPHS.workspace_active if active else GLYPHS.workspace_inactive)
            dot.set_color(PALETTE.text if active else PALETTE.text_dim)


class PillBar(Surface):
    """Workspaces, volume, network, clock, battery -- left to right."""

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
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(10)

        self._workspaces = WorkspaceDots(self)
        self._volume_icon = IconLabel(GLYPHS.volume_high, parent=self)
        self._network_icon = IconLabel(GLYPHS.wifi_off, parent=self)
        self._timer_label = TextLabel("", color=PALETTE.accent, parent=self)
        self._clock = TextLabel("--:--", bold=True, parent=self)
        self._battery_icon = IconLabel(GLYPHS.battery_alert, parent=self)
        self._battery_text = TextLabel("--", color=PALETTE.text_muted, parent=self)

        row.addWidget(self._workspaces)
        row.addWidget(self._volume_icon)
        row.addWidget(self._network_icon)
        row.addStretch(1)
        row.addWidget(self._clock)
        row.addStretch(1)
        row.addWidget(self._timer_label)
        row.addWidget(self._battery_icon)
        row.addWidget(self._battery_text)
        self._row = row
        self._timer_label.hide()

        self._volume_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self._volume_icon.mouseReleaseEvent = self._on_volume_click  # type: ignore[assignment]
        self._workspaces.switch_requested.connect(self._switch_workspace)

        self.setMouseTracking(True)

    # -- wiring ------------------------------------------------------------

    def bind(self) -> None:
        for name in self.uses:
            self.module(name).changed.connect(self.refresh)

    def refresh(self) -> None:
        clock = self.module("clock")
        self._clock.setText(str(clock.get("text", "--:--")))

        battery = self.module("battery")
        if battery.get("present", False):
            percent = int(battery.get("percent", 0))
            charging = bool(battery.get("charging", False))
            self._battery_icon.set_glyph(battery_glyph(percent, charging))
            self._battery_icon.set_color(battery_color(percent, charging))
            self._battery_text.setText(f"{percent}%")
            self._battery_icon.show()
            self._battery_text.show()
        else:
            self._battery_icon.hide()
            self._battery_text.hide()

        volume = self.module("volume")
        percent = int(volume.get("percent", 0))
        muted = bool(volume.get("muted", False))
        self._volume_icon.set_glyph(volume_glyph(percent, muted))
        self._volume_icon.set_color(PALETTE.text_muted if muted else PALETTE.text)

        network = self.module("network")
        kind = str(network.get("kind", "none"))
        self._network_icon.set_glyph({"wifi": GLYPHS.wifi, "ethernet": GLYPHS.ethernet}.get(kind, GLYPHS.wifi_off))
        self._network_icon.set_color(PALETTE.text if kind != "none" else PALETTE.text_dim)

        workspaces = self.module("workspaces")
        if workspaces.get("enabled", False):
            self._workspaces.show()
            self._workspaces.set_state(int(workspaces.get("count", 0)), int(workspaces.get("current", 1)))
        else:
            self._workspaces.hide()

        timer = self.module("timer")
        if timer.get("running", False):
            self._timer_label.setText(f"{GLYPHS.timer} {timer.get('text', '')}")
            self._timer_label.show()
        else:
            self._timer_label.hide()

        self.geometry_hint_changed.emit()

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
        self.refresh()

    # -- interaction -------------------------------------------------------

    def _on_volume_click(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.module("volume").toggle_mute()  # type: ignore[attr-defined]

    def _switch_workspace(self, number: int) -> None:
        self.module("workspaces").switch_to(number)  # type: ignore[attr-defined]

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.surface_requested.emit(PillState.CONTROL_CENTER)
        elif event.button() == Qt.MouseButton.RightButton:
            self.surface_requested.emit(PillState.DASHBOARD)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override
        """Scrolling the bar changes volume, like the original."""
        self.module("volume").step(5 if event.angleDelta().y() > 0 else -5)  # type: ignore[attr-defined]
