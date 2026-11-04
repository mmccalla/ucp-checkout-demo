"""AC-39: out-of-stock at Complete as HTTP 200 with `messages`, or as HTTP 409.

Both forms give one state. The Platform sends no second Complete with the same key and it
sends Get Checkout (`send_get`). HTTP 409 for an idempotency conflict is not this state.
Source: https://ucp.dev/2026-04-08/specification/checkout-rest/ (03-spec U-12).
"""

from __future__ import annotations

from typing import Any

from platform_app import checkout_view as cv
from platform_app.checkout_client import Result

from tests.s2.unit.test_complete_recovery import ID, Script, co, make
from tests.s2.unit.test_view import checkout, err

GOOD = checkout("ready_for_complete", id="c1")


def complete(status: int, body: Any) -> Result:
    return Result(
        "complete", "POST", "/checkout-sessions/c1/complete", status, body, {}, "r", "k", 1
    )


def session() -> cv.Session:
    return cv.Session(last_good=GOOD)


def view_200() -> cv.View:
    body = checkout("ready_for_complete", id="c1", messages=[err("out_of_stock", "recoverable")])
    return cv.interpret(session(), complete(200, body))


def view_409() -> cv.View:
    return cv.interpret(
        session(), complete(409, {"code": "out_of_stock", "content": "Item is out of stock"})
    )


def key(v: cv.View) -> tuple[Any, ...]:
    return (v.state, [m["code"] for m in v.messages], v.controls, v.send_get, v.problem)


def test_200_and_409_show_the_same_state_and_send_get() -> None:
    a, b = view_200(), view_409()
    assert key(a) == key(b)
    assert a.state == "out_of_stock" and a.send_get and cv.COMPLETE not in a.controls
    assert b.checkout == GOOD  # the last good checkout stays


def test_409_with_ucp_error_body_and_stock_message() -> None:
    body = {
        "ucp": {"version": "2026-04-08", "status": "error"},
        "messages": [err("out_of_stock", "recoverable")],
    }
    v = cv.interpret(session(), complete(409, body))
    assert key(v) == key(view_200())


def test_409_idempotency_conflict_is_not_out_of_stock() -> None:
    v = cv.interpret(
        session(), complete(409, {"code": "idempotency_key_reused", "content": "Key used"})
    )
    assert v.state == "setup_problem" and not v.send_get


def test_out_of_stock_on_create_is_unchanged() -> None:
    body = checkout(messages=[err("out_of_stock", "recoverable")])
    r = Result("create", "POST", "/checkout-sessions", 200, body, {}, "r", None, 1)
    v = cv.interpret(cv.Session(), r)
    assert v.state != "out_of_stock" and not v.send_get


def test_client_sends_one_complete_only_for_each_form() -> None:
    for status, body in (
        (200, co("ready_for_complete", messages=[err("out_of_stock", "recoverable")])[1]),
        (409, {"code": "out_of_stock", "content": "stock"}),
    ):
        t = Script([(status, body)], [])
        c, waits = make(t)
        r = c.complete(ID, {"payment": {}}, None)
        assert [x[0] for x in t.calls] == ["complete"] and waits == []
        assert r.status == status and r.tries == 1
