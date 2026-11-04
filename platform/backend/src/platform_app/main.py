"""Platform server: the Google Pay TEST smoke page (S0), discovery (S1) and checkout (S2).

The server listens on 127.0.0.1 only (DM-26). Caddy gives TLS 1.3 in front of it (T-90).
The smoke log keeps no token value. It keeps only the type, the length and the status.
S2: the checkout API for the S3 page at `/api/checkout*` and the merged timeline at
`/api/timeline` (AC-07, AC-100). The Platform signs each checkout request with its own key
(T-04). The browser never gets a key or a token.
S3: the checkout page at `/checkout/`, the review and pay API (approval gate DM-06, mapper,
approval hash), "Try again" with the same key (AC-52), and timeline events and export (AC-59).
The browser sends the Google Pay `PaymentData` to `/api/checkout/{id}/pay` once. The server
puts the token only into the Complete body and then discards it.
"""

import json
import os
import pathlib
import threading
import time
import uuid
from urllib.parse import urlsplit
from collections.abc import Callable
from typing import Any

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from ucp_core import jwk as jwkmod
from ucp_core import telemetry
from ucp_core.constants import UCP_VERSION
from ucp_core.schema_registry import SchemaRegistry

import ucp_sigs

from . import checkout_view, discovery, webhooks
from .catalog_client import CapabilityNotActive, CatalogClient
from .checkout_client import CheckoutClient, Result
from . import audit
from .pay import approval, payment_request, policy, totals_check
from .pay.instrument import InstrumentError, from_payment_data
from .pay.money import display
from .pay.redact import MASK, redact
from .timeline import EVENT_KINDS, SOURCES, Timeline

ROOT = pathlib.Path(__file__).resolve().parents[4]
WEB = ROOT / "platform" / "web" / "smoke"
DISCOVERY_WEB = ROOT / "platform" / "web" / "discovery"
CHECKOUT_WEB = ROOT / "platform" / "web" / "checkout"
PAY_JS = "https://pay.google.com/gp/p/js/pay.js"  # Google Pay Web tutorial, "Load the library"
OP_NAMES = {
    "create": "Create Checkout",
    "update": "Update Checkout",
    "get": "Get Checkout",
    "cancel": "Cancel Checkout",
    "complete": "Complete Checkout",
    "get_order": "Get Order",
    "get_business_profile": "Get Business profile (signing keys)",
    "search": "Search Catalog",
    "lookup": "Batch Lookup",
    "product": "Get Product",
}
# S7 (UX-4.2a.6): the two catalog rows sit under the group "Find product".
CATALOG_OPS = {"search": "M1a", "product": "M1b"}
HANDLER_FIXTURE = ROOT / "contracts" / "fixtures" / "gpay-handler-test.json"
LOG = pathlib.Path(os.environ.get("SMOKE_LOG", str(ROOT / ".run" / "smoke-events.jsonl")))
MODE = os.environ.get("MODE", "demo")
SAFE_KEYS = {
    "case",
    "step",
    "ok",
    "result",
    "statusCode",
    "statusMessage",
    "errorName",
    "tokenType",
    "tokenLength",
    "cardNetwork",
    "origin",
    "secureContext",
    "detail",
}

KEY_FILE = pathlib.Path(
    os.environ.get("PLATFORM_KEY_FILE", str(ROOT / ".run" / "keys" / "platform-es256.pem"))
)

app = FastAPI(title="platform", redirect_slashes=False)
_registry: list[SchemaRegistry] = []
_state: dict[str, Any] = {}
_sessions: dict[str, checkout_view.Session] = {}
_retry: dict[str, Result] = {}
_pay: dict[str, dict[str, Any]] = {}
_pay_lock = threading.Lock()


def signing_key() -> Any:
    """CI: a new ephemeral key per process. Demo: a key file under .run (not in Git)."""
    if "key" not in _state:
        _state["key"] = jwkmod.ephemeral() if MODE == "ci" else jwkmod.load_or_create(KEY_FILE)
    return _state["key"]


def public_jwk() -> dict[str, Any]:
    return jwkmod.public_jwk(signing_key())


def timeline() -> Timeline:
    if "timeline" not in _state:
        _state["timeline"] = Timeline()
    tl: Timeline = _state["timeline"]
    return tl


def client() -> CheckoutClient:
    if "client" not in _state:
        _state["client"] = CheckoutClient(
            discovery.business_origin(),
            discovery.platform_origin() + "/.well-known/ucp",
            key=signing_key(),
            kid=public_jwk()["kid"],
            verify=discovery.tls_context(),
        )
    c: CheckoutClient = _state["client"]
    return c


def catalog_client() -> CatalogClient:
    """S7: the catalog client. It sends one try for each call. The page shows 429 and 503."""
    if "catalog" not in _state:
        _state["catalog"] = CatalogClient(
            discovery.business_origin(),
            discovery.platform_origin() + "/.well-known/ucp",
            key=signing_key(),
            kid=public_jwk()["kid"],
            verify=discovery.tls_context(),
            max_tries=1,
        )
    c: CatalogClient = _state["catalog"]
    active = _state.get("active")
    if active is not None:
        c.active = frozenset(active)  # the capabilities of the last discovery (T-119)
    return c


def set_catalog_client(c: CatalogClient | None) -> None:
    """Tests: use a catalog client with a test transport."""
    _state.pop("catalog", None)
    if c is not None:
        _state["catalog"] = c


def set_client(c: CheckoutClient | None, tl: Timeline | None = None) -> None:
    """Tests: use a client with a test transport and a test timeline."""
    _state.pop("client", None)
    _state.pop("receiver", None)  # S4: a new receiver and key cache for each test stack
    _state.pop("keys", None)
    _state.pop("catalog", None)  # S7: a new catalog client and a new discovery for each stack
    _state.pop("active", None)
    _sessions.clear()
    _retry.clear()
    _pay.clear()
    if c is not None:
        _state["client"] = c
    if tl is not None:
        _state["timeline"] = tl


def set_psp_calls(fn: Callable[[str], int] | None) -> None:
    """CI test seam (UX-4.5.1, UX-AC-32). `fn(checkout_id)` gives the number of mock PSP calls.

    Only a test sets it, from Python. No route, no profile field and no config value reaches it.
    It has an effect only when MODE is "ci" (see `_same_key_note`). Demo mode ignores it.
    """
    _state.pop("psp_calls", None)
    if fn is not None:
        _state["psp_calls"] = fn


def _psp_calls_fn() -> Callable[[str], int] | None:
    """The seam function. It is None in demo mode, even if a test set it."""
    fn: Callable[[str], int] | None = _state.get("psp_calls")
    return fn if MODE == "ci" else None


def _same_key_note(res: Result, checkout_id: str, calls_before: int | None) -> bool:
    """UX-4.5.1: true only if all 3 conditions of `inspector.retry.sameKey` hold.

    (1) The Platform sent Complete again with the same `Idempotency-Key` (`res.tries` is 2 or
    more: `_send()` keeps the key and the body). (2) The body is the same (`_send()` keeps it).
    (3) Two records agree that the Business did not call the PSP again: the Business log has a
    replayed row for this `Request-Id`, and the mock PSP call count grew by one at most. CI only.
    """
    fn = _psp_calls_fn()
    if fn is None or calls_before is None or res.tries < 2 or not res.ok:
        return False
    rows = [
        r
        for r in timeline().merged()
        if r.get("side") == "business" and r.get("request_id") == res.request_id
    ]
    return len(rows) >= 2 and bool(rows[-1].get("replayed")) and fn(checkout_id) - calls_before <= 1


def set_discovery(fn: Callable[[str], dict[str, Any]] | None) -> None:
    """Tests: replace the network discovery with a function of the case name."""
    _state.pop("discover", None)
    if fn is not None:
        _state["discover"] = fn


def receiver() -> webhooks.Receiver:
    """S4: the order webhook receiver (AC-65 to AC-75)."""
    if "receiver" not in _state:
        db = os.environ.get(
            "PLATFORM_WEBHOOK_DB", str(ROOT / ".run" / "platform" / MODE / "webhooks.db")
        )

        def validate(order: Any) -> list[str]:
            return [
                f"{i.path}: {i.message}" for i in registry().validate(order, webhooks.ORDER_SCHEMA)
            ]

        _state["receiver"] = webhooks.Receiver(pathlib.Path(db), validate)
    r: webhooks.Receiver = _state["receiver"]
    return r


def set_key_resolver(fn: Callable[[str], list[dict[str, Any]]] | None) -> None:
    """Tests: replace the fetch of the signer keys (a function of the profile URL)."""
    _state.pop("keys_for", None)
    _state.pop("keys", None)
    if fn is not None:
        _state["keys_for"] = fn


def business_keys(profile_url: str) -> list[dict[str, Any]]:
    """The `signing_keys` of an allowed Business profile, with a 300 s cache."""
    fn = _state.get("keys_for")
    if fn is not None:
        keys: list[dict[str, Any]] = fn(profile_url)
        return keys
    cache: dict[str, tuple[float, list[dict[str, Any]]]] = _state.setdefault("keys", {})
    hit = cache.get(profile_url)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    if profile_url not in allowlist():
        raise ValueError("profile not in the allowlist")
    r = client().http.get(profile_url, headers={"Accept": "application/json"})
    # AC-59: each request that the Platform sends gets one timeline row.
    timeline().record(
        Result(
            op="get_business_profile",
            method="GET",
            path=urlsplit(profile_url).path,
            status=r.status_code,
            body=None,
            headers={},
            request_id=r.headers.get("request-id", ""),
            idempotency_key=None,
            tries=1,
        )
    )
    r.raise_for_status()
    keys = list((r.json() or {}).get("signing_keys") or [])
    cache[profile_url] = (time.monotonic() + 300, keys)
    return keys


def _response_signature(res: Result) -> str:
    """AC-64: check the Complete response signature. The flag off gives "not signed"."""
    if "signature" not in res.headers:
        return "not signed"
    try:
        kid = ucp_sigs.verify_response(
            int(res.status or 0), res.headers, res.raw, business_keys(business_profile_url())
        )
    except Exception as e:  # noqa: BLE001  SignatureError or a key fetch problem
        return f"invalid ({getattr(e, 'code', type(e).__name__)})"
    return f"verified keyid={kid}"


def business_profile_url() -> str:
    return discovery.business_origin() + "/.well-known/ucp"


def allowlist() -> list[str]:
    raw = os.environ.get("PLATFORM_ALLOWLIST", "")
    return [u.strip() for u in raw.split(",") if u.strip()] or [business_profile_url()]


def _inspector(res: Result) -> dict[str, Any]:
    """The inspector entry for one call. All secret values are masked (`redact.py`)."""
    headers = {"UCP-Agent": f'profile="{client().profile_url}"', "Request-Id": res.request_id}
    if res.idempotency_key is not None:
        headers["Idempotency-Key"] = res.idempotency_key
    headers["Signature-Input"] = MASK
    headers["Signature"] = MASK
    phase = "Completion" if res.op == "complete" else "Negotiation"
    if res.op in CATALOG_OPS:
        phase = "Find product"
    return {
        "name": OP_NAMES.get(res.op, res.op),
        "op": res.op,
        "mid": CATALOG_OPS.get(res.op),
        "phase": phase,
        "source": "LIVE CALL",
        "not_ucp": False,
        "method": res.method,
        "path": res.path,
        "request_id": res.request_id,
        "tries": res.tries,
        "request": {"headers": headers, "body": redact(res.request_body)},
        "response": {
            "status": res.status,
            "transport_error": res.transport_error,
            "body": redact(res.body),
        },
    }


def _view(session_key: str, res: Result) -> dict[str, Any]:
    session = _sessions.setdefault(session_key, checkout_view.Session())
    v = checkout_view.interpret(session, res)
    if res.op == "create" and res.ok and isinstance(res.body, dict) and "id" in res.body:
        # S4 (AC-69): the Business that may send order webhooks for this checkout.
        receiver().owned[str(res.body["id"])] = business_profile_url()
    timeline().record(res, v.state)
    calls = [_inspector(res)]
    if v.send_get and session.last_good is not None:
        res2 = client().get(str(session.last_good["id"]))
        v2 = checkout_view.interpret(session, res2)
        timeline().record(res2, v2.state)
        if v.state == "out_of_stock" and v2.state in ("ready_for_complete", "incomplete"):
            # AC-39: the buyer sees the out-of-stock state with its messages. The checkout is
            # the fresh one from Get Checkout. A `completed` or an error state of the Get wins.
            v.checkout = v2.checkout
        else:
            v = v2
        calls.append(_inspector(res2))
        res = res2
    if v.checkout is not None and "id" in v.checkout and session_key == "new":
        _sessions[str(v.checkout["id"])] = _sessions.pop("new")
    retry_id = None
    retryable = res.status is None or res.status in (429, 503)
    if retryable and res.op in ("create", "update"):
        _retry[res.request_id] = res  # AC-52: "Try again" sends the same request
        retry_id = res.request_id
    timeline().event("state", v.state, view_state=v.state)
    if v.problem is not None:
        timeline().event(
            "error", str(v.problem.get("kind")), status_code=str(v.problem.get("code"))
        )
    return {
        "view": asdict(v),
        "described_by": checkout_view.described_by(v),
        "messages_html": checkout_view.render_messages(v),
        "http_status": res.status,
        "inspector": calls,
        "retry_id": retry_id,
    }


def _review(checkout_id: str) -> dict[str, Any]:
    """A fresh Get, the totals check, the handler check, the gate and the approval (SC4)."""
    out = _view(checkout_id, client().get(checkout_id))
    v = out["view"]
    c = v["checkout"]
    review: dict[str, Any] = {"ok": False, "problems": [], "gate": [], "gpay": None}
    out["review"] = review
    if v["state"] != "ready_for_complete" or not isinstance(c, dict):
        review["problems"].append(f"status is {v['state']}, not ready_for_complete")
        return out
    currency = str(c.get("currency"))
    review["currency"] = currency
    review["continue_url"] = c.get("continue_url")
    review["links"] = c.get("links") or []
    review["line_items"] = [
        {
            "id": li.get("id"),
            "title": (li.get("item") or {}).get("title"),
            "quantity": li.get("quantity"),
            "total": _line_total(li, currency),
        }
        for li in c.get("line_items") or []
    ]
    problems = totals_check.check_checkout(c)
    review["totals_problems"] = problems
    review["totals"] = [
        {
            "type": e.get("type"),
            "label": totals_check.label(e),
            "amount": e.get("amount"),
            "text": _fmt(e.get("amount"), currency),
        }
        for e in c.get("totals") or []
        if isinstance(e, dict)
    ]
    if problems:  # AC-20: show the mismatch, no Google Pay button, offer continue_url
        review["problems"] += problems
        timeline().event("error", "totals_mismatch", status_code="totals_mismatch")
        return out
    total = totals_check.total_amount(c)
    review["total_text"] = _fmt(total, currency)
    handler = payment_request.pick_handler(c)
    env = ((handler or {}).get("config") or {}).get("environment")
    reasons = policy.gate(
        total=total,
        currency=currency,
        environment=env,
        business_profile_url=business_profile_url(),
        allowlist=allowlist(),
        spent_today=policy.Ledger().spent_today(),
    )
    review["gate"] = [{"code": g.code, "text": g.text} for g in reasons]
    if reasons:
        timeline().event("error", "gate_refused", status_code=reasons[0].code)
        return out
    plan = payment_request.build(registry(), handler, total, currency)
    review["gpay"] = asdict(plan)
    timeline().event(
        "mapping",
        "PaymentDataRequest built",
        phase="Acquisition",
        source="LOCAL STEP",  # AC-63: the Platform computed it, no network request
        not_ucp=True,
        result=plan.ok,
    )
    if not plan.ok:  # AC-27
        review["problems"] += plan.reasons
        return out
    try:  # S4: get the Business keys now, for the response and webhook signatures
        business_keys(business_profile_url())
    except Exception:  # noqa: BLE001  the check at use time gives the result
        pass
    h = approval.approval_hash(c, business_profile_url(), str(plan.handler_id))
    review["approval_hash"] = h
    review["ok"] = True
    with _pay_lock:
        # A fresh review keeps in_flight (AC-51) and the decline count (ST13 declined.again).
        prev = _pay.get(checkout_id, {})
        _pay[checkout_id] = {
            "hash": h,
            "handler_id": plan.handler_id,
            "used": False,
            # AC-55: what the audit record needs from the approval. No token and no continue_url.
            "audit": {
                "approval_id": str(uuid.uuid4()),
                "approval_time_utc": datetime.now(UTC).isoformat(),
                "approval_hash": h,
                "business_profile_url": business_profile_url(),
                "ucp_version": UCP_VERSION,
                "handler_version": str((handler or {}).get("version")),
                "currency": currency,
                "total_minor": total,
                "line_items_summary": [
                    {
                        "id": x["id"],
                        "title": x["title"],
                        "quantity": x["quantity"],
                        "total": x["total"],
                    }
                    for x in review["line_items"]
                ],
                "handler_id": str(plan.handler_id),
                "environment": env,
                "policy_result": "pass",
            },
        } | {k: prev[k] for k in ("in_flight", "declines") if k in prev}
    return out


def _fmt(amount: Any, currency: str) -> str | None:
    try:
        return display(int(amount), currency)
    except (TypeError, ValueError):
        return None


def _line_total(li: dict[str, Any], currency: str) -> str | None:
    for e in li.get("totals") or []:
        if isinstance(e, dict) and e.get("type") == "total":
            return _fmt(e.get("amount"), currency)
    return None


def registry() -> SchemaRegistry:
    if not _registry:
        _registry.append(SchemaRegistry.load(ROOT))
    return _registry[0]


@app.get("/.well-known/ucp")
def well_known_ucp() -> JSONResponse:
    return JSONResponse(
        discovery.platform_profile(public_jwk()), headers={"Cache-Control": "public, max-age=300"}
    )


@app.exception_handler(ValueError)
async def on_value_error(request: Request, exc: ValueError) -> JSONResponse:
    del request
    return JSONResponse({"code": "invalid_request", "content": str(exc)}, status_code=400)


@app.post("/api/checkout")
async def api_checkout_create(request: Request) -> JSONResponse:
    body: dict[str, Any] = await request.json()
    _sessions.pop("new", None)
    # The client call blocks. It runs in a worker thread, so that this server can still
    # answer the Business when it fetches /.well-known/ucp during the call.
    return JSONResponse(await run_in_threadpool(lambda: _view("new", client().create(body))))


@app.get("/api/checkout/{checkout_id}")
def api_checkout_get(checkout_id: str) -> JSONResponse:
    return JSONResponse(_view(checkout_id, client().get(checkout_id)))


@app.put("/api/checkout/{checkout_id}")
async def api_checkout_update(checkout_id: str, request: Request) -> JSONResponse:
    body: dict[str, Any] = await request.json()
    return JSONResponse(
        await run_in_threadpool(lambda: _view(checkout_id, client().update(checkout_id, body)))
    )


@app.post("/api/checkout/{checkout_id}/cancel")
def api_checkout_cancel(checkout_id: str) -> JSONResponse:
    return JSONResponse(_view(checkout_id, client().cancel(checkout_id)))


def _catalog_view(call: Callable[[CatalogClient], Result]) -> JSONResponse:
    """S7: one catalog call for the page. The answer is the body and one inspector row."""
    try:
        res = call(catalog_client())
    except CapabilityNotActive as e:  # T-119: the Platform sends nothing
        return JSONResponse(
            {"code": "capability_not_active", "content": str(e), "capability": e.capability}, 409
        )
    timeline().record(res, "catalog")
    return JSONResponse(
        {
            "http_status": res.status,
            "transport_error": res.transport_error,
            "body": redact(res.body),
            "schema_problems": len(res.schema_problems),
            "inspector": [_inspector(res)],
        }
    )


@app.post("/api/catalog/search")
async def api_catalog_search(request: Request) -> JSONResponse:
    """UX-4.2a.3 query rules: only `query` (trimmed) and, for more, `pagination.cursor`."""
    raw: dict[str, Any] = await request.json()
    query = raw.get("query")
    if not isinstance(query, str) or not query.strip():
        return JSONResponse({"code": "invalid_request", "content": "A query is required."}, 400)
    cursor = raw.get("cursor")
    page = {"cursor": cursor} if isinstance(cursor, str) and cursor else None
    return await run_in_threadpool(
        lambda: _catalog_view(lambda c: c.search(query.strip(), pagination=page))
    )


@app.post("/api/catalog/product")
async def api_catalog_product(request: Request) -> JSONResponse:
    """UX-4.2a.5: Get Product with `id` only."""
    raw: dict[str, Any] = await request.json()
    ident = raw.get("id")
    if not isinstance(ident, str) or not ident:
        return JSONResponse({"code": "invalid_request", "content": "An id is required."}, 400)
    return await run_in_threadpool(lambda: _catalog_view(lambda c: c.product(ident)))


@app.get("/api/timeline")
def api_timeline() -> JSONResponse:
    return JSONResponse({"rows": timeline().merged()})


@app.get("/api/checkout/{checkout_id}/review")
def api_checkout_review(checkout_id: str) -> JSONResponse:
    return JSONResponse(_review(checkout_id))


@app.post("/api/checkout/{checkout_id}/pay")
async def api_checkout_pay(checkout_id: str, request: Request) -> JSONResponse:
    body: dict[str, Any] = await request.json()
    return await run_in_threadpool(lambda: _pay_now(checkout_id, body))


def _pay_now(checkout_id: str, body: dict[str, Any]) -> JSONResponse:
    """Complete once after the buyer approved in Google Pay (AC-22, AC-51, AC-98, AC-111)."""
    with _pay_lock:
        entry = _pay.get(checkout_id)
        if entry is None:
            return JSONResponse({"code": "no_approval", "content": "No review."}, 409)
        if entry.get("in_flight"):  # AC-51: no second Complete
            timeline().event("buyer_action", "pay again (refused)", status_code="in_flight")
            return JSONResponse(
                {"code": "complete_in_flight", "content": "A Complete is in flight."}, 409
            )
        if entry.get("used"):
            return JSONResponse({"code": "approval_used", "content": "Approval used."}, 409)
        entry["in_flight"] = True
    payment_data = body.pop("payment_data", None)
    # AC-55: one audit record when the attempt ends. `att` has no token.
    att: dict[str, Any] = {"id": audit.new_attempt_id(), "final": None}
    try:
        if body.get("approval_hash") != entry["hash"]:
            return JSONResponse({"code": "approval_unknown", "content": "Bad approval."}, 409)
        fresh = _review(checkout_id)  # AC-22: a fresh Get before Complete
        if fresh["review"].get("approval_hash") != entry["hash"] or not fresh["review"]["ok"]:
            payment_data = None  # discard the token
            att["final"] = "approval_changed"
            timeline().event("error", "approval_changed", status_code="approval_changed")
            return JSONResponse({"outcome": "changed"} | fresh)
        try:
            inst = from_payment_data(registry(), payment_data, str(entry["handler_id"]))
        except InstrumentError as e:
            payment_data = None
            att["final"] = "instrument_invalid"
            timeline().event(
                "mapping",
                "M7 instrument",
                phase="Acquisition",
                source="LOCAL STEP",
                not_ucp=True,
                result="invalid",
            )
            return JSONResponse({"code": "instrument_invalid", "content": str(e)}, 400)
        # M7 (AC-63): PaymentMethodData to card_payment_instrument. The token is masked.
        m7 = {
            "input": redact((payment_data or {}).get("paymentMethodData")),
            "output": redact(inst),
        }
        timeline().event(
            "mapping",
            "M7 instrument",
            phase="Acquisition",
            source="LOCAL STEP",
            not_ucp=True,
            result="built",
        )
        payment_data = None
        att["instrument"] = {"id": inst.get("id"), "display": inst.get("display")}
        att["final"] = "transport_error"
        with _pay_lock:
            _pay[checkout_id]["used"] = True
            _pay[checkout_id]["in_flight"] = True
        psp_fn = _psp_calls_fn()
        calls_before = psp_fn(checkout_id) if psp_fn is not None else None
        known = (_sessions.get(checkout_id) or checkout_view.Session()).last_good or {}
        res = client().complete(
            checkout_id, {"payment": {"instruments": [inst]}}, known.get("expires_at")
        )
        inst = {}
        same_key = _same_key_note(res, checkout_id, calls_before)
        for earlier in res.earlier:  # AC-44: a Complete with no response, then Get calls
            timeline().record(earlier, "complete_recovery")
        out = _view(checkout_id, res)
        at = len(res.earlier)  # the entry of the final response
        out["inspector"] = [_inspector(earlier) for earlier in res.earlier] + out["inspector"]
        if same_key:  # UX-4.5.1: CI only. The page shows `inspector.retry.sameKey`.
            out["inspector"][at]["same_key"] = True
        out["response_signature"] = _response_signature(res)  # AC-64
        out["inspector"][at]["response"]["signature"] = out["response_signature"]
        res.request_body = None  # discard the token from memory
        c = out["view"]["checkout"]
        att["key"] = res.idempotency_key
        att["checkout"] = c if isinstance(c, dict) else None
        att["final"] = str(c.get("status")) if isinstance(c, dict) and c.get("status") else "error"
        m9: dict[str, Any] | None = None
        if res.ok and isinstance(c, dict) and c.get("status") == "completed":
            policy.Ledger().add(checkout_id, totals_check.total_amount(c), str(c["currency"]))
            m9 = {"result": "approved"}
        elif res.ok and isinstance(c, dict) and _payment_failed(c):
            # T-105 (AC-34, AC-35): no order and no ledger entry. The approval opens again,
            # so a new click gives a new token, a new body and a new Idempotency-Key.
            with _pay_lock:
                _pay[checkout_id]["used"] = False
                _pay[checkout_id]["declines"] = int(_pay[checkout_id].get("declines", 0)) + 1
                declines = _pay[checkout_id]["declines"]
            timeline().event("state", "payment_failed", status_code="payment_failed")
            m9 = {"result": "declined", "declines": declines}
        # M9 (UX-4.4, section 15.5): the Platform does not see M9. The row tells what the
        # M10 response shows about the simulated processor result.
        return JSONResponse({"outcome": "sent", "m7": m7, "m9": m9} | out)
    finally:
        if att["final"] is not None:
            audit.write(
                audit.build(
                    attempt_id=att["id"],
                    approval=entry["audit"],
                    checkout_id=checkout_id,
                    instrument=att.get("instrument"),
                    idempotency_key=att.get("key"),
                    final_status=att["final"],
                    checkout=att.get("checkout"),
                )
            )
        with _pay_lock:
            if checkout_id in _pay:
                _pay[checkout_id]["in_flight"] = False


def _payment_failed(c: dict[str, Any]) -> bool:
    """T-105: status stays ready_for_complete and a payment_failed error message is there."""
    if c.get("status") != "ready_for_complete":
        return False
    return any(
        isinstance(m, dict) and m.get("type") == "error" and m.get("code") == "payment_failed"
        for m in c.get("messages") or []
    )


@app.post("/webhooks/ucp/orders")
async def webhook_orders(request: Request) -> JSONResponse:
    """S4: order event webhooks (order.md "Events"). See `webhooks.py`."""
    body = await request.body()
    headers = dict(request.headers)
    out = await run_in_threadpool(
        lambda: receiver().receive(
            headers.get("host", ""),
            request.url.path,
            headers,
            body,
            allowlist(),
            business_keys,
        )
    )
    event = headers.get("x-event-type") or "order event"
    timeline().event(
        "request",
        f"M11 Order webhook {event}",
        phase="Post-purchase",
        source="SIMULATED",  # T-23: all order events are simulated
        result=out.applied,
        status_code=str(out.status),
    )
    retry = {"Retry-After": "1"} if out.status == 503 else None
    return JSONResponse(out.body(), status_code=out.status, headers=retry)


@app.get("/api/orders/{order_id}")
def api_order(order_id: str) -> JSONResponse:
    """T-69: the order state and the webhook rows for the UI (a server feed)."""
    v = receiver().view(order_id)
    if v is None:
        return JSONResponse({"code": "not_found", "content": "No webhook for this order yet."}, 404)
    return JSONResponse(v)


@app.post("/api/orders/{order_id}/reconcile")
def api_order_reconcile(order_id: str) -> JSONResponse:
    """AC-73 (T-43): Get Order, then compare its state with the state from the webhooks."""
    res = client().get_order(order_id)
    timeline().record(res)
    body = res.body if isinstance(res.body, dict) else {}
    get_state = webhooks.order_state(body) if res.ok and "id" in body else None
    v = receiver().view(order_id)
    hook_state = v["state"] if v else None
    return JSONResponse(
        {
            "order_id": order_id,
            "get_state": get_state,
            "webhook_state": hook_state,
            "match": get_state is not None and get_state == hook_state,
            "inspector": [_inspector(res)],
        }
    )


@app.post("/api/retry/{request_id}")
async def api_retry(request_id: str) -> JSONResponse:
    res = _retry.pop(request_id, None)
    if res is None:
        return JSONResponse({"code": "not_found", "content": "No request to send again."}, 404)
    key = "new" if res.op == "create" else res.path.split("/")[2]
    if res.op == "create":
        _sessions.setdefault("new", checkout_view.Session())
    return JSONResponse(await run_in_threadpool(lambda: _view(key, client().resend(res))))


@app.post("/api/timeline/event")
async def api_timeline_event(request: Request) -> JSONResponse:
    raw: dict[str, Any] = await request.json()
    kind, source = raw.get("kind"), raw.get("source", "LIVE CALL")
    if kind not in EVENT_KINDS or source not in SOURCES:
        return JSONResponse({"code": "invalid_request", "content": "bad kind or source"}, 400)
    result = raw.get("result")
    if result is not None and not isinstance(result, (bool, int, str)):
        result = None
    row = timeline().event(
        str(kind),
        str(raw.get("name", "")),
        phase=raw.get("phase") if isinstance(raw.get("phase"), str) else None,
        source=str(source),
        not_ucp=bool(raw.get("not_ucp")),
        result=result,
        status_code=raw.get("status_code") if isinstance(raw.get("status_code"), str) else None,
    )
    return JSONResponse({"ok": True, "row": row})


@app.get("/api/timeline/export")
def api_timeline_export() -> Response:
    data = json.dumps({"rows": timeline().merged()}, indent=2, sort_keys=True)
    return Response(
        data,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="ucp-demo-timeline.json"'},
    )


@app.get("/checkout/")
def checkout_page() -> FileResponse:
    return FileResponse(CHECKOUT_WEB / "index.html", media_type="text/html")


@app.get("/checkout/app.js")
def checkout_js() -> FileResponse:
    return FileResponse(CHECKOUT_WEB / "app.js", media_type="text/javascript")


@app.get("/checkout/app.css")
def checkout_css() -> FileResponse:
    return FileResponse(CHECKOUT_WEB / "app.css", media_type="text/css")


@app.get("/checkout/config.json")
def checkout_config() -> JSONResponse:
    ci = MODE == "ci"
    return JSONResponse(
        {
            "mode": MODE,
            "gpay": "stub" if ci else "pay.js",
            "gpay_script": "/checkout/gpay-stub.js" if ci else PAY_JS,
            "auto_ms": 3000,
            "catalog_ms": 10000,  # AC-130: the page waits 10 s for a catalog answer
        }
    )


@app.get("/checkout/gpay-stub.js")
def checkout_gpay_stub() -> Response:
    if MODE != "ci":  # the stub is for CI only (04-build-plan S3)
        return JSONResponse({"code": "not_found", "content": "CI only"}, 404)
    return FileResponse(CHECKOUT_WEB / "gpay-stub.js", media_type="text/javascript")


@app.get("/api/discovery")
def api_discovery(case: str = "live") -> JSONResponse:
    fn = _state.get("discover")
    rep = fn(case) if fn is not None else discovery.discover(registry(), case=case)
    if rep.get("ok"):
        _state["active"] = list(rep.get("active", []))  # S7: the catalog client reads it (T-119)
    timeline().event("request", f"Discovery ({case})", phase="Negotiation", result=rep.get("ok"))
    return JSONResponse(rep)


@app.get("/discovery/")
def discovery_page() -> FileResponse:
    return FileResponse(DISCOVERY_WEB / "index.html", media_type="text/html")


@app.get("/livez")
def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ok", "mode": MODE}


@app.get("/smoke/")
def smoke_page() -> FileResponse:
    return FileResponse(WEB / "index.html", media_type="text/html")


@app.get("/smoke/smoke.js")
def smoke_js() -> FileResponse:
    return FileResponse(WEB / "smoke.js", media_type="text/javascript")


@app.get("/smoke/handler-config.json")
def handler_config() -> JSONResponse:
    handler = json.loads(HANDLER_FIXTURE.read_text())
    if handler["config"]["environment"] != "TEST":  # NFR-03: refuse any value other than TEST
        return JSONResponse({"error": "environment must be TEST"}, status_code=500)
    return JSONResponse(handler)


@app.post("/smoke/event")
async def smoke_event(request: Request) -> dict[str, bool]:
    raw: dict[str, Any] = await request.json()
    row = {k: v for k, v in raw.items() if k in SAFE_KEYS}  # drop all other keys (no token)
    row["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return {"ok": True}


telemetry.configure_logging()
telemetry.instrument_fastapi(app, "platform")  # off unless OTEL_EXPORTER_OTLP_ENDPOINT is set
