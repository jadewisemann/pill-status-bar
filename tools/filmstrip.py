"""Render a morph as a strip of frames.

The animation is the product, so it needs to be inspectable without a Windows
box.  This drives the real state machine and the real widgets on a virtual
clock, sampling the pill every N milliseconds and laying the frames out left to
right.

    python tools/filmstrip.py idle controlCenter out/morph.png

`QTest.qWait` is what advances Qt's animations: it spins the event loop for
real time, so the frames are what the compositor would actually show, not an
interpolation this script invented.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QSize  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from shell import modules as modules_pkg  # noqa: E402
from shell.config import Config  # noqa: E402
from shell.pill import Pill  # noqa: E402
from shell.state import MorphContext, PillState, PillStateMachine  # noqa: E402
from shell.surfaces import (  # noqa: E402
    ClipboardHistory,
    ControlCenter,
    Dashboard,
    Launcher,
    MediaPopup,
    NotificationPopup,
    Osd,
    PillBar,
    WallpaperSwitcher,
)

#: How often to sample, and for how long.  550ms covers the slowest morph
#: (height) with a little tail to show it settling.
STEP_MS = 40
TOTAL_MS = 640
BACKDROP = QColor(52, 58, 64)
GAP = 8

NAMES = {
    "idle": PillState.IDLE,
    "osd": PillState.OSD,
    "notification": PillState.NOTIFICATION,
    "media": PillState.MEDIA_POPUP,
    "controlCenter": PillState.CONTROL_CENTER,
    "dashboard": PillState.DASHBOARD,
    "launcher": PillState.LAUNCHER,
    "clipboard": PillState.CLIPBOARD,
    "wallpapers": PillState.WALLPAPERS,
}


def grab(pill: Pill) -> QImage:
    image = QImage(QSize(pill.width(), pill.height()), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    pill.render(painter)
    painter.end()
    return image


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(f"usage: filmstrip.py <from> <to> <out.png>\nstates: {', '.join(NAMES)}", file=sys.stderr)
        return 2
    start_name, end_name, out_path = argv[0], argv[1], argv[2]
    if start_name not in NAMES or end_name not in NAMES:
        print(f"unknown state; expected one of {', '.join(NAMES)}", file=sys.stderr)
        return 2

    # Kept in a local: Python must hold the reference for the widgets' lifetime,
    # or Qt tears the application down under them.
    app = QApplication(sys.argv[:1])
    config = Config()
    machine = PillStateMachine(MorphContext(row_width=240.0, row_height=24.0))
    registry = modules_pkg.build_registry(config)

    pill = Pill(config, machine)
    for surface in (
        PillBar(registry, config),
        ControlCenter(registry, config),
        Dashboard(registry, config),
        Osd(registry),
        NotificationPopup(registry),
        MediaPopup(registry),
        Launcher(registry),
        ClipboardHistory(registry),
        WallpaperSwitcher(registry, config),
    ):
        pill.add_surface(surface)
    pill.show()

    # Settle into the starting state with no animation at all.
    if NAMES[start_name] is not PillState.IDLE:
        machine.open(NAMES[start_name])
    pill.apply_morph(animated=False)
    QTest.qWait(60)

    frames: list[tuple[int, QImage]] = [(0, grab(pill))]
    if NAMES[end_name] is PillState.IDLE:
        machine.close_all()
    else:
        machine.open(NAMES[end_name])

    elapsed = 0
    while elapsed < TOTAL_MS:
        QTest.qWait(STEP_MS)
        elapsed += STEP_MS
        frames.append((elapsed, grab(pill)))

    width = sum(frame.width() + GAP for _, frame in frames) + GAP
    height = max(frame.height() for _, frame in frames) + GAP * 2
    strip = QImage(QSize(width, height), QImage.Format.Format_ARGB32_Premultiplied)
    strip.fill(BACKDROP)
    painter = QPainter(strip)
    painter.setPen(QColor(200, 200, 200))
    x = GAP
    for millis, frame in frames:
        y = (height - frame.height()) // 2
        painter.drawImage(x, y, frame)
        painter.drawText(x, height - 2, f"{millis}")
        x += frame.width() + GAP
    painter.end()

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    strip.save(out_path)
    print(f"{start_name} -> {end_name}: {len(frames)} frames every {STEP_MS}ms -> {out_path}")

    registry.stop_all()
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
