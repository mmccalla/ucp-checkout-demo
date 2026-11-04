"""AC-92, AC-96, AC-02 (part): the com.google.pay 2026-01-23 handler declaration and config."""

from __future__ import annotations

from typing import Any

import copy
import json
import logging

import pytest
from ucp_core import gpay_config
from ucp_core.constants import ROOT
from ucp_core.schema_registry import SchemaRegistry

FIXTURE = json.loads((ROOT / "contracts/fixtures/gpay-handler-test.json").read_text())


def entry() -> dict[str, Any]:
    e = FIXTURE if "config" in FIXTURE else FIXTURE["entry"]
    return copy.deepcopy(e)


def test_fixture_config_is_valid_and_test(reg: SchemaRegistry) -> None:
    e = entry()
    assert gpay_config.check_declaration(e) == []
    assert gpay_config.validate_config(reg, e["config"]) == []
    assert e["config"]["environment"] == "TEST"


@pytest.mark.parametrize("where", ["parameters", "billing_address_parameters"])
def test_ac92_unknown_key_in_closed_objects_fails(reg: SchemaRegistry, where: str) -> None:
    cfg = entry()["config"]
    params = cfg["allowed_payment_methods"][0]["parameters"]
    target = (
        params
        if where == "parameters"
        else params.setdefault("billing_address_parameters", {"format": "MIN"})
    )
    target["x_unknown"] = True
    issues = gpay_config.validate_config(reg, cfg)
    assert any("x_unknown" in i.message for i in issues)


@pytest.mark.parametrize("where", ["root", "merchant_info"])
def test_ac92_unknown_key_elsewhere_passes_is_logged_and_dropped(
    reg: SchemaRegistry, where: str, caplog: pytest.LogCaptureFixture
) -> None:
    cfg = entry()["config"]
    (cfg if where == "root" else cfg["merchant_info"])["x_unknown"] = "v"
    assert gpay_config.validate_config(reg, cfg) == []
    caplog.set_level(logging.WARNING)
    mapped, dropped = gpay_config.to_google_pay(cfg)
    assert any("x_unknown" in d for d in dropped)
    assert "x_unknown" not in json.dumps(mapped)
    assert "x_unknown" in caplog.text


def test_mapping_uses_google_pay_names() -> None:
    mapped, _ = gpay_config.to_google_pay(entry()["config"])
    req = mapped["paymentDataRequest"]
    assert mapped["environment"] == "TEST"
    assert {"apiVersion", "apiVersionMinor", "merchantInfo", "allowedPaymentMethods"} <= set(req)
    m = req["allowedPaymentMethods"][0]
    assert {"allowedAuthMethods", "allowedCardNetworks"} <= set(m["parameters"])


@pytest.mark.parametrize("version", ["2026-04-08", "2025-12-01", None])
def test_ac96_other_version_is_not_used(version: str | None) -> None:
    e = entry()
    e["version"] = version
    assert any("AC-96" in r for r in gpay_config.check_declaration(e))
