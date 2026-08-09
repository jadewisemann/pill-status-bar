"""Animation helpers.

The pill is an animation-first product: almost nothing in it changes state
instantly.  These are the two primitives that need to exist once rather than
five times -- a colour that eases to a new value, and a float that eases to a
new value -- plus the timing table transcribed from the original.

Durations and curves come from ChillPill-Shell's `Behavior` blocks.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QEasingCurve, QObject, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor

# --------------------------------------------------------------------------
# Timings
# --------------------------------------------------------------------------

#: The box itself (spec §1.2).
WIDTH_MS = 225
RADIUS_MS = 225
HEIGHT_MS = 550
HEIGHT_MEDIA_MS = 650

#: Content fades.  Panels wait a beat before appearing so the box is already
#: growing when the content arrives -- that lag is what makes the morph read as
#: one movement instead of two.
BAR_FADE_MS = 100
PANEL_FADE_DELAY_MS = 15
PANEL_FADE_MS = 150
DASHBOARD_FADE_DELAY_MS = 1
DASHBOARD_FADE_MS = 300
NOTIFICATION_FADE_MS = 150
MEDIA_POPUP_FADE_MS = 180

#: Controls.
SLIDER_FILL_MS = 60
HOVER_COLOR_MS = 100
TOGGLE_COLOR_MS = 150
TOGGLE_PRESS_MS = 80
WORKSPACE_COLOR_MS = 120
ICON_PULSE_UP_MS = 60
ICON_PULSE_DOWN_MS = 100
ICON_PULSE_SCALE = 1.15


@dataclass(frozen=True)
class FadeTiming:
    """How a surface's content appears and disappears."""

    delay_ms: int = PANEL_FADE_DELAY_MS
    in_ms: int = PANEL_FADE_MS
    out_ms: int = PANEL_FADE_MS


BAR_FADE = FadeTiming(delay_ms=0, in_ms=BAR_FADE_MS, out_ms=BAR_FADE_MS)
PANEL_FADE = FadeTiming()
DASHBOARD_FADE = FadeTiming(delay_ms=DASHBOARD_FADE_DELAY_MS, in_ms=DASHBOARD_FADE_MS, out_ms=DASHBOARD_FADE_MS)
NOTIFICATION_FADE = FadeTiming(delay_ms=0, in_ms=NOTIFICATION_FADE_MS, out_ms=NOTIFICATION_FADE_MS)
MEDIA_POPUP_FADE = FadeTiming(delay_ms=0, in_ms=MEDIA_POPUP_FADE_MS, out_ms=MEDIA_POPUP_FADE_MS)


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------


class AnimatedColor(QObject):
    """A QColor that eases to whatever you set it to.

    Owned by a painted widget, which connects `changed` to `update()` and reads
    `value` in its `paintEvent`.  Setting the same colour twice is free, and
    setting a new one mid-flight retargets from wherever the eased value
    currently is rather than restarting from the original.
    """

    changed = pyqtSignal()

    def __init__(self, color: str, duration_ms: int = HOVER_COLOR_MS, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._value = QColor(color)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(duration_ms)
        self._animation.valueChanged.connect(self._on_value)

    @property
    def value(self) -> QColor:
        return self._value

    def set(self, color: str | QColor, animated: bool = True) -> None:
        target = QColor(color)
        if target == self._value and self._animation.state() != QVariantAnimation.State.Running:
            return
        self._animation.stop()
        if not animated or not self._animation.duration():
            self._value = target
            self.changed.emit()
            return
        self._animation.setStartValue(QColor(self._value))
        self._animation.setEndValue(target)
        self._animation.start()

    def _on_value(self, value: object) -> None:
        self._value = QColor(value)  # type: ignore[arg-type]
        self.changed.emit()


class AnimatedFloat(QObject):
    """A float that eases to whatever you set it to."""

    changed = pyqtSignal()

    def __init__(
        self,
        value: float = 0.0,
        duration_ms: int = SLIDER_FILL_MS,
        curve: QEasingCurve.Type = QEasingCurve.Type.Linear,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._value = float(value)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(duration_ms)
        self._animation.setEasingCurve(curve)
        self._animation.valueChanged.connect(self._on_value)

    @property
    def value(self) -> float:
        return self._value

    def set(self, target: float, animated: bool = True) -> None:
        target = float(target)
        if abs(target - self._value) < 1e-4 and self._animation.state() != QVariantAnimation.State.Running:
            return
        self._animation.stop()
        if not animated or not self._animation.duration():
            self._value = target
            self.changed.emit()
            return
        self._animation.setStartValue(self._value)
        self._animation.setEndValue(target)
        self._animation.start()

    def _on_value(self, value: object) -> None:
        self._value = float(value)  # type: ignore[arg-type]
        self.changed.emit()

    def pulse(self, peak: float, rise_ms: int, fall_ms: int) -> None:
        """Overshoot to `peak` and settle back -- the volume icon's tick."""
        resting = self._value
        self._animation.stop()
        self._animation.setDuration(rise_ms)
        self._animation.setStartValue(resting)
        self._animation.setEndValue(peak)

        def settle() -> None:
            self._animation.finished.disconnect(settle)
            self._animation.stop()
            self._animation.setDuration(fall_ms)
            self._animation.setStartValue(peak)
            self._animation.setEndValue(resting)
            self._animation.start()

        self._animation.finished.connect(settle)
        self._animation.start()
