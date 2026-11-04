"""G4 contract, S7: AC-08b-1 to AC-08b-5 (spec v1.1.17, section AC-08 (b)).

AC-08b-6 is tested in test_ac08b6_inactive_capability.py.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from business_app.main import create_app
from fastapi.testclient import TestClient
from platform_app import discovery
from platform_app.catalog_client import LOOKUP, SEARCH
from ucp_core import jwk, profile_check
from ucp_core.schema_registry import SchemaRegistry

from tests.s7.conftest import Cat

V = "2026-04-08"


def served(mode: str) -> dict[str, Any]:
    c = TestClient(create_app(mode=mode, key=jwk.ephemeral()))
    body: dict[str, Any] = c.get("/.well-known/ucp").json()
    return body


@pytest.mark.parametrize("mode", ["demo", "ci"])
def test_ac08b_1_business_profile_declares_services_and_catalog(mode: str) -> None:
    ucp = served(mode)["ucp"]
    entries = ucp["services"]["dev.ucp.shopping"]
    assert [e["transport"] for e in entries] == ["rest"]
    assert entries[0]["endpoint"].startswith("https://")
    for name, slug in ((SEARCH, "search"), (LOOKUP, "lookup")):
        (entry,) = ucp["capabilities"][name]
        assert entry["version"] == V
        assert entry["spec"] == f"https://ucp.dev/{V}/specification/catalog/{slug}"
        assert entry["schema"] == f"https://ucp.dev/{V}/schemas/shopping/catalog_{slug}.json"
        assert "extends" not in entry


@pytest.fixture(scope="module")
def reg() -> SchemaRegistry:
    return SchemaRegistry.load()


def test_ac08b_2_both_capabilities_active(reg: SchemaRegistry) -> None:
    business = served("demo")
    report = profile_check.check(reg, business, discovery.platform_profile())
    assert SEARCH in report["active"] and LOOKUP in report["active"]
    assert report["search_notice"] is None
    assert SEARCH not in report["excluded"] and LOOKUP not in report["excluded"]


def test_ac08b_4_lookup_only_business_search_inactive_lookup_active(reg: SchemaRegistry) -> None:
    business = copy.deepcopy(served("demo"))
    del business["ucp"]["capabilities"][SEARCH]
    report = profile_check.check(reg, business, discovery.platform_profile())
    assert LOOKUP in report["active"] and SEARCH not in report["active"]
    assert report["search_notice"] == "Search is not available with this agent"


def test_ac08b_4_the_lookup_only_panel_case_still_shows_the_notice(reg: SchemaRegistry) -> None:
    # AC-09 regression: both profiles list both names now. The case removes search from the
    # Platform copy.
    b, p = discovery.apply_case("lookup-only", served("demo"), discovery.platform_profile())
    report = profile_check.check(reg, b, p)
    assert LOOKUP in report["active"] and SEARCH not in report["active"]
    assert report["search_notice"] == "Search is not available with this agent"


def test_ac08b_3_each_answer_has_ucp_version_and_its_capability(cat: Cat) -> None:
    cases = (
        (cat.client.search(query="demo"), SEARCH),
        (cat.client.lookup(["demo_mug"]), LOOKUP),
        (cat.client.product("demo_mug"), LOOKUP),
    )
    for r, name in cases:
        assert r.status == 200 and r.schema_problems == []
        ucp = r.body["ucp"]
        assert ucp["version"] == V
        assert isinstance(ucp["capabilities"], dict)  # an object, not an array (U-50 item 4)
        assert list(ucp["capabilities"]) == [name]
        assert ucp["capabilities"][name] == [{"version": V}]


def test_ac08b_5_lookup_and_product_both_answer_200(cat: Cat) -> None:
    lookup = cat.raw("/catalog/lookup", {"ids": ["demo_tshirt"]})
    product = cat.raw("/catalog/product", {"id": "demo_tshirt"})
    assert lookup.status_code == 200 and lookup.json()["products"]
    assert product.status_code == 200 and product.json()["product"]["id"] == "prod_demo_tshirt"
    assert lookup.headers["content-type"].startswith("application/json")
    assert product.headers["content-type"].startswith("application/json")
