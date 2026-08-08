# ---------------------------------------------------------------------------
# Vendored from yasb -- https://github.com/amnweb/yasb
# MIT License, Copyright (c) 2024 amnweb.  Full text: vendor/LICENSE.yasb
# Upstream path: src/core/utils/win32/bindings/dxva2.py
# Upstream revision: 95089f3cfffe5688911dc1a0e09dd959d49a321e
#
# DO NOT EDIT.  The only change applied to this file is a mechanical rewrite of
# import paths; see vendor/README.md.  Behaviour changes belong in
# shell/platform/, never here.
# ---------------------------------------------------------------------------
"""Wrappers for dxva2 win32 API functions for monitor brightness control via DDC/CI"""

import ctypes.wintypes as wintypes
from ctypes import POINTER, Structure, windll
from ctypes.wintypes import BOOL, BYTE, DWORD, HANDLE, WCHAR


class PHYSICAL_MONITOR(Structure):
    """Physical monitor structure for DDC/CI communication."""

    _fields_ = [
        ("hPhysicalMonitor", HANDLE),
        ("szPhysicalMonitorDescription", WCHAR * 128),
    ]


dxva2 = windll.dxva2

# GetNumberOfPhysicalMonitorsFromHMONITOR
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, POINTER(DWORD)]
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = BOOL

# GetPhysicalMonitorsFromHMONITOR
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, DWORD, POINTER(PHYSICAL_MONITOR)]
dxva2.GetPhysicalMonitorsFromHMONITOR.restype = BOOL

# GetVCPFeatureAndVCPFeatureReply - for reading monitor values like brightness
dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [HANDLE, BYTE, POINTER(DWORD), POINTER(DWORD), POINTER(DWORD)]
dxva2.GetVCPFeatureAndVCPFeatureReply.restype = BOOL

# SetVCPFeature - for setting monitor values like brightness
dxva2.SetVCPFeature.argtypes = [HANDLE, BYTE, DWORD]
dxva2.SetVCPFeature.restype = BOOL

# DestroyPhysicalMonitor
dxva2.DestroyPhysicalMonitor.argtypes = [HANDLE]
dxva2.DestroyPhysicalMonitor.restype = BOOL

# VCP codes
VCP_BRIGHTNESS = 0x10
VCP_CONTRAST = 0x12
