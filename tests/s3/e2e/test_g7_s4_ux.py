"""G7 for the S4 UX decisions (spec 15.8 rows 3 to 5, input-ux.md 4.5.1, UX-AC-31 to UX-AC-33).

- UX-AC-31: severity and `Idempotency-Key` on the decline row (checkout.md lines 125 to 132 at
  UCP 9c9d6fc: https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/docs/specification/checkout.md#L125-L132).
- UX-AC-32: `inspector.retry.sameKey` shows only in CI with the test seam (Hook.drop_response).
  The seam is not in demo mode and not in /.well-known/ucp.
- UX-AC-33: code words. HTML code element https://html.spec.whatwg.org/multipage/text-level-semantics.html#the-code-element
  and ARIA in HTML "Naming Prohibited" https://www.w3.org/TR/html-aria/#el-code.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from platform_app import main as pmain
from playwright.sync_api import Page, expect
from ucp_core.constants import ROOT

from tests.evidence import evidence_dir
from tests.s3.e2e.conftest import Stack
from tests.s3.e2e.test_g7_flow import open_page, to_review
from tests.s3.e2e.test_g7_s4 import _write

APP_JS = ROOT / "platform" / "web" / "checkout" / "app.js"
APP_CSS = ROOT / "platform" / "web" / "checkout" / "app.css"
SEVERITY_TEXT = (
    "What the agent must do about this message: fix it, ask you, or stop. "
    "recoverable: the Platform can fix this with a new request. "
    "The buyer does not go to the shop website."
)
KEY_TEXT = "A key that stops the shop from doing the same operation two times."
SAME_KEY = (
    "Same Idempotency-Key and same body. The shop sends its stored response again. "
    "It does not call the payment processor again."
)
SEAM_NAMES = ("drop_response", "set_psp_calls", "psp_calls", "same_key")


def _keys(p: Page) -> list[str]:
    return [t.strip() for t in p.locator("#msg-detail dl.keys dt").all_inner_texts()]


def _open_last(p: Page) -> None:
    rows = p.locator("#msg-list button")
    rows.nth(rows.count() - 1).click()


def _dd(p: Page, name: str) -> Any:
    return p.locator("#msg-detail dl.keys dd").nth(_keys(p).index(name))


def _no_code_naming(p: Page) -> None:
    bad = p.evaluate(
        """() => [...document.querySelectorAll('code')].filter(c =>
          c.hasAttribute('aria-label') || c.hasAttribute('aria-labelledby') || c.hasAttribute('title')
          || c.hasAttribute('hidden') || c.hasAttribute('aria-hidden')
          || c.querySelector('[aria-label],[title],[hidden],[aria-hidden],.visually-hidden')
          || (c.nextElementSibling && c.nextElementSibling.classList.contains('visually-hidden'))
          ).map(c => c.outerHTML)"""
    )
    assert bad == [], bad


# ---------------------------------------------------------------- UX-AC-31
def test_ux_ac31_decline_row_severity_and_key(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    s.pair.psp.outcome = "decline"
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#declined-heading")).to_be_visible(timeout=10000)
    _open_last(p)
    expect(p.locator("#msg-detail")).to_contain_text("HTTP 200")
    assert _keys(p) == [
        "HTTP status",
        "status",
        "messages[0].code",
        "messages[0].severity",
        "Idempotency-Key",
        "total",
    ]
    code = _dd(p, "messages[0].code")
    sev = _dd(p, "messages[0].severity")
    # Value in a code element, visible text only, no aria-label.
    assert code.locator("> code").inner_text() == "payment_failed"
    assert sev.locator("> code").inner_text() == "recoverable"
    assert sev.locator(".explain").inner_text() == SEVERITY_TEXT
    assert sev.locator(".explain code").inner_text() == "recoverable"
    assert _dd(p, "Idempotency-Key").locator(".explain").inner_text() == KEY_TEXT
    key_row = p.locator("#msg-detail dl.keys dt").nth(3)
    assert key_row.locator("code").inner_text() == "messages[0].severity"
    for e in p.locator("#msg-detail dl.keys").locator("dt, dd").all():
        assert e.get_attribute("aria-label") is None
    _no_code_naming(p)
    # The key is the one that the Platform sent.
    ks = [c["idempotency_key"] for c in s.hook.calls if c["op"] == "complete"]
    assert _dd(p, "Idempotency-Key").locator("> code").inner_text() == ks[-1]
    # UX-AC-32: no same-key note on a decline row, and no old key text.
    assert SAME_KEY not in p.locator("#msg-detail").inner_text()
    assert "A retry sends the same key." not in p.content()
    # The second decline keeps the key field and the order. A retry has a new key (AC-35).
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#declined-heading")).to_have_text("Payment declined again", timeout=10000)
    _open_last(p)
    expect(p.locator("#msg-detail")).to_contain_text("new `Idempotency-Key`".replace("`", ""))
    assert _keys(p)[3:5] == ["messages[0].severity", "Idempotency-Key"]
    s.pair.psp.outcome = "approve"
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    _open_last_complete(p)
    assert _keys(p) == ["HTTP status", "status", "order.id", "Idempotency-Key", "total"]
    assert SAME_KEY not in p.locator("#msg-detail").inner_text()
    _write("ux-ac31-decline-keys.json", {"keys": _keys(p)})


def _open_last_complete(p: Page) -> None:
    rows = p.locator("#msg-list button", has_text="Complete")
    rows.nth(rows.count() - 1).click()


# ---------------------------------------------------------------- UX-AC-32
def test_ux_ac32_same_key_note_only_with_seam(make_stack: Callable[..., Stack]) -> None:
    """CI mode with the seam: Complete response lost, same key and body, no second PSP call.

    The Get Checkout calls of the AC-44 recovery also get no response. So the Platform cannot
    learn what the Business did. It sends the identical Complete one time (UCP 2026-08-25,
    Complete Checkout). The Business sends its stored response again.
    """
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    s.hook.drop_response["complete"] = 1
    s.hook.drop_get_after_complete = 3
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=15000)
    complete = [c for c in s.hook.calls if c["op"] == "complete"]
    assert len(complete) == 2 and all(c["reached"] for c in complete)  # the first one arrived
    assert complete[0]["idempotency_key"] == complete[1]["idempotency_key"]
    assert complete[0]["request_id"] == complete[1]["request_id"]
    cid = p.evaluate("window.__ucpDemo.checkout.id")
    assert s.pair.psp.calls[cid] == 1  # no new charge for the second request
    assert [a["status"] for a in s.pair.psp.attempts] == ["approved"]
    _open_last_complete(p)
    note = p.locator("#msg-detail .note", has_text="stored response")
    expect(note).to_have_count(1)
    assert note.inner_text() == SAME_KEY
    assert note.locator("code").inner_text() == "Idempotency-Key"
    assert _keys(p) == ["HTTP status", "status", "order.id", "Idempotency-Key", "tries"]
    assert _dd(p, "tries").locator("> code").inner_text() == "2"
    _no_code_naming(p)
    # The note is on one row only: the final Complete row. The first Complete row (no response)
    # and the Get Checkout rows of the recovery have no note.
    with_note = []
    for i in range(p.locator("#msg-list button").count()):
        p.locator("#msg-list button").nth(i).click()
        if SAME_KEY in p.locator("#msg-detail").inner_text():
            with_note.append(p.locator("#msg-detail h3").inner_text())
    assert len(with_note) == 1 and "Complete" in with_note[0], with_note
    ops = [c["op"] for c in s.hook.calls]
    assert ops[-5:] == ["complete", "get", "get", "get", "complete"], ops  # AC-44: bounded
    p.screenshot(path=str(evidence_dir("S4", "g7") / "ux-ac32-same-key.png"))


def test_ux_ac32_no_note_without_same_key(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    for i in range(p.locator("#msg-list button").count()):
        p.locator("#msg-list button").nth(i).click()
        assert SAME_KEY not in p.locator("#msg-detail").inner_text()
    assert "stored response" not in p.locator("#inspector").inner_text()


def test_ux_ac32_seam_not_in_demo_mode_and_not_in_well_known(
    make_stack: Callable[..., Stack], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seam has no effect in demo mode. No route and no profile reaches it."""
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    calls: list[str] = []

    def counted(cid: str) -> int:
        calls.append(cid)
        return int(s.pair.psp.calls.get(cid, 0))

    pmain.set_psp_calls(counted)
    s.hook.drop_response["complete"] = 1  # the harness seam is on, as in CI
    s.hook.drop_get_after_complete = 3
    monkeypatch.setattr(pmain, "MODE", "demo")  # the page is loaded. The server is in demo mode.
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=15000)
    assert calls == []  # demo mode never calls the seam function
    _open_last_complete(p)
    assert _keys(p)[-1] == "tries"  # two tries, the same key
    assert SAME_KEY not in p.locator("#msg-detail").inner_text()  # but no note in demo mode
    assert "same_key" not in p.evaluate("JSON.stringify(window.__ucpDemo || {})")
    monkeypatch.setattr(pmain, "MODE", "ci")
    # /.well-known/ucp of the Business and of the Platform, and the page config, have no seam.
    bodies = [
        s.pair.biz.get("/.well-known/ucp").text,
        p.request.get(s.base + "/.well-known/ucp").text(),
        p.request.get(s.base + "/checkout/config.json").text(),
        p.request.get(s.base + "/readyz").text(),
    ]
    for b in bodies:
        for name in SEAM_NAMES:
            assert name not in b, (name, b[:200])
    # No route of the Platform or of the Business app has a seam name.
    for app in (pmain.app, s.pair.app):
        paths = [getattr(r, "path", "") for r in app.routes]
        assert not [x for x in paths if any(n in x for n in SEAM_NAMES)], paths
    # No source file of a service has the harness seam. Only `set_psp_calls` is in main.py.
    for d in ("platform", "business/src", "psp-mock", "libs"):
        for f in (ROOT / d).rglob("*"):
            if f.suffix not in (".py", ".js", ".json", ".html") or "vendor" in f.parts:
                continue
            t = f.read_text(errors="ignore")
            assert "drop_response" not in t, f
            if "set_psp_calls" in t:
                assert f.name == "main.py" and "platform_app" in f.parts, f


# ---------------------------------------------------------------- UX-AC-33
def _strings(src: str, start: str, end: str) -> dict[str, str]:
    block = src[src.index(start) : src.index(end, src.index(start))]
    return dict(re.findall(r'^\s+"([^"]+)": "((?:[^"\\]|\\.)*)",?\s*$', block, re.M))


def test_ux_ac33_copy_strings_have_even_back_quotes_and_new_keys() -> None:
    src = APP_JS.read_text()
    copy = _strings(src, "const S = {", "const fmt")
    explain = _strings(src, "const EXPLAIN = {", "function get(")
    assert len(copy) > 40 and len(explain) > 20
    for k, v in {**copy, **explain}.items():
        assert v.count("`") % 2 == 0, (k, v)  # an odd count is an authoring error
    # Buyer-view strings have no code word. Only the inspector strings have back-quotes.
    for k, v in copy.items():
        if not k.startswith("inspector."):
            assert "`" not in v, (k, v)
    assert copy["escalation.noLink"] == "The shop did not give a link to its website."
    assert copy["gpay.checkResult"] == "Google Pay check result:"
    assert "The shop gave no" not in src and "isReadyToPay result:" not in src
    assert "A retry sends the same key." not in src
    assert explain["Idempotency-Key"] == KEY_TEXT
    assert "REPLAY. Recorded messages. No calls go out." not in src  # the old replay text
    css = APP_CSS.read_text()
    assert "--font-family-code:" in css and len(re.findall(r"^code \{", css, re.M)) == 1


def _page_code_checks(p: Page, label: str) -> None:
    for region in ("#buyer-view", "#inspector"):
        assert "`" not in p.locator(region).inner_text(), (label, region)
        assert "`" not in p.locator(region).inner_html(), (label, region)
    # Buyer view: a code element only after a plain label that ends with a colon.
    bad = p.evaluate(
        """() => [...document.querySelectorAll('#buyer-view code')].filter(c => {
          const t = c.previousSibling; const txt = (t && t.textContent || '').trim();
          return !txt.endsWith(':'); }).map(c => c.parentElement.outerHTML)"""
    )
    assert bad == [], (label, bad)
    _no_code_naming(p)


def test_ux_ac33_code_words_on_screens(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    p = s.page
    open_page(s)
    p.locator("#toggle-inspector").click() if p.locator("#toggle-inspector").is_visible() else None
    _page_code_checks(p, "SC1")
    to_review(s)
    _page_code_checks(p, "SC4")
    s.pair.psp.outcome = "decline"
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#declined-heading")).to_be_visible(timeout=10000)
    _open_last(p)
    _page_code_checks(p, "ST13")
    assert p.locator("#msg-detail code").count() >= 8
    # Each inspector copy code word is in a code element: the note and the explanations.
    html = p.locator("#msg-detail").inner_html()
    assert "<code>status</code>" in html and "<code>ready_for_complete</code>" in html
    assert "<code>severity</code>" in html and "<code>recoverable</code>" in html
    s.pair.psp.outcome = "approve"
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    _page_code_checks(p, "SC6")
    for i in range(p.locator("#msg-list button").count()):
        p.locator("#msg-list button").nth(i).click()
        _page_code_checks(p, f"row {i}")


def test_ux_ac33_no_link_and_check_result_strings(make_stack: Callable[..., Stack]) -> None:
    # Totals mismatch with no continue_url.
    s = make_stack()

    def bad_total(req: Any, body: dict[str, Any]) -> dict[str, Any]:
        for e in body.get("totals", []):
            if e["type"] == "total":
                e["amount"] += 1
        return body

    open_page(s)
    s.hook.mutate["get"] = bad_total
    to_review(s)
    expect(s.page.locator("#gate-panel #no-link")).to_have_text(
        "The shop did not give a link to its website. Cancel the checkout or start again."
    )
    assert "continue_url" not in s.page.locator("#buyer-view").inner_text()
    _page_code_checks(s.page, "totals no link")
    # Escalation with no continue_url.
    s2 = make_stack()

    def esc(req: Any, body: dict[str, Any]) -> dict[str, Any]:
        body["status"] = "requires_escalation"
        body["messages"] = [
            {
                "type": "error",
                "code": "requires_3ds",
                "content": "Finish on the shop website.",
                "severity": "requires_buyer_review",
            }
        ]
        return body

    open_page(s2)
    s2.hook.mutate["update"] = esc
    p = s2.page
    p.locator("#start").click()
    p.locator("#next-step").click()
    p.locator("#add").click()
    p.locator("#next-step").click()
    p.locator("#field-buyer-email").fill("buyer@example.com")
    p.locator("#continue").click()
    p.locator("#next-step").click()
    expect(p.locator("#no-link")).to_have_text("The shop did not give a link to its website.")
    assert "continue_url" not in p.locator("#buyer-view").inner_text()
    _page_code_checks(p, "escalation no link")
    # Google Pay check result label.
    s3 = make_stack(gpay={"ready": False})
    open_page(s3)
    to_review(s3)
    box = s3.page.locator("#gpay-state")
    expect(box).to_contain_text("Google Pay check result: false")
    assert "isReadyToPay result" not in box.inner_text()
    _page_code_checks(s3.page, "gpay check result")


def test_ux_ac33_code_style_and_320px_wrap(make_stack: Callable[..., Stack]) -> None:
    s = make_stack(viewport=(320, 800))
    p = s.page
    open_page(s)
    p.locator("#toggle-inspector").click()
    to_review(s)
    s.pair.psp.outcome = "decline"
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#declined-heading")).to_be_visible(timeout=10000)
    _open_last(p)
    info = p.evaluate(
        """() => { const root = getComputedStyle(document.documentElement);
          const bodyPx = parseFloat(getComputedStyle(document.body).fontSize);
          const codes = [...document.querySelectorAll('#msg-detail code')];
          return { token: root.getPropertyValue('--font-family-code').trim(),
            vw: document.documentElement.clientWidth, sw: document.documentElement.scrollWidth,
            bodyPx, n: codes.length,
            rows: codes.map(c => { const cs = getComputedStyle(c); const ps = getComputedStyle(c.parentElement);
              const r = c.getBoundingClientRect();
              return { family: cs.fontFamily, px: parseFloat(cs.fontSize), parentPx: parseFloat(ps.fontSize),
                color: cs.color, parentColor: ps.color, bg: cs.backgroundColor, right: r.right, text: c.textContent }; }) }; }"""
    )
    assert info["token"].startswith("ui-monospace") and info["n"] >= 8
    assert info["sw"] <= info["vw"], info  # no horizontal scroll at 320 px (SC 1.4.10)
    for r in info["rows"]:
        assert "monospace" in r["family"], r
        assert r["px"] >= info["bodyPx"] - 0.01 and r["px"] >= r["parentPx"] - 0.01, r
        assert r["color"] == r["parentColor"], r  # same colour as the text next to it
        assert r["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), r  # no background: no new pair
        assert r["right"] <= info["vw"] + 1, r  # a long name wraps inside the screen
    _write("ux-ac33-code-style-320.json", info)
    json.dumps(info)


# ---------------------------------------------------------------- AC-44 (full stack)
def test_ac44_response_lost_get_shows_completed_no_second_complete(
    make_stack: Callable[..., Stack],
) -> None:
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    s.hook.drop_response["complete"] = 1  # the Business placed the order. The reply is lost.
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=15000)
    ops = [c["op"] for c in s.hook.calls]
    assert ops[-2:] == ["complete", "get"] and ops.count("complete") == 1, ops
    cid = p.evaluate("window.__ucpDemo.checkout.id")
    assert s.pair.psp.calls[cid] == 1 and [a["status"] for a in s.pair.psp.attempts] == ["approved"]
    for i in range(p.locator("#msg-list button").count()):
        p.locator("#msg-list button").nth(i).click()
        assert SAME_KEY not in p.locator("#msg-detail").inner_text()  # no resend: no note
    _write("ac44-response-lost.json", {"ops": ops})


def test_ac44_request_lost_get_shows_ready_one_identical_complete(
    make_stack: Callable[..., Stack],
) -> None:
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    s.hook.drop["complete"] = 1  # the request never reaches the Business
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=15000)
    complete = [c for c in s.hook.calls if c["op"] == "complete"]
    assert len(complete) == 2 and not complete[0]["reached"] and complete[1]["reached"]
    assert complete[0]["idempotency_key"] == complete[1]["idempotency_key"]
    assert [c["op"] for c in s.hook.calls][-3:] == ["complete", "get", "complete"]
    cid = p.evaluate("window.__ucpDemo.checkout.id")
    assert s.pair.psp.calls[cid] == 1
    # The Business had no stored response, so the note is not true here. It does not show.
    for i in range(p.locator("#msg-list button").count()):
        p.locator("#msg-list button").nth(i).click()
        assert SAME_KEY not in p.locator("#msg-detail").inner_text()


def test_ac44_nothing_answers_at_most_one_more_complete_no_new_key(
    make_stack: Callable[..., Stack],
) -> None:
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    s.hook.drop["complete"] = 5
    s.hook.drop_get_after_complete = 0
    s.hook.drop["get"] = 0
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("We cannot reach the shop", timeout=20000)
    complete = [c for c in s.hook.calls if c["op"] == "complete"]
    assert p.locator("#try-again").count() == 0  # AC-52: Try again is for Create and Update
    assert len({c["idempotency_key"] for c in complete}) == 1  # never a new key
    assert len(complete) == 2  # the first, and one identical Complete
