"""G3, S4: the audit record (AC-55, 02-design.md section 12, DM-13)."""

from __future__ import annotations

import hashlib
import pathlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from platform_app import audit

APPROVAL = {
    "approval_id": "a1",
    "approval_time_utc": "2026-10-28T10:00:00+00:00",
    "approval_hash": "h" * 64,
    "business_profile_url": "https://localhost:9443/.well-known/ucp",
    "ucp_version": "2026-04-08",
    "handler_version": "2026-01-23",
    "currency": "GBP",
    "total_minor": 2300,
    "line_items_summary": [{"id": "li1", "title": "T-shirt", "quantity": 1, "total": "£23.00"}],
    "handler_id": "gpay-test",
    "environment": "TEST",
    "policy_result": "pass",
}
INST = {"id": "instr_1", "display": {"brand": "VISA", "last_digits": "1234"}}


def rec(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "attempt_id": "x1",
        "approval": APPROVAL,
        "checkout_id": "c1",
        "instrument": INST,
        "idempotency_key": "key-1",
        "final_status": "completed",
        "checkout": {"status": "completed", "order": {"id": "o1"}, "messages": []},
    }
    return audit.build(**(base | kw))


def test_record_has_all_fields_and_no_key_or_url() -> None:
    r = rec()
    audit.check(r)
    assert set(r) == set(audit.FIELDS)
    assert r["idempotency_key_hash"] == hashlib.sha256(b"key-1").hexdigest()
    assert "key-1" not in str(r) and r["order_id"] == "o1" and r["card_last_digits"] == "1234"


def test_escalation_says_if_continue_url_was_offered_but_never_stores_it() -> None:
    r = rec(
        final_status="requires_escalation",
        checkout={"status": "requires_escalation", "continue_url": "https://x.test/c"},
    )
    assert r["escalation"] == {"reason": "requires_escalation", "continue_url_offered": True}
    assert "https://x.test/c" not in str(r)


@pytest.mark.parametrize(
    "bad", ["credential", "token", "pan", "cvc", "continue_url", "billing_address"]
)
def test_forbidden_field_is_refused_at_any_depth(bad: str) -> None:
    r = rec()
    r["line_items_summary"] = [{"id": "li1", bad: "x"}]
    with pytest.raises(audit.AuditError):
        audit.check(r)


def test_missing_field_is_refused() -> None:
    r = rec()
    del r["currency"]
    with pytest.raises(audit.AuditError):
        audit.check(r)


def test_write_read_and_30_day_purge(tmp_path: pathlib.Path) -> None:
    db = tmp_path / "a.sqlite"
    audit.write(rec(), db)
    assert [x["attempt_id"] for x in audit.read_all(db)] == ["x1"]
    assert audit.purge(db, now=datetime.now(UTC) + timedelta(days=29)) == 0
    assert audit.purge(db, now=datetime.now(UTC) + timedelta(days=31)) == 1
    assert audit.read_all(db) == []
