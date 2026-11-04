"""S3 unit tests: money, totals check, gate (DM-06), approval hash, mapper, instrument, redaction."""

from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import random
import re
from typing import Any

import pytest
from platform_app.pay import approval, payment_request, policy, totals_check
from platform_app.pay.instrument import InstrumentError, from_payment_data
from platform_app.pay.money import PRICE_RE, display, minor_to_price, price_to_minor
from platform_app.pay.redact import MASK, redact, redact_headers
from ucp_core.constants import ROOT
from ucp_core.schema_registry import SchemaRegistry

HANDLER: dict[str, Any] = json.loads(
    (ROOT / "contracts" / "fixtures" / "gpay-handler-test.json").read_text()
)
# The PaymentData example of https://developers.google.com/pay/api/web/reference/response-objects
PAYMENT_DATA = {
    "apiVersion": 2,
    "apiVersionMinor": 0,
    "paymentMethodData": {
        "type": "CARD",
        "description": "Visa •••• 1234",
        "info": {"cardNetwork": "VISA", "cardDetails": "1234", "cardFundingSource": "CREDIT"},
        "tokenizationData": {"type": "PAYMENT_GATEWAY", "token": "examplePaymentMethodToken"},
    },
}


@pytest.fixture(scope="module")
def reg() -> SchemaRegistry:
    return SchemaRegistry.load(ROOT)


def checkout(total: int = 2300) -> dict[str, Any]:
    return {
        "id": "co_1",
        "currency": "GBP",
        "status": "ready_for_complete",
        "line_items": [
            {
                "id": "li_1",
                "item": {"id": "demo_tshirt", "title": "Demo T-shirt", "price": 2000},
                "quantity": 1,
                "totals": [{"type": "subtotal", "amount": 2000}, {"type": "total", "amount": 2000}],
            }
        ],
        "totals": [
            {"type": "subtotal", "amount": 2000},
            {"type": "fulfillment", "amount": total - 2000},
            {"type": "total", "amount": total},
        ],
        "ucp": {"payment_handlers": {"com.google.pay": [HANDLER]}},
    }


# ---------------------------------------------------------------- money, AC-21, AC-110
def test_ac21_1999_minor_units(reg: SchemaRegistry) -> None:
    plan = payment_request.build(reg, HANDLER, 1999, "GBP")
    assert plan.ok, plan.reasons
    ti = plan.payment_data_request["transactionInfo"]  # type: ignore[index]
    assert ti["totalPrice"] == "19.99"
    assert ti["currencyCode"] == "GBP"
    assert ti["totalPriceStatus"] == "FINAL"
    assert ti["checkoutOption"] == "COMPLETE_IMMEDIATE_PURCHASE"


@pytest.mark.parametrize(
    ("amount", "price"), [(0, "0.00"), (1, "0.01"), (10, "0.10"), (100, "1.00"), (2300, "23.00")]
)
def test_minor_to_price(amount: int, price: str) -> None:
    assert minor_to_price(amount, "GBP") == price
    assert price_to_minor(price, "GBP") == amount


@pytest.mark.parametrize("bad", [-1, 1.5, True, "100"])
def test_minor_to_price_rejects(bad: Any) -> None:
    with pytest.raises(ValueError):
        minor_to_price(bad, "GBP")


def test_non_gbp_rejected() -> None:
    with pytest.raises(ValueError):
        minor_to_price(100, "USD")


def test_ac110_property_10000_amounts(reg: SchemaRegistry) -> None:
    """AC-110: 10 000 seeded random amounts through the real handler config map."""
    rnd = random.Random(20261024)
    amounts = [0, 1, 99, 100, 5000, 10**9] + [rnd.randrange(0, 10**9) for _ in range(9994)]
    assert len(amounts) == 10000
    plan0 = payment_request.build(reg, HANDLER, 0, "GBP")
    for m in plan0.payment_data_request["allowedPaymentMethods"]:  # type: ignore[index]
        assert m["parameters"]["allowedAuthMethods"] == ["PAN_ONLY"]
    for a in amounts:
        plan = payment_request.build(reg, HANDLER, a, "GBP")
        pdr = plan.payment_data_request
        assert pdr is not None
        assert "merchantOrigin" not in pdr["merchantInfo"]
        assert "authJwt" not in pdr["merchantInfo"]
        s = pdr["transactionInfo"]["totalPrice"]
        assert PRICE_RE.match(s), s
        assert price_to_minor(s, "GBP") == a
        assert re.fullmatch(r"^[0-9]+(\.[0-9][0-9])?$", s)


def test_display() -> None:
    assert display(2300, "GBP") == "£23.00"
    assert display(-150, "GBP") == "-£1.50"


# ---------------------------------------------------------------- AC-36, AC-27
def test_ac36_map_follows_8_3(reg: SchemaRegistry) -> None:
    cfg = copy.deepcopy(HANDLER["config"])
    cfg["merchant_info"]["merchant_origin"] = "localhost"  # config.json: format hostname
    cfg["merchant_info"]["auth_jwt"] = "x.y.z"
    h = dict(HANDLER, config=cfg)
    plan = payment_request.build(reg, h, 2300, "GBP")
    assert plan.ok, plan.reasons
    pdr = plan.payment_data_request
    assert pdr is not None
    assert plan.environment == "TEST"
    assert "environment" not in pdr
    assert pdr["apiVersion"] == cfg["api_version"]
    assert pdr["apiVersionMinor"] == cfg["api_version_minor"]
    assert pdr["merchantInfo"] == {
        "merchantId": cfg["merchant_info"]["merchant_id"],
        "merchantName": cfg["merchant_info"]["merchant_name"],
    }
    m0, c0 = pdr["allowedPaymentMethods"][0], cfg["allowed_payment_methods"][0]
    assert m0["parameters"]["allowedAuthMethods"] == c0["parameters"]["allowed_auth_methods"]
    assert m0["parameters"]["allowedCardNetworks"] == c0["parameters"]["allowed_card_networks"]
    assert m0["tokenizationSpecification"] == c0["tokenization_specification"]
    assert any("merchant_origin" in d for d in plan.dropped)
    assert any("auth_jwt" in d for d in plan.dropped)
    irtp = plan.is_ready_to_pay_request
    assert irtp == {
        "apiVersion": 2,
        "apiVersionMinor": 0,
        "allowedPaymentMethods": pdr["allowedPaymentMethods"],
    }


@pytest.mark.parametrize(
    "drop",
    [("environment",), ("allowed_payment_methods",), ("merchant_info", "merchant_id")],
    ids=["environment", "allowed_payment_methods", "merchant_id"],
)
def test_ac27_config_missing_field_fails(reg: SchemaRegistry, drop: tuple[str, ...]) -> None:
    cfg = copy.deepcopy(HANDLER["config"])
    obj = cfg
    for k in drop[:-1]:
        obj = obj[k]
    del obj[drop[-1]]
    plan = payment_request.build(reg, dict(HANDLER, config=cfg), 2300, "GBP")
    assert not plan.ok
    assert plan.payment_data_request is None
    assert plan.reasons


def test_ac27_test_config_with_merchant_id_test_passes(reg: SchemaRegistry) -> None:
    assert HANDLER["config"]["merchant_info"]["merchant_id"] == "TEST"
    assert payment_request.build(reg, HANDLER, 2300, "GBP").ok


# ---------------------------------------------------------------- AC-20 totals
def test_totals_ok() -> None:
    assert totals_check.check_checkout(checkout()) == []


def test_ac20_mismatch_detected() -> None:
    c = checkout()
    c["totals"][2]["amount"] += 1
    assert totals_check.check_checkout(c)


def test_totals_two_totals_and_lines() -> None:
    c = checkout()
    c["totals"].append({"type": "total", "amount": 2300})
    assert totals_check.check_checkout(c)
    c = checkout()
    c["totals"][1]["lines"] = [{"amount": 100}, {"amount": 100}]
    assert any("lines" in p for p in totals_check.check_checkout(c))


def test_totals_discount_negative() -> None:
    c = checkout()
    c["totals"].insert(1, {"type": "discount", "amount": -300, "display_text": "Promo"})
    c["totals"][-1]["amount"] = 2000
    assert totals_check.check_checkout(c) == []
    assert totals_check.label(c["totals"][1]) == "Promo"
    assert totals_check.label({"type": "fulfillment"}) == "Shipping"


# ---------------------------------------------------------------- DM-06 gate, AC-23 to AC-25
def g(**kw: Any) -> list[policy.Reason]:
    args: dict[str, Any] = {
        "total": 2300,
        "currency": "GBP",
        "environment": "TEST",
        "business_profile_url": "https://localhost:9443/.well-known/ucp",
        "allowlist": ["https://localhost:9443/.well-known/ucp"],
        "spent_today": 0,
    }
    args.update(kw)
    return policy.gate(**args)


def test_gate_passes() -> None:
    assert g() == []
    assert g(total=5000) == []
    assert g(total=1000, spent_today=9000) == []


def test_ac23_per_payment() -> None:
    r = g(total=5001)
    assert [x.code for x in r] == ["per_payment"]
    assert "per-payment limit" in r[0].text


def test_ac24_daily() -> None:
    r = g(total=2000, spent_today=9000)
    assert [x.code for x in r] == ["daily"]
    assert "daily limit" in r[0].text


def test_ac25_allowlist_currency_env() -> None:
    assert [x.code for x in g(allowlist=["https://other.example/.well-known/ucp"])] == ["allowlist"]
    assert [x.code for x in g(currency="USD")] == ["currency"]
    r = g(environment="PRODUCTION")
    assert [x.code for x in r] == ["not_test"]
    assert r[0].text == "Demo stopped. The shop is not in TEST mode."


def test_ledger(tmp_path: pathlib.Path) -> None:
    led = policy.Ledger(tmp_path / "spend.jsonl")
    assert led.spent_today() == 0
    led.add("a", 2300, "GBP")
    led.add("b", 1000, "GBP")
    assert led.spent_today() == 3300
    assert led.spent_today(dt.date(2000, 1, 1)) == 0


# ---------------------------------------------------------------- AC-22 approval hash
def test_ac22_hash_changes_with_the_order() -> None:
    url = "https://localhost:9443/.well-known/ucp"
    h = approval.approval_hash(checkout(), url, "gpay_demo_test_01")
    assert h == approval.approval_hash(checkout(), url, "gpay_demo_test_01")
    c = checkout()
    c["totals"][1]["amount"] = 400
    c["totals"][2]["amount"] = 2400
    assert approval.approval_hash(c, url, "gpay_demo_test_01") != h
    c = checkout()
    c["line_items"][0]["quantity"] = 2
    assert approval.approval_hash(c, url, "gpay_demo_test_01") != h
    assert approval.approval_hash(checkout(), url, "other") != h
    assert approval.approval_hash(checkout(), "https://x/.well-known/ucp", "gpay_demo_test_01") != h


# ---------------------------------------------------------------- AC-111 instrument, redaction
def test_ac111_instrument(reg: SchemaRegistry, caplog: pytest.LogCaptureFixture) -> None:
    pd = copy.deepcopy(PAYMENT_DATA)
    pd["paymentMethodData"]["info"]["cardNetwork"] = "visa"  # type: ignore[index]
    inst = from_payment_data(reg, pd, "gpay_demo_test_01")
    assert inst["display"]["brand"] == "VISA"
    assert inst["display"]["last_digits"] == "1234"
    assert inst["credential"]["type"] == "PAYMENT_GATEWAY"
    assert inst["type"] == "card" and inst["handler_id"] == "gpay_demo_test_01"
    assert (
        reg.validate(
            inst, "https://pay.google.com/gp/p/ucp/2026-01-23/schemas/card_payment_instrument.json"
        )
        == []
    )
    shown = json.dumps(redact({"payment": {"instruments": [inst]}}))
    assert "examplePaymentMethodToken" not in shown and MASK in shown
    assert "examplePaymentMethodToken" not in caplog.text


def test_ac111_bad_instrument_message_has_no_token(reg: SchemaRegistry) -> None:
    pd = copy.deepcopy(PAYMENT_DATA)
    pd["paymentMethodData"]["tokenizationData"]["type"] = "OTHER"  # type: ignore[index]
    with pytest.raises(InstrumentError) as e:
        from_payment_data(reg, pd, "h")
    assert "examplePaymentMethodToken" not in str(e.value)
    with pytest.raises(InstrumentError):
        from_payment_data(reg, {}, "h")


def test_redact_headers_and_pan() -> None:
    h = redact_headers({"Signature": "sig1=:x:", "Authorization": "Bearer y", "Request-Id": "r"})
    assert h == {"Signature": MASK, "Authorization": MASK, "Request-Id": "r"}
    assert redact({"note": "card 4111 1111 1111 1111"}) == {"note": f"card {MASK}"}
    assert redact({"ts": "2026-10-24T23:00:00+0100"}) == {"ts": "2026-10-24T23:00:00+0100"}
