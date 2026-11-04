"""G4 contract, S7: catalog search, AC-12.1 to AC-12.10 (spec v1.1.17, section AC-12).

The Business and the Platform client run in one process. Source: UCP 2026-04-08 at 9c9d6fc,
`docs/specification/catalog/` (search.md, index.md, rest.md) and the pinned schemas.

Not tested here (UI, waits for UX-4.2a): the display of AC-12.3, the disabled button of AC-12.9
and the text of AC-12.10. The data that those UI parts need is tested.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

import pytest
from business_app import catalog
from platform_app.catalog_client import LOOKUP, SEARCH, CapabilityNotActive, CatalogClient

from tests.s2.conftest import create_body
from tests.s7.conftest import Cat


def ids(body: dict[str, Any]) -> list[str]:
    return [p["id"] for p in body["products"]]


def test_ac12_1_headers_and_no_idempotency_key(cat: Cat) -> None:
    r = cat.client.search(query="demo")
    assert r.status == 200 and r.schema_problems == []
    sent = cat.rec.requests[-1]
    assert sent.url.path == "/catalog/search" and sent.method == "POST"
    assert sent.headers["ucp-agent"].startswith('profile="')
    assert str(uuid.UUID(sent.headers["request-id"])) == sent.headers["request-id"]
    assert "idempotency-key" not in sent.headers
    assert r.idempotency_key is None


def test_ac12_1_a_search_with_no_signature_and_no_key_gets_200(cat: Cat) -> None:
    # The Business requires signatures on checkout. Catalog calls need no signature.
    r = cat.raw("/catalog/search", {"query": "mug"})
    assert r.status_code == 200
    assert [p["id"] for p in r.json()["products"]] == ["prod_demo_mug"]
    assert "authorization" not in r.request.headers and "x-api-key" not in r.request.headers
    assert "signature" not in r.request.headers


def test_ac12_2_products_have_the_required_fields(cat: Cat) -> None:
    r = cat.client.search(query="demo")
    assert r.status == 200 and r.schema_problems == []
    assert set(r.body) >= {"ucp", "products"}
    assert len(r.body["products"]) == 2
    for p in r.body["products"]:
        for k in ("id", "title", "description", "price_range", "variants"):
            assert k in p
        assert len(p["variants"]) >= 1
        for v in p["variants"]:
            for k in ("id", "title", "description", "price"):
                assert k in v
            price = v["price"]
            assert isinstance(price["amount"], int) and price["currency"] == "GBP"


def test_ac12_3_data_for_the_display(cat: Cat) -> None:
    # This test checks the data for the display. The display is tested in tests/s7/e2e.
    for p in cat.client.search(query="demo").body["products"]:
        lo, hi = p["price_range"]["min"], p["price_range"]["max"]
        assert lo["currency"] == hi["currency"] and lo["amount"] <= hi["amount"]
        assert p["variants"][0]["price"] == lo  # the featured variant is the first


def test_ac12_4_no_match_gives_empty_products_and_no_messages(cat: Cat) -> None:
    r = cat.client.search(query="no-such-product-xyz")
    assert r.status == 200 and r.schema_problems == []
    assert r.body["products"] == []
    assert "messages" not in r.body


def test_ac12_5_pagination_next_page_and_last_page(cat: Cat) -> None:
    first = cat.client.search(query="demo", pagination={"limit": 1})
    assert first.status == 200 and first.schema_problems == []
    assert len(first.body["products"]) == 1
    assert first.body["pagination"]["has_next_page"] is True
    cursor = first.body["pagination"]["cursor"]
    second = cat.client.search(query="demo", pagination={"limit": 1, "cursor": cursor})
    assert second.status == 200 and second.schema_problems == []
    assert second.body["pagination"]["has_next_page"] is False
    assert "cursor" not in second.body["pagination"]
    assert ids(first.body) != ids(second.body)


def _many(n: int) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        p: dict[str, Any] = {
            "id": f"prod_{i:02d}",
            "title": f"Item {i}",
            "description": {"plain": "demo item"},
            "price_range": {"min": {"amount": 100, "currency": "GBP"}},
            "variants": [
                {
                    "id": f"item_{i:02d}",
                    "title": f"Item {i}",
                    "description": {"plain": "demo item"},
                    "price": {"amount": 100, "currency": "GBP"},
                }
            ],
        }
        p["price_range"]["max"] = copy.deepcopy(p["price_range"]["min"])
        out.append(p)
    return out


def test_ac12_5_default_page_is_10_and_a_big_limit_gives_a_smaller_page(
    cat: Cat, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalog, "load_products", lambda *a: _many(25))
    default = cat.client.search(query="item")
    assert default.status == 200 and len(default.body["products"]) == 10
    assert default.body["pagination"]["has_next_page"] is True
    big = cat.client.search(query="item", pagination={"limit": 100})
    assert big.status == 200 and big.schema_problems == []
    assert len(big.body["products"]) == catalog.MAX_LIMIT == 20  # 20: accepted default (T-118)
    assert big.body["pagination"]["cursor"]


@pytest.mark.parametrize("body", [{}, {"query": ""}, {"query": "  "}, {"filters": {}}])
def test_ac12_6_a_search_with_no_input_gets_400(cat: Cat, body: dict[str, Any]) -> None:
    r = cat.raw("/catalog/search", body)
    assert r.status_code == 400  # the status only (U-51)
    assert "products" not in r.json()


def test_ac12_7_category_filter_uses_or(cat: Cat) -> None:
    one = cat.client.search(filters={"categories": ["Apparel"]})
    assert one.status == 200 and ids(one.body) == ["prod_demo_tshirt"]
    both = cat.client.search(filters={"categories": ["Apparel", "Homeware"]})
    assert sorted(ids(both.body)) == ["prod_demo_mug", "prod_demo_tshirt"]
    assert cat.client.search(filters={"categories": ["Nothing"]}).body["products"] == []


def test_ac12_7_price_filter_is_in_minor_units_and_inclusive(cat: Cat) -> None:
    ctx = {"currency": "GBP"}
    cheap = cat.client.search(query="demo", filters={"price": {"max": 1500}}, context=ctx)
    assert ids(cheap.body) == ["prod_demo_mug"]
    dear = cat.client.search(query="demo", filters={"price": {"min": 1500}}, context=ctx)
    assert ids(dear.body) == ["prod_demo_tshirt"]
    edge = cat.client.search(filters={"price": {"min": 2000, "max": 2000}}, context=ctx)
    assert ids(edge.body) == ["prod_demo_tshirt"]
    assert edge.schema_problems == []


def test_ac12_7_filter_and_query_combine_with_and(cat: Cat) -> None:
    r = cat.client.search(query="mug", filters={"categories": ["Apparel"]})
    assert r.status == 200 and r.body["products"] == []


def test_ac12_7_unknown_filter_property_is_accepted(cat: Cat) -> None:
    r = cat.client.search(query="mug", filters={"colour": "white"})
    assert r.status == 200 and ids(r.body) == ["prod_demo_mug"]


def test_ac12_8_the_variant_id_is_the_checkout_item_id(cat: Cat) -> None:
    r = cat.client.search(query="T-shirt")
    product = r.body["products"][0]
    variant = product["variants"][0]
    assert variant["id"] != product["id"]
    created = cat.pair.client.create(create_body(item=variant["id"]))
    assert created.status == 201, created.body
    item = created.body["line_items"][0]["item"]
    assert item["id"] == variant["id"] != product["id"]
    totals = {t["type"]: t["amount"] for t in created.body["totals"]}
    assert totals["total"] == variant["price"]["amount"]  # the price agrees with the catalog


def test_ac12_9_each_variant_has_availability_and_the_mug_is_not_available(cat: Cat) -> None:
    # This test checks the data. The disabled button is tested in tests/s7/e2e.
    products = cat.client.search(query="demo").body["products"]
    for p in products:
        for v in p["variants"]:
            assert isinstance(v["availability"]["available"], bool)
    mug = next(p for p in products if p["id"] == "prod_demo_mug")
    assert mug["variants"][0]["availability"]["available"] is False


def test_ac12_10_search_not_active_sends_no_post(cat: Cat) -> None:
    client = CatalogClient(
        cat.client.base_url,
        cat.client.profile_url,
        key=cat.client.key,
        kid=cat.client.kid,
        transport=cat.rec,
        active=[LOOKUP],  # AC-09: lookup without search
    )
    before = len(cat.rec.requests)
    with pytest.raises(CapabilityNotActive):
        client.search(query="demo")
    assert len(cat.rec.requests) == before
    assert SEARCH not in client.active


def test_ac12_10_no_negotiation_result_sends_no_post(cat: Cat) -> None:
    client = CatalogClient(
        cat.client.base_url,
        cat.client.profile_url,
        key=cat.client.key,
        kid=cat.client.kid,
        transport=cat.rec,
    )
    before = len(cat.rec.requests)
    with pytest.raises(CapabilityNotActive):
        client.search(query="demo")
    assert len(cat.rec.requests) == before
