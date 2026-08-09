"""Surface base class.

A surface is a page inside the pill, not a window.  It knows which `PillState`
it serves, it may contribute measurements to the morph context (the pill bar's
natural row width, the notification list's height), and it gets told when it
becomes visible so it can start and stop the modules it reads.
"""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import QEasingCurve, QVariantAnimation, pyqtSignal
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

from shell.anim import PANEL_FADE, FadeTiming
from shell.modules.base import Module, ModuleRegistry
from shell.state import PillState, PillStateMachine


class Surface(QWidget):
    """Base for every page."""

    #: Raise when the surface's own measurements changed and the pill should
    #: re-resolve its geometry (row grew, notification list got longer).
    geometry_hint_changed = pyqtSignal()

    #: The state this surface is shown for.
    state: PillState = PillState.IDLE
    #: Modules this surface needs while visible.
    uses: tuple[str, ...] = ()
    #: How this surface's content fades in and out.  The default is the
    #: original's panel timing: a 15ms beat, then 150ms OutExpo -- the box is
    #: already growing when the content arrives, which is what makes the morph
    #: read as one movement rather than two.
    fade: FadeTiming = PANEL_FADE

    #: Raised once the fade-out has finished, so the pill can stop drawing it.
    faded_out = pyqtSignal()

    def __init__(self, registry: ModuleRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._held: dict[str, Module] = {}
        self._visible = False
        self._bound_to: dict[str, Module] = {}

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QVariantAnimation(self)
        self._fade.valueChanged.connect(lambda value: self._effect.setOpacity(float(value)))
        self._fade.finished.connect(self._on_fade_finished)

    # -- fading ------------------------------------------------------------

    def fade_in(self) -> None:
        self._start_fade(1.0, self.fade.in_ms, self.fade.delay_ms)

    def fade_out(self) -> None:
        self._start_fade(0.0, self.fade.out_ms, 0)

    def show_instantly(self) -> None:
        """No fade -- used on the first paint, before anything is on screen."""
        self._fade.stop()
        self._effect.setOpacity(1.0)

    @property
    def opacity(self) -> float:
        return float(self._effect.opacity())

    def _start_fade(self, target: float, duration_ms: int, delay_ms: int) -> None:
        start = self._effect.opacity()
        if abs(start - target) < 0.001 and self._fade.state() != QVariantAnimation.State.Running:
            if target == 0.0:
                self.faded_out.emit()
            return
        self._fade.stop()
        # A delay is expressed as a flat leading segment rather than a timer:
        # one animation is easier to interrupt cleanly than a timer plus one.
        total = max(1, duration_ms + delay_ms)
        self._fade.setDuration(total)
        self._fade.setStartValue(start)
        self._fade.setEndValue(target)
        if delay_ms and total:
            hold = delay_ms / total
            curve = QEasingCurve(QEasingCurve.Type.OutExpo)
            self._fade.setEasingCurve(curve)
            self._fade.setKeyValues([(0.0, start), (hold, start), (1.0, target)])
        else:
            self._fade.setEasingCurve(QEasingCurve.Type.OutExpo)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._effect.opacity() <= 0.001:
            self.faded_out.emit()

    # -- modules -----------------------------------------------------------

    def module(self, name: str) -> Module:
        """Get a module, holding a reference for as long as this surface lives.

        Surfaces that are shown and hidden constantly (the pill bar) hold their
        modules permanently; ones that are rarely opened acquire on show and
        release on hide -- see `retain_modules`.
        """
        module = self._held.get(name)
        if module is None:
            module = self._registry.get(name)
            self._held[name] = module
        return module

    def release_modules(self, names: Iterable[str] | None = None) -> None:
        for name in list(names if names is not None else self._held):
            if self._held.pop(name, None) is not None:
                self._registry.release(name)

    #: When True the surface keeps its modules running while hidden.  The pill
    #: bar sets this: its clock and battery must stay live because it is what
    #: the pill falls back to.
    retain_modules = False

    # -- visibility --------------------------------------------------------

    def on_shown(self) -> None:
        """Acquire modules, wire them up, then read them.

        Deliberately not done in `__init__`: constructing a surface must not
        start a WiFi scan or fetch the weather for a panel nobody has opened.
        """
        self._visible = True
        current = {name: self.module(name) for name in self.uses}
        # Rebind only when the instances actually changed.  Releasing on hide
        # does not always destroy a module -- something else may still hold it
        # -- and binding twice to a survivor would double every signal.
        if current != self._bound_to:
            self.bind()
            self._bound_to = current
        self.refresh()

    def on_hidden(self) -> None:
        self._visible = False
        if not self.retain_modules:
            self.release_modules()

    @property
    def is_visible_surface(self) -> bool:
        return self._visible

    # -- hooks -------------------------------------------------------------

    def bind(self) -> None:
        """Connect to the modules in `uses`.

        Runs on first show, and again whenever a module this surface uses has
        been destroyed and rebuilt since the last one.
        """

    def refresh(self) -> None:
        """Re-read module state into the widgets.  Called when shown."""

    def contribute_context(self, machine: PillStateMachine) -> None:
        """Push measurements into the morph context before geometry is resolved.

        Only the pill bar and the control center need this; the fixed-size
        surfaces leave it alone.
        """
