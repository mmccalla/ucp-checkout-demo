"""Platform profile resolution at the Business (AC-11, AC-95, AC-108).

- `UCP-Agent` carries the profile URL as `profile="<url>"` (overview, "Profile Advertisement").
- The URL must be HTTPS and its path must be `/.well-known/ucp` (AC-11, AC-108).
- The fetch uses `ucp_core.netguard.fetch_profile`: no redirect, size bound, address check
  before the connection (overview "Fetching").
- The profile must validate against `profile.json#/$defs/platform_profile`.
- The cache keeps a profile for `max-age` seconds, at most 300 s.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ucp_core import netguard, profile_check, tlsctx
from ucp_core.constants import LOOPBACK_HOST
from ucp_core.schema_registry import SchemaRegistry

PROFILE_RE = re.compile(r'(?:^|[;,\s])profile="([^"]+)"')
MAX_TTL = 300

Fetcher = Callable[[str], tuple[dict[str, Any], dict[str, str]]]


class ProfileProblem(Exception):
    def __init__(self, status: int, code: str, content: str):
        super().__init__(content)
        self.status, self.code, self.content = status, code, content


SUITE_PROFILE_PATH = "/profiles/shopping-agent.json"  # `AgentProfileServer.PROFILE_PATH` at 016ecbc
SUITE_HOSTS = ("localhost", "127.0.0.1")


def profile_url(ucp_agent: str | None, ci_http_port: int | None = None) -> str:
    """Return the profile URL of `UCP-Agent`.

    `ci_http_port` is the one CI-only seam (spec T-114, option (a)). `None` means no seam: only
    `https` and `/.well-known/ucp` pass. With a port, one more URL passes: `http`, host
    `localhost` or `127.0.0.1`, exactly that port, path `/profiles/shopping-agent.json`, no
    user, query or fragment. Any other `http` URL is refused. `main.py` sets the port only in
    MODE=ci, inside a network namespace that has only `lo` (T-109).
    """
    if not ucp_agent:
        raise ProfileProblem(400, "invalid_profile_url", "The UCP-Agent header is missing.")
    m = PROFILE_RE.search(ucp_agent)
    if not m:
        raise ProfileProblem(400, "invalid_profile_url", "UCP-Agent has no profile URL.")
    url = m.group(1)
    u = urllib.parse.urlsplit(url)
    try:
        port = u.port
    except ValueError:
        port = None
    ci_ok = (
        ci_http_port is not None
        and u.scheme == "http"
        and u.hostname in SUITE_HOSTS
        and port == ci_http_port
        and u.username is None
        and u.password is None
        and u.path == SUITE_PROFILE_PATH
    )
    if (u.scheme != "https" and not ci_ok) or not u.hostname:
        raise ProfileProblem(400, "invalid_profile_url", "The profile URL must use HTTPS.")
    if (not ci_ok and u.path != "/.well-known/ucp") or u.query or u.fragment:
        raise ProfileProblem(
            400, "invalid_profile_url", "The profile URL must point to /.well-known/ucp."
        )
    return url


def default_fetcher(url: str) -> tuple[dict[str, Any], dict[str, str]]:
    f = netguard.fetch_profile(url, LOOPBACK_HOST, verify=tlsctx.client_context())
    if not isinstance(f.body, dict):
        raise netguard.FetchError("profile_malformed", f"{url}: not a JSON object")
    return f.body, f.headers


def ci_fetcher(url: str) -> tuple[dict[str, Any], dict[str, str]]:
    """MODE=ci only: like `default_fetcher`. `profile_url` has already limited `http` to one URL."""
    f = netguard.fetch_profile(
        url, LOOPBACK_HOST, verify=tlsctx.client_context(), ci_http_loopback=True
    )
    if not isinstance(f.body, dict):
        raise netguard.FetchError("profile_malformed", f"{url}: not a JSON object")
    return f.body, f.headers


def _ttl(headers: dict[str, str]) -> int:
    m = re.search(r"max-age=(\d+)", headers.get("cache-control", ""))
    return min(int(m.group(1)), MAX_TTL) if m else 0


@dataclass
class Resolver:
    registry: SchemaRegistry
    fetcher: Fetcher = default_fetcher
    cache: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict)
    ci_http_port: int | None = None  # MODE=ci only: the suite port of the one http URL (T-114)
    ci_http_guard: Callable[[], bool] = lambda: False  # checked before each use (T-114 clause 2)

    def _http_port(self) -> int | None:
        return self.ci_http_port if self.ci_http_port is not None and self.ci_http_guard() else None

    def resolve(self, ucp_agent: str | None) -> dict[str, Any]:
        url = profile_url(ucp_agent, self._http_port())
        hit = self.cache.get(url)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        try:
            body, headers = self.fetcher(url)
        except netguard.BlockedAddress as e:
            raise ProfileProblem(400, "invalid_profile_url", f"Address refused: {e.reason}") from e
        except netguard.FetchError as e:
            status = 422 if e.code == "profile_malformed" else 424
            raise ProfileProblem(status, e.code, "The platform profile: " + e.detail) from e
        issues = profile_check.schema_issues(self.registry, body, "platform_profile")
        if issues:
            raise ProfileProblem(422, "profile_malformed", "; ".join(issues[:3]))
        ttl = _ttl({k.lower(): v for k, v in headers.items()})
        self.cache[url] = (time.monotonic() + ttl, body)
        return body

    def cached(self, ucp_agent: str | None) -> dict[str, Any] | None:
        """For the sample hook (P6): return the profile only from the cache. No fetch."""
        try:
            url = profile_url(ucp_agent, self._http_port())
        except ProfileProblem:
            return None
        hit = self.cache.get(url)
        return hit[1] if hit else None
