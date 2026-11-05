"""Business order events for S4 (AC-65, AC-72, AC-74, AC-75, T-23, T-32, T-42).

- `ObservedTransport` wraps the webhook transport of the sample (`config.WEBHOOK_TRANSPORT`).
  It writes one timeline row for each delivery attempt, with the Webhook-Id and the attempt
  number. It sends only to a loopback host (DM-26). The row has no header value and no body.
- `dead_letter` is the sample hook `config.WEBHOOK_DEAD_LETTER` (patch P16). It writes the
  failed event to the dead-letter file after the last attempt or after a 4xx (T-42).
- `after_complete` runs after the Complete response is sent. It writes the confirmation
  e-mail to a log (AC-75). Then it simulates the shipped and delivered events (AC-74). All
  order events in this demo are simulated (T-23).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx2
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from ucp_core import telemetry, tlsctx

from . import events, store

log = logging.getLogger("business.order_events")
LOOPBACK_HOSTS = {"localhost", "127.0.0.1"}
SUITE_WEBHOOK_PATH = "/webhooks/partners/test_partner/events/order"  # suite 016ecbc, line 12
_lock = threading.Lock()


def _jsonl(name: str) -> pathlib.Path:
    d = pathlib.Path(os.environ.get("BUSINESS_DATA_DIR") or store.data_dir(_mode()))
    return d / name


def _mode() -> str:
    from ucp_core.constants import mode

    return mode()


def _append(path: pathlib.Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **row}
    with _lock, path.open("a") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def outbox_file() -> pathlib.Path:
    return pathlib.Path(os.environ.get("BUSINESS_OUTBOX", str(_jsonl("outbox.jsonl"))))


def dead_letter_file() -> pathlib.Path:
    return pathlib.Path(
        os.environ.get("BUSINESS_DEAD_LETTER", str(_jsonl("webhook-dead-letter.jsonl")))
    )


def suite_webhook_url_ok(url: httpx2.URL, port: int) -> bool:
    """T-115 item 3: the exact suite webhook URL.

    Scheme `http`, host `localhost`, the configured port, the one path, no query, no fragment,
    no credentials. `127.0.0.1` does not match.
    """
    return (
        url.scheme == "http"
        and url.host == "localhost"
        and url.port == port
        and url.path == SUITE_WEBHOOK_PATH
        and not url.query
        and not url.fragment
        and not url.userinfo
    )


class ObservedTransport(httpx2.AsyncBaseTransport):
    """Log each webhook attempt (AC-72).

    Refuse a host that is not loopback (DM-26). Refuse a URL with scheme `http` (T-115), with
    one exception: in `mode="ci"`, with `suite_webhook_port` set, and while `ci_guard()` is true
    (the T-109 namespace), the exact suite webhook URL passes.
    """

    def __init__(
        self,
        inner: httpx2.AsyncBaseTransport | None = None,
        *,
        mode: str = "demo",
        suite_webhook_port: int | None = None,
        ci_guard: Callable[[], bool] = lambda: False,
    ):
        self.inner = inner or httpx2.AsyncHTTPTransport(verify=tlsctx.client_context())
        self.attempts: dict[str, int] = {}
        self.mode = mode
        self.suite_webhook_port = suite_webhook_port
        self.ci_guard = ci_guard

    def _http_allowed(self, url: httpx2.URL) -> bool:
        return (
            self.mode == "ci"
            and self.suite_webhook_port is not None
            and self.ci_guard()  # checked before each use (T-114 clause 2, T-115 clause 4)
            and suite_webhook_url_ok(url, self.suite_webhook_port)
        )

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        """One CLIENT span for each attempt (AC-66, AC-72). The span has no header and no body."""
        prov = telemetry.provider("business")
        if prov is None:
            return await self._attempt(request)
        tracer = prov.get_tracer("business_app.order_events")
        with tracer.start_as_current_span(
            "POST order webhook",
            kind=SpanKind.CLIENT,
            attributes={
                "http.request.method": "POST",
                "url.path": request.url.path,
                "ucp.webhook.event_type": request.headers.get("x-event-type", ""),
            },
        ) as span:
            propagate.inject(request.headers)  # `traceparent`; the signature does not cover it
            try:
                resp = await self._attempt(request, span)
            except httpx2.HTTPError as e:
                span.set_status(Status(StatusCode.ERROR, type(e).__name__))
                raise
            span.set_attribute("http.response.status_code", resp.status_code)
            if resp.status_code >= 400:
                span.set_status(Status(StatusCode.ERROR))
            return resp

    async def _attempt(
        self, request: httpx2.Request, span: trace.Span | None = None
    ) -> httpx2.Response:
        wid = request.headers.get("webhook-id", "")
        n = self.attempts.get(wid, 0) + 1
        self.attempts[wid] = n
        if span is not None:
            span.set_attribute("ucp.webhook.attempt", n)
        row: dict[str, Any] = {
            "method": "POST",
            "path": request.url.path,
            "webhook_id": wid,
            "event_type": request.headers.get("x-event-type"),
            "attempt": n,
            "note": "webhook delivery",
        }
        if request.url.host not in LOOPBACK_HOSTS:
            row["code"] = "blocked_non_loopback"
            events.write(row)
            raise httpx2.ConnectError("webhook host is not loopback (DM-26)", request=request)
        if request.url.scheme != "https" and not self._http_allowed(request.url):
            row["code"] = "blocked_non_https"
            events.write(row)
            raise httpx2.ConnectError("webhook URL is not https (T-115)", request=request)
        try:
            resp = await self.inner.handle_async_request(request)
        except httpx2.HTTPError as e:
            row["code"] = type(e).__name__
            events.write(row)
            raise
        row["status"] = resp.status_code
        events.write(row)
        return resp


def dead_letter(event_type: str, webhook_id: str, failure: str) -> None:
    row = {"event_type": event_type, "webhook_id": webhook_id, "failure": failure}
    _append(dead_letter_file(), row)
    events.write(
        {
            "webhook_id": webhook_id,
            "event_type": event_type,
            "dead_letter": True,
            "note": f"dead letter: {failure}",
        }
    )


def write_confirmation_email(order: dict[str, Any], checkout: dict[str, Any]) -> None:
    """AC-75: the demo sends no e-mail. It writes the message to the outbox log."""
    buyer = checkout.get("buyer") or {}
    _append(
        outbox_file(),
        {
            "to": buyer.get("email"),
            "subject": "Order confirmed (demo, simulated)",
            "order_id": order.get("id"),
            "permalink_url": order.get("permalink_url"),
            "sent": False,
            "note": "Demo only. No e-mail leaves the computer.",
        },
    )


async def simulate_fulfilment(order_id: str, base_url: str, delay: float) -> None:
    """AC-74: simulated shipped, then delivered. Each step sends a signed webhook."""
    import db as sample_db  # vendored sample module
    from services.checkout_service import CheckoutService
    from services.fulfillment_service import FulfillmentService

    for step in ("ship_order", "deliver_order"):
        if delay:
            await asyncio.sleep(delay)
        ps = sample_db.manager.products_session_factory
        ts = sample_db.manager.transactions_session_factory
        if ps is None or ts is None:
            return
        async with ps() as p, ts() as t:
            svc = CheckoutService(FulfillmentService(), p, t, base_url)
            await getattr(svc, step)(order_id)


def make_after_complete(base_url: str, simulate: bool, delay: float) -> Any:
    async def after_complete(body: dict[str, Any]) -> None:
        order = body.get("order") or {}
        order_id = order.get("id")
        if not order_id:
            return
        try:
            write_confirmation_email(order, body)
            if simulate:
                await simulate_fulfilment(str(order_id), base_url, delay)
        except Exception as e:  # noqa: BLE001  the simulation never breaks the checkout
            log.warning("order event simulation failed: %s", type(e).__name__)

    return after_complete
