"""AC-93 (DATA AC-R6): a checkout response with `credential.token` fails validation.

The Platform logs a security event. The log, the problem list, the view and the timeline row
never have the token value.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

import pytest
from platform_app import checkout_view
from platform_app.timeline import Timeline

from tests.s2.unit.test_complete_recovery import ID, Script, co, make

SECRET = "tok_SECRET_VALUE_0123456789"


def leaking() -> tuple[int, dict[str, Any]]:
    status, body = co("completed", order={"id": "o1"})
    body["payment"] = {
        "instruments": [
            {
                "id": "i1",
                "handler_id": "h",
                "type": "card",
                "display": {"brand": "VISA", "last_digits": "1234"},
                "credential": {"type": "PAYMENT_GATEWAY", "token": SECRET},
            }
        ]
    }
    return status, body


def test_token_in_response_fails_validation_and_logs_event_without_token(
    caplog: pytest.LogCaptureFixture, tmp_path: pathlib.Path
) -> None:
    caplog.set_level(logging.DEBUG)
    c, _ = make(Script([], [leaking()]))
    r = c.get(ID)
    assert r.schema_problems == [
        "$.payment.instruments[0].credential.token: SECURITY credential_token_in_response"
    ]
    events = [x for x in caplog.records if x.name == "platform.security"]
    assert len(events) == 1 and "credential_token_in_response" in events[0].getMessage()
    assert SECRET not in caplog.text
    v = checkout_view.interpret(checkout_view.Session(), r)
    assert (
        v.state == "setup_problem" and v.problem and v.problem["code"] == "response_schema_invalid"
    )
    assert SECRET not in json.dumps(v.problem)
    tl = Timeline(tmp_path / "p.jsonl", tmp_path / "b.jsonl")
    row = tl.record(r, v.state)
    assert row["schema_problems"] == 1 and "credential.token" in row["note"]
    assert SECRET not in (tmp_path / "p.jsonl").read_text()


def test_response_without_credential_is_not_an_event(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    c, _ = make(Script([], [co("ready_for_complete")]))
    c.get(ID)
    assert not [x for x in caplog.records if x.name == "platform.security"]
