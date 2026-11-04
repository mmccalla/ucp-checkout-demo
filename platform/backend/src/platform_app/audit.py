"""Audit record for each payment attempt (AC-55, 02-design.md section 12, DM-13).

One row for each payment attempt, in a local SQLite file. The fields come from
`input-agent-control.md` section 7 and `02-design.md` section 12. A record never has these
fields: `credential.token`, PAN, expiry, CVC, cryptogram, billing address, `continue_url`.
`write` refuses a record that has a forbidden key (at any depth) or a missing field.
Retention: 30 days at most (DM-13). `purge` deletes older rows.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ucp_core.constants import ROOT

FIELDS = (
    "attempt_id",
    "approval_id",
    "approval_time_utc",
    "approval_hash",
    "checkout_id",
    "business_profile_url",
    "ucp_version",
    "handler_version",
    "currency",
    "total_minor",
    "line_items_summary",
    "handler_id",
    "instrument_id",
    "card_brand",
    "card_last_digits",
    "environment",
    "idempotency_key_hash",
    "policy_result",
    "final_status",
    "messages",
    "order_id",
    "escalation",
)
FORBIDDEN = (
    "credential",
    "token",
    "pan",
    "expiry",
    "cvc",
    "cryptogram",
    "billing_address",
    "continue_url",
)
RETENTION_DAYS = 30
_lock = threading.Lock()


class AuditError(Exception):
    pass


def db_path() -> pathlib.Path:
    return pathlib.Path(
        os.environ.get("PLATFORM_AUDIT_DB", str(ROOT / ".run" / "platform-audit.sqlite"))
    )


def _connect(path: pathlib.Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.execute(
        "CREATE TABLE IF NOT EXISTS audit (attempt_id TEXT PRIMARY KEY, ts TEXT NOT NULL, "
        "record TEXT NOT NULL)"
    )
    return con


def key_hash(key: str | None) -> str | None:
    return hashlib.sha256(key.encode()).hexdigest() if key else None


def _keys(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            out.append(str(k))
            out += _keys(v)
    elif isinstance(value, list):
        for v in value:
            out += _keys(v)
    return out


def check(record: dict[str, Any]) -> None:
    missing = [f for f in FIELDS if f not in record]
    extra = [k for k in record if k not in FIELDS]
    if missing or extra:
        raise AuditError(f"audit record fields: missing {missing}, unknown {extra}")
    bad = [k for k in _keys(record) if k.lower() in FORBIDDEN]
    if bad:
        raise AuditError(f"forbidden audit field: {bad}")


def new_attempt_id() -> str:
    return str(uuid.uuid4())


def build(
    *,
    attempt_id: str,
    approval: dict[str, Any],
    checkout_id: str,
    instrument: dict[str, Any] | None,
    idempotency_key: str | None,
    final_status: str,
    checkout: dict[str, Any] | None,
    escalation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make the record. `approval` is the context saved at the review (no token in it)."""
    display = (instrument or {}).get("display") or {}
    messages = [
        {"code": m.get("code"), "severity": m.get("severity")}
        for m in ((checkout or {}).get("messages") or [])
        if isinstance(m, dict)
    ]
    order = (checkout or {}).get("order") or {}
    if escalation is None and final_status == "requires_escalation":
        escalation = {
            "reason": "requires_escalation",
            "continue_url_offered": bool((checkout or {}).get("continue_url")),
        }
    return {
        "attempt_id": attempt_id,
        "approval_id": approval["approval_id"],
        "approval_time_utc": approval["approval_time_utc"],
        "approval_hash": approval["approval_hash"],
        "checkout_id": checkout_id,
        "business_profile_url": approval["business_profile_url"],
        "ucp_version": approval["ucp_version"],
        "handler_version": approval["handler_version"],
        "currency": approval["currency"],
        "total_minor": approval["total_minor"],
        "line_items_summary": approval["line_items_summary"],
        "handler_id": approval["handler_id"],
        "instrument_id": (instrument or {}).get("id"),
        "card_brand": display.get("brand"),
        "card_last_digits": display.get("last_digits"),
        "environment": approval["environment"],
        "idempotency_key_hash": key_hash(idempotency_key),
        "policy_result": approval["policy_result"],
        "final_status": final_status,
        "messages": messages,
        "order_id": order.get("id") if isinstance(order, dict) else None,
        "escalation": escalation,
    }


def write(record: dict[str, Any], path: pathlib.Path | None = None) -> None:
    check(record)
    now = datetime.now(UTC).isoformat()
    with _lock, _connect(path) as con:
        con.execute(
            "INSERT INTO audit (attempt_id, ts, record) VALUES (?, ?, ?)",
            (record["attempt_id"], now, json.dumps(record, sort_keys=True)),
        )


def read_all(path: pathlib.Path | None = None) -> list[dict[str, Any]]:
    with _lock, _connect(path) as con:
        rows = con.execute("SELECT record FROM audit ORDER BY ts").fetchall()
    return [json.loads(r[0]) for r in rows]


def purge(path: pathlib.Path | None = None, now: datetime | None = None) -> int:
    cutoff = ((now or datetime.now(UTC)) - timedelta(days=RETENTION_DAYS)).isoformat()
    with _lock, _connect(path) as con:
        return con.execute("DELETE FROM audit WHERE ts < ?", (cutoff,)).rowcount
