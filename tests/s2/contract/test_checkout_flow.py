"""G4 contract, S2: signed Platform requests to the Business REST binding, in one process.

ACs: AC-07, AC-11 (in-process part), AC-13, AC-14, AC-37, AC-38, AC-41, AC-42, AC-43,
AC-48, AC-89, AC-94, AC-95, AC-100, AC-104, AC-108, AC-109.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
from business_app import store
from platform_app import checkout_view
from ucp_core import composed

from tests.s2.conftest import PROFILE_URL, Pair, create_body, make_pair, without_key_ids


def rows(p: pathlib.Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def count(pair: Pair) -> int:
    return store.checkout_count(pair.app.state.transactions_db)


def test_ac13_create_201_total_option_handler(pair: Pair) -> None:
    r = pair.client.create(create_body())
    assert r.status == 201, r.body
    b = r.body
    assert r.schema_problems == []
    assert b["ucp"]["status"] == "success"
    assert [t for t in b["totals"] if t["type"] == "total"][0]["amount"] == 2000
    groups = b["fulfillment"]["methods"][0]["groups"]
    assert groups[0]["options"][0]["id"] == "gb-standard"
    assert "com.google.pay" in b["ucp"]["payment_handlers"]
    assert b["currency"] == "GBP"


def test_ac07_headers_and_timeline(pair: Pair) -> None:
    r = pair.client.create(create_body())
    pair.timeline.record(r)
    biz = rows(pair.tmp / "business.jsonl")
    assert biz[-1]["request_id"] == r.request_id
    assert biz[-1]["idempotency_key_present"] is True
    assert biz[-1]["signature"].startswith("verified keyid=")
    merged = pair.timeline.merged()
    assert [m["side"] for m in merged] == ["platform", "business"]
    assert merged[0]["idempotency_key_present"] is True
    assert pair.fetches == [PROFILE_URL]  # AC-11: the UCP-Agent URL is the profile URL


def test_ac100_no_token_or_header_value_in_rows(pair: Pair) -> None:
    r = pair.client.create(create_body())
    pair.timeline.record(r)
    # The `kid` in "verified keyid=<kid>" is random. "eyJ" can be in it by chance: remove it first.
    text = without_key_ids(
        (pair.tmp / "business.jsonl").read_text() + (pair.tmp / "platform.jsonl").read_text()
    )
    assert str(r.idempotency_key) not in text
    for word in ("sig1=", "Signature", "token", "eyJ", PROFILE_URL):
        assert word not in text
    for row in pair.timeline.merged():
        assert row["request_id"] == r.request_id


def test_ac14_out_of_stock_create_with_one_item_in_stock(pair: Pair) -> None:
    body = create_body()
    body["line_items"].append({"item": {"id": "demo_mug"}, "quantity": 1})
    r = pair.client.create(body)
    assert r.status == 201
    errs = [m for m in r.body["messages"] if m["type"] == "error"]
    assert len(errs) == 1 and errs[0]["code"] == "out_of_stock"
    assert errs[0]["path"] == "$.line_items[1]"
    assert r.body["status"] == "incomplete"
    v = checkout_view.interpret(checkout_view.Session(), r)
    assert v.controls == [checkout_view.CHANGE_ITEM, checkout_view.BACK]
    assert checkout_view.COMPLETE not in v.controls
    assert checkout_view.described_by(v) == {"field-line-items-1": "ucp-msg-0"}


def test_ac14_create_with_no_checkout_is_200_error_response(pair: Pair) -> None:
    before = count(pair)
    r = pair.client.create(create_body(item="demo_mug"))
    assert r.status == 200
    assert r.body["ucp"]["status"] == "error"
    assert "id" not in r.body
    assert [m["code"] for m in r.body["messages"]] == ["out_of_stock"]
    assert count(pair) == before


def test_ac14_address_undeliverable_on_update_is_200(pair: Pair) -> None:
    c = pair.client.create(create_body()).body
    upd = {
        "line_items": [
            {"id": c["line_items"][0]["id"], "item": {"id": "demo_tshirt"}, "quantity": 1}
        ],
        "fulfillment": {
            "methods": [
                {
                    "id": c["fulfillment"]["methods"][0]["id"],
                    "type": "shipping",
                    # fulfillment_method.json line 25: required on update
                    "line_item_ids": [c["line_items"][0]["id"]],
                    "destinations": [
                        dict(
                            create_body()["fulfillment"]["methods"][0]["destinations"][0],
                            address_country="FR",
                        )
                    ],
                    "selected_destination_id": "d1",
                }
            ]
        },
    }
    r = pair.client.update(c["id"], upd)
    assert r.status == 200, r.body
    errs = [m for m in r.body["messages"] if m["type"] == "error"]
    assert [m["code"] for m in errs] == ["address_undeliverable"]
    v = checkout_view.interpret(checkout_view.Session(), r)
    assert v.controls[0] == checkout_view.CHANGE_ADDRESS


def test_ac109_incomplete_to_ready_minor_units_links(pair: Pair) -> None:
    c = pair.client.create(create_body()).body
    assert c["status"] == "incomplete"
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
    assert r.status == 200, r.body
    assert r.schema_problems == []
    assert r.body["status"] == "ready_for_complete"
    assert {t["type"]: t["amount"] for t in r.body["totals"]}["total"] == 2300
    amounts: list[Any] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "amount":
                    amounts.append(v)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(r.body)
    assert amounts and all(type(a) is int for a in amounts)
    assert {link["type"] for link in r.body["links"]} >= {"privacy_policy", "terms_of_service"}
    for link in r.body["links"]:
        page = pair.biz.get(link["url"].removeprefix("https://localhost:9443"))
        assert page.status_code == 200
    v = checkout_view.interpret(checkout_view.Session(), r)
    assert checkout_view.COMPLETE in v.controls


def test_ac42_replay_same_key_same_body(pair: Pair) -> None:
    body = json.dumps(create_body(), separators=(",", ":"))
    h = pair.headers(**{"Idempotency-Key": "k-42", "Content-Type": "application/json"})
    unsigned = make_unsigned(pair)
    r1 = unsigned.post("/checkout-sessions", content=body, headers=h)
    r2 = unsigned.post("/checkout-sessions", content=body, headers=h)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json() == r2.json()
    assert count(pair) == 1
    biz = rows(pair.tmp / "business.jsonl")
    assert biz[-1].get("replayed") is True and "replayed" not in biz[-2]


def test_ac43_same_key_other_body_409(pair: Pair) -> None:
    h = pair.headers(**{"Idempotency-Key": "k-43"})
    unsigned = make_unsigned(pair)
    r1 = unsigned.post("/checkout-sessions", json=create_body(), headers=h)
    r2 = unsigned.post("/checkout-sessions", json=create_body(qty=2), headers=h)
    assert r1.status_code == 201
    assert r2.status_code == 409
    assert set(r2.json()) >= {"code", "content"}
    assert count(pair) == 1


def test_ac48_missing_idempotency_key_400_no_state(pair: Pair) -> None:
    unsigned = make_unsigned(pair)
    r = unsigned.post("/checkout-sessions", json=create_body(), headers=pair.headers())
    assert r.status_code == 400
    assert r.json()["ucp"]["status"] == "error"
    assert r.json()["messages"][0]["code"] == "invalid_request"
    assert count(pair) == 0


def test_ac89_schema_failure_is_400_error_response(pair: Pair) -> None:
    unsigned = make_unsigned(pair)
    r = unsigned.post(
        "/checkout-sessions",
        json={"line_items": "x"},
        headers=pair.headers(**{"Idempotency-Key": "k-89"}),
    )
    assert r.status_code == 400
    b = r.json()
    assert b["ucp"]["status"] == "error"
    m = b["messages"][0]
    assert {"type", "code", "content", "severity"} <= set(m) and m["code"] == "invalid_request"
    assert count(pair) == 0


def test_ac104_enum_value_not_in_schema_rejected(pair: Pair) -> None:
    body = create_body()
    body["fulfillment"]["methods"][0]["type"] = "drone"
    unsigned = make_unsigned(pair)
    r = unsigned.post(
        "/checkout-sessions", json=body, headers=pair.headers(**{"Idempotency-Key": "k-104"})
    )
    assert r.status_code == 400
    assert count(pair) == 0


def test_ac38_risk_signals_pass_and_are_logged(pair: Pair) -> None:
    body = create_body()
    body["risk_signals"] = {"x": 1}
    unsigned = make_unsigned(pair)
    r = unsigned.post(
        "/checkout-sessions", json=body, headers=pair.headers(**{"Idempotency-Key": "k-38"})
    )
    assert r.status_code == 201, r.text
    assert "risk_signals" not in r.json() and "signals" not in r.json()
    assert rows(pair.tmp / "business.jsonl")[-1]["unknown_root_fields"] == ["risk_signals"]
    assert composed.problems("checkout.create_request", body) == []


def test_ac37_platform_never_sends_signals(pair: Pair) -> None:
    body = create_body()
    body["signals"] = {}
    with pytest.raises(ValueError):
        pair.client.create(body)
    r = pair.client.create(create_body())
    assert r.request_body is not None
    assert "signals" not in r.request_body and "risk_signals" not in r.request_body


def test_ac108_no_ucp_agent_or_wrong_path(pair: Pair) -> None:
    unsigned = make_unsigned(pair)
    for agent in (
        None,
        'profile="https://localhost:8443/profile.json"',
        'profile="http://localhost:8443/.well-known/ucp"',
    ):
        h = {"Request-Id": "r", "Idempotency-Key": f"k-108-{agent}"}
        if agent:
            h["UCP-Agent"] = agent
        r = unsigned.post("/checkout-sessions", json=create_body(), headers=h)
        assert r.status_code == 400
        assert r.json()["code"] == "invalid_profile_url"
    assert count(pair) == 0


def test_get_unknown_checkout_is_200_not_found(pair: Pair) -> None:
    r = pair.client.get("no-such-id")
    assert r.status == 200
    assert r.body["ucp"]["status"] == "error"
    assert r.body["messages"][0]["code"] == "not_found"
    assert r.body["messages"][0]["severity"] == "unrecoverable"


def test_ac41_error_response_keeps_last_good(pair: Pair) -> None:
    s = checkout_view.Session()
    good = pair.client.create(create_body())
    checkout_view.interpret(s, good)
    v = checkout_view.interpret(s, pair.client.get("no-such-id"))
    assert v.state == "error_response"
    assert v.checkout is not None and v.checkout["id"] == good.body["id"]
    assert v.messages[0]["code"] == "not_found"


def test_signature_required_by_default(pair: Pair) -> None:
    unsigned = pair.biz
    r = unsigned.post(
        "/checkout-sessions",
        json=create_body(),
        headers=pair.headers(**{"Idempotency-Key": "k-sig"}),
    )
    assert r.status_code == 401
    assert r.json()["code"] == "signature_missing"
    assert count(pair) == 0


def test_cancel_is_signed_and_works(pair: Pair) -> None:
    c = pair.client.create(create_body()).body
    r = pair.client.cancel(c["id"])
    assert r.status == 200, r.body
    assert r.body["status"] == "canceled"


def make_unsigned(pair: Pair) -> Any:
    """A Business client with signature enforcement off (the G5 setting, T-04)."""
    pair.app.state.gate.require_signatures = False
    return pair.biz


@pytest.fixture
def old_version(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    def edit(p: dict[str, Any]) -> None:
        p["ucp"]["version"] = "2026-01-11"

    yield from make_pair(tmp_path, monkeypatch, profile_edit=edit)


def test_ac95_version_unsupported(old_version: Pair) -> None:
    r = old_version.client.create(create_body())
    assert r.status == 422
    assert r.body["code"] == "version_unsupported"
    v = checkout_view.interpret(checkout_view.Session(), r)
    assert v.state == "setup_problem" and v.problem is not None
    assert (v.problem["code"], v.problem["http_status"]) == ("version_unsupported", 422)
    assert v.problem["payment_problem"] is False


def test_ac94_totals_with_zero_or_two_total_entries_fail(pair: Pair) -> None:
    import copy

    good = pair.client.create(create_body()).body
    assert composed.problems("checkout.read_response", good) == []
    zero = copy.deepcopy(good)
    zero["totals"] = [t for t in zero["totals"] if t["type"] != "total"]
    two = copy.deepcopy(good)
    two["totals"].append({"type": "total", "amount": 1})
    assert composed.problems("checkout.read_response", zero)
    assert composed.problems("checkout.read_response", two)
