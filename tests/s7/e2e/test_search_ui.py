"""G7 (S7): SC2a (find a product) and SC2 (product detail) in headless Chrome.

Spec v1.1.18, section 7.12 (AC-123 to AC-138), AC-12.3, AC-12.8 to AC-12.10, AC-12.15.
Design: 02-design.md UX-4.2a, UX-7.6, UX-8.2. T-120: Playwright 1.56.0, sync API.
Each test shows the AC id in its name. The catalog calls go to the in-process Business.
The page sends no request to a host outside 127.0.0.1 (the test blocks the image hosts).
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from typing import Any

import httpx
from playwright.sync_api import Page, expect

from tests.evidence import evidence_dir
from tests.s2.conftest import PROFILE_URL
from tests.s3.e2e.conftest import Stack
from tests.s3.e2e.helpers import audit, write
from tests.s3.e2e.test_g7_flow import next_step as _next_step
from tests.s3.e2e.test_g7_flow import open_page

EVIDENCE = evidence_dir("S7", "g7")
AUDIT_LOG: list[dict[str, Any]] = []
CATALOG = ("search", "lookup", "product")
Make = Callable[..., Stack]


# ---------------------------------------------------------------- helpers
def next_step(page: Page) -> None:
    """Click Next step. Below 1024 px the inspector is closed, so open it first."""
    toggle = page.locator("#toggle-inspector")
    if toggle.is_visible() and toggle.get_attribute("aria-expanded") == "false":
        toggle.click()
    _next_step(page)


def to_search(s: Stack, query: str = "") -> None:
    """Start the demo in step mode. SC2a opens after Discovery."""
    s.page.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda r: r.abort())
    open_page(s, query)
    s.page.locator("#start").click()
    next_step(s.page)
    expect(s.page.locator("#screen-title")).to_have_text("Find a product")


def run_search(s: Stack, text: str) -> None:
    s.page.locator("#search-q").fill(text)
    s.page.locator("#search-go").click()
    next_step(s.page)


def search_ok(s: Stack, text: str = "demo") -> None:
    run_search(s, text)
    expect(s.page.locator("#search-status")).to_contain_text("Products shown")


def ops(s: Stack, which: tuple[str, ...] = CATALOG) -> list[str]:
    return [c["op"] for c in s.hook.calls if c["op"] in which]


def bodies(s: Stack, op: str) -> list[Any]:
    return [c["body"] for c in s.hook.calls if c["op"] == op]


def biz_product(s: Stack, product_id: str) -> dict[str, Any]:
    h = {"UCP-Agent": f'profile="{PROFILE_URL}"', "Request-Id": "rid-test"}
    r: httpx.Response = s.pair.biz.post("/catalog/product", json={"id": product_id}, headers=h)
    body: dict[str, Any] = r.json()
    return body


def more_pages() -> Callable[[httpx.Request, dict[str, Any]], Any]:
    """A mutator: page 1 has 3 products and a cursor. The request with that cursor gets page 2."""

    def product(base: dict[str, Any], n: int) -> dict[str, Any]:
        p = copy.deepcopy(base)
        p["id"], p["title"] = f"prod_extra_{n}", f"Extra product {n}"
        p["variants"][0]["id"] = f"extra_{n}"
        return p

    seen: dict[str, Any] = {}

    def mutate(req: httpx.Request, body: dict[str, Any]) -> Any:
        sent = json.loads(req.content)
        if "products" in body:  # the Business does not know the cursor "c1"
            seen["body"] = body
        base = seen["body"]["products"][0]
        if (sent.get("pagination") or {}).get("cursor") == "c1":
            return 200, {
                **seen["body"],
                "products": [product(base, 4), product(base, 5)],
                "pagination": {"has_next_page": False, "total_count": 5},
            }
        return {
            **body,
            "products": [*body["products"], product(base, 3)],
            "pagination": {"has_next_page": True, "cursor": "c1", "total_count": 5},
        }

    return mutate


def alert_text(page: Page, ident: str = "#search-alert") -> Any:
    return page.locator(ident)


def active(page: Page) -> str:
    out: str = page.evaluate(
        "() => { const e = document.activeElement; return e.id ? '#' + e.id : e.tagName + ':' + e.textContent.trim(); }"
    )
    return out


# ---------------------------------------------------------------- AC-123, AC-124, AC-125
def test_ac123_form_has_role_label_and_hint(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    p = s.page
    form = p.get_by_role("search", name="Find a product")
    expect(form).to_have_count(1)
    expect(p.get_by_label("Search the shop")).to_have_count(1)
    q = p.locator("#search-q")
    expect(q).to_have_attribute("maxlength", "100")
    expect(q).to_have_attribute("autocomplete", "off")
    assert q.get_attribute("placeholder") is None  # a placeholder is never the only label
    hint = q.get_attribute("aria-describedby")
    assert hint and p.locator("#" + hint).inner_text() == "Type a word, for example a product name."
    # Page order: heading, field, hint, button, status region, alert region.
    order = p.evaluate(
        """() => ['screen-title','search-q','search-hint','search-go','search-status','search-alert']
          .map((i) => document.getElementById(i)).map((e, k, a) => k === 0 || !!(a[k-1].compareDocumentPosition(e) & 4))"""
    )
    assert all(order), order
    # Both live regions exist and are empty before the first search.
    expect(p.locator("#search-status")).to_have_attribute("role", "status")
    expect(p.locator("#search-alert")).to_have_attribute("role", "alert")
    expect(p.locator("#search-status")).to_have_text("")
    expect(p.locator("#search-alert")).to_have_text("")
    audit(p, "sc2a-idle", AUDIT_LOG, width=1280)
    write("audit-s7.json", AUDIT_LOG, EVIDENCE)


def test_ac124_empty_field_sends_no_call(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    p = s.page
    for text in ("", "   "):
        p.locator("#search-q").fill(text)
        p.locator("#search-go").click()
        expect(p.locator("#search-q")).to_have_attribute("aria-invalid", "true")
        expect(p.locator("#search-err")).to_have_text("Type a word to search for.")
        assert active(p) == "#search-q"
    # Enter in the field does the same.
    p.locator("#search-q").fill(" ")
    p.keyboard.press("Enter")
    expect(p.locator("#search-err")).to_be_visible()
    assert p.locator("#search-err").get_attribute("role") is None  # not a live region
    described = p.locator("#search-q").get_attribute("aria-describedby") or ""
    assert "search-err" in described and "search-hint" in described
    expect(p.locator("#search-status")).to_have_text("")
    assert ops(s) == []  # no call went out
    # Typing alone sends nothing.
    p.locator("#search-q").fill("mug")
    assert ops(s) == []


def test_ac125_query_is_trimmed_and_alone(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    search_ok(s, "  mug  ")
    assert bodies(s, "search") == [{"query": "mug"}]
    sent = bodies(s, "search")[0]
    for key in ("limit", "filters", "context", "signals", "attribution", "sort", "pagination"):
        assert key not in sent


# ---------------------------------------------------------------- AC-126, AC-127, AC-12.3
def test_ac126_idle_and_no_results(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    p = s.page
    idle = p.locator("#search-idle")
    expect(idle).to_have_text("No search yet. Type a word and select 'Search'.")
    expect(p.locator("#search-status")).to_have_text("")
    expect(p.locator("#search-alert")).to_have_text("")
    assert p.locator("#results").is_hidden()
    idle_icon = idle.locator("svg").evaluate("e => e.innerHTML")
    run_search(s, "roses")
    status = p.locator("#search-status")
    expect(status).to_have_text("No products match 'roses'. Try another word.")
    expect(p.locator("#search-alert")).to_have_text("")
    none_icon = status.locator("svg").evaluate("e => e.innerHTML")
    assert idle_icon != none_icon  # the two states have different icons
    assert p.locator("#search-idle").is_hidden()
    assert p.locator("#results li").count() == 0


def test_ac127_cards_show_only_the_allowed_fields(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    search_ok(s, "demo")
    p = s.page
    ul = p.get_by_role("list", name="Results")
    expect(ul.locator("li")).to_have_count(2)
    expect(p.locator("#search-status")).to_have_text("Products shown: 2 of 2")
    expect(p.locator("#results-h")).to_have_text("Results")
    for i in range(2):
        card = ul.locator("li").nth(i)
        title = card.locator("h4").inner_text()
        expect(card.locator("p.price")).to_have_text(re.compile(r"^£\d+\.\d\d$"))
        expect(card.locator("p.avail")).to_have_text(re.compile(r"^(In stock|Out of stock)$"))
        expect(card.get_by_role("button", name=f"View details {title}")).to_have_count(1)
        tags = card.evaluate("e => [...e.children].map(c => c.tagName)")
        assert set(tags) <= {"IMG", "H4", "P", "BUTTON"}, tags
        assert card.locator("button").count() == 1
    lines = [x for x in p.locator("#results li").nth(0).inner_text().split("\n") if x.strip()]
    # title, price, availability, and the button (its hidden part repeats the title)
    assert len(lines) == 5 and lines[3] == "View details" and lines[4] == lines[0], lines
    audit(p, "sc2a-results", AUDIT_LOG, width=1280)


def test_ac12_3_one_price_or_a_range(make_stack: Make) -> None:
    def ranged(req: httpx.Request, body: dict[str, Any]) -> dict[str, Any]:
        first = body["products"][0]
        first["price_range"] = {
            "min": {"amount": 1500, "currency": "GBP"},
            "max": {"amount": 2000, "currency": "GBP"},
        }
        return body

    s = make_stack(catalog=True)
    s.hook.mutate["search"] = ranged
    to_search(s)
    search_ok(s, "demo")
    prices = s.page.locator("#results p.price")
    expect(prices.nth(0)).to_have_text("£15.00 to £20.00")
    expect(prices.nth(1)).to_have_text(re.compile(r"^£\d+\.\d\d$"))  # min equals max: one price


def test_ux76_image_has_alt_text_or_is_decorative(make_stack: Make) -> None:
    """UX-7.6 SC 1.1.1: `alt_text` is the text alternative. With none, the image is decorative."""

    def images(req: httpx.Request, body: dict[str, Any]) -> dict[str, Any]:
        url = "https://images.example/p.png"
        body["products"][0]["media"] = [{"type": "image", "url": url, "alt_text": "A white mug"}]
        body["products"][1]["media"] = [{"type": "image", "url": url}]
        return body

    s = make_stack(catalog=True)
    s.hook.mutate["search"] = images
    to_search(s)
    search_ok(s, "demo")
    cards = s.page.locator("#results li")
    first, second = cards.nth(0).locator("img"), cards.nth(1).locator("img")
    expect(first).to_have_attribute("alt", "A white mug")
    expect(second).to_have_attribute("alt", "")  # decorative: the title is next to the image
    assert cards.nth(1).locator("h4").inner_text()


# ---------------------------------------------------------------- AC-128, AC-129
def test_ac128_ac129_show_more_results(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    s.hook.mutate["search"] = more_pages()
    to_search(s)
    search_ok(s, "demo")
    p = s.page
    # AC-129: 3 products and has_next_page true. The button shows. No error shows.
    expect(p.locator("#results li")).to_have_count(3)
    more = p.get_by_role("button", name="Show more results")
    expect(more).to_be_visible()
    expect(p.locator("#search-alert")).to_have_text("")
    expect(p.locator("#search-status")).to_have_text("Products shown: 3 of 5")
    first_titles = p.locator("#results h4").all_inner_texts()
    s.hook.delay["search"] = 0.6
    more.click()
    expect(p.locator("#search-status")).to_have_text("Loading more products.")
    expect(p.locator("#results")).to_have_attribute("aria-busy", "true")
    expect(more).to_be_hidden()
    expect(p.locator("#results li")).to_have_count(3)  # the old products stay
    next_step(p)
    expect(p.locator("#results li")).to_have_count(5)
    # AC-128: the request has the cursor of the last answer. New products follow the old ones.
    assert bodies(s, "search")[1] == {"query": "demo", "pagination": {"cursor": "c1"}}
    assert p.locator("#results h4").all_inner_texts()[:3] == first_titles
    assert active(p) == "BUTTON:View details Extra product 4"
    expect(p.locator("#search-status")).to_have_text("Products shown: 5 of 5")
    expect(p.locator("#results")).to_have_attribute("aria-busy", "false")
    # has_next_page false: no "Show more results" and no previous-page control.
    expect(p.locator("#more")).to_have_count(1)
    expect(p.locator("#more")).to_be_hidden()
    assert p.get_by_role("button", name=re.compile("previous", re.I)).count() == 0


# ---------------------------------------------------------------- AC-130
def test_ac130_no_answer_in_10_s(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    p = s.page
    cfg = p.evaluate("fetch('/checkout/config.json').then(r => r.json())")
    assert cfg["catalog_ms"] == 10000  # the 10 s limit of UX-U-29
    search_ok(s, "demo")
    expect(p.locator("#results li")).to_have_count(2)
    p.clock.install()
    s.hook.delay["search"] = 2.0
    p.locator("#search-q").fill("mug")
    p.locator("#search-go").click()
    expect(p.locator("#search-status")).to_have_text("Searching the shop.")
    next_step(p)
    row = p.locator('#msg-list li[data-mid="M1a"]').last
    expect(row).to_contain_text("Waiting")
    expect(p.locator("#results")).to_have_attribute("aria-busy", "true")
    expect(p.locator("#search-alert")).to_have_text("")
    p.clock.fast_forward(9_000)  # not yet 10 s
    expect(p.locator("#search-alert")).to_have_text("")
    p.clock.fast_forward(1_500)
    alert = p.locator("#search-alert")
    expect(alert).to_contain_text("We cannot reach the shop. Your search is still on this page.")
    expect(alert.get_by_role("button", name="Try again")).to_be_visible()
    expect(p.locator("#search-status")).to_have_text("")
    expect(row).to_contain_text("No response")
    expect(p.locator("#results li")).to_have_count(2)  # the old list stays
    # A late answer changes nothing.
    p.wait_for_timeout(2300)
    expect(alert).to_contain_text("We cannot reach the shop")
    expect(p.locator("#results li")).to_have_count(2)
    # Try again sends the same request.
    s.hook.delay.clear()
    alert.get_by_role("button", name="Try again").click()
    next_step(p)
    expect(p.locator("#search-status")).to_have_text("Products shown: 1 of 1")
    assert bodies(s, "search")[-1] == {"query": "mug"}
    assert bodies(s, "search")[-2] == {"query": "mug"}
    expect(p.locator("#search-alert")).to_have_text("")


# ---------------------------------------------------------------- AC-131
def test_ac131_network_error_and_protocol_error(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    p = s.page
    s.hook.drop["search"] = 1
    run_search(s, "demo")
    alert = p.locator("#search-alert")
    expect(alert).to_contain_text("We cannot reach the shop. Your search is still on this page.")
    expect(p.locator("#search-go")).to_be_enabled()
    expect(p.locator("#msg-list li").last).to_contain_text("No response")
    alert.get_by_role("button", name="Try again").click()
    next_step(p)
    expect(p.locator("#results li")).to_have_count(2)
    # HTTP 500: protocol text and "Start again". No "Try again".
    s.hook.status["search"] = (500, {"code": "internal"})
    run_search(s, "mug")
    expect(alert).to_contain_text(
        "The shop did not accept the search. This is a demo setup problem."
    )
    expect(alert.get_by_role("button", name="Start again")).to_be_visible()
    assert alert.get_by_role("button", name="Try again").count() == 0
    expect(p.locator("#msg-list li").last).to_contain_text("Error")
    expect(p.locator("#results li")).to_have_count(2)
    # HTTP 429 and 503: "Try again". No "Start again".
    for code in (429, 503):
        s.hook.status["search"] = (code, {"code": "busy"})
        p.locator("#search-go").click()
        next_step(p)
        expect(alert.get_by_role("button", name="Try again")).to_be_visible()
        assert alert.get_by_role("button", name="Start again").count() == 0
    # ucp.status error with HTTP 200 gets the protocol text and "Start again".
    s.hook.status.pop("search")

    def refused(req: httpx.Request, body: dict[str, Any]) -> dict[str, Any]:
        err = {
            "type": "error",
            "code": "invalid_request",
            "content": "no",
            "severity": "recoverable",
        }
        return {"ucp": {**body["ucp"], "status": "error"}, "products": [], "messages": [err]}

    s.hook.mutate["search"] = refused
    p.locator("#search-go").click()
    next_step(p)
    expect(alert).to_contain_text("The shop did not accept the search.")
    expect(alert.get_by_role("button", name="Start again")).to_be_visible()
    expect(p.locator("#search-status")).to_have_text("")


# ---------------------------------------------------------------- AC-132, AC-12.10, AC-08b-6 (page)
def test_ac132_lookup_only_has_no_search(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    s.page.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda r: r.abort())
    open_page(s, "?case=lookup-only")
    p = s.page
    p.locator("#start").click()
    next_step(p)
    expect(p.locator("#screen-title")).to_have_text("Shop and item")
    notice = p.locator("#search-notice")
    expect(notice).to_have_text("Search is not available with this agent")
    expect(notice).to_have_attribute("role", "status")
    assert p.locator("#search-form").count() == 0
    # ST28: no quantity field and no button while the product loads.
    expect(p.locator("#detail-status")).to_have_text("Getting the product details.")
    assert p.locator("#field-line-items-0").count() == 0
    assert p.locator("#add").count() == 0
    next_step(p)
    expect(p.locator("#detail-card h3")).to_have_text("Demo T-shirt")
    assert bodies(s, "product") == [{"id": "demo_tshirt"}]
    # The Item select works: it sends Get Product again.
    expect(p.locator("#item-hint")).to_have_text(
        "The product details change when you select another item."
    )
    expect(p.locator("#item-choice")).to_have_attribute("aria-describedby", "item-hint")
    p.locator("#item-choice").select_option("demo_mug")
    next_step(p)
    expect(p.locator("#detail-card h3")).to_have_text("Demo mug")
    assert bodies(s, "product") == [{"id": "demo_tshirt"}, {"id": "demo_mug"}]
    assert "search" not in ops(s) and "lookup" not in ops(s)


def test_ac12_10_neither_capability_keeps_the_one_item_start(make_stack: Make) -> None:
    s = make_stack()  # the harness default: no catalog capability is active
    open_page(s)
    p = s.page
    p.locator("#start").click()
    next_step(p)
    expect(p.locator("#screen-title")).to_have_text("Shop and item")
    assert p.locator("#search-form").count() == 0
    expect(p.locator("#item-choice")).to_be_visible()
    assert ops(s) == []


def test_ac12_10_search_only_uses_the_card_and_sends_no_get_product(make_stack: Make) -> None:
    s = make_stack(catalog="search")
    to_search(s)
    search_ok(s, "demo")
    p = s.page
    p.get_by_role("button", name="View details Demo T-shirt").click()
    expect(p.locator("#screen-title")).to_have_text("Shop and item")
    expect(p.locator("#detail-card h3")).to_have_text("Demo T-shirt")  # no call: the card gives it
    assert ops(s) == ["search"]
    sent: list[Any] = []
    p.on(
        "request",
        lambda r: sent.append(r.post_data_json) if r.url.endswith("/api/checkout") else None,
    )
    p.locator("#add").click()
    next_step(p)
    expect(p.locator("#screen-title")).to_have_text("Your details")
    assert sent[0]["line_items"][0]["item"]["id"] == "demo_tshirt"  # AC-12.8: the variant id
    assert ops(s) == ["search"]


# ---------------------------------------------------------------- AC-133, AC-12.8
def test_ac133_view_details_calls_get_product(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    search_ok(s, "mug")
    p = s.page
    pid = p.locator("#results li").first.get_attribute("data-product")
    assert pid
    p.get_by_role("button", name="View details Demo mug").click()
    expect(p.locator("#screen-title")).to_have_text("Shop and item")
    assert active(p) == "#screen-title"  # focus is on the SC2 heading
    expect(p.locator("#detail-status")).to_have_text("Getting the product details.")
    next_step(p)
    card = p.locator("#detail-card")
    expect(card.locator("h3")).to_have_text("Demo mug")
    expect(card.locator("p.price")).to_have_text(re.compile(r"^£\d+\.\d\d$"))
    expect(card.locator("p.avail")).to_have_text(re.compile(r"^(In stock|Out of stock)$"))
    want = biz_product(s, pid)["product"]["description"]["plain"]
    expect(card.locator("p.desc")).to_have_text(want)
    assert bodies(s, "product") == [{"id": pid}]  # no selected, preferences or filters
    assert "lookup" not in ops(s)
    expect(p.locator("#detail-status")).to_have_text("")
    audit(p, "sc2-detail", AUDIT_LOG, width=1280)


def test_ac134_add_sends_the_variant_id_or_is_disabled(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    search_ok(s, "demo")
    p = s.page
    p.get_by_role("button", name="View details Demo T-shirt").click()
    next_step(p)
    sent: list[Any] = []
    p.on(
        "request",
        lambda r: sent.append(r.post_data_json) if r.url.endswith("/api/checkout") else None,
    )
    p.locator("#field-line-items-0").fill("2")
    p.locator("#add").click()
    next_step(p)
    expect(p.locator("#screen-title")).to_have_text("Your details")
    line = sent[0]["line_items"][0]
    assert line["item"]["id"] == "demo_tshirt"  # variants[0].id, not the product id
    assert line["quantity"] == 2
    assert "create" in s.hook.ops()


def test_ac134_unavailable_missing_availability_and_missing_variants(make_stack: Make) -> None:
    s = make_stack(catalog=True)

    def unavailable(req: httpx.Request, body: dict[str, Any]) -> dict[str, Any]:
        body["product"]["variants"][0]["availability"] = {"available": False}
        return body

    def no_availability(req: httpx.Request, body: dict[str, Any]) -> dict[str, Any]:
        del body["product"]["variants"][0]["availability"]
        return body

    def no_variants(req: httpx.Request, body: dict[str, Any]) -> dict[str, Any]:
        body["product"]["variants"] = []
        return body

    to_search(s)
    search_ok(s, "mug")
    p = s.page
    cases = (
        (unavailable, False, "Not available"),
        (no_availability, True, None),
        (no_variants, False, None),
    )
    for mutator, enabled, avail in cases:
        s.hook.mutate["product"] = mutator
        p.get_by_role("button", name="View details Demo mug").click()
        next_step(p)
        add = p.locator("#add")
        expect(add).to_be_visible()
        if enabled:
            expect(add).to_be_enabled()
            assert p.locator("#add-unavailable").count() == 0
            assert p.locator("#detail-card p.avail").count() == 0  # nothing when it is missing
        else:
            expect(add).to_be_disabled()
            expect(p.locator("#add-unavailable")).to_have_text("You cannot add this item now.")
            expect(add).to_have_attribute("aria-describedby", "add-unavailable")
        if avail:
            expect(p.locator("#detail-card p.avail")).to_have_text(avail)
        p.get_by_role("button", name="Back to results").click()
    assert "create" not in s.hook.ops()  # no checkout call for a disabled button


def test_ac134_availability_texts(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    statuses = ["in_stock", "backorder", "preorder", "out_of_stock", "discontinued"]

    def many(req: httpx.Request, body: dict[str, Any]) -> dict[str, Any]:
        base = body["products"][0]
        out = []
        for i, st in enumerate(statuses):
            p = copy.deepcopy(base)
            p["id"], p["title"] = f"prod_a{i}", f"Item {i}"
            p["variants"][0]["availability"] = {"available": st != "discontinued", "status": st}
            out.append(p)
        for flag in (True, False):
            p = copy.deepcopy(base)
            p["id"], p["title"] = f"prod_f{flag}", f"Flag {flag}"
            p["variants"][0]["availability"] = {"available": flag}
            out.append(p)
        p = copy.deepcopy(base)
        p["id"], p["title"] = "prod_none", "No state"
        del p["variants"][0]["availability"]
        out.append(p)
        return {**body, "products": out}

    s.hook.mutate["search"] = many
    to_search(s)
    search_ok(s, "demo")
    avail = s.page.locator("#results li").evaluate_all(
        "els => els.map(e => (e.querySelector('p.avail') || {}).textContent || null)"
    )
    assert avail == [
        "In stock",
        "On backorder",
        "Pre-order",
        "Out of stock",
        "No longer sold",
        "Available",
        "Not available",
        None,
    ]


# ---------------------------------------------------------------- AC-135, AC-12.15
def test_ac135_no_answer_and_not_found(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    search_ok(s, "mug")
    p = s.page
    p.clock.install()
    s.hook.delay["product"] = 1.5
    p.get_by_role("button", name="View details Demo mug").click()
    next_step(p)
    expect(p.locator('#msg-list li[data-mid="M1b"]').last).to_contain_text("Waiting")
    p.clock.fast_forward(10_500)
    alert = p.locator("#detail-alert")
    expect(alert).to_contain_text("We cannot reach the shop. Your choice is still on this page.")
    expect(alert.get_by_role("button", name="Try again")).to_be_visible()
    expect(alert.get_by_role("button", name="Back to results")).to_be_visible()
    expect(p.locator('#msg-list li[data-mid="M1b"]').last).to_contain_text("No response")
    p.wait_for_timeout(1800)
    s.hook.delay.clear()

    def not_found(req: httpx.Request, body: dict[str, Any]) -> dict[str, Any]:
        err = {"type": "error", "code": "not_found", "content": "gone", "severity": "recoverable"}
        return {"ucp": {**body["ucp"], "status": "error"}, "messages": [err]}

    s.hook.mutate["product"] = not_found
    before = len(bodies(s, "product"))
    alert.get_by_role("button", name="Try again").click()
    next_step(p)
    # ST16 by the code: the text of AC-12.15 and "Back to items". The same id is not sent again.
    expect(p.locator("#screen-title")).to_have_text("This item is not available")
    expect(p.get_by_text("This item is not available. Select a different item.")).to_be_visible()
    assert len(bodies(s, "product")) == before + 1
    expect(p.locator('#msg-list li[data-mid="M1b"]').last).to_contain_text("Error")
    p.get_by_role("button", name="Back to items").click()
    expect(p.locator("#screen-title")).to_have_text("Find a product")
    assert len(bodies(s, "product")) == before + 1


def test_ac12_15_back_to_items_without_search_opens_sc2(make_stack: Make) -> None:
    s = make_stack(catalog="lookup")

    def not_found(req: httpx.Request, body: dict[str, Any]) -> dict[str, Any]:
        err = {"type": "error", "code": "not_found", "content": "gone", "severity": "recoverable"}
        return {"ucp": {**body["ucp"], "status": "error"}, "messages": [err]}

    s.hook.mutate["product"] = not_found
    s.page.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda r: r.abort())
    open_page(s)
    s.page.locator("#start").click()
    next_step(s.page)
    expect(s.page.locator("#screen-title")).to_have_text("Shop and item")
    next_step(s.page)
    expect(s.page.locator("#screen-title")).to_have_text("This item is not available")
    s.page.get_by_role("button", name="Back to items").click()
    expect(s.page.locator("#screen-title")).to_have_text("Shop and item")
    assert s.page.locator("#search-form").count() == 0
    assert len(bodies(s, "product")) == 1  # the same id is not sent again until the buyer acts
    s.hook.mutate.clear()
    next_step(s.page)  # the item screen asks for the item again, as on open (AC-132)
    expect(s.page.locator("#detail-card h3")).to_have_text("Demo T-shirt")


def test_detail_protocol_error_buttons(make_stack: Make) -> None:
    """ST30: the buttons follow the code. Back to results shows with search."""
    s = make_stack(catalog=True)
    to_search(s)
    search_ok(s, "mug")
    p = s.page
    s.hook.status["product"] = (500, {"code": "x"})
    p.get_by_role("button", name="View details Demo mug").click()
    next_step(p)
    alert = p.locator("#detail-alert")
    expect(alert).to_contain_text(
        "The shop did not accept the request for this product. This is a demo setup problem."
    )
    expect(alert.get_by_role("button", name="Start again")).to_be_visible()
    assert alert.get_by_role("button", name="Try again").count() == 0
    expect(alert.get_by_role("button", name="Back to results")).to_be_visible()
    s.hook.status["product"] = (503, {"code": "x"})
    p.get_by_role("button", name="Back to results").click()
    p.get_by_role("button", name="View details Demo mug").click()
    next_step(p)
    expect(alert.get_by_role("button", name="Try again")).to_be_visible()


# ---------------------------------------------------------------- AC-136
def test_ac136_inspector_rows_and_replay(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    to_search(s)
    search_ok(s, "demo")
    p = s.page
    p.get_by_role("button", name="View details Demo mug").click()
    next_step(p)
    expect(p.locator("#detail-card h3")).to_have_text("Demo mug")
    rows = p.locator("#msg-list li")
    expect(rows).to_have_count(3)  # Discovery, M1a, M1b
    for i, name in ((1, "Search Catalog"), (2, "Get Product")):
        row = rows.nth(i)
        expect(row).to_contain_text(name)
        expect(row).to_contain_text("Phase: Find product")
        expect(row.locator(".badge")).to_have_attribute("data-source", "LIVE CALL")
        assert row.locator(".badge.notucp").count() == 0
        assert row.locator(".badge.local").count() == 0
        row.locator("button").click()
        keys = p.locator("#msg-detail dt")
        assert 3 <= keys.count() <= 6, keys.all_inner_texts()
        expect(p.locator("#msg-detail")).to_contain_text(
            "This call finds products. It does not start a checkout."
        )
    names = p.locator("#msg-detail dt").all_inner_texts()
    assert names[:2] == ["id", "HTTP status"]
    rows.nth(1).locator("button").click()
    assert p.locator("#msg-detail dt").all_inner_texts()[:4] == [
        "query",
        "HTTP status",
        "products",
        "pagination.has_next_page",
    ]
    calls = len(s.hook.calls)
    # Replay: both rows are RECORDED. SC2a shows the saved query read-only. No call goes out.
    p.locator("#replay").click()
    for _ in range(3):
        next_step(p)
        if p.locator("#search-form").count():
            break
    expect(p.locator("#screen-title")).to_have_text("Find a product")
    expect(p.locator("#search-q")).to_have_value("demo")
    expect(p.locator("#search-q")).to_have_attribute("readonly", "")
    expect(p.locator("#replay-search-note")).to_have_text(
        "This is a recorded search. The answers are saved."
    )
    expect(p.locator("#results li")).to_have_count(2)
    expect(p.locator("#search-go")).to_have_attribute("aria-disabled", "true")
    p.locator("#search-go").click(force=True)  # aria-disabled: nothing happens
    p.locator("#results button.view").first.click(force=True)
    expect(p.locator("#screen-title")).to_have_text("Find a product")
    next_step(p)
    expect(p.locator("#replay-done")).to_be_visible()
    badges = p.locator("#msg-list .badge").evaluate_all("els => els.map(e => e.dataset.source)")
    assert badges and set(badges) == {"RECORDED"}, badges
    assert len(s.hook.calls) == calls  # no catalog call in the replay
    assert not [r for r in s.requests if "/api/catalog" in r and r.endswith("/search")][1:]


# ---------------------------------------------------------------- AC-137
def test_ac137_keyboard_order_and_back_to_results(make_stack: Make) -> None:
    s = make_stack(catalog=True)
    s.hook.mutate["search"] = more_pages()
    to_search(s)
    search_ok(s, "demo")
    p = s.page
    p.locator("#search-q").focus()
    seen = ["#search-q"]
    visible = []
    for _ in range(5):
        p.keyboard.press("Tab")
        seen.append(active(p))
        visible.append(
            p.evaluate(
                "() => { const c = getComputedStyle(document.activeElement);"
                " return c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) >= 2; }"
            )
        )
    assert seen == [
        "#search-q",
        "#search-go",
        "BUTTON:View details Demo mug",
        "BUTTON:View details Demo T-shirt",
        "BUTTON:View details Extra product 3",
        "#more",
    ], seen
    assert all(visible), visible  # each control has a visible focus
    # Open the second product with the keyboard. Back to results returns the focus to it.
    p.get_by_role("button", name="View details Demo T-shirt").focus()
    pid = p.evaluate("document.activeElement.closest('li').dataset.product")
    p.keyboard.press("Enter")
    next_step(p)
    expect(p.locator("#detail-card h3")).to_have_text("Demo T-shirt")
    p.get_by_role("button", name="Back to results").focus()
    p.keyboard.press("Enter")
    expect(p.locator("#screen-title")).to_have_text("Find a product")
    assert p.evaluate("document.activeElement.closest('li').dataset.product") == pid
    expect(p.locator("#results li")).to_have_count(3)  # the list is still there
    # When the product is not in the list any more, the focus goes to the heading.
    p.evaluate("window.__ucpDemo.cat.opened = 'gone'")
    p.get_by_role("button", name="View details Demo mug").click()
    next_step(p)
    p.evaluate("window.__ucpDemo.cat.opened = 'gone'")
    p.get_by_role("button", name="Back to results").click()
    assert active(p) == "#screen-title"


# ---------------------------------------------------------------- AC-138
def test_ac138_reflow_and_target_size_at_320(make_stack: Make) -> None:
    s = make_stack(catalog=True, viewport=(320, 700))
    s.hook.mutate["search"] = more_pages()
    to_search(s)
    p = s.page
    audit(p, "sc2a-320-idle", AUDIT_LOG, width=320)
    search_ok(s, "demo")
    audit(p, "sc2a-320-results", AUDIT_LOG, width=320)
    box = p.evaluate(
        """() => { const q = document.getElementById('search-q').getBoundingClientRect();
          const b = document.getElementById('search-go').getBoundingClientRect();
          return { qBottom: q.bottom, bTop: b.top, qLeft: q.left, bLeft: b.left,
            scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth }; }"""
    )
    assert box["bTop"] >= box["qBottom"] - 1, box  # the button is below the field (stacked)
    assert box["scrollW"] <= box["clientW"], box  # no sideways scroll
    p.get_by_role("button", name="View details Demo mug").click()
    next_step(p)
    expect(p.locator("#detail-card h3")).to_have_text("Demo mug")
    audit(p, "sc2-320-detail", AUDIT_LOG, width=320)
    alert_state = p.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    assert alert_state
    write("audit-s7.json", AUDIT_LOG, EVIDENCE)
