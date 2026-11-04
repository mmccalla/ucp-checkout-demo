"""T-93, T-114: the CI-only seams of the Business for the conformance suite (MODE=ci only).

- The one `http` suite profile URL (exact scheme, host, port, path). one test for each guard
  is below (T-114). T-115 (the webhook URL scheme) has its tests at the end.
- The path `/testing/simulate-shipping/{id}`.
Demo mode has none of them (AC-107).
"""

from __future__ import annotations

import asyncio
import json
import pathlib
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from ucp_core import jwk, netns
from business_app import order_events
from business_app import main as bmain
from business_app import platform_profiles as pp
from ucp_core import netguard


def test_http_profile_is_refused_by_default() -> None:
    with pytest.raises(pp.ProfileProblem) as e:
        pp.profile_url(AGENT)
    assert e.value.code == "invalid_profile_url"


def test_http_loopback_profile_is_accepted_in_ci_seam() -> None:
    assert pp.profile_url(AGENT, 8285) == ("http://localhost:8285/profiles/shopping-agent.json")


@pytest.mark.parametrize(
    "agent",
    [
        'profile="http://example.com/profiles/shopping-agent.json"',  # not a loopback name
        'profile="http://localhost:8285/other.json"',  # other path
        'profile="http://localhost:8285/profiles/shopping-agent.json?x=1"',
        'profile="ftp://localhost/.well-known/ucp"',
        'profile="http://localhost:8443/.well-known/ucp"',  # http needs the suite path (AC-108)
    ],
)
def test_ci_seam_refuses_other_urls(agent: str) -> None:
    with pytest.raises(pp.ProfileProblem):
        pp.profile_url(agent, 8285)


def test_https_well_known_still_works_with_seam() -> None:
    url = "https://localhost:8443/.well-known/ucp"
    assert pp.profile_url(f'profile="{url}"', 8285) == url


def test_http_needs_loopback_addresses_even_in_seam() -> None:
    url = "http://localhost:8285/profiles/shopping-agent.json"
    with pytest.raises(netguard.BlockedAddress):
        netguard.resolve_checked(url, "127.0.0.1", lambda h, p: ["93.184.216.34"], True)
    assert netguard.resolve_checked(url, "127.0.0.1", lambda h, p: ["127.0.0.1"], True) == [
        "127.0.0.1"
    ]


def test_http_is_refused_without_the_seam() -> None:
    url = "http://localhost:8285/profiles/shopping-agent.json"
    with pytest.raises(netguard.FetchError):
        netguard.resolve_checked(url, "127.0.0.1", lambda h, p: ["127.0.0.1"])


@pytest.mark.parametrize(("mode", "mounted"), [("ci", True), ("demo", False)])
def test_simulate_shipping_only_in_ci(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, mode: str, mounted: bool
) -> None:
    monkeypatch.setenv("BUSINESS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UCP_TRACING", "0")
    app = bmain.create_app(mode=mode, require_signatures=False)
    paths = {getattr(r, "path", "") for r in app.router.routes}
    assert ("/testing/simulate-shipping/{id}" in paths) is mounted


# --- T-114: guards of the profile URL seam (one test for each guard) ---

SUITE_URL = "http://localhost:8285/profiles/shopping-agent.json"
AGENT = f'profile="{SUITE_URL}"'
ENV_ON = {
    "BUSINESS_CI_SUITE_PROFILE_HTTP": "1",
    "BUSINESS_CI_SUITE_PROFILE_PORT": "8285",
    "BUSINESS_CI_NETNS": "1",
}


@pytest.fixture
def lo_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netns, "loopback_only", lambda path=netns.PROC_NET_DEV: True)


@pytest.fixture
def two_nics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netns, "loopback_only", lambda path=netns.PROC_NET_DEV: False)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_exact_suite_url_is_accepted_with_the_port(host: str) -> None:
    url = f"http://{host}:8285/profiles/shopping-agent.json"
    assert pp.profile_url(f'profile="{url}"', 8285) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:9999/profiles/shopping-agent.json",  # other port
        "http://localhost:8285/.well-known/ucp",  # other path
        "http://localhost:8285/profiles/other.json",
        "http://localhost/profiles/shopping-agent.json",  # no port
        "http://example.com:8285/profiles/shopping-agent.json",  # other host
        "http://[::1]:8285/profiles/shopping-agent.json",
        "http://user:pw@localhost:8285/profiles/shopping-agent.json",  # credentials
        "http://localhost:8285/profiles/shopping-agent.json?x=1",  # query
        "http://localhost:8285/profiles/shopping-agent.json#f",  # fragment
        "ftp://localhost:8285/profiles/shopping-agent.json",  # other scheme
        "https://localhost:8285/profiles/shopping-agent.json",  # https needs the well-known path
    ],
)
def test_any_other_url_is_refused_in_ci(url: str) -> None:
    with pytest.raises(pp.ProfileProblem) as e:
        pp.profile_url(f'profile="{url}"', 8285)
    assert e.value.code == "invalid_profile_url"


def test_https_well_known_still_works_with_the_seam() -> None:
    url = "https://localhost:8443/.well-known/ucp"
    assert pp.profile_url(f'profile="{url}"', 8285) == url


def test_no_port_means_no_seam() -> None:
    with pytest.raises(pp.ProfileProblem) as e:
        pp.profile_url(AGENT, None)
    assert e.value.code == "invalid_profile_url"


def test_all_guards_on_gives_the_port(lo_only: None) -> None:
    assert bmain.ci_suite_profile_port("ci", ENV_ON) == 8285


def test_port_default_is_8285(lo_only: None) -> None:
    env = {k: v for k, v in ENV_ON.items() if k != "BUSINESS_CI_SUITE_PROFILE_PORT"}
    assert bmain.ci_suite_profile_port("ci", env) == 8285


def test_switch_off_rejects_suite_url(lo_only: None) -> None:
    """T-114 clause 4. The switch is off or not set, in MODE=ci and in the namespace."""
    for env in (
        {k: v for k, v in ENV_ON.items() if k != "BUSINESS_CI_SUITE_PROFILE_HTTP"},
        {**ENV_ON, "BUSINESS_CI_SUITE_PROFILE_HTTP": "0"},
    ):
        assert bmain.ci_suite_profile_port("ci", env) is None
        r = pp.Resolver(registry=None)  # type: ignore[arg-type]
        with pytest.raises(pp.ProfileProblem) as e:
            r.resolve(AGENT)
        assert e.value.code == "invalid_profile_url"


@pytest.mark.parametrize("drop", ["BUSINESS_CI_SUITE_PROFILE_HTTP", "BUSINESS_CI_NETNS"])
def test_missing_switch_or_flag_turns_it_off(lo_only: None, drop: str) -> None:
    env = {k: v for k, v in ENV_ON.items() if k != drop}
    assert bmain.ci_suite_profile_port("ci", env) is None


def test_demo_mode_turns_it_off(lo_only: None) -> None:
    assert bmain.ci_suite_profile_port("demo", ENV_ON) is None


def test_other_interface_turns_it_off(two_nics: None) -> None:
    assert bmain.ci_suite_profile_port("ci", ENV_ON) is None


def test_namespace_is_checked_again_before_each_use() -> None:
    state = {"ok": True}
    r = pp.Resolver(registry=None)  # type: ignore[arg-type]
    r.ci_http_port = 8285
    r.ci_http_guard = lambda: state["ok"]
    assert r._http_port() == 8285
    state["ok"] = False
    assert r._http_port() is None
    with pytest.raises(pp.ProfileProblem):
        r.resolve(AGENT)


def test_bad_port_value_is_an_error(lo_only: None) -> None:
    with pytest.raises(RuntimeError):
        bmain.ci_suite_profile_port("ci", {**ENV_ON, "BUSINESS_CI_SUITE_PROFILE_PORT": "x"})


def _app(mode: str, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("BUSINESS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UCP_TRACING", "0")
    return bmain.create_app(mode=mode, require_signatures=False, key=jwk.ephemeral())


def test_demo_app_rejects_suite_url_with_400(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, lo_only: None
) -> None:
    """T-114 clause 3: MODE=demo, all env set, exact suite URL: 400 invalid_profile_url."""
    for k, v in ENV_ON.items():
        monkeypatch.setenv(k, v)
    app = _app("demo", tmp_path, monkeypatch)
    assert app.state.gate.resolver.ci_http_port is None
    c = TestClient(app)
    r = c.post(
        "/checkout-sessions",
        content=json.dumps({"line_items": []}),
        headers={"UCP-Agent": AGENT, "Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_profile_url"


def test_ci_app_has_the_seam_only_with_all_guards(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, lo_only: None
) -> None:
    for k, v in ENV_ON.items():
        monkeypatch.setenv(k, v)
    on = _app("ci", tmp_path, monkeypatch).state.gate.resolver
    assert on.ci_http_port == 8285 and on.fetcher is pp.ci_fetcher
    monkeypatch.setenv("BUSINESS_CI_SUITE_PROFILE_HTTP", "0")
    off = _app("ci", tmp_path, monkeypatch).state.gate.resolver
    assert off.ci_http_port is None and off.fetcher is not pp.ci_fetcher


# --- T-115: the scheme of the webhook URL ---

HOOK_PATH = "/webhooks/partners/test_partner/events/order"
SUITE_HOOK = f"http://localhost:8284{HOOK_PATH}"
HOOK_ENV = {
    "BUSINESS_CI_SUITE_WEBHOOK_HTTP": "1",
    "BUSINESS_CI_SUITE_WEBHOOK_PORT": "8284",
    "BUSINESS_CI_NETNS": "1",
}


class Hook:
    """Send one webhook attempt through `ObservedTransport`. Collect the log rows."""

    def __init__(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BUSINESS_EVENTS", str(tmp_path / "business.jsonl"))
        self.log = tmp_path / "business.jsonl"
        self.sent: list[httpx2.Request] = []

    def send(self, url: str, **kw: Any) -> str | None:
        def inner(req: httpx2.Request) -> httpx2.Response:
            self.sent.append(req)
            return httpx2.Response(200)

        t = order_events.ObservedTransport(httpx2.MockTransport(inner), **kw)
        req = httpx2.Request("POST", url, headers={"webhook-id": "w1"}, content=b"{}")
        try:
            asyncio.run(t.handle_async_request(req))
        except httpx2.ConnectError:
            pass
        rows = (
            [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []
        )
        return str(rows[-1].get("code")) if rows and "code" in rows[-1] else None


@pytest.fixture
def hook(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Hook:
    return Hook(tmp_path, monkeypatch)


CI_ON: dict[str, Any] = {"mode": "ci", "suite_webhook_port": 8284, "ci_guard": lambda: True}


def test_webhook_http_refused_in_demo(hook: Hook) -> None:  # T-115 clause 1
    for url in (SUITE_HOOK, "http://127.0.0.1:8284/x", "http://localhost:1/x"):
        assert hook.send(url) == "blocked_non_https"
    # the same URL is refused in demo even if every other setting is on
    assert hook.send(SUITE_HOOK, mode="demo", suite_webhook_port=8284, ci_guard=lambda: True) == (
        "blocked_non_https"
    )
    assert hook.sent == []  # no connection was opened


def test_webhook_https_loopback_delivered_in_demo(hook: Hook) -> None:  # T-115 clause 1
    assert hook.send("https://localhost:8443/webhooks/ucp/orders") is None
    assert hook.send("https://127.0.0.1:8443/webhooks/ucp/orders") is None
    assert len(hook.sent) == 2


def test_webhook_suite_url_delivered_in_ci(hook: Hook) -> None:  # T-115 clause 2
    assert hook.send(SUITE_HOOK, **CI_ON) is None
    assert len(hook.sent) == 1


@pytest.mark.parametrize(
    "url",
    [
        f"https://localhost:8284{HOOK_PATH}",  # https is allowed by the general rule: see below
        f"http://127.0.0.1:8284{HOOK_PATH}",  # another host
        f"http://localhost:9999{HOOK_PATH}",  # another port
        "http://localhost:8284/webhooks/other",  # another path
        f"http://localhost:8284{HOOK_PATH}?x=1",  # query
        f"http://localhost:8284{HOOK_PATH}#f",  # fragment
        f"http://user:pw@localhost:8284{HOOK_PATH}",  # credentials
        f"http://localhost{HOOK_PATH}",  # no port
    ],
)
def test_webhook_other_http_url_refused_in_ci(hook: Hook, url: str) -> None:  # T-115 clause 2
    code = hook.send(url, **CI_ON)
    if url.startswith("https://"):
        assert code is None  # an https URL to loopback is not an http URL
    else:
        assert code == "blocked_non_https"
        assert hook.sent == []


def test_webhook_suite_url_refused_outside_ci(hook: Hook) -> None:  # T-115 clause 3
    assert hook.send(SUITE_HOOK, **{**CI_ON, "mode": "demo"}) == "blocked_non_https"
    assert (
        bmain.ci_suite_webhook_port("demo", {**HOOK_ENV, "BUSINESS_CI_SUITE_WEBHOOK_HTTP": "1"})
        is None
    )


def test_webhook_suite_url_refused_outside_netns(
    hook: Hook, two_nics: None, monkeypatch: pytest.MonkeyPatch
) -> None:  # T-115 clause 4
    assert bmain.ci_suite_webhook_port("ci", HOOK_ENV) is None
    assert hook.send(SUITE_HOOK, **{**CI_ON, "ci_guard": lambda: bmain.ci_netns_ok(HOOK_ENV)}) == (
        "blocked_non_https"
    )
    assert hook.sent == []


def test_webhook_suite_url_refused_when_switch_off(hook: Hook, lo_only: None) -> None:  # clause 5
    for drop in (
        {k: v for k, v in HOOK_ENV.items() if k != "BUSINESS_CI_SUITE_WEBHOOK_HTTP"},
        {**HOOK_ENV, "BUSINESS_CI_SUITE_WEBHOOK_HTTP": "0"},
    ):
        port = bmain.ci_suite_webhook_port("ci", drop)
        assert port is None
        assert hook.send(SUITE_HOOK, mode="ci", suite_webhook_port=port, ci_guard=lambda: True) == (
            "blocked_non_https"
        )
    assert bmain.ci_suite_webhook_port("ci", HOOK_ENV) == 8284


def test_webhook_non_loopback_host_refused_in_every_mode(hook: Hook) -> None:  # T-115 clause 6
    for kw in ({}, CI_ON):
        assert hook.send("https://example.com/x", **kw) == "blocked_non_loopback"
        assert hook.send("http://example.com:8284" + HOOK_PATH, **kw) == "blocked_non_loopback"


def test_webhook_profile_url_must_be_https() -> None:  # signatures.md 622 to 625
    assert bmain.webhook_profile_url("https://localhost:9443", {}) == (
        "https://localhost:9443/.well-known/ucp"
    )
    assert bmain.webhook_profile_url(
        "http://127.0.0.1:18201",
        {"BUSINESS_WEBHOOK_PROFILE_URL": "https://localhost:9443/.well-known/ucp"},
    ).startswith("https://")
    with pytest.raises(RuntimeError):
        bmain.webhook_profile_url("http://127.0.0.1:18201", {})
    with pytest.raises(RuntimeError):
        bmain.webhook_profile_url(
            "https://x", {"BUSINESS_WEBHOOK_PROFILE_URL": "http://x/.well-known/ucp"}
        )


# --- T-115 clauses 7 and 8, and the start-up check of the suite ports ---


BAD_PORTS = ["x", "", "70000", "0", "-1", "80.5", "port"]


def _start_ci_app(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, port_var: str, bad: str
) -> None:
    for k, v in {**ENV_ON, **HOOK_ENV}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv(port_var, bad)
    with pytest.raises(bmain.ConfigurationError) as err:
        _app("ci", tmp_path, monkeypatch)  # create_app raises: no app object, nothing to serve
    msg = str(err.value)
    assert "configuration error" in msg and port_var in msg and "does not start" in msg


@pytest.mark.parametrize("bad", BAD_PORTS)
def test_webhook_bad_port_fails_startup(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, lo_only: None, bad: str
) -> None:  # T-115 clause 9
    _start_ci_app(tmp_path, monkeypatch, "BUSINESS_CI_SUITE_WEBHOOK_PORT", bad)


@pytest.mark.parametrize("bad", BAD_PORTS)
def test_profile_bad_port_fails_startup(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, lo_only: None, bad: str
) -> None:  # T-114 clause 5
    _start_ci_app(tmp_path, monkeypatch, "BUSINESS_CI_SUITE_PROFILE_PORT", bad)


def test_webhook_switch_outside_netns_does_not_crash(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, two_nics: None
) -> None:  # T-115 clause 7
    for k, v in {**ENV_ON, **HOOK_ENV}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("BUSINESS_CI_SUITE_WEBHOOK_PORT", "x")  # a wrong port is not read here
    monkeypatch.setenv("BUSINESS_CI_SUITE_PROFILE_PORT", "x")
    app = _app("ci", tmp_path, monkeypatch)
    assert app.state.gate.resolver.ci_http_port is None
    assert bmain.ci_suite_webhook_port("ci") is None


def test_webhook_non_loopback_http_reports_non_loopback(hook: Hook) -> None:  # T-115 clause 8
    url = "http://example.com" + HOOK_PATH
    for kw in ({}, {**CI_ON, "mode": "demo"}, CI_ON):
        assert hook.send(url, **kw) == "blocked_non_loopback"


def test_webhook_loopback_http_reports_non_https(hook: Hook) -> None:  # T-115 clause 8
    for url in ("http://127.0.0.1:8284" + HOOK_PATH, "http://localhost:9999" + HOOK_PATH):
        assert hook.send(url) == "blocked_non_https"
        assert hook.send(url, **CI_ON) == "blocked_non_https"
