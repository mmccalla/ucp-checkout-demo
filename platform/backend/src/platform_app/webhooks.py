"""Platform order webhook receiver and order state (S4, AC-65 to AC-75, T-32, T-40, T-42).

Sources at UCP commit 9c9d6fc: `docs/specification/order.md` lines 416 to 542 ("Events",
"Webhook Signature Verification", "Verification (Platform)", "Authorization").

The receiver does these steps in this order for `POST /webhooks/ucp/orders`:

1. Get the signer profile URL from `UCP-Agent`. Only a profile in the allowlist is fetched.
2. Verify the RFC 9421 signature with the `signing_keys` of that profile. The signature must
   also cover `webhook-id` and `webhook-timestamp` (`ucp_sigs.verify_webhook`). Fail: 401.
3. Parse the body and validate it against the pinned order schema. Fail: 400.
4. Check that the signer is authorized (order.md lines 512 to 517). The order `checkout_id`
   must be a checkout that this Platform created with the same Business profile. Fail: 403.
5. Dedup by `Webhook-Id` (T-32). If the dedup store does not answer: 503, so the Business
   retries (T-42). A seen `Webhook-Id` gives 200 and no change.
6. Apply the order snapshot. The order state goes forward only: created, shipped, delivered
   (T-40, opt-in ordering). An older event does not move the state back (AC-71).

The receiver answers quickly with 2xx (order.md "Platform" guidelines). It keeps no header
value. All order events in this demo are simulated (T-23).
"""

from __future__ import annotations

import json
import pathlib
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import ucp_sigs

ORDER_SCHEMA = "https://ucp.dev/2026-04-08/schemas/shopping/order.json"
PROFILE_RE = re.compile(r'profile="([^"]+)"')
RANK = {"created": 0, "shipped": 1, "delivered": 2}
LABELS = {"created": "Order confirmed", "shipped": "Shipped", "delivered": "Delivered"}
KeyResolver = Callable[[str], list[dict[str, Any]]]


def order_state(order: dict[str, Any]) -> str:
    kinds = {e.get("type") for e in ((order.get("fulfillment") or {}).get("events") or [])}
    if "delivered" in kinds:
        return "delivered"
    if "shipped" in kinds:
        return "shipped"
    return "created"


@dataclass
class OrderRecord:
    order_id: str
    checkout_id: str
    state: str = "created"
    order: dict[str, Any] = field(default_factory=dict)
    last_ts: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Outcome:
    status: int
    code: str
    content: str
    order_id: str | None = None
    applied: bool = False

    def body(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "content": self.content}
        if self.order_id:
            out["order_id"] = self.order_id
        return out


class Receiver:
    def __init__(self, dedup_db: pathlib.Path, schema_validate: Callable[[Any], list[str]]):
        self.dedup_db = dedup_db
        self.validate = schema_validate
        self.owned: dict[str, str] = {}  # checkout_id -> Business profile URL
        self.orders: dict[str, OrderRecord] = {}
        self.feed: list[dict[str, Any]] = []  # T-69: the inspector feed (server side)
        self.dedup_down = 0  # tests (T-42): the next N dedup calls fail
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ dedup store
    def _seen(self, webhook_id: str) -> bool:
        if self.dedup_down > 0:
            self.dedup_down -= 1
            raise sqlite3.OperationalError("dedup store down (test)")
        self.dedup_db.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.dedup_db), timeout=1.0)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS seen (webhook_id TEXT PRIMARY KEY, ts REAL)")
            cur = con.execute("INSERT OR IGNORE INTO seen VALUES (?, ?)", (webhook_id, time.time()))
            con.commit()
            return cur.rowcount == 0
        finally:
            con.close()

    # ------------------------------------------------------------------ receive
    def receive(
        self,
        authority: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
        allowlist: list[str],
        keys_for: KeyResolver,
    ) -> Outcome:
        h = {k.lower(): v for k, v in headers.items()}
        wid = h.get("webhook-id", "")
        row: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "webhook_id": wid,
            "webhook_timestamp": h.get("webhook-timestamp"),
            "event_type": h.get("x-event-type"),
        }
        out = self._receive(authority, path, h, body, allowlist, keys_for, row)
        row.update(status=out.status, code=out.code, order_id=out.order_id)
        with self.lock:
            self.feed.append(row)
        return out

    def _receive(
        self,
        authority: str,
        path: str,
        h: dict[str, str],
        body: bytes,
        allowlist: list[str],
        keys_for: KeyResolver,
        row: dict[str, Any],
    ) -> Outcome:
        m = PROFILE_RE.search(h.get("ucp-agent", ""))
        if m is None or m.group(1) not in allowlist:
            row["signature"] = "unknown signer"
            return Outcome(401, "signature_invalid", "The signer profile is not allowed.")
        profile_url = m.group(1)
        try:
            kid = ucp_sigs.verify_webhook(authority, path, h, body, keys_for(profile_url))
        except ucp_sigs.SignatureError as e:
            row["signature"] = f"invalid {getattr(e, 'code', 'signature_invalid')}"
            msg = str(getattr(e, "message", "") or "Bad signature.")
            return Outcome(401, str(getattr(e, "code", "signature_invalid")), msg)
        except Exception:  # noqa: BLE001  the profile fetch failed
            row["signature"] = "keys not available"
            return Outcome(401, "key_not_found", "The signer keys are not available.")
        row["signature"] = f"verified keyid={kid}"
        try:
            order = json.loads(body)
        except ValueError:
            return Outcome(400, "invalid_request", "The body is not JSON.")
        problems = self.validate(order)
        if problems or not isinstance(order, dict):
            return Outcome(400, "invalid_request", "; ".join(problems[:3]) or "Not an order.")
        order_id, checkout_id = str(order["id"]), str(order["checkout_id"])
        if self.owned.get(checkout_id) != profile_url:
            return Outcome(403, "unauthorized", "The signer does not own this order.", order_id)
        try:
            if self._seen(h.get("webhook-id", "")):
                return Outcome(200, "duplicate", "Seen before. No change.", order_id)
        except sqlite3.Error:
            return Outcome(503, "dedup_unavailable", "The dedup store is not available.", order_id)
        applied = self._apply(order_id, checkout_id, order, int(h.get("webhook-timestamp") or 0))
        return Outcome(200, "accepted", "Accepted.", order_id, applied)

    def _apply(self, order_id: str, checkout_id: str, order: dict[str, Any], ts: int) -> bool:
        new = order_state(order)
        with self.lock:
            rec = self.orders.setdefault(order_id, OrderRecord(order_id, checkout_id))
            older = ts < rec.last_ts or RANK[new] < RANK[rec.state]
            rec.events.append({"state": new, "applied": not older, "webhook_timestamp": ts})
            if older and rec.order:
                return False  # AC-71: an older event does not move the state back
            rec.state, rec.order, rec.last_ts = new, order, max(ts, rec.last_ts)
            return True

    def view(self, order_id: str) -> dict[str, Any] | None:
        with self.lock:
            rec = self.orders.get(order_id)
            if rec is None:
                return None
            reached = [s for s in ("created", "shipped", "delivered") if RANK[s] <= RANK[rec.state]]
            events = (rec.order.get("fulfillment") or {}).get("events") or []
            tracking = next(
                (
                    {"number": e.get("tracking_number"), "url": e.get("tracking_url")}
                    for e in reversed(events)
                    if e.get("tracking_number")
                ),
                None,
            )
            return {
                "order_id": rec.order_id,
                "checkout_id": rec.checkout_id,
                "state": rec.state,
                "steps": [{"state": s, "label": LABELS[s], "source": "SIMULATED"} for s in reached],
                "tracking": tracking,
                "permalink_url": rec.order.get("permalink_url"),
                "webhooks": [r for r in self.feed if r.get("order_id") == order_id],
            }
