"""The palette and glyph tables, pinned to ChillPill-Shell 0.3.1.

These are transcription tests, not behaviour tests.  Their job is to make a
drift in the look show up as a failing assertion rather than as a screenshot
somebody notices three months later.
"""

from __future__ import annotations

import pytest

from shell.theme import (
    FONTS,
    GLYPHS,
    PALETTE,
    battery_color,
    battery_glyph,
    brightness_glyph,
    padding_scale,
    volume_glyph,
    weather_glyph,
    wifi_glyph,
)

# -- Theme.qml --------------------------------------------------------------


def test_theme_qml_palette() -> None:
    assert PALETTE.bg == "#171717"
    assert PALETTE.bg1 == "#151515"
    assert PALETTE.fg == "#dadada"
    assert PALETTE.fg1 == "#e7e7e7"
    assert PALETTE.fg2 == "#dfdfdf"
    assert PALETTE.fg3d == "#a7a7a7"
    assert PALETTE.fg4d == "#c5c4c4"
    assert PALETTE.accent == "#979797"
    assert PALETTE.cover_art_glow == "#80aae6"


def test_accent_is_grey_not_a_highlight_colour() -> None:
    """The original's "accent" is a muted grey; nothing in the shell is gold."""
    assert PALETTE.accent == "#979797"
    assert PALETTE.text_muted == PALETTE.accent


def test_control_center_measurements_palette() -> None:
    assert PALETTE.cc_media_bg == "#1a1a1a"
    assert PALETTE.cc_button_bg_off == "#151515"
    assert PALETTE.cc_button_fg_off == "#a8a8a8"
    assert PALETTE.cc_button_bg_on == "#212529"
    assert PALETTE.slider_track == "#3a3a3a"
    assert PALETTE.slider_fill == "#c9c9c9"


def test_rgba_helper() -> None:
    assert PALETTE.rgba("fg", 0.5) == "rgba(218, 218, 218, 0.500)"


# -- battery ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("percent", "charging", "expected"),
    [
        (100, False, PALETTE.battery_good),
        (31, False, PALETTE.battery_good),
        (30, False, PALETTE.battery_warn),
        (16, False, PALETTE.battery_warn),
        (15, False, PALETTE.battery_critical),
        (0, False, PALETTE.battery_critical),
        (5, True, PALETTE.battery_good),  # charging always reads green
    ],
)
def test_battery_colour_thresholds(percent: int, charging: bool, expected: str) -> None:
    assert battery_color(percent, charging) == expected


def test_battery_ramp_is_monotonic() -> None:
    """The original repeats one step and swaps another; ours must not.

    Ten distinct glyphs, so 30% and 40% cannot look identical.
    """
    assert len(GLYPHS.battery_ramp) == 10
    assert len(set(GLYPHS.battery_ramp)) == 10


def test_battery_ramp_endpoints() -> None:
    assert ord(GLYPHS.battery_ramp[0]) == 0xF0083  # battery_alert
    assert ord(GLYPHS.battery_ramp[9]) == 0xF0079  # battery (full)


def test_charging_appends_rather_than_replaces() -> None:
    """The original overlays the bolt on the level glyph; it does not swap it."""
    plain = battery_glyph(45, charging=False)
    charging = battery_glyph(45, charging=True)
    assert charging == plain + GLYPHS.battery_charging_overlay
    assert len(charging) == 2


def test_no_battery_shows_a_plug() -> None:
    assert battery_glyph(0, charging=False, present=False) == GLYPHS.power_plug


# -- volume, wifi, brightness ----------------------------------------------


@pytest.mark.parametrize(
    ("percent", "muted", "expected"),
    [
        (0, False, GLYPHS.volume_muted),
        (39, False, GLYPHS.volume_low),
        (40, False, GLYPHS.volume_high),
        (80, True, GLYPHS.volume_muted),
    ],
)
def test_volume_glyph_thresholds(percent: int, muted: bool, expected: str) -> None:
    assert volume_glyph(percent, muted) == expected


def test_headphones_get_their_own_glyph() -> None:
    assert volume_glyph(50, muted=False, headphones=True) == GLYPHS.headphones
    assert volume_glyph(50, muted=True, headphones=True) == GLYPHS.headphones_muted


@pytest.mark.parametrize(
    ("signal", "codepoint"),
    [(10, 0xF0925), (30, 0xF0928), (60, 0xF092B), (90, 0xF092E)],
)
def test_wifi_tiers(signal: int, codepoint: int) -> None:
    assert ord(wifi_glyph(signal, connected=True)) == codepoint


def test_wifi_disconnected_and_disabled_share_a_glyph() -> None:
    assert wifi_glyph(90, connected=False) == GLYPHS.wifi_none
    assert wifi_glyph(90, connected=True, enabled=False) == GLYPHS.wifi_none


@pytest.mark.parametrize(("percent", "index"), [(0, 0), (24, 0), (25, 1), (50, 2), (75, 3), (100, 3)])
def test_brightness_ramp(percent: int, index: int) -> None:
    assert brightness_glyph(percent) == GLYPHS.brightness_ramp[index]


# -- weather ----------------------------------------------------------------


def test_weather_glyphs_carry_their_colours() -> None:
    assert weather_glyph("clear") == (GLYPHS.weather_clear, "#f4c542")
    assert weather_glyph("rain") == (GLYPHS.weather_rain, "#4a9de8")
    assert weather_glyph("showers") == (GLYPHS.weather_rain, "#4a9de8")


def test_unknown_weather_falls_back_to_cloudy() -> None:
    assert weather_glyph("meteors") == (GLYPHS.weather_cloudy, "#9aa0a6")


# -- fonts and scaling ------------------------------------------------------


def test_font_families() -> None:
    assert FONTS.text_family == "Monocraft"
    assert FONTS.nerd_family == "JetBrainsMono Nerd Font Propo"


def test_padding_scales_sub_linearly() -> None:
    """A 2x pill should not get 2x padding, or the bar becomes mostly air."""
    assert padding_scale(1.0) == 1.0
    assert padding_scale(2.0) == pytest.approx(1.6)
    assert padding_scale(1.5) == pytest.approx(1.3)


def test_every_glyph_is_a_single_codepoint() -> None:
    """A two-character "glyph" is a typo that renders as two boxes."""
    for name in dir(GLYPHS):
        if name.startswith("_"):
            continue
        value = getattr(GLYPHS, name)
        if isinstance(value, str):
            assert len(value) == 1, f"{name} is {len(value)} characters"
        elif isinstance(value, tuple):
            for index, glyph in enumerate(value):
                assert len(glyph) == 1, f"{name}[{index}] is {len(glyph)} characters"
