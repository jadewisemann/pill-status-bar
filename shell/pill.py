"""The pill: one frameless window that changes shape.

Implementation notes that matter (spec §3.5):

* The corner radius is animated, so it cannot be a stylesheet `border-radius`.
  It is a `pyqtProperty(float)` painted by hand in `paintEvent`.
* Width and height animate on different curves and different durations, so they
  are two independent `QVariantAnimation`s driving one `setGeometry`, not a
  single geometry animation.
* The window keeps itself horizontally centred on its screen every frame, which
  is what makes the pill look like it grows outward from the middle rather than
  from its left edge.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import (
    QEasingCurve,
    QRect,
    Qt,
    QVariantAnimation,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QScreen
from PyQt6.QtWidgets import QApplication, QStackedLayout, QWidget

from shell.config import Config
from shell.platform import IS_WINDOWS
from shell.platform.window import (
    apply_backdrop,
    apply_shell_window_style,
    set_round_region,
    set_topmost,
)
from shell.state import (
    RADIUS_DURATION_MS,
    WIDTH_DURATION_MS,
    Morph,
    MorphContext,
    PillState,
    PillStateMachine,
    height_duration_for,
)
from shell.surfaces.base import Surface

logger = logging.getLogger(__name__)

EASING = QEasingCurve.Type.OutExpo
#: Anchor edge.  The original hangs off the top of the screen with
#: `pillTopMargin` above it and reserves `pillBottomMargin` below.
EDGE_TOP = "top"
EDGE_BOTTOM = "bottom"


class Pill(QWidget):
    """The single window.  Surfaces are pages inside it, never windows."""

    #: Emitted after a morph settles, with the state that is now showing.
    settled = pyqtSignal(object)

    def __init__(self, config: Config, machine: PillStateMachine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._machine = machine
        self._surfaces: dict[PillState, Surface] = {}
        self._radius = 20.0
        self._background = QColor(machine.morph().background)
        self._edge = EDGE_TOP
        self._hidden_for_fullscreen = False

        # No WindowDoesNotAcceptFocus: the launcher and clipboard need the
        # keyboard.  Focus stealing is controlled at the Win32 level instead,
        # by toggling WS_EX_NOACTIVATE around those two surfaces.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        self.setMouseTracking(True)

        self._pages = QStackedLayout(self)
        self._pages.setContentsMargins(0, 0, 0, 0)
        self._pages.setStackingMode(QStackedLayout.StackingMode.StackOne)

        self._width_anim = self._make_animation(WIDTH_DURATION_MS, self._on_width)
        self._height_anim = self._make_animation(0, self._on_height)
        self._radius_anim = self._make_animation(RADIUS_DURATION_MS, self._on_radius)
        self._height_anim.finished.connect(self._on_settled)

        machine.state_changed.connect(self._on_state_changed)
        machine.geometry_invalidated.connect(self.apply_morph)

    # -- animated properties -----------------------------------------------

    def _make_animation(self, duration: int, on_value: object) -> QVariantAnimation:
        animation = QVariantAnimation(self)
        animation.setDuration(duration)
        animation.setEasingCurve(EASING)
        animation.valueChanged.connect(on_value)  # type: ignore[arg-type]
        return animation

    @pyqtProperty(float)
    def radius(self) -> float:  # type: ignore[override]
        return self._radius

    @radius.setter  # type: ignore[no-redef]
    def radius(self, value: float) -> None:
        if abs(value - self._radius) < 0.01:
            return
        self._radius = float(value)
        self.update()

    # -- surface registration ----------------------------------------------

    def add_surface(self, surface: Surface) -> None:
        """Register a page.  The state it serves comes from the surface itself."""
        self._surfaces[surface.state] = surface
        surface.setParent(self)
        self._pages.addWidget(surface)
        surface.geometry_hint_changed.connect(self.apply_morph)

    def surface(self, state: PillState) -> Surface | None:
        return self._surfaces.get(state)

    def current_surface(self) -> Surface | None:
        return self._surfaces.get(self._machine.state)

    # -- morphing ----------------------------------------------------------

    def apply_morph(self, animated: bool = True) -> None:
        """Animate to whatever the state machine currently says."""
        state = self._machine.state
        self._sync_context(state)
        target = self._machine.morph()

        page = self._surfaces.get(state)
        if page is not None and self._pages.currentWidget() is not page:
            self._pages.setCurrentWidget(page)

        self._background = QColor(target.background)
        self._animate_to(target, state, animated)
        self.update()

    def _sync_context(self, state: PillState) -> MorphContext:
        """Let the active surface contribute its measurements to the context."""
        surface = self._surfaces.get(state)
        if surface is not None:
            surface.contribute_context(self._machine)
        return self._machine.context

    def _animate_to(self, target: Morph, state: PillState, animated: bool) -> None:
        width = int(round(target.width))
        height = int(round(target.height))

        if not animated or not self.isVisible():
            self._width_anim.stop()
            self._height_anim.stop()
            self._radius_anim.stop()
            self._radius = target.radius
            self._set_geometry(width, height)
            self._refresh_region()
            return

        self._start(self._width_anim, self.width(), width, WIDTH_DURATION_MS)
        self._start(self._height_anim, self.height(), height, height_duration_for(state))
        self._start(self._radius_anim, self._radius, target.radius, RADIUS_DURATION_MS)

    @staticmethod
    def _start(animation: QVariantAnimation, start: float, end: float, duration: int) -> None:
        if abs(start - end) < 0.5:
            return
        animation.stop()
        animation.setDuration(duration)
        animation.setStartValue(float(start))
        animation.setEndValue(float(end))
        animation.start()

    def _on_width(self, value: object) -> None:
        self._set_geometry(int(round(float(value))), self.height())  # type: ignore[arg-type]

    def _on_height(self, value: object) -> None:
        self._set_geometry(self.width(), int(round(float(value))))  # type: ignore[arg-type]

    def _on_radius(self, value: object) -> None:
        self.radius = float(value)  # type: ignore[arg-type]

    def _on_settled(self) -> None:
        self._refresh_region()
        self.settled.emit(self._machine.state)

    # -- geometry ----------------------------------------------------------

    def target_screen(self) -> QScreen | None:
        return self.screen() or QApplication.primaryScreen()

    def _set_geometry(self, width: int, height: int) -> None:
        screen = self.target_screen()
        if screen is None:
            return
        area = screen.geometry()
        x = area.x() + (area.width() - width) // 2
        if self._edge == EDGE_TOP:
            y = area.y() + self._config.pill_top_margin
        else:
            y = area.y() + area.height() - height - self._config.pill_bottom_margin
        self.setGeometry(QRect(x, y, max(1, width), max(1, height)))

    def _refresh_region(self) -> None:
        """Clip input to the pill's silhouette once it stops moving.

        Doing this per animation frame would mean a GDI region object per frame;
        during the morph the window is briefly click-transparent at the corners
        instead, which nobody can hit on purpose in 225ms.
        """
        if IS_WINDOWS:
            set_round_region(int(self.winId()), self.width(), self.height(), int(round(self._radius)))

    def reposition(self) -> None:
        """Re-centre after a resolution or monitor change."""
        self._set_geometry(self.width(), self.height())

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), self._radius, self._radius)
        painter.fillPath(path, self._background)
        painter.end()

    # -- input -------------------------------------------------------------

    def enterEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        if self._machine.state is PillState.IDLE:
            self._machine.update_context(hovered=True)

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._machine.update_context(hovered=False)

    # -- platform integration ----------------------------------------------

    def attach_to_windows(self) -> None:
        """Apply the Win32 window traits.  Safe to call more than once."""
        if not IS_WINDOWS:
            return
        hwnd = int(self.winId())
        apply_shell_window_style(hwnd)
        apply_backdrop(hwnd, acrylic=True, rounded=False)
        set_topmost(hwnd, True)
        self._refresh_region()

    def reassert_topmost(self) -> None:
        """Other shells and installers steal the top slot; take it back."""
        if IS_WINDOWS and self.isVisible():
            set_topmost(int(self.winId()), True)

    def set_hidden_for_fullscreen(self, hidden: bool) -> None:
        """Hide over games and video without forgetting the current state."""
        if hidden == self._hidden_for_fullscreen:
            return
        self._hidden_for_fullscreen = hidden
        if hidden:
            self.hide()
        else:
            self.show()
            self.attach_to_windows()

    # -- config ------------------------------------------------------------

    def apply_config(self, config: Config) -> None:
        self._config = config
        self.apply_morph(animated=False)

    def _on_state_changed(self, new_state: PillState, previous: PillState) -> None:
        old_surface = self._surfaces.get(previous)
        if old_surface is not None:
            old_surface.on_hidden()
        new_surface = self._surfaces.get(new_state)
        if new_surface is not None:
            new_surface.on_shown()
