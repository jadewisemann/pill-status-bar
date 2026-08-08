"""Notification popup: 305x52 at radius 99 -- the pill at its most literal.

Also carries the fullscreen slide-in variant, which is the one exception to
"the pill is the only window": a toast that must be readable over a maximised
window cannot live inside a 305px bar.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from shell.modules.base import ModuleRegistry
from shell.modules.notifications import Notification
from shell.state import PillState
from shell.surfaces.base import Surface
from shell.theme import FONTS, GLYPHS, PALETTE
from shell.widgets import IconLabel, MarqueeLabel, TextLabel


class NotificationPopup(Surface):
    """The in-pill toast."""

    state = PillState.NOTIFICATION
    uses = ()

    #: The toast was clicked; the app opens the control center in response.
    activated = pyqtSignal(int)  # notification id

    def __init__(self, registry: ModuleRegistry, parent: QWidget | None = None) -> None:
        super().__init__(registry, parent)
        self._current: Notification | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(22, 0, 22, 0)
        row.setSpacing(10)

        self.icon = IconLabel(GLYPHS.bell, size=FONTS.popup_icon, parent=self)
        row.addWidget(self.icon)

        text = QVBoxLayout()
        text.setSpacing(3)
        # Stretches above and below keep the two lines together in the middle;
        # without them the layout spreads them to the pill's full 52px.
        text.addStretch(1)
        self.title = MarqueeLabel("", size=FONTS.popup_title, parent=self)
        self.title.set_weight(700)
        self.body = MarqueeLabel("", size=FONTS.popup_body, color=PALETTE.notif_popup_body, parent=self)
        text.addWidget(self.title)
        text.addWidget(self.body)
        text.addStretch(1)
        row.addLayout(text, 1)

    def show_notification(self, notification: Notification) -> None:
        self._current = notification
        self.title.set_text(notification.title or notification.app or "Notification")
        self.body.set_text(notification.body.replace("\n", " "))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._current is not None:
            self.activated.emit(self._current.id)


class FullscreenToast(QWidget):
    """Slide-in toast for when the pill is hidden behind a fullscreen app.

    A separate top-level window on purpose: the pill hides itself over games
    and video, and a notification that only appears when the pill is visible is
    a notification you miss.
    """

    WIDTH = 340
    HEIGHT = 72
    MARGIN = 24

    activated = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_id: int | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(12)
        self.icon = IconLabel(GLYPHS.bell, size=16, parent=self)
        row.addWidget(self.icon)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = TextLabel("", size=11, bold=True, parent=self)
        self.body = TextLabel("", size=9, color=PALETTE.notif_popup_body, parent=self)
        text.addWidget(self.title)
        text.addWidget(self.body)
        row.addLayout(text, 1)

        self._slide = QPropertyAnimation(self, b"geometry", self)
        self._slide.setDuration(320)
        self._slide.setEasingCurve(QEasingCurve.Type.OutExpo)
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.slide_out)

    def present(self, notification: Notification, duration_ms: int) -> None:
        self._current_id = notification.id
        self.title.setText(notification.title or notification.app or "Notification")
        self.body.setText(notification.body.replace("\n", " ")[:80])

        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        end_x = area.right() - self.WIDTH - self.MARGIN
        start_x = area.right() + self.MARGIN
        y = area.top() + self.MARGIN

        self.setGeometry(QRect(start_x, y, self.WIDTH, self.HEIGHT))
        self.show()
        self._slide.stop()
        self._slide.setStartValue(QRect(start_x, y, self.WIDTH, self.HEIGHT))
        self._slide.setEndValue(QRect(end_x, y, self.WIDTH, self.HEIGHT))
        self._slide.start()
        self._dismiss_timer.start(max(1000, duration_ms))

    def slide_out(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None or not self.isVisible():
            self.hide()
            return
        area = screen.availableGeometry()
        current = self.geometry()
        self._slide.stop()
        self._slide.setStartValue(current)
        self._slide.setEndValue(QRect(area.right() + self.MARGIN, current.y(), self.WIDTH, self.HEIGHT))
        self._slide.start()
        QTimer.singleShot(self._slide.duration(), self.hide)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._current_id is not None:
            self.activated.emit(self._current_id)
            self.slide_out()

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), 18.0, 18.0)
        painter.fillPath(path, QColor(PALETTE.bg))
        painter.end()
