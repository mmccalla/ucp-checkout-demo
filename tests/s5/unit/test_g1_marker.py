"""AC-118 clauses 2 to 4 (T-108): the scoped G1 marker `g1-allow-unpinned`.

Clause 2: the marker is allowed only in a `#` comment on a `.py` line outside tools/gates/, and the
same comment cites a UCP 2026-08-25 URL and `AC-44` or `AC-45`. It skips only the `ucp.dev` version
check. Clause 3: any other marker fails. Clause 4: the number of marked lines is 3.
Each test builds a small tree in `tmp_path`.
"""

from __future__ import annotations

import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "gates"))

import g1  # noqa: E402

MARK = "g1-allow-unpinned"
AUG = "https://ucp.dev/" + "2026-08-25" + "/specification/shopping/checkout/"
OK_LINE = f"# AC-44 source: {AUG}  # {MARK}\n"
GOOD_SHA = "9c9d6fc"  # replaced below by the real pin


def tree(tmp: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    (tmp / "pins").mkdir()
    shutil.copy(ROOT / "pins" / "PINS.toml", tmp / "pins" / "PINS.toml")
    shutil.copy(ROOT / "pyproject.toml", tmp / "pyproject.toml")
    for rel, body in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return tmp


def pins(root: pathlib.Path, expected_marks: int = g1.EXPECTED_MARKS) -> list[str]:
    """Check a small tree: it has no schema registry, so the alias count is 0 (T-116)."""
    return g1.check_pins(root, expected_marks=expected_marks, expected_aliases=0)


def errors(tmp: pathlib.Path, files: dict[str, str], marks: int = 1) -> list[str]:
    return pins(tree(tmp, files), expected_marks=marks)


def test_valid_marker_passes(tmp_path: pathlib.Path) -> None:
    assert errors(tmp_path, {"app/a.py": OK_LINE}) == []


def test_valid_marker_with_ac45_passes(tmp_path: pathlib.Path) -> None:
    line = f"# AC-45 source: {AUG}  # {MARK}\n"
    assert errors(tmp_path, {"app/a.py": line}) == []


def test_august_url_without_marker_fails(tmp_path: pathlib.Path) -> None:
    got = errors(tmp_path, {"app/a.py": f"# AC-44 {AUG}\n"}, marks=0)
    assert any("app/a.py:1" in e and "not a pinned UCP version" in e for e in got)


def test_marker_without_url_fails_with_file_and_line(tmp_path: pathlib.Path) -> None:
    got = errors(tmp_path, {"app/a.py": f"x = 1\ny = 2  # AC-44 {MARK}\n"})
    assert any(e.startswith("app/a.py:2:") and "URL" in e for e in got)


def test_marker_without_ac_id_fails(tmp_path: pathlib.Path) -> None:
    got = errors(tmp_path, {"app/a.py": f"# source: {AUG}  # {MARK}\n"})
    assert any(e.startswith("app/a.py:1:") and "AC-44 or AC-45" in e for e in got)
    assert any("not a pinned UCP version" in e for e in got)  # the line is not skipped


def test_marker_with_other_ac_id_fails(tmp_path: pathlib.Path) -> None:
    got = errors(tmp_path, {"app/a.py": f"# AC-46 {AUG}  # {MARK}\n"})
    assert any("AC-44 or AC-45" in e for e in got)


def test_ac_id_in_the_url_or_a_longer_id_does_not_count(tmp_path: pathlib.Path) -> None:
    got = errors(tmp_path, {"app/a.py": f"# AC-445 {AUG}  # {MARK}\n"})
    assert any("AC-44 or AC-45" in e for e in got)


def test_marker_in_a_markdown_file_fails(tmp_path: pathlib.Path) -> None:
    got = errors(tmp_path, {"docs/a.md": f"text {AUG} AC-44 # {MARK}\n"}, marks=0)
    assert any(e.startswith("docs/a.md:1:") and "only in .py files" in e for e in got)
    assert any("not a pinned UCP version" in e for e in got)


def test_marker_in_a_toml_file_fails(tmp_path: pathlib.Path) -> None:
    got = errors(tmp_path, {"cfg/a.toml": f"k = 1  # AC-44 {AUG} # {MARK}\n"}, marks=0)
    assert any(e.startswith("cfg/a.toml:1:") for e in got)


def test_marker_under_tools_gates_fails(tmp_path: pathlib.Path) -> None:
    got = errors(tmp_path, {"tools/gates/x.py": OK_LINE}, marks=0)
    assert any(e.startswith("tools/gates/x.py:1:") and "outside tools/gates/" in e for e in got)


def test_marker_in_a_tests_py_file_is_allowed(tmp_path: pathlib.Path) -> None:
    assert errors(tmp_path, {"tests/t.py": OK_LINE}) == []


def test_marker_text_in_a_docstring_is_not_a_use(tmp_path: pathlib.Path) -> None:
    body = f'"""Prose that names {MARK} here, with no comment."""\n'
    assert errors(tmp_path, {"app/a.py": body}, marks=0) == []


def test_marker_in_a_string_is_not_a_use_and_does_not_skip(tmp_path: pathlib.Path) -> None:
    body = f'x = "{AUG} AC-44 # {MARK}"\n'
    got = errors(tmp_path, {"app/a.py": body}, marks=0)
    assert any("not a pinned UCP version" in e for e in got)


def test_marker_skips_only_the_version_check_github(tmp_path: pathlib.Path) -> None:
    bad = "https://github.com/Universal-Commerce-Protocol/ucp/blob/" + "0" * 40 + "/README.md"
    line = f"# AC-44 {AUG} {bad}  # {MARK}\n"
    got = errors(tmp_path, {"app/a.py": line})
    assert any("not the pin" in e for e in got)


def test_marker_skips_only_the_version_check_alias(tmp_path: pathlib.Path) -> None:
    alias = "https://ucp.dev/" + "latest" + "/schemas/ucp.json"
    line = f"# AC-44 {AUG} {alias}  # {MARK}\n"
    got = errors(tmp_path, {"app/a.py": line})
    assert any("alias is not pinned" in e for e in got)


def test_marker_skips_only_the_august_version(tmp_path: pathlib.Path) -> None:
    other = "https://ucp.dev/" + "2026-09-30" + "/specification/"
    line = f"# AC-44 {AUG} {other}  # {MARK}\n"
    got = errors(tmp_path, {"app/a.py": line})
    assert any("2026-09-30" in e and "not a pinned UCP version" in e for e in got)


def test_marker_skips_only_the_version_check_google_pay(tmp_path: pathlib.Path) -> None:
    line = f"# AC-44 {AUG} com.google.pay 2099-01-01  # {MARK}\n"
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    pay_bad = pins(tree(one, {"app/a.py": line}), expected_marks=1)
    plain = pins(tree(two, {"app/a.py": "# com.google.pay 2099-01-01\n"}), expected_marks=0)
    # the Google Pay result of the marked line equals the result of the same text without a marker
    assert [e.split(": ", 1)[1] for e in pay_bad if "google" in e.lower()] == [
        e.split(": ", 1)[1] for e in plain if "google" in e.lower()
    ]


def test_count_not_3_fails() -> None:
    assert g1.EXPECTED_MARKS == 3


def test_count_below_expected_fails(tmp_path: pathlib.Path) -> None:
    got = errors(tmp_path, {"app/a.py": OK_LINE}, marks=3)
    assert any("expected number is 3" in e and "on 1 lines" in e for e in got)


def test_count_above_expected_fails(tmp_path: pathlib.Path) -> None:
    got = errors(tmp_path, {"app/a.py": OK_LINE * 2}, marks=1)
    assert any("on 2 lines" in e for e in got)


def test_count_equal_passes(tmp_path: pathlib.Path) -> None:
    assert errors(tmp_path, {"app/a.py": OK_LINE * 3}, marks=3) == []


def test_the_real_tree_has_3_valid_markers() -> None:
    assert g1.check_pins(ROOT) == []
    n = 0
    for p in g1.files(ROOT):
        rel = p.relative_to(ROOT)
        uses = g1.marker_uses(rel, g1.text(p))
        valid, errs, counted = g1.check_marker(rel, uses)
        assert errs == [], rel
        n += counted
    assert n == 3
