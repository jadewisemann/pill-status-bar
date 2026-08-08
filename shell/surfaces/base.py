"""Surface base class.

A surface is a page inside the pill, not a window.  It knows which `PillState`
it serves, it may contribute measurements to the morph context (the pill bar's
natural row width, the notification list's height), and it gets told when it
becomes visible so it can start and stop the modules it reads.
"""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

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

    def __init__(self, registry: ModuleRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._held: dict[str, Module] = {}
        self._visible = False
        self._bound_to: dict[str, Module] = {}

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
