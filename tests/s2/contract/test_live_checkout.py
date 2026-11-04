"""G4 live, S2: AC-07, AC-11, AC-13, AC-100 over the TLS 1.3 loopback layout.

The layout must run (`tools/run_local.sh start`). A failed connection is a FAIL, not a skip.
The Platform signs the request. The Business gets the Platform profile from the `UCP-Agent`
URL over HTTPS (netguard: no redirect) and verifies the signature with its `signing_keys`.
"""

from __future__ import annotations

import json
import os
import ssl
from typing import Any

import httpx
from ucp_core.constants import ROOT

from tests.s2.conftest import create_body

CA = ROOT / ".run/xdg-data/caddy/pki/authorities/local/root.crt"
PLATFORM = "https://localhost:8443"
EVIDENCE = os.environ.get("S2_EVIDENCE")


def ctx() -> ssl.SSLContext:
    c = ssl.create_default_context(cafile=str(CA))
    c.minimum_version = ssl.TLSVersion.TLSv1_3
    return c


def save(name: str, data: Any) -> None:
    if EVIDENCE:
        d = ROOT / EVIDENCE / "live"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps(data, indent=2) + "\n")


def test_live_create_signed_and_timeline() -> None:
    with httpx.Client(verify=ctx(), follow_redirects=False, timeout=20) as c:
        prof = c.get(PLATFORM + "/.well-known/ucp")
        assert prof.status_code == 200
        assert prof.json()["signing_keys"][0]["alg"] == "ES256"
        assert "d" not in prof.json()["signing_keys"][0]
        r = c.post(PLATFORM + "/api/checkout", json=create_body())
        assert r.status_code == 200
        out = r.json()
        save("api-checkout-create.json", out)
        assert out["http_status"] == 201, out
        view = out["view"]
        assert view["state"] == "incomplete"
        assert view["checkout"]["currency"] == "GBP"
        tl = c.get(PLATFORM + "/api/timeline").json()["rows"]
    # S3 (AC-59): the timeline also has state, buyer action and error rows. Use the request row.
    plat = [x for x in tl if x["side"] == "platform" and x.get("kind", "request") == "request"][-1]
    # Some business rows have no request_id (webhook delivery rows). Use .get().
    biz = [x for x in tl if x["side"] == "business" and x.get("request_id") == plat["request_id"]]
    save("timeline-last.json", [plat, *biz])
    assert plat["op"] == "create" and plat["status"] == 201
    assert plat["idempotency_key_present"] is True
    assert len(biz) == 1
    assert biz[0]["status"] == 201
    assert biz[0]["signature"].startswith("verified keyid=")
    text = json.dumps(tl)
    for word in ("sig1=", "eyJ", "BEGIN", "token"):
        assert word not in text
