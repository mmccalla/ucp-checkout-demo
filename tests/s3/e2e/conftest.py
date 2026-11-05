"""G7 e2e harness: the Platform page in headless Chrome against the in-process Business.

- The Platform app (`platform_app.main.app`, MODE=ci) runs in uvicorn on 127.0.0.1 and a free
  port (DM-26). http://127.0.0.1 is a secure context (W3C Secure Contexts, "potentially
  trustworthy"), so the page APIs behave as on the TLS layout.
- The Platform checkout client sends signed requests to the Business through a hook transport
  around the Starlette test transport (`tests/s2/conftest.make_pair`). The hook can drop a request,
  return a status, change a response and record each request (method, path, Request-Id and
  Idempotency-Key only, never a body or a signature).
- The Google Pay library is the CI stub `/checkout/gpay-stub.js` (04-build-plan S3).
- The browser is /usr/bin/google-chrome, headless, through Playwright 1.56.0.
"""

from __future__ import annotations

import json
import os
import pathlib
import socket
import threading
import time
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from typing import Any, cast

import httpx2
import pytest
import uvicorn
from fastapi.testclient import TestClient
from platform_app import main as pmain
from platform_app.catalog_client import LOOKUP, SEARCH, CatalogClient
from platform_app.checkout_client import CheckoutClient
from platform_app.discovery import apply_case, platform_profile
from playwright.sync_api import Browser, Page, sync_playwright
from ucp_core import jwk, profile_check
from ucp_core.constants import ROOT
from ucp_core.schema_registry import SchemaRegistry

from tests.evidence import evidence_dir
from tests.s2.conftest import BUSINESS, PROFILE_URL, Pair, make_pair

CHROME = os.environ.get("UCP_CHROME", "/usr/bin/google-chrome")  # Google Chrome of the runner image
EVIDENCE = (
    pathlib.Path(os.environ["S3_EVIDENCE"])
    if os.environ.get("S3_EVIDENCE")
    else evidence_dir("S3", "g7")
)
Mutator = Callable[
    [httpx2.Request, dict[str, Any]], dict[str, Any] | tuple[int, dict[str, Any]] | None
]


@dataclass
class Hook:
    calls: list[dict[str, Any]] = field(default_factory=list)
    drop: dict[str, int] = field(default_factory=dict)  # op -> count of transport errors
    status: dict[str, tuple[int, dict[str, Any]]] = field(default_factory=dict)
    mutate: dict[str, Mutator] = field(default_factory=dict)
    delay: dict[str, float] = field(default_factory=dict)
    # CI-only seam (UX-4.5.1, UX-AC-32). op -> count. The request reaches the Business, the
    # Business stores its response, and then the response is lost (a transport error). The
    # Platform sends the same Idempotency-Key and the same body again. This code is in the
    # test harness only. No Platform or Business source file has it.
    drop_response: dict[str, int] = field(default_factory=dict)
    # After a Complete has reached the Business, the next N Get Checkout calls get a transport
    # error (AC-44 recovery: the Platform cannot learn what the Business did).
    drop_get_after_complete: int = 0
    strip_signature: bool = False

    @staticmethod
    def op(req: httpx2.Request) -> str:
        p = req.url.path
        if p.endswith("/catalog/search"):
            return "search"
        if p.endswith("/catalog/lookup"):
            return "lookup"
        if p.endswith("/catalog/product"):
            return "product"
        if p.endswith("/complete"):
            return "complete"
        if p.endswith("/cancel"):
            return "cancel"
        if req.method == "POST":
            return "create"
        return "update" if req.method == "PUT" else "get"

    def ops(self) -> list[str]:
        return [c["op"] for c in self.calls if c["reached"]]


class HookTransport(httpx2.BaseTransport):
    def __init__(self, inner: httpx2.BaseTransport, hook: Hook) -> None:
        self.inner, self.hook = inner, hook

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        h = self.hook
        op = h.op(request)
        row = {
            "op": op,
            "method": request.method,
            "path": request.url.path,
            "request_id": request.headers.get("request-id"),
            "idempotency_key": request.headers.get("idempotency-key"),
            "reached": False,
        }
        if op in ("search", "lookup", "product"):
            # S7: the catalog request has no secret. The test checks the exact body (AC-127).
            row["body"] = json.loads(request.content or b"null")
        h.calls.append(row)
        if h.drop.get(op, 0) > 0:
            h.drop[op] -= 1
            raise httpx2.ConnectError("hook: dropped", request=request)
        if op in h.status:
            code, body = h.status[op]
            return httpx2.Response(code, json=body, request=request)
        if h.strip_signature:
            for k in ("signature", "signature-input"):
                if k in request.headers:
                    del request.headers[k]
        if op in h.delay:
            time.sleep(h.delay[op])
        row["reached"] = True
        r = self.inner.handle_request(request)
        if op == "complete" and h.drop_get_after_complete:
            h.drop["get"] = h.drop_get_after_complete
            h.drop_get_after_complete = 0
        if h.drop_response.get(op, 0) > 0:
            h.drop_response[op] -= 1
            r.read()
            raise httpx2.ReadError("hook: response dropped", request=request)
        if op in h.mutate:
            r.read()
            body = json.loads(r.content or b"null")
            new = h.mutate[op](request, body)
            if new is not None:
                hdrs = {k: v for k, v in r.headers.items() if k.lower() not in ("content-length",)}
                status = r.status_code
                if isinstance(new, tuple):  # S7: a mutator can also set the HTTP status
                    status, new = new
                return httpx2.Response(status, json=new, headers=hdrs, request=request)
        return r


@dataclass
class Stack:
    pair: Pair
    hook: Hook
    base: str
    page: Page
    console: list[str]
    requests: list[str]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def server() -> Iterator[str]:
    pmain.MODE = "ci"
    port = _free_port()
    cfg = uvicorn.Config(pmain.app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(5)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    # Module scope, not session scope. While a `sync_playwright()` instance is open, the main
    # thread has a running asyncio event loop (Playwright runs its driver on that loop).
    # `asyncio.run()` cannot start in that thread then (Python 3.12 docs, asyncio.run). A session
    # fixture would stay open to the end of the session and would break every later test that
    # calls `asyncio.run()` (tests/s5/unit, tests/s6/unit). A module fixture is closed after the
    # last test of the e2e module (pytest 8.4 docs, "Fixture scopes"). The guard test
    # tests/s3/e2e/test_loop_released.py checks this.
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True)
        yield b
        b.close()


@pytest.fixture(scope="session")
def reg() -> SchemaRegistry:
    return SchemaRegistry.load(ROOT)


def _discovery(
    pair: Pair, reg: SchemaRegistry, catalog: bool | str = False
) -> Callable[[str], dict[str, Any]]:
    def run(case: str) -> dict[str, Any]:
        r = pair.biz.get("/.well-known/ucp")
        b, p = apply_case(case, r.json(), platform_profile())
        # S1 to S6 tests (`catalog=False`): the Platform lists no catalog capability. Neither is
        # active, so the page starts at SC2 as before S7. The S7 tests set `catalog=True`.
        # `catalog="search"`: only search is listed. `catalog="lookup"`: only lookup.
        drop = {
            False: (SEARCH, LOOKUP),
            True: (),
            "search": (LOOKUP,),
            "lookup": (SEARCH,),
        }[catalog]
        for cap in drop:
            p["ucp"]["capabilities"].pop(cap, None)
        rep = profile_check.check(reg, b, p, {k.lower(): v for k, v in r.headers.items()})
        return {"case": case, "url": BUSINESS + "/.well-known/ucp", "ok": True} | rep

    return run


@pytest.fixture
def make_stack(
    server: str,
    browser: Browser,
    reg: SchemaRegistry,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[..., Stack]]:
    gens: list[Iterator[Pair]] = []
    pages: list[Page] = []

    def build(
        gpay: dict[str, Any] | None = None,
        faults: dict[str, int] | None = None,
        viewport: tuple[int, int] = (1280, 900),
        catalog: bool | str = False,
    ) -> Stack:
        monkeypatch.setenv("PLATFORM_SPEND_FILE", str(tmp_path / "spend.jsonl"))
        monkeypatch.setenv("PLATFORM_AUDIT_DB", str(tmp_path / "audit.sqlite"))  # AC-55
        monkeypatch.delenv("PLATFORM_ALLOWLIST", raising=False)
        monkeypatch.delenv("BUSINESS_ORIGIN", raising=False)
        monkeypatch.setenv("PLATFORM_WEBHOOK_DB", str(tmp_path / f"webhooks-{len(gens)}.db"))
        gen = make_pair(tmp_path, monkeypatch, faults=faults)
        gens.append(gen)
        pair = next(gen)

        # S4 (AC-74): the Business sends each order webhook to the Platform server on
        # 127.0.0.1. The Host header stays the signed authority (localhost:8443).
        def forward(req: httpx2.Request) -> httpx2.Response:
            h = {k: v for k, v in req.headers.items() if k.lower() != "content-length"}
            r = httpx2.post(server + req.url.path, content=req.content, headers=h, timeout=10)
            return httpx2.Response(r.status_code, content=r.content)

        pair.webhook_target["fn"] = forward
        hook = Hook()
        # raise_server_exceptions=False: a Business server error is an HTTP 500, as on the
        # live layout (uvicorn), and not an exception in the test process.
        biz = TestClient(
            pair.app, base_url=BUSINESS, raise_server_exceptions=False, follow_redirects=False
        )
        client = CheckoutClient(
            BUSINESS,
            PROFILE_URL,
            key=pair.key,
            kid=jwk.public_jwk(pair.key)["kid"],
            transport=HookTransport(httpx2.MockTransport(biz.send), hook),
            sleep=pair.sleeps.append,
        )
        pmain.set_client(client, pair.timeline)
        pmain.set_catalog_client(
            CatalogClient(
                BUSINESS,
                PROFILE_URL,
                key=pair.key,
                kid=jwk.public_jwk(pair.key)["kid"],
                transport=HookTransport(httpx2.MockTransport(biz.send), hook),
                sleep=pair.sleeps.append,
                max_tries=1,
            )
        )
        pmain.set_psp_calls(lambda cid: pair.psp.calls.get(cid, 0))  # CI seam, see Hook
        pmain.set_discovery(_discovery(pair, reg, catalog))
        ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
        page = ctx.new_page()
        pages.append(page)
        console: list[str] = []
        requests: list[str] = []
        page.on("console", lambda m: console.append(m.text))
        page.on("request", lambda r: requests.append(r.method + " " + r.url))
        stub = {"ready": True, "outcome": "approve"} | (gpay or {})
        page.add_init_script(f"window.__gpayStub = {json.dumps(stub)};")
        return Stack(pair, hook, server, page, console, requests)

    yield build
    for p in pages:
        p.context.close()
    pmain.set_client(None)
    pmain.set_catalog_client(None)
    pmain.set_psp_calls(None)
    pmain.set_discovery(None)
    for g in gens:
        cast(Generator[Pair, None, None], g).close()  # make_pair is a generator
