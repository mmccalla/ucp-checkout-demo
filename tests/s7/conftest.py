"""S7 fixtures: the Business app and the Platform catalog client in one process (no network).

The fixture `pair` is the S2 pair (Business in MODE=ci with signatures required, Platform
profile from the test fetcher). `cat` is a `CatalogClient` on the same test transport. It
records each request that it sends.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from platform_app.catalog_client import LOOKUP, SEARCH, CatalogClient
from ucp_core import jwk

from tests.s2.conftest import BUSINESS, PROFILE_URL, Pair, make_pair


class Recorder(httpx.BaseTransport):
    """Pass each request to the test transport. Keep the request."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self.inner = inner
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.inner.handle_request(request)


@dataclass
class Cat:
    pair: Pair
    client: CatalogClient
    rec: Recorder
    extra: dict[str, Any] = field(default_factory=dict)

    def raw(self, path: str, body: Any, **headers: str) -> httpx.Response:
        """A request with only the given headers (no signature, no Idempotency-Key)."""
        h = {"UCP-Agent": f'profile="{PROFILE_URL}"', "Request-Id": "rid-raw"} | headers
        return self.pair.biz.post(path, json=body, headers=h)


@pytest.fixture
def pair(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Pair]:
    yield from make_pair(tmp_path, monkeypatch)


@pytest.fixture
def cat(pair: Pair) -> Cat:
    rec = Recorder(pair.biz._transport)
    client = CatalogClient(
        BUSINESS,
        PROFILE_URL,
        key=pair.key,
        kid=jwk.public_jwk(pair.key)["kid"],
        transport=rec,
        active=[SEARCH, LOOKUP],
    )
    return Cat(pair, client, rec)
