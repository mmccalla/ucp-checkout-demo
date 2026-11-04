"""Approval hash (AC-22, CTL-4).

The hash covers what the buyer approves on the review screen: the checkout id, the Business
profile URL, the currency, the line items, the totals and the handler id. A fresh Get before
Complete must give the same hash. If not, the Platform discards the token and shows a new
review. One approval permits one Complete.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def approval_hash(checkout: dict[str, Any], business_profile_url: str, handler_id: str) -> str:
    subject = {
        "id": checkout.get("id"),
        "business": business_profile_url,
        "currency": checkout.get("currency"),
        "line_items": checkout.get("line_items"),
        "totals": checkout.get("totals"),
        "handler_id": handler_id,
    }
    canon = json.dumps(subject, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()
