"""S2 fixtures: the Business app and the Platform client in one process.

The Platform client sends signed requests through the Starlette test transport. The Business
gets the Platform profile from a test fetcher (no network). Each test has its own data folder,
its own timeline files and its own keys.
"""

from __future__ import annotations

import copy
import importlib
import pathlib
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from business_app import order_events, psp_client
from business_app.main import create_app
from fastapi.testclient import TestClient
from psp_mock import main as psp_main
from platform_app import discovery
from platform_app.checkout_client import CheckoutClient
from platform_app.timeline import Timeline
from ucp_core import jwk

BUSINESS = "https://localhost:9443"
PROFILE_URL = "https://localhost:8443/.well-known/ucp"
ADDRESS = {
    "id": "d1",
    "street_address": "1 Test Street",
    "address_locality": "London",
    "postal_code": "SW1A 1AA",
    "address_country": "GB",
}


_KEY_ID = r"keyid=([A-Za-z0-9_-]{43})(?![A-Za-z0-9_-])"


def without_key_ids(text: str) -> str:
    """Remove the `kid` of each `keyid=<kid>` in log rows before a scan for short forbidden words.

    The `kid` is the RFC 7638 thumbprint of a key that each run makes new: 43 random base64url
    characters. A short word such as "eyJ" is in a random `kid` by chance (about 1 in 6000). Each
    `keyid=` must have a value of exactly this form, so no other text hides behind it.
    """
    assert re.search(r"keyid=(?![A-Za-z0-9_-]{43}(?![A-Za-z0-9_-]))", text) is None, "bad keyid"
    return re.sub(_KEY_ID, "keyid=", text)


def create_body(item: str = "demo_tshirt", qty: int = 1, country: str = "GB") -> dict[str, Any]:
    dest = dict(ADDRESS, address_country=country)
    return {
        "line_items": [{"item": {"id": item}, "quantity": qty}],
        "fulfillment": {
            "methods": [
                {"type": "shipping", "destinations": [dest], "selected_destination_id": "d1"}
            ]
        },
    }


@dataclass
class Pair:
    biz: TestClient
    client: CheckoutClient
    timeline: Timeline
    platform_profile: dict[str, Any]
    key: Any
    fetches: list[str]
    sleeps: list[float]
    app: Any
    tmp: pathlib.Path
    profile_for: dict[str, Any] = field(default_factory=dict)
    psp: Any = None  # psp_mock Store: the charge records (S4)
    webhooks: list[httpx.Request] = field(default_factory=list)  # S4: webhook deliveries
    # S4 (G6): a function that answers each webhook delivery. None answers 200.
    webhook_target: dict[str, Callable[[httpx.Request], httpx.Response]] = field(
        default_factory=dict
    )

    def headers(self, **extra: str) -> dict[str, str]:
        h = {"UCP-Agent": f'profile="{PROFILE_URL}"', "Request-Id": "rid-test"}
        h.update(extra)
        return h


def make_pair(
    tmp: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    require_signatures: bool = True,
    faults: dict[str, int] | None = None,
    profile_edit: Callable[[dict[str, Any]], None] | None = None,
) -> Iterator[Pair]:
    monkeypatch.setenv("BUSINESS_DATA_DIR", str(tmp / "data"))
    monkeypatch.setenv("BUSINESS_EVENTS", str(tmp / "business.jsonl"))
    monkeypatch.setenv("PLATFORM_EVENTS", str(tmp / "platform.jsonl"))
    key = jwk.ephemeral()
    pprof = discovery.platform_profile(jwk.public_jwk(key))
    if profile_edit is not None:
        pprof = copy.deepcopy(pprof)
        profile_edit(pprof)
    fetches: list[str] = []

    def fetcher(url: str) -> tuple[dict[str, Any], dict[str, str]]:
        fetches.append(url)
        return pprof, {"cache-control": "public, max-age=300"}

    # S4: the Business calls the mock PSP through an in-process transport (no network).
    psp_app = psp_main.create_app()
    psp_tc = TestClient(psp_app, base_url="http://psp.test")
    app = create_app(
        payment_authorizer=psp_client.make_authorizer("http://psp.test", psp_tc._transport),
        mode="ci",
        key=jwk.ephemeral(),
        endpoint=BUSINESS,
        fetcher=fetcher,
        require_signatures=require_signatures,
        faults=faults or {},
    )
    # S4: webhook deliveries go to an in-process recorder. No test delivery leaves the process.
    hooks: list[httpx.Request] = []
    target: dict[str, Callable[[httpx.Request], httpx.Response]] = {}

    def _webhook(request: httpx.Request) -> httpx.Response:
        request.read()
        hooks.append(request)
        fn = target.get("fn")
        return fn(request) if fn is not None else httpx.Response(200)

    monkeypatch.setattr(
        importlib.import_module("config"),
        "WEBHOOK_TRANSPORT",
        order_events.ObservedTransport(httpx.MockTransport(_webhook)),
    )
    monkeypatch.setenv("BUSINESS_DEAD_LETTER", str(tmp / "dead-letter.jsonl"))
    monkeypatch.setenv("BUSINESS_OUTBOX", str(tmp / "outbox.jsonl"))
    sleeps: list[float] = []
    tl = Timeline(tmp / "platform.jsonl", tmp / "business.jsonl")
    with TestClient(app, base_url=BUSINESS) as biz:
        client = CheckoutClient(
            BUSINESS,
            PROFILE_URL,
            key=key,
            kid=jwk.public_jwk(key)["kid"],
            transport=biz._transport,
            sleep=sleeps.append,
        )
        yield Pair(
            biz,
            client,
            tl,
            pprof,
            key,
            fetches,
            sleeps,
            app,
            tmp,
            psp=psp_app.state.store,
            webhooks=hooks,
            webhook_target=target,
        )


@pytest.fixture
def pair(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Pair]:
    yield from make_pair(tmp_path, monkeypatch)
