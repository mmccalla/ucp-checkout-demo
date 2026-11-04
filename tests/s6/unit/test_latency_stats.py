"""AC-117: the G8 statistics and the verdict (the live run is `tools/latency/run_g8.sh`)."""

from __future__ import annotations

import pytest
import g8_stats as stats


def test_nearest_rank_percentile() -> None:
    v = [float(i) for i in range(1, 101)]
    assert stats.percentile(v, 95) == 95.0
    assert stats.percentile(v, 50) == 50.0
    assert stats.percentile([3.0, 1.0, 2.0], 95) == 3.0
    with pytest.raises(ValueError):
        stats.percentile([], 95)


def ok_stats(**over: float) -> list[stats.OpStats]:
    base = {"create": 0.5, "update": 0.5, "complete": 1.0}
    base.update(over)
    return [stats.summarise(op, [t] * 100, 0) for op, t in base.items()]


def test_pass() -> None:
    assert stats.verdict(ok_stats()) == []


@pytest.mark.parametrize(("op", "slow"), [("create", 4.01), ("update", 5.01), ("complete", 10.01)])
def test_p95_above_the_google_limit_fails(op: str, slow: float) -> None:
    v = stats.verdict(ok_stats(**{op: slow}))
    assert len(v) == 1 and v[0].startswith(f"{op}: p95")


@pytest.mark.parametrize("op", ["create", "update", "complete"])
def test_the_limit_itself_passes(op: str) -> None:
    assert stats.verdict(ok_stats(**{op: stats.P95_LIMITS[op]})) == []


def test_one_error_fails_even_if_fast() -> None:
    s = ok_stats()
    s[2] = stats.summarise("complete", [1.0] * 100, 1)
    v = stats.verdict(s)
    assert v == ["complete: 1 error(s) in 100 calls (the limit is 0 %)"]


def test_wrong_number_of_calls_and_missing_op_fail() -> None:
    s = ok_stats()
    s[0] = stats.summarise("create", [0.1] * 99, 0)
    assert any("99 calls, 100 needed" in x for x in stats.verdict(s))
    assert "complete: no result" in stats.verdict(s[:2])


def test_p50_targets_do_not_fail() -> None:
    # SLO p50 values (1 s, 1 s, 6 s) are recorded only (DM-25).
    s = [stats.summarise(op, [3.5] * 100, 0) for op in ("create", "update")]
    s.append(stats.summarise("complete", [9.5] * 100, 0))
    assert stats.verdict(s) == []
