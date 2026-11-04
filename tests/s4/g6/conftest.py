"""G6 fixtures: signatures on (02-design 17.3, T-04). Business, Platform and mock PSP in process.

The Business sends each order webhook to the Platform app through an in-process transport
(no network). The Platform gets the Business keys from the Business profile (no network).
"""

from __future__ import annotations

import importlib
import pathlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from platform_app import main as pmain

from tests.s2.conftest import BUSINESS, Pair, make_pair

PLATFORM = "https://localhost:8443"
BUSINESS_PROFILE = BUSINESS + "/.well-known/ucp"
OTHER_PROFILE = "https://localhost:9444/.well-known/ucp"  # a second Business (AC-69)
DROP = {"host", "content-length"}


@dataclass
class G6:
    pair: Pair
    platform: TestClient
    extra_keys: dict[str, list[dict[str, Any]]]

    def business_key(self) -> tuple[Any, str]:
        key: tuple[Any, str] = importlib.import_module("config").WEBHOOK_SIGNING_KEY
        return key

    def post_webhook(self, headers: dict[str, str], body: bytes) -> httpx.Response:
        h = {k: v for k, v in headers.items() if k.lower() not in DROP}
        return self.platform.post("/webhooks/ucp/orders", content=body, headers=h)


def build(
    tmp: pathlib.Path, monkeypatch: pytest.MonkeyPatch, require_signatures: bool = True
) -> Iterator[G6]:
    monkeypatch.setenv("PLATFORM_ALLOWLIST", f"{BUSINESS_PROFILE},{OTHER_PROFILE}")
    monkeypatch.setenv("PLATFORM_WEBHOOK_DB", str(tmp / "webhooks.db"))
    gen = make_pair(tmp, monkeypatch, require_signatures=require_signatures)
    pair = next(gen)
    pmain.set_client(pair.client, pair.timeline)
    keys = {BUSINESS_PROFILE: pair.biz.get("/.well-known/ucp").json()["signing_keys"]}
    extra: dict[str, list[dict[str, Any]]] = {}
    pmain.set_key_resolver(lambda url: keys.get(url) or extra.get(url) or [])
    ptc = TestClient(pmain.app, base_url=PLATFORM)
    g = G6(pair, ptc, extra)

    def forward(request: httpx.Request) -> httpx.Response:
        r = g.post_webhook(dict(request.headers), request.content)
        return httpx.Response(r.status_code, content=r.content)

    pair.webhook_target["fn"] = forward
    try:
        yield g
    finally:
        pmain.set_key_resolver(None)
        pmain.set_client(None)
        try:
            next(gen)
        except StopIteration:
            pass


@pytest.fixture
def g6(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[G6]:
    yield from build(tmp_path, monkeypatch)


@pytest.fixture
def g6_off(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[G6]:
    """The request-signature flag off (as in G5). Webhooks stay signed (AC-65, T-04)."""
    yield from build(tmp_path, monkeypatch, require_signatures=False)
