"""G3, S4: the telemetry module (AC-56 rules, DM-26)."""

from __future__ import annotations

import logging

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from ucp_core import telemetry


@pytest.fixture(autouse=True)
def _clean() -> None:
    for s in ("t-a", "t-b"):
        telemetry.reset(s)


def test_off_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(telemetry.ENDPOINT_ENV, raising=False)
    assert telemetry.init("t-a") is None
    assert telemetry.trace_id() is None


@pytest.mark.parametrize(
    "url", ["http://example.com:4318", "http://10.0.0.5:4318", "https://x.test"]
)
def test_endpoint_must_be_loopback(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv(telemetry.ENDPOINT_ENV, url)
    with pytest.raises(telemetry.TelemetryError):
        telemetry.init("t-a")


def test_traces_endpoint_must_be_loopback_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(telemetry.ENDPOINT_ENV, "http://127.0.0.1:4318")
    monkeypatch.setenv(telemetry.TRACES_ENDPOINT_ENV, "http://example.com/v1/traces")
    with pytest.raises(telemetry.TelemetryError):
        telemetry.init("t-a")


def test_loopback_endpoint_gives_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(telemetry.ENDPOINT_ENV, "http://127.0.0.1:4318")
    monkeypatch.delenv(telemetry.TRACES_ENDPOINT_ENV, raising=False)
    assert telemetry.init("t-a") is not None


def test_trace_id_and_log_filter_in_a_span() -> None:
    p = telemetry.init("t-b", exporter=InMemorySpanExporter(), simple=True)
    assert p is not None
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "m", None, None)
    telemetry.TraceIdFilter().filter(rec)
    assert rec.trace_id == "-"  # type: ignore[attr-defined]
    with p.get_tracer("t").start_as_current_span("s"):
        tid = telemetry.trace_id()
        assert tid is not None and len(tid) == 32
        telemetry.TraceIdFilter().filter(rec)
        assert rec.trace_id == tid  # type: ignore[attr-defined]
        telemetry.set_attribute("ucp.test", True)
