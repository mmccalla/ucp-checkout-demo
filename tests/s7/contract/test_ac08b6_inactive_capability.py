"""G4 contract, S7: AC-08b-6 (T-119). A call to a capability that is not active.

Spec v1.1.18, section AC-08 (b). The rule: the Business gives HTTP 200, `ucp.status` "error" and
one `error` message. The code is `capabilities_incompatible`. The severity is `recoverable`.
Search and lookup bodies keep `products: []`. A Get Product body is an `error_response` with no
`product`.

Sources (UCP 2026-04-08, commit 9c9d6fc): overview.md:789-798, :810 and :2205-2208;
catalog_search.json:33-61; catalog_lookup.json:52-86; rest.openapi.json:1019-1024;
error_response.json:7-27; catalog/index.md:244.
UNVERIFIED (U-54): the pin has no catalog example of this answer. The use of overview.md:2205-2208
for the catalog is an inference.
"""

from __future__ import annotations

import copy
import pathlib
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from business_app import profile as business_profile
from platform_app.catalog_client import LOOKUP, SEARCH
from ucp_core.schema_registry import SchemaRegistry

from tests.s2.conftest import PROFILE_URL, Pair, make_pair

BASE = "https://ucp.dev/2026-04-08/schemas/shopping"
SEARCH_BODY = {"query": "mug"}
LOOKUP_BODY = {"ids": ["prod_demo_mug"]}
PRODUCT_BODY = {"id": "prod_demo_mug"}


@pytest.fixture(scope="module")
def reg() -> SchemaRegistry:
    return SchemaRegistry.load()


def drop(name: str) -> Callable[[dict[str, Any]], None]:
    def edit(profile: dict[str, Any]) -> None:
        del profile["ucp"]["capabilities"][name]

    return edit


@pytest.fixture
def business_without_search(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Pair]:
    """AC-08b-4: a Business test profile with lookup and no search. The Platform has both."""
    real = business_profile.build

    def build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        body = copy.deepcopy(real(*args, **kwargs))
        drop(SEARCH)(body)
        return body

    monkeypatch.setattr(business_profile, "build", build)
    yield from make_pair(tmp_path, monkeypatch)


@pytest.fixture
def business_without_lookup(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Pair]:
    real = business_profile.build

    def build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        body = copy.deepcopy(real(*args, **kwargs))
        drop(LOOKUP)(body)
        return body

    monkeypatch.setattr(business_profile, "build", build)
    yield from make_pair(tmp_path, monkeypatch)


@pytest.fixture
def platform_without_lookup(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Pair]:
    yield from make_pair(tmp_path, monkeypatch, profile_edit=drop(LOOKUP))


@pytest.fixture
def platform_without_search(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Pair]:
    yield from make_pair(tmp_path, monkeypatch, profile_edit=drop(SEARCH))


@pytest.fixture
def both_active(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Pair]:
    yield from make_pair(tmp_path, monkeypatch)


def post(pair: Pair, path: str, body: dict[str, Any]) -> Any:
    h = {"UCP-Agent": f'profile="{PROFILE_URL}"', "Request-Id": "rid-t119"}
    return pair.biz.post(path, json=body, headers=h)


def one_incompatible(body: dict[str, Any]) -> None:
    (msg,) = body["messages"]
    assert msg["type"] == "error"
    assert msg["code"] == "capabilities_incompatible"
    assert msg["severity"] == "recoverable"  # catalog/index.md:244 (U-50: not `unrecoverable`)
    assert body["ucp"]["status"] == "error"


def test_ac08b_6_search_not_active_business(
    business_without_search: Pair, reg: SchemaRegistry
) -> None:
    r = post(business_without_search, "/catalog/search", SEARCH_BODY)
    assert r.status_code == 200
    body = r.json()
    one_incompatible(body)
    assert body["products"] == []
    assert reg.validate(body, f"{BASE}/catalog_search.json#/$defs/search_response") == []


def test_ac08b_6_search_not_active_platform(
    platform_without_search: Pair, reg: SchemaRegistry
) -> None:
    r = post(platform_without_search, "/catalog/search", SEARCH_BODY)
    assert r.status_code == 200
    body = r.json()
    one_incompatible(body)
    assert body["products"] == []
    assert reg.validate(body, f"{BASE}/catalog_search.json#/$defs/search_response") == []


def test_ac08b_6_lookup_not_active_business(
    business_without_lookup: Pair, reg: SchemaRegistry
) -> None:
    r = post(business_without_lookup, "/catalog/lookup", LOOKUP_BODY)
    assert r.status_code == 200
    body = r.json()
    one_incompatible(body)
    assert body["products"] == []
    assert reg.validate(body, f"{BASE}/catalog_lookup.json#/$defs/lookup_response") == []


def test_ac08b_6_lookup_not_active_platform(
    platform_without_lookup: Pair, reg: SchemaRegistry
) -> None:
    r = post(platform_without_lookup, "/catalog/lookup", LOOKUP_BODY)
    assert r.status_code == 200
    body = r.json()
    one_incompatible(body)
    assert body["products"] == []
    assert reg.validate(body, f"{BASE}/catalog_lookup.json#/$defs/lookup_response") == []


def test_ac08b_6_get_product_is_an_error_response_with_no_product(
    platform_without_lookup: Pair, reg: SchemaRegistry
) -> None:
    r = post(platform_without_lookup, "/catalog/product", PRODUCT_BODY)
    assert r.status_code == 200
    body = r.json()
    one_incompatible(body)
    assert "product" not in body and "products" not in body
    assert reg.validate(body, f"{BASE}/types/error_response.json") == []


def test_ac08b_6_the_other_capability_still_works(business_without_search: Pair) -> None:
    """AC-08b-4: with lookup active and search not active, lookup and Get Product answer."""
    r = post(business_without_search, "/catalog/lookup", LOOKUP_BODY)
    assert r.status_code == 200 and r.json()["ucp"].get("status") != "error"
    assert [p["id"] for p in r.json()["products"]] == ["prod_demo_mug"]
    r = post(business_without_search, "/catalog/product", PRODUCT_BODY)
    assert r.status_code == 200 and r.json()["product"]["id"] == "prod_demo_mug"


def test_ac08b_6_both_active_is_not_an_error(both_active: Pair) -> None:
    for path, body in (("/catalog/search", SEARCH_BODY), ("/catalog/product", PRODUCT_BODY)):
        r = post(both_active, path, body)
        assert r.status_code == 200
        assert not any(
            m["code"] == "capabilities_incompatible" for m in r.json().get("messages", [])
        )


def test_ac08b_6_check_comes_before_body_check(business_without_search: Pair) -> None:
    """A body that is not valid, sent to an inactive path, also gets the T-119 answer."""
    r = post(business_without_search, "/catalog/search", {})  # no `query`: not a valid request
    assert r.status_code == 200
    body = r.json()
    one_incompatible(body)
    assert body["products"] == []
