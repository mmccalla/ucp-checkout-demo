"""The CI workflow pins every action to a full commit SHA and uses no `latest` (project rule, 28 Oct 2026)."""

from __future__ import annotations

import re

from ucp_core.constants import ROOT

WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yaml").read_text()
USES = re.findall(r"^\s*-?\s*uses:\s*(\S+)", WORKFLOW, re.M)


def test_workflow_uses_actions() -> None:
    assert len(USES) >= 2


def test_every_action_is_pinned_to_a_full_commit_sha() -> None:
    for ref in USES:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), ref


def test_every_pinned_action_has_a_version_comment() -> None:
    lines = WORKFLOW.splitlines()
    for number, line in enumerate(lines):
        if re.match(r"\s*-?\s*uses:", line):
            assert re.search(r"#.*\bv\d+\.\d+", lines[number - 1]), line


def test_no_latest_in_the_workflow() -> None:
    code = [ln for ln in WORKFLOW.splitlines() if not ln.lstrip().startswith("#")]
    assert not [ln for ln in code if re.search(r"\blatest\b", ln)]


def test_tool_versions_are_pinned() -> None:
    assert 'version: "0.13.6"' in WORKFLOW
    assert "uv python install 3.12.16" in WORKFLOW
    assert "--rev 6dd2a613d38828c97dca723bdb9ccfc79b2a7e80" in WORKFLOW
    assert "ubuntu-24.04" in WORKFLOW


def test_job_does_not_set_mode_ci() -> None:
    """MODE=ci gives each process its own signing key, so G8 (a second process) gets HTTP 401."""
    code = [ln for ln in WORKFLOW.splitlines() if not ln.lstrip().startswith("#")]
    assert not [ln for ln in code if re.match(r"\s*MODE\s*:", ln)]
