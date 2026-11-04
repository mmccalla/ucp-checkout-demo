"""G4 contract: AC-02, AC-106, AC-107, T-04. In-process apps, no network."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
from typing import Any

import pytest
from business_app.main import create_app
from fastapi.testclient import TestClient
from ucp_core import jwk
from ucp_core.constants import ROOT

UCP_SCHEMA = os.environ.get("UCP_SCHEMA_BIN", "ucp-schema")


def served(mode: str) -> tuple[int, dict[str, str], dict[str, Any]]:
    c = TestClient(create_app(mode=mode, key=jwk.ephemeral()))
    r = c.get("/.well-known/ucp", follow_redirects=False)
    return r.status_code, dict(r.headers), r.json()


def ac106_validate(path: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """The AC-106 command (ADR 0002): ucp-schema 1.4.1, src/bin/ucp-schema.rs:144-191."""
    return subprocess.run(
        [
            UCP_SCHEMA,
            "validate",
            str(path),
            "--schema",
            "contracts/ucp-schemas/discovery/profile.json",
            "--schema-local-base",
            "contracts/ucp-schemas",
            "--schema-remote-base",
            "https://ucp.dev/2026-04-08/schemas",
            "--op",
            "read",
            "--def",
            "business_profile",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("mode", ["demo", "ci"])
def test_ac02_ac106_served_profile(mode: str, tmp_path: pathlib.Path) -> None:
    status, headers, body = served(mode)
    assert status == 200
    assert headers["cache-control"] == "public, max-age=300"
    assert body["ucp"]["version"] == "2026-04-08"
    svc = body["ucp"]["services"]["dev.ucp.shopping"]
    assert [s["transport"] for s in svc] == ["rest"]
    gp = body["ucp"]["payment_handlers"]["com.google.pay"][0]
    assert gp["config"]["environment"] == "TEST"
    p = tmp_path / f"{mode}.json"
    p.write_text(json.dumps(body))
    r = ac106_validate(p)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout)["valid"] is True


def test_ac106_invalid_profile_fails_validate(tmp_path: pathlib.Path) -> None:
    _, _, body = served("demo")
    del body["ucp"]["payment_handlers"]
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(body))
    assert ac106_validate(p).returncode != 0


def test_ac107_demo_has_no_mock_or_shop_pay_and_ci_differs_only_by_mock() -> None:
    _, _, demo = served("demo")
    _, _, ci = served("ci")
    text = json.dumps(demo)
    assert "mock_payment_handler" not in text and "shop_pay" not in text
    for d in (demo, ci):
        d.pop("signing_keys")
        d.pop("keys")
    extra = ci["ucp"]["payment_handlers"].pop("dev.mock.payment_handler")
    assert extra[0]["id"] == "mock_payment_handler"
    assert ci == demo


def test_t04_signing_keys_and_keys_mirror() -> None:
    _, _, body = served("demo")
    sk, ks = body["signing_keys"], body["keys"]
    assert [k["kid"] for k in sk] == [k["kid"] for k in ks]
    for a, b in zip(sk, ks, strict=True):
        assert jwk.thumbprint(a) == jwk.thumbprint(b) == a["kid"]
        assert a["alg"] == "ES256" and a["crv"] == "P-256"
        assert "d" not in a and "d" not in b  # public key only


def test_profile_route_does_not_redirect() -> None:
    c = TestClient(create_app(mode="demo", key=jwk.ephemeral()))
    assert c.get("/.well-known/ucp/", follow_redirects=False).status_code == 404
