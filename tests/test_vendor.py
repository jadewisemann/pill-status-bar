"""Guards on the vendored tree.

These are boundary tests, not behaviour tests: vendored code cannot be
exercised off Windows, but the rules about how it is wired in can be.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor"
SHELL = REPO / "shell"


def python_files(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def imported_names(path: pathlib.Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        # vendor/win32/typecheck.py uses PEP 695 generics, so the project needs
        # Python 3.12+.  Running the suite on an older interpreter should say so
        # rather than report a spurious failure.
        pytest.skip(f"{path.name} needs a newer Python than this interpreter: {exc.msg}")
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def test_the_project_requires_a_python_the_vendored_code_parses_on() -> None:
    """PEP 695 syntax in vendor/win32/typecheck.py sets the floor at 3.12."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.12"' in pyproject


def test_vendor_tree_is_present() -> None:
    assert (VENDOR / "win32" / "bindings" / "user32.py").is_file()
    assert (VENDOR / "LICENSE.yasb").is_file()


def test_every_vendored_file_carries_its_provenance() -> None:
    """Attribution is a licence obligation, so it is a test, not a convention."""
    for path in python_files(VENDOR / "win32"):
        if path.name == "__init__.py" and path.stat().st_size == 0:
            continue
        head = path.read_text(encoding="utf-8")[:900]
        assert "amnweb/yasb" in head, f"{path} is missing its vendoring header"
        assert "vendor/LICENSE.yasb" in head, f"{path} does not point at the licence"


def test_no_yasb_internal_imports_survive() -> None:
    from tools.vendorize import find_unrewritten

    assert find_unrewritten(VENDOR / "win32") == set()


@pytest.mark.parametrize("path", python_files(VENDOR), ids=lambda p: str(p.relative_to(VENDOR)))
def test_vendor_never_imports_the_shell(path: pathlib.Path) -> None:
    """The dependency arrow points one way: shell -> vendor, never back."""
    offenders = [name for name in imported_names(path) if name == "shell" or name.startswith("shell.")]
    assert not offenders, f"{path} imports {offenders}"


def test_shell_reaches_vendor_only_through_the_platform_layer() -> None:
    """Keeping ctypes behind shell/platform is what makes the rest testable.

    `shell/modules/` is the one exception: a few modules read Win32 structures
    directly (WLAN network lists, interface counters) where wrapping them would
    add an indirection and nothing else.
    """
    allowed = {SHELL / "platform", SHELL / "modules", SHELL / "surfaces" / "launcher.py"}
    for path in python_files(SHELL):
        if any(path == entry or entry in path.parents for entry in allowed):
            continue
        offenders = [name for name in imported_names(path) if name.startswith("vendor")]
        assert not offenders, f"{path.relative_to(REPO)} should not import {offenders} directly"


def struct_names(path: pathlib.Path) -> set[str]:
    """Names of ctypes Structure/Union subclasses declared in `path`."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        pytest.skip(f"{path.name} needs a newer Python than this interpreter: {exc.msg}")
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for base in node.bases
        if (isinstance(base, ast.Attribute) and base.attr in ("Structure", "Union"))
        or (isinstance(base, ast.Name) and base.id in ("Structure", "Union"))
    }


def test_shell_never_redeclares_a_vendored_struct() -> None:
    """One Win32 struct, one definition in the process.

    `ctypes.windll.kernel32` is a process-wide singleton and argtypes are cached
    on its function objects, so whichever struct class the vendored bindings
    registered wins for everyone. A second declaration of the same struct in
    `shell/` is a *different* type as far as ctypes is concerned, and passing a
    pointer to it raises ArgumentError -- at runtime, on Windows only, in
    whichever module happens to run first.

    That cannot be caught off Windows by executing the code, but it can be read
    off the source, which is the whole point of the boundary tests.
    """
    vendored = struct_names(VENDOR / "win32" / "structs.py")
    assert vendored, "no structs found in the vendored tree; this test is not testing anything"

    for path in python_files(SHELL):
        clashes = sorted(struct_names(path) & vendored)
        assert not clashes, (
            f"{path.relative_to(REPO)} redeclares {clashes}, which vendor/win32/structs.py already "
            f"defines. Import the vendored one instead -- ctypes will not accept both."
        )
