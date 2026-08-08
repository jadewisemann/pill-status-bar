"""End-to-end wiring, exercised offscreen.

Builds the real `ChillPillApp` -- real modules, real surfaces, real pill -- and
drives it through the IPC command handler.  Off Windows the platform modules
report themselves unavailable, which is exactly the degraded path this checks:
the shell must come up and stay responsive with nothing behind it.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from shell.app import ChillPillApp  # noqa: E402
from shell.ipc.protocol import Command, parse_argv  # noqa: E402
from shell.state import PillState  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def shell(qapp: QApplication, tmp_path, monkeypatch) -> ChillPillApp:
    """A live shell with its config and caches pointed at a temp directory."""
    monkeypatch.setattr("shell.config.config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr("shell.config.cache_dir", lambda: tmp_path / "cache")
    app = ChillPillApp(qapp)
    # The real startup path: it writes the default config, shows the pill and
    # arms the timers.  Off Windows the AppBar, IPC and hotkey calls no-op.
    app.start()
    yield app
    app.quit()


def run(shell: ChillPillApp, *argv: str) -> dict:
    return shell._handle(parse_argv(list(argv)))


# -- construction -----------------------------------------------------------


def test_every_state_has_a_surface(shell: ChillPillApp) -> None:
    """A state with no page would morph the pill into an empty box."""
    for state in PillState:
        assert shell._pill.surface(state) is not None, f"no surface for {state}"


def test_starts_idle(shell: ChillPillApp) -> None:
    assert shell._machine.state is PillState.IDLE


# -- IPC round trips --------------------------------------------------------


def test_ping(shell: ChillPillApp) -> None:
    assert run(shell, "ping") == {"ok": True, "result": "pong"}


def test_toggle_opens_and_closes(shell: ChillPillApp) -> None:
    assert run(shell, "toggle", "dashboard")["result"] == {"open": "dashboard"}
    assert shell._machine.state is PillState.DASHBOARD
    assert run(shell, "toggle", "dashboard")["result"] == {"open": None}
    assert shell._machine.state is PillState.IDLE


def test_opening_one_panel_closes_another(shell: ChillPillApp) -> None:
    run(shell, "show", "controlCenter")
    run(shell, "show", "wallpapers")
    assert shell._machine.state is PillState.WALLPAPERS
    assert not shell._machine.is_open(PillState.CONTROL_CENTER)


def test_hide_star_closes_everything(shell: ChillPillApp) -> None:
    run(shell, "show", "clipboard")
    assert run(shell, "hide", "*")["result"] == {"open": None}
    assert shell._machine.state is PillState.IDLE


def test_show_star_is_rejected(shell: ChillPillApp) -> None:
    reply = run(shell, "show", "*")
    assert reply["ok"] is False


def test_status_reports_geometry_from_the_table(shell: ChillPillApp) -> None:
    run(shell, "show", "launcher")
    status = run(shell, "status")["result"]
    assert status["state"] == "launcher"
    assert status["geometry"] == {"width": 390.0, "height": 410.0, "radius": 30.0}


def test_status_includes_live_module_state(shell: ChillPillApp) -> None:
    modules = run(shell, "status")["result"]["modules"]
    # The pill bar holds these open for the whole session.
    assert {"clock", "battery", "volume", "network"} <= set(modules)
    assert modules["clock"]["text"]


def test_dnd_toggles(shell: ChillPillApp) -> None:
    assert run(shell, "dnd", "on")["result"] == {"dnd": True}
    assert run(shell, "dnd", "toggle")["result"] == {"dnd": False}


def test_timer_starts_and_cancels(shell: ChillPillApp) -> None:
    assert run(shell, "timer", "5")["result"] == {"timer": 5.0}
    assert shell._registry.get("timer").get("running") is True
    assert run(shell, "timer", "cancel")["result"] == {"timer": None}
    assert shell._registry.get("timer").get("running") is False


def test_timer_rejects_nonsense(shell: ChillPillApp) -> None:
    assert run(shell, "timer", "soon")["ok"] is False


def test_notify_lands_in_the_stack(shell: ChillPillApp) -> None:
    reply = run(shell, "notify", "Build", "finished in 42s")
    assert reply["ok"] is True
    stack = shell._registry.get("notifications").stack
    assert stack[0].title == "Build"
    assert stack[0].body == "finished in 42s"


def test_duplicate_notifications_are_suppressed(shell: ChillPillApp) -> None:
    run(shell, "notify", "Same", "text")
    run(shell, "notify", "Same", "text")
    assert len(shell._registry.get("notifications").stack) == 1


def test_an_unhandled_command_reports_rather_than_raises(shell: ChillPillApp) -> None:
    assert shell._handle(Command(cmd="wallpaper", args={"path": "/nope.png"}))["ok"] is False


# -- transient states -------------------------------------------------------


def test_notification_pops_the_pill(shell: ChillPillApp) -> None:
    run(shell, "notify", "Hello", "there")
    assert shell._machine.state is PillState.NOTIFICATION


def test_an_open_panel_swallows_the_popup(shell: ChillPillApp) -> None:
    """The control center already lists notifications; popping over it is noise."""
    run(shell, "show", "controlCenter")
    run(shell, "notify", "Hello", "there")
    assert shell._machine.state is PillState.CONTROL_CENTER


def test_dnd_stops_the_popup_but_not_the_stack(shell: ChillPillApp) -> None:
    run(shell, "dnd", "on")
    run(shell, "notify", "Quiet", "please")
    assert shell._machine.state is PillState.IDLE
    assert len(shell._registry.get("notifications").stack) == 1


def test_osd_stays_out_of_the_way_by_default(shell: ChillPillApp) -> None:
    """`osdEnabled` is false, so a volume change must not morph the pill."""
    shell._registry.get("volume").update(percent=42, muted=False)
    assert shell._machine.state is PillState.IDLE


# -- config -----------------------------------------------------------------


def test_reload_applies_a_changed_config(shell: ChillPillApp, qapp: QApplication) -> None:
    # Stop the file watcher first: otherwise it races the explicit reload, and
    # whichever wins leaves the other a no-op.  Both paths end in the same
    # place at runtime, but the test wants one deterministic trigger.
    shell._store.stop_watching()
    shell._store.path.write_text('{"clockFormat": "HH:mm:ss", "pillScale": 1.5}', encoding="utf-8")

    assert run(shell, "reload")["ok"] is True
    qapp.processEvents()

    assert shell._config.pill_scale == 1.5
    assert shell._config.clock_format == "HH:mm:ss"
    # The new scale must reach the morph context, not just the config object.
    assert shell._machine.context.pill_scale == 1.5
