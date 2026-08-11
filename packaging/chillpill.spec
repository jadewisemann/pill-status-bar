# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows build.

    pyinstaller --noconfirm --clean packaging/chillpill.spec

Produces `dist/ChillPill/` (onedir -- Qt starts faster from a directory than
from a self-extracting onefile, and a crash leaves a readable tree) holding two
executables built from one analysis:

    ChillPill.exe          windowed; what you actually run
    ChillPill-console.exe  same bundle with a console, so you can see the log
                           and reach the `doctor` and `ctl` subcommands

Nothing here is loaded from disk at runtime -- the tray icon is painted in
`shell/app.py` and the default config is generated in `shell/config.py` -- so
the bundle carries no data files of its own.

NOTE ON LICENSING: this bundle contains PyQt6, which is GPLv3 unless you hold a
Riverbank commercial licence.  The binary is therefore a combined work covered
by the GPL, even though this project's own source is MIT.  See
`packaging/BINARY-LICENSE.md`, which the release workflow ships inside the zip.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 -- SPECPATH is injected by PyInstaller


def _submodules(package: str) -> list[str]:
    """`collect_submodules`, but an uninstalled package is not fatal.

    Every Windows backend is optional at runtime by design; a bundle missing one
    should degrade the same way a source install does, not fail to build.
    """
    try:
        return collect_submodules(package)
    except Exception:  # noqa: BLE001 -- a build-time probe, not a runtime path
        return []


# WinRT is one distribution per namespace and the module graph cannot see all of
# them: `shell/modules/media.py` and `notifications.py` reach namespaces through
# the *types they get back* -- iterating a notification list touches
# Foundation.Collections, reading a toast's source app touches ApplicationModel
# -- so those never appear in an import statement.  Collecting the whole `winrt`
# namespace is bounded here because only the namespaces pyproject.toml lists are
# installed in the first place.
hiddenimports = _submodules("winrt")

# Imported inside functions and guarded by try/except, which the module graph
# follows, but listed anyway so a build failure is never a silent feature loss.
hiddenimports += [
    "comtypes",
    "pycaw.pycaw",
    "pyvda",
    "win32api",
    "win32con",
    "win32gui",
    "wmi",
    "PIL.Image",
    # Reached only through the frozen entry point's dispatch.
    "shell.app",
    "shell.cli",
    "shell.doctor",
]

# pyvda ships VirtualDesktopAccessor.dll as package data; without it the
# workspace indicator would fall over instead of degrading.
binaries = collect_dynamic_libs("pyvda") + collect_dynamic_libs("winrt")
datas = collect_data_files("pyvda")

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Qt modules this shell never touches -- it imports QtCore, QtGui and
    # QtWidgets and nothing else.  Excluding them is worth ~100 MB.
    excludes=[
        "PyQt6.Qt3DCore",
        "PyQt6.QtBluetooth",
        "PyQt6.QtCharts",
        "PyQt6.QtDataVisualization",
        "PyQt6.QtDesigner",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtNfc",
        "PyQt6.QtOpenGL",
        "PyQt6.QtPositioning",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuick3D",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtRemoteObjects",
        "PyQt6.QtSensors",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSql",
        "PyQt6.QtSvgWidgets",
        "PyQt6.QtTest",
        "PyQt6.QtWebChannel",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebSockets",
        # Test and build tooling that pip drags in next to the app.
        "pytest",
        "ruff",
        "tkinter",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)  # noqa: F821

# Two executables, one analysis: same code, same bundle, different subsystem.
exe_windowed = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ChillPill",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

exe_console = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ChillPill-console",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe_windowed,
    exe_console,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ChillPill",
)
