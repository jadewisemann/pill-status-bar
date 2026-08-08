# ---------------------------------------------------------------------------
# Vendored from yasb -- https://github.com/amnweb/yasb
# MIT License, Copyright (c) 2024 amnweb.  Full text: vendor/LICENSE.yasb
# Upstream path: src/core/utils/win32/bindings/ole32.py
# Upstream revision: 95089f3cfffe5688911dc1a0e09dd959d49a321e
#
# DO NOT EDIT.  The only change applied to this file is a mechanical rewrite of
# import paths; see vendor/README.md.  Behaviour changes belong in
# shell/platform/, never here.
# ---------------------------------------------------------------------------
"""Wrappers for ole32 win32 API functions to make them easier to use and have proper types"""

from ctypes import c_long, c_void_p, windll

ole32 = windll.ole32

ole32.CoInitialize.argtypes = [c_void_p]
ole32.CoInitialize.restype = c_long

ole32.CoUninitialize.argtypes = []
ole32.CoUninitialize.restype = None
