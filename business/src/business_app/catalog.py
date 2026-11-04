"""Catalog search, batch lookup and Get Product (S7 v1, DM-11, AC-08b, AC-12).

Source: UCP 2026-04-08 at commit 9c9d6fc (https://ucp.dev/2026-04-08/specification/catalog/).
Each path below is `<file>:<line>` in that source tree.

- REST paths: `POST /catalog/search`, `POST /catalog/lookup`, `POST /catalog/product`
  (docs/specification/catalog/rest.md:64-66). If Lookup is advertised, both lookup paths MUST
  exist (rest.md:659).
- Request and response shapes are the pinned schemas `catalog_search.json` and
  `catalog_lookup.json` (`$defs` `search_request`, `search_response`, `lookup_request`,
  `lookup_response`, `get_product_request`, `get_product_response`).
- A response has the `ucp` envelope with `version` and `capabilities` (ucp.json:277-292,
  overview.md:751-754).
- Business outcomes use HTTP 200 (rest.md:598-600). A request that is not valid is HTTP 400
  (rest.md:587-596). The 400 body is `error_response` with `invalid_request`
  (UNVERIFIED: the pin has no schema for the 400 body, G-09 of docs/S7-catalog-reading.md).
- Catalog errors use `severity` `recoverable` (catalog/index.md:244). Ruling of the Chief of
  Staff (28 Oct 2026, 20:53 GMT): this holds also for `not_found` of Get Product. The text of
  rest.md:567 shows `unrecoverable`. Precedence: schema, then normative prose, then examples.
- Price filter bounds are inclusive (UNVERIFIED: the pin does not say).
- Limits are PROPOSED values (spec U-53): default page 10 (pagination.json:12-21), maximum
  page `MAX_LIMIT`, maximum batch `MAX_BATCH` (lookup.md:76-79: at least 10).
- A call to a capability that is not active (T-119, AC-08b-6, U-54): HTTP 200 and `ucp.status`
  `error`, with one `error` message. The code is `capabilities_incompatible` and the severity is
  `recoverable`. Sources: overview.md:789-798 and :810 (HTTP 200 for this code, "UCP response")
  and overview.md:2205-2208 ("MUST return a `capabilities_incompatible` error").
  UNVERIFIED: the pin does not show a catalog example. Search and lookup bodies also keep
  `products: []` (catalog_search.json:33-61, catalog_lookup.json:52-86). A Get Product body is an
  `error_response` and has no `product` (rest.openapi.json:1019-1024, error_response.json:7-27).
  Severity: catalog/index.md:244 (all catalog errors are `recoverable`).
"""

from __future__ import annotations

import base64
import binascii
import json
import pathlib
import sqlite3
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from ucp_core import negotiation
from ucp_core.constants import ROOT, UCP_VERSION
from ucp_core.schema_registry import SchemaRegistry

from . import errors

SEARCH = "dev.ucp.shopping.catalog.search"
LOOKUP = "dev.ucp.shopping.catalog.lookup"
SCHEMA_BASE = f"https://ucp.dev/{UCP_VERSION}/schemas/shopping"
SEARCH_SCHEMA = f"{SCHEMA_BASE}/catalog_search.json"
LOOKUP_SCHEMA = f"{SCHEMA_BASE}/catalog_lookup.json"
TEXT_FILE = ROOT / "business" / "data" / "catalog" / "demo.json"
DEFAULT_LIMIT = 10  # pagination.json:12-21
MAX_LIMIT = 20  # PROPOSED (U-53)
MAX_BATCH = 10  # PROPOSED (U-53). lookup.md:76-79: at least 10.
CURRENCY = "GBP"  # the shop trades in GBP (sample config DEFAULT_CURRENCY)


def _ucp(capability: str, status: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "version": UCP_VERSION,
        "capabilities": {capability: [{"version": UCP_VERSION}]},
    }
    if status:
        out["status"] = status
    return out


def _texts(path: pathlib.Path = TEXT_FILE) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text())
    texts = data.get("products", {})
    assert isinstance(texts, dict)
    return texts


def load_products(products_db: str, transactions_db: str) -> list[dict[str, Any]]:
    """Build the pinned `product` objects from the product and inventory tables."""
    texts = _texts()
    con = sqlite3.connect(f"file:{products_db}?mode=ro", uri=True, timeout=1.0)
    try:
        rows = con.execute(
            "SELECT id, title, price, image_url FROM products ORDER BY id"
        ).fetchall()
    finally:
        con.close()
    con = sqlite3.connect(f"file:{transactions_db}?mode=ro", uri=True, timeout=1.0)
    try:
        stock = dict(con.execute("SELECT product_id, quantity FROM inventory").fetchall())
    finally:
        con.close()
    out: list[dict[str, Any]] = []
    for item_id, title, price, image_url in rows:
        t = texts.get(item_id, {})
        text = {"plain": t.get("description") or title}
        media = [{"type": "image", "url": image_url, "alt_text": title}] if image_url else []
        in_stock = int(stock.get(item_id, 0)) > 0
        variant: dict[str, Any] = {
            "id": item_id,  # the checkout item id (index.md:47-49, variant.json:16)
            "title": title,
            "description": text,
            "price": {"amount": int(price), "currency": CURRENCY},
            # AC-12.9: the Business always sends `availability`.
            "availability": {
                "available": in_stock,
                "status": "in_stock" if in_stock else "out_of_stock",
            },
        }
        product: dict[str, Any] = {
            "id": t.get("product_id") or f"prod_{item_id}",
            "title": title,
            "description": text,
            "categories": [{"value": v, "taxonomy": "merchant"} for v in t.get("categories", [])],
            "price_range": {"min": variant["price"], "max": variant["price"]},
            "variants": [variant],
        }
        if t.get("handle"):
            product["handle"] = t["handle"]
        if media:
            product["media"] = media
            variant["media"] = media
        out.append(product)
    return out


def _price_ok(variant: dict[str, Any], price_filter: dict[str, Any] | None) -> bool:
    if not price_filter:
        return True
    amount = variant["price"]["amount"]
    lo, hi = price_filter.get("min"), price_filter.get("max")
    return (lo is None or amount >= lo) and (hi is None or amount <= hi)


def _narrow(product: dict[str, Any], filters: dict[str, Any] | None) -> dict[str, Any] | None:
    """Apply the filters (AND between filters, OR between categories). None: no match."""
    if not filters:
        return product
    wanted = [c.lower() for c in filters.get("categories") or []]
    if wanted and not any(c["value"].lower() in wanted for c in product.get("categories", [])):
        return None
    variants = [v for v in product["variants"] if _price_ok(v, filters.get("price"))]
    if not variants:
        return None
    out = dict(product)
    out["variants"] = variants
    prices = sorted((v["price"] for v in variants), key=lambda p: p["amount"])
    out["price_range"] = {"min": prices[0], "max": prices[-1]}
    return out


def _words_match(product: dict[str, Any], query: str) -> bool:
    hay = " ".join(
        [
            product["title"],
            product["description"].get("plain", ""),
            product.get("handle", ""),
            *[c["value"] for c in product.get("categories", [])],
            *[v["title"] for v in product["variants"]],
        ]
    ).lower()
    return all(word in hay for word in query.lower().split())


def _has_input(body: dict[str, Any]) -> bool:
    """search.md:40-51: at least one recognized input (a `query` or a `filters` value)."""
    query = body.get("query")
    if isinstance(query, str) and query.strip():
        return True
    f = body.get("filters")
    if not isinstance(f, dict):
        return False
    price = f.get("price")
    return bool(f.get("categories")) or (
        isinstance(price, dict) and ("min" in price or "max" in price)
    )


def _cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode().rstrip("=")


def _offset(cursor: str) -> int | None:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None
    if raw.startswith("o:") and raw[2:].isdigit():
        return int(raw[2:])
    return None


def search(
    products: list[dict[str, Any]], body: dict[str, Any]
) -> tuple[dict[str, Any], int] | None:
    """The search result as (response body, status). None: a request that is not valid."""
    hits = []
    query = body.get("query")
    for p in products:
        if isinstance(query, str) and query.strip() and not _words_match(p, query):
            continue
        narrowed = _narrow(p, body.get("filters"))
        if narrowed is not None:
            hits.append(narrowed)
    page = body.get("pagination") or {}
    limit = min(int(page.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)  # clamp: no error (G-11)
    offset = 0
    if page.get("cursor") is not None:
        found = _offset(str(page["cursor"]))
        if found is None:
            return None
        offset = found
    chunk = hits[offset : offset + limit]
    more = offset + limit < len(hits)
    pagination: dict[str, Any] = {"has_next_page": more, "total_count": len(hits)}
    if more:
        pagination["cursor"] = _cursor(offset + limit)
    return {"ucp": _ucp(SEARCH), "products": chunk, "pagination": pagination}, 200


def _resolve(products: list[dict[str, Any]], ident: str) -> tuple[dict[str, Any], str, str] | None:
    """Resolve an id to (product, variant id, match). lookup.md:83-88: exact or featured."""
    for p in products:
        for v in p["variants"]:
            if v["id"] == ident:
                return p, v["id"], "exact"
    for p in products:
        if p["id"] == ident:
            return p, p["variants"][0]["id"], "featured"
    return None


def lookup(products: list[dict[str, Any]], body: dict[str, Any]) -> dict[str, Any]:
    """Batch lookup (lookup.md:51-59). Unknown ids give an info `not_found` message."""
    ids = list(dict.fromkeys(body["ids"]))  # duplicates are removed (lookup.md:51-53)
    found: dict[str, dict[str, Any]] = {}  # product id -> product with variants and inputs
    messages: list[dict[str, Any]] = []
    for ident in ids:
        hit = _resolve(products, ident)
        if hit is None:
            messages.append({"type": "info", "code": "not_found", "content": ident})
            continue
        product, variant_id, match = hit
        entry = found.setdefault(product["id"], {"product": product, "inputs": {}})
        entry["inputs"].setdefault(variant_id, []).append({"id": ident, "match": match})
    out: list[dict[str, Any]] = []
    for entry in found.values():
        p = _narrow(entry["product"], body.get("filters"))
        if p is None:
            continue
        variants = [
            dict(v, inputs=entry["inputs"][v["id"]])
            for v in p["variants"]
            if v["id"] in entry["inputs"]  # no inputs, no variant (lookup.md:61-72)
        ]
        if not variants:
            continue
        out.append(dict(p, variants=variants))
    resp: dict[str, Any] = {"ucp": _ucp(LOOKUP), "products": out}
    if messages:
        resp["messages"] = messages
    return resp


def get_product(products: list[dict[str, Any]], body: dict[str, Any]) -> dict[str, Any]:
    """Get Product (lookup.md:118-168). Not found: `ucp.status` error (rest.md:549-579)."""
    ident = body["id"]
    hit = _resolve(products, ident)
    product = _narrow(hit[0], body.get("filters")) if hit else None
    if hit is None or product is None:
        text = f"Product not found: {ident}"
        return {
            "ucp": _ucp(LOOKUP, "error"),
            "messages": [errors.message("not_found", text, "recoverable")],
        }
    _, variant_id, _match = hit
    variants = sorted(product["variants"], key=lambda v: v["id"] != variant_id)
    # No option axes, so `selected` is omitted (catalog_lookup.json:87-94, lookup.md:164-168).
    return {"ucp": _ucp(LOOKUP), "product": dict(product, variants=variants)}


def inactive_answer(capability: str, empty_list: bool) -> JSONResponse:
    """T-119: HTTP 200, `ucp.status` error and `capabilities_incompatible` (recoverable)."""
    text = f"The capability {capability} is not active for this request."
    body: dict[str, Any] = {
        "ucp": {"version": UCP_VERSION, "status": "error"},
        "messages": [errors.message("capabilities_incompatible", text, "recoverable")],
    }
    if empty_list:
        body["products"] = []
    return JSONResponse(body, status_code=200)


def make_router(
    products_db: str,
    transactions_db: str,
    registry: SchemaRegistry,
    business_capabilities: dict[str, list[dict[str, Any]]] | None = None,
) -> APIRouter:
    """`business_capabilities` is the `ucp.capabilities` of the Business profile.

    With `None`, the router does not check capability activity (older callers).
    """
    router = APIRouter()

    def is_active(request: Request, capability: str) -> bool:
        if business_capabilities is None:
            return True
        platform = getattr(request.state, "ucp_platform_capabilities", None)
        if platform is None:
            return True  # the Gate did not run: no Platform profile to compare
        active, _excluded = negotiation.intersect(business_capabilities, platform)
        return capability in active

    async def read(request: Request, schema: str) -> dict[str, Any] | JSONResponse:
        try:
            body = json.loads(await request.body() or b"null")
        except ValueError:
            return errors.invalid_request([("$", "The body is not JSON.")])
        issues = registry.validate(body, schema)
        if issues:
            return errors.invalid_request([(i.path, i.message) for i in issues])
        assert isinstance(body, dict)
        return body

    @router.post("/catalog/search")
    async def post_search(request: Request) -> JSONResponse:
        if not is_active(request, SEARCH):
            return inactive_answer(SEARCH, empty_list=True)
        body = await read(request, f"{SEARCH_SCHEMA}#/$defs/search_request")
        if isinstance(body, JSONResponse):
            return body
        if not _has_input(body):
            return errors.invalid_request(
                [("$", "A search needs a query or a filter (search.md:40-51).")]
            )
        done = search(load_products(products_db, transactions_db), body)
        if done is None:
            return errors.invalid_request([("$.pagination.cursor", "The cursor is not valid.")])
        return JSONResponse(done[0], status_code=done[1])

    @router.post("/catalog/lookup")
    async def post_lookup(request: Request) -> JSONResponse:
        if not is_active(request, LOOKUP):
            return inactive_answer(LOOKUP, empty_list=True)
        body = await read(request, f"{LOOKUP_SCHEMA}#/$defs/lookup_request")
        if isinstance(body, JSONResponse):
            return body
        if len(body["ids"]) > MAX_BATCH:
            return errors.error_response(
                [
                    errors.message(
                        "request_too_large",
                        f"A request can have at most {MAX_BATCH} identifiers.",
                        "recoverable",
                        "$.ids",
                    )
                ],
                status=400,
            )
        return JSONResponse(lookup(load_products(products_db, transactions_db), body))

    @router.post("/catalog/product")
    async def post_product(request: Request) -> JSONResponse:
        if not is_active(request, LOOKUP):
            return inactive_answer(LOOKUP, empty_list=False)
        body = await read(request, f"{LOOKUP_SCHEMA}#/$defs/get_product_request")
        if isinstance(body, JSONResponse):
            return body
        return JSONResponse(get_product(load_products(products_db, transactions_db), body))

    return router
