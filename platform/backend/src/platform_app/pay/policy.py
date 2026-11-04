"""The approval gate: the spend limits of DM-06 (FR-09). Our own choice, not a UCP rule.

- (a) GBP 50.00 for each payment, GBP 100.00 each day, GBP only, one shop, TEST only.
- The gate is code. The agent part cannot change it (02-design.md section 2, item 3).
- The ledger counts only payments that the Business completed (status `completed`).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import threading
from dataclasses import dataclass
from typing import Any

from ucp_core.constants import ROOT

from .money import display

PER_PAYMENT = 5000
PER_DAY = 10000
CURRENCY = "GBP"
TEXT = {
    "per_payment": "This payment is more than the demo limit. You did not pay. "
    "The per-payment limit is £50.00.",
    "daily": "This payment is more than the demo limit. You did not pay. "
    "The daily limit is £100.00. Spent today: {spent}.",
    "currency": "Demo stopped. The currency is {currency}. The demo pays in GBP only.",
    "allowlist": "Demo stopped. This shop is not on the allowlist of the agent.",
    "not_test": "Demo stopped. The shop is not in TEST mode.",
}


@dataclass
class Reason:
    code: str
    text: str


def _ledger_file() -> pathlib.Path:
    return pathlib.Path(
        os.environ.get("PLATFORM_SPEND_FILE", str(ROOT / ".run" / "platform-spend.jsonl"))
    )


class Ledger:
    def __init__(self, path: pathlib.Path | None = None) -> None:
        self.path = path or _ledger_file()
        self._lock = threading.Lock()

    def spent_today(self, today: dt.date | None = None) -> int:
        day = (today or dt.date.today()).isoformat()
        if not self.path.exists():
            return 0
        total = 0
        for line in self.path.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("date") == day and row.get("currency") == CURRENCY:
                total += int(row.get("amount", 0))
        return total

    def add(self, checkout_id: str, amount: int, currency: str) -> None:
        row = {
            "date": dt.date.today().isoformat(),
            "checkout_id": checkout_id,
            "amount": amount,
            "currency": currency,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def gate(
    *,
    total: int,
    currency: str,
    environment: Any,
    business_profile_url: str,
    allowlist: list[str],
    spent_today: int,
) -> list[Reason]:
    reasons: list[Reason] = []
    if environment != "TEST":
        reasons.append(Reason("not_test", TEXT["not_test"]))
    if business_profile_url not in allowlist:
        reasons.append(Reason("allowlist", TEXT["allowlist"]))
    if currency != CURRENCY:
        reasons.append(Reason("currency", TEXT["currency"].format(currency=currency)))
        return reasons
    if total > PER_PAYMENT:
        reasons.append(Reason("per_payment", TEXT["per_payment"]))
    elif spent_today + total > PER_DAY:
        spent = display(spent_today, CURRENCY)
        reasons.append(Reason("daily", TEXT["daily"].format(spent=spent)))
    return reasons
