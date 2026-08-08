"""Render every pill state to a PNG.

A development aid, not part of the shell.  It builds the real widgets with the
real state machine, so it catches layout and construction mistakes without a
Windows box -- run it with `QT_QPA_PLATFORM=offscreen` on any machine.

    python tools/preview.py out/

The platform modules report themselves unavailable off Windows, so the surfaces
render with empty readings.  That is the point: it exercises the geometry, not
the data.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QSize  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402
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


def seed(registry, *, media: bool, notifications: int) -> None:
    """Fake enough module state for a picture.

    The surfaces recompute the morph context from their modules, so injecting
    context directly would be overwritten -- the fake has to go in at the
    module layer, exactly where the real reading would arrive.
    """
    from shell.modules.notifications import Notification

    media_module = registry.get("media")
    if media:
        media_module.update(
            active=True,
            title="Everything In Its Right Place",
            artist="Radiohead",
            album="Kid A",
            playing=True,
            position=97.0,
            duration=251.0,
        )
    else:
        media_module.update(active=False, title="", artist="", playing=False)

    stack = registry.get("notifications")
    stack.clear()
    for index in range(notifications):
        stack.push(
            Notification(
                id=1000 + index,
                app="Mail",
                title=f"Message {index + 1}",
                body="Subject line that is long enough to be elided",
            )
        )


#: (state, extra context) pairs worth a picture.
SHOTS: list[tuple[str, PillState, dict]] = [
    ("idle", PillState.IDLE, {}),
    ("idle-hover", PillState.IDLE, {"hovered": True}),
    ("osd", PillState.OSD, {}),
    ("notification", PillState.NOTIFICATION, {}),
    ("media-popup", PillState.MEDIA_POPUP, {}),
    ("control-center", PillState.CONTROL_CENTER, {}),
    ("control-center-media", PillState.CONTROL_CENTER, {"media_active": True}),
    (
        "control-center-notifications",
        PillState.CONTROL_CENTER,
        {"notification_count": 2, "notification_list_height": 94.0},
    ),
    ("dashboard", PillState.DASHBOARD, {}),
    ("launcher", PillState.LAUNCHER, {}),
    ("clipboard", PillState.CLIPBOARD, {}),
    ("wallpapers", PillState.WALLPAPERS, {}),
]


def main(out_dir: str = "out") -> int:
    app = QApplication(sys.argv)
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

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    for name, state, context in SHOTS:
        machine.close_all()
        seed(
            registry,
            media=bool(context.pop("media_active", False)),
            notifications=int(context.pop("notification_count", 0)),
        )
        # Reset the context between shots so one picture cannot leak into the next.
        machine.update_context(**{"hovered": False, "notification_list_height": 0.0, **context})
        if state is not PillState.IDLE:
            machine.open(state)
        pill.apply_morph(animated=False)
        pill.show()
        app.processEvents()

        morph = machine.morph()
        image = QImage(QSize(pill.width(), pill.height()), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        pill.render(painter)
        painter.end()
        path = target / f"{name}.png"
        image.save(str(path))
        print(f"{name:<30} {morph.width:>6.0f} x {morph.height:<6.0f} r{morph.radius:<5.0f} -> {path}")

    registry.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "out"))
