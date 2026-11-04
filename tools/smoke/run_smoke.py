"""Headless S0 smoke run (spec 4.2 steps 1-4) with the local Google Chrome.

Run: uv run python tools/smoke/run_smoke.py OUT_DIR
It does not sign in to a Google Account. It records isReadyToPay, the button,
the result of a trusted click on the button (loadPaymentData), the pop-up URL host
and path, and the pay.google.com network status codes. Query strings are not stored.
"""

import json
import pathlib
import sys
import time
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Browser, ConsoleMessage, Response, sync_playwright

CHROME = "/usr/bin/google-chrome"
CASES = [
    ("tls-valid", "https://localhost:8443/smoke/?case=valid"),
    ("tls-bad-request", "https://localhost:8443/smoke/?case=bad-request"),
    ("loopback-http-valid", "http://localhost:8101/smoke/?case=valid"),
]


def strip(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def run_case(browser: Browser, name: str, url: str) -> dict[str, Any]:
    ctx = browser.new_context(ignore_https_errors=True, locale="en-GB")
    page = ctx.new_page()
    out: dict[str, Any] = {"case": name, "url": url, "console": [], "network": [], "popups": []}

    def on_console(m: ConsoleMessage) -> None:
        out["console"].append(f"{m.type}: {m.text[:300]}")

    def on_response(r: Response) -> None:
        if "google" in r.url:
            out["network"].append({"status": r.status, "url": strip(r.url)})

    page.on("console", on_console)
    ctx.on("response", on_response)
    page.goto(url, wait_until="load")
    page.wait_for_function(
        "window.__smoke && window.__smoke.some(e => e.step === 'createButton' "
        "|| e.step === 'main' || e.step === 'pay.js')",
        timeout=30000,
    )
    page.wait_for_timeout(1500)
    button = page.locator("#gpay-container button")
    out["button_count"] = button.count()
    if out["button_count"]:
        out["button_label"] = button.first.get_attribute("aria-label")
        try:
            with ctx.expect_page(timeout=15000) as pop_info:
                button.first.click()  # trusted (CDP) user gesture
            pop = pop_info.value
            pop.wait_for_load_state("load", timeout=30000)
            time.sleep(3)
            out["popups"].append(
                {
                    "url": strip(pop.url),
                    "title": pop.title()[:120],
                    "text": pop.inner_text("body")[:600],
                }
            )
            pop.screenshot(path=str(OUT / f"{name}-popup.png"))
            pop.close()  # the user closes the sheet without sign-in -> expect CANCELED
        except Exception as exc:  # no pop-up: sheet or error inside the page
            out["popup_error"] = str(exc)[:300]
        page.wait_for_timeout(4000)
    page.screenshot(path=str(OUT / f"{name}-page.png"), full_page=True)
    out["events"] = page.evaluate("window.__smoke")
    ctx.close()
    return out


if __name__ == "__main__":
    OUT = pathlib.Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True)
        results.append({"chrome": browser.version})
        for name, url in CASES:
            results.append(run_case(browser, name, url))
        browser.close()
    (OUT / "smoke-results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
