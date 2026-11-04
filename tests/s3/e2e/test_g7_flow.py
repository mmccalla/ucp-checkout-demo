"""G7: the S3 checkout page end to end in headless Chrome with the Google Pay CI stub."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page, expect

from tests.s3.e2e.conftest import EVIDENCE, Stack
from tests.s3.e2e.helpers import audit, kb_activate, kb_type, tab_sequence, write

TOKEN = "examplePaymentMethodToken"
AC102_BANNER = (
    "Google Pay TEST — dummy token, cannot be charged. "
    "Simulated payment processor. No real money moves."
)
TAB_LOG: list[dict[str, Any]] = []
AUDIT_LOG: list[dict[str, Any]] = []


def stub_calls(page: Page) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = page.evaluate("window.__gpayStub.calls || []")
    return calls


def state_audit(page: Page, name: str) -> None:
    """AC-82, AC-84, AC-85 on a state screen: contrast, target size, names. Colour is not the only signal."""
    log: list[dict[str, Any]] = []
    audit(page, name, log)
    signals = page.evaluate(
        """() => [...document.querySelectorAll('.panel')].filter(p => p.offsetParent).map(p => ({
          icon: !!p.querySelector('.panel-title svg.icon'),
          title: (p.querySelector('.panel-title') || {}).textContent || ''}))"""
    )
    for sgl in signals:
        assert sgl["icon"] and sgl["title"].strip(), (name, sgl)
    log[0]["panel_signals"] = signals
    write("audit-state-" + name.replace(" ", "-") + ".json", log, EVIDENCE)


def open_page(s: Stack, query: str = "") -> None:
    s.page.goto(s.base + "/checkout/" + query)
    expect(s.page.locator("#screen-title")).to_have_text("UCP checkout with Google Pay - demo")


def next_step(page: Page) -> None:
    expect(page.locator("#next-step")).to_be_enabled()
    page.locator("#next-step").click()


def to_review(s: Stack, qty: int = 1, auto: bool = False) -> None:
    """Mouse path to SC4 (the keyboard path is in test_happy_path_keyboard)."""
    p = s.page
    if auto:
        p.locator('input[name="play"][value="auto"]').check()
    p.locator("#start").click()
    if not auto:
        next_step(p)
    expect(p.locator("#screen-title")).to_have_text("Shop and item")
    p.locator("#field-line-items-0").fill(str(qty))
    p.locator("#add").click()
    if not auto:
        next_step(p)
    expect(p.locator("#screen-title")).to_have_text("Your details")
    p.locator("#field-buyer-email").fill("buyer@example.com")
    p.locator("#field-buyer-first-name").fill("Ada")
    p.locator("#field-buyer-last-name").fill("Lovelace")
    p.locator("#continue").click()
    if not auto:
        next_step(p)
        next_step(p)
    expect(p.locator("#screen-title")).to_have_text("Review and pay")


def test_happy_path_keyboard(make_stack: Callable[..., Stack]) -> None:
    """AC-79 (to Complete), AC-80, AC-18, AC-19, AC-21, AC-36, AC-76, AC-77, AC-98 (part), AC-111."""
    s = make_stack()
    p = s.page
    open_page(s)
    tab_sequence(p, "SC1 Start", TAB_LOG)
    audit(p, "SC1 Start", AUDIT_LOG)
    kb_activate(p, "#start")
    kb_activate(p, "#next-step")
    expect(p.locator("#screen-title")).to_have_text("Shop and item")
    expect(p.locator("#screen-title")).to_be_focused()
    tab_sequence(p, "SC2 Shop and item", TAB_LOG)
    audit(p, "SC2 Shop and item", AUDIT_LOG)
    kb_activate(p, "#add")
    kb_activate(p, "#next-step")
    expect(p.locator("#screen-title")).to_have_text("Your details")
    tab_sequence(p, "SC3 Your details", TAB_LOG)
    audit(p, "SC3 Your details", AUDIT_LOG)
    kb_type(p, "#field-buyer-email", "buyer@example.com")
    kb_type(p, "#field-buyer-first-name", "Ada")
    kb_type(p, "#field-buyer-last-name", "Lovelace")
    kb_activate(p, "#continue")
    kb_activate(p, "#next-step")
    expect(p.locator("#pending")).to_contain_text("Get Checkout (review)")
    kb_activate(p, "#next-step")
    expect(p.locator("#screen-title")).to_have_text("Review and pay")
    expect(p.locator(".gpay-stub-button")).to_be_visible()
    tab_sequence(p, "SC4 Review and pay", TAB_LOG)
    audit(p, "SC4 Review and pay", AUDIT_LOG)
    # AC-18: line items, totals in Business order, currency, all links, from a fresh Get
    assert s.hook.ops()[-1] == "get"
    rows = p.locator("table").nth(1).locator("th").all_inner_texts()
    assert rows == ["Subtotal", "Shipping", "Total"]
    expect(p.locator("#currency")).to_have_text("GBP")
    expect(p.locator("#total-to-pay")).to_have_text("Total to pay: £23.00")
    assert p.locator("#links a").all_inner_texts() == ["Privacy policy", "Terms of service"]
    # AC-19: no loadPaymentData and no Complete before the click
    calls = stub_calls(p)
    assert [c["fn"] for c in calls] == ["PaymentsClient", "isReadyToPay", "createButton"]
    assert "complete" not in s.hook.ops()
    # AC-76: createButton with buttonType buy, not smaller than the other buttons, 8 px clear space
    assert calls[2]["options"]["buttonType"] == "buy"
    gb = p.locator(".gpay-stub-button").bounding_box()
    cb = p.locator("#cancel-checkout").bounding_box()
    assert gb and cb and gb["height"] >= cb["height"] and gb["width"] >= cb["width"]
    assert gb["width"] >= 240
    pad = p.evaluate("getComputedStyle(document.getElementById('gpay-area')).padding")
    assert pad == "8px"
    # Keyboard: Tab to the Google Pay button, press Enter
    kb_activate(p, ".gpay-stub-button")
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    assert "Placing your order" in p.evaluate("window.__ucpDemo.screens")  # SC5, no button
    calls = stub_calls(p)
    ld = [c for c in calls if c["fn"] == "loadPaymentData"]
    assert len(ld) == 1
    assert ld[0]["activationActive"] is True  # AC-77: called inside the click activation
    ti = ld[0]["request"]["transactionInfo"]
    assert ti == {
        "totalPriceStatus": "FINAL",
        "totalPrice": "23.00",
        "currencyCode": "GBP",
        "countryCode": "GB",
        "checkoutOption": "COMPLETE_IMMEDIATE_PURCHASE",
    }
    req = ld[0]["request"]
    assert "merchantOrigin" not in req["merchantInfo"] and "authJwt" not in req["merchantInfo"]
    assert req["allowedPaymentMethods"][0]["parameters"]["allowedAuthMethods"] == ["PAN_ONLY"]
    # AC-98 (part): Complete goes out after the sheet approval, with no other buyer click
    deadline = time.time() + 10
    while "complete" not in s.hook.ops() and time.time() < deadline:
        time.sleep(0.05)
    assert s.hook.ops().count("complete") == 1
    # S4 (AC-33, AC-79, AC-98): the mock PSP approves. The shop places the order.
    expect(p.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    expect(p.locator("#simulated-payment")).to_have_text("Simulated payment. No money moved.")
    expect(p.locator("#order-id")).not_to_be_empty()
    assert len(s.pair.psp.attempts) == 1 and s.pair.psp.attempts[0]["status"] == "approved"
    texts = p.locator("#msg-list button").all_inner_texts()
    assert any("M7" in t and "LOCAL STEP" in t and "NOT UCP" in t for t in texts), texts
    assert any("M9" in t and "SIMULATED" in t and "NOT UCP" in t for t in texts), texts
    assert any("Complete" in t and "LIVE CALL" in t and "NOT UCP" not in t for t in texts), texts
    # AC-111: the token is in no page element, console line, timeline row or export
    html = p.content()
    for m in p.locator("#msg-list button").all():
        m.click()
        html += p.locator("#msg-detail").inner_html()
        p.locator("#msg-detail summary").click()
        html += p.locator("#msg-detail pre").inner_text()
    assert TOKEN not in html
    assert TOKEN not in "\n".join(s.console)
    export = p.request.get(s.base + "/api/timeline/export").text()
    assert TOKEN not in export
    for f in (s.pair.tmp / "platform.jsonl", s.pair.tmp / "business.jsonl"):
        assert TOKEN not in (f.read_text() if f.exists() else "")
    # AC-115 (log order): the Platform log shows discovery, create, update and complete in this
    # order, and the run ends with an order ID. The log is the append-only platform.jsonl file.
    log = [
        json.loads(x) for x in (s.pair.tmp / "platform.jsonl").read_text().splitlines() if x.strip()
    ]
    steps = ["Discovery (live)", "create", "update", "complete"]
    first = [
        next(i for i, r in enumerate(log) if r.get("name") == w or r.get("op") == w) for w in steps
    ]
    assert first == sorted(set(first)) and len(first) == 4, (steps, first)
    assert log[first[3]]["view_state"] == "completed" and log[first[3]]["status"] == 200
    write("log-order.json", {"steps": steps, "first_row_index": first}, EVIDENCE)
    write("tab-sequence.json", TAB_LOG, EVIDENCE)
    write("audit-1280.json", AUDIT_LOG, EVIDENCE)
    write("happy-path-stub-calls.json", stub_calls(p), EVIDENCE)
    write("happy-path-ops.json", s.hook.calls, EVIDENCE)
    (EVIDENCE / "happy-path-timeline-export.json").write_text(export)
    p.screenshot(path=str(EVIDENCE / "happy-path-end.png"), full_page=True)
    json.loads(export)


# ---------------------------------------------------------------- Google Pay outcomes
def test_ac28_is_ready_to_pay_false(make_stack: Callable[..., Stack]) -> None:
    s = make_stack(gpay={"ready": False})
    open_page(s)
    to_review(s)
    expect(s.page.locator("#gpay-unavailable")).to_contain_text(
        "Google Pay is not available in this browser."
    )
    assert s.page.locator(".gpay-stub-button").count() == 0
    assert "createButton" not in [c["fn"] for c in stub_calls(s.page)]
    expect(s.page.locator("#msg-list")).to_contain_text("isReadyToPay")
    s.page.locator("#msg-list button", has_text="isReadyToPay").click()
    expect(s.page.locator("#msg-detail")).to_contain_text("false")
    s.page.screenshot(path=str(EVIDENCE / "ac28-not-ready.png"), full_page=True)


def test_ac29_buyer_closes_sheet(make_stack: Callable[..., Stack]) -> None:
    s = make_stack(gpay={"outcome": "cancel"})
    open_page(s)
    to_review(s)
    before = list(s.hook.calls)
    s.page.locator(".gpay-stub-button").click()
    expect(s.page.locator("#buyer-canceled")).to_have_text(
        "You closed Google Pay. You did not pay. Select the Google Pay button to try again."
    )
    time.sleep(0.5)
    assert s.hook.calls == before  # no UCP request
    expect(s.page.locator(".gpay-stub-button")).to_be_focused()
    cid = s.page.evaluate("window.__ucpDemo.checkout.id")
    assert s.pair.client.get(cid).body["status"] == "ready_for_complete"
    s.page.screenshot(path=str(EVIDENCE / "ac29-canceled.png"), full_page=True)
    state_audit(s.page, "ST08 sheet closed")


def test_ac30_cancel_checkout(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    open_page(s)
    to_review(s)
    s.page.locator("#cancel-checkout").click()
    expect(s.page.locator("#buyer-view")).to_contain_text("You did not pay")
    assert s.hook.ops()[-1] == "cancel"
    cid = s.page.evaluate("window.__ucpDemo.checkout.id")
    assert s.pair.client.get(cid).body["status"] == "canceled"
    assert "complete" not in s.hook.ops()


# ---------------------------------------------------------------- totals and gate
def test_ac20_totals_mismatch(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()

    def bad_total(req: Any, body: dict[str, Any]) -> dict[str, Any]:
        for e in body.get("totals", []):
            if e["type"] == "total":
                e["amount"] += 1
        # The demo Business sends no continue_url (open item T-68). The test adds one.
        body["continue_url"] = "https://localhost:9443/checkout/" + str(body.get("id"))
        return body

    open_page(s)
    s.hook.mutate["get"] = bad_total
    to_review(s)
    expect(s.page.locator("#totals-mismatch")).to_be_visible()
    expect(s.page.locator("#continue-url")).to_have_attribute(
        "href", "https://localhost:9443/checkout/" + s.page.evaluate("window.__ucpDemo.checkout.id")
    )
    assert s.page.locator(".gpay-stub-button").count() == 0
    assert not [c for c in stub_calls(s.page) if c["fn"] == "loadPaymentData"]
    s.page.screenshot(path=str(EVIDENCE / "ac20-mismatch.png"), full_page=True)
    state_audit(s.page, "totals mismatch")


def test_ac23_per_payment_limit(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    open_page(s)
    to_review(s, qty=3)  # 3 x 20.00 + 3.00 = 63.00 > 50.00
    expect(s.page.locator("#gate-panel")).to_contain_text("per-payment limit")
    expect(s.page.locator("#gate-panel")).to_contain_text(
        "This payment is more than the demo limit. You did not pay."
    )
    assert s.page.locator(".gpay-stub-button").count() == 0
    s.page.screenshot(path=str(EVIDENCE / "ac23-per-payment.png"), full_page=True)
    state_audit(s.page, "ST20 limit")


def test_ac24_daily_limit(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    from platform_app.pay.policy import Ledger

    Ledger().add("seed", 9000, "GBP")  # GBP 90.00 spent today
    open_page(s)
    to_review(s)  # GBP 23.00 (spec example: GBP 20.00; any amount above GBP 10.00 applies)
    expect(s.page.locator("#gate-panel")).to_contain_text("daily limit")
    assert s.page.locator(".gpay-stub-button").count() == 0


def test_ac25_allowlist(make_stack: Callable[..., Stack], monkeypatch: Any) -> None:
    s = make_stack()
    monkeypatch.setenv("PLATFORM_ALLOWLIST", "https://other.example/.well-known/ucp")
    open_page(s)
    to_review(s)
    expect(s.page.locator("#gate-panel")).to_contain_text("not on the allowlist")
    assert s.page.locator(".gpay-stub-button").count() == 0


def test_ac25_not_test_environment(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()

    def prod(req: Any, body: dict[str, Any]) -> dict[str, Any]:
        for h in body["ucp"]["payment_handlers"].get("com.google.pay", []):
            h["config"]["environment"] = "PRODUCTION"
        return body

    open_page(s)
    s.hook.mutate["get"] = prod
    to_review(s)
    expect(s.page.locator("#gate-panel")).to_contain_text(
        "Demo stopped. The shop is not in TEST mode."
    )
    assert s.page.locator(".gpay-stub-button").count() == 0


def test_ac25_currency(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()

    def usd(req: Any, body: dict[str, Any]) -> dict[str, Any]:
        body["currency"] = "USD"
        return body

    open_page(s)
    s.hook.mutate["get"] = usd
    to_review(s)
    expect(s.page.locator("#gate-panel")).to_contain_text("The demo pays in GBP only.")
    assert s.page.locator(".gpay-stub-button").count() == 0


def test_ac27_config_without_merchant_id(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()

    def no_mid(req: Any, body: dict[str, Any]) -> dict[str, Any]:
        for h in body["ucp"]["payment_handlers"].get("com.google.pay", []):
            del h["config"]["merchant_info"]["merchant_id"]
        return body

    open_page(s)
    s.hook.mutate["get"] = no_mid
    to_review(s)
    expect(s.page.locator("#gate-panel")).to_contain_text("The payment step stopped")
    expect(s.page.locator("#gate-panel")).to_contain_text("merchant_id")
    assert s.page.locator(".gpay-stub-button").count() == 0


# ---------------------------------------------------------------- approval and in-flight
def test_ac22_changed_after_approval(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    open_page(s)
    to_review(s)

    def more(req: Any, body: dict[str, Any]) -> dict[str, Any]:
        body["line_items"][0]["item"]["title"] = "Demo T-shirt (changed)"
        return body

    s.hook.mutate["get"] = more
    s.page.locator(".gpay-stub-button").click()
    expect(s.page.locator("#buyer-view")).to_contain_text(
        "The order changed after your approval. Review the new order."
    )
    expect(s.page.locator("#screen-title")).to_have_text("Review and pay")
    assert "complete" not in [c["op"] for c in s.hook.calls]
    expect(s.page.locator("#buyer-view")).to_contain_text("Demo T-shirt (changed)")


def test_ac51_no_second_complete(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    open_page(s)
    to_review(s)
    s.hook.delay["complete"] = 1.5
    h = s.page.evaluate("window.__ucpDemo.review.approval_hash")
    cid = s.page.evaluate("window.__ucpDemo.checkout.id")
    s.page.locator(".gpay-stub-button").click()
    deadline = time.time() + 5
    while "complete" not in [c["op"] for c in s.hook.calls] and time.time() < deadline:
        time.sleep(0.02)
    # A second click while Complete is in flight: SC5 has no button, and the API refuses.
    assert s.page.locator("#buyer-view button").count() == 0
    r = s.page.evaluate(
        "async ([cid, h]) => (await fetch('/api/checkout/' + cid + '/pay', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({approval_hash: h, payment_data: {}})})).status",
        [cid, h],
    )
    assert r == 409
    expect(s.page.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    r2 = s.page.evaluate(
        "async ([cid, h]) => (await fetch('/api/checkout/' + cid + '/pay', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({approval_hash: h, payment_data: {}})})).status",
        [cid, h],
    )
    assert r2 == 409  # one approval permits one Complete
    assert [c["op"] for c in s.hook.calls].count("complete") == 1


# ---------------------------------------------------------------- errors and messages
def test_ac52_try_again_same_key(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    open_page(s)
    s.hook.drop["update"] = 3  # the client tries 3 times (AC-49). All get no response.
    p = s.page
    p.locator("#start").click()
    next_step(p)
    p.locator("#add").click()
    next_step(p)
    p.locator("#field-buyer-email").fill("buyer@example.com")
    p.locator("#continue").click()
    next_step(p)
    expect(p.locator("#buyer-view")).to_contain_text(
        "We cannot reach the shop. Your details are safe on this page. Try again."
    )
    dropped = [c for c in s.hook.calls if c["op"] == "update"]
    assert len(dropped) == 3 and not any(c["reached"] for c in dropped)
    p.locator("#try-again").click()
    next_step(p)
    expect(p.locator("#screen-title")).not_to_have_text("We cannot reach the shop")
    ups = [c for c in s.hook.calls if c["op"] == "update"]
    assert len(ups) == 4 and ups[-1]["reached"]
    assert len({c["idempotency_key"] for c in ups}) == 1
    assert len({c["request_id"] for c in ups}) == 1
    write("ac52-update-calls.json", ups, EVIDENCE)


def test_ac53_protocol_error_5xx(make_stack: Callable[..., Stack]) -> None:
    s = make_stack(faults={"unavailable": 3})
    open_page(s)
    p = s.page
    p.locator("#start").click()
    next_step(p)
    p.locator("#add").click()
    next_step(p)
    expect(p.locator("#buyer-view")).to_contain_text(
        "The shop did not accept the request (HTTP 503). This is a problem in the demo setup, not a payment problem."
    )
    expect(p.locator("#problem-code")).to_have_text("fault_injected")
    expect(p.locator("#try-again")).to_be_visible()
    p.screenshot(path=str(EVIDENCE / "ac53-503.png"), full_page=True)
    state_audit(p, "ST15 protocol error")


def test_ac53_protocol_error_4xx(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    s.hook.strip_signature = True  # the Business requires a signature: HTTP 401
    open_page(s)
    p = s.page
    p.locator("#start").click()
    next_step(p)
    p.locator("#add").click()
    next_step(p)
    expect(p.locator("#buyer-view")).to_contain_text(
        "(HTTP 401). This is a problem in the demo setup, not a payment problem."
    )
    code = p.locator("#problem-code").inner_text()
    assert code
    assert p.locator("#try-again").count() == 0
    write("ac53-401-code.json", {"code": code}, EVIDENCE)


def test_ac14_out_of_stock_no_checkout(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    open_page(s)
    p = s.page
    p.locator("#start").click()
    next_step(p)
    p.locator("#item-choice").select_option("demo_mug")
    p.locator("#add").click()
    next_step(p)
    # The Create makes no checkout: HTTP 200 error_response without a path (patch P8).
    # Without a path the text is at the top of the buyer view.
    msg = p.locator("#top-messages .field-msg")
    expect(msg).to_contain_text("out of stock")
    assert p.locator("[aria-describedby]").count() == 0
    assert [c["op"] for c in s.hook.calls].count("create") == 1
    # No checkout: only the control to change the data
    assert p.locator("#add").inner_text() == "Change item"
    assert p.locator("#cancel-checkout").count() == 0
    p.screenshot(path=str(EVIDENCE / "ac14-out-of-stock.png"), full_page=True)


def test_ac14_address_undeliverable(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    open_page(s)
    p = s.page
    p.locator("#start").click()
    next_step(p)
    p.locator("#add").click()
    next_step(p)
    p.locator("#addr-country").select_option("FR")
    p.locator("#continue").click()
    next_step(p)
    expect(p.locator(".field-msg")).to_be_visible()
    mid = p.locator(".field-msg").first.get_attribute("id")
    assert p.locator(f'[aria-describedby~="{mid}"]').count() == 1
    assert p.locator("#continue").inner_text() == "Change address"
    expect(p.locator("#cancel-checkout")).to_be_visible()
    p.screenshot(path=str(EVIDENCE / "ac14-undeliverable.png"), full_page=True)
    state_audit(p, "address undeliverable")


def test_ac15_requires_buyer_input(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()

    def ask(req: Any, body: dict[str, Any]) -> dict[str, Any]:
        body["status"] = "incomplete"
        body["messages"] = [
            {
                "type": "error",
                "code": "missing",
                "path": "$.buyer.email",
                "content": "Enter your email address.",
                "severity": "requires_buyer_input",
            }
        ]
        return body

    open_page(s)
    s.hook.mutate["update"] = ask
    p = s.page
    p.locator("#start").click()
    next_step(p)
    p.locator("#add").click()
    next_step(p)
    p.locator("#continue").click()
    next_step(p)
    expect(p.locator("#buyer-view")).to_contain_text("The agent does not make up a value.")
    expect(p.locator("#field-buyer-email")).to_have_attribute("aria-describedby", "ucp-msg-0")
    expect(p.locator("#field-buyer-email")).to_have_value("")
    sent = [c for c in s.hook.calls if c["op"] == "update"]
    assert len(sent) == 1


def test_ac16_requires_escalation(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()

    def esc(req: Any, body: dict[str, Any]) -> dict[str, Any]:
        body["status"] = "requires_escalation"
        body["continue_url"] = "https://localhost:9443/checkout/" + str(body["id"])
        body["messages"] = [
            {
                "type": "error",
                "code": "requires_3ds",
                "content": "Finish on the shop website.",
                "severity": "requires_buyer_review",
            }
        ]
        return body

    open_page(s)
    s.hook.mutate["update"] = esc
    p = s.page
    p.locator("#start").click()
    next_step(p)
    p.locator("#add").click()
    next_step(p)
    p.locator("#field-buyer-email").fill("buyer@example.com")
    p.locator("#continue").click()
    next_step(p)
    expect(p.locator("#continue-url")).to_have_text("Continue on the shop website")
    href = p.locator("#continue-url").get_attribute("href", timeout=1000) or ""
    assert href.startswith("https://localhost:9443/checkout/")
    assert "complete" not in s.hook.ops()
    assert p.locator(".gpay-stub-button").count() == 0


def test_ac17_unrecoverable(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()

    def unrec(req: Any, body: dict[str, Any]) -> dict[str, Any]:
        body["messages"] = [
            {
                "type": "error",
                "code": "item_discontinued",
                "content": "This item is discontinued.",
                "severity": "unrecoverable",
            }
        ]
        return body

    open_page(s)
    s.hook.mutate["update"] = unrec
    p = s.page
    p.locator("#start").click()
    next_step(p)
    p.locator("#add").click()
    next_step(p)
    p.locator("#continue").click()
    next_step(p)
    expect(p.locator("#screen-title")).to_have_text("This item is not available")
    expect(p.locator("#back-items")).to_have_text("Back to items")
    p.locator("#back-items").click()
    expect(p.locator("#screen-title")).to_have_text("Shop and item")


def test_ac09_search_notice(make_stack: Callable[..., Stack]) -> None:
    s = make_stack(catalog=True)
    open_page(s, "?case=lookup-only")
    s.page.locator("#start").click()
    next_step(s.page)
    expect(s.page.locator("#search-notice")).to_have_text("Search is not available with this agent")


# ---------------------------------------------------------------- inspector and run modes
def test_ac59_to_63_inspector_and_timeline(make_stack: Callable[..., Stack]) -> None:
    s = make_stack(gpay={"outcome": "cancel"})
    open_page(s)
    to_review(s)
    p = s.page
    p.locator(".gpay-stub-button").click()
    expect(p.locator("#buyer-canceled")).to_be_visible()
    items = p.locator("#msg-list button")
    texts = items.all_inner_texts()
    # AC-63: one source label each. AC-60: NOT UCP on Google Pay and mapping rows.
    labels = ("LIVE CALL", "RECORDED", "GOOGLE PAY TEST", "SIMULATED", "LOCAL STEP")
    assert any("Mapping" in t for t in texts)
    for t in texts:
        assert sum(t.count(lab) for lab in labels) == 1, t
        is_gpay = any(k in t for k in ("isReadyToPay", "loadPaymentData", "Mapping", "M9"))
        assert ("NOT UCP" in t) == is_gpay, t
        # AC-63 (spec v1.1.4): mapping rows are LOCAL STEP, never LIVE CALL.
        assert ("LOCAL STEP" in t) == ("Mapping" in t), t
        if "isReadyToPay" in t or "loadPaymentData" in t:
            assert "SIMULATED" in t
    # AC-61: 3 to 6 key fields with explanations, raw JSON collapsed
    for i in range(items.count()):
        items.nth(i).click()
        n = p.locator("#msg-detail dl.keys dt").count()
        assert 3 <= n <= 6, (texts[i], n)
        assert p.locator("#msg-detail dl.keys .explain").count() == n
        assert p.locator("#msg-detail details").get_attribute("open") is None
    # AC-81: the status region announces, the focus does not move
    focused = p.evaluate("document.activeElement.id || document.activeElement.className")
    announce = p.locator("#announcer").inner_text()
    assert announce.startswith("Message ") or "Google Pay" in announce
    assert focused
    # AC-59: one row for each request, state change, buyer action and error. Export as JSON.
    export = json.loads(p.request.get(s.base + "/api/timeline/export").text())
    kinds = {r.get("kind") for r in export["rows"] if r.get("side") == "platform"}
    assert {"request", "state", "buyer_action", "gpay"} <= kinds, kinds
    reqs = [
        r
        for r in export["rows"]
        if r.get("side") == "platform" and r.get("kind") == "request" and r.get("op")
    ]
    assert len(reqs) == len([c for c in s.hook.calls if c["reached"]])
    write("ac59-timeline-export.json", export, EVIDENCE)


def test_ac59_error_row(make_stack: Callable[..., Stack]) -> None:
    s = make_stack(faults={"unavailable": 3})
    open_page(s)
    s.page.locator("#start").click()
    next_step(s.page)
    s.page.locator("#add").click()
    next_step(s.page)
    expect(s.page.locator("#problem-code")).to_be_visible()
    rows = json.loads(s.page.request.get(s.base + "/api/timeline/export").text())["rows"]
    assert any(r.get("kind") == "error" for r in rows)


def test_ac62_step_auto_pause_replay(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    open_page(s, "?auto_ms=400")
    p = s.page
    p.locator('input[name="play"][value="auto"]').check()
    p.locator("#start").click()
    expect(p.locator("#screen-title")).to_have_text("Shop and item", timeout=5000)  # Auto continues
    p.locator("#add").click()
    expect(p.locator("#pause")).to_be_enabled()
    p.locator("#pause").click()  # Pause stops the run
    expect(p.locator("#pause")).to_have_attribute("aria-pressed", "true")
    n = len(s.hook.calls)
    time.sleep(1.2)
    assert len(s.hook.calls) == n
    expect(p.locator("#screen-title")).to_have_text("Shop and item")
    p.locator("#pause").click()  # continue
    expect(p.locator("#screen-title")).to_have_text("Your details", timeout=5000)
    # Replay: recorded messages, RECORDED labels, no calls
    count = p.locator("#msg-list li").count()
    before = len(s.requests)
    calls_before = len(s.hook.calls)
    p.locator("#replay").click()
    # UX-AC-20 (spec 15.8 rows 9 and 10): banner.test.label, then banner.replay. No source label.
    expect(p.locator("#banner-label")).to_have_text("TEST MODE.")
    expect(p.locator("#banner-detail")).to_have_text(
        "REPLAY. These are recorded messages. No calls go out."
    )
    banner = p.locator("#mode-banner").inner_text()
    for label in ("LIVE CALL", "RECORDED", "GOOGLE PAY TEST", "SIMULATED", "LOCAL STEP"):
        assert label not in banner, (label, banner)  # source labels show on inspector rows only
    assert "REPLAY. Recorded messages. No calls go out." not in p.content()  # old text is gone
    expect(p.locator("#replay-done")).to_be_visible(timeout=10000)
    assert p.locator("#msg-list li").count() == count
    for t in p.locator("#msg-list button").all_inner_texts():
        assert "RECORDED" in t
    # UX-4.5: the detail tells the original source.
    p.locator("#msg-list button").first.click()
    expect(p.locator("#msg-detail .recorded-text")).to_have_text(
        "Recorded. Original source: LIVE CALL."
    )
    assert len(s.requests) == before
    assert len(s.hook.calls) == calls_before
    state_audit(p, "replay")


def test_ac78_banner(make_stack: Callable[..., Stack]) -> None:
    s = make_stack()
    open_page(s)
    expect(s.page.locator("#banner-label")).to_have_text("TEST MODE.")
    expect(s.page.locator("#banner-detail")).to_have_text(AC102_BANNER)
    assert s.page.locator("#mode-banner svg.icon").count() == 1
    banner = s.page.locator("#mode-banner").inner_text()
    for label in ("LIVE CALL", "RECORDED", "GOOGLE PAY TEST", "SIMULATED", "LOCAL STEP"):
        assert label not in banner, (label, banner)  # UX-AC-20: no source label in the banner


def test_ac102_banner_after_stub_approval(make_stack: Callable[..., Stack]) -> None:
    """AC-102 (spec 15.7 row 4). The banner keeps the TEST text after the sheet approval.

    Source: Google Pay handler spec https://pay.google.com/gp/p/ucp/2026-01-23/ section 5.2
    "TEST Mode: In the TEST environment, Google Pay returns dummy tokens. These cannot be charged."
    The mock PSP records no real charge: each record is simulated and has a TEST id.
    """
    s = make_stack()
    open_page(s)
    to_review(s)
    s.page.locator(".gpay-stub-button").click()
    expect(s.page.locator("#screen-title")).to_have_text("Order confirmed", timeout=10000)
    expect(s.page.locator("#banner-label")).to_have_text("TEST MODE.")
    expect(s.page.locator("#banner-detail")).to_have_text(AC102_BANNER)
    assert "TEST — dummy token, cannot be charged" in s.page.locator("#mode-banner").inner_text()
    att = s.pair.psp.attempts
    assert len(att) == 1 and att[0]["status"] == "approved"
    assert att[0]["simulated"] is True and str(att[0]["id"]).startswith("TEST-auth-")
    assert "Simulated payment. No money moved." in s.page.locator("#simulated-payment").inner_text()
    # No call to a host other than the Platform on 127.0.0.1 (DM-26): no real PSP, no Google call.
    assert all(r.split(" ", 1)[1].startswith(s.base) for r in s.requests), s.requests


def test_ac83_320px_and_inspector_toggle(make_stack: Callable[..., Stack]) -> None:
    s = make_stack(viewport=(320, 800))
    log: list[dict[str, Any]] = []
    open_page(s)
    p = s.page
    expect(p.locator("#toggle-inspector")).to_be_visible()
    expect(p.locator("#inspector-body")).to_be_hidden()
    audit(p, "SC1 Start", log, 320)
    p.locator("#toggle-inspector").click()
    expect(p.locator("#toggle-inspector")).to_have_attribute("aria-expanded", "true")
    expect(p.locator("#inspector-body")).to_be_visible()
    to_review(s)
    audit(p, "SC4 Review and pay", log, 320)
    p.locator("#msg-list button").last.click()
    p.locator("#msg-detail summary").click()
    audit(p, "SC4 with raw JSON open", log, 320)
    write("audit-320.json", log, EVIDENCE)
    p.screenshot(path=str(EVIDENCE / "sc4-320px.png"), full_page=True)
