"""Pytest plugin: keep the Playwright trace of a failed e2e test (UCP_TRACE_ON_FAILURE=1).

The plugin does nothing unless the environment variable `UCP_TRACE_ON_FAILURE` is `1`.
It does not change a test, a timeout, a wait or a retry. It wraps two Playwright methods:

- `Browser.new_context`: after the context exists, it starts a trace on the context
  (`context.tracing.start(screenshots=True, snapshots=True, sources=True)`).
- `BrowserContext.close`: it stops the trace, then it closes the context. If the test failed,
  the trace goes to a zip file. If the test did not fail, the trace is discarded.

On a failed test, the plugin also writes one `ps` snapshot of the processes at that time.
Output folder: the environment variable `UCP_CAPTURE_DIR`, subfolder `traces`.
`tools/ci-repro/capture_on_failure.sh` sets both variables and loads this plugin.

Sources (see docs/S7-ci-failure-capture.md):
- Playwright 1.56.0, `docs/src/api/class-tracing.md` (`Tracing.start`, `Tracing.stop`, option `path`).
- pytest 8.4, reference, hook `pytest_runtest_makereport` (hook wrapper, one report for each phase).
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
from collections.abc import Generator
from typing import Any

import pytest

ENV_ON = "UCP_TRACE_ON_FAILURE"
ENV_DIR = "UCP_CAPTURE_DIR"
PS_COMMAND = ["ps", "-eo", "pid,ppid,stat,pcpu,pmem,etime,cmd", "--sort=-pcpu"]


def enabled(env: dict[str, str] | os._Environ[str] | None = None) -> bool:
    """True only if the environment variable `UCP_TRACE_ON_FAILURE` is `1`."""
    source = os.environ if env is None else env
    return source.get(ENV_ON) == "1"


def safe_name(nodeid: str) -> str:
    """A file name from a test id: only letters, digits, `_`, `.` and `-`; 150 characters at most."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("_")[:150] or "test"


def output_dir(env: dict[str, str] | os._Environ[str] | None = None) -> pathlib.Path:
    """The trace folder. Without `UCP_CAPTURE_DIR` it is `.run/failure-capture/traces` in the folder."""
    source = os.environ if env is None else env
    base = source.get(ENV_DIR)
    root = pathlib.Path(base) if base else pathlib.Path.cwd() / ".run" / "failure-capture"
    return root / "traces"


class FailureCapture:
    """Hook implementations and the two wrappers. One instance for each pytest run."""

    def __init__(self, out: pathlib.Path) -> None:
        self.out = out
        self.failed = False
        self.name = ""
        self.saved = 0
        self._orig_new: Any = None
        self._orig_close: Any = None
        self._classes: tuple[Any, Any] | None = None

    # -- pytest hooks ------------------------------------------------------------------------

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(
        self, item: pytest.Item, call: pytest.CallInfo[None]
    ) -> Generator[None, pytest.TestReport, pytest.TestReport]:
        del call
        report = yield
        if report.when == "setup":
            self.failed = False
            self.name = safe_name(item.nodeid)
            self.saved = 0
        if report.failed and report.when in ("setup", "call") and not self.failed:
            self.failed = True
            self._write_ps()
        return report

    # -- Playwright wrappers -----------------------------------------------------------------

    def install(self, browser_cls: Any, context_cls: Any) -> None:
        """Wrap `new_context` and `close`. `uninstall` puts the original methods back."""
        self._classes = (browser_cls, context_cls)
        self._orig_new = browser_cls.new_context
        self._orig_close = context_cls.close
        capture = self

        def new_context(browser: Any, *args: Any, **kwargs: Any) -> Any:
            context = capture._orig_new(browser, *args, **kwargs)
            try:
                context.tracing.start(screenshots=True, snapshots=True, sources=True)
                context._ucp_traced = True
            except Exception as error:  # the trace is a help only: it must not fail a test
                print(f"ucp_failure_capture: no trace: {error}", file=sys.stderr)
            return context

        def close(context: Any, *args: Any, **kwargs: Any) -> Any:
            if getattr(context, "_ucp_traced", False):
                context._ucp_traced = False
                try:
                    if capture.failed:
                        capture.out.mkdir(parents=True, exist_ok=True)
                        capture.saved += 1
                        path = capture.out / f"{capture.name}-{capture.saved}.zip"
                        context.tracing.stop(path=str(path))
                    else:
                        context.tracing.stop()
                except Exception as error:  # for example the context is closed already
                    print(f"ucp_failure_capture: trace not saved: {error}", file=sys.stderr)
            return capture._orig_close(context, *args, **kwargs)

        browser_cls.new_context = new_context
        context_cls.close = close

    def uninstall(self) -> None:
        if self._classes is not None:
            self._classes[0].new_context = self._orig_new
            self._classes[1].close = self._orig_close
            self._classes = None

    # -- the ps snapshot ---------------------------------------------------------------------

    def _write_ps(self) -> None:
        try:
            self.out.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                PS_COMMAND, capture_output=True, text=True, timeout=10, check=False
            )
            text = result.stdout or f"ps gave no output: exit {result.returncode}: {result.stderr}"
        except (OSError, subprocess.SubprocessError) as error:
            text = f"ps not available: {error}"
        try:
            (self.out / f"{self.name}-ps-at-failure.txt").write_text(text, encoding="utf-8")
        except OSError as error:
            print(f"ucp_failure_capture: no ps file: {error}", file=sys.stderr)


def pytest_configure(config: pytest.Config) -> None:
    if not enabled():
        return
    from playwright.sync_api import Browser, BrowserContext

    capture = FailureCapture(output_dir())
    capture.install(Browser, BrowserContext)
    config.pluginmanager.register(capture, "ucp-failure-capture")
    config.add_cleanup(capture.uninstall)
