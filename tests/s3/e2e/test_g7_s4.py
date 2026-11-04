"""G7 for S4: ST13 decline and retry (T-105, AC-34, AC-35), source labels (AC-63) and UX-U-18.

UX-U-18 is an automated contrast test on the built UI. It uses the WCAG 2.2 formulas:
relative luminance https://www.w3.org/TR/WCAG22/#dfn-relative-luminance and contrast ratio
https://www.w3.org/TR/WCAG22/#dfn-contrast-ratio. Thresholds: SC 1.4.3 text 4.5:1
(https://www.w3.org/TR/WCAG22/#contrast-minimum) and SC 1.4.11 non-text 3:1
(https://www.w3.org/TR/WCAG22/#non-text-contrast).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from platform_app import audit
from playwright.sync_api import Page, expect

from tests.evidence import evidence_dir
from tests.s3.e2e.conftest import Stack
from tests.s3.e2e.test_g7_flow import TOKEN, open_page, to_review

EVIDENCE = evidence_dir("S4", "g7")
S = {
    "declined.heading": "Payment declined",
    "declined.body": "The shop's payment processor declined your payment. You did not pay. The shop did not place your order. Your items and details did not change.",  # noqa: E501
    "declined.retry.hint": "To try again, select the Google Pay button. You can select a different card in Google Pay.",  # noqa: E501
    "declined.announce": "Payment declined. You did not pay. You can try again with Google Pay.",
    "declined.simulated": "Simulated: the demo payment processor declined this payment. Google Pay did not decline it.",  # noqa: E501
    "declined.again.heading": "Payment declined again",
    "declined.again.body": "The shop's payment processor declined your payment again. You did not pay. Select a different card in Google Pay, or cancel the checkout.",  # noqa: E501
    "declined.again.announce": "Payment declined again. You did not pay.",
}
LOCAL_NAME = "Local step: the Platform did this step. No network call."


def _write(name: str, data: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(data, indent=2, default=str))


def _complete_keys(s: Stack) -> list[str | None]:
    return [c["idempotency_key"] for c in s.hook.calls if c["op"] == "complete" and c["reached"]]


def test_ac34_ac35_st13_decline_again_then_retry_completes(
    make_stack: Callable[..., Stack],
) -> None:
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    s.pair.psp.outcome = "decline"
    # First decline: declined.* texts, focus on the panel heading, role="status" announcement.
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#declined-heading")).to_have_text(S["declined.heading"], timeout=10000)
    expect(p.locator("#declined-heading")).to_be_focused()
    expect(p.locator("#declined-body")).to_have_text(S["declined.body"])
    expect(p.locator("#declined-simulated")).to_have_text(S["declined.simulated"])
    expect(p.locator("#declined-retry-hint")).to_have_text(S["declined.retry.hint"])
    expect(p.locator("#announcer")).to_have_text(S["declined.announce"])
    assert p.locator("#announcer").get_attribute("role") == "status"
    assert p.locator("#declined-panel").get_attribute("role") is None  # not an error alert
    expect(p.locator("#cancel-checkout")).to_have_text("Cancel checkout")
    # The items and totals did not change.
    expect(p.locator("#total-to-pay")).to_have_text("Total to pay: £23.00")
    # ST13 inspector: M10 LIVE CALL with inspector.m10.declined, M9 SIMULATED, M7 LOCAL STEP.
    texts = p.locator("#msg-list button").all_inner_texts()
    m9 = [t for t in texts if "M9" in t]
    assert len(m9) == 1 and "SIMULATED" in m9[0] and "NOT UCP" in m9[0]
    rows = p.locator("#msg-list button")
    last = rows.nth(rows.count() - 1)
    assert "Complete" in last.inner_text() and "LIVE CALL" in last.inner_text()
    last.click()
    expect(p.locator("#msg-detail")).to_contain_text("HTTP 200: this is a business result")
    assert TOKEN not in p.locator("#msg-detail").inner_html()
    p.screenshot(path=str(EVIDENCE / "st13-declined.png"), full_page=True)
    contrast_1 = _contrast(p)
    # Second decline: declined.again.*
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#declined-heading")).to_have_text(S["declined.again.heading"], timeout=10000)
    expect(p.locator("#declined-heading")).to_be_focused()
    expect(p.locator("#declined-body")).to_have_text(S["declined.again.body"])
    expect(p.locator("#announcer")).to_have_text(S["declined.again.announce"])
    rows = p.locator("#msg-list button")
    rows.nth(rows.count() - 1).click()
    expect(p.locator("#msg-detail")).to_contain_text("so the Platform uses a new Idempotency-Key")
    p.screenshot(path=str(EVIDENCE / "st13-declined-again.png"), full_page=True)
    # Retry approved: new click, new token, new key (AC-35). One approval, one order.
    s.pair.psp.outcome = "approve"
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    expect(p.locator("#order-id")).not_to_be_empty()
    keys = _complete_keys(s)
    assert len(keys) == 3 and len(set(keys)) == 3 and None not in keys
    att = s.pair.psp.attempts
    assert [a["status"] for a in att] == ["declined", "declined", "approved"]
    # The PSP records keep no token. The page, console and logs show no token.
    assert TOKEN not in json.dumps(att)
    html = p.content()
    assert TOKEN not in html and TOKEN not in "\n".join(s.console)
    for f in (s.pair.tmp / "platform.jsonl", s.pair.tmp / "business.jsonl"):
        assert TOKEN not in (f.read_text() if f.exists() else "")
    # AC-55: one audit record for each payment attempt. All fields, no forbidden field.
    recs = audit.read_all(s.pair.tmp / "audit.sqlite")
    assert len(recs) == 3, recs
    for r, k in zip(recs, keys, strict=True):
        audit.check(r)
        assert r["idempotency_key_hash"] == hashlib.sha256(str(k).encode()).hexdigest()
        assert r["currency"] == "GBP" and r["total_minor"] == 2300 and r["environment"] == "TEST"
        assert r["card_last_digits"] and r["card_brand"] == "VISA" and r["policy_result"] == "pass"
        assert r["line_items_summary"] and r["approval_hash"] and r["approval_id"]
    assert [r["final_status"] for r in recs] == ["ready_for_complete"] * 2 + ["completed"]
    assert [m["code"] for m in recs[0]["messages"]] == ["payment_failed"]
    assert recs[0]["order_id"] is None and recs[2]["order_id"]
    assert len({r["attempt_id"] for r in recs}) == 3
    raw = (s.pair.tmp / "audit.sqlite").read_bytes()
    assert TOKEN.encode() not in raw and b"continue_url" not in raw
    _write("ac55-audit-records.json", recs)
    _write("st13-ops.json", s.hook.calls)
    _write("st13-psp-attempts.json", att)
    _write("ux-u-18-contrast-decline.json", contrast_1)


def test_ac63_labels_icons_local_step_name_and_replay(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    labels = ("LIVE CALL", "RECORDED", "GOOGLE PAY TEST", "SIMULATED", "LOCAL STEP")
    rows = p.locator("#msg-list button")
    texts = rows.all_inner_texts()
    for t in texts:
        assert sum(t.count(lab) for lab in labels) == 1, t
    # LOCAL STEP only on the two Google Pay mapping rows (PaymentDataRequest and M7).
    local = [t for t in texts if "LOCAL STEP" in t]
    assert len(local) == 2 and all("Mapping" in t and "NOT UCP" in t for t in local), local
    # Each badge has one aria-hidden Material Symbols icon. LOCAL STEP has the accessible name.
    info = p.evaluate(
        """() => [...document.querySelectorAll('#msg-list .badge[data-source]')].map(b => ({
          source: b.dataset.source, icons: b.querySelectorAll('svg').length,
          hidden: [...b.querySelectorAll('svg')].every(x => x.getAttribute('aria-hidden') === 'true'),
          vb: (b.querySelector('svg') || {getAttribute: () => ''}).getAttribute('viewBox'),
          sr: (b.querySelector('.visually-hidden') || {}).textContent || ''}))"""
    )
    for b in info:
        assert b["icons"] == 1 and b["hidden"] and b["vb"] == "0 -960 960 960", b
        if b["source"] == "LOCAL STEP":
            assert b["sr"] == LOCAL_NAME, b
    i = next(n for n, t in enumerate(texts) if "LOCAL STEP" in t)
    rows.nth(i).click()
    expect(p.locator("#msg-detail .local-text")).to_have_text(LOCAL_NAME)
    # Replay: each label RECORDED. NOT UCP stays.
    not_ucp = [("NOT UCP" in t) for t in texts]
    stub_before = len(p.evaluate("window.__gpayStub.calls"))
    requests_before = len(s.requests)
    p.locator("#replay").click()
    # UX-AC-20: banner.test.label, then banner.replay. No source label in the banner.
    expect(p.locator("#banner-label")).to_have_text("TEST MODE.")
    expect(p.locator("#banner-detail")).to_have_text(
        "REPLAY. These are recorded messages. No calls go out."
    )
    for lab in labels:
        assert lab not in p.locator("#mode-banner").inner_text()
    sheet_rows = 0
    for k in range(len(texts)):  # step mode: one Next step for each recorded message
        if "loadPaymentData" in texts[k]:
            # UX-4.4: the Google Pay button shows the recorded sheet result. It opens no sheet.
            sheet_rows += 1
            expect(p.locator("#replay-gpay")).to_be_visible()
            p.locator("#replay-gpay").click()
            expect(p.locator("#replay-sheet-result")).to_have_text(
                "Recorded Google Pay sheet result: approved. The Google Pay sheet did not open."
            )
        else:
            expect(p.locator("#next-step")).to_be_enabled()
            p.locator("#next-step").click()
    assert sheet_rows == 1
    expect(p.locator("#replay-done")).to_be_visible(timeout=5000)
    # No loadPaymentData call, no isReadyToPay call and no network request in the replay.
    assert len(p.evaluate("window.__gpayStub.calls")) == stub_before
    assert len(s.requests) == requests_before
    replayed = p.locator("#msg-list button").all_inner_texts()
    assert len(replayed) == len(texts)
    for t, nu in zip(replayed, not_ucp, strict=True):
        assert sum(t.count(lab) for lab in labels) == 1 and "RECORDED" in t, t
        assert ("NOT UCP" in t) == nu, t
    p.locator("#msg-list button").nth(i).click()
    expect(p.locator("#msg-detail .recorded-text")).to_have_text(
        "Recorded. Original source: LOCAL STEP."
    )
    _write("ac63-labels.json", {"live": texts, "replay": replayed, "badges": info})


# ---------------------------------------------------------------- UX-U-18
_JS = """() => {
  const rgb = (s) => { const m = s.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const v = m[1].split(',').map(x => parseFloat(x)); return {r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1}; };
  const bgOf = (el) => { for (let e = el; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor);
    if (c && c.a > 0) return c; } return {r: 255, g: 255, b: 255, a: 1}; };
  const parentBg = (el) => bgOf(el.parentElement);
  const out = [];
  const add = (kind, name, el, fg, bg, min) => out.push({kind, name, fg, bg, min});
  document.querySelectorAll('#msg-list .badge, #ux-u-18-fixture .badge').forEach((b) => {
    const cs = getComputedStyle(b); const name = (b.dataset.source || b.textContent).trim();
    add('text', name, b, rgb(cs.color), bgOf(b), 4.5);
    add('border', name, b, rgb(cs.borderTopColor), parentBg(b), 3);
    const svg = b.querySelector('svg'); if (svg) add('icon', name, svg, rgb(getComputedStyle(svg).color), bgOf(b), 3);
  });
  const panel = document.getElementById('declined-panel');
  if (panel) {
    add('border', 'decline panel', panel, rgb(getComputedStyle(panel).borderLeftColor), parentBg(panel), 3);
    panel.querySelectorAll('h2, p').forEach((e) => add('text', 'decline ' + (e.id || e.tagName), e, rgb(getComputedStyle(e).color), bgOf(e), 4.5));
    const hint = document.getElementById('declined-retry-hint');
    if (hint) add('text', 'decline retry hint', hint, rgb(getComputedStyle(hint).color), bgOf(hint), 4.5);
  }
  return out;
}"""


def _lum(c: dict[str, float]) -> float:
    def ch(v: float) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(c["r"]) + 0.7152 * ch(c["g"]) + 0.0722 * ch(c["b"])


def ratio(a: dict[str, float], b: dict[str, float]) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _contrast(p: Page) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = p.evaluate(_JS)
    for r in rows:
        r["ratio"] = round(ratio(r["fg"], r["bg"]), 2)
        assert r["fg"]["a"] == 1, r  # no translucent colours: the ratio is exact
        assert r["ratio"] >= r["min"], r
    return rows


def test_ux_u_18_ratio_formula() -> None:
    """Known values: black on white is 21:1. #767676 on white is about 4.54:1."""
    w: dict[str, float] = {"r": 255, "g": 255, "b": 255}
    k: dict[str, float] = {"r": 0, "g": 0, "b": 0}
    assert round(ratio(k, w), 2) == 21.0
    grey: dict[str, float] = {"r": 118, "g": 118, "b": 118}
    assert round(ratio(grey, w), 2) == 4.54


def test_ux_u_18_contrast_all_badges(make_stack: Callable[..., Stack]) -> None:
    """Each of the 5 source labels and NOT UCP, built with the page's own badge() and CSS.

    GOOGLE PAY TEST shows only with the real pay.js (not in CI). So the test also renders
    one badge of each label in a fixture list, with the same CSS classes as the inspector.
    """
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    p.evaluate(
        """() => { const d = document.createElement('div'); d.id = 'ux-u-18-fixture';
          const first = document.querySelector('#msg-list .badge');
          for (const [src, cls] of [['LIVE CALL','live'],['RECORDED','recorded'],['GOOGLE PAY TEST','gpaytest'],
              ['SIMULATED','simulated'],['LOCAL STEP','local']]) {
            const b = first.cloneNode(true); b.className = 'badge ' + cls; b.dataset.source = src;
            b.lastChild.textContent = src; d.appendChild(b); }
          const n = document.createElement('span'); n.className = 'badge notucp'; n.textContent = 'NOT UCP';
          d.appendChild(n); document.getElementById('msg-list').parentElement.appendChild(d); }"""
    )
    rows = _contrast(p)
    names = {r["name"] for r in rows}
    assert {
        "LIVE CALL",
        "RECORDED",
        "GOOGLE PAY TEST",
        "SIMULATED",
        "LOCAL STEP",
        "NOT UCP",
    } <= names
    _write("ux-u-18-contrast-badges.json", rows)


def test_ac64_ac73_ac74_order_events_reconcile_and_signature(
    make_stack: Callable[..., Stack],
) -> None:
    """AC-74: the UI shows the three simulated order events. AC-73: Reconcile. AC-64: M10."""
    s = make_stack()
    p = s.page
    open_page(s)
    to_review(s)
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    steps = p.locator("#order-steps li")
    expect(steps).to_have_count(3, timeout=10000)
    assert [t.strip() for t in steps.all_inner_texts()] == [
        "Order confirmed Simulated",
        "Shipped Simulated",
        "Delivered Simulated",
    ]
    expect(p.locator("#order-tracking")).to_contain_text("Tracking number (fake): SIM-")
    p.locator("#reconcile").click()
    expect(p.locator("#reconcile-result")).to_have_text(
        "Reconcile: Get Order gives the same state as the webhooks (delivered).", timeout=10000
    )
    texts = p.locator("#msg-list button").all_inner_texts()
    m11 = [t for t in texts if "M11" in t]
    assert len(m11) == 3 and all("SIMULATED" in t for t in m11)
    assert any("Get Order" in t and "LIVE CALL" in t for t in texts)
    rows = p.locator("#msg-list button")
    idx = next(i for i, t in enumerate(texts) if "Complete Checkout" in t)
    rows.nth(idx).click()
    expect(p.locator("#msg-detail")).to_contain_text("Response signature: verified keyid=")
    p.screenshot(path=str(EVIDENCE / "ac74-order-events.png"), full_page=True)
    _write(
        "ac74-webhooks.json",
        [dict(w.headers) | {"body_len": len(w.content)} for w in s.pair.webhooks],
    )
