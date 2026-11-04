"""CI failure capture (docs/S7-ci-failure-capture.md): the trace plugin and the wrapper script.

The tests use no browser. The plugin wraps two Playwright methods. The tests give it stand-in
classes. The wrapper script runs a command that passes and a command that fails.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import subprocess
import sys
from types import ModuleType
from typing import Any

from ucp_core.constants import ROOT

TOOLS = ROOT / "tools" / "ci-repro"
SCRIPT = TOOLS / "capture_on_failure.sh"
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yaml").read_text()


def load_plugin() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "ucp_failure_capture_under_test", TOOLS / "ucp_failure_capture.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTracing:
    def __init__(self) -> None:
        self.started: dict[str, Any] | None = None
        self.stopped: list[dict[str, Any]] = []

    def start(self, **kwargs: Any) -> None:
        self.started = kwargs

    def stop(self, **kwargs: Any) -> None:
        self.stopped.append(kwargs)
        if "path" in kwargs:
            pathlib.Path(kwargs["path"]).write_bytes(b"zip")


class FakeContext:
    def __init__(self) -> None:
        self.tracing = FakeTracing()
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class FakeBrowser:
    def new_context(self, **kwargs: Any) -> FakeContext:
        del kwargs
        return FakeContext()


def test_plugin_is_off_unless_the_variable_is_1() -> None:
    plugin = load_plugin()
    assert not plugin.enabled({})
    assert not plugin.enabled({"UCP_TRACE_ON_FAILURE": "0"})
    assert plugin.enabled({"UCP_TRACE_ON_FAILURE": "1"})


def test_plugin_names_and_folder() -> None:
    plugin = load_plugin()
    name = plugin.safe_name("tests/s3/e2e/test_g7_flow.py::test_ac23[a b]")
    assert re.fullmatch(r"[A-Za-z0-9_.-]+", name) and len(name) <= 150
    assert plugin.output_dir({"UCP_CAPTURE_DIR": "/x"}) == pathlib.Path("/x/traces")
    assert plugin.output_dir({}).parts[-3:] == (".run", "failure-capture", "traces")


def test_plugin_saves_the_trace_of_a_failed_test_only(tmp_path: pathlib.Path) -> None:
    plugin = load_plugin()
    capture = plugin.FailureCapture(tmp_path / "traces")
    original = (FakeBrowser.new_context, FakeContext.close)
    capture.install(FakeBrowser, FakeContext)
    try:
        passed = FakeBrowser().new_context(viewport=1)
        assert passed.tracing.started == {"screenshots": True, "snapshots": True, "sources": True}
        passed.close()
        assert passed.tracing.stopped == [{}] and passed.closed == 1  # stop, no file
        capture.failed, capture.name = True, "t"
        failed = FakeBrowser().new_context()
        failed.close()
        assert failed.closed == 1
        assert failed.tracing.stopped == [{"path": str(tmp_path / "traces" / "t-1.zip")}]
        assert (tmp_path / "traces" / "t-1.zip").read_bytes() == b"zip"
    finally:
        capture.uninstall()
    assert (FakeBrowser.new_context, FakeContext.close) == original


def run_script(tmp_path: pathlib.Path, *command: str) -> tuple[int, pathlib.Path]:
    out = tmp_path / "capture"
    env = {**os.environ, "UCP_CAPTURE_DIR": str(out)}
    done = subprocess.run(
        ["bash", str(SCRIPT), *command], env=env, capture_output=True, text=True, check=False
    )
    return done.returncode, out


def test_script_leaves_nothing_when_the_command_passes(tmp_path: pathlib.Path) -> None:
    code, out = run_script(tmp_path, sys.executable, "-c", "pass")
    assert code == 0
    assert not out.exists()


def test_script_keeps_the_capture_when_the_command_fails(tmp_path: pathlib.Path) -> None:
    code, out = run_script(tmp_path, sys.executable, "-c", "raise SystemExit(3)")
    assert code == 3  # the exit code of the command
    for name in ("vmstat.txt", "ps.txt", "dmesg.txt", "capture-info.txt"):
        assert (out / name).is_file(), name
    info = (out / "capture-info.txt").read_text()
    assert "exit code: 3" in info
    assert re.search(r"^dmesg: (ok|not available)", info, re.M)  # dmesg can be restricted


def test_workflow_runs_the_wrapper_and_uploads_only_on_failure() -> None:
    assert "tools/ci-repro/capture_on_failure.sh uv run --no-sync pytest -q" in WORKFLOW
    step = WORKFLOW.split("uses: actions/upload-artifact@", 1)[1]
    assert re.match(r"[0-9a-f]{40}\n", step)
    assert "if: failure()" in step
    assert "retention-days: 7" in step
