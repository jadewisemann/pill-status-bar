"""The morph table is the specification; these are its assertions.

Every number here comes from spec §1.2.  If a value changes, it changes because
the design changed -- not because the implementation drifted.
"""

from __future__ import annotations

import pytest

from shell.state import (
    EXCLUSIVE_STATES,
    HEIGHT_DURATION_MEDIA_MS,
    HEIGHT_DURATION_MS,
    WIDTH_DURATION_MS,
    MorphContext,
    PillState,
    PillStateMachine,
    height_duration_for,
    resolve_geometry,
)
from shell.theme import PALETTE


@pytest.fixture
def ctx() -> MorphContext:
    return MorphContext(row_width=240.0, row_height=24.0, pill_scale=1.0)


# -- the table --------------------------------------------------------------


def test_idle_width_is_row_plus_twelve_plus_fiftysix(ctx: MorphContext) -> None:
    morph = resolve_geometry(PillState.IDLE, ctx)
    assert morph.width == 240 + 12 + 56
    assert morph.height == 24 * 1.0 + 10
    assert morph.radius == 20


def test_idle_hover_widens_by_twelve(ctx: MorphContext) -> None:
    idle = resolve_geometry(PillState.IDLE, ctx)
    hovered = resolve_geometry(PillState.IDLE, MorphContext(**{**ctx.__dict__, "hovered": True}))
    assert hovered.width - idle.width == 12
    assert hovered.height == idle.height


def test_pill_scale_multiplies_idle_metrics() -> None:
    ctx = MorphContext(row_width=240.0, row_height=24.0, pill_scale=1.5)
    morph = resolve_geometry(PillState.IDLE, ctx)
    assert morph.width == 240 + 12 * 1.5 + 56 * 1.5
    assert morph.height == 24 * 1.5 + 10
    assert morph.radius == 30


@pytest.mark.parametrize(
    ("state", "width", "height", "radius"),
    [
        (PillState.OSD, 220, 40, 20),
        (PillState.NOTIFICATION, 305, 52, 99),
        (PillState.MEDIA_POPUP, 340, 90, 22),
        (PillState.LAUNCHER, 390, 410, 30),
        (PillState.DASHBOARD, 420, 155, 20),
        (PillState.CLIPBOARD, 460, 270, 28),
        (PillState.WALLPAPERS, 600, 308, 30),
    ],
)
def test_fixed_states(ctx: MorphContext, state: PillState, width: int, height: int, radius: int) -> None:
    morph = resolve_geometry(state, ctx)
    assert (morph.width, morph.height, morph.radius) == (width, height, radius)


def test_fixed_states_ignore_pill_scale() -> None:
    """Only the idle bar scales; the panels are absolute sizes in the table."""
    scaled = MorphContext(pill_scale=2.0)
    assert resolve_geometry(PillState.DASHBOARD, scaled).width == 420


def test_control_center_grows_for_media(ctx: MorphContext) -> None:
    without = resolve_geometry(PillState.CONTROL_CENTER, ctx)
    with_media = resolve_geometry(PillState.CONTROL_CENTER, MorphContext(media_active=True))
    assert (without.width, without.height, without.radius) == (390, 118, 25)
    assert (with_media.width, with_media.height, with_media.radius) == (390, 240, 23)


# -- the notification bump --------------------------------------------------


def test_no_notifications_means_no_bump() -> None:
    ctx = MorphContext(notification_count=0, notification_list_height=200.0)
    assert ctx.notif_bump == 0
    assert resolve_geometry(PillState.CONTROL_CENTER, ctx).height == 118


def test_bump_is_list_height_plus_forty() -> None:
    ctx = MorphContext(notification_count=1, notification_list_height=44.0)
    assert ctx.notif_bump == 84
    assert resolve_geometry(PillState.CONTROL_CENTER, ctx).height == 118 + 84


def test_bump_saturates_at_one_hundred_thirty() -> None:
    ctx = MorphContext(notification_count=8, notification_list_height=400.0)
    assert ctx.notif_bump == 130
    assert resolve_geometry(PillState.CONTROL_CENTER, ctx).height == 118 + 130


# -- backgrounds ------------------------------------------------------------


def test_media_popup_has_its_own_background(ctx: MorphContext) -> None:
    assert resolve_geometry(PillState.MEDIA_POPUP, ctx).background == PALETTE.background_media_popup


def test_control_center_background_depends_on_media() -> None:
    plain = resolve_geometry(PillState.CONTROL_CENTER, MorphContext())
    with_media = resolve_geometry(PillState.CONTROL_CENTER, MorphContext(media_active=True))
    assert plain.background == PALETTE.background
    assert with_media.background == PALETTE.background_control_center


def test_every_other_state_uses_the_default_background(ctx: MorphContext) -> None:
    for state in (PillState.IDLE, PillState.OSD, PillState.NOTIFICATION, PillState.LAUNCHER):
        assert resolve_geometry(state, ctx).background == PALETTE.background


# -- timings ----------------------------------------------------------------


def test_durations() -> None:
    assert WIDTH_DURATION_MS == 225
    assert height_duration_for(PillState.CONTROL_CENTER) == HEIGHT_DURATION_MS == 550
    assert height_duration_for(PillState.MEDIA_POPUP) == HEIGHT_DURATION_MEDIA_MS == 650


# -- the state machine ------------------------------------------------------


def test_starts_idle() -> None:
    assert PillStateMachine().state is PillState.IDLE


def test_panels_are_mutually_exclusive() -> None:
    machine = PillStateMachine()
    machine.open(PillState.CONTROL_CENTER)
    machine.open(PillState.LAUNCHER)
    assert machine.state is PillState.LAUNCHER
    assert not machine.is_open(PillState.CONTROL_CENTER)


@pytest.mark.parametrize("state", EXCLUSIVE_STATES)
def test_toggle_round_trips(state: PillState) -> None:
    machine = PillStateMachine()
    assert machine.toggle(state) is True
    assert machine.state is state
    assert machine.toggle(state) is False
    assert machine.state is PillState.IDLE


def test_an_open_panel_outranks_a_transient() -> None:
    """The control center already shows volume; an OSD on top would be noise."""
    machine = PillStateMachine()
    machine.open(PillState.CONTROL_CENTER)
    machine.open(PillState.OSD)
    assert machine.state is PillState.CONTROL_CENTER
    machine.close(PillState.CONTROL_CENTER)
    assert machine.state is PillState.OSD


def test_notification_outranks_osd_and_media() -> None:
    machine = PillStateMachine()
    machine.open(PillState.MEDIA_POPUP)
    machine.open(PillState.OSD)
    assert machine.state is PillState.OSD
    machine.open(PillState.NOTIFICATION)
    assert machine.state is PillState.NOTIFICATION
    machine.close(PillState.NOTIFICATION)
    assert machine.state is PillState.OSD


def test_close_all_returns_to_idle() -> None:
    machine = PillStateMachine()
    machine.open(PillState.WALLPAPERS)
    machine.open(PillState.NOTIFICATION)
    machine.close_all()
    assert machine.state is PillState.IDLE


def test_close_exclusive_leaves_transients_alone() -> None:
    machine = PillStateMachine()
    machine.open(PillState.DASHBOARD)
    machine.open(PillState.NOTIFICATION)
    machine.close_exclusive()
    assert machine.state is PillState.NOTIFICATION


def test_state_changed_reports_both_ends() -> None:
    machine = PillStateMachine()
    seen: list[tuple[PillState, PillState]] = []
    machine.state_changed.connect(lambda new, old: seen.append((new, old)))
    machine.open(PillState.DASHBOARD)
    machine.close_all()
    assert seen == [
        (PillState.DASHBOARD, PillState.IDLE),
        (PillState.IDLE, PillState.DASHBOARD),
    ]


def test_context_update_is_a_no_op_when_nothing_changes() -> None:
    machine = PillStateMachine()
    fired: list[int] = []
    machine.geometry_invalidated.connect(lambda: fired.append(1))
    machine.update_context(pill_scale=1.0)  # already the default
    assert fired == []
    machine.update_context(pill_scale=1.25)
    assert fired == [1]


def test_media_context_moves_the_open_control_center() -> None:
    machine = PillStateMachine()
    machine.open(PillState.CONTROL_CENTER)
    assert machine.morph().height == 118
    machine.update_context(media_active=True)
    assert machine.morph().height == 240
