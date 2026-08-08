"""The morph state machine.

One window changes shape.  That is the whole product, so the size table lives
here as data, transcribed from the ChillPill-Shell spec §1.2, and every other
part of the shell reads it rather than hard-coding geometry.

Two things this module owns:

* `resolve_geometry()` -- state + context -> (width, height, radius, background)
* `PillStateMachine` -- which state is current, given what is open right now
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

from PyQt6.QtCore import QObject, pyqtSignal

from shell.theme import PALETTE, Palette


class PillState(StrEnum):
    """Every shape the pill can take."""

    IDLE = "idle"
    OSD = "osd"
    NOTIFICATION = "notification"
    MEDIA_POPUP = "mediaPopup"
    CONTROL_CENTER = "controlCenter"
    LAUNCHER = "launcher"
    DASHBOARD = "dashboard"
    CLIPBOARD = "clipboard"
    WALLPAPERS = "wallpapers"


#: States that own the whole pill and cannot be shown together -- opening one
#: closes the others (spec §1.2: the QML IpcHandler forces the rest to false).
EXCLUSIVE_STATES: tuple[PillState, ...] = (
    PillState.CONTROL_CENTER,
    PillState.LAUNCHER,
    PillState.DASHBOARD,
    PillState.CLIPBOARD,
    PillState.WALLPAPERS,
)

#: Transient overlays, highest priority first.  An open exclusive panel beats
#: all of them: it already shows the volume slider, the media art and the
#: notification stack, so an OSD on top would be redundant.
TRANSIENT_PRIORITY: tuple[PillState, ...] = (
    PillState.NOTIFICATION,
    PillState.OSD,
    PillState.MEDIA_POPUP,
)


@dataclass(frozen=True)
class MorphContext:
    """Everything the size table depends on besides the state itself."""

    #: Natural size of the pill bar's content row, in logical pixels.
    row_width: float = 240.0
    row_height: float = 24.0
    #: `pillScale` from the config.  Multiplies most of the idle metrics.
    pill_scale: float = 1.0
    #: Pointer is over the pill.  Idle only: widens the bar by 12 * scale.
    hovered: bool = False
    #: A media session exists -- the control center grows to fit the player.
    media_active: bool = False
    #: Height of the notification list inside the control center, unscaled.
    notification_list_height: float = 0.0
    #: Number of notifications in the stack; 0 means no bump at all.
    notification_count: int = 0

    @property
    def notif_bump(self) -> float:
        """Spec §1.2: min(list height + 40, 130), and exactly 0 when empty."""
        if self.notification_count <= 0:
            return 0.0
        return min(self.notification_list_height + 40.0, 130.0)


@dataclass(frozen=True)
class Morph:
    """A resolved target shape."""

    width: float
    height: float
    radius: float
    background: str


#: state -> (width, height, radius) as functions of the context.
#: Transcribed literally from spec §1.2; `ps` is `ctx.pill_scale`.
_TABLE: dict[PillState, tuple[Callable[[MorphContext], float], ...]] = {
    PillState.IDLE: (
        lambda c: c.row_width + 12 * c.pill_scale + (68 if c.hovered else 56) * c.pill_scale,
        lambda c: c.row_height * c.pill_scale + 10,
        lambda c: 20 * c.pill_scale,
    ),
    PillState.OSD: (
        lambda c: 220.0,
        lambda c: 40.0,
        lambda c: 20.0,
    ),
    PillState.NOTIFICATION: (
        lambda c: 305.0,
        lambda c: 52.0,
        lambda c: 99.0,  # fully rounded -- a literal pill
    ),
    PillState.MEDIA_POPUP: (
        lambda c: 340.0,
        lambda c: 90.0,
        lambda c: 22.0,
    ),
    PillState.CONTROL_CENTER: (
        lambda c: 390.0,
        lambda c: (240.0 if c.media_active else 118.0) + c.notif_bump,
        lambda c: 23.0 if c.media_active else 25.0,
    ),
    PillState.LAUNCHER: (
        lambda c: 390.0,
        lambda c: 410.0,
        lambda c: 30.0,
    ),
    PillState.DASHBOARD: (
        lambda c: 420.0,
        lambda c: 155.0,
        lambda c: 20.0,
    ),
    PillState.CLIPBOARD: (
        lambda c: 460.0,
        lambda c: 270.0,
        lambda c: 28.0,
    ),
    PillState.WALLPAPERS: (
        lambda c: 600.0,
        lambda c: 308.0,
        lambda c: 30.0,
    ),
}


def background_for(state: PillState, ctx: MorphContext, palette: Palette = PALETTE) -> str:
    """Spec §1.2: the pill's fill is state-dependent."""
    if state is PillState.MEDIA_POPUP:
        return palette.background_media_popup
    if state is PillState.CONTROL_CENTER and ctx.media_active:
        return palette.background_control_center
    return palette.background


def resolve_geometry(state: PillState, ctx: MorphContext, palette: Palette = PALETTE) -> Morph:
    """Look up the target shape for `state` under `ctx`."""
    width_fn, height_fn, radius_fn = _TABLE[state]
    return Morph(
        width=width_fn(ctx),
        height=height_fn(ctx),
        radius=radius_fn(ctx),
        background=background_for(state, ctx, palette),
    )


# --------------------------------------------------------------------------
# Animation timing (spec §1.2)
# --------------------------------------------------------------------------

WIDTH_DURATION_MS = 225
RADIUS_DURATION_MS = 225
HEIGHT_DURATION_MS = 550
#: The media auto-popup grows more slowly than everything else.
HEIGHT_DURATION_MEDIA_MS = 650


def height_duration_for(state: PillState) -> int:
    return HEIGHT_DURATION_MEDIA_MS if state is PillState.MEDIA_POPUP else HEIGHT_DURATION_MS


# --------------------------------------------------------------------------
# State machine
# --------------------------------------------------------------------------


class PillStateMachine(QObject):
    """Tracks what is open and derives the single current state.

    Surfaces never set the state directly -- they open and close themselves and
    the machine picks the winner by priority.  That keeps the exclusivity rule
    in one place instead of scattered across five toggle handlers.
    """

    #: (new state, previous state)
    state_changed = pyqtSignal(object, object)
    #: Emitted whenever the target geometry may have changed, state or not.
    geometry_invalidated = pyqtSignal()

    def __init__(self, ctx: MorphContext | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx or MorphContext()
        self._exclusive: PillState | None = None
        self._transient: set[PillState] = set()
        self._state = PillState.IDLE

    # -- queries -----------------------------------------------------------

    @property
    def state(self) -> PillState:
        return self._state

    @property
    def context(self) -> MorphContext:
        return self._ctx

    @property
    def exclusive(self) -> PillState | None:
        return self._exclusive

    def is_open(self, state: PillState) -> bool:
        if state in EXCLUSIVE_STATES:
            return self._exclusive is state
        if state is PillState.IDLE:
            return self._state is PillState.IDLE
        return state in self._transient

    def morph(self) -> Morph:
        return resolve_geometry(self._state, self._ctx)

    # -- mutations ---------------------------------------------------------

    def update_context(self, **fields: object) -> None:
        """Patch the context; re-resolves the state (media_active moves it)."""
        new_ctx = replace(self._ctx, **fields)  # type: ignore[arg-type]
        if new_ctx == self._ctx:
            return
        self._ctx = new_ctx
        self._reevaluate()

    def open(self, state: PillState) -> None:
        if state is PillState.IDLE:
            self.close_all()
            return
        if state in EXCLUSIVE_STATES:
            self._exclusive = state
        else:
            self._transient.add(state)
        self._reevaluate()

    def close(self, state: PillState) -> None:
        if state in EXCLUSIVE_STATES:
            if self._exclusive is state:
                self._exclusive = None
        else:
            self._transient.discard(state)
        self._reevaluate()

    def toggle(self, state: PillState) -> bool:
        """Returns the resulting open/closed state of `state`."""
        if self.is_open(state):
            self.close(state)
            return False
        self.open(state)
        return True

    def close_all(self) -> None:
        self._exclusive = None
        self._transient.clear()
        self._reevaluate()

    def close_exclusive(self) -> None:
        """Dismiss whichever panel is open, leaving transient overlays alone."""
        self._exclusive = None
        self._reevaluate()

    # -- internals ---------------------------------------------------------

    def _resolve_state(self) -> PillState:
        if self._exclusive is not None:
            return self._exclusive
        for candidate in TRANSIENT_PRIORITY:
            if candidate in self._transient:
                return candidate
        return PillState.IDLE

    def _reevaluate(self) -> None:
        previous, self._state = self._state, self._resolve_state()
        if previous is not self._state:
            self.state_changed.emit(self._state, previous)
        self.geometry_invalidated.emit()
