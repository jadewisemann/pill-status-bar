"""Wallpaper library: list a directory, set the desktop background."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPixmap

from shell.modules.base import Module
from shell.platform.system import set_wallpaper

logger = logging.getLogger(__name__)

EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
THUMBNAIL_SIZE = QSize(160, 90)


class WallpaperModule(Module):
    name = "wallpaper"
    #: Rescans are triggered by opening the switcher, not by a timer -- the
    #: directory changes when the user puts a file in it, and they will be
    #: looking at the switcher when they do.
    poll_interval_ms = None

    def __init__(self, directory: str = "", parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._dir = Path(directory) if directory else Path.home() / "Pictures" / "wallpapers"
        self._files: list[Path] = []
        self._thumbnails: dict[str, QPixmap] = {}
        self._current: str = ""

    def set_directory(self, directory: str) -> None:
        new_dir = Path(directory)
        if new_dir == self._dir:
            return
        self._dir = new_dir
        self._thumbnails.clear()
        self.refresh()

    def refresh(self) -> None:
        if not self._dir.is_dir():
            self._files = []
            self.update(count=0, directory=str(self._dir), missing=True)
            return
        self._files = sorted(
            (p for p in self._dir.iterdir() if p.suffix.lower() in EXTENSIONS),
            key=lambda p: p.name.lower(),
        )
        self.update(count=len(self._files), directory=str(self._dir), missing=False)

    @property
    def files(self) -> list[Path]:
        return list(self._files)

    @property
    def current(self) -> str:
        return self._current

    def thumbnail(self, path: Path) -> QPixmap:
        """Scaled preview, cached by path.

        Decoding a 4K wallpaper takes long enough to drop frames, so the grid
        asks for these once and holds them for the process lifetime.
        """
        key = str(path)
        cached = self._thumbnails.get(key)
        if cached is not None:
            return cached
        pixmap = QPixmap(key)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                THUMBNAIL_SIZE,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._thumbnails[key] = pixmap
        return pixmap

    def apply(self, path: Path | str) -> bool:
        ok = set_wallpaper(path)
        if ok:
            self._current = str(path)
            self.update(current=self._current)
        return ok
