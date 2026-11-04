"""AC-54: the span scan reads names, attribute keys and attribute values. It does not read IDs or times.

The contract test `tests/s4/contract/test_traces.py::test_ac54_...` used to search the whole JSON
of the spans for "4111". A random span ID (`cdce94111947da14`) held "4111" and the test failed
at random. These tests need no Jaeger. They give spans in the OTLP/JSON form that Jaeger returns.
"""

from __future__ import annotations

import json
import random
from typing import Any

import pytest

from tests.s4.contract.test_traces import (
    FORBIDDEN,
    FORBIDDEN_WORDS,
    TEST_PANS,
    assert_spans_have_no_forbidden_text,
    span_texts,
)

PAN = "4111111111111111"


def _attr(key: str, value: dict[str, Any]) -> dict[str, Any]:
    return {"key": key, "value": value}


def _span(**changes: Any) -> dict[str, Any]:
    span: dict[str, Any] = {
        "traceId": "dc839534dcb6a50dc01e99d7473b036d",
        "spanId": "1df52895800835c1",
        "parentSpanId": "ada9858f9cd7493d",
        "flags": 256,
        "name": "POST /checkout-sessions",
        "kind": 1,
        "startTimeUnixNano": "1793807063145087051",
        "endTimeUnixNano": "1793807063172160013",
        "attributes": [
            _attr("http.method", {"stringValue": "POST"}),
            _attr("http.status_code", {"intValue": "201"}),
            _attr("ucp.idempotency.replayed", {"boolValue": False}),
        ],
        "status": {},
        "service": "business",
    }
    return span | changes


# ---- IDs and times with "4111" do not fail ----------------------------------------------------


def test_ids_and_times_with_4111_do_not_fail() -> None:
    span = _span(
        traceId="4111aaaabbbbccccddddeeee41114111",
        spanId="cdce94111947da14",  # the span ID of the failed CI run 41855034170
        parentSpanId="a4111b2c3d4e5f60",
        startTimeUnixNano="1793804111000000000",
        endTimeUnixNano="1793807063411100000",
        events=[{"timeUnixNano": "1793804111999999999", "name": "event", "attributes": []}],
        links=[
            {
                "traceId": "4111" * 8,
                "spanId": "4111" * 4,
                "traceState": "4111=4111",
                "attributes": [],
            }
        ],
    )
    assert_spans_have_no_forbidden_text([span])
    assert not any("4111" in t for t in span_texts(span))


def test_the_old_search_of_the_whole_json_found_4111_in_an_id() -> None:
    """The defect: a search of `json.dumps(spans)` finds "4111" in a span ID."""
    span = _span(spanId="cdce94111947da14")
    assert "4111" in json.dumps([span]).lower()
    assert_spans_have_no_forbidden_text([span])


def test_random_ids_and_times_never_fail() -> None:
    rnd = random.Random(54)  # fixed seed: the run is the same each time
    spans = [
        _span(
            traceId=f"{rnd.getrandbits(128):032x}",
            spanId=f"{rnd.getrandbits(64):016x}",
            parentSpanId=f"{rnd.getrandbits(64):016x}",
            startTimeUnixNano=str(rnd.randrange(10**18, 2 * 10**18)),
            endTimeUnixNano=str(rnd.randrange(10**18, 2 * 10**18)),
        )
        for _ in range(20000)
    ]
    # Some of the IDs and times have "4111": the seed is fixed, so this is always true.
    assert any(
        "4111" in str(s[k]) for s in spans for k in ("traceId", "spanId", "startTimeUnixNano")
    )
    for chunk in range(0, len(spans), 2000):
        assert_spans_have_no_forbidden_text(spans[chunk : chunk + 2000])


def test_random_ids_in_attribute_values_do_not_fail() -> None:
    span = _span(
        attributes=[
            _attr(
                "http.target",
                {"stringValue": "/checkout-sessions/1519da53-4111-4986-8c95-805185b2e215"},
            ),
            _attr(
                "http.url",
                {
                    "stringValue": "https://localhost:9443/checkout-sessions/41114111-4111-4111-8111-411141114111"
                },
            ),
            _attr(
                "@jaeger@warnings",
                {
                    "arrayValue": {
                        "values": [
                            {"stringValue": "parent span ID=cdce94111947da14 is not in the trace"}
                        ]
                    }
                },
            ),
        ]
    )
    assert_spans_have_no_forbidden_text([span])


# ---- a test card number in a name, a key or a value fails -----------------------------------


def test_the_test_card_numbers_are_the_ones_of_the_repository() -> None:
    assert set(TEST_PANS) == {"4111111111111111", "4242424242424242"}


PAN_FORMS = [
    PAN,
    "4111 1111 1111 1111",
    "4111-1111-1111-1111",
    "card=4111111111111111&x=1",
    "pan:4111.1111.1111.1111",
    "4242424242424242",
    "4242 4242 4242 4242",
]


@pytest.mark.parametrize("value", PAN_FORMS)
def test_test_card_number_in_attribute_value_fails(value: str) -> None:
    span = _span(attributes=[_attr("ucp.note", {"stringValue": value})])
    with pytest.raises(AssertionError):
        assert_spans_have_no_forbidden_text([span])


def test_test_card_number_as_int_value_fails() -> None:
    span = _span(attributes=[_attr("ucp.note", {"intValue": PAN})])
    with pytest.raises(AssertionError):
        assert_spans_have_no_forbidden_text([span])


def test_test_card_number_in_a_random_looking_value_fails() -> None:
    """The ID filter of the short check does not hide a full card number."""
    for value in (PAN, "ab" + PAN, PAN + "cd", "11111111-" + PAN):
        span = _span(attributes=[_attr("ucp.note", {"stringValue": value})])
        with pytest.raises(AssertionError):
            assert_spans_have_no_forbidden_text([span])


def test_short_4111_in_a_value_fails() -> None:
    span = _span(attributes=[_attr("ucp.note", {"stringValue": "card 4111"})])
    with pytest.raises(AssertionError, match="4111"):
        assert_spans_have_no_forbidden_text([span])


@pytest.mark.parametrize(
    "where",
    [
        "name",
        "service",
        "attribute key",
        "attribute array",
        "attribute kvlist value",
        "attribute kvlist key",
        "status message",
        "event name",
        "event attribute",
        "link attribute",
    ],
)
def test_test_card_number_is_found_in_each_scanned_field(where: str) -> None:
    value = {"stringValue": PAN}
    cases: dict[str, dict[str, Any]] = {
        "name": {"name": f"POST {PAN}"},
        "service": {"service": PAN},
        "attribute key": {"attributes": [_attr(PAN, {"stringValue": "x"})]},
        "attribute array": {"attributes": [_attr("a", {"arrayValue": {"values": [value]}})]},
        "attribute kvlist value": {
            "attributes": [_attr("a", {"kvlistValue": {"values": [{"key": "k", "value": value}]}})]
        },
        "attribute kvlist key": {
            "attributes": [
                _attr(
                    "a", {"kvlistValue": {"values": [{"key": PAN, "value": {"stringValue": "x"}}]}}
                )
            ]
        },
        "status message": {"status": {"code": 2, "message": f"declined {PAN}"}},
        "event name": {"events": [{"timeUnixNano": "1", "name": PAN, "attributes": []}]},
        "event attribute": {
            "events": [{"timeUnixNano": "1", "name": "e", "attributes": [_attr("a", value)]}]
        },
        "link attribute": {
            "links": [{"traceId": "a" * 32, "spanId": "b" * 16, "attributes": [_attr("a", value)]}]
        },
    }
    with pytest.raises(AssertionError):
        assert_spans_have_no_forbidden_text([_span(**cases[where])])


# ---- the forbidden words still fail --------------------------------------------------------


@pytest.mark.parametrize("word", [*FORBIDDEN, *FORBIDDEN_WORDS])
def test_each_forbidden_word_fails_in_a_value_in_any_case(word: str) -> None:
    for text in (f"x {word} y", f"x {word.upper()} y"):
        span = _span(attributes=[_attr("ucp.note", {"stringValue": text})])
        with pytest.raises(AssertionError):
            assert_spans_have_no_forbidden_text([span])


def test_forbidden_word_in_a_span_name_fails() -> None:
    with pytest.raises(AssertionError):
        assert_spans_have_no_forbidden_text([_span(name="GET /address")])


def test_a_clean_span_passes() -> None:
    assert_spans_have_no_forbidden_text([_span()])


def test_span_texts_has_no_id_and_no_time() -> None:
    span = _span(
        events=[{"timeUnixNano": "1793807063145087052", "name": "e", "attributes": []}],
        links=[{"traceId": "c" * 32, "spanId": "d" * 16, "attributes": []}],
    )
    joined = "\n".join(span_texts(span))
    for hidden in (
        span["traceId"],
        span["spanId"],
        span["parentSpanId"],
        span["startTimeUnixNano"],
        span["endTimeUnixNano"],
        "1793807063145087052",
        "c" * 32,
        "d" * 16,
    ):
        assert hidden not in joined
    assert "POST /checkout-sessions" in joined and "business" in joined and "201" in joined
