"""Business server, slice S2: profile (S1) and checkout Create, Get, Update, Cancel.

- It listens on 127.0.0.1 (DM-26). Caddy gives TLS 1.3 in front of it (T-90).
- `redirect_slashes=False`: a profile endpoint "MUST NOT use redirects (3xx)" (overview, Hosting).
- The checkout routes are the vendored samples copy `rest/python/server` at `e7c9c12`
  (spec T-05, D11) with the patches in `business/UPSTREAM.md`. The gate (`gate.py`) runs in
  front of them. The error bodies follow spec T-102 (`errors.py`, ADR 0006).
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from ucp_core import composed, netns, telemetry
from ucp_core import jwk as jwkmod
from ucp_core.constants import mode as current_mode
from ucp_core.schema_registry import SchemaRegistry

from . import catalog, errors, events, order_events, profile, store
from .gate import Gate, GateConfig
from .platform_profiles import Fetcher, Resolver, ci_fetcher, default_fetcher

if str(store.SAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(store.SAMPLE_DIR))

import config as sample_config  # noqa: E402  (vendored sample, top-level modules)
import db as sample_db  # noqa: E402
import generated_routes.ucp_routes as sample_routes  # noqa: E402
import routes.order as sample_order_routes  # noqa: E402
import routes.ucp_implementation as sample_impl  # noqa: E402
import ucp_signing  # noqa: E402
from exceptions import UcpError  # noqa: E402

from . import psp_client  # noqa: E402  (needs the vendored modules on sys.path)

LINK_PATHS = {"privacy_policy": "/policies/privacy", "terms_of_service": "/policies/terms"}
POLICY_TEXT = {
    "/policies/privacy": ("Privacy policy", "This is a demo shop. It keeps no personal data."),
    "/policies/terms": ("Terms of service", "This is a demo shop. No order is real."),
}


def _root_fields(name: str) -> frozenset[str]:
    out: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            out.update((node.get("properties") or {}).keys())
            for sub in node.get("allOf", []):
                walk(sub)

    walk(composed.validator(name).schema)
    return frozenset(out)


def _flags(products: str, transactions: str, require_signatures: bool, mode: str) -> None:
    f = sample_config.FLAGS
    if not f.is_parsed():
        f(["business"])
    f.products_db_path = products
    f.transactions_db_path = transactions
    f.require_signatures = require_signatures
    f.allow_insecure_profile_urls = False
    if mode == "ci":
        # Simulation path (spec T-93). The secret is given by the CI job. Demo mode: no path.
        f.simulation_secret = os.environ.get("SIMULATION_SECRET", "")


def _faults() -> dict[str, int]:
    out: dict[str, int] = {}
    for part in os.environ.get("BUSINESS_FAULTS", "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = int(v)
    return out


CI_MOCK_SCHEMA = (
    pathlib.Path(__file__).resolve().parents[3] / "conformance" / "schemas"
    / "ci_mock_payment_instrument.json"
)  # fmt: skip


def _ci_mock_schema() -> dict[str, Any]:
    """The CI-only mock instrument schema (T-111). Demo mode never reads this file."""
    doc = json.loads(CI_MOCK_SCHEMA.read_text())
    assert isinstance(doc, dict)
    return doc


SUITE_HTTP_SWITCH = "BUSINESS_CI_SUITE_PROFILE_HTTP"  # the one switch: "1" turns the seam on
SUITE_PORT_VAR = "BUSINESS_CI_SUITE_PROFILE_PORT"  # the suite `mock_agent_port`, default 8285
NETNS_FLAG = "BUSINESS_CI_NETNS"  # "1": the launcher checked the namespace (T-109)
SUITE_PORT_DEFAULT = 8285


class ConfigurationError(RuntimeError):
    """A start-up setting is wrong. The Business does not start (T-114, T-115)."""


def _port_setting(name: str, raw: str) -> int:
    value = raw.strip()
    if not (value.isdigit() and 1 <= int(value) <= 65535):
        raise ConfigurationError(
            f"configuration error: {name} must be a port number from 1 to 65535, "
            f"the value is {raw!r}. The Business does not start."
        )
    return int(value)


def ci_netns_ok(environ: Mapping[str, str] | None = None) -> bool:
    """The launcher set the flag and this namespace has only `lo` (T-114 clause 2)."""
    env = os.environ if environ is None else environ
    return env.get(NETNS_FLAG) == "1" and netns.loopback_only()


SUITE_WEBHOOK_SWITCH = "BUSINESS_CI_SUITE_WEBHOOK_HTTP"  # T-115: "1" turns the seam on
SUITE_WEBHOOK_PORT_VAR = "BUSINESS_CI_SUITE_WEBHOOK_PORT"  # the suite `mock_webhook_port`
SUITE_WEBHOOK_PORT_DEFAULT = 8284
WEBHOOK_PROFILE_URL_VAR = "BUSINESS_WEBHOOK_PROFILE_URL"


def ci_suite_webhook_port(mode: str = "ci", environ: Mapping[str, str] | None = None) -> int | None:
    """The port of the one `http` suite webhook URL, or None (T-115 item 3).

    Same guards as `ci_suite_profile_port`: MODE=ci, the switch, the launcher flag and a
    network namespace that has only `lo`.
    """
    env = os.environ if environ is None else environ
    if mode != "ci" or env.get(SUITE_WEBHOOK_SWITCH) != "1" or not ci_netns_ok(env):
        return None
    return _port_setting(
        SUITE_WEBHOOK_PORT_VAR, env.get(SUITE_WEBHOOK_PORT_VAR, str(SUITE_WEBHOOK_PORT_DEFAULT))
    )


def webhook_profile_url(origin: str, environ: Mapping[str, str] | None = None) -> str:
    """The `UCP-Agent` profile URL of the Business in a webhook. It must be HTTPS.

    Source: https://github.com/Universal-Commerce-Protocol/ucp at 9c9d6fc,
    docs/specification/signatures.md lines 622 to 625: the value "MUST be a quoted string
    containing an HTTPS URL"; "Reject non-HTTPS URLs". The Business refuses to start with
    another scheme. `BUSINESS_WEBHOOK_PROFILE_URL` gives the value when `origin` is not HTTPS
    (G5 serves the Business over plain `http` inside the namespace).
    """
    env = os.environ if environ is None else environ
    url = env.get(WEBHOOK_PROFILE_URL_VAR) or origin + "/.well-known/ucp"
    if not url.startswith("https://"):
        raise RuntimeError(f"the webhook profile URL is not HTTPS (signatures.md 622-625): {url}")
    return url


def ci_suite_profile_port(mode: str = "ci", environ: Mapping[str, str] | None = None) -> int | None:
    """The port of the one `http` suite profile URL, or None (spec T-114 option (a)).

    The seam is on only if all of these are true: MODE=ci, the switch is `1`, the launcher set
    `BUSINESS_CI_NETNS=1` and this process runs in a network namespace that has only `lo`
    (T-109). Else it is off. `Resolver` checks the namespace again before each use.
    """
    env = os.environ if environ is None else environ
    if mode != "ci" or env.get(SUITE_HTTP_SWITCH) != "1" or not ci_netns_ok(env):
        return None
    return _port_setting(SUITE_PORT_VAR, env.get(SUITE_PORT_VAR, str(SUITE_PORT_DEFAULT)))


def create_app(
    mode: str | None = None,
    key: Any = None,
    endpoint: str | None = None,
    fetcher: Fetcher = default_fetcher,
    require_signatures: bool | None = None,
    faults: dict[str, int] | None = None,
    payment_authorizer: Callable[[str, Any, Any], None] | None = None,
) -> FastAPI:
    telemetry.configure_logging()
    m = mode or current_mode()
    if key is None:
        # CI uses a new ephemeral key for each run (input-engineering 6, rule 3).
        key = jwkmod.ephemeral() if m == "ci" else jwkmod.load_or_create(profile.key_file())
    origin = endpoint or profile.origin()
    body = profile.build(m, jwkmod.public_jwk(key), origin)
    products, transactions = store.prepare(m)
    if require_signatures is None:
        # T-04: on in demo mode and in CI gate G6. Off only in gate G5 (conformance).
        require_signatures = os.environ.get("BUSINESS_REQUIRE_SIGNATURES", "true") != "false"
    _flags(products, transactions, require_signatures, m)
    sample_config.set_profile(body)
    sample_config.LINKS = [{"type": t, "url": origin + p} for t, p in LINK_PATHS.items()]
    # S4 (P15, FR-11): the default hook calls the mock PSP. Tests can give their own hook.
    sample_config.PAYMENT_AUTHORIZER = payment_authorizer or psp_client.make_authorizer()
    resolver = Resolver(SchemaRegistry.load())
    resolver.fetcher = fetcher
    if m == "ci":
        # Spec T-114 option (a): the one `http` suite profile URL, only if the switch is set
        # and only in a network namespace that has only `lo` (T-109). Demo mode never.
        resolver.ci_http_port = ci_suite_profile_port()
        resolver.ci_http_guard = ci_netns_ok
        if fetcher is default_fetcher and resolver.ci_http_port is not None:
            resolver.fetcher = ci_fetcher
    sample_config.PROFILE_RESOLVER = resolver.cached
    # S4 (patch P16): webhooks are signed with the published profile key (AC-65). UCP-Agent
    # names the public profile URL. Each attempt is logged. A failed event is a dead letter.
    kid = jwkmod.public_jwk(key)["kid"]
    sample_config.WEBHOOK_SIGNING_KEY = (key, kid)
    sample_config.WEBHOOK_PROFILE_URL = webhook_profile_url(origin)
    sample_config.WEBHOOK_DEAD_LETTER = order_events.dead_letter
    sample_config.WEBHOOK_TRANSPORT = order_events.ObservedTransport(
        mode=m,
        suite_webhook_port=ci_suite_webhook_port(m),
        ci_guard=ci_netns_ok,
    )
    simulate = os.environ.get("BUSINESS_SIMULATE_ORDER_EVENTS", "true") != "false"
    delay = float(os.environ.get("BUSINESS_ORDER_EVENT_DELAY", "1.0" if m == "demo" else "0"))

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await sample_db.manager.init_dbs(products, transactions)
        yield
        await sample_db.manager.close()

    app = FastAPI(title="business", redirect_slashes=False, lifespan=lifespan)
    cfg = GateConfig(
        resolver=resolver,
        transactions_db=transactions,
        verify=ucp_signing.verify_request,
        require_signatures=require_signatures,
        mode=m,
        faults=dict(faults if faults is not None else (_faults() if m == "ci" else {})),
        root_fields=_root_fields("checkout.create_request")
        | _root_fields("checkout.update_request"),
        sign_key=key,
        sign_kid=kid,
        after_complete=order_events.make_after_complete(origin, simulate, delay),
        registry=resolver.registry,
        ci_mock_instrument_schema=_ci_mock_schema() if m == "ci" else None,
    )
    app.state.gate = cfg
    app.state.transactions_db = transactions

    @app.exception_handler(RequestValidationError)
    async def on_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        del request
        probs = []
        for err in exc.errors():
            loc = [p for p in err.get("loc", ()) if p not in ("body",)]
            path = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in loc)
            probs.append((path, str(err.get("msg", "not valid"))))
        return errors.invalid_request(probs)

    @app.exception_handler(UcpError)
    async def on_ucp_error(request: Request, exc: UcpError) -> Response:
        del request
        code = str(exc.code).lower()
        if exc.status_code == 404 or code == "resource_not_found":
            # ADR 0006: no checkout exists. checkout.md lines 141-145: error_response, no
            # resource, severity unrecoverable. The pinned status table has no 404.
            return errors.error_response(
                [errors.message("not_found", exc.message, "unrecoverable")], status=200
            )
        if exc.status_code == 200:  # P8: Create made no checkout (all items out of stock)
            return errors.error_response(
                [errors.message(code, exc.message, "unrecoverable")], status=200
            )
        if exc.status_code == 400:
            return errors.invalid_request([("$", exc.message)])
        status = exc.status_code if exc.status_code in errors.PROTOCOL_STATUSES else 500
        return errors.protocol(status, code, exc.message)

    @app.get("/livez")
    def livez() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        ok = store.available(transactions)
        return JSONResponse(
            {"status": "ok" if ok else "red", "mode": m, "idempotency_store": ok},
            status_code=200 if ok else 503,
        )

    @app.get("/.well-known/ucp")
    def well_known_ucp() -> JSONResponse:
        return JSONResponse(body, headers={"Cache-Control": profile.CACHE_CONTROL})

    @app.get("/policies/{name}")
    def policy(name: str) -> HTMLResponse:
        title, text = POLICY_TEXT.get(f"/policies/{name}", ("Not found", ""))
        status = 200 if text else 404
        html = (
            f"<!doctype html><html lang=en-GB><title>{title}</title><h1>{title}</h1><p>{text}</p>"
        )
        return HTMLResponse(html, status_code=status)

    sample_impl.apply_implementation(sample_routes.router)
    for route in list(sample_routes.router.routes):
        path = getattr(route, "path", "")
        if path.startswith("/checkout-sessions"):
            app.router.routes.append(route)
    # S4: Get Order only (order.md "Operations"). Update Order is not mounted. The demo
    # simulates the order events itself (AC-74, 02-design 17.4). In MODE=ci only, the
    # simulate-shipping path is mounted (spec T-93). It needs the `Simulation-Secret` header.
    ci_paths = ("/testing/simulate-shipping/{id}",) if m == "ci" else ()
    for route in list(sample_order_routes.router.routes):
        path, methods = getattr(route, "path", ""), getattr(route, "methods", ())
        if (path == "/orders/{id}" and "GET" in methods) or path in ci_paths:
            app.router.routes.append(route)
    # S7 (DM-11): catalog search, batch lookup and Get Product (catalog.py).
    app.include_router(
        catalog.make_router(products, transactions, resolver.registry, body["ucp"]["capabilities"])
    )
    app.add_middleware(Gate, cfg=cfg)
    telemetry.instrument_fastapi(app, "business")  # last, so the server span is outermost
    events.log_file()
    return app
