"""G4, S4: AC-56 on the live layout (Platform -> Caddy TLS -> Business -> mock PSP).

Needs the layout (`tools/run_local.sh start`) started while Jaeger runs (`tools/jaeger.sh start`),
so the services have OTEL_EXPORTER_OTLP_ENDPOINT. Spans cross real sockets here, so the Business
span is a SERVER span with a remote parent (the in-process test cannot show this).
Jaeger is read only through `/api/v3/*` (T-34).
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Any

import httpx2
import pytest

from tests.s2.conftest import create_body
from tests.s4.contract.test_traces import EVIDENCE, JAEGER, _attrs, _kind, fetch_trace

PLATFORM = "https://localhost:8443"


@pytest.fixture(scope="module")
def platform() -> httpx2.Client:
    c = httpx2.Client(base_url=PLATFORM, verify=False, timeout=30)  # noqa: S501  (test CA, loopback)
    try:
        assert c.get("/livez").status_code == 200, "the layout does not run"
        assert httpx2.get(JAEGER + "/api/v3/services", timeout=3).status_code == 200, "no Jaeger"
    except httpx2.HTTPError as e:
        pytest.fail(f"the layout or Jaeger does not run: {e}")
    return c


def _wait(pred: Any, timeout: float = 20.0) -> list[dict[str, Any]]:
    deadline = time.time() + timeout
    rows: list[dict[str, Any]] = []
    while time.time() < deadline:
        rows = pred()
        if rows:
            return rows
        time.sleep(0.3)
    return rows


def test_ac56_live_create_has_one_trace_across_platform_business(platform: httpx2.Client) -> None:
    r = platform.post("/api/checkout", json=create_body())
    assert r.status_code == 200, r.text
    rows = platform.get("/api/timeline").json()["rows"]
    plat = [x for x in rows if x.get("side") == "platform" and x.get("op") == "create"]
    assert plat and plat[-1].get("trace_id"), "no trace_id on the Platform row (is tracing on?)"
    tid = plat[-1]["trace_id"]
    rid = plat[-1]["request_id"]
    biz = [x for x in rows if x.get("side") == "business" and x.get("request_id") == rid]
    assert biz and all(x.get("trace_id") == tid for x in biz), (tid, biz)

    def want(spans: list[dict[str, Any]]) -> bool:
        svc = {(s["service"], _kind(s)) for s in spans}
        return {("platform", "SERVER"), ("platform", "CLIENT"), ("business", "SERVER")} <= svc

    spans = fetch_trace(tid, want)
    assert want(spans), [(s["service"], _kind(s), s["name"]) for s in spans]
    by_id = {s["spanId"]: s for s in spans}
    server = next(s for s in spans if s["service"] == "business" and _kind(s) == "SERVER")
    client = by_id[server["parentSpanId"]]
    assert client["service"] == "platform" and _kind(client) == "CLIENT"
    top = by_id[client["parentSpanId"]]
    assert top["service"] == "platform" and _kind(top) == "SERVER"
    assert {s["traceId"] for s in spans} == {tid}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    pathlib.Path(EVIDENCE / "ac56-live-trace.json").write_text(
        json.dumps(
            {
                "trace_id": tid,
                "request_id": rid,
                "spans": [
                    {
                        "service": s["service"],
                        "kind": _kind(s),
                        "name": s["name"],
                        "span_id": s["spanId"],
                        "parent": s.get("parentSpanId"),
                        "http.route": _attrs(s).get("http.route"),
                    }
                    for s in spans
                ],
                "business_log_rows_with_trace_id": len(biz),
            },
            indent=2,
        )
        + "\n"
    )
