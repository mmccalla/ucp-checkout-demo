"""Latency statistics and the G8 verdict (AC-117, spec DM-25).

Limits (95th percentile, in seconds): Create 4, Update 5, Complete 10, and an error rate of 0 %.
Source: https://developers.google.com/merchant/ucp/guides/overview/native-checkout, section
"Service level objectives" (page read on 28 Oct 2026; the page has no version in its URL).
The 50th-percentile targets (1 s, 1 s, 6 s) of the same table are only recorded (DM-25).
"""

from __future__ import annotations

import dataclasses
import math

P95_LIMITS = {"create": 4.0, "update": 5.0, "complete": 10.0}
P50_TARGETS = {"create": 1.0, "update": 1.0, "complete": 6.0}  # recorded only
CALLS = 100


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile: the value at rank ceil(pct/100 * n) of the sorted list."""
    if not values:
        raise ValueError("no values")
    s = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(s)))
    return s[rank - 1]


@dataclasses.dataclass
class OpStats:
    op: str
    calls: int
    errors: int
    p50: float
    p95: float
    max: float
    limit_p95: float
    target_p50: float

    @property
    def error_rate(self) -> float:
        return self.errors / self.calls if self.calls else 1.0


def summarise(op: str, seconds: list[float], errors: int) -> OpStats:
    # A failed call counts as a call with an error. Its time is in `seconds` too.
    return OpStats(
        op=op,
        calls=len(seconds),
        errors=errors,
        p50=percentile(seconds, 50),
        p95=percentile(seconds, 95),
        max=max(seconds),
        limit_p95=P95_LIMITS[op],
        target_p50=P50_TARGETS[op],
    )


def verdict(stats: list[OpStats], expected_calls: int = CALLS) -> list[str]:
    """Return the list of violations. An empty list is a pass."""
    out: list[str] = []
    seen = {s.op for s in stats}
    for op in P95_LIMITS:
        if op not in seen:
            out.append(f"{op}: no result")
    for s in stats:
        if s.calls != expected_calls:
            out.append(f"{s.op}: {s.calls} calls, {expected_calls} needed")
        if s.p95 > s.limit_p95:
            out.append(f"{s.op}: p95 {s.p95:.3f} s is above {s.limit_p95:g} s")
        if s.errors:
            out.append(f"{s.op}: {s.errors} error(s) in {s.calls} calls (the limit is 0 %)")
    return out
