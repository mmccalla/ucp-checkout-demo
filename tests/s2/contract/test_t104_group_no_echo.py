"""Spec v1.1.4 T-104 (ACCEPTED) and patch P14: client-sent group `omit` fields.

The Business accepts an Update with `groups[].line_item_ids` or `groups[].options`. It ignores
the client value and never echoes it. The log has the field path, never the value.
Sources: fulfillment.md line 29 ("business-generated packages") and fulfillment_group.json
lines 19 and 25 (`"ucp_request": "omit"`) at UCP 9c9d6fc.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from tests.s2.conftest import Pair, create_body

CLIENT_LI = "CLIENT-LINE-ITEM-7f3a"
CLIENT_OPT = "client-option-91bd"
CLIENT_TITLE = "CLIENT-TITLE-55e0"


def _update(c: dict[str, Any], group_extra: dict[str, Any]) -> dict[str, Any]:
    m = c["fulfillment"]["methods"][0]
    group = {"id": m["groups"][0]["id"], "selected_option_id": "gb-standard"} | group_extra
    return {
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
                    "groups": [group],
                }
            ]
        },
    }


@pytest.mark.parametrize(
    "extra",
    [
        {"line_item_ids": [CLIENT_LI]},
        {"options": [{"id": CLIENT_OPT, "title": CLIENT_TITLE, "totals": []}]},
        {
            "line_item_ids": [CLIENT_LI],
            "options": [{"id": CLIENT_OPT, "title": CLIENT_TITLE, "totals": []}],
        },
    ],
    ids=["line_item_ids", "options", "both"],
)
def test_t104_no_echo_and_path_only_log(
    pair: Pair, caplog: pytest.LogCaptureFixture, extra: dict[str, Any]
) -> None:
    c = pair.client.create(create_body()).body
    caplog.set_level(logging.WARNING)
    r = pair.client.update(c["id"], _update(c, extra))
    assert r.status == 200, r.body
    text = json.dumps(r.body)
    # (i) the response never has the client-sent values
    for value in (CLIENT_LI, CLIENT_OPT, CLIENT_TITLE):
        assert value not in text
    group = r.body["fulfillment"]["methods"][0]["groups"][0]
    assert group["line_item_ids"] == [c["line_items"][0]["id"]]
    assert {o["id"] for o in group["options"]} == {"gb-standard"}
    g = pair.client.get(c["id"]).body
    for value in (CLIENT_LI, CLIENT_OPT, CLIENT_TITLE):
        assert value not in json.dumps(g)
    # (ii) the log has the field path, never the value
    logs = "\n".join(rec.getMessage() for rec in caplog.records)
    for field in extra:
        assert f"$.fulfillment.methods[0].groups[0].{field}" in logs
    for value in (CLIENT_LI, CLIENT_OPT, CLIENT_TITLE):
        assert value not in logs
    for f in (pair.tmp / "business.jsonl", pair.tmp / "platform.jsonl"):
        if f.exists():
            for value in (CLIENT_LI, CLIENT_OPT, CLIENT_TITLE):
                assert value not in f.read_text()
