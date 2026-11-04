"""Guard: the e2e fixtures leave no asyncio event loop running in the main thread.

While a `sync_playwright()` instance is open, `asyncio.get_running_loop()` returns a running
loop in the main thread, and `asyncio.run()` raises RuntimeError. The `browser` fixture in
`conftest.py` has module scope, so Playwright is stopped when the last e2e module ends. This
file sorts after the other e2e modules. If the fixture scope goes back to "session", the
Playwright instance of an earlier module is still open here and these tests fail.

Sources:
- https://docs.python.org/3.12/library/asyncio-runner.html#asyncio.run
  ("This function cannot be called when another asyncio event loop is running in the same thread.")
- https://github.com/microsoft/playwright-python/blob/v1.56.0/playwright/sync_api/_context_manager.py
"""

from __future__ import annotations

import asyncio

from playwright.sync_api import sync_playwright


async def _one() -> int:
    return 1


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def test_no_event_loop_runs_after_the_browser_modules() -> None:
    assert _running_loop() is None
    assert asyncio.run(_one()) == 1


def test_playwright_sync_instance_holds_the_loop_only_while_open() -> None:
    """The reason for the module scope: this is how Playwright 1.56.0 behaves."""
    with sync_playwright():
        assert _running_loop() is not None
    assert _running_loop() is None
    assert asyncio.run(_one()) == 1
