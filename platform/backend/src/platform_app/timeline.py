"""Merged request timeline (AC-07, AC-100).

- The Platform writes one row for each checkout call (after the last try).
- The Business writes one row for each request it gets (`business_app.events`).
- `merged()` joins the rows on `request_id`. The order is the Platform call order. The
  Business rows for a call come after the Platform row of that call.
- A row never has a header value, a body, a token, a key or a credential. Only the keys
  in ROW_KEYS go into a row.
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

from .checkout_client import SECURITY_TOKEN_IN_RESPONSE, Result

ROW_KEYS = {
    "ts",
    "side",
    "request_id",
    "op",
    "method",
    "path",
    "status",
    "code",
    "tries",
    "idempotency_key_present",
    "transport_error",
    "schema_problems",
    "view_state",
    "note",
    # S3 rows that are not a checkout call (AC-59, AC-60, AC-63)
    "kind",
    "name",
    "phase",
    "source",
    "not_ucp",
    "result",
    "status_code",
    "seq",
    "trace_id",
}
EVENT_KINDS = ("request", "state", "buyer_action", "error", "gpay", "mapping")
# AC-63 (spec v1.1.4): 5 source labels. LOCAL STEP only for the 2 Google Pay mapping steps.
SOURCES = ("LIVE CALL", "RECORDED", "GOOGLE PAY TEST", "SIMULATED", "LOCAL STEP")


def _path(env: str, default: str) -> pathlib.Path:
    return pathlib.Path(os.environ.get(env, str(ROOT / ".run" / "timeline" / default)))


class Timeline:
    def __init__(
        self, platform_file: pathlib.Path | None = None, business_file: pathlib.Path | None = None
    ) -> None:
        self.platform_file = platform_file or _path("PLATFORM_EVENTS", "platform.jsonl")
        self.business_file = business_file or _path("BUSINESS_EVENTS", "business.jsonl")
        self._lock = threading.Lock()

    def record(self, res: Result, view_state: str | None = None) -> dict[str, Any]:
        body = res.body if isinstance(res.body, dict) else {}
        code = body.get("code")
        if code is None and body.get("messages"):
            first = body["messages"][0]
            code = first.get("code") if isinstance(first, dict) else None
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "side": "platform",
            "kind": "request",
            "source": "LIVE CALL",
            "not_ucp": False,
            "request_id": res.request_id,
            "op": res.op,
            "method": res.method,
            "path": res.path,
            "status": res.status,
            "code": code,
            "tries": res.tries,
            "idempotency_key_present": res.idempotency_key is not None,
            "transport_error": res.transport_error,
            "schema_problems": len(res.schema_problems),
            "view_state": view_state,
            "trace_id": telemetry.trace_id(),  # AC-56
        }
        if any(SECURITY_TOKEN_IN_RESPONSE in p for p in res.schema_problems):  # AC-93
            row["note"] = "security event: credential.token in a response"
        clean = {k: v for k, v in row.items() if k in ROW_KEYS}
        if clean.get("trace_id") is None:
            clean.pop("trace_id", None)
        self.platform_file.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.platform_file.open("a") as fh:
            fh.write(json.dumps(clean, sort_keys=True) + "\n")
        return clean

    def event(
        self,
        kind: str,
        name: str,
        *,
        phase: str | None = None,
        source: str = "LIVE CALL",
        not_ucp: bool = False,
        result: Any = None,
        status_code: str | None = None,
        view_state: str | None = None,
    ) -> dict[str, Any]:
        """Write a row for a state change, a buyer action, an error or a Google Pay step.

        Only scalar values go in. `result` must be a bool, a short string or None.
        """
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind {kind!r}")
        if source not in SOURCES:
            raise ValueError(f"unknown source {source!r}")
        if result is not None and not isinstance(result, (bool, int, str)):
            raise ValueError("result must be a scalar")
        if isinstance(result, str):
            result = result[:80]
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "side": "platform",
            "kind": kind,
            "name": str(name)[:80],
            "phase": phase,
            "source": source,
            "not_ucp": bool(not_ucp),
            "result": result,
            "status_code": None if status_code is None else str(status_code)[:40],
            "view_state": view_state,
            "trace_id": telemetry.trace_id(),  # AC-56
        }
        clean = {k: v for k, v in row.items() if k in ROW_KEYS}
        if clean.get("trace_id") is None:
            clean.pop("trace_id", None)
        self.platform_file.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.platform_file.open("a") as fh:
            fh.write(json.dumps(clean, sort_keys=True) + "\n")
        return clean

    @staticmethod
    def _read(p: pathlib.Path) -> list[dict[str, Any]]:
        if not p.exists():
            return []
        rows = []
        for line in p.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows

    def merged(self) -> list[dict[str, Any]]:
        plat = self._read(self.platform_file)
        biz: dict[str, list[dict[str, Any]]] = {}
        for r in self._read(self.business_file):
            biz.setdefault(str(r.get("request_id")), []).append(r)
        out: list[dict[str, Any]] = []
        for p in plat:
            out.append(p)
            out.extend(biz.pop(str(p.get("request_id")), []))
        for rows in biz.values():  # Business rows with no Platform row (direct calls)
            out.extend(rows)
        return out
