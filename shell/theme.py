"""Palette, fonts and glyphs.

Colour values are transcribed from the ChillPill-Shell design spec (§1.3).  The
spec fixes the ones that are load-bearing for the look -- the three pill
backgrounds, the two text greys, and the three battery colours.  The remaining
entries (surfaces, borders, slider chrome) are derived from those so the whole
sheet stays on one ramp; they are marked below.

No ChillPill-Shell code or assets are used here.  Colour values and numeric
behaviour are factual data, not copyrightable expression -- see docs/CREDITS.md.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    # -- from the spec ------------------------------------------------------
    background: str = "#171717"  # every state except the two below
    background_media_popup: str = "#151515"  # media auto-popup
    background_control_center: str = "#1a1a1a"  # control center *with* media
    text: str = "#dadada"
    text_muted: str = "#979797"
    battery_good: str = "#4bd25c"  # >30% or charging
    battery_warn: str = "#eecc47"  # 16-30%
    battery_critical: str = "#e22323"  # <=15%

    # -- derived (not in the spec; kept on the same ramp) --------------------
    surface: str = "#202020"  # cards and rows inside a panel
    surface_hover: str = "#262626"
    surface_active: str = "#2e2e2e"
    border: str = "#2a2a2a"
    text_dim: str = "#6b6b6b"  # timestamps, secondary metadata
    accent: str = "#eecc47"
    slider_track: str = "#2e2e2e"
    slider_fill: str = "#dadada"
    shadow: str = "#00000066"

    def rgba(self, key: str, alpha: float) -> str:
        """`palette.rgba("text", 0.5)` -> "rgba(218, 218, 218, 0.500)"."""
        value = getattr(self, key)
        r, g, b = (int(value[i : i + 2], 16) for i in (1, 3, 5))
        return f"rgba({r}, {g}, {b}, {alpha:.3f})"


PALETTE = Palette()


def battery_color(percent: int, charging: bool, palette: Palette = PALETTE) -> str:
    """Spec §1.3: >30% or charging -> green, <=15% -> red, otherwise yellow."""
    if charging or percent > 30:
        return palette.battery_good
    if percent <= 15:
        return palette.battery_critical
    return palette.battery_warn


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Fonts:
    text_family: str = "Monocraft"
    nerd_family: str = "JetBrainsMono Nerd Font Propo"
    pill_size: int = 11
    panel_size: int = 11
    title_size: int = 13
    small_size: int = 9
    icon_size: int = 13


FONTS = Fonts()


# --------------------------------------------------------------------------
# Glyphs
# --------------------------------------------------------------------------
#
# Nerd Fonts codepoints (Material Design set).  Names are kept next to the
# characters so a mismatch against a locally installed font is a one-line fix.
# If a glyph renders as a box, check the name against
# https://www.nerdfonts.com/cheat-sheet rather than guessing a new codepoint.


@dataclass(frozen=True)
class Glyphs:
    # battery ramp: index 0 = 0-9%, index 9 = 90-100%
    battery_ramp: tuple[str, ...] = (
        "\U000f008e",  # nf-md-battery_outline
        "\U000f007a",  # nf-md-battery_10
        "\U000f007b",  # nf-md-battery_20
        "\U000f007c",  # nf-md-battery_30
        "\U000f007d",  # nf-md-battery_40
        "\U000f007e",  # nf-md-battery_50
        "\U000f007f",  # nf-md-battery_60
        "\U000f0080",  # nf-md-battery_70
        "\U000f0081",  # nf-md-battery_80
        "\U000f0079",  # nf-md-battery (full)
    )
    battery_charging: str = "\U000f0084"  # nf-md-battery_charging
    battery_alert: str = "\U000f0083"  # nf-md-battery_alert

    volume_muted: str = "\U000f075f"  # nf-md-volume_mute
    volume_low: str = "\U000f0580"  # nf-md-volume_low
    volume_medium: str = "\U000f0580"  # nf-md-volume_medium
    volume_high: str = "\U000f057e"  # nf-md-volume_high

    brightness: str = "\U000f00e0"  # nf-md-brightness_5
    brightness_low: str = "\U000f00da"  # nf-md-brightness_2

    wifi: str = "\U000f05a9"  # nf-md-wifi
    wifi_off: str = "\U000f05aa"  # nf-md-wifi_off
    ethernet: str = "\U000f0200"  # nf-md-ethernet
    bluetooth: str = "\U000f00af"  # nf-md-bluetooth

    clock: str = "\U000f0954"  # nf-md-clock_outline
    calendar: str = "\U000f00ed"  # nf-md-calendar
    timer: str = "\U000f13ab"  # nf-md-timer_outline
    bell: str = "\U000f009a"  # nf-md-bell
    bell_off: str = "\U000f009b"  # nf-md-bell_off

    play: str = "\U000f040a"  # nf-md-play
    pause: str = "\U000f03e4"  # nf-md-pause
    next_track: str = "\U000f04ad"  # nf-md-skip_next
    prev_track: str = "\U000f04ae"  # nf-md-skip_previous

    power: str = "\U000f0425"  # nf-md-power
    lock: str = "\U000f033e"  # nf-md-lock
    restart: str = "\U000f0454"  # nf-md-restart
    sleep: str = "\U000f04b2"  # nf-md-sleep
    logout: str = "\U000f0343"  # nf-md-logout

    upload: str = "\U000f0552"  # nf-md-upload
    download: str = "\U000f01da"  # nf-md-download
    clipboard: str = "\U000f00c7"  # nf-md-clipboard_outline
    image: str = "\U000f02e9"  # nf-md-image
    search: str = "\U000f0349"  # nf-md-magnify
    memory: str = "\U000f035b"  # nf-md-memory
    thermometer: str = "\U000f050f"  # nf-md-thermometer

    weather_clear: str = "\U000f0599"  # nf-md-weather_sunny
    weather_cloudy: str = "\U000f0590"  # nf-md-weather_cloudy
    weather_rain: str = "\U000f0597"  # nf-md-weather_rainy
    weather_snow: str = "\U000f0598"  # nf-md-weather_snowy
    weather_fog: str = "\U000f0591"  # nf-md-weather_fog
    weather_storm: str = "\U000f0593"  # nf-md-weather_lightning

    workspace_active: str = "●"  # filled circle
    workspace_inactive: str = "○"  # hollow circle


GLYPHS = Glyphs()


def battery_glyph(percent: int, charging: bool, glyphs: Glyphs = GLYPHS) -> str:
    """Ten-step ramp; charging replaces the glyph with the charging overlay."""
    if charging:
        return glyphs.battery_charging
    index = max(0, min(9, percent // 10))
    return glyphs.battery_ramp[index]


def volume_glyph(percent: int, muted: bool, glyphs: Glyphs = GLYPHS) -> str:
    if muted or percent == 0:
        return glyphs.volume_muted
    if percent < 34:
        return glyphs.volume_low
    if percent < 67:
        return glyphs.volume_medium
    return glyphs.volume_high
