"""G4 live: AC-01, AC-02, AC-04, AC-06, AC-08 (a), AC-122 over the TLS 1.3 loopback layout.

The layout must run (`tools/run_local.sh start`). A failed connection is a FAIL, not a skip.
"""

from __future__ import annotations

import json
import os
import ssl
from typing import Any

import httpx2
from ucp_core.constants import ROOT

CA = ROOT / ".run/xdg-data/caddy/pki/authorities/local/root.crt"
EVIDENCE = os.environ.get("S1_EVIDENCE")


def ctx() -> ssl.SSLContext:
    c = ssl.create_default_context(cafile=str(CA))
    c.minimum_version = ssl.TLSVersion.TLSv1_3
    return c


def get(url: str) -> httpx2.Response:
    with httpx2.Client(verify=ctx(), follow_redirects=False, timeout=10) as c:
        return c.get(url)


def save(name: str, data: Any) -> None:
    if EVIDENCE:
        (ROOT / EVIDENCE / name).write_text(json.dumps(data, indent=2) + "\n")


def test_live_business_profile_ac02() -> None:
    r = get("https://localhost:9443/.well-known/ucp")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=300"
    assert r.json()["ucp"]["payment_handlers"]["com.google.pay"][0]["config"]["environment"] == (
        "TEST"
    )


def test_live_discovery_ac01_ac04_ac06_ac08a_ac122() -> None:
    r = get("https://localhost:8443/api/discovery")
    assert r.status_code == 200
    d = r.json()
    save("api-discovery.live.json", d)
    assert d["ok"] is True, d
    assert d["redirects"] == 0
    assert d["ucp_version"] == d["selected_version"] == "2026-04-08"
    assert d["transport"] == "REST"
    # Active = the capabilities that both live profiles list. The running Business can have the
    # catalog capabilities (S7) or not, so the list comes from the two live profiles.
    business = get("https://localhost:9443/.well-known/ucp").json()["ucp"]["capabilities"]
    platform = get("https://localhost:8443/.well-known/ucp").json()["ucp"]["capabilities"]
    assert d["active"] == sorted(set(business) & set(platform))
    assert {
        "dev.ucp.shopping.checkout",
        "dev.ucp.shopping.fulfillment",
        "dev.ucp.shopping.order",
    } <= set(d["active"])
    assert set(d["resolved"]) <= {"127.0.0.1", "::1"}
    assert d["payment_handlers"]["com.google.pay#gpay_demo_test_01"]["used"] is True


def test_live_cases_ac03_ac05_ac09() -> None:
    m = get("https://localhost:8443/api/discovery?case=malformed").json()
    assert m["ok"] is False and m["error"] == "profile_malformed"
    b = get("https://localhost:8443/api/discovery?case=binding").json()
    assert "dev.ucp.shopping.fulfillment" in b["excluded"]
    lk = get("https://localhost:8443/api/discovery?case=lookup-only").json()
    assert lk["search_notice"] == "Search is not available with this agent"


def test_live_platform_profile() -> None:
    r = get("https://localhost:8443/.well-known/ucp")
    assert r.status_code == 200
    assert r.json()["ucp"]["version"] == "2026-04-08"
