"""G7, S5: AC-39 in the browser. Out-of-stock at Complete as HTTP 200 or as HTTP 409.

The page shows the same state for both forms. The Platform sends no second Complete with the
same Idempotency-Key. It sends Get Checkout. Source: https://ucp.dev/2026-04-08/specification/checkout-rest/
(03-spec U-12). The test changes the Complete answer in the harness hook only (no source file).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2
from playwright.sync_api import expect

from tests.evidence import evidence_dir
from tests.s3.e2e.conftest import Stack
from tests.s3.e2e.test_g7_flow import open_page, to_review

EVIDENCE = evidence_dir("S5", "ac39")
MSG = {
    "type": "error",
    "code": "out_of_stock",
    "content": "An item is out of stock.",
    "severity": "recoverable",
}


def _run(s: Stack, form: str) -> dict[str, Any]:
    last: dict[str, Any] = {}

    def keep(_req: httpx2.Request, body: dict[str, Any]) -> dict[str, Any] | None:
        last.update(body)  # the last good checkout; the answer is not changed
        return None

    s.hook.mutate["update"] = keep
    s.hook.mutate["get"] = keep
    open_page(s)
    to_review(s)
    assert last.get("status") == "ready_for_complete", last.get("status")
    # The Complete request does not reach the Business: the hook answers in its place.
    if form == "200":
        s.hook.status["complete"] = (200, {**last, "messages": [MSG]})
    else:
        s.hook.status["complete"] = (
            409,
            {"ucp": {"version": "2026-04-08", "status": "error"}, "messages": [MSG]},
        )
    p = s.page
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Shop and item", timeout=10000)
    expect(p.locator("#msg-list")).to_contain_text("Complete")
    page_text = p.locator("#screen").inner_text()
    assert "out of stock" in page_text.lower(), page_text
    assert p.locator("#add").is_visible()  # Change item
    expect(p.locator("#screen-title")).to_have_text("Shop and item")  # it stays
    ops = [c["op"] for c in s.hook.calls]
    completes = [c for c in s.hook.calls if c["op"] == "complete"]
    after = ops[ops.index("complete") + 1 :]
    return {
        "form": form,
        "title": p.locator("#screen-title").inner_text(),
        "has_change_item": True,
        "pay_button_visible": p.locator(".gpay-stub-button").is_visible(),
        "complete_calls": len(completes),
        "same_key_sent_twice": len({c["idempotency_key"] for c in completes}) != len(completes),
        "get_after_complete": "get" in after,
    }


def test_ac39_200_and_409_show_the_same_state_in_the_browser(
    make_stack: Callable[..., Stack],
) -> None:
    a = _run(make_stack(), "200")
    b = _run(make_stack(), "409")
    for r in (a, b):
        assert r["complete_calls"] == 1 and not r["same_key_sent_twice"], r
        assert r["get_after_complete"], r
        assert not r["pay_button_visible"], r
    same = {k: v for k, v in a.items() if k != "form"} == {
        k: v for k, v in b.items() if k != "form"
    }
    assert same, (a, b)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ac39-browser.json").write_text(json.dumps({"200": a, "409": b}, indent=2) + "\n")
