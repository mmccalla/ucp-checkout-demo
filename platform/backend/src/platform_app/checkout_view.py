"""Platform checkout state and buyer controls from Business responses (S2).

The S3 page renders this view model. The rules come from the pinned spec text
(UCP 9c9d6fc, `docs/specification/checkout.md` and `overview.md`) and spec v1.1.2.

- AC-14: an `error_response` or a message with code `out_of_stock` or
  `address_undeliverable` gives the two controls "Change item" / "Change address" and
  "Back to items". It never shows Complete.
- AC-15: severity `requires_buyer_input` asks the buyer for the field at `path`. The
  Platform never makes up a value.
- AC-16: status `requires_escalation` shows a link to `continue_url` and no Complete
  (checkout.md, "Continue URL").
- AC-17: severity `unrecoverable` shows the message and "Back to items".
- AC-40: an unknown `status` value is logged (ENUM_UNKNOWN_LOGGED). The state does not
  change. The Platform sends one Get. If the value stays unknown, it stops and shows it.
- AC-41: an `error_response` keeps the last good checkout and shows the messages.
- AC-53, AC-10: a protocol error (`{code, content}`) or a transport error is a setup
  problem, not a payment problem. The Platform shows the code and the HTTP status.
- AC-99: a message of type `error` with code `signal` stops the flow and shows the message.
  The Platform sends no risk signals in v1 (AC-37), so it cannot act on such a message.
- Each message with a `path` gets an element id. The field that the path names gets
  `aria-describedby` with that id (WCAG 2.2 SC 3.3.1, AC-14).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

from .checkout_client import Result

STATUSES = (
    "incomplete",
    "requires_escalation",
    "ready_for_complete",
    "complete_in_progress",
    "completed",
    "canceled",
)
CHANGE_ITEM, CHANGE_ADDRESS, BACK, COMPLETE, CONTINUE = (
    "change_item",
    "change_address",
    "back_to_items",
    "complete",
    "continue_on_business",
)


@dataclass
class View:
    state: str
    checkout: dict[str, Any] | None
    messages: list[dict[str, Any]] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)
    problem: dict[str, Any] | None = None
    ask_buyer: list[str] = field(default_factory=list)
    continue_url: str | None = None
    logs: list[str] = field(default_factory=list)
    send_get: bool = False


@dataclass
class Session:
    last_good: dict[str, Any] | None = None
    unknown_status_gets: int = 0
    history: list[View] = field(default_factory=list)


def _msg_id(i: int) -> str:
    return f"ucp-msg-{i}"


def field_id(path: str) -> str:
    """Map a JSONPath such as `$.line_items[0]` to a stable element id."""
    return "field-" + re.sub(r"[^a-z0-9]+", "-", path.lower().lstrip("$.")).strip("-")


def _messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for i, m in enumerate(body.get("messages") or []):
        if not isinstance(m, dict):
            continue
        item = dict(m)
        item["element_id"] = _msg_id(i)
        if isinstance(m.get("path"), str):
            item["field_id"] = field_id(m["path"])
        out.append(item)
    return out


def _change_controls(msgs: list[dict[str, Any]]) -> list[str]:
    codes = {m.get("code") for m in msgs}
    first = CHANGE_ADDRESS if "address_undeliverable" in codes else CHANGE_ITEM
    return [first, BACK]


def _stock_at_complete_409(res: Result, b: dict[str, Any]) -> list[dict[str, Any]] | None:
    """AC-39: HTTP 409 at Complete with an out-of-stock reason. Else None.

    HTTP 409 for an idempotency conflict (checkout-rest) has no stock reason, so it does not
    match. Source: https://ucp.dev/2026-04-08/specification/checkout-rest/ and 03-spec U-12.
    """
    if res.op != "complete" or res.status != 409:
        return None
    msgs = _messages(b)
    text = " ".join(
        [str(b.get("code", "")), str(b.get("content", ""))]
        + [f"{m.get('code', '')} {m.get('content', '')}" for m in msgs]
    ).lower()
    if "stock" not in text:
        return None
    if not any(m.get("code") == "out_of_stock" for m in msgs):
        msgs = [
            {
                "type": "error",
                "code": "out_of_stock",
                "content": str(b.get("content") or "An item is out of stock."),
                "severity": "recoverable",
                "element_id": _msg_id(0),
            }
        ]
    return msgs


def _out_of_stock_view(
    session: Session, res: Result, msgs: list[dict[str, Any]], b: dict[str, Any]
) -> View:
    """AC-39: one state for the 200 form and the 409 form. The Platform sends Get Checkout.

    It never sends the same Complete again (the client sends a Complete one time) and it keeps
    the last good checkout. `send_get` makes `main._view` send the Get.
    """
    if isinstance(b.get("id"), str) and b.get("status") in STATUSES:
        session.last_good = b
    return View(
        "out_of_stock",
        session.last_good,
        msgs,
        _change_controls(msgs),
        logs=[f"OUT_OF_STOCK_AT_COMPLETE http_status={res.status}"],
        send_get=True,
    )


def interpret(session: Session, res: Result) -> View:
    v = _interpret(session, res)
    session.history.append(v)
    return v


def _interpret(session: Session, res: Result) -> View:
    if res.status is None:
        return View(
            "setup_problem",
            session.last_good,
            problem={
                "kind": "transport",
                "code": res.transport_error,
                "http_status": None,
                "tries": res.tries,
                "payment_problem": False,
            },
            controls=[BACK],
        )
    b = res.body if isinstance(res.body, dict) else {}
    stock = _stock_at_complete_409(res, b)
    if stock is not None:  # AC-39: the 409 form of out-of-stock at Complete
        return _out_of_stock_view(session, res, stock, b)
    if "ucp" not in b:
        return View(
            "setup_problem",
            session.last_good,
            problem={
                "kind": "protocol",
                "code": b.get("code"),
                "content": b.get("content"),
                "http_status": res.status,
                "continue_url": b.get("continue_url"),
                "tries": res.tries,
                "payment_problem": False,
            },
            controls=[BACK],
        )
    if res.schema_problems:
        return View(
            "setup_problem",
            session.last_good,
            problem={
                "kind": "schema",
                "code": "response_schema_invalid",
                "content": res.schema_problems[:5],
                "http_status": res.status,
                "payment_problem": False,
            },
            controls=[BACK],
        )
    msgs = _messages(b)
    if b["ucp"].get("status") == "error" or "id" not in b:
        # AC-41 and AC-14: no checkout in the body. Keep the last good checkout.
        return View("error_response", session.last_good, msgs, _change_controls(msgs))
    status = b.get("status")
    if status not in STATUSES:
        session.unknown_status_gets += 1
        v = View(
            "unchanged",
            session.last_good,
            msgs,
            [BACK],
            logs=[f"ENUM_UNKNOWN_LOGGED field=status value={status!r}"],
        )
        if session.unknown_status_gets == 1:
            v.send_get = True
        else:
            v.state = "stopped"
            v.problem = {
                "kind": "enum",
                "code": "status_unknown",
                "content": str(status),
                "http_status": res.status,
                "payment_problem": False,
            }
        return v
    session.unknown_status_gets = 0
    session.last_good = b
    signal = [m for m in msgs if m.get("type") == "error" and m.get("code") == "signal"]
    if signal:
        return View(
            "stopped",
            b,
            msgs,
            [BACK],
            problem={
                "kind": "message",
                "code": "signal",
                "content": signal[0].get("content"),
                "http_status": res.status,
                "payment_problem": False,
            },
        )
    v = View(str(status), b, msgs)
    sev = {m.get("severity") for m in msgs if m.get("type") == "error"}
    codes = {m.get("code") for m in msgs}
    if status == "requires_escalation":
        v.continue_url = b.get("continue_url")
        v.controls = [CONTINUE, BACK] if v.continue_url else [BACK]
        return v
    if "unrecoverable" in sev:
        v.controls = [BACK]
        return v
    if res.op == "complete" and "out_of_stock" in codes:  # AC-39: the HTTP 200 form
        return _out_of_stock_view(session, res, msgs, b)
    if codes & {"out_of_stock", "address_undeliverable", "item_unavailable"}:
        v.controls = _change_controls(msgs)
        return v
    if "requires_buyer_input" in sev:
        v.ask_buyer = [
            m["path"]
            for m in msgs
            if m.get("severity") == "requires_buyer_input" and isinstance(m.get("path"), str)
        ]
        v.controls = [BACK]
        return v
    if status == "ready_for_complete":
        v.controls = [COMPLETE, BACK]
    else:
        v.controls = [BACK]
    return v


def render_messages(v: View) -> str:
    """HTML for the message list. Each message has an id for `aria-describedby`."""
    items = []
    for m in v.messages:
        role = ' role="alert"' if m.get("type") == "error" else ""
        items.append(
            f'<li id="{html.escape(m["element_id"])}"{role} data-code="'
            f'{html.escape(str(m.get("code", "")))}">{html.escape(str(m.get("content", "")))}</li>'
        )
    return '<ul class="ucp-messages">' + "".join(items) + "</ul>"


def described_by(v: View) -> dict[str, str]:
    """Map each field id to the message ids for its `aria-describedby` attribute."""
    out: dict[str, list[str]] = {}
    for m in v.messages:
        if "field_id" in m:
            out.setdefault(m["field_id"], []).append(m["element_id"])
    return {k: " ".join(ids) for k, ids in out.items()}
