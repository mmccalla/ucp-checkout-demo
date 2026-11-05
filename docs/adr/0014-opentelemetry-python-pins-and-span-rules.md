# ADR 0014: OpenTelemetry Python pins and span rules

- Status: Accepted for S4 (AC-42, AC-54, AC-56).
- Date: 2026-10-28.
- Owner: Mark McCalla.

## Context

AC-56 needs one trace per call through the Platform, the Business and the mock PSP. The trace must be readable in Jaeger through `/api/v3/*` (T-34). Each log row must have the trace ID. AC-42 needs a span attribute that shows a replayed idempotency key. AC-54 forbids a token, a PAN, an address, an e-mail, an API key and a signature in a span.

## Decision

1. The direct dependencies are in `pyproject.toml`. `uv.lock` holds the resolved versions. All packages are from PyPI. The versions were published on 6 Oct 2026 (PyPI JSON, checked 28 Oct 2026).

   | Package | Version | Use | Documentation read |
   |---|---|---|---|
   | opentelemetry-api | 1.45.1 | `trace` API | https://opentelemetry.io/docs/languages/python/getting-started/ |
   | opentelemetry-sdk | 1.45.1 | `TracerProvider`, `Resource`, span processors | https://opentelemetry.io/docs/languages/python/getting-started/ |
   | opentelemetry-exporter-otlp-proto-http | 1.45.1 | OTLP over HTTP to Jaeger port 4318 | https://opentelemetry.io/docs/languages/python/exporters/ |
   | opentelemetry-instrumentation-fastapi | 0.66b1 | server span for each request | https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html |
   | opentelemetry-instrumentation-httpx | 0.66b1 | client span and `traceparent` header (class `HTTPX2ClientInstrumentor`, for the `httpx2` client) | https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html |

   UNVERIFIED: the two instrumentation pages above are for `latest`. They do not name version 0.66b1. The tests in `tests/s4/contract/` show the behaviour of 0.66b1 (see "Observed").

   Version-pinned sources. Checked on 2026-10-28: each URL below answers HTTP 200. No documentation page with a version path exists: `https://opentelemetry-python.readthedocs.io/en/v1.45.1/` and `https://opentelemetry-python-contrib.readthedocs.io/en/v0.66b1/` answer HTTP 404. The pinned sources are the PyPI page and the Git tag of the exact version (spec T-107 PROPOSED, Appendix A.2):

   | Package | Version | PyPI page at the exact version | Source at the Git tag |
   |---|---|---|---|
   | opentelemetry-api | 1.45.1 | https://pypi.org/project/opentelemetry-api/1.45.1/ | https://github.com/open-telemetry/opentelemetry-python/blob/v1.45.1/docs/api/trace.rst |
   | opentelemetry-sdk | 1.45.1 | https://pypi.org/project/opentelemetry-sdk/1.45.1/ | https://github.com/open-telemetry/opentelemetry-python/blob/v1.45.1/docs/sdk/trace.rst |
   | opentelemetry-exporter-otlp-proto-http | 1.45.1 | https://pypi.org/project/opentelemetry-exporter-otlp-proto-http/1.45.1/ | https://github.com/open-telemetry/opentelemetry-python/blob/v1.45.1/docs/exporter/otlp/otlp.rst |
   | opentelemetry-instrumentation-fastapi | 0.66b1 | https://pypi.org/project/opentelemetry-instrumentation-fastapi/0.66b1/ | https://github.com/open-telemetry/opentelemetry-python-contrib/blob/v0.66b1/instrumentation/opentelemetry-instrumentation-fastapi/src/opentelemetry/instrumentation/fastapi/__init__.py |
   | opentelemetry-instrumentation-httpx | 0.66b1 | https://pypi.org/project/opentelemetry-instrumentation-httpx/0.66b1/ | https://github.com/open-telemetry/opentelemetry-python-contrib/blob/v0.66b1/instrumentation/opentelemetry-instrumentation-httpx/src/opentelemetry/instrumentation/httpx/__init__.py |

   Git tags: https://github.com/open-telemetry/opentelemetry-python/tree/v1.45.1 and https://github.com/open-telemetry/opentelemetry-python-contrib/tree/v0.66b1. `version.py` at each tag has `1.45.1` and `0.66b1`. The 8 transitive packages have a PyPI page at the exact version (spec Appendix A.2). UNVERIFIED as version-pinned: the `opentelemetry.io` pages and the `latest` Read the Docs pages in the first table above. They are not pinned to a version. The tests in `tests/s4/contract/` show the behaviour.

2. Transitive packages in `uv.lock`: opentelemetry-proto 1.45.1, opentelemetry-exporter-otlp-proto-common 1.45.1, opentelemetry-exporter-http-transport 0.66b1, opentelemetry-exporter-otlp-common 0.66b1, opentelemetry-instrumentation 0.66b1, opentelemetry-instrumentation-asgi 0.66b1, opentelemetry-semantic-conventions 0.66b1, opentelemetry-util-http 0.66b1, protobuf 7.36.2, requests 2.34.2, urllib3 2.8.0, wrapt 2.5.1. The exact names are in `uv.lock`.
3. `libs/ucp_core/telemetry.py` is the only module that imports OpenTelemetry. Each service has its own `TracerProvider` and `service.name`: `platform`, `business`, `psp-mock`.
4. Spans are off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. The value, and `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` if set, must name `127.0.0.1` or `localhost` (DM-26). Other values raise `TelemetryError`. `tools/run_local.sh start` sets the variable when Jaeger answers on 127.0.0.1:16686. `UCP_TRACING=0` turns this off.
5. The Business gate is an ASGI middleware. `instrument_fastapi` runs after it, so the server span is the outermost layer and the Business gate decisions are inside it. The spans `receive` and `send` are not made.
6. Attribute rules (AC-54). The code adds no header and no body to a span. A span has the standard HTTP attributes of the instrumentation and the attribute `ucp.idempotency.replayed` (boolean, set by the Business gate when the request has an `Idempotency-Key`). `tests/s4/contract/test_traces.py::test_ac54_...` reads a full Complete trace from Jaeger and fails if it finds one of: the test credential token, the buyer e-mail, `signature`, `authorization`, `credential`, `street`, `address`, `4111`, `tok_`, `api_key`, `apikey`, or an attribute key with `header` or `body`.
7. Log rows. The Platform and Business JSONL rows have the field `trace_id` (32 hex digits) when a span is active. Python log lines use `LOG_FORMAT` with `trace_id=`. The value is `-` when no span is active.
8. CI reads Jaeger only through `/api/v3/*` (T-34): `/api/v3/services` and `/api/v3/traces/{trace_id}`. Source: https://www.jaegertracing.io/docs/2.22/apis/.
9. The mock PSP now imports `ucp_core.telemetry`. `tools/run_local.sh` adds `libs` to its `PYTHONPATH`.

## Observed

- In process, the Starlette `TestClient` keeps the Platform client span as the active parent. The instrumentation then marks the Business span INTERNAL and ignores a `traceparent` header. Over a real socket the Business span is SERVER with a remote parent. For this reason there are two tests: an in-process test (`test_traces.py`) and a live test on the TLS layout (`test_live_traces.py`). The live test checks the SERVER kind and the parent chain Platform SERVER, Platform CLIENT, Business SERVER.
- Jaeger 2.22.0 adds the attribute `@jaeger@warnings` to some spans. The AC-54 scan does not treat it as an error.
