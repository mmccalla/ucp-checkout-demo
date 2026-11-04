"""T-110 (CI profile fixture), T-111 (CI-only handler routing), T-112 (required capabilities)."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
from typing import Any

import pytest
from business_app import main as bmain
from business_app import platform_profiles as pp
from business_app.gate import Gate
from ucp_core import jwk
from ucp_core.constants import ROOT
from ucp_core.schema_registry import SchemaRegistry

import s5_profile  # conformance/s5_profile.py

# The tool comes from UCP_SCHEMA_BIN (the workflow and the box gates set it) or from PATH.
UCP_SCHEMA = os.environ.get("UCP_SCHEMA_BIN") or shutil.which("ucp-schema") or ""
SUITE_PROFILE = {  # shape of `shopping-agent-test.json` at 016ecbc: no services, no handlers
    "ucp": {"version": "2026-04-08", "capabilities": {}}
}


@pytest.fixture(scope="module")
def reg() -> SchemaRegistry:
    return SchemaRegistry.load()


def fixture_doc() -> dict[str, Any]:
    text = s5_profile.FIXTURE.read_text().replace("{ucp_version}", "2026-04-08")
    doc: dict[str, Any] = json.loads(text.replace("{webhook_port}", "8284"))
    return doc


# --- T-110 ---------------------------------------------------------------------------------


def test_fixture_is_a_valid_platform_profile(reg: SchemaRegistry) -> None:
    resolver = pp.Resolver(registry=reg, fetcher=lambda url: (fixture_doc(), {}))
    assert resolver.resolve('profile="https://localhost:8443/.well-known/ucp"')


@pytest.mark.skipif(
    not (UCP_SCHEMA and pathlib.Path(UCP_SCHEMA).exists()), reason="ucp-schema is not installed"
)
def test_fixture_passes_ucp_schema_validate(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "p.json"
    f.write_text(json.dumps(fixture_doc()))
    out = subprocess.run(
        [UCP_SCHEMA, "validate", str(f), "--schema", "contracts/ucp-schemas/discovery/profile.json",
         "--schema-local-base", "contracts/ucp-schemas",
         "--schema-remote-base", "https://ucp.dev/2026-04-08/schemas",
         "--op", "read", "--def", "platform_profile", "--json"],
        cwd=ROOT, capture_output=True, text=True,
    )  # fmt: skip
    assert out.returncode == 0, out.stdout + out.stderr


def test_the_suite_own_profile_gives_422_profile_malformed(reg: SchemaRegistry) -> None:
    """T-110: with no fixture the Business refuses (the pinned rule holds)."""
    resolver = pp.Resolver(registry=reg, fetcher=lambda url: (SUITE_PROFILE, {}))
    with pytest.raises(pp.ProfileProblem) as e:
        resolver.resolve('profile="https://localhost:8443/.well-known/ucp"')
    assert (e.value.status, e.value.code) == (422, "profile_malformed")


def test_plugin_replaces_only_the_template_in_memory(tmp_path: pathlib.Path) -> None:
    class Server:
        def __init__(self) -> None:
            self._profile_template = "suite"

    s5_profile.install(Server)
    assert Server()._profile_template == s5_profile.FIXTURE.read_text()


# --- T-111 ---------------------------------------------------------------------------------

MOCK = {
    "id": "i1",
    "handler_id": "mock_payment_handler",
    "type": "card",
    "display": {"brand": "VISA", "last_digits": "1111"},
    "credential": {"type": "token", "token": "success_token"},
}


def gate(mode: str, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Gate:
    monkeypatch.setenv("BUSINESS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UCP_TRACING", "0")
    app = bmain.create_app(mode=mode, require_signatures=False, key=jwk.ephemeral())
    return Gate(app, app.state.gate)


def check(g: Gate, inst: dict[str, Any]) -> Any:
    body = json.dumps({"payment": {"instruments": [inst]}}).encode()
    return g._check_instruments(body, {}, {})


def test_ci_accepts_the_mock_token_instrument(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # T-111 criterion 1
    assert isinstance(check(gate("ci", tmp_path, monkeypatch), MOCK), bytes)


@pytest.mark.parametrize(
    "change",
    [
        {"credential": {"type": "token"}},  # token missing (token_credential.json)
        {"credential": {"token": "s"}},  # type missing (credential.json)
        {"credential": {"type": "token", "token": 5}},  # token is not a string
        {"id": None},  # card_payment_instrument.json: id is a string
    ],
)
def test_ci_schema_still_applies_the_pinned_rules(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, change: dict[str, Any]
) -> None:  # T-111 criterion 2
    r = check(gate("ci", tmp_path, monkeypatch), {**MOCK, **change})
    assert getattr(r, "status_code", None) == 400


def test_ci_google_pay_instrument_still_uses_the_google_pay_schema(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gp = {**MOCK, "handler_id": "gpay", "credential": {"type": "token", "token": "x"}}
    r = check(gate("ci", tmp_path, monkeypatch), gp)
    assert getattr(r, "status_code", None) == 400  # `type: token` is not DIRECT or PAYMENT_GATEWAY


def test_demo_rejects_the_mock_handler(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # T-111 criterion 3, AC-32, T-93
    r = check(gate("demo", tmp_path, monkeypatch), MOCK)
    assert r.status_code == 400
    assert b"handler_id" in r.body


def test_demo_app_has_no_ci_schema(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    g = gate("demo", tmp_path, monkeypatch)
    assert g.cfg.ci_mock_instrument_schema is None


def test_ci_schema_file_holds_only_pinned_refs() -> None:
    doc = json.loads(bmain.CI_MOCK_SCHEMA.read_text())
    refs = [x["$ref"] for x in doc["allOf"] if "$ref" in x]
    refs += [
        y["$ref"] for x in doc["allOf"] for y in x.get("properties", {}).values() if "$ref" in y
    ]
    assert sorted(refs) == [
        "https://ucp.dev/2026-04-08/schemas/shopping/types/card_payment_instrument.json",
        "https://ucp.dev/2026-04-08/schemas/shopping/types/token_credential.json",
    ]


def test_demo_profile_golden_is_unchanged() -> None:  # T-111 criterion 4, AC-107
    status = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "business/profile/demo.json"], cwd=ROOT
    )
    assert status.returncode == 0


# --- T-112 ---------------------------------------------------------------------------------


def test_required_capabilities_equal_the_ci_profile() -> None:
    ci = json.loads((ROOT / "business" / "profile" / "ci.json").read_text())
    inp = json.loads((ROOT / "conformance" / "input" / "conformance_input.json").read_text())
    # The suite at 016ecbc tests checkout, fulfillment and order only. The two catalog
    # capabilities (S7) are not in the suite input.
    ci_caps = [
        c for c in ci["ucp"]["capabilities"] if not c.startswith("dev.ucp.shopping.catalog.")
    ]
    assert sorted(inp["required_capabilities"]) == sorted(ci_caps)
    assert sorted(inp["required_capabilities"]) == [
        "dev.ucp.shopping.checkout",
        "dev.ucp.shopping.fulfillment",
        "dev.ucp.shopping.order",
    ]
