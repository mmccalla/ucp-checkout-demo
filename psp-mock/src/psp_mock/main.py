"""Mock PSP (S4). It moves no money. Each result is "Simulated payment".

- It binds 127.0.0.1 only (DM-26), port PSP_MOCK_APP_PORT (8301). Only the Business calls it.
- AC-97 and 02-design 16.3: it does not log, keep or decrypt the token. It checks only that a
  token is present. A charge record has no token and no card data.
- 02-design 14.1 (T-31): the Business sends the checkout `id` as the idempotency key. After an
  approved charge, the same checkout id gets the same approval and no second charge. A decline
  does not block a later attempt (AC-35: a retry has a new token).
- The outcome (`approve` or `decline`) comes from the SC7 outcome selector or CI (T-73, UX Q4):
  `PUT /outcome`. The default is `approve`.

Run: `uvicorn --factory psp_mock.main:create_app --host 127.0.0.1 --port 8301`.
"""

from __future__ import annotations

import datetime
import logging
import threading
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from ucp_core import telemetry

OUTCOMES = ("approve", "decline")
log = logging.getLogger("psp_mock")


class Store:
    """In-memory charge records. No token, no card data (AC-97)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.outcome = "approve"
        self.attempts: list[dict[str, Any]] = []
        self.approved: dict[str, dict[str, Any]] = {}
        # Each valid POST /charges, also one that gets a stored approval (CI seam).
        self.calls: dict[str, int] = {}

    def charge(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        checkout_id = body.get("idempotency_key")
        has_token = isinstance(body.get("token"), str) and bool(body.get("token"))
        if not isinstance(checkout_id, str) or not checkout_id or not has_token:
            return 400, {"status": "error", "code": "invalid_request"}
        with self.lock:
            self.calls[checkout_id] = self.calls.get(checkout_id, 0) + 1
            if checkout_id in self.approved:  # one charge for each checkout (T-31)
                return 200, self.approved[checkout_id] | {"replayed": True}
            status = "approved" if self.outcome == "approve" else "declined"
            rec = {
                "id": f"TEST-auth-{uuid.uuid4()}",
                "status": status,
                "simulated": True,
                "idempotency_key": checkout_id,
                "handler_id": str(body.get("handler_id", "")),
                "amount": body.get("amount") if isinstance(body.get("amount"), int) else None,
                "currency": str(body.get("currency", "")),
                "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
            }
            if status == "declined":
                rec["reason"] = "simulated_decline"
            self.attempts.append(rec)
            if status == "approved":
                self.approved[checkout_id] = rec
        # Log line with no token (AC-97, AC-54).
        log.info("charge %s %s checkout=%s", rec["id"], status, checkout_id)
        return 200, rec


def create_app(store: Store | None = None) -> FastAPI:
    telemetry.configure_logging()
    app = FastAPI(
        title="psp-mock", redirect_slashes=False, docs_url=None, redoc_url=None, openapi_url=None
    )
    st = store or Store()
    app.state.store = st

    @app.get("/livez")
    def livez() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ok", "outcome": st.outcome}

    @app.post("/charges")
    async def charges(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return JSONResponse({"status": "error", "code": "invalid_request"}, 400)
        status, out = st.charge(body)
        body.clear()  # the token leaves memory with the request (02-design 16.3)
        return JSONResponse(out, status)

    @app.put("/outcome")
    async def set_outcome(request: Request) -> JSONResponse:
        body = await request.json()
        outcome = body.get("outcome") if isinstance(body, dict) else None
        if outcome not in OUTCOMES:
            return JSONResponse({"code": "invalid_request", "content": "approve or decline"}, 400)
        st.outcome = str(outcome)
        return JSONResponse({"outcome": st.outcome})

    @app.get("/charges")
    def list_charges() -> dict[str, Any]:
        """For tests and the audit view: the charge records (no token)."""
        with st.lock:
            return {
                "attempts": list(st.attempts),
                "approved_count": len(st.approved),
                "attempt_count": len(st.attempts),
            }

    telemetry.instrument_fastapi(app, "psp-mock")
    return app
