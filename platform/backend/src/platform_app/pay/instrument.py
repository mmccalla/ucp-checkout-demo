"""Map Google Pay `PaymentData` to the UCP payment instrument (AC-111, ENG-09).

- `PaymentData.paymentMethodData` has `type`, `description`, `info.cardNetwork`,
  `info.cardDetails` and `tokenizationData {type, token}`
  (https://developers.google.com/pay/api/web/reference/response-objects).
- The instrument must be valid against the pinned Google Pay `card_payment_instrument.json`
  (`contracts/gpay-handler`): `type` "card", `display.brand` in UPPERCASE from the enum,
  `display.last_digits`, `credential {type, token}`.
- The token goes only into the Complete body. No log line, timeline row or page element
  holds it (`redact.py`).
"""

from __future__ import annotations

import uuid
from typing import Any

from ucp_core.constants import GPAY_INSTRUMENT_SCHEMA
from ucp_core.schema_registry import SchemaRegistry


class InstrumentError(ValueError):
    pass


def from_payment_data(reg: SchemaRegistry, payment_data: Any, handler_id: str) -> dict[str, Any]:
    pmd = payment_data.get("paymentMethodData") if isinstance(payment_data, dict) else None
    if not isinstance(pmd, dict):
        raise InstrumentError("PaymentData has no paymentMethodData")
    info = pmd.get("info") or {}
    tok = pmd.get("tokenizationData") or {}
    display: dict[str, Any] = {
        "brand": str(info.get("cardNetwork", "")).upper(),
        "last_digits": str(info.get("cardDetails", "")),
    }
    if isinstance(pmd.get("description"), str):
        display["description"] = pmd["description"]
    inst = {
        "id": f"instr_{uuid.uuid4().hex[:12]}",
        "handler_id": handler_id,
        "type": "card",
        "selected": True,
        "display": display,
        "credential": {"type": tok.get("type"), "token": tok.get("token")},
    }
    issues = reg.validate(inst, GPAY_INSTRUMENT_SCHEMA)
    if issues:
        # The message names the path only. It never quotes the token.
        raise InstrumentError("instrument not valid: " + "; ".join(i.path for i in issues))
    return inst
