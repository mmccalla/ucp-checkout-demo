"""G2 and G3, S7: the 23 pinned catalog schema files (UCP 2026-04-08 at 9c9d6fc).

The files are the hosted bytes (`https://ucp.dev/2026-04-08/schemas/`). `$id` and each `$ref` have
the version path. Each file has a line in `pins/schema-manifest.sha256`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from ucp_core.constants import ROOT
from ucp_core.schema_registry import SchemaRegistry, read_manifest

BASE = "https://ucp.dev/2026-04-08/schemas/shopping"
FILES = [
    "shopping/catalog_lookup.json",
    "shopping/catalog_search.json",
    *[
        f"shopping/types/{n}.json"
        for n in (
            "category description detail_option_value input_correlation media "
            "media_external_video media_image media_model_3d media_source media_video "
            "option_value pagination price price_filter price_range product product_option "
            "rating search_filters selected_option variant"
        ).split()
    ],
]
PRICE = {"amount": 2000, "currency": "GBP"}
VARIANT = {
    "id": "demo_tshirt",
    "title": "Demo T-shirt",
    "description": {"plain": "A T-shirt."},
    "price": PRICE,
}
PRODUCT = {
    "id": "prod_demo_tshirt",
    "title": "Demo T-shirt",
    "description": {"plain": "A T-shirt."},
    "price_range": {"min": PRICE, "max": PRICE},
    "variants": [VARIANT],
}
UCP = {
    "version": "2026-04-08",
    "capabilities": {"dev.ucp.shopping.catalog.search": [{"version": "2026-04-08"}]},
}


@pytest.fixture(scope="module")
def reg() -> SchemaRegistry:
    return SchemaRegistry.load()


def test_there_are_23_catalog_files() -> None:
    assert len(FILES) == 23


@pytest.mark.parametrize("rel", FILES)
def test_catalog_file_agrees_with_manifest(rel: str) -> None:
    manifest = read_manifest(ROOT / "pins/schema-manifest.sha256")
    path = ROOT / "contracts/ucp-schemas" / rel
    assert manifest[f"ucp-schemas/{rel}"] == hashlib.sha256(path.read_bytes()).hexdigest()
    doc = json.loads(path.read_text())
    assert doc["$id"] == f"https://ucp.dev/2026-04-08/schemas/{rel}"
    assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_search_response_schema_accepts_a_valid_body(reg: SchemaRegistry) -> None:
    body = {"ucp": UCP, "products": [PRODUCT], "pagination": {"has_next_page": False}}
    assert reg.validate(body, f"{BASE}/catalog_search.json#/$defs/search_response") == []


def test_search_response_schema_refuses_a_price_without_currency(reg: SchemaRegistry) -> None:
    bad = json.loads(json.dumps(PRODUCT))
    del bad["variants"][0]["price"]["currency"]
    body = {"ucp": UCP, "products": [bad]}
    assert reg.validate(body, f"{BASE}/catalog_search.json#/$defs/search_response") != []


def test_search_response_schema_needs_cursor_when_next_page(reg: SchemaRegistry) -> None:
    body: dict[str, Any] = {"ucp": UCP, "products": [], "pagination": {"has_next_page": True}}
    assert reg.validate(body, f"{BASE}/catalog_search.json#/$defs/search_response") != []


def test_lookup_response_schema_needs_inputs(reg: SchemaRegistry) -> None:
    schema = f"{BASE}/catalog_lookup.json#/$defs/lookup_response"
    ucp = {"version": "2026-04-08"}
    assert reg.validate({"ucp": ucp, "products": [PRODUCT]}, schema) != []
    good = json.loads(json.dumps(PRODUCT))
    good["variants"][0]["inputs"] = [{"id": "demo_tshirt", "match": "exact"}]
    assert reg.validate({"ucp": ucp, "products": [good]}, schema) == []


def test_get_product_response_schema_needs_product(reg: SchemaRegistry) -> None:
    schema = f"{BASE}/catalog_lookup.json#/$defs/get_product_response"
    ucp = {"version": "2026-04-08"}
    assert reg.validate({"ucp": ucp, "product": PRODUCT}, schema) == []
    assert reg.validate({"ucp": ucp}, schema) != []
