"""Wallpaper switcher: 600x308, a scrollable grid of thumbnails."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPaintEvent
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from shell.config import Config
from shell.modules.base import ModuleRegistry
from shell.platform.system import open_path
from shell.state import PillState
from shell.surfaces.base import Surface
from shell.theme import GLYPHS, PALETTE
from shell.widgets import GlyphButton, IconLabel, TextLabel, scrollbar_stylesheet

COLUMNS = 3
TILE = QSize(172, 97)


class WallpaperTile(QWidget):
    """One thumbnail; click to apply."""

    chosen = pyqtSignal(object)  # Path

    def __init__(self, path: Path, pixmap: object, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = path
        self._pixmap = pixmap
        self._hovered = False
        self.setFixedSize(TILE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(path.name)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def enterEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = False
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.chosen.emit(self._path)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), 10.0, 10.0)
        painter.setClipPath(path)
        painter.fillPath(path, QColor(PALETTE.surface))
        if self._pixmap is not None and not self._pixmap.isNull():  # type: ignore[union-attr]
            x = (self.width() - self._pixmap.width()) // 2  # type: ignore[union-attr]
            y = (self.height() - self._pixmap.height()) // 2  # type: ignore[union-attr]
            painter.drawPixmap(x, y, self._pixmap)  # type: ignore[arg-type]
        if self._hovered:
            painter.fillPath(path, QColor(255, 255, 255, 46))
        painter.end()


class WallpaperSwitcher(Surface):
    state = PillState.WALLPAPERS
    uses = ("wallpaper",)

    dismissed = pyqtSignal()

    def __init__(self, registry: ModuleRegistry, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        self._config = config
        self._tiles: list[WallpaperTile] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(IconLabel(GLYPHS.image, size=14, parent=self))
        self.title = TextLabel("Wallpapers", size=11, bold=True, parent=self)
        header.addWidget(self.title)
        header.addStretch(1)
        self.folder_button = GlyphButton("\U000f0256", diameter=24, parent=self)  # nf-md-folder_open
        self.folder_button.clicked.connect(self._open_folder)
        header.addWidget(self.folder_button)
        self.reload_button = GlyphButton(GLYPHS.restart, diameter=24, parent=self)
        self.reload_button.clicked.connect(self.refresh)
        header.addWidget(self.reload_button)
        outer.addLayout(header)

        self.area = QScrollArea(self)
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area.setStyleSheet(scrollbar_stylesheet())
        holder = QWidget()
        self._grid = QGridLayout(holder)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        self.area.setWidget(holder)
        outer.addWidget(self.area, 1)

        self.status = TextLabel("", size=9, color=PALETTE.text_dim, parent=self)
        outer.addWidget(self.status)

    # -- content -----------------------------------------------------------

    def on_shown(self) -> None:
        super().on_shown()
        self.module("wallpaper").refresh()  # type: ignore[attr-defined]
        self.refresh()

    def refresh(self) -> None:
        wallpaper = self.module("wallpaper")
        for tile in self._tiles:
            self._grid.removeWidget(tile)
            tile.deleteLater()
        self._tiles = []

        files = wallpaper.files  # type: ignore[attr-defined]
        for index, path in enumerate(files):
            tile = WallpaperTile(path, wallpaper.thumbnail(path), parent=self)  # type: ignore[attr-defined]
            tile.chosen.connect(self._apply)
            self._grid.addWidget(tile, index // COLUMNS, index % COLUMNS)
            self._tiles.append(tile)

        directory = str(wallpaper.get("directory", ""))
        if wallpaper.get("missing", False):
            self.status.setText(f"{directory} does not exist")
        else:
            self.status.setText(f"{len(files)} in {directory}")

    # -- actions -----------------------------------------------------------

    def _apply(self, path: Path) -> None:
        if self.module("wallpaper").apply(path) and self._config.ws_close_on_wallpaper_set:  # type: ignore[attr-defined]
            self.dismissed.emit()

    def _open_folder(self) -> None:
        open_path(self.module("wallpaper").get("directory", ""))

    def apply_config(self, config: Config) -> None:
        self._config = config
        # Only if the module is already running -- a config reload should not
        # spin one up for a panel that has never been opened.
        if "wallpaper" in self._held:
            self._held["wallpaper"].set_directory(config.wallpapers_dir)  # type: ignore[attr-defined]
