"""Check a fetched Business profile and negotiate with the Platform profile.

Covers AC-02 (cache), AC-03 (malformed), AC-04 (version), AC-05 (binding), AC-06 (REST),
AC-08 (a), AC-09, AC-92, AC-96. The result is a plain dict for the discovery panel.
"""

from __future__ import annotations

from typing import Any

from . import gpay_config, negotiation
from .constants import GPAY_HANDLER, SHOPPING_SERVICE, UCP_SCHEMA_BASE, UCP_VERSION
from .netguard import cache_control_ok
from .schema_registry import SchemaRegistry

PROFILE_SCHEMA = UCP_SCHEMA_BASE + "discovery/profile.json"
SEARCH = "dev.ucp.shopping.catalog.search"
LOOKUP = "dev.ucp.shopping.catalog.lookup"
SEARCH_NOTICE = "Search is not available with this agent"


class ProfileMalformed(Exception):
    """The Platform stops discovery and shows "profile malformed" (AC-03)."""


def schema_issues(reg: SchemaRegistry, profile: dict[str, Any], def_name: str) -> list[str]:
    url = f"{PROFILE_SCHEMA}#/$defs/{def_name}"
    return [f"{i.path}: {i.message}" for i in reg.validate(profile, url)]


def check(
    reg: SchemaRegistry,
    business: dict[str, Any],
    platform: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    ucp = business.get("ucp")
    if not isinstance(ucp, dict) or "payment_handlers" not in ucp:
        raise ProfileMalformed("profile malformed: no ucp.payment_handlers")
    issues = schema_issues(reg, business, "business_profile")
    if issues:
        raise ProfileMalformed("profile malformed: " + "; ".join(issues[:5]))
    report: dict[str, Any] = {"ucp_version": ucp.get("version")}
    if ucp.get("version") != UCP_VERSION:
        raise ProfileMalformed(f"profile version {ucp.get('version')} is not {UCP_VERSION}")
    report["selected_version"] = UCP_VERSION
    if headers is not None:
        cc_ok, cc_detail = cache_control_ok(headers.get("cache-control"))
        report["cache_control"] = {"ok": cc_ok, "detail": cc_detail}

    rest = [
        s
        for s in ucp.get("services", {}).get(SHOPPING_SERVICE, [])
        if s.get("transport") == "rest" and s.get("version") == UCP_VERSION
    ]
    report["transport"] = "REST" if rest else None
    report["endpoint"] = rest[0].get("endpoint") if rest else None
    report["services"] = sorted(ucp.get("services", {}))

    unbound: dict[str, list[str]] = {}
    caps: dict[str, list[dict[str, Any]]] = {}
    for name, entries in ucp.get("capabilities", {}).items():
        ok_entries = []
        for e in entries:
            issues = negotiation.binding_issues(name, e)
            if issues:
                unbound.setdefault(name, []).extend(issues)
            else:
                ok_entries.append(e)
        if ok_entries:
            caps[name] = ok_entries
    pcaps = platform.get("ucp", {}).get("capabilities", {})
    active, excluded = negotiation.intersect(caps, pcaps)
    for name, found in unbound.items():
        if name not in active:
            excluded[name] = "binding: " + "; ".join(found)
    report["active"] = sorted(active)
    report["excluded"] = dict(sorted(excluded.items()))
    report["search_notice"] = SEARCH_NOTICE if LOOKUP in active and SEARCH not in active else None

    handlers: dict[str, Any] = {}
    for name, entries in ucp.get("payment_handlers", {}).items():
        for e in entries:
            reasons = negotiation.binding_issues(name, e)
            if name == GPAY_HANDLER:
                reasons += gpay_config.check_declaration(e)
                if isinstance(e.get("config"), dict):
                    reasons += [
                        f"config {i.path}: {i.message}"
                        for i in gpay_config.validate_config(reg, e["config"])
                    ]
            handlers[f"{name}#{e.get('id')}"] = {
                "used": not reasons,
                "reasons": reasons,
                "environment": (e.get("config") or {}).get("environment"),
            }
    report["payment_handlers"] = handlers
    return report
