"""G4 contract, S2: check recorded payloads with the pinned `ucp-schema validate` (1.4.1).

The REST payloads carry no capability schema URLs. The test adds the `ucp` block of
`contracts/composed/self-describing.json` (the Business profile capabilities, as in
`tools/contracts/compose.py`), so that `ucp-schema` can infer the composed schema.
AC-89, AC-94, AC-104: a bad value fails. AC-13, AC-109: the recorded payloads pass.
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import shutil
import subprocess
from typing import Any

from ucp_core.constants import ROOT

from tests.s2.conftest import Pair, create_body

BIN = os.environ.get("UCP_SCHEMA_BIN") or shutil.which("ucp-schema") or "ucp-schema"
BASE = [
    "--schema-local-base",
    "contracts/ucp-schemas",
    "--schema-remote-base",
    "https://ucp.dev/2026-04-08/schemas",
]
SELF = json.loads((ROOT / "contracts" / "composed" / "self-describing.json").read_text())
EVIDENCE = os.environ.get("S2_EVIDENCE")


def validate(
    tmp: pathlib.Path, name: str, payload: dict[str, Any], direction: str, op: str
) -> dict[str, Any]:
    p = copy.deepcopy(payload)
    ucp = p.setdefault("ucp", {})
    ucp["version"] = SELF["ucp"]["version"]
    ucp["capabilities"] = SELF["ucp"]["capabilities"]
    f = tmp / f"{name}.json"
    f.write_text(json.dumps(p, indent=2))
    out = subprocess.run(
        [BIN, "validate", str(f), f"--{direction}", "--op", op, *BASE, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    result: dict[str, Any] = json.loads(out.stdout)
    result["rc"] = out.returncode
    if EVIDENCE:
        d = ROOT / EVIDENCE / "ucp-schema"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.payload.json").write_text(json.dumps(payload, indent=2) + "\n")
        (d / f"{name}.result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def test_recorded_create_and_update_pass(pair: Pair, tmp_path: pathlib.Path) -> None:
    body = create_body()
    r = pair.client.create(body)
    assert validate(tmp_path, "create.request", body, "request", "create")["valid"] is True
    res = validate(tmp_path, "create.response", r.body, "response", "create")
    assert res["valid"] is True, res
    c = r.body
    m = c["fulfillment"]["methods"][0]
    upd = {
        "line_items": [
            {"id": c["line_items"][0]["id"], "item": {"id": "demo_tshirt"}, "quantity": 1}
        ],
        "fulfillment": {
            "methods": [
                {
                    "id": m["id"],
                    "type": "shipping",
                    "line_item_ids": m["line_item_ids"],
                    "destinations": m["destinations"],
                    "selected_destination_id": "d1",
                    "groups": [{"id": m["groups"][0]["id"], "selected_option_id": "gb-standard"}],
                }
            ]
        },
    }
    assert validate(tmp_path, "update.request", upd, "request", "update")["valid"] is True
    r2 = pair.client.update(c["id"], upd)
    res2 = validate(tmp_path, "update.response", r2.body, "response", "update")
    assert res2["valid"] is True, res2


def test_bad_payloads_fail(tmp_path: pathlib.Path) -> None:
    drone = create_body()
    drone["fulfillment"]["methods"][0]["type"] = "drone"
    assert validate(tmp_path, "bad.enum", drone, "request", "create")["valid"] is False
    upd_no_ids = {
        "line_items": [{"id": "x", "item": {"id": "demo_tshirt"}, "quantity": 1}],
        "fulfillment": {"methods": [{"id": "m", "type": "shipping"}]},
    }
    res = validate(tmp_path, "bad.update-no-line_item_ids", upd_no_ids, "request", "update")
    assert res["valid"] is False
