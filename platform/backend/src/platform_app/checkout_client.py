"""Platform checkout client for the Business REST binding (FR-07 to FR-12, S2).

- Each request sends `UCP-Agent: profile="<platform profile URL>"` and a `Request-Id`
  (checkout-rest.md, "Headers"). POST and PUT also send an `Idempotency-Key` (overview,
  "Idempotency").
- It signs each attempt with the Platform ES256 key (RFC 9421, `ucp_sigs`, T-04). The key
  stays on the server. The browser never gets it.
- Retry (AC-49, AC-50): on a transport error, 429 or 503 it sends the same body with the same
  Idempotency-Key and Request-Id. It waits for `Retry-After` (capped) and stops after
  `max_tries` (default 3) tries.
- Complete with no response (AC-44): the Platform does not retry at once. It calls Get Checkout
  with bounded backoff and stops at `expires_at`. Only if Get does not show what the Business
  did, it sends the identical Complete one time, with the same key. Source: UCP 2026-08-25,
  "Complete Checkout" (the URL is in the comment below this docstring),
  used where compatible with 2026-04-08 (03-spec.md AC-44).
- It never adds risk signals to a body (AC-37). A body with `signals` or `risk_signals` raises.
- It validates a checkout response (`ucp.status` = success) against the composed response
  schema (`contracts/composed`, AC-104). A failed check is a protocol problem, not a payment
  problem.
"""

# AC-44 source: UCP 2026-08-25, "Complete Checkout": https://ucp.dev/2026-08-25/specification/shopping/checkout/#complete-checkout  # g1-allow-unpinned
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from dataclasses import dataclass, field
from typing import Any

import httpx
import ucp_sigs
from ucp_core import composed, telemetry

RETRY_STATUSES = (429, 503)
MAX_RETRY_AFTER = 5.0
RECOVERY_BACKOFF = (0.5, 1.0, 2.0)  # AC-44: bounded. One Get after each wait.
MAX_IN_PROGRESS_POLLS = 30  # AC-45: a cap when `expires_at` is absent
FORBIDDEN_FIELDS = ("signals", "risk_signals")
SECURITY_TOKEN_IN_RESPONSE = "SECURITY credential_token_in_response"  # AC-93
security_log = logging.getLogger("platform.security")


def _token_paths(value: Any, path: str = "$") -> list[str]:
    """Paths of each `credential.token` in a response body. Never the value."""
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if str(k) == "credential" and isinstance(v, dict) and "token" in v:
                out.append(f"{path}.credential.token")
            out += _token_paths(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out += _token_paths(v, f"{path}[{i}]")
    return out


@dataclass
class Result:
    op: str
    method: str
    path: str
    status: int | None
    body: Any
    headers: dict[str, str]
    request_id: str
    idempotency_key: str | None
    tries: int
    request_body: Any = None
    schema_problems: list[str] = field(default_factory=list)
    transport_error: str | None = None
    raw: bytes = b""  # S4: the exact response bytes, for the response signature (AC-64)
    # AC-44: the earlier calls of a Complete recovery, in order: the Complete with no response
    # and each Get Checkout. The caller writes one timeline row for each (AC-59).
    earlier: list[Result] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


class CheckoutClient:
    # S7: the catalog client sends no `Idempotency-Key` (rest.openapi.json lines 564 to 720).
    idempotent = True

    def __init__(
        self,
        base_url: str,
        profile_url: str,
        key: Any,
        kid: str,
        transport: httpx.BaseTransport | None = None,
        verify: Any = True,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_tries: int = 3,
        sign: bool = True,
        on_result: Callable[[Result], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.profile_url = profile_url
        self.key = key
        self.kid = kid
        self.sleep = sleep
        self.now = now
        self.max_tries = max_tries
        self.sign = sign
        self.on_result = on_result
        self.http = httpx.Client(
            transport=transport, verify=verify, timeout=10.0, follow_redirects=False
        )
        telemetry.instrument_client(self.http, "platform")  # client span and `traceparent`

    def create(self, body: dict[str, Any]) -> Result:
        return self._send("create", "POST", "/checkout-sessions", body)

    def get(self, checkout_id: str) -> Result:
        return self._send("get", "GET", f"/checkout-sessions/{checkout_id}", None)

    def update(self, checkout_id: str, body: dict[str, Any]) -> Result:
        return self._send("update", "PUT", f"/checkout-sessions/{checkout_id}", body)

    def cancel(self, checkout_id: str) -> Result:
        return self._send("cancel", "POST", f"/checkout-sessions/{checkout_id}/cancel", None)

    def complete(
        self, checkout_id: str, body: dict[str, Any], expires_at: str | None = None
    ) -> Result:
        """S3: Complete Checkout (checkout-rest.md, `POST /checkout-sessions/{id}/complete`)."""
        path = f"/checkout-sessions/{checkout_id}/complete"
        first = self._send("complete", "POST", path, body, max_tries=1)
        if first.transport_error is None:
            if (
                first.ok
                and isinstance(first.body, dict)
                and first.body.get("status") == "complete_in_progress"
            ):
                return self._poll_in_progress(first, checkout_id, expires_at)
            return first
        return self._recover_complete(first, checkout_id, expires_at)

    def _poll_in_progress(self, first: Result, checkout_id: str, expires_at: str | None) -> Result:
        """AC-45. `complete_in_progress`: no Update and no Complete. Poll Get until a final status.

        The wait grows (0.5, 1, 2 s, then 2 s) and stops at `expires_at`. If `expires_at` is
        absent, at most `MAX_IN_PROGRESS_POLLS` Get calls are sent. The last Get result is the
        answer, with the Complete in `earlier`. Source: checkout.md status values
        (https://ucp.dev/2026-04-08/specification/checkout/) and the no-new-Complete rule of
        UCP 2026-08-25 (the URL is in the comment below this docstring).
        """
        # AC-45 source: UCP 2026-08-25, no new Complete: https://ucp.dev/2026-08-25/specification/shopping/checkout/  # g1-allow-unpinned
        stop = _parse_time(expires_at)
        earlier = [first]
        last: Result | None = None
        for n in range(MAX_IN_PROGRESS_POLLS):
            if stop is not None and self.now() >= stop:
                break
            self.sleep(RECOVERY_BACKOFF[min(n, len(RECOVERY_BACKOFF) - 1)])
            g = self._send("get", "GET", f"/checkout-sessions/{checkout_id}", None, max_tries=1)
            earlier.append(g)
            if not (g.ok and isinstance(g.body, dict)):
                continue
            last = g
            if g.body.get("status") != "complete_in_progress":
                break  # a final status (or any other status): stop
        if last is None:
            return first
        last.earlier = [e for e in earlier if e is not last]
        return last

    def _recover_complete(self, first: Result, checkout_id: str, expires_at: str | None) -> Result:
        """AC-44. Get with bounded backoff, then at most one identical Complete (same key)."""
        earlier = [first]
        last_get: Result | None = None
        stop = _parse_time(expires_at)
        for wait in RECOVERY_BACKOFF:
            if stop is not None and self.now() >= stop:
                break  # the Platform stops at `expires_at`
            self.sleep(wait)
            g = self._send("get", "GET", f"/checkout-sessions/{checkout_id}", None, max_tries=1)
            earlier.append(g)
            if not (g.ok and isinstance(g.body, dict)):
                continue  # Get does not show what the Business did
            last_get = g
            status = g.body.get("status")
            if status in ("completed", "canceled"):
                g.earlier = earlier[:-1]
                return g  # the Business processed the Complete. No second Complete.
            if status == "ready_for_complete":
                break  # the Business did not process it (or it declined). Send once more.
            # `complete_in_progress`: the Platform must not start a new Complete. Keep polling.
        if last_get is not None and last_get.body.get("status") == "complete_in_progress":
            last_get.earlier = [e for e in earlier if e is not last_get]
            return last_get
        if stop is not None and self.now() >= stop:
            first.earlier = earlier[1:]
            return first  # expired: no resend
        again = self.resend(first, max_tries=1)
        again.tries = first.tries + 1  # the number of Complete sends with this key
        again.earlier = earlier
        return again

    def get_order(self, order_id: str) -> Result:
        """S4 Reconcile (AC-73, T-43): Get Order (order.md "Operations", `GET /orders/{id}`)."""
        return self._send("get_order", "GET", f"/orders/{order_id}", None)

    def resend(self, res: Result, max_tries: int | None = None) -> Result:
        """AC-52 "Try again": the same request with the same `Request-Id` and key."""
        return self._send(
            res.op,
            res.method,
            res.path,
            res.request_body,
            request_id=res.request_id,
            idempotency_key=res.idempotency_key,
            max_tries=max_tries,
        )

    def _headers(self, request_id: str, idem: str | None, has_body: bool) -> dict[str, str]:
        h = {"UCP-Agent": f'profile="{self.profile_url}"', "Request-Id": request_id}
        if idem is not None:
            h["Idempotency-Key"] = idem
        if has_body:
            h["Content-Type"] = "application/json"
        return h

    def _send(
        self,
        op: str,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
        max_tries: int | None = None,
    ) -> Result:
        tries = max_tries or self.max_tries
        if body is not None:
            bad = [f for f in FORBIDDEN_FIELDS if f in body]
            if bad:
                raise ValueError(f"the Platform does not send risk signals (AC-37): {bad}")
        raw = b"" if body is None else json.dumps(body, separators=(",", ":")).encode()
        request_id = request_id or str(uuid.uuid4())
        idem = None
        if self.idempotent and method in ("POST", "PUT"):
            idem = idempotency_key or str(uuid.uuid4())
        url = self.base_url + path
        res = Result(op, method, path, None, None, {}, request_id, idem, 0, body)
        for attempt in range(1, tries + 1):
            res.tries = attempt
            headers = self._headers(request_id, idem, bool(raw))
            if self.sign:
                headers.update(ucp_sigs.sign_request(self.key, self.kid, method, url, headers, raw))
            try:
                r = self.http.request(method, url, content=raw or None, headers=headers)
            except httpx.TransportError as e:
                res.transport_error = type(e).__name__
                res.status, res.body, res.headers = None, None, {}
                if attempt < tries:
                    self.sleep(min(0.5 * attempt, MAX_RETRY_AFTER))
                continue
            res.transport_error = None
            res.status = r.status_code
            res.headers = {k.lower(): v for k, v in r.headers.items()}
            res.raw = r.content
            try:
                res.body = r.json()
            except ValueError:
                res.body = None
            if r.status_code in RETRY_STATUSES and attempt < tries:
                self.sleep(_retry_after(res.headers.get("retry-after")))
                continue
            break
        res.schema_problems = self._check(op, res)
        if self.on_result is not None:
            self.on_result(res)
        return res

    @staticmethod
    def _check(op: str, res: Result) -> list[str]:
        b = res.body
        # AC-93 (DATA AC-R6): a response never has `credential.token`. The check fails, the
        # Platform logs a security event, and no text of the response goes to the log or to
        # the problem list (a schema message could quote the token).
        leaks = _token_paths(b)
        if leaks:
            security_log.warning(
                "%s op=%s request_id=%s paths=%s",
                SECURITY_TOKEN_IN_RESPONSE,
                op,
                res.request_id,
                leaks,
            )
            return [f"{p}: {SECURITY_TOKEN_IN_RESPONSE}" for p in leaks]
        if op == "get_order" or not (res.ok and isinstance(b, dict) and "id" in b):
            return []
        if (b.get("ucp") or {}).get("status") != "success":
            return []
        name = "checkout.read_response"
        if op in ("create", "update") and f"checkout.{op}_response" in composed.names():
            name = f"checkout.{op}_response"
        return [f"{p.path}: {p.message}" for p in composed.problems(name, b)]


def _parse_time(value: str | None) -> datetime | None:
    """An RFC 3339 time, for `expires_at`. None if it is absent or not valid."""
    if not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _retry_after(value: str | None) -> float:
    try:
        return max(0.0, min(float(value or 1), MAX_RETRY_AFTER))
    except ValueError:
        return 1.0
