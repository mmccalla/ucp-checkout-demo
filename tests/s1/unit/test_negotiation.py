"""AC-05, AC-08 (a), AC-09: intersection and spec URL binding (overview)."""

from __future__ import annotations

from typing import Any

from ucp_core import negotiation

V = "2026-04-08"


def cap(name: str, version: str = V, **kw: Any) -> dict[str, list[dict[str, Any]]]:
    slug = name.rsplit(".", 1)[1]
    return {
        name: [
            {
                "version": version,
                "spec": f"https://ucp.dev/{version}/specification/{slug}",
                "schema": f"https://ucp.dev/{version}/schemas/shopping/{slug}.json",
                **kw,
            }
        ]
    }


CHECKOUT = "dev.ucp.shopping.checkout"
FULFILLMENT = "dev.ucp.shopping.fulfillment"
ORDER = "dev.ucp.shopping.order"
SEARCH = "dev.ucp.shopping.catalog.search"
LOOKUP = "dev.ucp.shopping.catalog.lookup"


def ours() -> dict[str, list[dict[str, Any]]]:
    return cap(CHECKOUT) | cap(FULFILLMENT, extends=CHECKOUT) | cap(ORDER)


def test_ac08a_our_platform_and_business() -> None:
    active, excluded = negotiation.intersect(ours(), ours())
    assert sorted(active) == [CHECKOUT, FULFILLMENT, ORDER]
    assert excluded == {}


def test_ac09_lookup_without_search() -> None:
    business = ours() | cap(SEARCH) | cap(LOOKUP)
    platform = cap(CHECKOUT) | cap(LOOKUP)
    active, excluded = negotiation.intersect(business, platform)
    assert LOOKUP in active and CHECKOUT in active and SEARCH not in active
    assert excluded[SEARCH] == "not declared by the platform"


def test_extension_removed_when_parent_not_active() -> None:
    business = ours()
    platform = cap(FULFILLMENT, extends=CHECKOUT) | cap(ORDER)
    active, excluded = negotiation.intersect(business, platform)
    assert FULFILLMENT not in active
    assert "parent" in excluded[FULFILLMENT]


def test_no_mutual_version_excluded() -> None:
    active, excluded = negotiation.intersect(cap(CHECKOUT), cap(CHECKOUT, version="2026-01-23"))
    assert active == {}
    assert excluded[CHECKOUT] == "no mutual version"


def test_highest_mutual_version_selected() -> None:
    b = {CHECKOUT: cap(CHECKOUT, "2026-01-23")[CHECKOUT] + cap(CHECKOUT)[CHECKOUT]}
    active, _ = negotiation.intersect(b, b)
    assert active[CHECKOUT]["version"] == V


def test_ac05_binding() -> None:
    good = cap(CHECKOUT)[CHECKOUT][0]
    assert negotiation.binding_issues(CHECKOUT, good) == []
    bad = dict(good, spec="https://example.com/spec")
    assert negotiation.binding_issues(CHECKOUT, bad)
    assert negotiation.binding_issues(CHECKOUT, dict(good, schema="http://ucp.dev/x.json"))
    # Subdomain of the authority: accepted, UNVERIFIED (INFERENCE), see ADR 0002.
    gp = {"spec": "https://pay.google.com/gp/p/ucp/2026-01-23/"}
    assert negotiation.binding_issues("com.google.pay", gp) == []
    assert negotiation.binding_issues("com.google.pay", {"spec": "https://evilgoogle.com/"})
