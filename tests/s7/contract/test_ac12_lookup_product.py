"""G4 contract, S7: batch lookup and Get Product, AC-12.11 to AC-12.15 (spec v1.1.17).

Source: UCP 2026-04-08 at 9c9d6fc, `docs/specification/catalog/lookup.md`, `rest.md`,
`index.md` and the pinned schemas `catalog_lookup.json` and `types/error_response.json`.
"""

from __future__ import annotations

from typing import Any

from tests.s7.conftest import Cat


def variants(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [v for p in body["products"] for v in p["variants"]]


def test_ac12_11_product_id_and_variant_id_of_another_product(cat: Cat) -> None:
    r = cat.client.lookup(["prod_demo_tshirt", "demo_mug"])
    assert r.status == 200 and r.schema_problems == []
    assert sorted(p["id"] for p in r.body["products"]) == ["prod_demo_mug", "prod_demo_tshirt"]
    by_input: dict[str, str] = {}
    for p in r.body["products"]:
        assert "description" in p and len(p["variants"]) >= 1
        for v in p["variants"]:
            assert len(v["inputs"]) >= 1
            for i in v["inputs"]:
                by_input[i["id"]] = i["match"]
    assert by_input == {"prod_demo_tshirt": "featured", "demo_mug": "exact"}


def test_ac12_11_two_ids_for_one_product_give_the_product_once(cat: Cat) -> None:
    r = cat.client.lookup(["prod_demo_tshirt", "demo_tshirt", "demo_tshirt"])
    assert r.status == 200 and r.schema_problems == []
    assert [p["id"] for p in r.body["products"]] == ["prod_demo_tshirt"]
    (v,) = variants(r.body)
    assert sorted((i["id"], i["match"]) for i in v["inputs"]) == [
        ("demo_tshirt", "exact"),
        ("prod_demo_tshirt", "featured"),
    ]  # the duplicate id is removed


def test_ac12_11_ids_need_at_least_one_item(cat: Cat) -> None:
    assert cat.raw("/catalog/lookup", {"ids": []}).status_code == 400
    assert cat.raw("/catalog/lookup", {}).status_code == 400


def test_ac12_12_known_and_unknown_id(cat: Cat) -> None:
    r = cat.client.lookup(["demo_mug", "prod_unknown"])
    assert r.status == 200 and r.schema_problems == []
    assert [p["id"] for p in r.body["products"]] == ["prod_demo_mug"]
    for m in r.body.get("messages", []):  # the messages are optional (MAY)
        assert m["type"] == "info" and m["code"] == "not_found"
        assert m["content"] == "prod_unknown" and "severity" not in m


def test_ac12_12_all_ids_unknown(cat: Cat) -> None:
    r = cat.client.lookup(["a", "b"])
    assert r.status == 200 and r.schema_problems == []
    assert r.body["products"] == []
    assert [m["content"] for m in r.body.get("messages", [])] == ["a", "b"]


def test_ac12_13_batch_maximum_is_10(cat: Cat) -> None:
    too_many = cat.raw("/catalog/lookup", {"ids": [f"x{i}" for i in range(11)]})
    assert too_many.status_code == 400
    assert "request_too_large" in too_many.text
    ok = cat.client.lookup([f"x{i}" for i in range(10)])
    assert ok.status == 200 and ok.body["products"] == []


def test_ac12_13_the_client_sends_the_batch_it_is_given(cat: Cat) -> None:
    r = cat.client.lookup([f"x{i}" for i in range(11)])
    assert r.status == 400 and "request_too_large" in str(r.body)


def test_lookup_filters_apply_after_resolution(cat: Cat) -> None:
    r = cat.client.lookup(["demo_tshirt", "demo_mug"], filters={"price": {"max": 1500}})
    assert [p["id"] for p in r.body["products"]] == ["prod_demo_mug"]
    assert r.schema_problems == []


def test_ac12_14_get_product_by_product_id(cat: Cat) -> None:
    r = cat.client.product("prod_demo_tshirt")
    assert r.status == 200 and r.schema_problems == []
    assert "ucp" in r.body and isinstance(r.body["product"], dict)
    p = r.body["product"]
    assert "description" in p and len(p["variants"]) >= 1
    assert p["variants"][0]["id"] == "demo_tshirt"  # the featured variant
    assert "selected" not in p  # the demo product has no configurable option


def test_ac12_14_get_product_by_variant_id_has_the_variant_first(cat: Cat) -> None:
    r = cat.client.product("demo_mug")
    assert r.status == 200 and r.schema_problems == []
    assert r.body["product"]["id"] == "prod_demo_mug"
    assert r.body["product"]["variants"][0]["id"] == "demo_mug"


def test_ac12_14_selected_and_preferences_are_optional(cat: Cat) -> None:
    r = cat.client.product(
        "demo_tshirt", selected=[{"name": "Size", "label": "M"}], preferences=["Size"]
    )
    assert r.status == 200 and r.schema_problems == []
    assert r.body["product"]["variants"][0]["id"] == "demo_tshirt"


def test_ac12_15_unknown_id_gives_status_error_not_found(cat: Cat) -> None:
    r = cat.client.product("prod_invalid")
    assert r.status == 200
    assert r.schema_problems == []  # valid `error_response` (rest.openapi.json 1019 to 1024)
    assert r.body["ucp"]["status"] == "error"
    assert "product" not in r.body
    errors = [m for m in r.body["messages"] if m["type"] == "error"]
    assert len(errors) == 1
    assert errors[0]["code"] == "not_found"
    # Severity `recoverable` (index.md line 244, U-50 item 1). rest.md line 567 shows
    # `unrecoverable`. The ruling of the project owner on 28 Oct 2026 and spec v1.1.17 choose
    # `recoverable`.
    assert errors[0]["severity"] == "recoverable"
    assert "prod_invalid" in errors[0]["content"]


def test_get_product_needs_an_id(cat: Cat) -> None:
    assert cat.raw("/catalog/product", {}).status_code == 400
