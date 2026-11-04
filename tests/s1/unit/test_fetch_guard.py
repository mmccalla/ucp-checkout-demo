"""AC-122, AC-01 (no redirect), AC-02 (cache): profile fetch rules (overview "Fetching")."""

from __future__ import annotations

import logging

import httpx
import pytest
from ucp_core import netguard
from ucp_core.constants import MAX_PROFILE_BYTES

URL = "https://shop.example/.well-known/ucp"


def resolver_for(*addrs: str) -> netguard.Resolver:
    def r(host: str, port: int) -> list[str]:
        return list(addrs)

    return r


class NoConnect(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("the guard must refuse before any connection")


@pytest.mark.parametrize("addr", ["10.0.0.5", "172.17.0.2", "192.168.1.10", "169.254.169.254"])
def test_ac122_special_use_address_refused_before_connect(
    addr: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="ucp.netguard")
    with pytest.raises(netguard.BlockedAddress) as e:
        netguard.fetch_profile(URL, "127.0.0.1", resolver=resolver_for(addr), transport=NoConnect())
    assert e.value.address == addr
    assert f"resolved={addr}" in caplog.text


def test_ac122_loopback_refused_when_verifier_not_on_loopback() -> None:
    with pytest.raises(netguard.BlockedAddress):
        netguard.resolve_checked(URL, "192.0.2.10", resolver_for("127.0.0.1"))


def test_ac122_loopback_allowed_when_verifier_on_loopback() -> None:
    assert netguard.resolve_checked(URL, "127.0.0.1", resolver_for("127.0.0.1", "::1")) == [
        "127.0.0.1",
        "::1",
    ]


def test_mixed_answer_with_one_private_address_is_refused() -> None:
    with pytest.raises(netguard.BlockedAddress):
        netguard.resolve_checked(URL, "127.0.0.1", resolver_for("127.0.0.1", "10.0.0.5"))


def test_http_url_is_refused() -> None:
    with pytest.raises(netguard.FetchError):
        netguard.resolve_checked("http://shop.example/.well-known/ucp", "127.0.0.1")


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_ac01_redirect_is_not_followed(status: int) -> None:
    t = httpx.MockTransport(
        lambda req: httpx.Response(status, headers={"Location": "https://other.example/"})
    )
    with pytest.raises(netguard.FetchError, match="redirect refused"):
        netguard.fetch_profile(URL, "127.0.0.1", resolver=resolver_for("127.0.0.1"), transport=t)


def test_body_over_limit_is_refused() -> None:
    big = b"[" + b"0," * (MAX_PROFILE_BYTES // 2) + b"0]"
    t = httpx.MockTransport(lambda req: httpx.Response(200, content=big))
    with pytest.raises(netguard.FetchError, match="over limit"):
        netguard.fetch_profile(URL, "127.0.0.1", resolver=resolver_for("127.0.0.1"), transport=t)


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("public, max-age=300", True),
        ("public, max-age=60", True),
        ("public, max-age=59", False),
        ("max-age=300", False),
        ("public, no-store, max-age=300", False),
        (None, False),
    ],
)
def test_ac02_cache_control(value: str | None, ok: bool) -> None:
    assert netguard.cache_control_ok(value)[0] is ok
