"""G4 contract, S7: the Platform catalog API for the page (`/api/catalog/*`).

It checks what the browser may cause: only `query` (trimmed) and `pagination.cursor` go to the
Business (UX-4.2a.3 query rules), Get Product sends `id` only (AC-133), a capability that is not
active gets no request (T-119, AC-12.10), and the inspector row has the id and the group name
of UX-4.2a.6. Source: UCP 2026-04-08 at 9c9d6fc, catalog/rest.md:64-66.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from platform_app import main as pmain
from platform_app.catalog_client import LOOKUP, SEARCH, CatalogClient
from ucp_core import jwk

from tests.s2.conftest import BUSINESS, PROFILE_URL, Pair
from tests.s7.conftest import Recorder


def stack(pair: Pair, active: list[str]) -> tuple[TestClient, Recorder]:
    rec = Recorder(pair.biz._transport)
    client = CatalogClient(
        BUSINESS,
        PROFILE_URL,
        key=pair.key,
        kid=jwk.public_jwk(pair.key)["kid"],
        transport=rec,
        active=active,
        max_tries=1,
    )
    pmain.set_client(None, pair.timeline)
    pmain.set_catalog_client(client)
    return TestClient(pmain.app), rec


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    yield
    pmain.set_catalog_client(None)
    pmain.set_client(None)


def sent(rec: Recorder) -> list[tuple[str, dict[str, object]]]:
    return [(r.url.path, json.loads(r.content)) for r in rec.requests]


def test_search_sends_the_trimmed_query_only(pair: Pair) -> None:
    web, rec = stack(pair, [SEARCH, LOOKUP])
    r = web.post("/api/catalog/search", json={"query": "  mug  ", "limit": 3, "filters": {}})
    assert r.status_code == 200
    assert sent(rec) == [("/catalog/search", {"query": "mug"})]
    out = r.json()
    assert out["http_status"] == 200
    assert [p["id"] for p in out["body"]["products"]] == ["prod_demo_mug"]
    (row,) = out["inspector"]
    assert (row["mid"], row["phase"], row["name"]) == ("M1a", "Find product", "Search Catalog")
    assert row["source"] == "LIVE CALL" and row["not_ucp"] is False


def test_more_results_sends_the_cursor_only(pair: Pair) -> None:
    web, rec = stack(pair, [SEARCH, LOOKUP])
    cursor = "bzoxMA"  # the Business answers HTTP 400: this is a cursor it did not make
    r = web.post("/api/catalog/search", json={"query": "mug", "cursor": cursor})
    assert sent(rec) == [("/catalog/search", {"query": "mug", "pagination": {"cursor": cursor}})]
    assert r.status_code == 200


def test_empty_query_sends_nothing(pair: Pair) -> None:
    web, rec = stack(pair, [SEARCH, LOOKUP])
    for query in ("", "   ", None):
        assert web.post("/api/catalog/search", json={"query": query}).status_code == 400
    assert rec.requests == []


def test_product_sends_id_only(pair: Pair) -> None:
    web, rec = stack(pair, [SEARCH, LOOKUP])
    r = web.post("/api/catalog/product", json={"id": "prod_demo_mug", "selected": [1]})
    assert sent(rec) == [("/catalog/product", {"id": "prod_demo_mug"})]
    (row,) = r.json()["inspector"]
    assert (row["mid"], row["phase"], row["name"]) == ("M1b", "Find product", "Get Product")
    assert r.json()["body"]["product"]["variants"][0]["id"] == "demo_mug"


def test_no_request_for_a_capability_that_is_not_active(pair: Pair) -> None:
    web, rec = stack(pair, [LOOKUP])  # AC-12.10: a lookup-only Platform
    r = web.post("/api/catalog/search", json={"query": "mug"})
    assert r.status_code == 409 and r.json()["code"] == "capability_not_active"
    web, rec2 = stack(pair, [SEARCH])  # T-119: lookup not active
    r = web.post("/api/catalog/product", json={"id": "prod_demo_mug"})
    assert r.status_code == 409 and r.json()["capability"] == LOOKUP
    assert rec.requests == [] and rec2.requests == []


def test_a_pan_like_query_is_masked_in_the_inspector(pair: Pair) -> None:
    web, _rec = stack(pair, [SEARCH, LOOKUP])
    out = web.post("/api/catalog/search", json={"query": "4111 1111 1111 1111"}).json()
    assert out["inspector"][0]["request"]["body"]["query"] == "[REDACTED]"
