"""Windows plumbing, wrapped so the rest of the shell never touches ctypes.

Everything here degrades to a no-op off Windows.  That is not for portability --
ChillPill-Win is a Windows shell -- it is so the pure parts (state table,
config, layout) stay importable and testable on any machine.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


def windows_build() -> int:
    """Windows build number, or 0 elsewhere.  22000+ means Windows 11."""
    if not IS_WINDOWS:
        return 0
    return sys.getwindowsversion().build  # type: ignore[attr-defined]


def is_windows_11() -> bool:
    return windows_build() >= 22000


__all__ = ["IS_WINDOWS", "is_windows_11", "windows_build"]
