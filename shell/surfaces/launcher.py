"""Built-in app launcher: 390x410.

The fallback for when Flow Launcher is not installed.  Enumeration comes from
the vendored yasb loader -- Start Menu shortcuts, UWP apps via Get-StartApps,
and Control Panel applets are three different lookups with three different
launch mechanisms, and none of them is worth rediscovering.  Icons come from
`shell.platform.icons`.
"""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shell.modules.base import ModuleRegistry
from shell.platform import IS_WINDOWS
from shell.platform.icons import icon_for
from shell.platform.system import open_path, run_detached
from shell.state import PillState
from shell.surfaces.base import Surface
from shell.theme import FONTS, GLYPHS, PALETTE
from shell.widgets import IconLabel, scrollbar_stylesheet, text_font

logger = logging.getLogger(__name__)

MAX_RESULTS = 40
ICON_SIZE = 24


class Launcher(Surface):
    state = PillState.LAUNCHER
    uses = ()

    #: The launcher finished its job and the pill should close.
    dismissed = pyqtSignal()

    def __init__(self, registry: ModuleRegistry, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        self._apps: list[tuple[str, str, str | None]] = []
        self._loader: object | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        search_row.addWidget(IconLabel(GLYPHS.search, size=14, parent=self))
        self.query = QLineEdit(self)
        self.query.setPlaceholderText("Search applications")
        self.query.setFont(text_font(size=FONTS.panel_size))
        self.query.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {PALETTE.text}; }}"
            f"QLineEdit::placeholder {{ color: {PALETTE.text_dim}; }}"
        )
        self.query.textChanged.connect(self._filter)
        self.query.returnPressed.connect(self._launch_selected)
        search_row.addWidget(self.query, 1)
        outer.addLayout(search_row)

        self.results = QListWidget(self)
        self.results.setStyleSheet(
            scrollbar_stylesheet()
            + f"""
            QListWidget {{ background: transparent; border: none; outline: none; }}
            QListWidget::item {{ color: {PALETTE.text}; padding: 6px 8px; border-radius: 8px; }}
            QListWidget::item:selected {{ background: {PALETTE.surface_hover}; }}
            """
        )
        self.results.setFont(text_font(size=FONTS.panel_size))
        self.results.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.results.itemActivated.connect(lambda _item: self._launch_selected())
        self.results.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        outer.addWidget(self.results, 1)

        self.status = QLabel("", self)
        self.status.setFont(text_font(size=FONTS.small_size))
        self.status.setStyleSheet(f"color: {PALETTE.text_dim}; background: transparent;")
        outer.addWidget(self.status)

    # -- lifecycle ---------------------------------------------------------

    def on_shown(self) -> None:
        super().on_shown()
        self.query.clear()
        self.query.setFocus(Qt.FocusReason.OtherFocusReason)
        if not self._apps:
            self._load_apps()
        else:
            self._filter("")

    def _load_apps(self) -> None:
        if not IS_WINDOWS:
            self.status.setText("app enumeration is Windows-only")
            return
        try:
            from vendor.win32.app_loader import AppListLoader
        except ImportError as exc:
            logger.error("app loader unavailable: %s", exc)
            self.status.setText("could not read the Start Menu")
            return
        self.status.setText("reading the Start Menu...")
        loader = AppListLoader()
        loader.apps_loaded.connect(self._on_apps_loaded)
        loader.start()
        self._loader = loader  # keep the QThread alive until it finishes

    def _on_apps_loaded(self, apps: list) -> None:
        self._apps = sorted(apps, key=lambda entry: str(entry[0]).lower())
        self.status.setText(f"{len(self._apps)} applications")
        self._filter(self.query.text())

    # -- filtering ---------------------------------------------------------

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        self.results.clear()
        matches = 0
        for name, target, _description in self._apps:
            if needle and needle not in str(name).lower():
                continue
            item = QListWidgetItem(str(name))
            item.setData(Qt.ItemDataRole.UserRole, target)
            icon = self._icon_for(str(target))
            if icon is not None:
                item.setIcon(icon)
            self.results.addItem(item)
            matches += 1
            if matches >= MAX_RESULTS:
                break
        if self.results.count():
            self.results.setCurrentRow(0)
        if needle:
            self.status.setText(f"{matches} match{'' if matches == 1 else 'es'}")

    def _icon_for(self, target: str) -> QIcon | None:
        pixmap = icon_for(target, size=ICON_SIZE * 2)
        return QIcon(pixmap) if not pixmap.isNull() else None

    # -- launching ---------------------------------------------------------

    def _launch_selected(self) -> None:
        item = self.results.currentItem()
        if item is None:
            return
        target = str(item.data(Qt.ItemDataRole.UserRole))
        if self.launch(target):
            self.dismissed.emit()

    @staticmethod
    def launch(target: str) -> bool:
        """Start whatever kind of entry this is.

        Three shapes come out of the enumerator and each needs its own verb:
        a UWP app is an AppsFolder item, a Control Panel applet is a shell
        CLSID, and everything else is a path the shell can open directly.
        """
        if target.startswith("UWP::"):
            return run_detached(f"explorer.exe shell:AppsFolder\\{target[5:]}")
        if target.startswith("CPL::"):
            parts = target.split("::")
            clsid = parts[1] if len(parts) > 1 else ""
            return run_detached(f"explorer.exe shell:::{clsid}")
        if os.path.exists(target):
            return open_path(target)
        return run_detached(target)

    # -- input -------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.dismissed.emit()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.results.count():
            step = 1 if key == Qt.Key.Key_Down else -1
            row = (self.results.currentRow() + step) % self.results.count()
            self.results.setCurrentRow(row)
            return
        super().keyPressEvent(event)
