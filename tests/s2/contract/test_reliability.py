"""G4 contract, S2: retries, faults and profile problems (AC-10, AC-47, AC-49, AC-50)."""

from __future__ import annotations

import os
import pathlib
from typing import Any

import httpx
import pytest
from business_app import store
from platform_app import checkout_view
from ucp_core import netguard

from tests.s2.conftest import Pair, create_body, make_pair


class FlakyTransport(httpx.BaseTransport):
    """Fail the first `fail` requests with a network error. Record each request."""

    def __init__(self, inner: httpx.BaseTransport, fail: int) -> None:
        self.inner, self.fail = inner, fail
        self.seen: list[tuple[str, dict[str, str], bytes]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.seen.append((request.method, dict(request.headers), request.read()))
        if self.fail > 0:
            self.fail -= 1
            raise httpx.ConnectError("test: network error", request=request)
        return self.inner.handle_request(request)


def test_ac49_network_error_on_update_retries_same_key_and_body(pair: Pair) -> None:
    c = pair.client.create(create_body()).body
    flaky = FlakyTransport(httpx.MockTransport(pair.biz.send), fail=1)
    pair.client.http = httpx.Client(transport=flaky)
    upd = {
        "line_items": [
            {"id": c["line_items"][0]["id"], "item": {"id": "demo_tshirt"}, "quantity": 2}
        ]
    }
    r = pair.client.update(c["id"], upd)
    assert r.status == 200 and r.tries == 2, r.body
    (m1, h1, b1), (m2, h2, b2) = flaky.seen
    assert m1 == m2 == "PUT"
    assert h1["idempotency-key"] == h2["idempotency-key"]
    assert h1["request-id"] == h2["request-id"]
    assert b1 == b2
    assert pair.sleeps == [0.5]


@pytest.fixture
def rate_limited(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    yield from make_pair(tmp_path, monkeypatch, faults={"rate_limit": 2, "retry_after": 2})


def test_ac50_429_waits_retry_after_then_201(rate_limited: Pair) -> None:
    r = rate_limited.client.create(create_body())
    assert r.status == 201 and r.tries == 3
    assert rate_limited.sleeps == [2.0, 2.0]


@pytest.fixture
def unavailable(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    yield from make_pair(tmp_path, monkeypatch, faults={"unavailable": 5, "retry_after": 1})


def test_ac50_503_stops_after_3_tries(unavailable: Pair) -> None:
    r = unavailable.client.create(create_body())
    assert r.status == 503 and r.tries == 3
    assert unavailable.sleeps == [1.0, 1.0]
    assert r.headers["retry-after"] == "1"
    v = checkout_view.interpret(checkout_view.Session(), r)
    assert v.state == "setup_problem"


def test_ac47_store_unavailable_503_and_readiness_red(pair: Pair) -> None:
    assert pair.biz.get("/readyz").status_code == 200
    db = pair.app.state.transactions_db
    os.rename(db, db + ".away")
    try:
        r = pair.client.create(create_body())
        assert r.status == 503
        assert r.body["code"] == "store_unavailable"
        assert r.headers["retry-after"] == "2"
        ready = pair.biz.get("/readyz")
        assert ready.status_code == 503 and ready.json()["status"] == "red"
    finally:
        os.rename(db + ".away", db)
    assert store.checkout_count(db) == 0


def _fetch_fails(code: str) -> Any:
    def fetcher(url: str) -> tuple[dict[str, Any], dict[str, str]]:
        raise netguard.FetchError(code, f"test {code} for {url}")

    return fetcher


@pytest.mark.parametrize(
    ("code", "status"), [("profile_unreachable", 424), ("profile_malformed", 422)]
)
def test_ac10_profile_problem_stops_with_code_and_status(
    pair: Pair, code: str, status: int
) -> None:
    resolver = pair.app.state.gate.resolver
    resolver.cache.clear()
    resolver.fetcher = _fetch_fails(code)
    r = pair.client.create(create_body())
    assert (r.status, r.body["code"]) == (status, code)
    v = checkout_view.interpret(checkout_view.Session(), r)
    assert v.problem is not None
    assert (v.problem["code"], v.problem["http_status"]) == (code, status)
    assert store.checkout_count(pair.app.state.transactions_db) == 0


def test_blocked_address_is_400_invalid_profile_url(pair: Pair) -> None:
    def fetcher(url: str) -> tuple[dict[str, Any], dict[str, str]]:
        raise netguard.BlockedAddress(url, "10.0.0.1", "private")

    resolver = pair.app.state.gate.resolver
    resolver.cache.clear()
    resolver.fetcher = fetcher
    r = pair.client.create(create_body())
    assert (r.status, r.body["code"]) == (400, "invalid_profile_url")
