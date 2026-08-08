# ---------------------------------------------------------------------------
# Vendored from yasb -- https://github.com/amnweb/yasb
# MIT License, Copyright (c) 2024 amnweb.  Full text: vendor/LICENSE.yasb
# Upstream path: src/core/utils/win32/typecheck.py
# Upstream revision: 95089f3cfffe5688911dc1a0e09dd959d49a321e
#
# DO NOT EDIT.  The only change applied to this file is a mechanical rewrite of
# import paths; see vendor/README.md.  Behaviour changes belong in
# shell/platform/, never here.
# ---------------------------------------------------------------------------
"""
Type checking helpers for ctypes
Required for private types (_CArgObject, _CFunctionType, _Pointer) not exposed to the public API
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # NOTE: this is an internal ctypes type that does not exist during runtime
    from ctypes import _CArgObject as CArgObject  # type: ignore[reportPrivateUsage]
    from ctypes import _CFunctionType as CFunctionType  # type: ignore[reportPrivateUsage]
    from ctypes import _Pointer as CPointer  # type: ignore[reportPrivateUsage]
else:
    # NOTE: During runtime just use Any placeholders
    CArgObject = Any
    CFunctionType = Any

    class CPointer[T]:
        pass
