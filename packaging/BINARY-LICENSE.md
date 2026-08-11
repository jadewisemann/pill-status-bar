# Licence of this binary

**This packaged build is distributed under the GNU General Public License,
version 3.** That is stricter than the project's own licence, and it is not a
choice — it follows from what is inside the zip.

## Why, when the source is MIT

ChillPill-Win's own source code is MIT (see `LICENSE`). But this build bundles
**PyQt6**, which is GPLv3 unless the distributor holds a Riverbank commercial
licence. A binary that contains both is a combined work, and the GPL's terms
govern the combination. So:

| | |
| --- | --- |
| the source in this repository | MIT — unchanged, do what you like with it |
| this `.exe` and everything in the zip beside it | GPLv3 |

Running from source (`pip install -e .`) is unaffected: nothing is being
distributed, so no combined work exists. The obligation lands on whoever ships
the packaged binary — here, the release workflow.

If that ever becomes a problem, the swap is PySide6, which is LGPLv3. Nothing
in the codebase depends on PyQt-specific behaviour beyond the `pyqtProperty`
and `pyqtSignal` spellings — see [docs/CREDITS.md](docs/CREDITS.md).

## Corresponding source

GPLv3 §6 requires the source that corresponds to this binary to be available
from the same place. It is: this build was produced by the `Release` workflow
from the tagged commit at

    https://github.com/jadewisemann/pill-status-bar

and the tag matching this build's version is that corresponding source,
together with the build recipe in `packaging/chillpill.spec` and the exact
dependency versions the workflow log records.

Third-party source:

* **PyQt6** — https://www.riverbankcomputing.com/software/pyqt/download (GPLv3)
* **Qt 6**, bundled inside PyQt6 — https://download.qt.io/ (LGPLv3). The build
  is a directory, not a single self-extracting file, so the Qt DLLs sit beside
  the executable as separate replaceable files; that is what LGPLv3 §4(d)
  asks for.
* **yasb**, vendored under `vendor/win32/` — MIT, © 2024 amnweb. Licence text
  in `vendor/LICENSE.yasb`, provenance in `NOTICE`.
* Everything else — pydantic, pycaw, comtypes, pywin32, pyvda, WMI, watchdog,
  Pillow, the WinRT projections — is MIT, BSD or PSF. `docs/CREDITS.md` lists
  each one.

## Not included

No code, images or sounds from [ChillPill-Shell](https://github.com/LUCKYS1NGHH/ChillPill-Shell)
are in this zip. The design was reimplemented from the factual spec recorded in
`docs/SPEC.md`; see `NOTICE` for the full statement.

## No warranty

As stated in section 15 of the GPL and in the MIT licence: this software comes
with no warranty. It is a desktop shell that registers an AppBar and global
hotkeys — read `docs/RISKS.md` before running it on a machine you care about.
