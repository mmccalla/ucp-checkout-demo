"""DM-26 containment of G5 (accepted as CI-only with 2 conditions, 28 Oct 2026).

1. The gate fails (exit 2) if `unshare` is not available.
2. The gate checks that the namespace is a new one and has only the `lo` interface.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import gate
import pytest

OUTER = "net:[4026531840]"
INNER = "net:[4026532999]"


def test_unshare_missing_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert gate.unshare_problem() == "unshare is not installed"


def test_unshare_that_does_not_work_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, "", "unshare failed: Operation not permitted")

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/unshare")
    monkeypatch.setattr(subprocess, "run", fake_run)
    problem = gate.unshare_problem()
    assert problem is not None and "Operation not permitted" in problem


def test_main_exits_2_and_does_not_run_the_suite_without_unshare(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: object
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    called: list[str] = []
    monkeypatch.setattr(gate, "ensure_suite", lambda *a, **k: called.append("ensure_suite"))
    monkeypatch.setattr(sys, "argv", ["gate.py", f"--report-dir={tmp_path}"])
    assert gate.main() == 2
    assert called == []  # no clone, no suite run
    assert "unshare is not installed" in capsys.readouterr().err


def test_loopback_only_new_namespace_is_ok() -> None:
    assert gate.loopback_problems(["lo"], OUTER, INNER) == []


def test_other_interface_is_a_failure() -> None:
    problems = gate.loopback_problems(["eth0", "lo"], OUTER, INNER)
    assert any("other than `lo`: eth0" in p for p in problems)


def test_no_loopback_interface_is_a_failure() -> None:
    assert any("no `lo`" in p for p in gate.loopback_problems([], OUTER, INNER))


def test_same_namespace_as_the_caller_is_a_failure() -> None:
    problems = gate.loopback_problems(["lo"], INNER, INNER)
    assert any("not a new network namespace" in p for p in problems)


def test_missing_caller_namespace_is_a_failure() -> None:
    assert gate.loopback_problems(["lo"], None, INNER) != []


def test_real_namespace_has_only_lo() -> None:
    if gate.unshare_problem() is not None:
        # The gate fails in this case (tests above). There is nothing to measure here.
        return
    r = subprocess.run(
        [
            "unshare",
            "--map-root-user",
            "--net",
            "bash",
            "-c",
            "ip link set lo up; cat /proc/net/dev",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    names = sorted(ln.split(":", 1)[0].strip() for ln in r.stdout.splitlines()[2:])
    assert names == ["lo"]
