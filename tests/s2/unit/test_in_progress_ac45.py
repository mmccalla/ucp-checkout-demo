"""AC-45: a Business that answers `complete_in_progress`.

The Platform sends no Update and no Complete. It polls Get Checkout until a final status or
`expires_at`. The mock PSP has exactly one charge. The CI switch in the Business is
`BUSINESS_FAULTS=complete_in_progress=N,in_progress_gets=K` (spec 4.1, DM-10, T-44).
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from datetime import timedelta

import pytest
from platform_app.checkout_client import MAX_IN_PROGRESS_POLLS, RECOVERY_BACKOFF

from tests.s2.conftest import Pair, make_pair
from tests.s2.unit.test_complete_recovery import ID, NOW, Script, co, make
from tests.s4.conftest import complete_body, handler_id, ready


@pytest.fixture
def pair(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Pair]:
    yield from make_pair(
        tmp_path, monkeypatch, faults={"complete_in_progress": 1, "in_progress_gets": 2}
    )


def test_business_in_progress_then_completed_one_charge_no_update_no_second_complete(
    pair: Pair,
) -> None:
    c = ready(pair)
    seen: list[tuple[str, str, int | None]] = []
    orig = pair.client.http.request

    def spy(method: str, url: str, **kw: object) -> object:
        seen.append((method, str(url).split("9443")[-1], None))
        return orig(method, url, **kw)  # type: ignore[arg-type]

    pair.client.http.request = spy  # type: ignore[assignment]
    r = pair.client.complete(c["id"], complete_body(handler_id(c)), c.get("expires_at"))
    assert r.status == 200 and r.body["status"] == "completed", r.body
    assert r.body["order"]["id"]
    ops = [(m, p.rsplit("/", 1)[-1] if p.endswith("/complete") else "") for m, p, _ in seen]
    assert [m for m, _ in ops] == ["POST", "GET", "GET", "GET"], seen  # one Complete, 3 Gets
    assert [e.op for e in r.earlier] == ["complete", "get", "get"]
    assert [e.body["status"] for e in r.earlier] == ["complete_in_progress"] * 3
    assert "order" not in r.earlier[0].body
    assert len(pair.psp.attempts) == 1 and pair.psp.attempts[0]["status"] == "approved"
    assert pair.sleeps == list(RECOVERY_BACKOFF[:2]) + [RECOVERY_BACKOFF[2]]
    keys = {e.idempotency_key for e in r.earlier if e.op == "complete"}
    assert len(keys) == 1


def test_polls_stop_at_expires_at_before_any_get() -> None:
    t = Script([co("complete_in_progress")], [])
    c, waits = make(t)
    r = c.complete(ID, {"payment": {}}, (NOW - timedelta(seconds=1)).isoformat())
    assert [x[0] for x in t.calls] == ["complete"] and waits == []
    assert r.body["status"] == "complete_in_progress"


def test_polls_have_a_cap_when_expires_at_is_absent() -> None:
    t = Script([co("complete_in_progress")], [co("complete_in_progress")] * MAX_IN_PROGRESS_POLLS)
    c, waits = make(t)
    r = c.complete(ID, {"payment": {}}, None)
    assert [x[0] for x in t.calls] == ["complete"] + ["get"] * MAX_IN_PROGRESS_POLLS
    assert r.body["status"] == "complete_in_progress"
    assert max(waits) == RECOVERY_BACKOFF[-1]  # bounded
    assert len({x[1] for x in t.calls if x[0] == "complete"}) == 1
