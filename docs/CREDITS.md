# Credits

## Design

**Design inspired by [ChillPill-Shell](https://github.com/LUCKYS1NGHH/ChillPill-Shell)
by LUCKYS1NGHH.**

ChillPill-Shell is GPLv3. **No code and no assets from it are used here.** Its
QML would be meaningless on Windows anyway; what was taken is factual design
data — the morph size table, colour values, animation curves and durations, and
the configuration key names. Those are facts and ideas, not copyrightable
expression, and they are reproduced openly in [SPEC.md](SPEC.md) so anyone can
check what was and was not carried over.

Specifically **not** used:

* `screenshots/*.webp`
* `share/notification.wav` — no notification sound ships with this project
* `share/logo.png` — the tray icon is drawn at runtime in `shell/app.py`

### On the name

"ChillPill-Win" is used pending the original author's agreement. That
conversation has not happened yet. If the name is not welcome, the project
renames — **Lozenge** and **Capsule** are the alternatives held in reserve, and
nothing in the codebase depends on the name beyond strings in `pyproject.toml`,
the tray tooltip, the pipe name and the config directory.

## Code

**[yasb](https://github.com/amnweb/yasb)** by amnweb, MIT licensed. Its Win32
plumbing is vendored under `vendor/win32/` — see [NOTICE](../NOTICE) and
[vendor/README.md](../vendor/README.md) for exactly which files, at which
revision, and what was changed (import paths only).

yasb's service layer was additionally read as documentation for the harder
Windows APIs — media transport controls, the notification listener, audio
endpoint callbacks, DDC/CI brightness, WLAN enumeration. Those parts were
reimplemented here rather than copied, because taking them wholesale would have
dragged in yasb's widget and settings abstractions.

## Everything else

| | |
| --- | --- |
| [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) | GPLv3 / commercial |
| [pydantic](https://docs.pydantic.dev/) | MIT |
| [pycaw](https://github.com/AndreMiras/pycaw) | MIT |
| [pyvda](https://github.com/Ciantic/VirtualDesktopAccessor) bindings | MIT |
| [comtypes](https://github.com/enthought/comtypes), [pywin32](https://github.com/mhammond/pywin32) | MIT / PSF |
| [Open-Meteo](https://open-meteo.com/) | weather data, CC-BY 4.0, no API key |
| [Flow Launcher](https://github.com/Flow-Launcher/Flow.Launcher) | MIT — optional integration only |

**A note on PyQt6:** it is GPLv3 unless you hold a Riverbank commercial
licence. This project's own source is MIT, but a distributed binary that bundles
PyQt6 is a combined work and inherits GPLv3 obligations. That affects anyone
shipping a packaged `.exe`, not anyone running from source. PySide6 (LGPL) would
be the swap if that ever matters; nothing here depends on PyQt-specific
behaviour beyond `pyqtProperty` and `pyqtSignal` spellings.
