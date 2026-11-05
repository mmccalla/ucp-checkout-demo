"""AC-44: a Complete with no response. Get Checkout with bounded backoff, stop at `expires_at`,
at most one identical Complete with the same key, never a new key.

Source: UCP 2026-08-25 "Complete Checkout", used where compatible with 2026-04-08
(the URL is in the comment below this docstring). The text:
"If the Platform does not receive a response to Complete Checkout, it SHOULD use Get Checkout with
bounded backoff ... and MUST stop at `expires_at`. Only if Get Checkout still does not establish
whether the Business processed the original request, the Platform MAY submit the identical
original Complete Checkout request again with the same idempotency key."
"""

# AC-44 source: UCP 2026-08-25, "Complete Checkout": https://ucp.dev/2026-08-25/specification/shopping/checkout/#complete-checkout  # g1-allow-unpinned
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
from platform_app.checkout_client import RECOVERY_BACKOFF, CheckoutClient

ID = "chk_1"
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


class Script(httpx2.BaseTransport):
    """Each answer is a status and body, or None (a transport error)."""

    def __init__(self, complete: list[Any], get: list[Any]) -> None:
        self.queue = {"complete": list(complete), "get": list(get)}
        self.calls: list[tuple[str, str | None, bytes]] = []

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        op = "complete" if request.url.path.endswith("/complete") else "get"
        self.calls.append((op, request.headers.get("idempotency-key"), request.content))
        item = self.queue[op].pop(0)
        if item is None:
            raise httpx2.ReadTimeout("no response", request=request)
        return httpx2.Response(item[0], json=item[1], request=request)


def make(t: Script) -> tuple[CheckoutClient, list[float]]:
    waits: list[float] = []
    c = CheckoutClient(
        "http://business.test",
        "https://platform.test/profile",
        None,
        "k1",
        transport=t,
        sleep=waits.append,
        now=lambda: NOW,
        sign=False,
    )
    return c, waits


def co(status: str, **extra: Any) -> tuple[int, dict[str, Any]]:
    return 200, {"ucp": {"status": "success"}, "id": ID, "status": status, **extra}


def test_get_shows_completed_no_second_complete() -> None:
    t = Script([None], [co("completed", order={"id": "o1", "permalink_url": "https://x"})])
    c, waits = make(t)
    r = c.complete(ID, {"payment": {}}, (NOW + timedelta(hours=1)).isoformat())
    assert [x[0] for x in t.calls] == ["complete", "get"]
    assert r.op == "get" and r.body["status"] == "completed"
    assert [e.op for e in r.earlier] == ["complete"] and r.earlier[0].transport_error
    assert waits == [RECOVERY_BACKOFF[0]]


def test_get_shows_ready_one_identical_complete_same_key() -> None:
    t = Script([None, co("completed", order={"id": "o1"})], [co("ready_for_complete")])
    c, waits = make(t)
    r = c.complete(ID, {"payment": {"x": 1}}, (NOW + timedelta(hours=1)).isoformat())
    ops = [x[0] for x in t.calls]
    assert ops == ["complete", "get", "complete"]
    assert t.calls[0][1] == t.calls[2][1] and t.calls[0][1]  # same Idempotency-Key
    assert t.calls[0][2] == t.calls[2][2]  # same body
    assert r.op == "complete" and r.tries == 2 and r.status == 200
    assert [e.op for e in r.earlier] == ["complete", "get"]


def test_get_never_answers_waits_are_bounded_then_one_complete() -> None:
    n = len(RECOVERY_BACKOFF)
    t = Script([None, None], [None] * n)
    c, waits = make(t)
    r = c.complete(ID, {"payment": {}}, (NOW + timedelta(hours=1)).isoformat())
    assert [x[0] for x in t.calls] == ["complete"] + ["get"] * n + ["complete"]  # at most one more
    assert len({x[1] for x in t.calls if x[0] == "complete"}) == 1  # never a new key
    assert waits == list(RECOVERY_BACKOFF) and sum(waits) <= 4.0
    assert r.transport_error is not None and r.tries == 2


def test_stops_at_expires_at_no_get_no_second_complete() -> None:
    t = Script([None], [])
    c, waits = make(t)
    r = c.complete(ID, {"payment": {}}, (NOW - timedelta(seconds=1)).isoformat())
    assert [x[0] for x in t.calls] == ["complete"] and waits == []
    assert r.transport_error is not None


def test_in_progress_never_starts_a_new_complete() -> None:
    n = len(RECOVERY_BACKOFF)
    t = Script([None], [co("complete_in_progress")] * n)
    c, _ = make(t)
    r = c.complete(ID, {"payment": {}}, (NOW + timedelta(hours=1)).isoformat())
    assert [x[0] for x in t.calls].count("complete") == 1
    assert r.op == "get" and r.body["status"] == "complete_in_progress"


def test_response_received_is_not_a_recovery() -> None:
    t = Script([co("completed", order={"id": "o1"})], [])
    c, waits = make(t)
    r = c.complete(ID, {"payment": {}}, None)
    assert [x[0] for x in t.calls] == ["complete"] and r.earlier == [] and waits == []
