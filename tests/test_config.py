"""Config loading: camelCase on disk, snake_case in Python, never fatal."""

from __future__ import annotations

from pathlib import Path

from shell.config import Config, ConfigStore, load_config, strip_jsonc, write_default_config

# -- JSONC ------------------------------------------------------------------


def test_strips_line_and_block_comments() -> None:
    text = """
    {
      // a line comment
      "clockFormat": "HH:mm", /* and a block one */
      "pillScale": 1.25,
    }
    """
    assert "comment" not in strip_jsonc(text)
    import json

    assert json.loads(strip_jsonc(text))["pillScale"] == 1.25


def test_keeps_slashes_inside_strings() -> None:
    """A Windows path is full of backslashes, and a URL is full of forward ones."""
    text = '{"wallpapersDir": "C://Users//me//Pictures", "displayPicture": "https://example.com/a.png"}'
    stripped = strip_jsonc(text)
    assert "C://Users//me//Pictures" in stripped
    assert "https://example.com/a.png" in stripped


def test_strips_trailing_commas() -> None:
    import json

    assert json.loads(strip_jsonc('{"a": 1, "b": [1, 2,],}')) == {"a": 1, "b": [1, 2]}


# -- defaults ---------------------------------------------------------------


def test_defaults_match_the_spec() -> None:
    config = Config()
    assert config.clock_format == "hh:mm"
    assert config.pill_top_margin == 9
    assert config.pill_bottom_margin == 26
    assert config.pill_scale == 1.0
    assert config.timer_presets == [1, 5, 10, 15, 30]
    assert config.media_popup_duration == 2000
    assert config.max_workspaces == 5
    assert config.notification_display_time == 3000
    assert config.max_notifications_in_stack == 20
    assert config.avoid_duplicate_notifications is True
    assert config.bandwidth_refresh_interval == 300_000
    assert config.osd_duration == 800
    assert config.weather_location == "Delhi"
    assert config.weather_units == "metric"
    assert config.weather_refresh_interval == 3_600_000
    assert config.ws_close_on_wallpaper_set is True


def test_windows_ports_of_the_linux_defaults() -> None:
    config = Config()
    assert "LockWorkStation" in config.screen_lock_app_command
    assert config.default_terminal == "wt.exe"
    assert config.terminal_fallback == "powershell.exe"


def test_osd_ships_disabled() -> None:
    """Windows has no way to suppress its own OSD, so ours is opt-in."""
    assert Config().osd_enabled is False


# -- files ------------------------------------------------------------------


def test_reads_camel_case_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.jsonc"
    path.write_text('{"clockFormat": "HH:mm:ss", "pillScale": 1.5}', encoding="utf-8")
    config = load_config(path)
    assert config.clock_format == "HH:mm:ss"
    assert config.pill_scale == 1.5


def test_round_trips_through_disk(tmp_path: Path) -> None:
    path = tmp_path / "config.jsonc"
    write_default_config(path)
    assert load_config(path) == Config()


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_config(tmp_path / "absent.jsonc") == Config()


def test_broken_json_gives_defaults(tmp_path: Path) -> None:
    """A typo in the config must not leave the user with no shell to fix it in."""
    path = tmp_path / "config.jsonc"
    path.write_text('{"clockFormat": ', encoding="utf-8")
    assert load_config(path) == Config()


def test_invalid_value_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.jsonc"
    path.write_text('{"pillScale": 99}', encoding="utf-8")  # above the cap
    assert load_config(path) == Config()


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    """Typos should be loud, not silently ignored."""
    path = tmp_path / "config.jsonc"
    path.write_text('{"clockFormat": "HH:mm", "clokFormat": "oops"}', encoding="utf-8")
    assert load_config(path) == Config()


def test_write_default_does_not_clobber(tmp_path: Path) -> None:
    path = tmp_path / "config.jsonc"
    path.write_text('{"pillScale": 2.0}', encoding="utf-8")
    write_default_config(path)
    assert load_config(path).pill_scale == 2.0


# -- the store --------------------------------------------------------------


def test_store_emits_only_on_a_real_change(tmp_path: Path) -> None:
    path = tmp_path / "config.jsonc"
    write_default_config(path)
    store = ConfigStore(path)
    seen: list[Config] = []
    store.changed.connect(seen.append)

    store.reload()
    assert seen == []

    path.write_text('{"pillScale": 1.25}', encoding="utf-8")
    store.reload()
    assert len(seen) == 1
    assert store.config.pill_scale == 1.25
