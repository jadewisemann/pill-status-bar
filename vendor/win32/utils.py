# ---------------------------------------------------------------------------
# Partial extract from yasb -- https://github.com/amnweb/yasb
# MIT License, Copyright (c) 2024 amnweb.  Full text: vendor/LICENSE.yasb
# Upstream path: src/core/utils/win32/utils.py
#
# Upstream utils.py is 497 lines and pulls in PackageManager (WinRT), PIL and a
# yasb-internal helper.  Per the implementation spec only the monitor/foreground
# helpers are needed here, so this is a verbatim extract of those functions
# rather than a full copy.  Everything below is upstream code with imports
# rewritten; do not add new behaviour to this file -- put it in
# shell/platform/ instead.
# ---------------------------------------------------------------------------

import logging

import win32api
import win32gui
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication
from win32api import GetMonitorInfo, MonitorFromWindow

from vendor.win32.bindings import GetForegroundWindow, SetForegroundWindow


def get_monitor_hwnd(window_hwnd: int) -> int | None:
    monitor = MonitorFromWindow(window_hwnd)
    if monitor is None:
        return None
    return int(monitor)


def get_monitor_info(monitor_hwnd: int) -> dict:
    monitor_info = GetMonitorInfo(monitor_hwnd)
    return {
        "rect": {
            "x": monitor_info["Monitor"][0],
            "y": monitor_info["Monitor"][1],
            "width": monitor_info["Monitor"][2],
            "height": monitor_info["Monitor"][3],
        },
        "rect_work_area": {
            "x": monitor_info["Work"][0],
            "y": monitor_info["Work"][1],
            "width": monitor_info["Work"][2],
            "height": monitor_info["Work"][3],
        },
        "flags": monitor_info["Flags"],
        "device": monitor_info["Device"],
    }


def get_foreground_hwnd():
    """Get HWND of the current foreground window"""
    return GetForegroundWindow()


def set_foreground_hwnd(hwnd):
    """Set focus to the given HWND"""
    if hwnd and hwnd != 0:
        SetForegroundWindow(int(hwnd))


def find_focused_screen(follow_mouse, follow_window, follow_primary=False, screens=None):
    """Find the screen that should be focused based on mouse position, active window, or primary screen."""

    qt_screens = QApplication.screens()
    primary_screen = QApplication.primaryScreen()

    def is_valid(name):
        return screens is None or any(name in s for s in screens)

    # Map device names to Qt screen names for window focus
    device_to_screen = {
        win32api.GetMonitorInfo(win32api.MonitorFromRect((geo.left(), geo.top(), geo.right(), geo.bottom()))).get(
            "Device"
        ): screen.name()
        for screen in qt_screens
        for geo in [screen.geometry()]
    }

    if follow_primary:
        if primary_screen is not None and is_valid(primary_screen.name()):
            return primary_screen.name()

    if follow_mouse:
        try:
            pos = QCursor.pos()
            for screen in qt_screens:
                if screen.geometry().contains(pos) and is_valid(screen.name()):
                    return screen.name()
        except Exception as e:
            logging.error("Exception in follow_mouse: %s", e)

    if follow_window:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            monitor = get_monitor_hwnd(hwnd)
            if monitor is not None:
                device_name = win32api.GetMonitorInfo(monitor).get("Device")
                screen_name = device_to_screen.get(device_name)
                if screen_name and is_valid(screen_name):
                    return screen_name

    # Fallback to primary screen
    if primary_screen is not None and is_valid(primary_screen.name()):
        return primary_screen.name()
    # Final fallback to first available screen from the list if no other screen is valid
    for screen in qt_screens:
        if is_valid(screen.name()):
            return screen.name()
    return None
