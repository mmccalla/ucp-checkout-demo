"""AC-114, AC-119, AC-120: the G5 hard-fail rules (spec T-91, input-engineering 7.3).

The tests use synthetic JUnit files. They do not start the suite.
"""

from __future__ import annotations

import pathlib

import gate
import pytest

PIN = gate.Pin("https://example.invalid/conformance", "0" * 40, 5)


def junit(tmp: pathlib.Path, cases: list[tuple[str, str]]) -> pathlib.Path:
    """cases: (name, kind) with kind in pass, failure, error, skipped."""
    rows = []
    for name, kind in cases:
        inner = {
            "pass": "",
            "failure": '<failure message="x"/>',
            "error": '<error message="x"/>',
            "skipped": '<skipped message="no fixture"/>',
        }[kind]
        rows.append(f'<testcase classname="a_test.A" name="{name}">{inner}</testcase>')
    p = tmp / "junit.xml"
    p.write_text(f'<testsuites><testsuite name="pytest">{"".join(rows)}</testsuite></testsuites>')
    return p


def five(kinds: dict[str, str] | None = None) -> list[tuple[str, str]]:
    base = {f"t{i}": "pass" for i in range(5)}
    base.update(kinds or {})
    return list(base.items())


def test_all_pass_is_ok(tmp_path: pathlib.Path) -> None:
    v = gate.evaluate(junit(tmp_path, five()), PIN, set())
    assert v.ok and v.total == 5 and v.passed == 5 and v.violations == []


def test_failure_fails(tmp_path: pathlib.Path) -> None:
    v = gate.evaluate(junit(tmp_path, five({"t1": "failure"})), PIN, set())
    assert not v.ok and v.failures == ["a_test.A.t1"]


def test_error_fails(tmp_path: pathlib.Path) -> None:
    v = gate.evaluate(junit(tmp_path, five({"t2": "error"})), PIN, set())
    assert not v.ok and v.errors == ["a_test.A.t2"]


def test_unapproved_skip_fails_ac119(tmp_path: pathlib.Path) -> None:
    v = gate.evaluate(junit(tmp_path, five({"t3": "skipped"})), PIN, set())
    assert not v.ok
    assert any("AC-119: unapproved skip a_test.A.t3" in x for x in v.violations)


def test_approved_skip_passes(tmp_path: pathlib.Path) -> None:
    v = gate.evaluate(junit(tmp_path, five({"t3": "skipped"})), PIN, {"a_test.A.t3"})
    assert v.ok and v.skipped == [("a_test.A.t3", "no fixture")]


def test_approved_skip_that_did_not_skip_fails_ac119(tmp_path: pathlib.Path) -> None:
    v = gate.evaluate(junit(tmp_path, five()), PIN, {"a_test.A.t3"})
    assert not v.ok
    assert any("AC-119: approved skip did not skip a_test.A.t3" in x for x in v.violations)


@pytest.mark.parametrize("n", [4, 6])
def test_wrong_count_fails_ac120(tmp_path: pathlib.Path, n: int) -> None:
    cases = [(f"t{i}", "pass") for i in range(n)]
    v = gate.evaluate(junit(tmp_path, cases), PIN, set())
    assert not v.ok
    assert any(f"AC-120: {n} test cases, the pin has 5" in x for x in v.violations)


def test_pin_file_of_the_repo_is_valid() -> None:
    pin = gate.read_pin(gate.HERE / "PIN")
    assert pin.commit == "016ecbc22240affdec4429a60d539bedd04ab51b"
    assert pin.test_methods == 77
    assert pin.repo == "https://github.com/Universal-Commerce-Protocol/conformance"


def test_pin_with_a_short_commit_is_refused(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "PIN"
    p.write_text("repo=x\ncommit=016ecbc\ntest_methods=77\n")
    with pytest.raises(ValueError):
        gate.read_pin(p)


def test_approved_skips_file_reads_comments(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "approved-skips.txt"
    p.write_text("# header\n\na_test.A.t1  # reason\nb_test.B.t2\n")
    assert gate.read_approved(p) == {"a_test.A.t1", "b_test.B.t2"}


def test_gate_runs_the_full_suite_without_a_filter() -> None:
    src = (gate.HERE / "gate.py").read_text()
    assert '"-k"' not in src and "'-k'" not in src


def test_t113_listed_failure_is_allowed(tmp_path: pathlib.Path) -> None:
    v = gate.evaluate(junit(tmp_path, five({"t1": "failure"})), PIN, set(), {"a_test.A.t1"})
    assert v.ok and v.violations == []


def test_t113_unlisted_failure_fails(tmp_path: pathlib.Path) -> None:
    v = gate.evaluate(
        junit(tmp_path, five({"t1": "failure", "t2": "failure"})), PIN, set(), {"a_test.A.t1"}
    )
    assert not v.ok and any("unlisted failure" in x for x in v.violations)


def test_t113_listed_test_that_passes_fails(tmp_path: pathlib.Path) -> None:
    v = gate.evaluate(junit(tmp_path, five()), PIN, set(), {"a_test.A.t1"})
    assert not v.ok and any("did not fail" in x for x in v.violations)


def test_t113_the_list_has_six_entries() -> None:
    assert gate.read_approved(gate.HERE / "approved-failures.txt") == {
        "protocol_test.ProtocolTest.test_version_negotiation",
        "card_credential_test.CardCredentialTest.test_card_credential_payment",
        "order_test.OrderTest.test_order_update",
        "order_test.OrderTest.test_order_adjustments",
        "invalid_input_test.InvalidInputTest.test_invalid_adjustment_status",
        "invalid_input_test.InvalidInputTest.test_malformed_adjustment_payload",
    }


def test_t94_the_skip_list_has_seven_entries() -> None:
    skips = gate.read_approved(gate.HERE / "approved-skips.txt")
    assert len(skips) == 7
    assert "protocol_test.ProtocolTest.test_discovery_urls" in skips
