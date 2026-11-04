"""G3 unit, S2: Business error bodies (T-102), composed schemas, profile URL (AC-108)."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from business_app import errors, platform_profiles
from ucp_core.constants import ROOT


@pytest.mark.parametrize("status", sorted(errors.PROTOCOL_STATUSES))
def test_t102_protocol_body(status: int) -> None:
    r = errors.protocol(status, "c", "text", retry_after=4, continue_url="https://x/c")
    body = json.loads(bytes(r.body))
    assert body["code"] == "c" and body["content"] == "text"
    assert ("continue_url" in body) == (status in (422, 424))
    assert (r.headers.get("retry-after") == "4") == (status in (429, 503))


def test_t102_400_only_for_listed_codes() -> None:
    for code in errors.PROTOCOL_400_CODES:
        assert errors.protocol(400, code, "x").status_code == 400
    with pytest.raises(ValueError):
        errors.protocol(400, "invalid_request", "x")
    with pytest.raises(ValueError):
        errors.protocol(404, "not_found", "x")


def test_composed_check_is_same() -> None:
    out = subprocess.run(
        [sys.executable, "tools/contracts/compose.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "SAME" in out.stdout


@pytest.mark.parametrize(
    "agent",
    [
        None,
        "",
        'profile="https://h/x"',
        "https://h/.well-known/ucp",
        'profile="http://h/.well-known/ucp"',
    ],
)
def test_ac108_profile_url_rules(agent: str | None) -> None:
    with pytest.raises(platform_profiles.ProfileProblem) as e:
        platform_profiles.profile_url(agent)
    assert (e.value.status, e.value.code) == (400, "invalid_profile_url")


def test_profile_url_ok() -> None:
    url = platform_profiles.profile_url('profile="https://localhost:8443/.well-known/ucp"')
    assert url == "https://localhost:8443/.well-known/ucp"
