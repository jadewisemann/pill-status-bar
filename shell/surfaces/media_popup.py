"""Media auto-popup: 340x90, shown for `mediaPopupDuration` when a track starts."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from shell.modules.base import ModuleRegistry
from shell.state import PillState
from shell.surfaces.base import Surface
from shell.theme import GLYPHS, PALETTE
from shell.widgets import Artwork, GlyphButton, MarqueeLabel, ProgressBar, TextLabel


class MediaPopup(Surface):
    state = PillState.MEDIA_POPUP
    uses = ("media",)

    #: Clicked through to the full player.
    expand_requested = pyqtSignal()

    def __init__(self, registry: ModuleRegistry, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)

        self.artwork = Artwork(size=56, radius=8, parent=self)
        row.addWidget(self.artwork)

        column = QVBoxLayout()
        column.setSpacing(2)
        self.title = MarqueeLabel("", size=11, parent=self)
        self.artist = MarqueeLabel("", size=9, color=PALETTE.text_muted, parent=self)
        self.progress = ProgressBar(height=3, parent=self)
        column.addStretch(1)
        column.addWidget(self.title)
        column.addWidget(self.artist)
        column.addWidget(self.progress)
        column.addStretch(1)
        row.addLayout(column, 1)

        self.play_pause = GlyphButton(GLYPHS.play, diameter=28, parent=self)
        row.addWidget(self.play_pause)

        self.source = TextLabel("", size=8, color=PALETTE.text_dim, parent=self)
        self.source.hide()  # kept for the app id when we have room for it

        self.progress.seeked.connect(self._seek)

    def bind(self) -> None:
        media = self.module("media")
        media.changed.connect(self.refresh)
        media.artwork_ready.connect(self.artwork.set_pixmap)  # type: ignore[attr-defined]
        self.play_pause.clicked.connect(media.play_pause)  # type: ignore[attr-defined]

    def refresh(self) -> None:
        media = self.module("media")
        self.title.set_text(str(media.get("title", "")) or "Unknown track")
        self.artist.set_text(str(media.get("artist", "")))
        self.play_pause.set_glyph(GLYPHS.pause if media.get("playing") else GLYPHS.play)
        duration = float(media.get("duration", 0.0))
        position = float(media.get("position", 0.0))
        self.progress.set_fraction(position / duration if duration else 0.0)

    def set_artwork(self, pixmap: QPixmap) -> None:
        self.artwork.set_pixmap(pixmap)

    def _seek(self, fraction: float) -> None:
        media = self.module("media")
        duration = float(media.get("duration", 0.0))
        if duration:
            media.seek(fraction * duration)  # type: ignore[attr-defined]

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.expand_requested.emit()
