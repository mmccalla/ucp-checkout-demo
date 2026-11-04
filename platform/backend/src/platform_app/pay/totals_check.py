"""Totals check before payment (AC-20, AGT-12).

Pinned UCP `checkout.md` at commit `9c9d6fc`, lines 797 to 815:
- `assert sum(e.amount for e in totals if e.type != "total") == total_entry.amount`
- Sub-lines: the sum of the lines must equal the parent amount.
- Exactly one `subtotal` and exactly one `total`.
- "platforms MUST NOT autonomously complete a checkout with mismatched totals".
"""

from __future__ import annotations

from typing import Any

DEFAULT_LABELS = {
    "subtotal": "Subtotal",
    "items_discount": "Item Discounts",
    "discount": "Discount",
    "fulfillment": "Shipping",
    "tax": "Tax",
    "fee": "Fee",
    "total": "Total",
}


def _amount(e: Any) -> int | None:
    a = e.get("amount") if isinstance(e, dict) else None
    return a if isinstance(a, int) and not isinstance(a, bool) else None


def check_totals(totals: Any, where: str = "$.totals") -> list[str]:
    if not isinstance(totals, list) or not totals:
        return [f"{where}: no totals"]
    problems: list[str] = []
    types = [e.get("type") if isinstance(e, dict) else None for e in totals]
    for t in ("subtotal", "total"):
        if types.count(t) != 1:
            problems.append(f"{where}: {types.count(t)} entries of type {t!r}, expected 1")
    for i, e in enumerate(totals):
        if _amount(e) is None:
            problems.append(f"{where}[{i}].amount is not an integer")
            continue
        lines = e.get("lines")
        if isinstance(lines, list) and lines:
            amounts = [_amount(x) for x in lines]
            if None in amounts or sum(a for a in amounts if a is not None) != e["amount"]:
                problems.append(f"{where}[{i}].lines do not add up to {e['amount']}")
    if problems:
        return problems
    total = next(e for e in totals if e["type"] == "total")
    parts = sum(e["amount"] for e in totals if e["type"] != "total")
    if parts != total["amount"]:
        problems.append(f"{where}: the entries add up to {parts}, but total is {total['amount']}")
    return problems


def check_checkout(checkout: dict[str, Any]) -> list[str]:
    problems = check_totals(checkout.get("totals"))
    for i, li in enumerate(checkout.get("line_items") or []):
        if isinstance(li, dict) and li.get("totals") is not None:
            problems += check_totals(li["totals"], f"$.line_items[{i}].totals")
    return problems


def total_amount(checkout: dict[str, Any]) -> int:
    for e in checkout.get("totals") or []:
        if isinstance(e, dict) and e.get("type") == "total" and _amount(e) is not None:
            return int(e["amount"])
    raise ValueError("checkout has no total")


def label(entry: dict[str, Any]) -> str:
    text = entry.get("display_text")
    if isinstance(text, str) and text:
        return text
    return DEFAULT_LABELS.get(str(entry.get("type")), str(entry.get("type")))
