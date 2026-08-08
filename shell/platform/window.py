"""Window-level Win32 behaviour for the pill: DPI, styles, backdrop, AppBar.

Adapters only.  The ctypes lives in vendor/win32/; if something here needs to
behave differently, fix it here, never in vendor/.
"""

from __future__ import annotations

import ctypes
import logging
from typing import Any

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QScreen

from shell.platform import IS_WINDOWS, is_windows_11

logger = logging.getLogger(__name__)

# WS_EX_* / SWP_* values, repeated here so this module imports cleanly off Windows.
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

#: PROCESS_PER_MONITOR_DPI_AWARE_V2, as a DPI_AWARENESS_CONTEXT handle.
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def set_dpi_awareness() -> bool:
    """Opt into per-monitor DPI v2.

    Must run *before* QApplication is constructed.  Skipping it is the single
    most common cause of a pill that is the wrong size or in the wrong place on
    a multi-monitor setup (spec §3.5).
    """
    if not IS_WINDOWS:
        return False
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    try:
        if user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return True
    except (AttributeError, OSError):
        pass  # pre-1703; fall through to the older APIs
    try:
        # 2 == PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
        return True
    except (AttributeError, OSError):
        pass
    try:
        user32.SetProcessDPIAware()
        return True
    except (AttributeError, OSError):
        logger.warning("could not set DPI awareness; the pill may be mis-scaled")
        return False


def _ex_style(hwnd: int) -> int:
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    return user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)


def _set_ex_style(hwnd: int, style: int) -> None:
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)


def apply_shell_window_style(hwnd: int) -> None:
    """Make the window a shell overlay: no taskbar entry, never steals focus.

    WS_EX_NOACTIVATE is what lets you click the pill without the app underneath
    losing focus, which matters because clicking a volume slider should not
    de-focus your editor.
    """
    if not IS_WINDOWS or not hwnd:
        return
    _set_ex_style(hwnd, _ex_style(hwnd) | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST)


def set_focusable(hwnd: int, focusable: bool) -> None:
    """Let the window take the foreground, or go back to never stealing focus.

    The pill is WS_EX_NOACTIVATE by default so clicking a slider does not
    de-focus the app underneath.  The launcher and the clipboard have a text
    field, so they need the opposite for as long as they are open.
    """
    if not IS_WINDOWS or not hwnd:
        return
    style = _ex_style(hwnd)
    _set_ex_style(hwnd, style & ~WS_EX_NOACTIVATE if focusable else style | WS_EX_NOACTIVATE)


def set_topmost(hwnd: int, on_top: bool = True) -> None:
    """Re-assert topmost.  Other shells steal the top slot; call this on a timer."""
    if not IS_WINDOWS or not hwnd:
        return
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    insert_after = HWND_TOPMOST if on_top else -2  # HWND_NOTOPMOST
    user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def set_click_through(hwnd: int, enabled: bool) -> None:
    """Toggle WS_EX_TRANSPARENT so clicks fall through to whatever is behind.

    The layered+transparent pair is the Win32 equivalent of the Wayland input
    region mask the original shell uses: the pill keeps painting, but the
    padding around it stops eating clicks.
    """
    if not IS_WINDOWS or not hwnd:
        return
    style = _ex_style(hwnd)
    if enabled:
        style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
    else:
        style &= ~WS_EX_TRANSPARENT
    _set_ex_style(hwnd, style)


def set_input_region(hwnd: int, rect: QRect | None) -> None:
    """Restrict the window's hit-test area to `rect` (None = whole window).

    The pill window is larger than the pill so the drop shadow and the growth
    animation have room; without this, that empty margin swallows clicks meant
    for the desktop.
    """
    if not IS_WINDOWS or not hwnd:
        return
    gdi32 = ctypes.windll.gdi32  # type: ignore[attr-defined]
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    if rect is None:
        user32.SetWindowRgn(hwnd, None, True)
        return
    region = gdi32.CreateRectRgn(rect.left(), rect.top(), rect.right() + 1, rect.bottom() + 1)
    # SetWindowRgn takes ownership of the region on success -- do not delete it.
    if not user32.SetWindowRgn(hwnd, region, True):
        gdi32.DeleteObject(region)


def set_round_region(hwnd: int, width: int, height: int, radius: int) -> None:
    """Clip the window's hit-test area to its rounded-rectangle silhouette.

    Without this the square corners of the window still swallow clicks that
    visually land on the desktop -- the Win32 answer to the original shell's
    `mask: Region`.
    """
    if not IS_WINDOWS or not hwnd or width <= 0 or height <= 0:
        return
    gdi32 = ctypes.windll.gdi32  # type: ignore[attr-defined]
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    diameter = max(0, int(radius) * 2)
    region = gdi32.CreateRoundRectRgn(0, 0, int(width) + 1, int(height) + 1, diameter, diameter)
    if not region:
        return
    # SetWindowRgn takes ownership on success; only we clean up on failure.
    if not user32.SetWindowRgn(hwnd, region, True):
        gdi32.DeleteObject(region)


def apply_backdrop(hwnd: int, *, acrylic: bool = True, rounded: bool = False) -> None:
    """Blur behind the pill.

    `rounded` asks DWM for rounded corners.  It is off by default because the
    pill paints its own animated radius; letting DWM round the window as well
    clips the corners twice at different radii.
    """
    if not IS_WINDOWS or not hwnd:
        return
    try:
        from vendor.win32.backdrop import enable_blur, enable_mica
    except ImportError:  # pragma: no cover - vendored code missing
        logger.warning("vendor.win32.backdrop unavailable; no blur")
        return
    try:
        if acrylic:
            enable_blur(hwnd, DarkMode=True, RoundCorners=rounded, BorderColor="None")
        elif is_windows_11():
            enable_mica(hwnd)
    except Exception as exc:  # pragma: no cover - DWM is best-effort by nature
        logger.debug("backdrop not applied: %s", exc)


class AppBar:
    """Reserve desktop working area so maximised windows stop above the pill.

    Wraps vendor's `Win32AppBar`.  Registration is the part that most often goes
    wrong when hand-rolled -- an AppBar that is registered and never removed
    leaves a permanently shrunk desktop, so `remove()` runs from the app's
    shutdown path unconditionally.
    """

    EDGE_TOP = 1
    EDGE_BOTTOM = 3

    def __init__(self) -> None:
        self._impl: Any = None
        self._registered = False

    def create(self, hwnd: int, screen: QScreen, height: int, *, edge: int = EDGE_BOTTOM) -> None:
        if not IS_WINDOWS or not hwnd or self._registered:
            return
        try:
            from vendor.win32.app_bar import Win32AppBar
        except ImportError:  # pragma: no cover
            logger.warning("vendor.win32.app_bar unavailable; not reserving space")
            return
        try:
            self._impl = Win32AppBar()
            self._impl.create_appbar(
                hwnd=hwnd,
                edge=edge,
                app_bar_height=height,
                screen=screen,
                reserve_space=True,
                always_on_top=True,
            )
            self._registered = True
        except Exception as exc:
            logger.error("AppBar registration failed: %s", exc)
            self._impl = None

    def reposition(self, screen: QScreen, height: int) -> None:
        if not self._registered or self._impl is None:
            return
        try:
            self._impl.position_bar(height, screen)
            self._impl.set_position()
        except Exception as exc:
            logger.debug("AppBar reposition failed: %s", exc)

    def remove(self) -> None:
        if not self._registered or self._impl is None:
            return
        try:
            self._impl.remove_appbar()
        except Exception as exc:  # pragma: no cover
            logger.error("AppBar removal failed: %s", exc)
        finally:
            self._registered = False
            self._impl = None


def force_foreground(hwnd: int) -> None:
    """Steal focus for the built-in launcher.

    Windows fights this on purpose; vendor's `force_foreground_focus` carries
    the AttachThreadInput dance that still works (spec §8 R7).
    """
    if not IS_WINDOWS or not hwnd:
        return
    try:
        from vendor.win32.window_actions import force_foreground_focus

        force_foreground_focus(int(hwnd))
    except Exception as exc:
        logger.debug("could not take foreground: %s", exc)


def foreground_is_fullscreen() -> bool:
    """True when the focused window covers its whole monitor.

    Used to hide the pill over games and video.  Checked alongside the AppBar's
    ABN_FULLSCREENAPP notification because neither signal alone is reliable
    (spec §8 R4): the notification misses borderless-fullscreen games, and the
    geometry check alone would false-positive on the desktop itself.
    """
    if not IS_WINDOWS:
        return False
    try:
        import win32api
        import win32con
        import win32gui

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
        class_name = win32gui.GetClassName(hwnd)
        if class_name in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return False  # the desktop and the taskbar are not fullscreen apps
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        m_left, m_top, m_right, m_bottom = win32api.GetMonitorInfo(monitor)["Monitor"]
        return left <= m_left and top <= m_top and right >= m_right and bottom >= m_bottom
    except Exception as exc:  # pragma: no cover
        logger.debug("fullscreen check failed: %s", exc)
        return False


def set_app_user_model_id(aumid: str = "ChillPill.Win.Shell") -> None:
    """Give the process an AUMID.

    Unpackaged Python processes have none, and the WinRT notification APIs need
    one to associate with (spec §8 R3).  Cheap, so it runs at startup whether or
    not notifications end up being used.
    """
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(aumid)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover
        logger.debug("could not set AUMID: %s", exc)
