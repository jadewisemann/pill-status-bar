"""Re-import yasb's Win32 plumbing into vendor/win32/.

    git clone --depth 1 https://github.com/amnweb/yasb /tmp/yasb
    python tools/vendorize.py --source /tmp/yasb/src/core/utils/win32

Copies the file list below, stamps each file with its provenance and rewrites
yasb-internal import paths.  Nothing else is changed -- see vendor/README.md.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEST = REPO_ROOT / "vendor" / "win32"

#: Upstream-relative paths to import, from spec §4.1.  Two files from that list
#: are deliberately absent:
#:
#: * `utils.py` -- a hand-trimmed extract, not a copy, so re-running this script
#:   must not overwrite it
#: * `icon_extractor.py` -- upstream's copy does not parse under Python 3 (it
#:   contains a Python 2 `except A, B:` clause).  Its job is done by
#:   `shell/platform/icons.py`, which drives the same vendored primitives.
FILES = [
    "bindings/__init__.py",
    "bindings/dwmapi.py",
    "bindings/dxva2.py",
    "bindings/gdi32.py",
    "bindings/iphlpapi.py",
    "bindings/kernel32.py",
    "bindings/ntdll.py",
    "bindings/ole32.py",
    "bindings/pdh.py",
    "bindings/powrprof.py",
    "bindings/psapi.py",
    "bindings/setupapi.py",
    "bindings/shell32.py",
    "bindings/user32.py",
    "bindings/wlanapi.py",
    "structs.py",
    "constants.py",
    "error_check.py",
    "typecheck.py",
    "system_function.py",
    "backdrop.py",
    "app_bar.py",
    "window_actions.py",
    "hotkeys.py",
    "pe_icons.py",
    "aumid.py",
    "aumid_icons.py",
    "app_icons.py",
    "app_loader.py",
]

#: yasb import path -> ours.  Applied in order.
REWRITES = [
    ("core.utils.win32", "vendor.win32"),
    ("core.events.service", "vendor.compat.events"),
]

MARKER = "# " + "-" * 75

HEADER = (
    MARKER
    + """
# Vendored from yasb -- https://github.com/amnweb/yasb
# MIT License, Copyright (c) 2024 amnweb.  Full text: vendor/LICENSE.yasb
# Upstream path: src/core/utils/win32/{relpath}
# Upstream revision: {revision}
#
# DO NOT EDIT.  The only change applied to this file is a mechanical rewrite of
# import paths; see vendor/README.md.  Behaviour changes belong in
# shell/platform/, never here.
"""
    + MARKER
    + "\n"
)


def upstream_revision(source: pathlib.Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def rewrite(text: str) -> str:
    for old, new in REWRITES:
        text = text.replace(old, new)
    return text


def body_of(text: str) -> str:
    """The file's content with our provenance header removed."""
    return text.split(MARKER + "\n", 2)[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=pathlib.Path, help="path to yasb's src/core/utils/win32")
    parser.add_argument("--check", action="store_true", help="verify only; do not write")
    args = parser.parse_args(argv)

    source: pathlib.Path = args.source
    if not source.is_dir():
        print(f"no such directory: {source}", file=sys.stderr)
        return 1

    revision = upstream_revision(source)
    for relpath in FILES:
        origin = source / relpath
        if not origin.is_file():
            print(f"missing upstream file: {relpath}", file=sys.stderr)
            return 1
        content = HEADER.format(relpath=relpath, revision=revision) + rewrite(origin.read_text(encoding="utf-8"))
        target = DEST / relpath
        if args.check:
            if not target.is_file() or target.read_text(encoding="utf-8") != content:
                print(f"out of date: {relpath}", file=sys.stderr)
                return 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    leftovers = sorted(find_unrewritten(DEST))
    if leftovers:
        print("yasb-internal imports survived the rewrite:", *leftovers, sep="\n  ", file=sys.stderr)
        return 1

    print(f"{'checked' if args.check else 'vendored'} {len(FILES)} files from yasb@{revision[:12]}")
    return 0


def find_unrewritten(root: pathlib.Path) -> set[str]:
    """Any `core.*` reference left in a vendored file's body."""
    found: set[str] = set()
    for path in root.rglob("*.py"):
        for match in re.finditer(r"\bcore\.[a-z_.]+", body_of(path.read_text(encoding="utf-8"))):
            found.add(f"{path.relative_to(root)}: {match.group(0)}")
    return found


if __name__ == "__main__":
    raise SystemExit(main())
