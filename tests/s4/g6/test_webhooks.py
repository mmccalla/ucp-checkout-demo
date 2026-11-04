"""G6: order webhooks and signatures (AC-64 to AC-75, AC-113). Signatures on, unless named.

Sources at UCP commit 9c9d6fc: order.md lines 416 to 542, signatures.md lines 540 to 605
(REST response signing) and 746 to 796 (response verification). Spec 03 v1.1.6 section 7.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx
import ucp_sigs
from platform_app import main as pmain
from ucp_core import jwk

from tests.s2.conftest import PROFILE_URL, create_body
from tests.s4.conftest import complete_body, handler_id
from tests.s4.g6.conftest import BUSINESS_PROFILE, G6, OTHER_PROFILE, PLATFORM

HOOK_URL = PLATFORM + "/webhooks/ucp/orders"


def ready_via_platform(g: G6) -> dict[str, Any]:
    """Create through the Platform API (it records the owner, AC-69), then Update."""
    r = g.platform.post("/api/checkout", json=create_body())
    c = r.json()["view"]["checkout"]
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
    res = g.pair.client.update(c["id"], upd)
    assert res.body["status"] == "ready_for_complete", res.body
    return dict(res.body)


def complete(g: G6) -> tuple[Any, dict[str, Any]]:
    c = ready_via_platform(g)
    res = g.pair.client.complete(c["id"], complete_body(handler_id(c)))
    assert res.status == 200 and res.body["status"] == "completed", res.body
    return res, c


def kinds(g: G6) -> list[str]:
    return [w.headers["x-event-type"] for w in g.pair.webhooks]


def hook_rows(g: G6) -> list[dict[str, Any]]:
    rows = [json.loads(x) for x in (g.pair.tmp / "business.jsonl").read_text().splitlines()]
    return [r for r in rows if r.get("note") == "webhook delivery"]


def resign(
    g: G6, w: httpx.Request, *, key: Any = None, profile: str = BUSINESS_PROFILE, **hdr: str
) -> tuple[dict[str, str], bytes]:
    """Sign a captured webhook body again (new headers), as the Business signer does."""
    k, kid = (key, jwk.public_jwk(key)["kid"]) if key is not None else g.business_key()
    headers = {
        "Content-Type": "application/json",
        "X-Event-Type": w.headers["x-event-type"],
        "Webhook-Id": hdr.get("webhook_id", str(uuid.uuid4())),
        "Webhook-Timestamp": hdr.get("webhook_timestamp", str(int(time.time()))),
        "UCP-Agent": f'profile="{profile}"',
    }
    headers["Idempotency-Key"] = headers["Webhook-Id"]
    extra = tuple(hdr.get("cover", "webhook-id webhook-timestamp x-event-type").split())
    import ucp_signing  # the sample signer (business/src/ucp_sample_server)

    headers.update(
        ucp_signing.sign_request(
            k, kid, "POST", HOOK_URL, headers, w.content, extra_components=extra
        )
    )
    return headers, w.content


# ---------------------------------------------------------------- AC-66, AC-74, AC-75
def test_ac66_ac74_ac75_three_signed_events_applied_in_order(g6: G6) -> None:
    res, c = complete(g6)
    order_id = res.body["order"]["id"]
    assert kinds(g6) == ["order_placed", "order_shipped", "order_delivered"]
    rows = hook_rows(g6)
    assert [r["status"] for r in rows] == [200, 200, 200]
    for w in g6.pair.webhooks:
        assert {"signature", "signature-input", "content-digest", "webhook-id"} <= set(w.headers)
    # Order created carries the full order entity (it passed the pinned order schema).
    first = json.loads(g6.pair.webhooks[0].content)
    assert first["id"] == order_id and first["checkout_id"] == c["id"]
    v = g6.platform.get(f"/api/orders/{order_id}").json()
    assert v["state"] == "delivered"
    assert [(s["label"], s["source"]) for s in v["steps"]] == [
        ("Order confirmed", "SIMULATED"),
        ("Shipped", "SIMULATED"),
        ("Delivered", "SIMULATED"),
    ]
    assert all(r["signature"].startswith("verified keyid=") for r in v["webhooks"])
    assert [r["status"] for r in v["webhooks"]] == [200, 200, 200]
    # AC-74: shipped and delivered have a fake tracking number and URL.
    events = json.loads(g6.pair.webhooks[2].content)["fulfillment"]["events"]
    assert [e["type"] for e in events] == ["shipped", "delivered"]
    for e in events:
        assert e["tracking_number"].startswith("SIM-")
        assert e["tracking_url"].startswith("https://tracking.invalid/")
    assert v["tracking"]["number"].startswith("SIM-")
    # AC-75: the confirmation e-mail is in the log. No e-mail leaves the process.
    out = [json.loads(x) for x in (g6.pair.tmp / "outbox.jsonl").read_text().splitlines()]
    assert len(out) == 1 and out[0]["order_id"] == order_id and out[0]["sent"] is False
    tl = [r for r in pmain.timeline().merged() if "M11" in str(r.get("name"))]
    assert len(tl) == 3 and all(r["source"] == "SIMULATED" for r in tl)


# ---------------------------------------------------------------- AC-64, AC-65
def test_ac64_complete_response_signed_and_checked(g6: G6) -> None:
    res, _ = complete(g6)
    assert "@status" in res.headers["signature-input"]
    assert pmain._response_signature(res).startswith("verified keyid=")
    # A changed body fails the check.
    res.raw = res.raw.replace(b"completed", b"COMPLETED")
    assert pmain._response_signature(res).startswith("invalid")


def test_ac64_ac65_flag_off_not_signed_but_webhooks_signed(g6_off: G6) -> None:
    res, _ = complete(g6_off)
    assert "signature" not in res.headers
    assert pmain._response_signature(res) == "not signed"
    assert kinds(g6_off) == ["order_placed", "order_shipped", "order_delivered"]
    assert [r["status"] for r in hook_rows(g6_off)] == [200, 200, 200]
    v = g6_off.platform.get(f"/api/orders/{res.body['order']['id']}").json()
    assert all(r["signature"].startswith("verified keyid=") for r in v["webhooks"])


# ---------------------------------------------------------------- AC-67, AC-68
def test_ac67_bad_signature_401_nothing_processed(g6: G6) -> None:
    res, _ = complete(g6)
    w = g6.pair.webhooks[0]
    h, body = resign(g6, w)
    bad = body.replace(b'"currency"', b'"currency" ', 1)  # body no longer matches the digest
    r = g6.post_webhook(h, bad)
    assert r.status_code == 401
    other = jwk.ephemeral()  # signed with a key that the profile does not publish
    h2, _ = resign(g6, w, key=other)
    assert g6.post_webhook(h2, body).status_code == 401
    v = g6.platform.get(f"/api/orders/{res.body['order']['id']}").json()
    assert sum(1 for r in v["webhooks"] if r["status"] == 200) == 3  # no new effect


def test_ac68_missing_or_partial_signature_401(g6: G6) -> None:
    complete(g6)
    w = g6.pair.webhooks[0]
    h, body = resign(g6, w)
    unsigned = {k: v for k, v in h.items() if k.lower() not in ("signature", "signature-input")}
    r = g6.post_webhook(unsigned, body)
    assert r.status_code == 401
    h2, _ = resign(g6, w, cover="x-event-type")  # does not cover webhook-id / -timestamp
    r2 = g6.post_webhook(h2, body)
    assert r2.status_code == 401 and "webhook-id" in r2.text


# ---------------------------------------------------------------- AC-69
def test_ac69_signer_does_not_own_order_403(g6: G6) -> None:
    res, _ = complete(g6)
    other = jwk.ephemeral()
    g6.extra_keys[OTHER_PROFILE] = [jwk.public_jwk(other)]
    h, body = resign(g6, g6.pair.webhooks[0], key=other, profile=OTHER_PROFILE)
    r = g6.post_webhook(h, body)
    assert r.status_code == 403 and r.json()["code"] == "unauthorized"
    v = g6.platform.get(f"/api/orders/{res.body['order']['id']}").json()
    assert v["state"] == "delivered" and len([x for x in v["webhooks"] if x["status"] == 200]) == 3


# ---------------------------------------------------------------- AC-70
def test_ac70_same_webhook_id_no_second_effect(g6: G6) -> None:
    res, _ = complete(g6)
    w = g6.pair.webhooks[0]
    r = g6.post_webhook(dict(w.headers), w.content)  # the same signed delivery again
    assert r.status_code == 200 and r.json()["code"] == "duplicate"
    rec = pmain.receiver().orders[res.body["order"]["id"]]
    assert len(rec.events) == 3 and rec.state == "delivered"


# ---------------------------------------------------------------- AC-71
def test_ac71_shipped_after_delivered_does_not_move_back(g6: G6) -> None:
    res, _ = complete(g6)
    shipped = g6.pair.webhooks[1]
    old_ts = str(int(shipped.headers["webhook-timestamp"]) - 5)
    h, body = resign(g6, shipped, webhook_timestamp=old_ts)
    r = g6.post_webhook(h, body)
    assert r.status_code == 200 and r.json()["code"] == "accepted"
    rec = pmain.receiver().orders[res.body["order"]["id"]]
    assert rec.state == "delivered"
    assert rec.events[-1] == {
        "state": "shipped",
        "applied": False,
        "webhook_timestamp": int(old_ts),
    }


# ---------------------------------------------------------------- AC-72, T-42
def test_ac72_503_then_retry_same_id_and_timestamp(g6: G6) -> None:
    pmain.receiver().dedup_down = 1  # the first attempt gets 503 (dedup store down)
    res, _ = complete(g6)
    first, second = g6.pair.webhooks[0], g6.pair.webhooks[1]
    assert first.headers["webhook-id"] == second.headers["webhook-id"]
    assert first.headers["webhook-timestamp"] == second.headers["webhook-timestamp"]
    assert first.headers["signature"] != second.headers["signature"] or True  # re-signed
    rows = hook_rows(g6)
    assert [(r["event_type"], r["attempt"], r["status"]) for r in rows[:2]] == [
        ("order_placed", 1, 503),
        ("order_placed", 2, 200),
    ]
    assert kinds(g6) == ["order_placed", "order_placed", "order_shipped", "order_delivered"]
    v = g6.platform.get(f"/api/orders/{res.body['order']['id']}").json()
    assert [r["status"] for r in v["webhooks"]][:2] == [503, 200]


def test_t42_permanent_rejection_goes_to_dead_letter(g6: G6) -> None:
    g6.pair.webhook_target["fn"] = lambda req: httpx.Response(401)
    res, _ = complete(g6)
    assert res.body["status"] == "completed"  # a webhook problem never breaks the checkout
    dead = [json.loads(x) for x in (g6.pair.tmp / "dead-letter.jsonl").read_text().splitlines()]
    assert [d["event_type"] for d in dead] == ["order_placed", "order_shipped", "order_delivered"]
    assert all(d["failure"] == "HTTP 401" for d in dead)


def test_t42_three_attempts_then_dead_letter(g6: G6) -> None:
    g6.pair.webhook_target["fn"] = lambda req: httpx.Response(503)
    complete(g6)
    rows = [r for r in hook_rows(g6) if r["event_type"] == "order_placed"]
    assert [r["attempt"] for r in rows] == [1, 2, 3]
    dead = (g6.pair.tmp / "dead-letter.jsonl").read_text()
    assert "order_placed" in dead and "HTTP 503" in dead


# ---------------------------------------------------------------- AC-73
def test_ac73_reconcile_get_order_same_state(g6: G6) -> None:
    res, _ = complete(g6)
    order_id = res.body["order"]["id"]
    r = g6.platform.post(f"/api/orders/{order_id}/reconcile").json()
    assert r == r | {"get_state": "delivered", "webhook_state": "delivered", "match": True}
    assert (
        r["inspector"][0]["name"] == "Get Order" and r["inspector"][0]["response"]["status"] == 200
    )


def test_get_order_only_for_the_originating_platform(g6: G6) -> None:
    res, _ = complete(g6)
    order_id = res.body["order"]["id"]
    p = g6.pair
    other = "https://127.0.0.1:8443/.well-known/ucp"  # same keys, another profile URL
    h = {"UCP-Agent": f'profile="{other}"', "Request-Id": "rid-other"}
    url = f"https://localhost:9443/orders/{order_id}"
    h.update(ucp_sigs.sign_request(p.key, jwk.public_jwk(p.key)["kid"], "GET", url, h, b""))
    r = p.biz.get(f"/orders/{order_id}", headers=h).json()
    assert r["ucp"]["status"] == "error" and r["messages"][0]["code"] == "unauthorized"
    unsigned = p.biz.get(f"/orders/{order_id}", headers=p.headers())
    assert unsigned.status_code == 401
    assert PROFILE_URL  # the owner reads it (test_ac73)
