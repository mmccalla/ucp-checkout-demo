"""AC-02 to AC-06, AC-08 (a), AC-09, AC-96: checks on the served Business profile (in process)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from business_app import profile as bprofile
from platform_app import discovery
from ucp_core import jwk, profile_check
from ucp_core.schema_registry import SchemaRegistry

HEADERS = {"cache-control": "public, max-age=300"}


def business(mode: str = "demo") -> dict[str, Any]:
    return bprofile.build(mode, jwk.public_jwk(jwk.ephemeral()), "https://localhost:9443")


def run(reg: SchemaRegistry, case: str = "live", b: dict[str, Any] | None = None) -> Any:
    bb, pp = discovery.apply_case(case, b or business(), discovery.platform_profile())
    return profile_check.check(reg, bb, pp, HEADERS)


def test_live_profile(reg: SchemaRegistry) -> None:
    r = run(reg)
    assert r["ucp_version"] == r["selected_version"] == "2026-04-08"  # AC-04
    assert r["transport"] == "REST"  # AC-06
    assert r["active"] == [  # AC-08 (a); the two catalog names are AC-08b-2 (S7)
        "dev.ucp.shopping.catalog.lookup",
        "dev.ucp.shopping.catalog.search",
        "dev.ucp.shopping.checkout",
        "dev.ucp.shopping.fulfillment",
        "dev.ucp.shopping.order",
    ]
    gp = r["payment_handlers"]["com.google.pay#gpay_demo_test_01"]
    assert gp == {"used": True, "reasons": [], "environment": "TEST"}  # AC-02
    assert r["cache_control"]["ok"] is True


def test_ac03_no_payment_handlers_is_malformed(reg: SchemaRegistry) -> None:
    with pytest.raises(profile_check.ProfileMalformed, match="profile malformed"):
        run(reg, "malformed")


def test_ac03_schema_invalid_profile_is_malformed(reg: SchemaRegistry) -> None:
    b = business()
    b["ucp"]["services"] = "not an object"
    with pytest.raises(profile_check.ProfileMalformed, match="profile malformed"):
        run(reg, b=b)


def test_ac04_other_version_is_refused(reg: SchemaRegistry) -> None:
    b = business()
    b["ucp"]["version"] = "2026-01-23"
    with pytest.raises(profile_check.ProfileMalformed):
        run(reg, b=b)


def test_ac05_unbound_capability_not_used_with_reason(reg: SchemaRegistry) -> None:
    r = run(reg, "binding")
    assert "dev.ucp.shopping.fulfillment" not in r["active"]
    assert "binding" in r["excluded"]["dev.ucp.shopping.fulfillment"]


def test_ac06_no_rest_service(reg: SchemaRegistry) -> None:
    b = business()
    b["ucp"]["services"]["dev.ucp.shopping"][0]["transport"] = "mcp"
    assert run(reg, b=b)["transport"] is None


def test_ac09_lookup_only_notice(reg: SchemaRegistry) -> None:
    r = run(reg, "lookup-only")
    assert "dev.ucp.shopping.catalog.lookup" in r["active"]
    assert "dev.ucp.shopping.catalog.search" not in r["active"]
    assert r["search_notice"] == "Search is not available with this agent"


def test_ac96_wrong_handler_version_not_used(reg: SchemaRegistry) -> None:
    b = business()
    b["ucp"]["payment_handlers"]["com.google.pay"][0]["version"] = "2026-04-08"
    gp = run(reg, b=b)["payment_handlers"]["com.google.pay#gpay_demo_test_01"]
    assert gp["used"] is False
    assert any("AC-96" in x for x in gp["reasons"])


def test_ac92_bad_config_handler_not_used(reg: SchemaRegistry) -> None:
    b = copy.deepcopy(business())
    cfg = b["ucp"]["payment_handlers"]["com.google.pay"][0]["config"]
    cfg["allowed_payment_methods"][0]["parameters"]["x_unknown"] = 1
    gp = run(reg, b=b)["payment_handlers"]["com.google.pay#gpay_demo_test_01"]
    assert gp["used"] is False
    assert any("x_unknown" in x for x in gp["reasons"])
