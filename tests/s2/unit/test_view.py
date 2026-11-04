"""G3 unit, S2: the Platform checkout view (AC-15, AC-16, AC-17, AC-40, AC-53, AC-99, AC-10)."""

from __future__ import annotations

from typing import Any

from platform_app import checkout_view as cv
from platform_app.checkout_client import Result

V = "2026-04-08"


def res(body: Any, status: int = 200) -> Result:
    return Result("get", "GET", "/checkout-sessions/c1", status, body, {}, "rid", None, 1)


def checkout(
    status: str = "incomplete", messages: list[dict[str, Any]] | None = None, **extra: Any
) -> dict[str, Any]:
    b: dict[str, Any] = {
        "ucp": {"version": V, "status": "success"},
        "id": "c1",
        "status": status,
        "messages": messages or [],
    }
    b.update(extra)
    return b


def err(code: str, severity: str, path: str | None = None) -> dict[str, Any]:
    m = {"type": "error", "code": code, "content": f"{code} text", "severity": severity}
    if path:
        m["path"] = path
    return m


def test_ac15_requires_buyer_input_asks_and_invents_nothing() -> None:
    body = checkout(messages=[err("missing", "requires_buyer_input", "$.buyer.email")])
    v = cv.interpret(cv.Session(), res(body))
    assert v.ask_buyer == ["$.buyer.email"]
    assert cv.COMPLETE not in v.controls
    assert "buyer" not in (v.checkout or {})
    assert cv.described_by(v) == {"field-buyer-email": "ucp-msg-0"}


def test_ac16_requires_escalation_links_continue_url_no_complete() -> None:
    body = checkout("requires_escalation", continue_url="https://localhost:9443/continue/c1")
    v = cv.interpret(cv.Session(), res(body))
    assert v.continue_url == "https://localhost:9443/continue/c1"
    assert v.controls == [cv.CONTINUE, cv.BACK]


def test_ac17_unrecoverable_offers_back_to_items() -> None:
    v = cv.interpret(
        cv.Session(), res(checkout(messages=[err("item_unavailable", "unrecoverable")]))
    )
    assert v.controls == [cv.BACK]
    assert "item_unavailable text" in cv.render_messages(v)


def test_ac40_unknown_status_logged_one_get_then_stop() -> None:
    s = cv.Session()
    cv.interpret(s, res(checkout("incomplete")))
    v1 = cv.interpret(s, res(checkout("ready_for_payment")))
    assert v1.logs == ["ENUM_UNKNOWN_LOGGED field=status value='ready_for_payment'"]
    assert v1.send_get is True and v1.state == "unchanged"
    assert s.last_good is not None and s.last_good["status"] == "incomplete"
    assert cv.COMPLETE not in v1.controls
    v2 = cv.interpret(s, res(checkout("ready_for_payment")))
    assert v2.send_get is False and v2.state == "stopped"
    assert v2.problem is not None and v2.problem["content"] == "ready_for_payment"


def test_ac53_and_ac10_protocol_error_is_setup_problem() -> None:
    for status, code in (
        (424, "profile_unreachable"),
        (422, "profile_malformed"),
        (422, "version_unsupported"),
        (401, "signature_missing"),
        (503, "store_unavailable"),
    ):
        v = cv.interpret(cv.Session(), res({"code": code, "content": "x"}, status))
        assert v.state == "setup_problem"
        assert v.problem is not None
        assert (v.problem["code"], v.problem["http_status"]) == (code, status)
        assert v.problem["payment_problem"] is False


def test_transport_error_is_setup_problem() -> None:
    r = Result("update", "PUT", "/x", None, None, {}, "rid", "k", 3, transport_error="ConnectError")
    v = cv.interpret(cv.Session(), r)
    assert v.state == "setup_problem" and v.problem is not None and v.problem["tries"] == 3


def test_ac99_signal_error_stops_and_shows() -> None:
    v = cv.interpret(cv.Session(), res(checkout(messages=[err("signal", "recoverable")])))
    assert v.state == "stopped"
    assert v.problem is not None and v.problem["code"] == "signal"
    assert v.problem["content"] == "signal text"


def test_render_escapes_and_has_ids() -> None:
    m = err("out_of_stock", "recoverable", "$.line_items[0]")
    m["content"] = "<b>x</b>"
    v = cv.interpret(cv.Session(), res(checkout(messages=[m])))
    html = cv.render_messages(v)
    assert 'id="ucp-msg-0"' in html and "&lt;b&gt;" in html and 'role="alert"' in html
