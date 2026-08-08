"""Clipboard history surface: 460x270."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shell.modules.base import ModuleRegistry
from shell.state import PillState
from shell.surfaces.base import Surface
from shell.theme import FONTS, GLYPHS, PALETTE
from shell.widgets import GlyphButton, IconLabel, TextLabel, scrollbar_stylesheet, text_font


class ClipboardHistory(Surface):
    state = PillState.CLIPBOARD
    uses = ("clipboard",)

    dismissed = pyqtSignal()

    def __init__(self, registry: ModuleRegistry, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(IconLabel(GLYPHS.clipboard, size=14, parent=self))
        self.query = QLineEdit(self)
        self.query.setPlaceholderText("Search clipboard history")
        self.query.setFont(text_font(size=FONTS.panel_size))
        self.query.setStyleSheet(f"QLineEdit {{ background: transparent; border: none; color: {PALETTE.text}; }}")
        self.query.textChanged.connect(lambda _text: self.refresh())
        self.query.returnPressed.connect(self._copy_selected)
        header.addWidget(self.query, 1)
        self.clear_button = GlyphButton("\U000f0a7a", diameter=24, parent=self)  # nf-md-delete_sweep
        self.clear_button.clicked.connect(self._clear)
        header.addWidget(self.clear_button)
        outer.addLayout(header)

        self.entries = QListWidget(self)
        self.entries.setFont(text_font(size=FONTS.panel_size))
        self.entries.setStyleSheet(
            scrollbar_stylesheet()
            + f"""
            QListWidget {{ background: transparent; border: none; outline: none; }}
            QListWidget::item {{ color: {PALETTE.text}; padding: 7px 8px; border-radius: 8px; }}
            QListWidget::item:selected {{ background: {PALETTE.surface_hover}; }}
            """
        )
        self.entries.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.entries.itemActivated.connect(lambda _item: self._copy_selected())
        outer.addWidget(self.entries, 1)

        self.status = TextLabel("", size=FONTS.small_size, color=PALETTE.text_dim, parent=self)
        outer.addWidget(self.status)

    # -- content -----------------------------------------------------------

    def on_shown(self) -> None:
        super().on_shown()
        self.query.clear()
        self.query.setFocus(Qt.FocusReason.OtherFocusReason)

    def refresh(self) -> None:
        clipboard = self.module("clipboard")
        matches = clipboard.search(self.query.text())  # type: ignore[attr-defined]
        self.entries.clear()
        for entry in matches:
            item = QListWidgetItem(entry.preview or "(empty)")
            item.setData(Qt.ItemDataRole.UserRole, entry.digest)
            item.setToolTip(f"{entry.kind} · {entry.age_text}")
            if entry.kind == "image" and entry.path:
                pixmap = QPixmap(entry.path)
                if not pixmap.isNull():
                    from PyQt6.QtGui import QIcon

                    item.setIcon(QIcon(pixmap))
            self.entries.addItem(item)
        if self.entries.count():
            self.entries.setCurrentRow(0)
        total = int(clipboard.get("count", 0))
        self.status.setText(f"{len(matches)} of {total} entries")

    # -- actions -----------------------------------------------------------

    def _copy_selected(self) -> None:
        item = self.entries.currentItem()
        if item is None:
            return
        digest = str(item.data(Qt.ItemDataRole.UserRole))
        if self.module("clipboard").copy(digest):  # type: ignore[attr-defined]
            self.dismissed.emit()

    def _clear(self) -> None:
        self.module("clipboard").clear()  # type: ignore[attr-defined]
        self.refresh()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.dismissed.emit()
            return
        if key == Qt.Key.Key_Delete and self.entries.currentItem() is not None:
            digest = str(self.entries.currentItem().data(Qt.ItemDataRole.UserRole))
            self.module("clipboard").remove(digest)  # type: ignore[attr-defined]
            self.refresh()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.entries.count():
            step = 1 if key == Qt.Key.Key_Down else -1
            self.entries.setCurrentRow((self.entries.currentRow() + step) % self.entries.count())
            return
        super().keyPressEvent(event)
