"""The Business payment hook for `com.google.pay` (S4, patch D6 and P15, FR-11).

The vendored sample calls `config.PAYMENT_AUTHORIZER(handler_id, credential, checkout)`.
This hook sends the token to the mock PSP on 127.0.0.1 (DM-26) and maps the result:

- approved: return (the sample makes the order).
- declined: raise `PaymentFailedError`. The sample sends the T-105 response. The PSP reason
  goes to the log only, never into the response `content`.
- PSP not reachable: HTTP 503 `psp_unavailable` with `Retry-After` (T-102). No order.

The hook never logs the token (AC-54, AC-97). The checkout `id` is the PSP idempotency key
(02-design 14.1, T-31).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

import sys

import httpx

from . import store

if str(store.SAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(store.SAMPLE_DIR))

from exceptions import PaymentFailedError, UcpError  # noqa: E402  (vendored sample module)
from ucp_core import telemetry  # noqa: E402

log = logging.getLogger("business.psp")


def _total(checkout: Any) -> tuple[int | None, str]:
    amount = None
    for t in getattr(checkout, "totals", None) or []:
        if getattr(t, "type", None) == "total":
            amount = getattr(t, "amount", None)
    return amount, str(getattr(checkout, "currency", "") or "")


def make_authorizer(
    base_url: str | None = None, transport: httpx.BaseTransport | None = None
) -> Callable[[str, Any, Any], None]:
    url = (base_url or os.environ.get("PSP_MOCK_URL") or _default_url()).rstrip("/")

    def authorize(handler_id: str, credential: Any, checkout: Any) -> None:
        token = credential.get("token") if isinstance(credential, dict) else None
        if token is None:
            token = getattr(credential, "token", None)
        amount, currency = _total(checkout)
        body = {
            "handler_id": handler_id,
            "idempotency_key": str(getattr(checkout, "id", "")),
            "amount": amount,
            "currency": currency,
            "token": token,
        }
        try:
            with httpx.Client(transport=transport, timeout=5.0) as c:
                telemetry.instrument_client(c, "business")
                r = c.post(url + "/charges", json=body)
        except httpx.HTTPError as e:
            log.warning("psp not reachable: %s", type(e).__name__)
            raise UcpError(
                "The payment processor is not available.", "psp_unavailable", 503
            ) from None
        finally:
            body.clear()
            token = None
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        status = data.get("status") if isinstance(data, dict) else None
        log.info(
            "psp result %s charge=%s", status, data.get("id") if isinstance(data, dict) else None
        )
        if status == "approved":
            return
        if status == "declined":
            # The PSP reason stays in the log (T-105 item 4: not in `content`).
            log.info("psp decline reason %s", data.get("reason"))
            raise PaymentFailedError("The payment was declined.")
        raise UcpError("The payment processor gave no result.", "psp_unavailable", 503)

    return authorize


def _default_url() -> str:
    host = os.environ.get("LOOPBACK_HOST", "127.0.0.1")
    port = os.environ.get("PSP_MOCK_APP_PORT", "8301")
    return f"http://{host}:{port}"
