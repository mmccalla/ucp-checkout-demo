"""Build the Google Pay Web requests from the Business handler `config` (AC-21, AC-27, AC-36).

- The config map is `ucp_core.gpay_config.to_google_pay` (02-design.md section 8.3).
- `transactionInfo` (https://developers.google.com/pay/api/web/reference/request-objects):
  `totalPriceStatus` "FINAL", `totalPrice` from minor units, `currencyCode`, and `checkoutOption`
  "COMPLETE_IMMEDIATE_PURCHASE" (only valid with FINAL, AC-98).
- `countryCode` "GB": the reference says it is required for EEA and SCA countries. UNVERIFIED
  (U-45): if the United Kingdom counts as an SCA country for Google Pay Web.
- `IsReadyToPayRequest` has `apiVersion`, `apiVersionMinor` and `allowedPaymentMethods`
  (same reference, IsReadyToPayRequest).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from ucp_core import gpay_config
from ucp_core.constants import GPAY_HANDLER
from ucp_core.schema_registry import SchemaRegistry

from .money import minor_to_price

COUNTRY_CODE = "GB"  # U-45 UNVERIFIED


@dataclass
class Plan:
    ok: bool
    handler_id: str | None = None
    environment: str | None = None
    payment_data_request: dict[str, Any] | None = None
    is_ready_to_pay_request: dict[str, Any] | None = None
    reasons: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


def pick_handler(checkout: dict[str, Any]) -> dict[str, Any] | None:
    handlers = ((checkout.get("ucp") or {}).get("payment_handlers") or {}).get(GPAY_HANDLER)
    if isinstance(handlers, list) and handlers and isinstance(handlers[0], dict):
        return handlers[0]
    return None


def transaction_info(total: int, currency: str) -> dict[str, str]:
    return {
        "totalPriceStatus": "FINAL",
        "totalPrice": minor_to_price(total, currency),
        "currencyCode": currency,
        "countryCode": COUNTRY_CODE,
        "checkoutOption": "COMPLETE_IMMEDIATE_PURCHASE",
    }


def build(reg: SchemaRegistry, handler: dict[str, Any] | None, total: int, currency: str) -> Plan:
    if handler is None:
        return Plan(False, reasons=[f"no {GPAY_HANDLER} handler in the checkout response"])
    reasons = gpay_config.check_declaration(handler)
    config = handler.get("config")
    if isinstance(config, dict):
        reasons += [
            f"config{i.path.lstrip('$')}: {i.message}"
            for i in gpay_config.validate_config(reg, config)
        ]
    if reasons:  # AC-27: validation fails and the payment step stops
        return Plan(False, handler_id=handler.get("id"), reasons=reasons)
    assert isinstance(config, dict)
    mapped, dropped = gpay_config.to_google_pay(config)
    pdr = copy.deepcopy(mapped["paymentDataRequest"])
    try:
        pdr["transactionInfo"] = transaction_info(total, currency)
    except ValueError as e:
        return Plan(False, handler_id=handler.get("id"), reasons=[str(e)])
    irtp = {
        "apiVersion": pdr.get("apiVersion"),
        "apiVersionMinor": pdr.get("apiVersionMinor"),
        "allowedPaymentMethods": copy.deepcopy(pdr["allowedPaymentMethods"]),
    }
    return Plan(
        True,
        handler_id=str(handler.get("id")),
        environment=mapped["environment"],
        payment_data_request=pdr,
        is_ready_to_pay_request=irtp,
        dropped=dropped,
    )
