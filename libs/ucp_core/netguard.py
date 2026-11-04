"""Profile fetch with the special-use address guard (AC-01, AC-122, DM-26).

UCP 2026-04-08 overview, "Fetching" (https://ucp.dev/2026-04-08/specification/overview/):
- "Implementations MUST reject URLs not served over HTTPS."
- "Implementations MUST NOT follow redirects (3xx)."
- "Implementations MUST reject URLs that resolve to special-use IP addresses (RFC 6890 ...),
  except a loopback target when the verifier itself runs on the same loopback interface".
- "Verifiers SHOULD validate the resolved address, not just the hostname".
"""

from __future__ import annotations

import ipaddress
import json
import logging
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from .constants import MAX_PROFILE_BYTES

log = logging.getLogger("ucp.netguard")
Resolver = Callable[[str, int], list[str]]
IP = ipaddress.IPv4Address | ipaddress.IPv6Address


class BlockedAddress(Exception):
    def __init__(self, url: str, address: str, reason: str):
        super().__init__(f"{url}: resolved address {address} refused ({reason})")
        self.url, self.address, self.reason = url, address, reason


class FetchError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


@dataclass
class Fetched:
    url: str
    status: int
    headers: dict[str, str]
    body: Any
    resolved: list[str] = field(default_factory=list)


def system_resolver(host: str, port: int) -> list[str]:
    import socket

    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(i[4][0]) for i in infos})


def special_use(ip: IP) -> str | None:
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_private:
        return "private"
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified or not ip.is_global:
        return "special-use"
    return None


def resolve_checked(
    url: str,
    verifier_host: str,
    resolver: Resolver = system_resolver,
    ci_http_loopback: bool = False,
) -> list[str]:
    """Resolve the URL host and check each address before any connection.

    Return the allowed addresses. Raise BlockedAddress for the first refused address.
    A loopback address is allowed only when `verifier_host` is itself a loopback address.
    `ci_http_loopback` is a CI-only seam (spec T-114 option (a)): `http` is allowed when every
    address of the host is loopback. The conformance suite serves its agent profile on
    `http://localhost`. The Business sets the flag only in MODE=ci.
    """
    parts = urlsplit(url)
    http_ok = ci_http_loopback and parts.scheme == "http"
    if parts.scheme != "https" and not http_ok:
        raise FetchError("profile_unreachable", f"{url}: not HTTPS")
    host = parts.hostname or ""
    port = parts.port or (80 if http_ok else 443)
    verifier_on_loopback = ipaddress.ip_address(verifier_host).is_loopback
    addrs = resolver(host, port)
    if not addrs:
        raise FetchError("profile_unreachable", f"{url}: no address for {host}")
    for a in addrs:
        log.info("profile url %s resolved=%s", url, a)
        reason = special_use(ipaddress.ip_address(a))
        if reason == "loopback" and verifier_on_loopback:
            continue
        if http_ok:
            log.warning("refused before connect: %s resolved=%s (http needs loopback)", url, a)
            raise BlockedAddress(url, a, reason or "not loopback")
        if reason is not None:
            log.warning("refused before connect: %s resolved=%s (%s)", url, a, reason)
            raise BlockedAddress(url, a, reason)
    return addrs


def fetch_profile(
    url: str,
    verifier_host: str,
    verify: ssl.SSLContext | bool = True,
    resolver: Resolver = system_resolver,
    timeout: float = 5.0,
    transport: httpx.BaseTransport | None = None,
    ci_http_loopback: bool = False,
) -> Fetched:
    """GET a profile. No redirect, size bound, JSON body. The checks run before the connection."""
    addrs = resolve_checked(url, verifier_host, resolver, ci_http_loopback)
    raw = b""
    with httpx.Client(
        verify=verify, follow_redirects=False, timeout=timeout, transport=transport
    ) as c:
        try:
            with c.stream("GET", url, headers={"Accept": "application/json"}) as r:
                if 300 <= r.status_code < 400:
                    raise FetchError(
                        "profile_unreachable",
                        f"{url}: HTTP {r.status_code} redirect refused (MUST NOT follow)",
                    )
                if r.status_code != 200:
                    raise FetchError("profile_unreachable", f"{url}: HTTP {r.status_code}")
                for chunk in r.iter_bytes():
                    raw += chunk
                    if len(raw) > MAX_PROFILE_BYTES:
                        raise FetchError("profile_malformed", f"{url}: body over limit")
                headers = {k.lower(): v for k, v in r.headers.items()}
        except httpx.HTTPError as e:
            raise FetchError("profile_unreachable", f"{url}: {type(e).__name__} {e}") from e
    try:
        body = json.loads(raw)
    except ValueError as e:
        raise FetchError("profile_malformed", f"{url}: not JSON") from e
    log.info("profile fetched %s status=200 resolved=%s", url, ",".join(addrs))
    return Fetched(url, 200, headers, body, addrs)


def cache_control_ok(value: str | None) -> tuple[bool, str]:
    """Overview "Hosting": `public` and `max-age` >= 60. No private, no-store or no-cache."""
    if not value:
        return False, "no Cache-Control header"
    d = {
        p.strip().split("=")[0].lower(): (p.split("=", 1)[1].strip() if "=" in p else "")
        for p in value.split(",")
        if p.strip()
    }
    if {"private", "no-store", "no-cache"} & d.keys():
        return False, f"forbidden directive in {value!r}"
    if "public" not in d:
        return False, "no public directive"
    try:
        age = int(d.get("max-age", ""))
    except ValueError:
        return False, "no max-age"
    return (age >= 60, f"max-age={age}")
