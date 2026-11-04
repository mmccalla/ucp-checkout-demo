# ADR 0015: G5 conformance gate, run in a loopback-only network namespace

- Status: PROPOSED for S5. G5 does not pass yet (see "Open items").
- Date: 2026-10-28.
- Owner: Mark McCalla.

## Context

Spec T-91 and T-93 say that G5 runs the pinned conformance suite against the Business in `MODE=ci`. The pin is `conformance/PIN` (commit `016ecbc22240affdec4429a60d539bedd04ab51b`, 77 test methods). AC-119 forbids an unapproved skip. AC-120 fixes the number of test cases.

## Decision

1. `conformance/gate.py` runs the full suite. It has no `-k` filter. It reads the JUnit file and fails on a failure, on an error, on a skip that is not in `conformance/approved-skips.txt`, on an approved skip that did not skip, and on a count other than the pin (AC-119, AC-120). Unit tests with synthetic JUnit files are in `tests/s5/unit/test_conformance_gate.py`.
2. DM-26. The suite starts a mock webhook server and a mock agent server on `0.0.0.0` (ports 8284 and 8285; `integration_test_utils.py` lines 273 and 361 at the pin). The pinned code stays unchanged. The gate runs the Business and the suite in a new network namespace with only a loopback interface (`unshare --map-root-user --net`). No other computer, and no other process on the box, can reach them. CONFIRMED on the box: a bind to `0.0.0.0` inside the namespace works and the namespace has only `lo`.
3. The suite reads its input through absl flags. The `pytest --conformance_input` option in its README does not work (its `conftest.py` has no such option). `conformance/s5_flags.py` is a pytest plugin that sets the two flags from environment variables. The suite files stay unchanged.
4. `conformance/input/conformance_input.json` is the suite file `flower_shop/conformance_input.json` with one change: `required_capabilities` lists checkout, order and fulfillment. The demo has no discount and no buyer consent (spec 1.3). PM or Mark must confirm this choice.
5. CI-only seams in the Business (`MODE=ci` only, tests in `tests/s5/unit/test_ci_seams.py`): an `http` profile URL on a loopback host with the one path `/profiles/shopping-agent.json`, and the path `/testing/simulate-shipping/{id}` with the `Simulation-Secret` header (T-93). Demo mode has none of them (AC-107).

## Open items (blockers, not hidden)

- The agent profile of the suite has no `services` and no `payment_handlers`. The Business checks the pinned `platform_profile` schema and answers 422 `profile_malformed`. To pass, a CI-only relaxation of a schema rule is needed. I did not add it (rule: do not work around a spec rule).
- The mock payment instrument of the suite gives HTTP 400 at `$.payment.instruments[0].credential.type` (UNVERIFIED cause; seen in a scratch run with the relaxation).
- 7 tests skip (6 discount tests, and `protocol_test.test_discovery_urls`: "Schemas not yet published on remote ucp.dev domain"). They need approval in `approved-skips.txt` (OQ-4). The file is empty.
- G5 is not in `tools/gates/run_all.sh`, because it fails and each commit must pass all gates. The result of the first run is in local run records (not in this repository).
