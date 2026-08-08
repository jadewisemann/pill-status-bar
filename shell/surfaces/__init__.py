"""Pages inside the pill.  One per `PillState`; see `shell.surfaces.base`."""

from shell.surfaces.base import Surface
from shell.surfaces.clipboard import ClipboardHistory
from shell.surfaces.control_center import ControlCenter
from shell.surfaces.dashboard import Dashboard
from shell.surfaces.launcher import Launcher
from shell.surfaces.media_popup import MediaPopup
from shell.surfaces.notification_popup import FullscreenToast, NotificationPopup
from shell.surfaces.osd import Osd
from shell.surfaces.pillbar import PillBar
from shell.surfaces.wallpapers import WallpaperSwitcher

__all__ = [
    "ClipboardHistory",
    "ControlCenter",
    "Dashboard",
    "FullscreenToast",
    "Launcher",
    "MediaPopup",
    "NotificationPopup",
    "Osd",
    "PillBar",
    "Surface",
    "WallpaperSwitcher",
]
