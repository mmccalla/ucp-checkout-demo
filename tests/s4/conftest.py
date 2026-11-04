"""S4 fixtures: the S2 pair (Business + mock PSP in process) and a checkout in ready_for_complete."""

from __future__ import annotations

import pathlib
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from tests.s2.conftest import Pair, create_body, make_pair

TOKEN = "examplePaymentMethodToken"  # Google's documented example token (PaymentData example)


@pytest.fixture
def pair(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Pair]:
    yield from make_pair(tmp_path, monkeypatch)


def ready(pair: Pair) -> dict[str, Any]:
    c = pair.client.create(create_body()).body
    m = c["fulfillment"]["methods"][0]
    upd = {
        "line_items": [
            {"id": c["line_items"][0]["id"], "item": {"id": "demo_tshirt"}, "quantity": 1}
        ],
        "buyer": {"email": "buyer@example.com", "first_name": "Test", "last_name": "Buyer"},
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
    r = pair.client.update(c["id"], upd)
    assert r.status == 200 and r.body["status"] == "ready_for_complete", r.body
    return dict(r.body)


def handler_id(checkout: dict[str, Any]) -> str:
    return str(checkout["ucp"]["payment_handlers"]["com.google.pay"][0]["id"])


def instrument(hid: str, token: str = TOKEN) -> dict[str, Any]:
    """The M7 instrument shape (platform_app.pay.instrument.from_payment_data)."""
    return {
        "id": f"instr_{uuid.uuid4().hex[:12]}",
        "handler_id": hid,
        "type": "card",
        "selected": True,
        "display": {"brand": "VISA", "last_digits": "1234", "description": "Visa •••• 1234"},
        "credential": {"type": "PAYMENT_GATEWAY", "token": token},
    }


def complete_body(hid: str, token: str = TOKEN) -> dict[str, Any]:
    return {"payment": {"instruments": [instrument(hid, token)]}}
