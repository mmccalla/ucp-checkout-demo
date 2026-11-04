"""Platform client for the catalog operations (S7 v1, DM-11, AC-12).

Source: UCP 2026-04-08 at commit 9c9d6fc, https://ucp.dev/2026-04-08/specification/catalog/rest/
(file `docs/specification/catalog/rest.md`).

- Paths: `POST /catalog/search`, `POST /catalog/lookup`, `POST /catalog/product`
  (rest.md:64-66).
- Headers: `UCP-Agent` and `Request-Id` (a UUID). No `Idempotency-Key`: the catalog operations do
  not list it (rest.openapi.json:564-720, 863, 882). The client signs the request as the
  checkout client does (T-04). The Business does not require the signature for these paths.
- AC-12.10: if search is not active, `search()` sends nothing and raises `CapabilityNotActive`.
  The text for the buyer is `ucp_core.profile_check.search_notice`.
- T-119, U-54: the same holds for `lookup()` and `product()` when lookup is not active.
  The Platform sends no request to a capability that is not active.
  UNVERIFIED (U-54): the pin has no rule for the Platform side. This is a demo rule.
- The client checks each 200 response against the pinned schemas (`catalog_search.json`,
  `catalog_lookup.json`, `types/error_response.json`). A failed check is in `schema_problems`.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from ucp_core.constants import UCP_VERSION
from ucp_core.schema_registry import SchemaRegistry

from .checkout_client import CheckoutClient, Result

SEARCH = "dev.ucp.shopping.catalog.search"
LOOKUP = "dev.ucp.shopping.catalog.lookup"
_BASE = f"https://ucp.dev/{UCP_VERSION}/schemas/shopping"
SCHEMAS = {
    "search": f"{_BASE}/catalog_search.json#/$defs/search_response",
    "lookup": f"{_BASE}/catalog_lookup.json#/$defs/lookup_response",
    "product": f"{_BASE}/catalog_lookup.json#/$defs/get_product_response",
}
ERROR_SCHEMA = f"{_BASE}/types/error_response.json"
_registry: SchemaRegistry | None = None


class CapabilityNotActive(Exception):
    """The capability is not active, so the Platform sends no request (AC-12.10)."""

    def __init__(self, capability: str):
        super().__init__(f"{capability} is not active")
        self.capability = capability


def _reg() -> SchemaRegistry:
    global _registry
    if _registry is None:
        _registry = SchemaRegistry.load()
    return _registry


class CatalogClient(CheckoutClient):
    idempotent = False

    def __init__(self, *args: Any, active: Collection[str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active = frozenset(active or ())

    def search(
        self,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        pagination: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Result:
        if SEARCH not in self.active:
            raise CapabilityNotActive(SEARCH)  # AC-12.10: no POST /catalog/search
        body = _drop_none(
            {"query": query, "filters": filters, "pagination": pagination, "context": context}
        )
        return self._send("search", "POST", "/catalog/search", body)

    def lookup(
        self,
        ids: list[str],
        filters: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Result:
        if LOOKUP not in self.active:
            raise CapabilityNotActive(LOOKUP)  # T-119: no POST /catalog/lookup
        body = _drop_none({"ids": ids, "filters": filters, "context": context})
        return self._send("lookup", "POST", "/catalog/lookup", body)

    def product(
        self,
        ident: str,
        selected: list[dict[str, Any]] | None = None,
        preferences: list[str] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> Result:
        if LOOKUP not in self.active:
            raise CapabilityNotActive(LOOKUP)  # T-119: no POST /catalog/product
        body = _drop_none(
            {"id": ident, "selected": selected, "preferences": preferences, "filters": filters}
        )
        return self._send("product", "POST", "/catalog/product", body)

    @staticmethod
    def _check(op: str, res: Result) -> list[str]:
        if not (res.ok and isinstance(res.body, dict)) or op not in SCHEMAS:
            return []
        status = (res.body.get("ucp") or {}).get("status")
        # rest.openapi.json:1019-1024: a Get Product answer is a product answer or an
        # `error_response`. A search or lookup answer with an error status also fits that body.
        schema = ERROR_SCHEMA if status == "error" and op == "product" else SCHEMAS[op]
        return [f"{i.path}: {i.message}" for i in _reg().validate(res.body, schema)]


def _drop_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}
