"""Flow Launcher detection and delegation.

When Flow is installed, the launcher and clipboard surfaces are redundant --
Flow already does app search better, and the plugin in `integrations/` gives it
the clipboard.  So the shell hands those two jobs over and keeps its own
surfaces as the fallback.

Delegation is deliberately one-directional.  Flow is single-instance and its
second-instance handler only calls `ShowMainWindow()` with no arguments, so
there is no supported way to open it with a query pre-filled; all we can do is
show it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from shell.platform import IS_WINDOWS
from shell.platform.system import run_detached

logger = logging.getLogger(__name__)

EXECUTABLE = "Flow.Launcher.exe"


def install_root() -> Path | None:
    """Where Flow lives, or None if it is not installed.

    Flow installs per-user under LOCALAPPDATA in a versioned `app-x.y.z`
    directory, so the newest one wins.
    """
    if not IS_WINDOWS:
        return None
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    base = Path(local) / "FlowLauncher"
    if not base.is_dir():
        return None
    if (base / EXECUTABLE).is_file():
        return base
    versions = sorted((p for p in base.glob("app-*") if (p / EXECUTABLE).is_file()), reverse=True)
    return versions[0] if versions else None


def is_installed() -> bool:
    return install_root() is not None


def plugin_dir() -> Path | None:
    """Where this repo's plugin should be copied to."""
    appdata = os.environ.get("APPDATA")
    return Path(appdata) / "FlowLauncher" / "Plugins" / "ChillPill" if appdata else None


def plugin_installed() -> bool:
    directory = plugin_dir()
    return bool(directory and (directory / "plugin.json").is_file())


def show() -> bool:
    """Bring Flow's query box up."""
    root = install_root()
    if root is None:
        return False
    return run_detached(f'"{root / EXECUTABLE}"')


def resolve_backend(configured: str) -> str:
    """`"auto"` -> `"flow"` or `"builtin"`, based on what is actually installed."""
    if configured in ("flow", "builtin"):
        return configured
    return "flow" if is_installed() else "builtin"
