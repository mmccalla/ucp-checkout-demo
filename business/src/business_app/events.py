"""Business log rows for the timeline (AC-100).

Each row has the `Request-Id` of the Platform request. A row never has a header value, a body,
a token or a credential. It has only the fields in ROW_KEYS.
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
import time
from typing import Any

from ucp_core import telemetry
from ucp_core.constants import ROOT

ROW_KEYS = {
    "ts",
    "side",
    "request_id",
    "method",
    "path",
    "status",
    "code",
    "replayed",
    "idempotency_key_present",
    "unknown_root_fields",
    "signature",
    "note",
    "webhook_id",
    "event_type",
    "attempt",
    "dead_letter",
    "trace_id",
    "field",
    "old_value",
    "new_value",
}
_lock = threading.Lock()


def log_file() -> pathlib.Path:
    return pathlib.Path(
        os.environ.get("BUSINESS_EVENTS", str(ROOT / ".run" / "timeline" / "business.jsonl"))
    )


def write(row: dict[str, Any]) -> dict[str, Any]:
    clean = {k: v for k, v in row.items() if k in ROW_KEYS}
    clean["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    clean["side"] = "business"
    tid = telemetry.trace_id()  # AC-56: each log row has the trace ID of its server span
    if tid:
        clean["trace_id"] = tid
    f = log_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with _lock, f.open("a") as fh:
        fh.write(json.dumps(clean, sort_keys=True) + "\n")
    return clean
