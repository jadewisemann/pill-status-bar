"""Application icons for the built-in launcher.

Three kinds of target need three different extractions:

* an `.exe`/`.dll` carries its icons as PE resources -- `pe_icons.IconExtractor`
* a `.lnk` points at one, possibly with an explicit icon override
* a UWP app has no file at all, only an AUMID -- `aumid_icons.get_icon_for_aumid`

The heavy lifting is vendored; this module picks the right one, converts the
result to a `QPixmap` and caches it on disk so the second time the launcher
opens it does not repeat the work.

Note: yasb's own `icon_extractor.py` orchestrates the same three paths, but the
revision this project vendors from does not parse under Python 3 (it contains a
Python 2 `except A, B:` clause), so it is not vendored.  See vendor/README.md.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from PyQt6.QtGui import QPixmap

from shell.config import cache_dir
from shell.platform import IS_WINDOWS

logger = logging.getLogger(__name__)

DEFAULT_SIZE = 48


def cache_directory() -> Path:
    path = cache_dir() / "icons"
    path.mkdir(parents=True, exist_ok=True)
    return path


def icon_for(target: str, size: int = DEFAULT_SIZE) -> QPixmap:
    """Best-effort icon for a launcher entry.  Never raises; may be null.

    A missing icon is cosmetic, and a launcher that refuses to list an app
    because its shortcut is broken is worse than one with a blank tile.
    """
    if not IS_WINDOWS or not target:
        return QPixmap()

    cached = cache_directory() / f"{_key(target, size)}.png"
    if cached.is_file():
        return QPixmap(str(cached))

    try:
        image = _extract(target, size)
    except Exception as exc:
        logger.debug("no icon for %s: %s", target, exc)
        return QPixmap()
    if image is None:
        return QPixmap()

    try:
        image.save(str(cached), format="PNG")
    except Exception as exc:  # a full or read-only cache must not break the list
        logger.debug("could not cache icon for %s: %s", target, exc)
        return _to_pixmap(image)
    return QPixmap(str(cached))


def _key(target: str, size: int) -> str:
    return hashlib.sha1(f"{target}\x00{size}".encode(), usedforsecurity=False).hexdigest()[:20]


def _extract(target: str, size: int) -> Any | None:
    """Return a PIL image for `target`, or None."""
    if target.startswith("UWP::"):
        from vendor.win32.aumid_icons import get_icon_for_aumid

        return get_icon_for_aumid(target[len("UWP::") :], size=size)

    if target.startswith("CPL::"):
        return None  # Control Panel applets keep their icon in a shell CLSID

    path = Path(target)
    if path.suffix.lower() == ".lnk":
        resolved = _resolve_shortcut(target)
        if not resolved:
            return None
        path = Path(resolved)

    if not path.is_file():
        return None
    return _from_pe(str(path), size)


def _resolve_shortcut(lnk_path: str) -> str | None:
    """Follow a .lnk to whatever it points at (or to its icon override)."""
    try:
        from vendor.win32.app_loader import ShortcutResolver

        target = ShortcutResolver.resolve_lnk_target(lnk_path)
    except Exception as exc:
        logger.debug("could not resolve %s: %s", lnk_path, exc)
        return None
    if isinstance(target, (tuple, list)):
        target = target[0] if target else None
    return str(target) if target else None


def _from_pe(path: str, size: int) -> Any | None:
    from PIL import Image

    from vendor.win32.pe_icons import IconExtractor

    stream = IconExtractor(path).get_icon(0)
    image = Image.open(stream)
    # An .ico holds several frames; pick the one closest to what was asked for.
    if getattr(image, "n_frames", 1) > 1:
        best_index, best_delta = 0, None
        for index in range(image.n_frames):
            image.seek(index)
            delta = abs(image.size[0] - size)
            if best_delta is None or delta < best_delta:
                best_index, best_delta = index, delta
        image.seek(best_index)
    return image.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


def _to_pixmap(image: Any) -> QPixmap:
    """PIL image -> QPixmap without touching the disk."""
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    return pixmap
