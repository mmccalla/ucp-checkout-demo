"""Headless S3 smoke run (AC-103, second run) on the S3 checkout page with the real pay.js.

Run: uv run python tools/smoke/run_smoke_s3.py OUT_DIR  (the layout must run: tools/run_local.sh start)
It goes to the review screen in Auto mode, records isReadyToPay, clicks the real Google Pay
button (trusted CDP click), records the pop-up host and path, closes the pop-up and records the
loadPaymentData result. It does not sign in to a Google Account (that is M-01). Query strings
are not stored.
"""

import json
import pathlib
import sys
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import ConsoleMessage, Response, sync_playwright

CHROME = "/usr/bin/google-chrome"
URL = "https://localhost:8443/checkout/?auto_ms=200"


def strip(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def main(out: pathlib.Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    res: dict[str, Any] = {"url": URL, "console": [], "network": [], "popups": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, headless=True)
        res["chrome"] = browser.version
        ctx = browser.new_context(ignore_https_errors=True, locale="en-GB")
        page = ctx.new_page()

        def on_console(m: ConsoleMessage) -> None:
            res["console"].append(f"{m.type}: {m.text[:300]}")

        def on_response(r: Response) -> None:
            if "google" in r.url:
                res["network"].append({"status": r.status, "url": strip(r.url)})

        page.on("console", on_console)
        ctx.on("response", on_response)
        page.goto(URL, wait_until="load")
        page.locator('input[name="play"][value="auto"]').check()
        page.locator("#start").click()
        page.locator("#add").click(timeout=15000)
        page.locator("#field-buyer-email").fill("buyer@example.com", timeout=15000)
        page.locator("#continue").click()
        page.wait_for_selector("#gpay-container button, #gpay-unavailable", timeout=30000)
        res["screen"] = page.locator("#screen-title").inner_text()
        page.screenshot(path=str(out / "s3-smoke-review.png"), full_page=True)
        button = page.locator("#gpay-container button")
        res["button_count"] = button.count()
        if res["button_count"]:
            res["button_label"] = button.first.get_attribute("aria-label")
            try:
                with ctx.expect_page(timeout=15000) as pop_info:
                    button.first.click()  # trusted (CDP) user gesture
                pop = pop_info.value
                pop.wait_for_load_state("load", timeout=30000)
                res["popups"].append({"url": strip(pop.url), "title": pop.title()})
                pop.screenshot(path=str(out / "s3-smoke-popup.png"))
                pop.close()
            except Exception as e:  # noqa: BLE001 - record the result, do not hide it
                res["popup_error"] = type(e).__name__
            page.wait_for_function(
                "document.querySelector('#buyer-canceled') || "
                "[...document.querySelectorAll('#msg-list button')].some(b => b.textContent.includes('loadPaymentData'))",
                timeout=30000,
            )
        page.wait_for_timeout(500)
        page.screenshot(path=str(out / "s3-smoke-end.png"), full_page=True)
        export = json.loads(page.request.get("https://localhost:8443/api/timeline/export").text())
        res["gpay_rows"] = [
            {k: r.get(k) for k in ("name", "source", "not_ucp", "result", "phase")}
            for r in export["rows"]
            if r.get("kind") == "gpay"
        ]
        res["ucp_ops"] = [r.get("op") for r in export["rows"] if r.get("kind") == "request"]
        res["buyer_text"] = page.locator("#buyer-view").inner_text()[:600]
        browser.close()
    (out / "s3-smoke-results.json").write_text(json.dumps(res, indent=1))
    print(
        json.dumps(
            {
                k: res.get(k)
                for k in (
                    "screen",
                    "button_count",
                    "button_label",
                    "popups",
                    "popup_error",
                    "gpay_rows",
                    "ucp_ops",
                )
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1])))
