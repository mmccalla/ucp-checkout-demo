"""AC-118 and T-116: the named G1 exception for the refusal list in the schema registry.

G1 exempts a string only if it is a whole string constant, exactly the `latest` or the `draft`
alias, inside the tuple or list named `FORBIDDEN` in `libs/ucp_core/schema_registry.py`, and the
number of exempt strings is 2. Each test builds a small tree in `tmp_path`.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

import pytest
from ucp_core import schema_registry as sr
from ucp_core.constants import ROOT as REPO_ROOT

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "gates"))

import g1  # noqa: E402

REGISTRY = "libs/ucp_core/schema_registry.py"
LATEST = "https://ucp.dev/latest/"
DRAFT = "https://ucp.dev/draft/"
MARK = "g1-allow-unpinned"
AUG = "https://ucp.dev/" + "2026-08-25" + "/specification/"  # built here: G1 scans this file


def tree(tmp: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    (tmp / "pins").mkdir()
    shutil.copy(ROOT / "pins" / "PINS.toml", tmp / "pins" / "PINS.toml")
    shutil.copy(ROOT / "pyproject.toml", tmp / "pyproject.toml")
    for rel, body in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return tmp


def forbidden(*items: str) -> str:
    body = "".join(f'    "{i}",\n' for i in items)
    return f"FORBIDDEN = (\n{body})\n"


def run(tmp: pathlib.Path, files: dict[str, str]) -> list[str]:
    return g1.check_pins(tree(tmp, files), expected_marks=0)


def test_real_tree_forbidden_has_2_exempt_lines_and_g1_passes() -> None:
    assert g1.check_pins(ROOT) == []
    exempt = g1.alias_exemptions(ROOT)
    assert len(exempt) == g1.ALIAS_REFUSAL_COUNT == 2
    assert all(e.startswith(REGISTRY + ":") for e in exempt)
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "gates" / "g1.py"),
            "--root",
            str(ROOT),
            "--skip-tools",
        ],
        capture_output=True,
        text=True,
    )
    assert r.stdout.count("EXEMPT (T-116, alias check only)") == 2


def test_same_strings_in_another_file_fail(tmp_path: pathlib.Path) -> None:
    files = {REGISTRY: forbidden(LATEST, DRAFT), "app/other.py": forbidden(LATEST, DRAFT)}
    got = run(tmp_path, files)
    assert any(e.startswith("app/other.py:2:") and "alias is not pinned" in e for e in got)
    assert any(e.startswith("app/other.py:3:") and "alias is not pinned" in e for e in got)


def test_strings_outside_forbidden_fail(tmp_path: pathlib.Path) -> None:
    body = f'OTHER = (\n    "{LATEST}",\n    "{DRAFT}",\n)\n'
    got = run(tmp_path, {REGISTRY: body})
    assert any("alias is not pinned" in e for e in got)
    assert any("alias exception (T-116) covers 0 strings" in e for e in got)


def test_third_alias_string_in_forbidden_fails(tmp_path: pathlib.Path) -> None:
    got = run(tmp_path, {REGISTRY: forbidden(LATEST, DRAFT, LATEST)})
    assert any("covers 3 strings" in e and "expected number is 2" in e for e in got)


def test_one_string_removed_from_forbidden_fails(tmp_path: pathlib.Path) -> None:
    got = run(tmp_path, {REGISTRY: forbidden(LATEST)})
    assert any("covers 1 strings" in e and "expected number is 2" in e for e in got)


def test_longer_url_in_forbidden_fails(tmp_path: pathlib.Path) -> None:
    got = run(tmp_path, {REGISTRY: forbidden(LATEST, DRAFT, LATEST + "schemas/x.json")})
    assert any(e.startswith(f"{REGISTRY}:4:") and "alias is not pinned" in e for e in got)


def test_wrong_github_commit_in_forbidden_still_fails(tmp_path: pathlib.Path) -> None:
    bad = "https://github.com/Universal-Commerce-Protocol/" + "ucp/blob/deadbee/x.md"  # built here
    got = run(tmp_path, {REGISTRY: forbidden(LATEST, DRAFT, bad)})
    assert any(e.startswith(f"{REGISTRY}:4:") and "is not the pin" in e for e in got)
    assert not any("alias" in e for e in got)


def test_marker_on_exempt_line_fails(tmp_path: pathlib.Path) -> None:
    body = f'FORBIDDEN = (\n    "{LATEST}",  # AC-44 {AUG} {MARK}\n    "{DRAFT}",\n)\n'
    got = g1.check_pins(tree(tmp_path, {REGISTRY: body}), expected_marks=0)
    assert any(f"{REGISTRY}:2:" in e and "alias is not pinned" in e for e in got)
    assert any("covers 1 strings" in e for e in got)
    assert any("the marker" in e and "lines in .py files" in e for e in got)


def test_unparsable_registry_fails(tmp_path: pathlib.Path) -> None:
    got = run(tmp_path, {REGISTRY: 'FORBIDDEN = (\n    "x",\n'})
    assert any(f"{REGISTRY}: cannot parse the file" in e for e in got)


# --- T-116 review of 28 Oct 2026: FORBIDDEN holds 3 strings; the list is used ---

THIRD = "https://ucp.dev/schemas/"


def test_forbidden_holds_the_2_exempt_aliases_and_one_other_string() -> None:
    assert sr.FORBIDDEN[:2] == g1.ALIAS_STRINGS
    assert sr.FORBIDDEN[2] == THIRD
    assert len(sr.FORBIDDEN) == 3


def test_third_string_is_not_an_alias_for_g1_and_is_not_exempt(tmp_path: pathlib.Path) -> None:
    """G1 does not flag the third string (no date, `latest` or `draft` after `ucp.dev/`)."""
    assert g1.UCP_URL_RE.findall(THIRD) == []
    files = {REGISTRY: forbidden(LATEST, DRAFT, THIRD)}
    assert run(tmp_path, files) == []  # no error: not flagged, so it needs no exemption
    exempt, errs = g1.alias_exempt_lines(pathlib.Path(REGISTRY), files[REGISTRY])
    assert exempt == {2, 3} and errs == []  # the third string (line 4) is not exempt


def _registry_tree(tmp: pathlib.Path, new_id: str) -> pathlib.Path:
    shutil.copytree(REPO_ROOT / "contracts", tmp / "contracts")
    shutil.copytree(REPO_ROOT / "pins", tmp / "pins")
    rel = "ucp-schemas/shopping/types/card_payment_instrument.json"
    p = tmp / "contracts" / rel
    doc = json.loads(p.read_text())
    doc["$id"] = new_id
    p.write_text(json.dumps(doc))
    man = tmp / "pins" / "schema-manifest.sha256"
    rows = sr.read_manifest(man)
    rows[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    man.write_text("".join(f"{d}  {r}\n" for r, d in rows.items()))
    return tmp


@pytest.mark.parametrize("alias", g1.ALIAS_STRINGS)
def test_registry_refuses_a_schema_id_that_starts_with_each_alias(
    tmp_path: pathlib.Path, alias: str
) -> None:
    root = _registry_tree(tmp_path, alias + "schemas/shopping/types/card_payment_instrument.json")
    with pytest.raises(sr.RegistryError, match="forbidden"):
        sr.SchemaRegistry.load(root)


@pytest.mark.parametrize("alias", g1.ALIAS_STRINGS)
def test_registry_refuses_a_schema_url_and_a_document_ref_with_each_alias(alias: str) -> None:
    reg = sr.SchemaRegistry.load()
    with pytest.raises(sr.RegistryError, match="forbidden"):
        reg.validator(alias + "schemas/shopping/checkout.json")
    with pytest.raises(sr.RegistryError, match="forbidden"):
        reg.validate_document({}, {"$ref": alias + "schemas/shopping/checkout.json"})


@pytest.mark.parametrize("alias", g1.ALIAS_STRINGS)
def test_the_refusal_comes_from_the_list(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, alias: str
) -> None:
    """Proof that the list is used: with the alias removed from FORBIDDEN, the message changes."""
    root = _registry_tree(tmp_path, alias + "schemas/shopping/types/card_payment_instrument.json")
    monkeypatch.setattr(sr, "FORBIDDEN", tuple(x for x in sr.FORBIDDEN if x != alias))
    with pytest.raises(sr.RegistryError) as err:
        sr.SchemaRegistry.load(root)
    assert "forbidden" not in str(err.value)
