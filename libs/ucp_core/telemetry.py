"""OpenTelemetry set-up for the Platform, the Business and the mock PSP (S4: AC-42, AC-54, AC-56).

Sources (read on 28 Oct 2026):
- Python exporters: https://opentelemetry.io/docs/languages/python/exporters/ (OTLP over HTTP,
  `BatchSpanProcessor`, `Resource` with `service.name`).
- Python instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
  and .../httpx/httpx.html. These pages are for `latest`. The pinned versions are in `uv.lock`.
- Jaeger 2.22 accepts OTLP on `127.0.0.1:4318` (https://www.jaegertracing.io/docs/2.22/apis/).

Rules:
- Spans are off unless `OTEL_EXPORTER_OTLP_ENDPOINT` names a loopback address, or a test gives an
  exporter. The endpoint must be `127.0.0.1` or `localhost` (DM-26).
- The code does not capture a header or a body. A span has the method, the URL path, the status
  and the `ucp.*` attributes in this file. It never has a token, a signature or a credential (AC-54).
- `ucp.idempotency.replayed` is set by the Business (AC-42).
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlsplit

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter

ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
TRACES_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
LOOPBACK = {"127.0.0.1", "localhost"}
_providers: dict[str, TracerProvider] = {}


class TelemetryError(Exception):
    pass


def _check_endpoint(url: str) -> None:
    host = urlsplit(url).hostname
    if host not in LOOPBACK:
        raise TelemetryError(f"{ENDPOINT_ENV} must be a loopback address (DM-26), not {host!r}")


def init(
    service: str, exporter: SpanExporter | None = None, simple: bool = False
) -> TracerProvider | None:
    """Register a tracer provider for `service`. Return None if spans are off."""
    if service in _providers:
        return _providers[service]
    if exporter is None:
        url = os.environ.get(ENDPOINT_ENV)
        if not url:
            return None
        _check_endpoint(url)
        # The exporter also reads this signal-specific variable. It must be a loopback address too.
        specific = os.environ.get(TRACES_ENDPOINT_ENV)
        if specific:
            _check_endpoint(specific)
        exporter = OTLPSpanExporter()  # reads the endpoint from the official env variable
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service}))
    processor = SimpleSpanProcessor(exporter) if simple else BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    _providers[service] = provider
    return provider


def provider(service: str) -> TracerProvider | None:
    return _providers.get(service)


def reset(service: str) -> None:
    """Test helper: flush and forget the provider of `service`."""
    p = _providers.pop(service, None)
    if p is not None:
        p.force_flush()
        p.shutdown()


def flush() -> None:
    for p in _providers.values():
        p.force_flush()


def instrument_fastapi(app: Any, service: str) -> bool:
    """Add the server span middleware to a FastAPI app. Call it after the last middleware."""
    p = _providers.get(service) or init(service)
    if p is None:
        return False
    FastAPIInstrumentor.instrument_app(app, tracer_provider=p, exclude_spans=["receive", "send"])
    return True


def uninstrument_fastapi(app: Any) -> None:
    FastAPIInstrumentor.uninstrument_app(app)


def instrument_client(client: Any, service: str) -> bool:
    """Add the client span (and the `traceparent` header) to an httpx client."""
    p = _providers.get(service) or init(service)
    if p is None:
        return False
    HTTPXClientInstrumentor.instrument_client(client, tracer_provider=p)
    return True


def trace_id() -> str | None:
    """The 32-digit trace ID of the current span, or None."""
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def set_attribute(key: str, value: bool | int | str) -> None:
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute(key, value)


class TraceIdFilter(logging.Filter):
    """Add `trace_id` to each log record (AC-56). The value is `-` when no span is active."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id() or "-"
        return True


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s trace_id=%(trace_id)s %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Put one handler on the root logger. Each line has `trace_id=` (AC-56)."""
    root = logging.getLogger()
    if any(getattr(h, "_ucp_trace", False) for h in root.handlers):
        return
    h = logging.StreamHandler()
    h._ucp_trace = True  # type: ignore[attr-defined]
    h.addFilter(TraceIdFilter())
    h.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(h)
    root.setLevel(level)
