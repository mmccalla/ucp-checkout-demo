"""Gate G8 driver (AC-117) and readiness check (AC-58).

It runs against a running loopback layout (`tools/run_local.sh start`). Use `run_g8.sh`: it starts
a clean copy of the layout in a private network namespace, then calls this file.

  g8_driver.py ready  --start-ns N --log FILE     all services answer readiness (AC-58, 120 s)
  g8_driver.py run    --report-dir DIR            100 calls for each operation (AC-117)

The calls go through the Platform client (`platform_app.main.client()`): it uses the Platform key
in `.run/keys` and sends the signed requests of the demo. Each call is timed with `perf_counter`.
The time includes the signing and the response checks of the client.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Any

import g8_stats
import httpx
from ucp_core import tlsctx

ROOT = pathlib.Path(__file__).resolve().parents[2]
READY_LIMIT_S = 120.0  # AC-58


def _ports() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "deploy/ports.env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def ready(start_ns: int, log: pathlib.Path, limit: float = READY_LIMIT_S) -> int:
    """AC-58: poll `/readyz` of the Platform, the Business and the mock PSP until all answer 200."""
    p = _ports()
    host = p["LOOPBACK_HOST"]
    urls = {
        "platform": f"http://{host}:{p['PLATFORM_APP_PORT']}/readyz",
        "business": f"http://{host}:{p['BUSINESS_APP_PORT']}/readyz",
        "psp-mock": f"http://{host}:{p['PSP_MOCK_APP_PORT']}/readyz",
        "platform-tls": f"https://localhost:{p['PLATFORM_TLS_PORT']}/readyz",
        "business-tls": f"https://localhost:{p['BUSINESS_TLS_PORT']}/readyz",
    }
    t_ok: dict[str, float] = {}
    lines: list[str] = []
    while time.monotonic_ns() - start_ns < limit * 1e9 and len(t_ok) < len(urls):
        for name, url in urls.items():
            if name in t_ok:
                continue
            try:
                # The TLS endpoints use the local CA of this layout (T-90), as the Platform does.
                verify = tlsctx.client_context() if url.startswith("https") else True
                r = httpx.get(url, timeout=2.0, verify=verify)
                if r.status_code == 200:
                    t_ok[name] = (time.monotonic_ns() - start_ns) / 1e9
                    lines.append(f"{t_ok[name]:8.2f} s  {name} ready  {url}")
            except (httpx.HTTPError, OSError):
                pass  # the service is not up yet, or the CA file is not written yet
        time.sleep(0.2)
    total = max(t_ok.values()) if len(t_ok) == len(urls) else None
    ok = total is not None and total <= limit
    lines.append(
        f"AC-58 {'PASS' if ok else 'FAIL'}: "
        + (
            f"all {len(urls)} endpoints ready after {total:.2f} s"
            if total is not None
            else "not all ready"
        )
        + f" (limit {limit:g} s)"
    )
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if ok else 1


def _create_body() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from tests.s2.conftest import create_body

    return create_body()


def _update_body(c: dict[str, Any]) -> dict[str, Any]:
    m = c["fulfillment"]["methods"][0]
    return {
        "line_items": [
            {"id": c["line_items"][0]["id"], "item": {"id": "demo_tshirt"}, "quantity": 1}
        ],
        "buyer": {"email": "buyer@example.com", "first_name": "Test", "last_name": "Buyer"},
        "fulfillment": {
            "methods": [
                {
                    "id": m["id"],
                    "type": "shipping",
                    "line_item_ids": m["line_item_ids"],
                    "destinations": m["destinations"],
                    "selected_destination_id": "d1",
                    "groups": [{"id": m["groups"][0]["id"], "selected_option_id": "gb-standard"}],
                }
            ]
        },
    }


def run(report_dir: pathlib.Path, calls: int = g8_stats.CALLS) -> int:
    from platform_app import main as pmain

    sys.path.insert(0, str(ROOT))
    from tests.s4.conftest import complete_body, handler_id

    client = pmain.client()
    times: dict[str, list[float]] = {"create": [], "update": [], "complete": []}
    errors = {"create": 0, "update": 0, "complete": 0}
    failures: list[str] = []

    def timed(op: str, fn: Any, want: str) -> Any:
        t0 = time.perf_counter()
        r = fn()
        times[op].append(time.perf_counter() - t0)
        got = r.body.get("status") if isinstance(r.body, dict) else None
        if not r.ok or got != want or r.transport_error:
            errors[op] += 1
            failures.append(f"{op}: HTTP {r.status} status {got!r} {r.transport_error or ''}")
        return r

    for _ in range(calls):
        a = timed("create", lambda: client.create(_create_body()), "incomplete")
        if not isinstance(a.body, dict) or "id" not in a.body:
            # The next calls cannot run. Count them as errors, with the time of the failed call.
            for op in ("update", "complete"):
                times[op].append(times["create"][-1])
                errors[op] += 1
            continue
        b = timed(
            "update",
            lambda: client.update(a.body["id"], _update_body(a.body)),
            "ready_for_complete",
        )
        if not isinstance(b.body, dict) or b.body.get("status") != "ready_for_complete":
            times["complete"].append(times["update"][-1])
            errors["complete"] += 1
            continue
        hid = handler_id(b.body)
        timed("complete", lambda: client.complete(b.body["id"], complete_body(hid)), "completed")

    stats = [
        g8_stats.summarise(op, times[op], errors[op]) for op in ("create", "update", "complete")
    ]
    violations = g8_stats.verdict(stats, calls)
    report_dir.mkdir(parents=True, exist_ok=True)
    status = "PASS" if not violations else "FAIL"
    data = {
        "gate": "G8",
        "status": status,
        "calls_per_operation": calls,
        "violations": violations,
        "operations": [
            {
                **{k: getattr(s, k) for k in ("op", "calls", "errors", "p50", "p95", "max")},
                "p95_limit_s": s.limit_p95,
                "p50_target_s": s.target_p50,
                "error_rate": s.error_rate,
            }
            for s in stats
        ],
        "first_failures": failures[:10],
        "method": "Platform client, loopback layout with local TLS 1.3 proxy, UCP_TRACING=0, perf_counter",
        "source": "https://developers.google.com/merchant/ucp/guides/overview/native-checkout "
        "(Service level objectives; page has no version in its URL; read 28 Oct 2026)",
        "git_head": os.environ.get("G8_GIT_HEAD", "unknown"),
    }
    (report_dir / "G8.json").write_text(json.dumps(data, indent=2) + "\n")
    rows = [
        "| Operation | Calls | Errors | p50 (s) | p95 (s) | max (s) | p95 limit (s) | p50 target (s, not a limit) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in stats:
        rows.append(
            f"| {s.op} | {s.calls} | {s.errors} | {s.p50:.3f} | {s.p95:.3f} | {s.max:.3f} "
            f"| {s.limit_p95:g} | {s.target_p50:g} |"
        )
    md = "# G8 latency report (AC-117)\n\n" + "\n".join(rows) + f"\n\nResult: **{status}**\n"
    if violations:
        md += "\nViolations:\n" + "\n".join(f"- {v}" for v in violations) + "\n"
    (report_dir / "G8.md").write_text(md)
    print(md)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r1 = sub.add_parser("ready")
    r1.add_argument("--start-ns", type=int, required=True)
    r1.add_argument("--log", type=pathlib.Path, required=True)
    r2 = sub.add_parser("run")
    r2.add_argument("--report-dir", type=pathlib.Path, required=True)
    r2.add_argument("--calls", type=int, default=g8_stats.CALLS)
    a = ap.parse_args()
    sys.exit(ready(a.start_ns, a.log) if a.cmd == "ready" else run(a.report_dir, a.calls))
