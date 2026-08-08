# ---------------------------------------------------------------------------
# Vendored from yasb -- https://github.com/amnweb/yasb
# MIT License, Copyright (c) 2024 amnweb.  Full text: vendor/LICENSE.yasb
# Upstream path: src/core/utils/win32/bindings/powrprof.py
# Upstream revision: 95089f3cfffe5688911dc1a0e09dd959d49a321e
#
# DO NOT EDIT.  The only change applied to this file is a mechanical rewrite of
# import paths; see vendor/README.md.  Behaviour changes belong in
# shell/platform/, never here.
# ---------------------------------------------------------------------------
"""Wrappers for powerprof win32 API functions to make them easier to use and have proper types"""

from ctypes import POINTER, windll, wintypes

from vendor.win32.structs import GUID

powrprof = windll.powrprof

# -- Power management function prototypes -- #
powrprof.PowerEnumerate.argtypes = [
    wintypes.HANDLE,
    POINTER(GUID),
    POINTER(GUID),
    wintypes.DWORD,
    wintypes.ULONG,
    wintypes.LPBYTE,
    POINTER(wintypes.DWORD),
]
powrprof.PowerEnumerate.restype = wintypes.DWORD

powrprof.PowerReadFriendlyName.argtypes = [
    wintypes.HANDLE,
    POINTER(GUID),
    POINTER(GUID),
    POINTER(wintypes.DWORD),
    wintypes.LPBYTE,
    POINTER(wintypes.DWORD),
]
powrprof.PowerReadFriendlyName.restype = wintypes.DWORD

powrprof.PowerGetActiveScheme.argtypes = [wintypes.HANDLE, POINTER(POINTER(GUID))]
powrprof.PowerGetActiveScheme.restype = wintypes.DWORD

powrprof.PowerSetActiveScheme.argtypes = [wintypes.HANDLE, POINTER(GUID)]
powrprof.PowerSetActiveScheme.restype = wintypes.DWORD

powrprof.PowerReadACValueIndex.argtypes = [
    wintypes.HANDLE,
    POINTER(GUID),
    POINTER(GUID),
    POINTER(GUID),
    POINTER(wintypes.DWORD),
]
powrprof.PowerReadACValueIndex.restype = wintypes.DWORD

powrprof.PowerReadDCValueIndex.argtypes = [
    wintypes.HANDLE,
    POINTER(GUID),
    POINTER(GUID),
    POINTER(GUID),
    POINTER(wintypes.DWORD),
]
powrprof.PowerReadDCValueIndex.restype = wintypes.DWORD

powrprof.PowerWriteACValueIndex.argtypes = [
    wintypes.HANDLE,
    POINTER(GUID),
    POINTER(GUID),
    POINTER(GUID),
    wintypes.DWORD,
]
powrprof.PowerWriteACValueIndex.restype = wintypes.DWORD

powrprof.PowerWriteDCValueIndex.argtypes = [
    wintypes.HANDLE,
    POINTER(GUID),
    POINTER(GUID),
    POINTER(GUID),
    wintypes.DWORD,
]
powrprof.PowerWriteDCValueIndex.restype = wintypes.DWORD


# -- Power management function wrappers -- #
def PowerEnumerate(
    RootPowerKey,
    SchemeGuid,
    SubGroupOfPowerSettingsGuid,
    AccessFlags,
    Index,
    Buffer,
    BufferSize,
):
    return powrprof.PowerEnumerate(
        RootPowerKey,
        SchemeGuid,
        SubGroupOfPowerSettingsGuid,
        AccessFlags,
        Index,
        Buffer,
        BufferSize,
    )


def PowerReadFriendlyName(
    RootPowerKey,
    SchemeGuid,
    SubGroupOfPowerSettingsGuid,
    PowerSettingGuid,
    Buffer,
    BufferSize,
):
    return powrprof.PowerReadFriendlyName(
        RootPowerKey,
        SchemeGuid,
        SubGroupOfPowerSettingsGuid,
        PowerSettingGuid,
        Buffer,
        BufferSize,
    )


def PowerGetActiveScheme(
    UserRootPowerKey,
    ActivePolicyGuid,
):
    return powrprof.PowerGetActiveScheme(UserRootPowerKey, ActivePolicyGuid)


def PowerSetActiveScheme(
    UserRootPowerKey,
    SchemeGuid,
):
    return powrprof.PowerSetActiveScheme(UserRootPowerKey, SchemeGuid)


def PowerReadACValueIndex(RootPowerKey, SchemeGuid, SubGroupGuid, PowerSettingGuid, ValueIndex):
    return powrprof.PowerReadACValueIndex(RootPowerKey, SchemeGuid, SubGroupGuid, PowerSettingGuid, ValueIndex)


def PowerReadDCValueIndex(RootPowerKey, SchemeGuid, SubGroupGuid, PowerSettingGuid, ValueIndex):
    return powrprof.PowerReadDCValueIndex(RootPowerKey, SchemeGuid, SubGroupGuid, PowerSettingGuid, ValueIndex)


def PowerWriteACValueIndex(RootPowerKey, SchemeGuid, SubGroupGuid, PowerSettingGuid, ValueIndex):
    return powrprof.PowerWriteACValueIndex(RootPowerKey, SchemeGuid, SubGroupGuid, PowerSettingGuid, ValueIndex)


def PowerWriteDCValueIndex(RootPowerKey, SchemeGuid, SubGroupGuid, PowerSettingGuid, ValueIndex):
    return powrprof.PowerWriteDCValueIndex(RootPowerKey, SchemeGuid, SubGroupGuid, PowerSettingGuid, ValueIndex)
