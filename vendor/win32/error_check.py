# ---------------------------------------------------------------------------
# Vendored from yasb -- https://github.com/amnweb/yasb
# MIT License, Copyright (c) 2024 amnweb.  Full text: vendor/LICENSE.yasb
# Upstream path: src/core/utils/win32/error_check.py
# Upstream revision: 95089f3cfffe5688911dc1a0e09dd959d49a321e
#
# DO NOT EDIT.  The only change applied to this file is a mechanical rewrite of
# import paths; see vendor/README.md.  Behaviour changes belong in
# shell/platform/, never here.
# ---------------------------------------------------------------------------
import ctypes as ct

from vendor.win32.bindings.kernel32 import FormatMessage
from vendor.win32.constants import FORMAT_MESSAGE_FROM_SYSTEM, FORMAT_MESSAGE_IGNORE_INSERTS


def format_error_message(error_code: int) -> str:
    buffer = ct.create_unicode_buffer(1024)
    length = FormatMessage(
        FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        None,
        error_code,
        0,
        buffer,
        len(buffer),
        None,
    )
    return buffer.value.strip() if length else f"Unknown error code: {error_code}"
