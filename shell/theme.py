"""Palette, fonts and glyphs, transcribed from ChillPill-Shell 0.3.1.

Values come from the original's `qml/Theme.qml` plus the literals its components
use inline.  They are facts about how the shell looks, not code: nothing here is
copied from the QML, and no ChillPill-Shell asset ships with this project.  See
docs/CREDITS.md.

Where the original had an obvious slip -- one duplicated entry and one swapped
pair in the battery ramp -- the comment says so and the corrected value is used.
A battery meter that shows the same icon at 30% and 40% is a bug, not a look.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    """Theme.qml, plus the inline literals from the components that need them."""

    # -- Theme.qml ---------------------------------------------------------
    bg: str = "#171717"  # the pill, in every state but the two below
    bg1: str = "#151515"  # media auto-popup, and control-center buttons when off
    fg: str = "#dadada"
    fg1: str = "#e7e7e7"
    fg2: str = "#dfdfdf"
    fg3d: str = "#a7a7a7"  # d == darker
    fg4d: str = "#c5c4c4"
    accent: str = "#979797"
    cover_art_glow: str = "#80aae6"

    # -- pill bar ----------------------------------------------------------
    battery_good: str = "#4bd25c"  # charging, or above 30%
    battery_warn: str = "#eecc47"  # 16-30%
    battery_critical: str = "#e22323"  # 15% and below
    volume_muted: str = "#fb2a2a"
    wifi_on: str = "#6791dc"
    wifi_off: str = "#9ea9bd"
    workspace_active_bg: str = "#4d5258"
    workspace_used_bg: str = "#393c41"
    workspace_active_fg: str = "#ffffff"
    workspace_idle_fg: str = "#dae0ea"

    # -- control center ----------------------------------------------------
    cc_media_bg: str = "#1a1a1a"  # also the pill's own fill when a player shows
    cc_media_border: str = "#202020"
    cc_button_bg_off: str = "#151515"
    cc_button_fg_off: str = "#a8a8a8"
    cc_button_border: str = "#202020"
    cc_button_bg_on: str = "#212529"  # wifi and timer when active
    cc_dnd_bg_on: str = "#262626"
    cc_wifi_icon_on: str = "#4282e9"
    cc_dnd_icon_on: str = "#fff9eb"
    cc_timer_icon_on: str = "#4490ee"
    cc_button_label: str = "#dedede"

    slider_track: str = "#3a3a3a"
    slider_fill: str = "#c9c9c9"
    slider_muted_icon: str = "#fd2222"

    media_title: str = "#e9e9e9"
    media_control: str = "#cdcdcd"
    media_control_hover: str = "#ffffff"
    media_progress_track: str = "#4d4d4d"
    media_time: str = "#676767"
    media_art_placeholder: str = "#555555"

    # -- notifications -----------------------------------------------------
    notif_card_bg: str = "#1c1c1c"
    notif_header_bg: str = "#2f2f2f"
    notif_header_fg: str = "#dddddd"
    notif_clear_bg: str = "#242424"
    notif_clear_bg_hover: str = "#1d1d1d"
    notif_time: str = "#858585"
    notif_body: str = "#9f9f9f"
    notif_popup_body: str = "#9b9b9b"
    notif_dismiss: str = "#404040"
    notif_dismiss_hover: str = "#bebebe"
    notif_separator: str = "#333333"

    # -- mini dashboard ----------------------------------------------------
    dash_bar_bg: str = "#212121"
    dash_subtitle: str = "#848484"
    dash_avatar_placeholder: str = "#454545"

    # -- OSD ---------------------------------------------------------------
    osd_track: str = "#333333"
    osd_timer_icon: str = "#5892f3"

    # -- surfaces the original builds ad hoc; kept on the same ramp ---------
    surface: str = "#1e1e1e"
    surface_hover: str = "#262626"
    surface_active: str = "#333333"
    border: str = "#202020"

    # -- backwards-friendly aliases used across the code -------------------
    @property
    def background(self) -> str:
        return self.bg

    @property
    def background_media_popup(self) -> str:
        return self.bg1

    @property
    def background_control_center(self) -> str:
        return self.cc_media_bg

    @property
    def text(self) -> str:
        return self.fg

    @property
    def text_muted(self) -> str:
        return self.accent

    @property
    def text_dim(self) -> str:
        return self.media_time

    def rgba(self, key: str, alpha: float) -> str:
        """`palette.rgba("fg", 0.5)` -> "rgba(218, 218, 218, 0.500)"."""
        value = getattr(self, key)
        r, g, b = (int(value[i : i + 2], 16) for i in (1, 3, 5))
        return f"rgba({r}, {g}, {b}, {alpha:.3f})"


PALETTE = Palette()


def battery_color(percent: int, charging: bool, palette: Palette = PALETTE) -> str:
    """Charging or above 30% is green, 15% and below is red, between is yellow."""
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
    """Sizes are in pixels, matching the original's `font.pixelSize`.

    The pill bar scales with `pillScale`; the panels do not, exactly as in the
    original -- their boxes are fixed sizes, so scaling their text would
    overflow them.
    """

    text_family: str = "Monocraft"
    nerd_family: str = "JetBrainsMono Nerd Font Propo"

    # pill bar (multiplied by pillScale at use)
    bar_text: int = 10
    bar_icon: int = 10
    bar_workspace: int = 9

    # control center
    cc_button_label: int = 12
    cc_button_icon: int = 14
    cc_slider_icon: int = 13
    cc_slider_value: int = 10
    media_title: int = 12
    media_artist: int = 10
    media_control: int = 23
    media_time: int = 10
    notif_header: int = 9
    notif_clear: int = 8
    notif_title: int = 11
    notif_body: int = 9
    notif_time: int = 8

    # popups
    popup_icon: int = 15
    popup_title: int = 10
    popup_body: int = 9

    # OSD
    osd_icon: int = 15
    osd_value: int = 10

    # dashboard
    dash_name: int = 13
    dash_subtitle: int = 9
    dash_value: int = 8

    # list surfaces (launcher, clipboard, wallpapers)
    panel_title: int = 12
    panel_body: int = 10
    panel_small: int = 9


FONTS = Fonts()


def padding_scale(pill_scale: float) -> float:
    """The original scales padding sub-linearly so a big pill stays sane."""
    return 1 + (pill_scale - 1) * 0.6


# --------------------------------------------------------------------------
# Glyphs
# --------------------------------------------------------------------------
#
# Codepoints taken from the original's components.  Written as `chr(0x...)`
# rather than string escapes: these live in the private use areas where a
# literal is invisible in a diff and easy to corrupt, and the hex is what you
# check against https://www.nerdfonts.com/cheat-sheet when a box appears.


def _cp(codepoint: int) -> str:
    return chr(codepoint)


@dataclass(frozen=True)
class Glyphs:
    #: Ten steps, 0-9% through 90-100%.
    #:
    #: The original's array is
    #:   [f0083, f007a, f007d, f007c, f007d, f007e, f007f, f0082, f0081, f0079]
    #: which repeats battery_40 at indices 2 and 4 and swaps 70/80 at 7 and 8.
    #: Corrected here so the meter climbs monotonically -- showing the same icon
    #: at 30% and 40% is a slip, not a design choice.
    battery_ramp: tuple[str, ...] = (
        _cp(0xF0083),  # nf-md-battery_alert    0-9%
        _cp(0xF007A),  # nf-md-battery_10
        _cp(0xF007B),  # nf-md-battery_20
        _cp(0xF007C),  # nf-md-battery_30
        _cp(0xF007D),  # nf-md-battery_40
        _cp(0xF007E),  # nf-md-battery_50
        _cp(0xF007F),  # nf-md-battery_60
        _cp(0xF0080),  # nf-md-battery_70
        _cp(0xF0081),  # nf-md-battery_80
        _cp(0xF0079),  # nf-md-battery       90-100%
    )
    #: Appended to the ramp glyph, not substituted for it.
    battery_charging_overlay: str = _cp(0xF140B)  # nf-md-flash
    power_plug: str = _cp(0xF06A5)  # shown instead of the ramp with no battery

    volume_muted: str = _cp(0xF0581)  # nf-md-volume_off
    volume_low: str = _cp(0xF0580)  # nf-md-volume_medium, below 40%
    volume_high: str = _cp(0xF057E)  # nf-md-volume_high
    headphones: str = _cp(0xEE58)
    headphones_muted: str = _cp(0xF025)  # nf-fa-volume_off

    #: Signal tiers 1-4; the original computes 0xf091f + (tier + 1) * 3.
    wifi_tiers: tuple[str, ...] = (
        _cp(0xF0925),
        _cp(0xF0928),
        _cp(0xF092B),
        _cp(0xF092E),
    )
    wifi_none: str = _cp(0xF092D)
    wifi_panel: str = _cp(0xF1EB)  # nf-fa-wifi, on the control-center button

    brightness_ramp: tuple[str, ...] = (
        _cp(0xF00DD),  # below 25%
        _cp(0xF00DE),  # 25-49%
        _cp(0xF00DF),  # 50-74%
        _cp(0xF00E0),  # 75%+
    )

    bell: str = _cp(0xF0F3)
    dnd: str = _cp(0xF1F6)
    timer_idle: str = _cp(0xF13AB)  # nf-md-timer_outline
    timer_running: str = _cp(0xF1ADE)  # nf-md-timer_pause_outline
    timer_paused: str = _cp(0xF1AE0)  # nf-md-timer_play_outline
    timer_done: str = _cp(0xF1AD1)  # nf-md-timer_alert_outline

    play: str = _cp(0xF040A)  # nf-md-play
    pause: str = _cp(0xF03E4)  # nf-md-pause
    #: Plain Unicode in the original, not Nerd Font -- they render anywhere.
    previous: str = "\u23ee"
    next: str = "\u23ed"
    music: str = _cp(0xF001)  # nf-fa-music, the album-art placeholder

    power: str = _cp(0xF0425)
    lock: str = _cp(0xF023)  # nf-fa-lock
    sleep: str = _cp(0xF0904)  # nf-md-weather_night
    restart: str = _cp(0xF0453)  # nf-md-restart
    close: str = _cp(0xF00D)  # nf-fa-close

    ip: str = _cp(0xF099D)  # nf-md-lan
    vpn: str = _cp(0xF0A5F)  # nf-md-shield_lock
    download: str = _cp(0xF01DA)
    upload: str = _cp(0xF0552)
    calendar: str = _cp(0xF00ED)
    clipboard: str = _cp(0xF00C7)
    image: str = _cp(0xF02E9)
    search: str = _cp(0xF0349)  # nf-md-magnify
    folder: str = _cp(0xF0256)  # nf-md-folder_open

    # Weather comes from the Weather Icons range, not Material Design.
    weather_clear: str = _cp(0xE30D)
    weather_cloudy: str = _cp(0xE312)
    weather_fog: str = _cp(0xE313)
    weather_rain: str = _cp(0xE318)
    weather_snow: str = _cp(0xE31A)
    weather_storm: str = _cp(0xE31D)
    weather_wind: str = _cp(0xE34B)
    weather_sunrise: str = _cp(0xE34C)
    weather_sunset: str = _cp(0xE34D)
    weather_thermometer: str = _cp(0xE34E)
    weather_humidity: str = _cp(0xE373)


GLYPHS = Glyphs()

#: Weather glyph colours, from the original's WeatherModule.
WEATHER_COLORS: dict[str, str] = {
    "clear": "#f4c542",
    "cloudy": "#9aa0a6",
    "fog": "#8a8a8a",
    "rain": "#4a9de8",
    "snow": "#d8e8f4",
    "storm": "#e8b84a",
}


# --------------------------------------------------------------------------
# Glyph selection
# --------------------------------------------------------------------------


def battery_glyph(percent: int, charging: bool, present: bool = True, glyphs: Glyphs = GLYPHS) -> str:
    """Ramp glyph, with the charging bolt appended rather than substituted."""
    if not present:
        return glyphs.power_plug
    base = glyphs.battery_ramp[max(0, min(9, percent // 10))]
    return base + glyphs.battery_charging_overlay if charging else base


def volume_glyph(percent: int, muted: bool, headphones: bool = False, glyphs: Glyphs = GLYPHS) -> str:
    if muted:
        return glyphs.headphones_muted if headphones else glyphs.volume_muted
    if headphones:
        return glyphs.headphones
    if percent == 0:
        return glyphs.volume_muted
    if percent < 40:
        return glyphs.volume_low
    return glyphs.volume_high


def wifi_glyph(signal: int, connected: bool, enabled: bool = True, glyphs: Glyphs = GLYPHS) -> str:
    """`signal` is 0-100; the original buckets it into four tiers."""
    if not enabled or not connected:
        return glyphs.wifi_none
    if signal >= 75:
        tier = 4
    elif signal >= 50:
        tier = 3
    elif signal >= 25:
        tier = 2
    else:
        tier = 1
    return glyphs.wifi_tiers[tier - 1]


def brightness_glyph(percent: int, glyphs: Glyphs = GLYPHS) -> str:
    if percent >= 75:
        return glyphs.brightness_ramp[3]
    if percent >= 50:
        return glyphs.brightness_ramp[2]
    if percent >= 25:
        return glyphs.brightness_ramp[1]
    return glyphs.brightness_ramp[0]


def weather_glyph(label: str, glyphs: Glyphs = GLYPHS) -> tuple[str, str]:
    """`label` -> (glyph, colour).  Anything unknown reads as cloudy grey."""
    mapping = {
        "clear": (glyphs.weather_clear, "clear"),
        "cloudy": (glyphs.weather_cloudy, "cloudy"),
        "fog": (glyphs.weather_fog, "fog"),
        "rain": (glyphs.weather_rain, "rain"),
        "showers": (glyphs.weather_rain, "rain"),
        "snow": (glyphs.weather_snow, "snow"),
        "storm": (glyphs.weather_storm, "storm"),
    }
    glyph, key = mapping.get(label, (glyphs.weather_cloudy, "cloudy"))
    return glyph, WEATHER_COLORS[key]
