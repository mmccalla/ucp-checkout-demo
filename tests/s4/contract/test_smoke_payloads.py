"""AC-57: CI validates the UCP payloads of the smoke flow against the pinned 2026-04-08 schemas.

The flow is the smoke path: Create, Update, Complete, Get, and a second checkout for Cancel.
Each request body and each response body is checked. The schemas are the local pinned copies
(`contracts/`, UCP 2026-04-08 at 9c9d6fc) and the composed schemas (`contracts/composed`). The
instrument is checked against the Google Pay schema (com.google.pay 2026-01-23). A check that
sees no payload fails (no empty PASS).
"""

from __future__ import annotations

import json
from typing import Any

from tests.evidence import evidence_dir
from tests.s2.conftest import Pair, create_body
from tests.s4.conftest import TOKEN, complete_body, handler_id, instrument, pair, ready  # noqa: F401
from ucp_core import composed
from ucp_core.constants import GPAY_INSTRUMENT_SCHEMA, UCP_VERSION
from ucp_core.schema_registry import SchemaRegistry

EVIDENCE = evidence_dir("S4", "ac57")


def test_ac57_smoke_payloads_validate_against_pinned_schemas(pair: Pair) -> None:  # noqa: F811
    registry = SchemaRegistry.load()
    checked: list[dict[str, Any]] = []

    def check(label: str, name: str, payload: Any) -> None:
        problems = [f"{p.path}: {p.message}" for p in composed.problems(name, payload)]
        checked.append({"payload": label, "schema": name, "problems": problems})
        assert problems == [], (label, problems)

    c0 = pair.client.create(create_body())
    check("create request", "checkout.create_request", c0.request_body)
    check("create response", "checkout.read_response", c0.body)
    c = ready(pair)  # an Update inside: its response is checked by the client (AC-93 path)
    check("ready response", "checkout.read_response", c)
    assert c["ucp"]["version"] == UCP_VERSION  # the pinned version

    inst = instrument(handler_id(c))
    issues = registry.validate(inst, GPAY_INSTRUMENT_SCHEMA)
    checked.append(
        {"payload": "complete instrument", "schema": GPAY_INSTRUMENT_SCHEMA, "problems": issues}
    )
    assert issues == []
    done = pair.client.complete(c["id"], complete_body(handler_id(c)), c.get("expires_at"))
    assert done.body["status"] == "completed", done.body
    check("complete response", "checkout.read_response", done.body)
    check("get response", "checkout.read_response", pair.client.get(c["id"]).body)

    second = pair.client.create(create_body()).body
    cancelled = pair.client.cancel(second["id"])
    assert cancelled.body["status"] == "canceled", cancelled.body
    check("cancel response", "checkout.read_response", cancelled.body)

    assert len(checked) >= 7 and all(not x["problems"] for x in checked)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ac57-smoke-payloads.json").write_text(
        json.dumps({"ucp_version": UCP_VERSION, "checked": checked}, indent=2, default=str) + "\n"
    )
