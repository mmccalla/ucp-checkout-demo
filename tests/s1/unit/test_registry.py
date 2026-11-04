"""AC-86, AC-87, AC-105 (TC-MV1 to TC-MV7, input-data D.1.2): the offline validator registry."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import shutil
from typing import Any

import pytest
from referencing.exceptions import Unresolvable
from ucp_core.constants import GPAY_INSTRUMENT_SCHEMA, ROOT, UCP_SCHEMA_BASE
from ucp_core.schema_registry import (
    DRAFT,
    RegistryError,
    SchemaRegistry,
    read_manifest,
)

UCP_CARD = UCP_SCHEMA_BASE + "shopping/types/card_payment_instrument.json"
BASE: dict[str, Any] = {
    "id": "instr_1",
    "type": "card",
    "handler_id": "gpay_demo_test_01",
    "display": {"brand": "VISA", "last_digits": "1111"},
    "credential": {"type": "PAYMENT_GATEWAY", "token": "opaque-test-token"},
}


def variant(**changes: Any) -> dict[str, Any]:
    d = copy.deepcopy(BASE)
    for k, v in changes.items():
        obj = d
        *parents, last = k.split("__")
        for p in parents:
            obj = obj[p]
        if v is None:
            obj.pop(last)
        else:
            obj[last] = v
    return d


CASES: dict[str, tuple[dict[str, Any], bool, bool | None]] = {  # (instance, Google ok, UCP ok)
    "TC-MV1": (variant(), True, True),
    "TC-MV2": (variant(display__brand="visa"), False, True),
    "TC-MV3": (variant(handler_id=None), False, False),
    "TC-MV4": (variant(display__last_digits=None), False, True),
    "TC-MV7": (variant(credential__type="TOKEN"), False, None),  # D.1.2 gives no UCP result
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_ac105_mixed_version_cases(reg: SchemaRegistry, case: str) -> None:
    inst, google_ok, ucp_ok = CASES[case]
    assert (reg.validate(inst, GPAY_INSTRUMENT_SCHEMA) == []) is google_ok
    if ucp_ok is not None:
        assert (reg.validate(inst, UCP_CARD) == []) is ucp_ok


def test_ac86_all_pinned_files_are_draft_2020_12() -> None:
    manifest = read_manifest(ROOT / "pins/schema-manifest.sha256")
    assert len(manifest) == 81
    for rel in manifest:
        assert json.loads((ROOT / "contracts" / rel).read_text())["$schema"] == DRAFT


@pytest.mark.parametrize("alias", ["latest", "draft"])
def test_ac87_alias_urls_are_refused(reg: SchemaRegistry, alias: str) -> None:
    with pytest.raises(RegistryError):
        reg.validator(f"https://ucp.dev/{alias}/schemas/shopping/checkout.json")


def test_ac87_unknown_ref_is_not_fetched(reg: SchemaRegistry) -> None:
    with pytest.raises(Unresolvable):
        reg.validate({}, "https://ucp.dev/2026-04-08/schemas/shopping/not_pinned.json")


def _copy_tree(tmp: pathlib.Path) -> pathlib.Path:
    shutil.copytree(ROOT / "contracts", tmp / "contracts")
    shutil.copytree(ROOT / "pins", tmp / "pins")
    return tmp


def test_tc_mv5_changed_file_stops_the_load(tmp_path: pathlib.Path) -> None:
    root = _copy_tree(tmp_path)
    p = root / "contracts/ucp-schemas-2026-01-23/shopping/types/payment_instrument.json"
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(RegistryError, match="TC-MV5"):
        SchemaRegistry.load(root)


def test_tc_mv5_2026_01_23_ref_mapped_to_2026_04_08_file_stops(tmp_path: pathlib.Path) -> None:
    root = _copy_tree(tmp_path)
    src = root / "contracts/ucp-schemas/shopping/types/payment_instrument.json"
    dst = root / "contracts/ucp-schemas-2026-01-23/shopping/types/payment_instrument.json"
    dst.write_bytes(src.read_bytes())
    man = root / "pins/schema-manifest.sha256"
    rel = "ucp-schemas-2026-01-23/shopping/types/payment_instrument.json"
    rows = read_manifest(man)
    rows[rel] = hashlib.sha256(dst.read_bytes()).hexdigest()
    man.write_text("".join(f"{d}  {r}\n" for r, d in rows.items()))
    with pytest.raises(RegistryError, match="TC-MV5"):
        SchemaRegistry.load(root)


def test_tc_mv6_unversioned_git_copy_stops_the_load(tmp_path: pathlib.Path) -> None:
    root = _copy_tree(tmp_path)
    p = root / "contracts/ucp-schemas/shopping/types/amount.json"
    doc = json.loads(p.read_text())
    doc["$id"] = "https://ucp.dev/schemas/shopping/types/amount.json"  # Git copy $id
    p.write_text(json.dumps(doc))
    man = root / "pins/schema-manifest.sha256"
    rows = read_manifest(man)
    rows["ucp-schemas/shopping/types/amount.json"] = hashlib.sha256(p.read_bytes()).hexdigest()
    man.write_text("".join(f"{d}  {r}\n" for r, d in rows.items()))
    with pytest.raises(RegistryError, match="TC-MV6"):
        SchemaRegistry.load(root)
