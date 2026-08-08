"""`python -m shell.doctor` -- check whether this machine can run the shell.

Written for the first install on a new machine, where the useful question is
not "did it crash" but "which of the eight optional Windows backends is
missing". Every check is read-only and none of them can fail the process: a
missing backend degrades one feature, and the report says which.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from dataclasses import dataclass

from shell.platform import IS_WINDOWS, windows_build

OK = "ok"
MISSING = "missing"
DEGRADED = "degraded"


@dataclass
class Check:
    name: str
    status: str
    detail: str

    @property
    def mark(self) -> str:
        return {OK: "+", DEGRADED: "~", MISSING: "-"}[self.status]


def _module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _font_installed(family: str) -> bool:
    """Whether Qt can see `family`.

    `QFontDatabase` aborts the process -- not raises -- if no QGuiApplication
    exists, so the caller must have built one first.
    """
    try:
        from PyQt6.QtGui import QFontDatabase

        return family in QFontDatabase.families()
    except Exception:
        return False


def _ensure_qt() -> bool:
    """Build a QGuiApplication if there isn't one, so the font check is safe."""
    try:
        from PyQt6.QtGui import QGuiApplication

        if QGuiApplication.instance() is None:
            _ensure_qt.app = QGuiApplication(sys.argv[:1])  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def run_checks() -> list[Check]:
    checks: list[Check] = []

    version = ".".join(str(part) for part in sys.version_info[:3])
    checks.append(
        Check(
            "Python 3.12+",
            OK if sys.version_info >= (3, 12) else MISSING,
            f"running {version}" + ("" if sys.version_info >= (3, 12) else "; vendored code needs 3.12"),
        )
    )

    build = windows_build()
    if not IS_WINDOWS:
        checks.append(Check("Windows", MISSING, f"this is {sys.platform}; the shell will start but do nothing"))
    elif build >= 22000:
        checks.append(Check("Windows", OK, f"build {build} (Windows 11: Mica and rounded corners available)"))
    elif build >= 17763:
        checks.append(Check("Windows", DEGRADED, f"build {build} (Windows 10: acrylic only, no Mica)"))
    else:
        checks.append(Check("Windows", MISSING, f"build {build} is older than 1809"))

    checks.append(Check("PyQt6", OK if _module("PyQt6") else MISSING, "the shell cannot start without it"))
    checks.append(Check("pydantic", OK if _module("pydantic") else MISSING, "the shell cannot start without it"))
    checks.append(
        Check(
            "watchdog",
            OK if _module("watchdog") else DEGRADED,
            "config live-reload; without it, use `chillpillc reload`",
        )
    )

    for label, module, feature in (
        ("pywin32", "win32api", "AppBar, monitors, shutdown privilege"),
        ("comtypes", "comtypes", "audio and shell COM interfaces"),
        ("pycaw", "pycaw", "volume slider and mute"),
        ("WMI", "wmi", "internal display brightness"),
        ("pyvda", "pyvda", "virtual desktop indicator"),
        ("Pillow", "PIL", "launcher icons"),
    ):
        present = _module(module)
        checks.append(Check(label, OK if present else DEGRADED, feature if present else f"{feature} unavailable"))

    winrt_groups = {
        "media": ("winrt.windows.media.control", "winrt.windows.storage.streams"),
        "notifications": (
            "winrt.windows.ui.notifications",
            "winrt.windows.ui.notifications.management",
            "winrt.windows.applicationmodel",
            "winrt.windows.foundation.collections",
        ),
    }
    for feature, modules in winrt_groups.items():
        absent = [name for name in modules if not _module(name)]
        checks.append(
            Check(
                f"WinRT ({feature})",
                OK if not absent else DEGRADED,
                "available" if not absent else f"missing {', '.join(absent)}",
            )
        )

    fonts_readable = _ensure_qt()
    for family in ("Monocraft", "JetBrainsMono Nerd Font Propo"):
        if not fonts_readable:
            checks.append(Check(f"font: {family}", DEGRADED, "could not query Qt's font database"))
            continue
        present = _font_installed(family)
        checks.append(
            Check(
                f"font: {family}",
                OK if present else DEGRADED,
                "installed" if present else "not installed; Qt will substitute and glyphs may show as boxes",
            )
        )

    from shell.platform import flow

    if flow.is_installed():
        detail = "installed" + ("" if flow.plugin_installed() else "; ChillPill plugin not copied in yet")
        checks.append(Check("Flow Launcher", OK if flow.plugin_installed() else DEGRADED, detail))
    else:
        checks.append(Check("Flow Launcher", DEGRADED, "not installed; the built-in launcher will be used"))

    running = False
    if IS_WINDOWS:
        from shell.ipc.client import is_running

        running = is_running()
    checks.append(
        Check("shell running", OK if running else DEGRADED, "answering on the pipe" if running else "not started")
    )

    if shutil.which("chillpillc") is None:
        checks.append(Check("chillpillc", DEGRADED, "not on PATH; use `python -m shell.cli` instead"))
    else:
        checks.append(Check("chillpillc", OK, shutil.which("chillpillc") or ""))

    return checks


def main() -> int:
    checks = run_checks()
    width = max(len(check.name) for check in checks)
    for check in checks:
        print(f"[{check.mark}] {check.name.ljust(width)}  {check.detail}")

    blockers = [check for check in checks if check.status == MISSING]
    degraded = [check for check in checks if check.status == DEGRADED]
    print()
    if blockers:
        print(f"{len(blockers)} blocker(s): " + ", ".join(check.name for check in blockers))
        print("The shell will not start until these are fixed.")
        return 1
    if degraded:
        print(f"Ready to start. {len(degraded)} feature(s) degraded: " + ", ".join(c.name for c in degraded))
        return 0
    print("Everything checks out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
