"""No test, tool or workflow file may name a path of the box (project rule of 28 Oct 2026, 22:26 GMT).

A path of the box exists on the box only. On a CI runner or in a clean clone it does not, and
a test that uses it fails. All paths come from the repository root or from environment
variables that the workflow sets. The strings are built at run time, so this file does not
contain them and does not match its own pattern.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
FORBIDDEN = ("/work" + "space", "/home/" + "box")
SCANNED = ("tests", "tools", ".github")
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv", "node_modules"}


def files() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for top in SCANNED:
        base = ROOT / top
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not SKIP_DIRS & set(path.relative_to(ROOT).parts):
                found.append(path)
    return found


def test_scan_finds_the_files() -> None:
    names = {p.relative_to(ROOT).as_posix() for p in files()}
    assert "tests/evidence.py" in names and "tools/run_local.sh" in names


def test_no_file_names_a_path_of_the_box() -> None:
    hits: list[str] = []
    for path in files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # a binary file
        for number, line in enumerate(text.splitlines(), 1):
            if any(word in line for word in FORBIDDEN):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    assert hits == [], "paths of the box found: " + ", ".join(hits)
