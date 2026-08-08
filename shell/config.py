"""Configuration: one flat pydantic model, loaded from a JSONC file.

Deliberately one model and one file.  yasb needs a per-widget schema system
because it has fifty widgets; ChillPill has one pill and twenty-odd knobs, so a
schema system would be more code than the thing it validates.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

APP_NAME = "chillpill-win"


def config_dir() -> Path:
    """%APPDATA%\\chillpill-win on Windows, XDG config dir elsewhere."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.jsonc"


def cache_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".cache"
    return base / APP_NAME


def _default_display_picture() -> str:
    return str(Path.home() / ".pfp.png")


def _default_wallpapers_dir() -> str:
    return str(Path.home() / "Pictures" / "wallpapers")


class Config(BaseModel):
    """Every key from spec §1.4, ported to Windows, plus three additions.

    Field names are snake_case in Python and camelCase on disk, so the config
    file stays byte-compatible with the original shell's keys.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid", validate_assignment=True)

    # -- appearance ---------------------------------------------------------
    display_picture: str = Field(default_factory=_default_display_picture, alias="displayPicture")
    clock_format: str = Field(default="hh:mm", alias="clockFormat")
    pill_top_margin: int = Field(default=9, alias="pillTopMargin")
    pill_bottom_margin: int = Field(default=26, alias="pillBottomMargin")
    pill_scale: float = Field(default=1.0, gt=0.1, le=4.0, alias="pillScale")
    text_font_family: str = Field(default="Monocraft", alias="textFontFamily")
    nerd_font_family: str = Field(default="JetBrainsMono Nerd Font Propo", alias="nerdFontFamily")

    # -- behaviour ----------------------------------------------------------
    timer_presets: list[int] = Field(default=[1, 5, 10, 15, 30], alias="timerPresets")
    media_popup_duration: int = Field(default=2000, ge=0, alias="mediaPopupDuration")
    max_workspaces: int = Field(default=5, ge=1, le=20, alias="maxWorkspaces")
    osd_duration: int = Field(default=800, ge=0, alias="osdDuration")

    # -- notifications ------------------------------------------------------
    notification_display_time: int = Field(default=3000, ge=0, alias="notificationDisplayTime")
    max_notifications_in_stack: int = Field(default=20, ge=1, alias="maxNotificationsInStack")
    avoid_duplicate_notifications: bool = Field(default=True, alias="avoidDuplicateNotifications")

    # -- system -------------------------------------------------------------
    bandwidth_refresh_interval: int = Field(default=300_000, ge=1000, alias="bandwidthRefreshInterval")
    screen_lock_app_command: str = Field(
        default="rundll32.exe user32.dll,LockWorkStation", alias="screenLockAppCommand"
    )
    default_terminal: str = Field(default="wt.exe", alias="defaultTerminal")

    # -- weather ------------------------------------------------------------
    weather_location: str = Field(default="Delhi", alias="weatherLocation")
    weather_units: Literal["metric", "imperial"] = Field(default="metric", alias="weatherUnits")
    weather_refresh_interval: int = Field(default=3_600_000, ge=60_000, alias="weatherRefreshInterval")

    # -- wallpapers ---------------------------------------------------------
    wallpapers_dir: str = Field(default_factory=_default_wallpapers_dir, alias="wallpapersDir")
    ws_close_on_wallpaper_set: bool = Field(default=True, alias="wsCloseOnWallpaperSet")

    # -- Windows-only additions --------------------------------------------
    #: Windows has no supported way to suppress its own volume/brightness OSD,
    #: so ours ships off to avoid two overlays fighting (spec §8 R1).
    osd_enabled: bool = Field(default=False, alias="osdEnabled")
    #: "auto" delegates the launcher and clipboard history to Flow Launcher when
    #: it is installed, and falls back to the built-in surfaces when it is not.
    launcher_backend: Literal["auto", "builtin", "flow"] = Field(default="auto", alias="launcherBackend")
    #: "vd" = Windows virtual desktops via pyvda.  "none" hides the indicator.
    workspace_backend: Literal["vd", "none"] = Field(default="vd", alias="workspaceBackend")

    # -- helpers ------------------------------------------------------------

    @property
    def terminal_fallback(self) -> str:
        return "powershell.exe"

    def dump_jsonc(self) -> str:
        """Serialise with the on-disk (camelCase) key names."""
        return json.dumps(self.model_dump(by_alias=True), indent=2)


# --------------------------------------------------------------------------
# JSONC parsing
# --------------------------------------------------------------------------

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(^|[^:])//[^\n]*")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas.

    String literals are protected first so a `//` inside a path value (or a
    `/*` inside a URL) survives.
    """
    literals: list[str] = []

    def stash(match: re.Match[str]) -> str:
        literals.append(match.group(0))
        return f"\x00{len(literals) - 1}\x00"

    text = re.sub(r'"(?:\\.|[^"\\])*"', stash, text)
    text = _BLOCK_COMMENT.sub("", text)
    text = _LINE_COMMENT.sub(r"\1", text)
    text = _TRAILING_COMMA.sub(r"\1", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: literals[int(m.group(1))], text)


def load_config(path: Path | None = None) -> Config:
    """Read the config file, falling back to defaults on any problem.

    A broken config must never stop the shell from starting -- the user would
    have no UI left to fix it with.
    """
    path = path or config_path()
    if not path.is_file():
        logger.info("no config at %s, using defaults", path)
        return Config()
    try:
        raw: Any = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("config %s is not readable JSONC (%s), using defaults", path, exc)
        return Config()
    if not isinstance(raw, dict):
        logger.error("config %s must contain a JSON object, using defaults", path)
        return Config()
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        logger.error("config %s rejected:\n%s\nusing defaults", path, exc)
        return Config()


def write_default_config(path: Path | None = None) -> Path:
    """Create a commented starter config if none exists.  Returns the path."""
    path = path or config_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    body = Config().dump_jsonc()
    path.write_text(
        "// ChillPill-Win configuration.\n"
        "// Comments and trailing commas are allowed.  Delete a key to use its default.\n"
        "// Saving this file reloads the shell live -- no restart needed.\n" + body + "\n",
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------
# Live reload
# --------------------------------------------------------------------------


class ConfigStore(QObject):
    """Holds the active config and reloads it when the file changes on disk."""

    changed = pyqtSignal(object)  # Config

    def __init__(self, path: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = path or config_path()
        self._config = load_config(self._path)
        self._observer: Any = None

    @property
    def config(self) -> Config:
        return self._config

    @property
    def path(self) -> Path:
        return self._path

    def reload(self) -> None:
        new_config = load_config(self._path)
        if new_config == self._config:
            return
        self._config = new_config
        logger.info("config reloaded from %s", self._path)
        self.changed.emit(new_config)

    def start_watching(self) -> None:
        """Watch the config's directory.  Silently a no-op without watchdog."""
        if self._observer is not None:
            return
        try:
            from watchdog.events import FileSystemEvent, FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:  # pragma: no cover - optional dependency
            logger.info("watchdog not installed; config live-reload disabled")
            return

        store = self

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event: FileSystemEvent) -> None:
                paths = [event.src_path, getattr(event, "dest_path", "")]
                if any(str(p).endswith(store._path.name) for p in paths if p):
                    # Editors write via a temp file + rename; reload on any of it.
                    store.reload()

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._observer = Observer()
        self._observer.schedule(_Handler(), str(self._path.parent), recursive=False)
        self._observer.daemon = True
        self._observer.start()

    def stop_watching(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=2)
        self._observer = None
