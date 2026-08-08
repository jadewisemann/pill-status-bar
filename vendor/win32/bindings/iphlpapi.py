# ---------------------------------------------------------------------------
# Vendored from yasb -- https://github.com/amnweb/yasb
# MIT License, Copyright (c) 2024 amnweb.  Full text: vendor/LICENSE.yasb
# Upstream path: src/core/utils/win32/bindings/iphlpapi.py
# Upstream revision: 95089f3cfffe5688911dc1a0e09dd959d49a321e
#
# DO NOT EDIT.  The only change applied to this file is a mechanical rewrite of
# import paths; see vendor/README.md.  Behaviour changes belong in
# shell/platform/, never here.
# ---------------------------------------------------------------------------
"""Wrappers for iphlpapi (IP Helper API) win32 API functions"""

from ctypes import c_void_p, windll
from ctypes.wintypes import DWORD, PULONG, ULONG

iphlpapi = windll.iphlpapi

# GetIfEntry2 - Get interface statistics
iphlpapi.GetIfEntry2.argtypes = [c_void_p]  # Pointer to MIB_IF_ROW2
iphlpapi.GetIfEntry2.restype = DWORD

# GetAdaptersAddresses - Get adapter addresses
iphlpapi.GetAdaptersAddresses.argtypes = [ULONG, ULONG, c_void_p, c_void_p, PULONG]
iphlpapi.GetAdaptersAddresses.restype = ULONG
