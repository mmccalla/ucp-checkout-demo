"""G4, S4: traces in Jaeger (AC-42, AC-54 span part, AC-56).

Jaeger 2.22.0 runs as the release binary (T-106, ADR 0013). The test uses a Jaeger that
already listens on 127.0.0.1:16686. If none runs, it starts `tools/jaeger.sh start` and stops it
at the end. If Jaeger cannot start, the test fails (it never skips). CI reads only `/api/v3/*`
(T-34): https://www.jaegertracing.io/docs/2.22/apis/ ("Read APIs").

The Platform client, the Business and the mock PSP run in this process. Each has its own tracer
provider and `service.name`. Spans go to Jaeger over OTLP/HTTP on 127.0.0.1:4318.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from ucp_core import telemetry
from ucp_core.constants import ROOT

from tests.evidence import evidence_dir
from tests.s2.conftest import Pair, create_body, make_pair
from tests.s4.conftest import complete_body, handler_id, ready

JAEGER = "http://127.0.0.1:16686"
OTLP = "http://127.0.0.1:4318"
SERVICES = ("platform", "business", "psp-mock")
EVIDENCE = evidence_dir("S4", "traces")


def _up() -> bool:
    try:
        return httpx.get(JAEGER + "/api/v3/services", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="module")
def jaeger() -> Iterator[None]:
    started = False
    if not _up():
        subprocess.run([str(ROOT / "tools" / "jaeger.sh"), "start"], check=True, cwd=ROOT)
        started = True
        for _ in range(100):
            if _up():
                break
            time.sleep(0.2)
    assert _up(), "Jaeger did not start on 127.0.0.1:16686"
    yield
    if started:
        subprocess.run([str(ROOT / "tools" / "jaeger.sh"), "stop"], check=True, cwd=ROOT)


@pytest.fixture
def tpair(jaeger: None, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Pair]:
    monkeypatch.setenv(telemetry.ENDPOINT_ENV, OTLP)
    for s in SERVICES:
        telemetry.reset(s)
        assert telemetry.init(s, simple=True) is not None
    yield from make_pair(tmp_path, monkeypatch)
    for s in SERVICES:
        telemetry.reset(s)


def _attrs(span: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for a in span.get("attributes", []):
        v = a["value"]
        out[a["key"]] = next(iter(v.values()))
    return out


def _kind(span: dict[str, Any]) -> str:
    k = span.get("kind")
    names = {1: "INTERNAL", 2: "SERVER", 3: "CLIENT"}
    return (
        names.get(k, str(k).replace("SPAN_KIND_", ""))
        if isinstance(k, int)
        else str(k).replace("SPAN_KIND_", "")
    )


def fetch_trace(
    trace_id: str, want: Callable[[list[dict[str, Any]]], bool], timeout: float = 20.0
) -> list[dict[str, Any]]:
    """GET /api/v3/traces/{id}. Wait until `want(spans)` is true. Return span dicts + service."""
    deadline = time.time() + timeout
    spans: list[dict[str, Any]] = []
    while time.time() < deadline:
        r = httpx.get(f"{JAEGER}/api/v3/traces/{trace_id}", timeout=5)
        spans = []
        if r.status_code == 200:
            for line in r.text.splitlines():
                if not line.strip():
                    continue
                for rs in json.loads(line).get("result", {}).get("resourceSpans", []):
                    svc = next(
                        a["value"]["stringValue"]
                        for a in rs["resource"]["attributes"]
                        if a["key"] == "service.name"
                    )
                    for ss in rs["scopeSpans"]:
                        for sp in ss["spans"]:
                            spans.append({**sp, "service": svc})
        if want(spans):
            return spans
        time.sleep(0.3)
    return spans


def _is_server(s: dict[str, Any]) -> bool:
    """In process, the TestClient keeps the client span as the active parent of the Business
    span, so the instrumentation marks it INTERNAL. Over a real socket it is SERVER. The live
    test (`tests/s4/e2e/test_live_traces.py`) checks the SERVER kind."""
    return _kind(s) in ("SERVER", "INTERNAL")


def _has(*pairs: str) -> Callable[[list[dict[str, Any]]], bool]:
    """True when the trace has a span for each (service, kind) pair given."""
    want = list(zip(pairs[::2], pairs[1::2], strict=True))
    return lambda spans: all(
        any(
            s["service"] == a and (_is_server(s) if b == "SERVER" else _kind(s) == b) for s in spans
        )
        for a, b in want
    )


def test_ac56_each_call_has_client_and_server_span_and_log_rows_have_the_trace_id(
    tpair: Pair,
) -> None:
    tracer = telemetry.provider("platform").get_tracer("tests.s4")  # type: ignore[union-attr]
    log_lines: list[tuple[str, str]] = []

    class Grab(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_lines.append((record.name, getattr(record, "trace_id", "?")))

    grab = Grab()
    grab.addFilter(telemetry.TraceIdFilter())
    root = logging.getLogger()
    root.addHandler(grab)
    root.setLevel(logging.INFO)
    traces: dict[str, str] = {}  # request id -> trace id
    results = []
    try:
        with tracer.start_as_current_span("smoke create", kind=SpanKind.SERVER):
            c = tpair.client.create(create_body())
            tpair.timeline.record(c)
            results.append(c)
        checkout = ready(tpair)
        with tracer.start_as_current_span("smoke complete", kind=SpanKind.SERVER):
            done = tpair.client.complete(
                checkout["id"], complete_body(handler_id(checkout)), checkout.get("expires_at")
            )
            tpair.timeline.record(done)
            results.append(done)
    finally:
        root.removeHandler(grab)
    assert done.status == 200 and done.body["status"] == "completed", done.body
    telemetry.flush()
    brows = [json.loads(x) for x in (tpair.tmp / "business.jsonl").read_text().splitlines() if x]
    prows = [json.loads(x) for x in (tpair.tmp / "platform.jsonl").read_text().splitlines() if x]
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"calls": []}
    for res in results:
        rid = res.request_id
        bro = [r for r in brows if r.get("request_id") == rid]
        pro = [r for r in prows if r.get("request_id") == rid]
        assert bro and pro, rid
        tids = {r["trace_id"] for r in bro + pro}
        assert len(tids) == 1, (rid, tids)  # each log row has the same trace ID
        tid = tids.pop()
        spans = fetch_trace(tid, _has("platform", "CLIENT", "business", "SERVER"))
        client = [s for s in spans if s["service"] == "platform" and _kind(s) == "CLIENT"]
        server = [s for s in spans if s["service"] == "business" and _is_server(s)]
        assert client and server, [(s["service"], _kind(s), s["name"]) for s in spans]
        assert {s["traceId"] for s in client + server} == {tid}
        assert any(s["parentSpanId"] == c_["spanId"] for s in server for c_ in client)
        traces[rid] = tid
        report["calls"].append(
            {
                "op": res.op,
                "request_id": rid,
                "trace_id": tid,
                "spans": [(s["service"], _kind(s), s["name"]) for s in spans],
            }
        )
    # The Complete call goes on to the mock PSP: client span (Business) and server span (PSP).
    spans = fetch_trace(traces[done.request_id], _has("business", "CLIENT", "psp-mock", "SERVER"))
    assert any(s["service"] == "business" and _kind(s) == "CLIENT" for s in spans)
    assert any(s["service"] == "psp-mock" and _is_server(s) for s in spans)
    # Python log lines inside a request have the trace ID of the request. No line has "-".
    ours = [(n, t) for n, t in log_lines if n in ("business.psp", "psp_mock")]
    assert ours, "no PSP log line was captured"
    assert all(t == traces[done.request_id] for _, t in ours), ours
    report["log_lines_checked"] = len(ours)
    (EVIDENCE / "ac56-trace-report.json").write_text(json.dumps(report, indent=2) + "\n")


def test_ac42_replay_span_has_replayed_true(tpair: Pair) -> None:
    body = json.dumps(create_body(), separators=(",", ":"))
    key = f"k-{uuid.uuid4().hex[:8]}"
    tids = []
    resp = []
    tracer = telemetry.provider("platform").get_tracer("tests.s4")  # type: ignore[union-attr]
    # An unsigned client: the signature check is not under test here (as in S2 AC-42).
    from tests.s2.contract.test_checkout_flow import make_unsigned

    unsigned = make_unsigned(tpair)
    for i in range(2):
        h = tpair.headers(**{"Idempotency-Key": key, "Content-Type": "application/json"})
        with tracer.start_as_current_span(f"replay try {i + 1}", kind=SpanKind.SERVER):
            tid = telemetry.trace_id()
            assert tid
            tids.append(tid)
            resp.append(unsigned.post("/checkout-sessions", content=body, headers=h))
    assert [r.status_code for r in resp] == [201, 201]
    assert resp[0].json() == resp[1].json()
    telemetry.flush()
    out = []
    for tid in tids:
        spans = [
            s for s in fetch_trace(tid, _has("business", "SERVER")) if s["service"] == "business"
        ]
        server = [s for s in spans if _is_server(s)]
        assert len(server) == 1, spans
        out.append(_attrs(server[0]).get("ucp.idempotency.replayed"))
    assert out == [False, True], out
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ac42-replayed-attribute.json").write_text(
        json.dumps({"trace_ids": tids, "ucp.idempotency.replayed": out}, indent=2) + "\n"
    )


FORBIDDEN = (
    "examplePaymentMethodToken",  # the credential token of the test
    "buyer@example.com",  # the buyer e-mail
    "signature",  # no signature header or value
    "authorization",
    "credential",
)


# Other words that no span name, attribute key or attribute value may have (AC-54).
FORBIDDEN_WORDS = ("street", "address", "tok_", "api_key", "apikey")
# The test card numbers of the repository, as digits only: `tests/s3/unit/test_pay_units.py`,
# `tests/s7/contract/test_platform_catalog_api.py` and `business/src/ucp_sample_server/integration_test.py`
# use 4111111111111111. `contracts/ucp-schemas/shopping/types/card_credential.json` has 4242424242424242.
TEST_PANS = ("4111111111111111", "4242424242424242")
SHORT_PAN = "4111"
# Random IDs: UUIDs (for example the checkout ID in `http.url`) and long hex runs (trace IDs, span IDs
# and hashes, for example in the `@jaeger@warnings` attribute). They can contain "4111" by chance.
_RANDOM_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}", re.IGNORECASE
)
# What the AC-54 scan reads. It never reads `traceId`, `spanId`, `parentSpanId`, `traceState`, `flags`,
# `kind`, a time field (`startTimeUnixNano`, `endTimeUnixNano`, `timeUnixNano`) or the `traceId` and
# `spanId` of a link. Those fields hold random or time values and no text of the application.
SCANNED_FIELDS = (
    "name",
    "service",
    "attributes[].key",
    "attributes[].value",
    "status.message",
    "events[].name",
    "events[].attributes[].key",
    "events[].attributes[].value",
    "links[].attributes[].key",
    "links[].attributes[].value",
)


def _any_value_texts(value: Any) -> Iterator[str]:
    """The text of an OTLP/JSON `AnyValue`: scalars, arrays and key-value lists, at all depths."""
    if not isinstance(value, dict):
        return
    for kind, inner in value.items():
        if kind == "arrayValue":
            for item in inner.get("values", []):
                yield from _any_value_texts(item)
        elif kind == "kvlistValue":
            for item in inner.get("values", []):
                yield str(item["key"])
                yield from _any_value_texts(item.get("value", {}))
        else:  # stringValue, intValue, doubleValue, boolValue, bytesValue
            yield str(inner)


def _attribute_texts(attributes: list[dict[str, Any]]) -> Iterator[str]:
    for a in attributes:
        yield str(a["key"])
        yield from _any_value_texts(a.get("value", {}))


def span_texts(span: dict[str, Any]) -> list[str]:
    """All text of one span that AC-54 scans (see `SCANNED_FIELDS`). No ID and no time field."""
    out: list[str] = [str(span.get("name", "")), str(span.get("service", ""))]
    out.extend(_attribute_texts(span.get("attributes", [])))
    out.append(str((span.get("status") or {}).get("message", "")))
    for event in span.get("events", []):
        out.append(str(event.get("name", "")))
        out.extend(_attribute_texts(event.get("attributes", [])))
    for link in span.get("links", []):
        out.extend(_attribute_texts(link.get("attributes", [])))
    return [t for t in out if t]


def assert_spans_have_no_forbidden_text(spans: list[dict[str, Any]]) -> None:
    """AC-54: no forbidden word, no test card number in the names, keys and values of the spans.

    The word checks read the text as it is. The check for a full test card number reads the
    digits of each text (spaces, hyphens and other separators removed), so "4111 1111 1111 1111"
    fails too. The short check for "4111" reads the text with random IDs removed: a UUID or a
    long hex run holds "4111" by chance and is not a card number. The full card number check
    still reads those IDs.
    """
    texts = [t for s in spans for t in span_texts(s)]
    text = "\n".join(texts).lower()
    for bad in FORBIDDEN:
        assert bad.lower() not in text, bad
    for word in FORBIDDEN_WORDS:
        assert word not in text, word
    for t in texts:
        digits = re.sub(r"\D", "", t)
        for pan in TEST_PANS:
            assert pan not in digits, "test card number as digits"
    without_ids = "\n".join(_RANDOM_ID.sub("<id>", t) for t in texts)
    assert SHORT_PAN not in without_ids, SHORT_PAN


def test_ac54_spans_have_no_token_pan_address_email_key_or_signature(tpair: Pair) -> None:
    tracer = telemetry.provider("platform").get_tracer("tests.s4")  # type: ignore[union-attr]
    with tracer.start_as_current_span("smoke", kind=SpanKind.SERVER):
        checkout = ready(tpair)
        done = tpair.client.complete(
            checkout["id"], complete_body(handler_id(checkout)), checkout.get("expires_at")
        )
        tid = format(trace.get_current_span().get_span_context().trace_id, "032x")
    assert done.status == 200
    telemetry.flush()
    spans = fetch_trace(tid, _has("business", "CLIENT", "psp-mock", "SERVER"))
    assert len(spans) >= 6, len(spans)
    # Scan names, attribute keys and attribute values only. Not the IDs and not the times: they are
    # random (a span ID can hold "4111" by chance). `SCANNED_FIELDS` lists what is read.
    assert_spans_have_no_forbidden_text(spans)
    # The only attribute keys are the standard HTTP keys and the `ucp.*` keys of this demo.
    keys = {k for s in spans for k in _attrs(s)}
    assert not [k for k in keys if "header" in k or "body" in k], keys
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ac54-span-scan.json").write_text(
        json.dumps(
            {
                "trace_id": tid,
                "spans": len(spans),
                "attribute_keys": sorted(keys),
                "forbidden_terms_checked": [*FORBIDDEN, *FORBIDDEN_WORDS, SHORT_PAN],
                "test_card_numbers_checked": len(TEST_PANS),
                "scanned_fields": list(SCANNED_FIELDS),
                "found": [],
                "scanned_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n"
    )
