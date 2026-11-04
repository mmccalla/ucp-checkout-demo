"""S4 Business Complete with the mock PSP: T-105 (AC-34), AC-31 to AC-33, AC-46, AC-90, AC-97, AC-112.

Spec v1.1.4 T-105 and patch P15 (business/UPSTREAM.md). Sources at UCP 9c9d6fc:
checkout-rest.md lines 1275-1282, checkout.md 242 and 245-248, rest.openapi.json 301-317,
signatures.md 833 and 844-848.
"""

from __future__ import annotations

import json
import logging
import pathlib
import uuid
from typing import Any

import pytest

from tests.s2.conftest import Pair, create_body
from tests.s4.conftest import TOKEN, complete_body, handler_id, ready

FORBIDDEN_UPPER = ("PAYMENT_FAILED", "INSUFFICIENT_FUNDS", "FRAUD_DETECTED", "UNKNOWN_TOKEN")


def _token() -> str:
    return f"tok-{uuid.uuid4().hex}"


def _scan(root: pathlib.Path, needle: str) -> list[str]:
    hits = []
    for p in root.rglob("*"):
        if p.is_file() and needle.encode() in p.read_bytes():
            hits.append(str(p.relative_to(root)))
    return hits


def test_ac33_ac112_approve_completes_with_order_and_echo_without_credential(
    pair: Pair, tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    c = ready(pair)
    tok = _token()
    r = pair.client.complete(c["id"], complete_body(handler_id(c), tok))
    assert r.status == 200, r.body
    assert r.schema_problems == []
    b = r.body
    assert b["ucp"]["status"] == "success"
    assert b["status"] == "completed"
    assert set(b["order"]) >= {"id", "permalink_url"}
    insts = b["payment"]["instruments"]
    assert len(insts) == 1 and "credential" not in insts[0]
    assert insts[0]["handler_id"] == handler_id(c)
    # AC-112: one PSP call
    assert len(pair.psp.attempts) == 1 and pair.psp.attempts[0]["status"] == "approved"
    # "Unknown credential type" is gone (P15). The token is not in any log or file.
    assert "Unknown credential type" not in caplog.text
    assert tok not in caplog.text
    assert tok not in repr(pair.psp.attempts)
    assert _scan(tmp_path, tok) == []


def test_ac34_t105_decline_is_200_checkout_body_and_replay_no_second_psp_call(
    pair: Pair, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    c = ready(pair)
    pair.psp.outcome = "decline"
    tok = _token()
    r = pair.client.complete(c["id"], complete_body(handler_id(c), tok))
    b = r.body
    assert r.status == 200, b  # never 402, never 500
    assert r.schema_problems == []
    assert b["ucp"]["status"] == "success"  # checkout body, not error_response
    assert b["status"] == "ready_for_complete"
    assert "order" not in b
    msgs = b["messages"]
    assert len(msgs) == 1
    m = msgs[0]
    assert (m["type"], m["code"], m["severity"]) == ("error", "payment_failed", "recoverable")
    assert tok not in m["content"] and "simulated_decline" not in m["content"]
    assert not any(code in repr(b) for code in FORBIDDEN_UPPER)
    # T-105 item 5: line items, totals and fulfillment do not change.
    for k in ("line_items", "totals", "fulfillment", "currency", "buyer"):
        assert b[k] == c[k], k
    assert len(pair.psp.attempts) == 1
    # Same key + same body: the stored response, no second PSP call (signatures.md line 833).
    again = pair.client.resend(r)
    assert again.status == 200 and again.body == b
    assert len(pair.psp.attempts) == 1
    # The stored checkout is not changed: Get has no payment_failed message.
    g = pair.client.get(c["id"]).body
    assert g["status"] == "ready_for_complete"
    assert not any(x.get("code") == "payment_failed" for x in g.get("messages") or [])
    assert tok not in caplog.text and "Unknown credential type" not in caplog.text


def test_ac35_retry_with_new_token_and_new_key_completes(pair: Pair) -> None:
    c = ready(pair)
    pair.psp.outcome = "decline"
    r1 = pair.client.complete(c["id"], complete_body(handler_id(c), _token()))
    assert r1.body["status"] == "ready_for_complete"
    pair.psp.outcome = "approve"
    r2 = pair.client.complete(c["id"], complete_body(handler_id(c), _token()))
    assert r2.idempotency_key != r1.idempotency_key
    assert r2.status == 200 and r2.body["status"] == "completed", r2.body
    assert [a["status"] for a in pair.psp.attempts] == ["declined", "approved"]


def test_ac46_identical_complete_after_success_returns_stored_response_one_charge(
    pair: Pair,
) -> None:
    c = ready(pair)
    r = pair.client.complete(c["id"], complete_body(handler_id(c)))
    assert r.body["status"] == "completed"
    again = pair.client.resend(r)
    assert again.status == 200 and again.body == r.body
    assert len(pair.psp.attempts) == 1 and len(pair.psp.approved) == 1


def test_same_key_other_body_is_409(pair: Pair) -> None:
    c = ready(pair)
    pair.psp.outcome = "decline"
    r = pair.client.complete(c["id"], complete_body(handler_id(c)))
    r.request_body = complete_body(handler_id(c), _token())
    again = pair.client.resend(r)
    assert again.status == 409  # signatures.md line 834
    assert len(pair.psp.attempts) == 1


def test_t105_no_charge_when_fulfillment_is_not_valid(pair: Pair) -> None:
    c = pair.client.create(create_body()).body  # incomplete: no option selected
    hid = handler_id(c)
    r = pair.client.complete(c["id"], complete_body(hid))
    assert r.status == 400, r.body
    assert r.body["messages"][0]["code"] == "invalid_request"
    assert pair.psp.attempts == []
    assert pair.client.get(c["id"]).body["status"] != "completed"


def test_ac32_undeclared_handler_rejected_no_charge(pair: Pair) -> None:
    c = ready(pair)
    r = pair.client.complete(c["id"], complete_body("gpay_not_declared"))
    assert r.status == 400 and r.body["ucp"]["status"] == "error", r.body
    assert pair.psp.attempts == []
    assert pair.client.get(c["id"]).body["status"] == "ready_for_complete"


def test_ac90_complete_without_payment_fails(pair: Pair) -> None:
    c = ready(pair)
    bodies: list[dict[str, Any]] = [{}, {"payment": {"instruments": []}}]
    for body in bodies:
        r = pair.client.complete(c["id"], body)
        assert r.status == 400, (body, r.body)
        assert r.body["ucp"]["status"] == "error"
    assert pair.psp.attempts == []
    assert pair.client.get(c["id"]).body["status"] == "ready_for_complete"


def test_psp_unreachable_is_503_no_order(pair: Pair, monkeypatch: pytest.MonkeyPatch) -> None:
    import config as sample_config  # vendored module
    from business_app import psp_client

    monkeypatch.setattr(
        sample_config, "PAYMENT_AUTHORIZER", psp_client.make_authorizer("http://127.0.0.1:9")
    )
    c = ready(pair)
    r = pair.client.complete(c["id"], complete_body(handler_id(c)))
    assert r.status == 503 and r.body["code"] == "psp_unavailable", r.body
    assert pair.client.get(c["id"]).body["status"] == "ready_for_complete"


def test_ac97_psp_keeps_no_token(caplog: pytest.LogCaptureFixture) -> None:
    from fastapi.testclient import TestClient
    from psp_mock.main import create_app

    caplog.set_level(logging.DEBUG)
    app = create_app()
    tok = _token()
    with TestClient(app) as tc:
        body: dict[str, Any] = {
            "idempotency_key": "chk1",
            "token": tok,
            "amount": 1,
            "currency": "GBP",
        }
        r = tc.post("/charges", json=body)
        assert r.json()["status"] == "approved" and r.json()["simulated"] is True
        assert tok not in r.text
        listing = tc.get("/charges").text
        assert tok not in listing
        assert tc.post("/charges", json={"idempotency_key": "chk2"}).status_code == 400
        assert tc.put("/outcome", json={"outcome": "maybe"}).status_code == 400
    assert tok not in caplog.text
    assert tok not in repr(vars(app.state.store))


def test_order_placed_webhook_signed_once_and_none_on_decline(pair: Pair) -> None:
    """The sample signs each webhook delivery (RFC 9421). A decline sends no webhook.

    The receiver checks (AC-64 to AC-75) are in tests/s4/g6. This test checks the sender only.
    """
    c = ready(pair)
    pair.psp.outcome = "decline"
    pair.client.complete(c["id"], complete_body(handler_id(c), _token()))
    assert pair.webhooks == []
    pair.psp.outcome = "approve"
    tok = _token()
    r = pair.client.complete(c["id"], complete_body(handler_id(c), tok))
    assert r.body["status"] == "completed"
    # S4 part 1: placed, then the simulated shipped and delivered events (AC-74).
    kinds = [w.headers["x-event-type"] for w in pair.webhooks]
    assert kinds == ["order_placed", "order_shipped", "order_delivered"]
    w = pair.webhooks[0]
    assert {"signature", "signature-input", "webhook-id", "webhook-timestamp"} <= set(w.headers)
    assert tok.encode() not in w.content
    assert r.body["order"]["id"].encode() in w.content


def _brand_body(c: dict[str, Any], brand: str) -> dict[str, Any]:
    body = complete_body(handler_id(c))
    body["payment"]["instruments"][0]["display"]["brand"] = brand
    return body


def test_ac91_lowercase_brand_becomes_uppercase_and_is_logged(pair: Pair) -> None:
    """AC-91 (DATA AC-R4): `visa` becomes `VISA`, one log row, then validation passes."""
    c = ready(pair)
    r = pair.client.complete(c["id"], _brand_body(c, "visa"))
    assert r.status == 200 and r.body["status"] == "completed", r.body
    rows = [json.loads(x) for x in (pair.tmp / "business.jsonl").read_text().splitlines() if x]
    fixed = [x for x in rows if x.get("old_value")]
    assert len(fixed) == 1, fixed
    assert fixed[0]["old_value"] == "visa" and fixed[0]["new_value"] == "VISA"
    assert fixed[0]["field"] == "payment.instruments[0].display.brand"
    assert "credential" not in json.dumps(fixed[0]) and TOKEN not in json.dumps(fixed[0])


def test_ac91_uppercase_brand_has_no_log_row(pair: Pair) -> None:
    c = ready(pair)
    r = pair.client.complete(c["id"], _brand_body(c, "VISA"))
    assert r.status == 200
    text = (pair.tmp / "business.jsonl").read_text()
    assert "old_value" not in text


def test_ac91_brand_not_in_enum_fails_validation_no_charge(pair: Pair) -> None:
    c = ready(pair)
    r = pair.client.complete(c["id"], _brand_body(c, "foo"))
    assert r.status == 400 and r.body["ucp"]["status"] == "error", r.body
    assert any("display" in str(m.get("path")) for m in r.body["messages"]), r.body
    assert TOKEN not in json.dumps(r.body)
    assert pair.psp.attempts == []
    assert pair.client.get(c["id"]).body["status"] == "ready_for_complete"
