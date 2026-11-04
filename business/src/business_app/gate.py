"""Request gate in front of the vendored sample routes (S2, ADR 0006).

The gate runs for each `/checkout-sessions` request, in this order:

1. CI fault hooks (spec 4.1): 429 or 503 with `Retry-After` (AC-50). Only in MODE=ci.
2. `UCP-Agent` and the platform profile (AC-11, AC-108): 400 `invalid_profile_url`,
   424 `profile_unreachable`, 422 `profile_malformed`.
3. Protocol version (AC-95): 422 `version_unsupported` if the profile `ucp.version` is not
   the Business version (overview.md lines 2193-2205, no `supported_versions`).
4. RFC 9421 request signature with the keys of that profile (T-04). 401 or 400 with the
   pinned codes. Enforcement follows `--require_signatures` (default on, patch P3).
5. `Idempotency-Key` on POST and PUT (T-31, AC-48): HTTP 400 `error_response`.
6. Idempotency store probe (AC-47): 503 `Retry-After`.
7. Body validation against the composed schema (AC-89, AC-94, AC-104): HTTP 400
   `error_response` with code `invalid_request`. Unknown root fields pass and are logged
   (AC-38, T-86).

S4 additions:

- `GET /orders/{id}` (order.md "Get Order"): steps 2 to 4, then the owner check. A platform
  reads only the orders that it originated (order.md, Authorization). Else the response is
  `error_response` with code `unauthorized`, as in the order.md example.
- Complete response signature (AC-64, signatures.md "REST Response Signing"): with
  enforcement on, the gate signs the Complete response with `@status`. With enforcement off,
  the response is not signed.
- After a new completed order, the gate records the owner and calls `after_complete` after
  the response is sent (AC-74, AC-75).

S7 additions: `POST /catalog/search`, `/catalog/lookup` and `/catalog/product` (catalog/rest.md
lines 64-66). The gate runs steps 1 to 3 and a signature check only if the request has
signature headers. The catalog operations need `UCP-Agent` and `Request-Id`. They have no
`Idempotency-Key` (rest.openapi.json lines 564-720, 863 and 882, UCP commit 9c9d6fc) and no
required signature (AC-12.1). The catalog route validates the body.

No step changes state before the sample route runs. Each request writes one timeline row with
its `Request-Id` (AC-100). The row has no header value and no body.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any

from starlette.responses import Response
from ucp_core import composed, telemetry
from ucp_core.constants import GPAY_INSTRUMENT_SCHEMA, UCP_VERSION
from ucp_core.schema_registry import SchemaRegistry

from . import errors, events, store
from .platform_profiles import ProfileProblem, Resolver

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
Verifier = Callable[[str, str, str, str, dict[str, str], bytes, list[dict[str, Any]]], str]

CHECKOUT = re.compile(r"^/checkout-sessions(?:/(?P<id>[^/]+)(?P<rest>/[a-z_]+)?)?$")
ORDER = re.compile(r"^/orders/(?P<id>[^/]+)$")
CATALOG = re.compile(r"^/catalog/(?:search|lookup|product)$")  # S7 (rest.md:64-66)
PROFILE_RE = re.compile(r'profile="([^"]+)"')
MOCK_HANDLER_ID = "mock_payment_handler"  # T-93, T-111


class SignatureProblem(Exception):
    def __init__(self, status: int, code: str, content: str):
        super().__init__(content)
        self.status, self.code, self.content = status, code, content


@dataclass
class GateConfig:
    resolver: Resolver
    transactions_db: str
    verify: Verifier | None
    require_signatures: bool
    mode: str
    faults: dict[str, int] = field(default_factory=dict)
    root_fields: frozenset[str] = frozenset()
    sign_key: Any = None
    sign_kid: str = ""
    after_complete: Callable[[dict[str, Any]], Awaitable[None]] | None = None
    registry: SchemaRegistry | None = None
    ci_mock_instrument_schema: dict[str, Any] | None = None  # MODE=ci only (T-111)
    # AC-45 (spec 4.1, CI only): checkout id -> number of Get Checkout calls that still show
    # `complete_in_progress`. The stored checkout is `completed`. The PSP got one charge.
    in_progress: dict[str, int] = field(default_factory=dict)


def _schema_for(method: str, m: re.Match[str]) -> str | None:
    if method == "POST" and m.group("id") is None:
        return "checkout.create_request"
    if method == "PUT" and m.group("id") and not m.group("rest"):
        return "checkout.update_request"
    return None


class Gate:
    def __init__(self, app: ASGIApp, cfg: GateConfig):
        self.app, self.cfg = app, cfg

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        m = CHECKOUT.match(path) or ORDER.match(path) or CATALOG.match(path)
        if not m:
            await self.app(scope, receive, send)
            return
        body = b""
        more = True
        while more:
            msg = await receive()
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        row: dict[str, Any] = {
            "request_id": headers.get("request-id"),
            "method": scope["method"],
            "path": scope["path"],
            "idempotency_key_present": "idempotency-key" in headers,
        }
        early = self._check(scope, m, headers, body, row)
        if early is not None:
            row["status"] = early.status_code
            row["code"] = _code_of(early)
            events.write(row)
            await early(scope, _replay(body), send)
            return
        if m.re is CHECKOUT and m.group("rest") == "/complete" and scope["method"] == "POST":
            fixed = self._check_instruments(body, row, headers)
            if isinstance(fixed, Response):
                row["status"] = fixed.status_code
                row["code"] = _code_of(fixed)
                events.write(row)
                await fixed(scope, _replay(body), send)
                return
            body = fixed
        key = headers.get("idempotency-key")
        replay = bool(key) and store.has_key(self.cfg.transactions_db, key or "")
        if key:  # AC-42: the server span says if the key had a stored response
            telemetry.set_attribute("ucp.idempotency.replayed", replay)
        status_box: dict[str, int] = {}
        is_complete = m.re is CHECKOUT and m.group("rest") == "/complete"
        pending_get = (
            m.re is CHECKOUT
            and scope["method"] == "GET"
            and not m.group("rest")
            and self.cfg.mode == "ci"
            and self.cfg.in_progress.get(m.group("id") or "", 0) > 0
        )
        buffered: list[Message] = []

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_box["status"] = message["status"]
                rid = headers.get("request-id")
                if rid:
                    message.setdefault("headers", [])
                    message["headers"] = list(message["headers"]) + [
                        (b"request-id", rid.encode("latin-1"))
                    ]
            if is_complete or pending_get:
                buffered.append(message)  # sent below, after the response signature
                return
            await send(message)

        await self.app(scope, _replay(body), send_wrapper)
        row["status"] = status_box.get("status")
        if replay and row["status"] is not None and row["status"] < 300:
            row["replayed"] = True  # span attribute ucp.idempotency.replayed=true (AC-42)
        if is_complete or pending_get:
            data = await self._send_complete(buffered, send, row, show_in_progress=pending_get, m=m)
            events.write(row)
            await self._after_complete(data, headers, replay)
            return
        events.write(row)

    def _in_progress_view(self, raw: bytes, m: re.Match[str], is_get: bool) -> bytes:
        """AC-45 test switch (spec 4.1). Show `complete_in_progress` without an `order`.

        `BUSINESS_FAULTS=complete_in_progress=N,in_progress_gets=K`: the first N Complete calls
        (after a real, one-time charge) answer `complete_in_progress`. The next K Get Checkout
        calls for that checkout answer the same. Then Get shows the stored `completed` state.
        """
        cfg = self.cfg
        try:
            data = json.loads(raw)
        except ValueError:
            return raw
        if not isinstance(data, dict) or data.get("status") != "completed":
            return raw
        cid = str(data.get("id"))
        if is_get:
            cfg.in_progress[cid] -= 1
        else:
            cfg.faults["complete_in_progress"] -= 1
            cfg.in_progress[cid] = cfg.faults.get("in_progress_gets", 1)
        data["status"] = "complete_in_progress"
        data.pop("order", None)
        return json.dumps(data, separators=(",", ":")).encode()

    async def _send_complete(
        self,
        buffered: list[Message],
        send: Send,
        row: dict[str, Any],
        show_in_progress: bool = False,
        m: re.Match[str] | None = None,
    ) -> dict[str, Any] | None:
        start = next((x for x in buffered if x["type"] == "http.response.start"), None)
        raw = b"".join(x.get("body", b"") for x in buffered if x["type"] == "http.response.body")
        if start is None:
            return None
        cfg = self.cfg
        real: bytes | None = None
        if (
            m is not None
            and cfg.mode == "ci"
            and start["status"] == 200
            and (
                show_in_progress
                or (cfg.faults.get("complete_in_progress", 0) > 0 and "replayed" not in row)
            )
        ):
            real = raw  # the order events follow the real (completed) state
            raw = self._in_progress_view(raw, m, show_in_progress)
        hdrs = [(k, v) for k, v in start.get("headers", []) if k.lower() != b"content-length"]
        if cfg.require_signatures and cfg.sign_key is not None:
            import ucp_sigs

            plain = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in hdrs}
            add = ucp_sigs.sign_response(cfg.sign_key, cfg.sign_kid, start["status"], plain, raw)
            hdrs = [(k, v) for k, v in hdrs if k.decode("latin-1").lower() not in add]
            hdrs += [(k.encode("latin-1"), v.encode("latin-1")) for k, v in add.items()]
            row["note"] = f"response signed keyid={cfg.sign_kid}"
        else:
            row["note"] = "response not signed (enforcement off)"
        hdrs.append((b"content-length", str(len(raw)).encode()))
        await send({"type": "http.response.start", "status": start["status"], "headers": hdrs})
        await send({"type": "http.response.body", "body": raw, "more_body": False})
        try:
            data = json.loads(real if real is not None else raw)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    async def _after_complete(
        self, data: dict[str, Any] | None, headers: dict[str, str], replay: bool
    ) -> None:
        if not data or replay or data.get("status") != "completed":
            return
        order_id = (data.get("order") or {}).get("id")
        pm = PROFILE_RE.search(headers.get("ucp-agent", ""))
        if not order_id or not pm:
            return
        # S6 (G8). The store calls are sync SQLite calls. They run in a thread. On the event loop
        # a write wait blocked the loop while the next request of the client held the write lock
        # of the shared session: a deadlock until the 1 s busy timeout, then HTTP 502 at the proxy.
        owner = await asyncio.to_thread(store.order_owner, self.cfg.transactions_db, str(order_id))
        if owner is not None:
            return  # a second Complete gave the same order: no second event
        await asyncio.to_thread(
            store.set_order_owner,
            self.cfg.transactions_db,
            str(order_id),
            pm.group(1),
            str(data.get("id")),
        )
        if self.cfg.after_complete is not None:
            await self.cfg.after_complete(data)

    def _check_instruments(
        self, body: bytes, row: dict[str, Any], headers: dict[str, str]
    ) -> bytes | Response:
        """AC-91 (DATA AC-R4, U-08). A lowercase card brand becomes UPPERCASE before validation.

        One log row has the old and the new value. A value that is not in the schema `enum`
        after the change fails with HTTP 400. The error names the path only, never the value.
        Schema: https://pay.google.com/gp/p/ucp/2026-01-23/schemas/card_payment_instrument.json
        Routing by `handler_id` (T-111): in MODE=ci the mock handler uses the CI-only schema in
        `conformance/schemas/`. In MODE=demo a `mock_payment_handler` instrument is refused.
        """
        try:
            data = json.loads(body or b"null")
        except ValueError:
            return body  # the route answers
        insts = (
            ((data or {}).get("payment") or {}).get("instruments")
            if isinstance(data, dict)
            else None
        )
        if not isinstance(insts, list):
            return body
        changed = False
        for i, inst in enumerate(insts):
            mock = isinstance(inst, dict) and inst.get("handler_id") == MOCK_HANDLER_ID
            if mock and self.cfg.mode != "ci":
                # AC-32, T-93 item 3, T-111 item 3: demo mode does not advertise the mock handler.
                return errors.invalid_request(
                    [(f"$.payment.instruments[{i}].handler_id", "The handler is not advertised.")]
                )
            if not (isinstance(inst, dict) and inst.get("type") == "card"):
                continue
            display = inst.get("display")
            brand = display.get("brand") if isinstance(display, dict) else None
            if isinstance(display, dict) and isinstance(brand, str) and brand != brand.upper():
                display["brand"] = brand.upper()
                changed = True
                events.write(
                    {
                        "request_id": headers.get("request-id"),
                        "method": "POST",
                        "field": f"payment.instruments[{i}].display.brand",
                        "old_value": brand,
                        "new_value": brand.upper(),
                        "note": "card brand changed to UPPERCASE before validation (AC-91)",
                    }
                )
            if self.cfg.registry is not None:
                if mock and self.cfg.ci_mock_instrument_schema is not None:
                    # T-111: MODE=ci routes the mock handler to the CI-only schema.
                    issues = self.cfg.registry.validate_document(
                        inst, self.cfg.ci_mock_instrument_schema
                    )
                else:
                    issues = self.cfg.registry.validate(inst, GPAY_INSTRUMENT_SCHEMA)
                if issues:
                    return errors.invalid_request(
                        [
                            (f"$.payment.instruments[{i}]" + x.path[1:], "The value is not valid.")
                            for x in issues
                        ]
                    )
        return json.dumps(data, separators=(",", ":")).encode() if changed else body

    def _check(
        self,
        scope: Scope,
        m: re.Match[str],
        headers: dict[str, str],
        body: bytes,
        row: dict[str, Any],
    ) -> Response | None:
        cfg = self.cfg
        if cfg.mode == "ci":
            for fault, status in (("rate_limit", 429), ("unavailable", 503)):
                if cfg.faults.get(fault, 0) > 0:
                    cfg.faults[fault] -= 1
                    return errors.protocol(
                        status,
                        "fault_injected",
                        f"CI fault: HTTP {status}.",
                        retry_after=cfg.faults.get("retry_after", 1),
                    )
        try:
            profile = cfg.resolver.resolve(headers.get("ucp-agent"))
        except ProfileProblem as e:
            return errors.protocol(e.status, e.code, e.content)
        version = profile.get("ucp", {}).get("version")
        if version != UCP_VERSION:
            return errors.protocol(
                422,
                "version_unsupported",
                f"Protocol version {version} is not supported. This business supports {UCP_VERSION}.",
            )
        try:
            row["signature"] = self._verify(scope, headers, body, profile)
        except SignatureProblem as e:
            return errors.protocol(e.status, e.code, e.content)
        method = scope["method"]
        if m.re is CATALOG:
            # T-119, AC-08b-6: the route needs the Platform capabilities to find the active ones.
            scope.setdefault("state", {})["ucp_platform_capabilities"] = profile["ucp"].get(
                "capabilities", {}
            )
            return None  # the route validates the body. No Idempotency-Key. No store probe.
        if m.re is ORDER:
            return self._order_access(m, headers, method)
        if method in ("POST", "PUT") and not headers.get("idempotency-key"):
            return errors.error_response(
                [
                    errors.message(
                        "invalid_request", "The Idempotency-Key header is required.", "recoverable"
                    )
                ],
                status=400,
            )
        if method in ("POST", "PUT") and not store.available(cfg.transactions_db):
            return errors.protocol(
                503, "store_unavailable", "The idempotency store is not available.", retry_after=2
            )
        schema = _schema_for(method, m)
        if schema:
            try:
                instance = json.loads(body or b"null")
            except ValueError:
                return errors.invalid_request([("$", "The body is not JSON.")])
            probs = composed.problems(schema, instance)
            if probs:
                return errors.invalid_request([(p.path, p.message) for p in probs])
            if isinstance(instance, dict) and cfg.root_fields:
                unknown = sorted(set(instance) - cfg.root_fields)
                if unknown:
                    row["unknown_root_fields"] = unknown
        return None

    def _order_access(
        self, m: re.Match[str], headers: dict[str, str], method: str
    ) -> Response | None:
        if method != "GET":
            return None  # the route answers 405
        order_id = m.group("id")
        pm = PROFILE_RE.search(headers.get("ucp-agent", ""))
        owner = store.order_owner(self.cfg.transactions_db, order_id)
        if owner is None and not store.order_exists(self.cfg.transactions_db, order_id):
            return None  # the route gives not_found
        if owner is None or pm is None or pm.group(1) != owner:
            return errors.error_response(
                [
                    errors.message(
                        "unauthorized", "Not authorized to access this order.", "unrecoverable"
                    )
                ],
                status=200,
            )
        return None

    def _verify(
        self, scope: Scope, headers: dict[str, str], body: bytes, profile: dict[str, Any]
    ) -> str:
        cfg = self.cfg
        has_sig = "signature" in headers and "signature-input" in headers
        if not has_sig:
            if cfg.require_signatures and not CATALOG.match(scope["path"]):
                raise SignatureProblem(401, "signature_missing", "Request signature is required.")
            scope.setdefault("state", {})["ucp_signature_checked"] = True
            if CATALOG.match(scope["path"]):
                return "absent (not required for catalog)"
            return "absent (enforcement off)"
        if cfg.verify is None:
            raise SignatureProblem(500, "signature_verifier_missing", "No verifier.")
        keys = profile.get("signing_keys") or []
        query = scope.get("query_string", b"").decode("latin-1")
        try:
            kid = cfg.verify(
                scope["method"], headers.get("host", ""), scope["path"], query, headers, body, keys
            )
        except Exception as e:  # the sample raises ucp_signing.SignatureError
            status = int(getattr(e, "status", getattr(e, "status_code", 401)))
            code = str(getattr(e, "code", "signature_invalid"))
            if cfg.require_signatures:
                raise SignatureProblem(status, code, str(getattr(e, "message", e))) from e
            scope.setdefault("state", {})["ucp_signature_checked"] = True
            return f"invalid {code} (enforcement off)"
        scope.setdefault("state", {})["ucp_signature_checked"] = True
        return f"verified keyid={kid}"


def _code_of(resp: Response) -> str | None:
    try:
        data = json.loads(bytes(resp.body))
    except ValueError:
        return None
    if isinstance(data, dict):
        if "code" in data:
            return str(data["code"])
        msgs = data.get("messages") or []
        if msgs and isinstance(msgs[0], dict):
            return str(msgs[0].get("code"))
    return None


def _replay(body: bytes) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive
