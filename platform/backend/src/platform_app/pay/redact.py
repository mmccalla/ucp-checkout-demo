"""Redaction for the inspector, the timeline and the logs (AC-111, UX `inspector.redacted`)."""

from __future__ import annotations

import re
from typing import Any

MASK = "[REDACTED]"
SECRET_KEYS = {"token", "authorization", "x-api-key", "signature", "signature-input"}
PAN_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: MASK if str(k).lower() in SECRET_KEYS else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return PAN_RE.sub(MASK, value)
    return value


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: MASK if k.lower() in SECRET_KEYS else v for k, v in headers.items()}
