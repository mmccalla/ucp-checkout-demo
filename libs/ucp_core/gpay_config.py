"""`com.google.pay` handler checks and the config map (AC-92, AC-96, AC-V5, 02-design 8.2, 8.3).

- `version` "must be 2026-01-23", and `spec` must be https://pay.google.com/gp/p/ucp/2026-01-23/
  (https://developers.google.com/pay/api/universal-commerce-protocol/google-pay-payment-handler).
- `config` is valid against the pinned `config.json`. That schema sets
  `additionalProperties: false` only on `parameters` and `billing_address_parameters`.
- The map renames `snake_case` to the Google Pay Web `camelCase` names
  (https://developers.google.com/pay/api/web/reference/request-objects). It does not send an
  unknown key: it logs the key and drops it. It does not send `merchant_origin` or `auth_jwt`
  (UNVERIFIED in Google Pay Web, 02-design 8.3).
"""

from __future__ import annotations

import logging
from typing import Any

from .constants import GPAY_SCHEMA, GPAY_SPEC, GPAY_VERSION
from .schema_registry import Issue, SchemaRegistry

log = logging.getLogger("ucp.gpay")

ROOT_MAP = {"api_version": "apiVersion", "api_version_minor": "apiVersionMinor"}
MERCHANT_MAP = {"merchant_id": "merchantId", "merchant_name": "merchantName"}
MERCHANT_NOT_SENT = {"merchant_origin", "auth_jwt"}
PARAM_MAP = {
    "allowed_auth_methods": "allowedAuthMethods",
    "allowed_card_networks": "allowedCardNetworks",
    "allow_prepaid_cards": "allowPrepaidCards",
    "allow_credit_cards": "allowCreditCards",
    "assurance_details_required": "assuranceDetailsRequired",
    "billing_address_required": "billingAddressRequired",
}
BAP_MAP = {"format": "format", "phone_number_required": "phoneNumberRequired"}


def check_declaration(entry: dict[str, Any]) -> list[str]:
    """Return the reasons that the Platform must not use this declaration (empty = use it)."""
    reasons = []
    if entry.get("version") != GPAY_VERSION:
        reasons.append(f"AC-96: version {entry.get('version')!r} is not {GPAY_VERSION}")
    if entry.get("spec") not in (None, GPAY_SPEC):
        reasons.append(f"spec {entry.get('spec')!r} is not {GPAY_SPEC}")
    if entry.get("schema") not in (None, GPAY_SCHEMA):
        reasons.append(f"schema {entry.get('schema')!r} is not {GPAY_SCHEMA}")
    if not isinstance(entry.get("config"), dict):
        reasons.append("no config object")
    elif entry["config"].get("environment") != "TEST":
        reasons.append("environment is not TEST (AC-26)")
    return reasons


def validate_config(reg: SchemaRegistry, config: dict[str, Any]) -> list[Issue]:
    return reg.validate(config, GPAY_SCHEMA)


def _pick(
    obj: dict[str, Any],
    mapping: dict[str, str],
    where: str,
    dropped: list[str],
    not_sent: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in obj.items():
        if k in mapping:
            out[mapping[k]] = v
        elif k in not_sent:
            dropped.append(f"{where}.{k} (not sent, 02-design 8.3)")
        else:
            dropped.append(f"{where}.{k} (unknown key)")
    return out


def to_google_pay(config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return ({environment, paymentDataRequest}, dropped keys)."""
    dropped: list[str] = []
    known_root = set(ROOT_MAP) | {"environment", "merchant_info", "allowed_payment_methods"}
    for k in config:
        if k not in known_root:
            dropped.append(f"config.{k} (unknown key)")
    req: dict[str, Any] = {ROOT_MAP[k]: config[k] for k in ROOT_MAP if k in config}
    req["merchantInfo"] = _pick(
        config.get("merchant_info", {}),
        MERCHANT_MAP,
        "config.merchant_info",
        dropped,
        MERCHANT_NOT_SENT,
    )
    methods = []
    for i, m in enumerate(config.get("allowed_payment_methods", [])):
        where = f"config.allowed_payment_methods[{i}]"
        for k in m:
            if k not in ("type", "parameters", "tokenization_specification"):
                dropped.append(f"{where}.{k} (unknown key)")
        params = dict(m.get("parameters", {}))
        bap = params.pop("billing_address_parameters", None)
        p = _pick(params, PARAM_MAP, where + ".parameters", dropped)
        if bap is not None:
            p["billingAddressParameters"] = _pick(
                bap, BAP_MAP, where + ".parameters.billing_address_parameters", dropped
            )
        ts = m.get("tokenization_specification", {})
        for k in ts:
            if k not in ("type", "parameters"):
                dropped.append(f"{where}.tokenization_specification.{k} (unknown key)")
        methods.append(
            {
                "type": m.get("type"),
                "parameters": p,
                # Copied without change: the UCP example already uses camelCase here (8.3).
                "tokenizationSpecification": {
                    "type": ts.get("type"),
                    "parameters": dict(ts.get("parameters", {})),
                },
            }
        )
    req["allowedPaymentMethods"] = methods
    for d in dropped:
        log.warning("google pay config key not sent: %s", d)
    return {"environment": config.get("environment"), "paymentDataRequest": req}, dropped
