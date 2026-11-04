"""Minor units to the Google Pay `totalPrice` string and to display text.

- UCP amounts are integers in minor units (`total.json` at UCP `9c9d6fc`).
- Google Pay `totalPrice` must match `^[0-9]+(\\.[0-9][0-9])?$`
  (https://developers.google.com/pay/api/web/reference/request-objects, TransactionInfo).
- The demo uses GBP only (DM-16). GBP has 2 minor-unit digits (ISO 4217).
"""

from __future__ import annotations

import re

EXPONENT = {"GBP": 2}
SCALE = {"GBP": 100}
SYMBOL = {"GBP": "£"}
PRICE_RE = re.compile(r"^[0-9]+(\.[0-9][0-9])?$")


def minor_to_price(amount: int, currency: str) -> str:
    """Return the exact decimal string for `amount` minor units. No float is used."""
    if currency not in EXPONENT:
        raise ValueError(f"currency {currency!r} is not supported (DM-16: GBP only)")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise ValueError(f"amount must be a non-negative integer, not {amount!r}")
    exp = EXPONENT[currency]
    units, minor = divmod(amount, SCALE[currency])
    return f"{units}.{minor:0{exp}d}"


def price_to_minor(price: str, currency: str) -> int:
    if not PRICE_RE.match(price):
        raise ValueError(f"price {price!r} does not match {PRICE_RE.pattern}")
    exp = EXPONENT[currency]
    units, _, minor = price.partition(".")
    return int(units) * SCALE[currency] + int((minor or "0").ljust(exp, "0"))


def display(amount: int, currency: str) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}{SYMBOL.get(currency, currency + ' ')}{minor_to_price(abs(amount), currency)}"
