# ---------------------------------------------------------------------------
# Vendored from yasb -- https://github.com/amnweb/yasb
# MIT License, Copyright (c) 2024 amnweb.  Full text: vendor/LICENSE.yasb
# Upstream path: src/core/utils/win32/bindings/pdh.py
# Upstream revision: 95089f3cfffe5688911dc1a0e09dd959d49a321e
#
# DO NOT EDIT.  The only change applied to this file is a mechanical rewrite of
# import paths; see vendor/README.md.  Behaviour changes belong in
# shell/platform/, never here.
# ---------------------------------------------------------------------------
"""Bindings for PDH (Performance Data Helper) API."""

from ctypes import POINTER, c_void_p, windll
from ctypes.wintypes import DWORD, HANDLE, LONG, LPCWSTR

pdh = windll.pdh

pdh.PdhOpenQueryW.argtypes = [LPCWSTR, c_void_p, POINTER(HANDLE)]
pdh.PdhOpenQueryW.restype = LONG

pdh.PdhAddEnglishCounterW.argtypes = [HANDLE, LPCWSTR, c_void_p, POINTER(HANDLE)]
pdh.PdhAddEnglishCounterW.restype = LONG

pdh.PdhCollectQueryData.argtypes = [HANDLE]
pdh.PdhCollectQueryData.restype = LONG

pdh.PdhGetFormattedCounterValue.argtypes = [HANDLE, DWORD, POINTER(DWORD), c_void_p]
pdh.PdhGetFormattedCounterValue.restype = LONG

pdh.PdhGetFormattedCounterArrayW.argtypes = [HANDLE, DWORD, POINTER(DWORD), POINTER(DWORD), c_void_p]
pdh.PdhGetFormattedCounterArrayW.restype = LONG

pdh.PdhCloseQuery.argtypes = [HANDLE]
pdh.PdhCloseQuery.restype = LONG
