"""G6: request signature enforcement on (AC-113, T-04, 02-design 17.3 and 17.4).

With enforcement on, the Business rejects an unsigned or badly signed request before any
checkout logic runs. No checkout row is made. Codes: signatures.md at UCP commit 9c9d6fc.
"""

from __future__ import annotations

import json

import ucp_sigs
from business_app import store
from ucp_core import jwk

from tests.s2.conftest import BUSINESS, create_body
from tests.s4.g6.conftest import G6


def _count(g: G6) -> int:
    return store.checkout_count(g.pair.app.state.transactions_db)


def test_ac113_unsigned_request_rejected_before_checkout_logic(g6: G6) -> None:
    before = _count(g6)
    p = g6.pair
    body = json.dumps(create_body()).encode()
    r = p.biz.post(
        "/checkout-sessions",
        content=body,
        headers=p.headers(**{"Idempotency-Key": "k-113a", "Content-Type": "application/json"}),
    )
    assert r.status_code == 401 and r.json()["code"] == "signature_missing"
    assert _count(g6) == before


def test_ac113_bad_signature_rejected_before_checkout_logic(g6: G6) -> None:
    before = _count(g6)
    p = g6.pair
    body = json.dumps(create_body()).encode()
    h = p.headers(**{"Idempotency-Key": "k-113b", "Content-Type": "application/json"})
    other = jwk.ephemeral()  # a key that the Platform profile does not publish
    h.update(
        ucp_sigs.sign_request(
            other, jwk.public_jwk(other)["kid"], "POST", BUSINESS + "/checkout-sessions", h, body
        )
    )
    r = p.biz.post("/checkout-sessions", content=body, headers=h)
    assert r.status_code in (400, 401), r.text
    assert _count(g6) == before
    tampered = body.replace(b"demo_tshirt", b"demo_mug")
    h2 = p.headers(**{"Idempotency-Key": "k-113c", "Content-Type": "application/json"})
    h2.update(
        ucp_sigs.sign_request(
            p.key, jwk.public_jwk(p.key)["kid"], "POST", BUSINESS + "/checkout-sessions", h2, body
        )
    )
    r2 = p.biz.post("/checkout-sessions", content=tampered, headers=h2)
    assert r2.status_code in (400, 401) and _count(g6) == before


def test_ac113_signed_request_passes(g6: G6) -> None:
    before = _count(g6)
    res = g6.pair.client.create(create_body())
    assert res.status in (200, 201) and _count(g6) == before + 1
