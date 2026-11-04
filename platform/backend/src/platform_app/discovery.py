"""Platform discovery (FR-01 to FR-04, AC-01 to AC-09, AC-122).

The Platform gets the Business profile with `ucp_core.netguard.fetch_profile` (HTTPS, no
redirect, address guard before the connection), then checks it with `ucp_core.profile_check`.
The panel cases (`case=`) change a copy of the fetched profile. They make the AC-03, AC-05 and
AC-09 states visible on the live panel. They do not change the Business.
"""

from __future__ import annotations

import copy
import json
import os
import ssl
from typing import Any

from ucp_core import netguard, profile_check, tlsctx
from ucp_core.constants import LOOPBACK_HOST, ROOT, UCP_VERSION
from ucp_core.schema_registry import SchemaRegistry

PROFILE_FILE = ROOT / "platform" / "backend" / "profile" / "platform.json"
DEFAULT_BUSINESS_PROFILE = "https://localhost:9443/.well-known/ucp"
CASES = ("live", "malformed", "binding", "lookup-only")
V = UCP_VERSION


def platform_origin() -> str:
    return os.environ.get("PLATFORM_ORIGIN", "https://localhost:8443").rstrip("/")


def platform_profile(jwk: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the Platform profile. S2: add the public signing key (T-04, ADR 0006)."""
    text = PROFILE_FILE.read_text().replace("{{ORIGIN}}", platform_origin())
    profile: dict[str, Any] = json.loads(text)
    if jwk is not None:
        profile["signing_keys"] = [jwk]
    return profile


def business_origin() -> str:
    return os.environ.get("BUSINESS_ORIGIN", "https://localhost:9443").rstrip("/")


def tls_context() -> ssl.SSLContext | bool:
    """Trust the Caddy local CA for this process only (ucp_core.tlsctx, T-90)."""
    return tlsctx.client_context()


def _cat(name: str) -> dict[str, list[dict[str, Any]]]:
    return {
        f"dev.ucp.shopping.catalog.{name}": [
            {
                "version": V,
                "spec": f"https://ucp.dev/{V}/specification/catalog/{name}",
                "schema": f"https://ucp.dev/{V}/schemas/shopping/catalog_{name}.json",
            }
        ]
    }


def apply_case(
    case: str, business: dict[str, Any], platform: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    b, p = copy.deepcopy(business), copy.deepcopy(platform)
    if case == "malformed":  # AC-03
        b["ucp"].pop("payment_handlers", None)
    elif case == "binding":  # AC-05
        b["ucp"]["capabilities"]["dev.ucp.shopping.fulfillment"][0]["spec"] = (
            "https://example.com/2026-04-08/specification/fulfillment"
        )
    elif case == "lookup-only":  # AC-09: a Platform like Google's (lookup, no search)
        # S7: both profiles list both capabilities. This case removes search from the Platform.
        b["ucp"]["capabilities"].update(_cat("search") | _cat("lookup"))
        p["ucp"]["capabilities"].pop("dev.ucp.shopping.catalog.search", None)
        p["ucp"]["capabilities"].update(_cat("lookup"))
    return b, p


def discover(reg: SchemaRegistry, url: str | None = None, case: str = "live") -> dict[str, Any]:
    if case not in CASES:
        return {"ok": False, "error": "unknown case", "case": case}
    url = url or os.environ.get("BUSINESS_PROFILE_URL", DEFAULT_BUSINESS_PROFILE)
    out: dict[str, Any] = {"case": case, "url": url}
    try:
        f = netguard.fetch_profile(url, LOOPBACK_HOST, verify=tls_context())
    except netguard.BlockedAddress as e:
        return out | {"ok": False, "error": "address_refused", "detail": str(e)}
    except netguard.FetchError as e:
        return out | {"ok": False, "error": e.code, "detail": e.detail}
    out["resolved"] = f.resolved
    out["redirects"] = 0
    b, p = apply_case(case, f.body, platform_profile())
    try:
        report = profile_check.check(reg, b, p, f.headers)
    except profile_check.ProfileMalformed as e:
        return out | {"ok": False, "error": "profile_malformed", "detail": str(e)}
    return out | {"ok": True} | report
