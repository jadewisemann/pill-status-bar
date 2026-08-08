# ---------------------------------------------------------------------------
# Vendored from yasb -- https://github.com/amnweb/yasb
# MIT License, Copyright (c) 2024 amnweb.  Full text: vendor/LICENSE.yasb
# Upstream path: src/core/utils/win32/bindings/ntdll.py
# Upstream revision: 95089f3cfffe5688911dc1a0e09dd959d49a321e
#
# DO NOT EDIT.  The only change applied to this file is a mechanical rewrite of
# import paths; see vendor/README.md.  Behaviour changes belong in
# shell/platform/, never here.
# ---------------------------------------------------------------------------
"""Wrappers for ntdll win32 API functions"""

from ctypes import POINTER, c_void_p, windll
from ctypes.wintypes import HANDLE, LONG, ULONG

ntdll = windll.ntdll

# NtQueryInformationProcess - used to get process command line, etc.
ntdll.NtQueryInformationProcess.argtypes = [
    HANDLE,  # ProcessHandle
    ULONG,  # ProcessInformationClass
    c_void_p,  # ProcessInformation
    ULONG,  # ProcessInformationLength
    POINTER(ULONG),  # ReturnLength
]
ntdll.NtQueryInformationProcess.restype = LONG

# NtQuerySystemInformation - used for memory list information, etc.
ntdll.NtQuerySystemInformation.argtypes = [
    ULONG,  # SystemInformationClass
    c_void_p,  # SystemInformation
    ULONG,  # SystemInformationLength
    POINTER(ULONG),  # ReturnLength
]
ntdll.NtQuerySystemInformation.restype = LONG

# Process information class constants
ProcessCommandLineInformation = 60

# System information class constants
SystemMemoryListInformation = 80
