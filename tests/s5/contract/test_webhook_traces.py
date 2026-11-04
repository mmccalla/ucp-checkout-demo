"""G4, S5: the trace parts of AC-66 and AC-72 (spec section 7).

AC-66: the order webhook has a Business client span and a Platform server span in one trace.
AC-72: after a 503, the trace shows each attempt (one Business client span for each attempt).

Jaeger 2.22.0 runs on 127.0.0.1:16686 (see `tests/s4/contract/test_traces.py`). Spans go to
127.0.0.1:4318. The test reads `/api/v3/traces/{id}` only. It never skips.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry.trace import SpanKind
from platform_app import main as pmain
from ucp_core import telemetry

from tests.evidence import evidence_dir
from tests.s4.contract.test_traces import (  # noqa: F401  (jaeger is a fixture)
    OTLP,
    SERVICES,
    _attrs,
    _is_server,
    _kind,
    fetch_trace,
    jaeger,
)
from tests.s4.g6.conftest import G6, build
from tests.s4.g6.test_webhooks import ready_via_platform
from tests.s4.conftest import complete_body, handler_id

EVIDENCE = evidence_dir("S5", "traces")
HOOK = "POST order webhook"


@pytest.fixture
def wg(jaeger: None, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[G6]:  # noqa: F811
    monkeypatch.setenv(telemetry.ENDPOINT_ENV, OTLP)
    for s in SERVICES:
        telemetry.reset(s)
        assert telemetry.init(s, simple=True) is not None
    telemetry.instrument_fastapi(pmain.app, "platform")  # off at import, no endpoint then
    pmain.app.middleware_stack = None  # Starlette builds the stack again with the new provider
    try:
        yield from build(tmp_path, monkeypatch)
    finally:
        telemetry.uninstrument_fastapi(pmain.app)
        pmain.app.middleware_stack = None
        for s in SERVICES:
            telemetry.reset(s)


def _complete_in_trace(g: G6) -> tuple[str, list[dict[str, Any]]]:
    c = ready_via_platform(g)
    tracer = telemetry.provider("platform").get_tracer("tests.s5")  # type: ignore[union-attr]
    with tracer.start_as_current_span("complete with webhooks", kind=SpanKind.SERVER):
        tid = telemetry.trace_id()
        assert tid
        res = g.pair.client.complete(c["id"], complete_body(handler_id(c)))
    assert res.status == 200 and res.body["status"] == "completed", res.body
    telemetry.flush()

    def has_all(spans: list[dict[str, Any]]) -> bool:
        """Wait until each webhook attempt has its Business client span and Platform server span."""
        hooks = [s for s in spans if s["name"] == HOOK]
        got = {_attrs(s).get("ucp.webhook.event_type") for s in hooks}
        return {"order_placed", "order_shipped", "order_delivered"} <= got and all(
            _server_children(spans, h) for h in hooks
        )

    spans = fetch_trace(tid, has_all, timeout=30)
    return tid, spans


def _hooks(spans: list[dict[str, Any]], event: str) -> list[dict[str, Any]]:
    out = [
        s
        for s in spans
        if s["service"] == "business"
        and s["name"] == HOOK
        and _attrs(s).get("ucp.webhook.event_type") == event
    ]
    return sorted(out, key=lambda s: int(_attrs(s).get("ucp.webhook.attempt", 0)))


def _server_children(spans: list[dict[str, Any]], parent: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        s
        for s in spans
        if s["service"] == "platform"
        and _is_server(s)
        and s.get("parentSpanId") == parent["spanId"]
    ]


def test_ac66_webhook_has_business_client_span_and_platform_server_span(wg: G6) -> None:
    tid, spans = _complete_in_trace(wg)
    report: dict[str, Any] = {"trace_id": tid, "events": {}}
    for event in ("order_placed", "order_shipped", "order_delivered"):
        hooks = _hooks(spans, event)
        assert len(hooks) == 1, (event, [s["name"] for s in spans])
        h = hooks[0]
        assert _kind(h) == "CLIENT" and h["traceId"] == tid
        kids = _server_children(spans, h)
        assert len(kids) == 1, (event, [(s["service"], s["name"]) for s in spans])
        assert kids[0]["traceId"] == tid
        assert int(_attrs(h)["http.response.status_code"]) == 200
        report["events"][event] = {"client": h["spanId"], "server": kids[0]["spanId"]}
    text = json.dumps(spans).lower()
    for bad in ("signature", "authorization", "credential", "buyer@example.com"):
        assert bad not in text, bad  # AC-54 holds for the new span
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ac66-webhook-trace.json").write_text(json.dumps(report, indent=2) + "\n")


def test_ac72_trace_shows_each_attempt_after_503(wg: G6) -> None:
    pmain.receiver().dedup_down = 1  # the first attempt gets 503
    tid, spans = _complete_in_trace(wg)
    hooks = _hooks(spans, "order_placed")
    assert [int(_attrs(s)["ucp.webhook.attempt"]) for s in hooks] == [1, 2]
    assert [int(_attrs(s)["http.response.status_code"]) for s in hooks] == [503, 200]
    assert all(_kind(s) == "CLIENT" for s in hooks)
    kids = [
        [
            (
                k["name"],
                k["spanId"],
                _attrs(k).get("http.status_code") or _attrs(k).get("http.response.status_code"),
            )
            for k in _server_children(spans, s)
        ]
        for s in hooks
    ]
    assert all(len(k) == 1 for k in kids), (
        kids,
        [(s["service"], s["name"], s.get("parentSpanId"), s["spanId"]) for s in spans],
    )
    assert len(_hooks(spans, "order_shipped")) == 1  # later events have one attempt
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ac72-webhook-attempts.json").write_text(
        json.dumps(
            {
                "trace_id": tid,
                "attempts": [
                    {
                        "attempt": int(_attrs(s)["ucp.webhook.attempt"]),
                        "status": int(_attrs(s)["http.response.status_code"]),
                        "span": s["spanId"],
                    }
                    for s in hooks
                ],
            },
            indent=2,
        )
        + "\n"
    )
