"""IPC grammar: the CLI shorthand and the wire form must agree."""

from __future__ import annotations

import pytest

from shell.ipc.protocol import (
    Command,
    ProtocolError,
    parse_argv,
    parse_message,
    parse_switch,
    parse_value,
    resolve_target,
)
from shell.state import PillState


def test_argv_and_wire_forms_agree() -> None:
    from_argv = parse_argv(["toggle", "controlCenter"])
    from_wire = parse_message(from_argv.to_json())
    assert (from_wire.cmd, from_wire.target) == (from_argv.cmd, from_argv.target)


@pytest.mark.parametrize(
    ("target", "state"),
    [
        ("controlCenter", PillState.CONTROL_CENTER),
        ("dashboard", PillState.DASHBOARD),
        ("clipboard", PillState.CLIPBOARD),
        ("launcher", PillState.LAUNCHER),
        ("wallpapers", PillState.WALLPAPERS),
    ],
)
def test_targets_map_to_states(target: str, state: PillState) -> None:
    assert Command(cmd="toggle", target=target).state is state


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("cliphist", "clipboard"),
        ("miniDashboard", "dashboard"),
        ("appLauncher", "launcher"),
        ("wallpaperSwitcher", "wallpapers"),
    ],
)
def test_original_shell_names_still_work(alias: str, canonical: str) -> None:
    """Scripts written against ChillPill-Shell's IPC keep working."""
    assert resolve_target(alias) == canonical
    assert parse_argv(["toggle", alias]).state is Command(cmd="toggle", target=canonical).state


def test_star_closes_everything() -> None:
    assert parse_argv(["hide", "*"]).target == "*"


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(ProtocolError, match="unknown command"):
        parse_argv(["explode"])


def test_unknown_target_is_rejected() -> None:
    with pytest.raises(ProtocolError, match="unknown target"):
        parse_argv(["toggle", "kitchenSink"])


def test_surface_command_needs_a_target() -> None:
    with pytest.raises(ProtocolError, match="needs a target"):
        parse_argv(["toggle"])


def test_value_command_needs_a_value() -> None:
    with pytest.raises(ProtocolError, match="needs a value"):
        parse_argv(["volume"])


def test_non_object_message_is_rejected() -> None:
    with pytest.raises(ProtocolError):
        parse_message("[1, 2, 3]")


def test_malformed_message_is_rejected() -> None:
    with pytest.raises(ProtocolError, match="not JSON"):
        parse_message("{oops")


# -- value parsing ----------------------------------------------------------


def test_absolute_value() -> None:
    assert parse_value("40", current=10) == 40


def test_relative_steps() -> None:
    assert parse_value("+5", current=10) == 15
    assert parse_value("-5", current=10) == 5


def test_values_are_clamped() -> None:
    assert parse_value("+50", current=80) == 100
    assert parse_value("-50", current=10) == 0
    assert parse_value("500", current=0) == 100


def test_non_numeric_value_is_rejected() -> None:
    with pytest.raises(ProtocolError):
        parse_value("loud", current=0)


@pytest.mark.parametrize(("raw", "expected"), [("on", True), ("off", False), ("1", True), ("no", False)])
def test_switches(raw: str, expected: bool) -> None:
    assert parse_switch(raw, current=not expected) is expected


def test_toggle_switch_inverts() -> None:
    assert parse_switch("toggle", current=True) is False
    assert parse_switch("toggle", current=False) is True


def test_wallpaper_path_with_spaces_survives() -> None:
    command = parse_argv(["wallpaper", "C:\\My", "Pictures\\a.png"])
    assert command.args["path"] == "C:\\My Pictures\\a.png"
