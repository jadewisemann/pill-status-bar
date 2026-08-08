"""Small painted widgets shared by the surfaces.

Everything here is hand-painted rather than styled: the pill's look is flat
shapes on a dark ground, and QSS on native controls fights that at every step
(focus rings, groove pixmaps, platform-specific paddings).
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from shell.theme import FONTS, GLYPHS, PALETTE, Fonts, Palette


def text_font(fonts: Fonts = FONTS, size: int | None = None, bold: bool = False) -> QFont:
    font = QFont(fonts.text_family, size or fonts.panel_body)
    font.setBold(bold)
    return font


def icon_font(fonts: Fonts = FONTS, size: int | None = None) -> QFont:
    return QFont(fonts.nerd_family, size or fonts.cc_button_icon)


class IconLabel(QLabel):
    """A single Nerd Font glyph, optionally tinted."""

    def __init__(self, glyph: str = "", size: int | None = None, parent: QWidget | None = None) -> None:
        super().__init__(glyph, parent)
        self.setFont(icon_font(size=size))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_color(PALETTE.text)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"color: {color}; background: transparent;")

    def set_glyph(self, glyph: str) -> None:
        if glyph != self.text():
            self.setText(glyph)

    def set_size(self, size: int) -> None:
        self.setFont(icon_font(size=size))


class TextLabel(QLabel):
    """Body text in the shell font."""

    def __init__(
        self,
        text: str = "",
        size: int | None = None,
        color: str | None = None,
        bold: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setFont(text_font(size=size, bold=bold))
        self.set_color(color or PALETTE.text)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"color: {color}; background: transparent;")

    def set_size(self, size: int, weight: int | None = None, letter_spacing: float = 0.0) -> None:
        """`weight` is a CSS-style number (400 normal, 500 medium, 700 bold)."""
        font = text_font(size=size)
        if weight is not None:
            font.setWeight(QFont.Weight(max(1, min(1000, weight))))
        if letter_spacing:
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
        self.setFont(font)


class MarqueeLabel(QWidget):
    """One line of text that scrolls when it does not fit.

    Track titles routinely overflow a 340px pill, and eliding them loses the
    part people actually read (the song name usually trails the remaster tag).
    """

    def __init__(
        self,
        text: str = "",
        size: int | None = None,
        color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._offset = 0.0
        self._gap = 40.0
        self._color = QColor(color or PALETTE.text)
        self.setFont(text_font(size=size))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._timer_id: int | None = None

    def set_text(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        self._offset = 0.0
        self._sync_timer()
        self.update()

    def set_weight(self, weight: int) -> None:
        """`weight` is a CSS-style number (400 normal, 700 bold)."""
        font = self.font()
        font.setWeight(QFont.Weight(max(1, min(1000, weight))))
        self.setFont(font)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        metrics = QFontMetrics(self.font())
        return QSize(metrics.horizontalAdvance(self._text), metrics.height())

    def _overflows(self) -> bool:
        return QFontMetrics(self.font()).horizontalAdvance(self._text) > self.width()

    def _sync_timer(self) -> None:
        should_run = self._overflows() and self.isVisible()
        if should_run and self._timer_id is None:
            self._timer_id = self.startTimer(33)  # ~30fps is plenty for a crawl
        elif not should_run and self._timer_id is not None:
            self.killTimer(self._timer_id)
            self._timer_id = None
            self._offset = 0.0

    def showEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)  # type: ignore[arg-type]
        self._sync_timer()

    def hideEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        super().hideEvent(event)  # type: ignore[arg-type]
        self._sync_timer()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._sync_timer()

    def timerEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        span = QFontMetrics(self.font()).horizontalAdvance(self._text) + self._gap
        self._offset = (self._offset + 0.6) % span
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setPen(self._color)
        painter.setFont(self.font())
        metrics = QFontMetrics(self.font())
        baseline = (self.height() + metrics.ascent() - metrics.descent()) / 2
        if not self._overflows():
            painter.drawText(QPointF(0.0, baseline), self._text)
        else:
            span = metrics.horizontalAdvance(self._text) + self._gap
            painter.drawText(QPointF(-self._offset, baseline), self._text)
            painter.drawText(QPointF(-self._offset + span, baseline), self._text)
        painter.end()


class Slider(QWidget):
    """Flat horizontal slider: rounded track, rounded fill, no handle.

    Click or drag anywhere on it to set the value; the wheel steps it.  Emits
    continuously while dragging so volume follows the finger, and once on
    release for consumers that only want the final value (DDC/CI writes).
    """

    value_changed = pyqtSignal(int)
    released = pyqtSignal(int)

    def __init__(
        self,
        value: int = 0,
        height: int = 4,
        fill: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._value = max(0, min(100, value))
        self._bar_height = height
        self._fill = QColor(fill or PALETTE.slider_fill)
        self._track = QColor(PALETTE.slider_track)
        self._dragging = False
        # The bar is 4px tall but the target is not: the original extends the
        # hit area by twice the bar height above and below so it stays clickable.
        self.setMinimumHeight(height * 5)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def value(self) -> int:
        return self._value

    def set_value(self, value: int, notify: bool = False) -> None:
        clamped = max(0, min(100, int(value)))
        if clamped == self._value:
            return
        self._value = clamped
        self.update()
        if notify:
            self.value_changed.emit(clamped)

    def set_fill(self, color: str) -> None:
        self._fill = QColor(color)
        self.update()

    def _value_at(self, x: float) -> int:
        if self.width() <= 0:
            return self._value
        return int(round(max(0.0, min(1.0, x / self.width())) * 100))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = True
        self.set_value(self._value_at(event.position().x()), notify=True)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if self._dragging:
            self.set_value(self._value_at(event.position().x()), notify=True)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if not self._dragging:
            return
        self._dragging = False
        self.set_value(self._value_at(event.position().x()), notify=True)
        self.released.emit(self._value)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override
        step = 5 if event.angleDelta().y() > 0 else -5
        self.set_value(self._value + step, notify=True)
        self.released.emit(self._value)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = float(self._bar_height)  # the original uses radius == height
        top = (self.height() - self._bar_height) / 2
        track = QRectF(0, top, self.width(), self._bar_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._track)
        painter.drawRoundedRect(track, radius, radius)
        filled_width = self.width() * self._value / 100
        if filled_width > 0:
            painter.setBrush(self._fill)
            painter.drawRoundedRect(
                QRectF(0, top, max(filled_width, self._bar_height), self._bar_height), radius, radius
            )
        painter.end()


class ProgressBar(QWidget):
    """Seekable playback position bar."""

    seeked = pyqtSignal(float)  # fraction 0..1

    def __init__(self, height: int = 4, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fraction = 0.0
        self._bar_height = height
        self.setMinimumHeight(height + 8)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_fraction(self, fraction: float) -> None:
        clamped = max(0.0, min(1.0, fraction))
        if abs(clamped - self._fraction) < 0.001:
            return
        self._fraction = clamped
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton or self.width() <= 0:
            return
        fraction = max(0.0, min(1.0, event.position().x() / self.width()))
        self.set_fraction(fraction)
        self.seeked.emit(fraction)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = self._bar_height / 2
        top = (self.height() - self._bar_height) / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE.slider_track))
        painter.drawRoundedRect(QRectF(0, top, self.width(), self._bar_height), radius, radius)
        width = self.width() * self._fraction
        if width > 0:
            painter.setBrush(QColor(PALETTE.text))
            painter.drawRoundedRect(QRectF(0, top, max(width, self._bar_height), self._bar_height), radius, radius)
        painter.end()


class GlyphButton(QWidget):
    """Round icon button."""

    clicked = pyqtSignal()

    def __init__(
        self,
        glyph: str,
        diameter: int = 30,
        active: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._glyph = glyph
        self._active = active
        self._hovered = False
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_glyph(self, glyph: str) -> None:
        if glyph != self._glyph:
            self._glyph = glyph
            self.update()

    def set_active(self, active: bool) -> None:
        if active != self._active:
            self._active = active
            self.update()

    @property
    def active(self) -> bool:
        return self._active

    def enterEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = False
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._active:
            background, foreground = QColor(PALETTE.text), QColor(PALETTE.background)
        elif self._hovered:
            background, foreground = QColor(PALETTE.surface_hover), QColor(PALETTE.text)
        else:
            background, foreground = QColor(PALETTE.surface), QColor(PALETTE.text_muted)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawEllipse(self.rect())
        painter.setPen(foreground)
        painter.setFont(icon_font(size=max(9, self._diameter // 2 - 2)))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._glyph)
        painter.end()


class Avatar(QWidget):
    """Circular profile picture with a glyph fallback."""

    def __init__(self, path: str = "", diameter: int = 48, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._diameter = diameter
        self._pixmap = QPixmap()
        self.setFixedSize(diameter, diameter)
        self.set_path(path)

    def set_path(self, path: str) -> None:
        pixmap = QPixmap(path) if path else QPixmap()
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self._diameter,
                self._diameter,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addEllipse(QRectF(0, 0, self._diameter, self._diameter))
        painter.setClipPath(path)
        if self._pixmap.isNull():
            painter.fillPath(path, QColor(PALETTE.surface))
            painter.setPen(QColor(PALETTE.text_muted))
            painter.setFont(icon_font(size=self._diameter // 2))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "\U000f0004")  # nf-md-account
        else:
            offset = QPointF(
                (self._diameter - self._pixmap.width()) / 2,
                (self._diameter - self._pixmap.height()) / 2,
            )
            painter.drawPixmap(offset, self._pixmap)
        painter.end()


class Artwork(QWidget):
    """Rounded album art with a music-note placeholder."""

    def __init__(self, size: int = 60, radius: int = 8, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._radius = radius
        self._pixmap = QPixmap()
        self.setFixedSize(size, size)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self._pixmap = QPixmap()
        else:
            self._pixmap = pixmap.scaled(
                self._size,
                self._size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.update()

    def clear(self) -> None:
        self._pixmap = QPixmap()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self._size, self._size), self._radius, self._radius)
        painter.setClipPath(path)
        if self._pixmap.isNull():
            painter.fillPath(path, QColor(PALETTE.surface))
            painter.setPen(QColor(PALETTE.text_dim))
            painter.setFont(icon_font(size=self._size // 3))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, GLYPHS.play)
        else:
            painter.drawPixmap(0, 0, self._pixmap)
        painter.end()


class Card(QWidget):
    """Rounded panel used as a row background inside surfaces."""

    clicked = pyqtSignal()

    def __init__(
        self,
        radius: int = 10,
        color: str | None = None,
        hoverable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._radius = radius
        self._color = QColor(color or PALETTE.surface)
        self._hoverable = hoverable
        self._hovered = False
        if hoverable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def enterEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        if self._hoverable:
            self._hovered = True
            self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        if self._hoverable:
            self._hovered = False
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(PALETTE.surface_hover) if (self._hoverable and self._hovered) else self._color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(self.rect()), self._radius, self._radius)
        painter.end()


class ToggleButton(QWidget):
    """A control-center pill: 110x35, rounded, icon and optional label.

    Three of these sit in a row (wifi, do-not-disturb, timer).  Off state is a
    dark fill with a 1px border; on state drops the border and lightens the
    fill, and the icon takes an accent colour that differs per button.
    """

    clicked = pyqtSignal()
    right_clicked = pyqtSignal()
    middle_clicked = pyqtSignal()

    WIDTH = 110
    HEIGHT = 35
    RADIUS = 10

    def __init__(
        self,
        glyph: str,
        label: str = "",
        on_color: str | None = None,
        icon_on_color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._glyph = glyph
        self._label = label
        self._active = False
        self._hovered = False
        self._pressed = False
        self._on_color = QColor(on_color or PALETTE.cc_button_bg_on)
        self._icon_on_color = QColor(icon_on_color or PALETTE.cc_wifi_icon_on)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    # -- state -------------------------------------------------------------

    def set_active(self, active: bool) -> None:
        if active != self._active:
            self._active = active
            self.update()

    def set_glyph(self, glyph: str) -> None:
        if glyph != self._glyph:
            self._glyph = glyph
            self.update()

    def set_label(self, label: str) -> None:
        if label != self._label:
            self._label = label
            self.update()

    @property
    def active(self) -> bool:
        return self._active

    # -- input -------------------------------------------------------------

    def enterEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = self._pressed = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        self._pressed = True
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        self._pressed = False
        self.update()
        if not self.rect().contains(event.position().toPoint()):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.middle_clicked.emit()

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # A press shrinks the button slightly, like the original's scale: 0.93.
        scale = 0.93 if self._pressed else 1.0
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(scale, scale)
        painter.translate(-self.width() / 2, -self.height() / 2)

        if self._active:
            background = self._on_color.lighter(120) if self._hovered else self._on_color
            icon_color = self._icon_on_color
            label_color = QColor(PALETTE.cc_button_label)
            border = None
        else:
            base = QColor(PALETTE.cc_button_bg_off)
            background = base.lighter(130) if self._hovered else base
            icon_color = label_color = QColor(PALETTE.cc_button_fg_off)
            border = QColor(PALETTE.cc_button_border)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setBrush(background)
        painter.setPen(QPen(border, 1) if border is not None else Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        icon_font_ = icon_font(size=FONTS.cc_button_icon)
        if not self._label:
            painter.setPen(icon_color)
            painter.setFont(icon_font_)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._glyph)
        else:
            label_font = text_font(size=FONTS.cc_button_label)
            icon_width = QFontMetrics(icon_font_).horizontalAdvance(self._glyph)
            label_width = QFontMetrics(label_font).horizontalAdvance(self._label)
            gap = 5.0
            start = (self.width() - icon_width - gap - label_width) / 2
            painter.setPen(icon_color)
            painter.setFont(icon_font_)
            painter.drawText(
                QRectF(start, 0, icon_width, self.height()),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                self._glyph,
            )
            painter.setPen(label_color)
            painter.setFont(label_font)
            painter.drawText(
                QRectF(start + icon_width + gap, 0, label_width + 2, self.height()),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                self._label,
            )
        painter.end()


class TransportButton(QWidget):
    """A bare media-transport glyph that brightens on hover.

    Not a circular button: the original draws these as plain text, and a chrome
    ring around them reads as a different product.
    """

    clicked = pyqtSignal()

    def __init__(self, glyph: str, size: int | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glyph = glyph
        self._hovered = False
        self._size = size or FONTS.media_control
        metrics = QFontMetrics(icon_font(size=self._size))
        self.setFixedSize(metrics.horizontalAdvance(glyph) + 6, metrics.height())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_glyph(self, glyph: str) -> None:
        if glyph != self._glyph:
            self._glyph = glyph
            self.update()

    def enterEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        del event
        self._hovered = False
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QColor(PALETTE.media_control_hover if self._hovered else PALETTE.media_control))
        painter.setFont(icon_font(size=self._size))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._glyph)
        painter.end()


class WorkspaceButton(QWidget):
    """One numbered square in the pill bar's workspace strip."""

    activated = pyqtSignal(int)

    def __init__(self, number: int, pill_scale: float = 1.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._number = number
        self._state = "empty"  # empty | used | active
        self.set_pill_scale(pill_scale)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_pill_scale(self, pill_scale: float) -> None:
        side = int(round(17.5 * pill_scale))
        self._radius = 8 * pill_scale
        self._font_size = max(6, int(round(FONTS.bar_workspace * pill_scale)))
        self.setFixedSize(side, side)

    def set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self._number)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        if self._state == "active":
            painter.setBrush(QColor(PALETTE.workspace_active_bg))
        elif self._state == "used":
            painter.setBrush(QColor(PALETTE.workspace_used_bg))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._state != "empty":
            painter.drawRoundedRect(QRectF(self.rect()), self._radius, self._radius)

        painter.setPen(QColor(PALETTE.workspace_active_fg if self._state == "active" else PALETTE.workspace_idle_fg))
        font = text_font(size=self._font_size)
        font.setWeight(QFont.Weight.Light)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._number))
        painter.end()


def scrollbar_stylesheet(palette: Palette = PALETTE) -> str:
    """Thin, chrome-less scrollbars for the list surfaces."""
    return f"""
        QScrollArea {{ background: transparent; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:vertical {{
            background: transparent; width: 4px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {palette.surface_active}; border-radius: 2px; min-height: 24px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{ height: 0; }}
    """
