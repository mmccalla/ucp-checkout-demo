# S4 completion report

Owner: Mark McCalla. Repository: https://github.com/mmccalla/ucp-checkout-demo (branch `main`). Times are Europe/London (UTC+0 on 2026-10-28).
Pins: UCP 2026-04-08 at `9c9d6fc`. Google Pay handler `com.google.pay` 2026-01-23.
Spec section 5 sha256 (`sed -n 172,219p 03-spec.md | sha256sum`): `a96cddc5fc62f87cba0c3dc546b10d6769376daf33d8e3a3fdc1178c0f5e5feb`. It did not change.

## 1. Result

S4 is NOT complete. S4 exit needs G1 to G4, G6 and G7 PASS and the M-02 and M-03 records. G1 to G4, G6 and G7 PASS on each pushed commit. M-02 and M-03 are BLOCKED (they need Mark). M1 (M-01) is NOT RUN (it needs Mark). AC-115 PASS: two loops of 20 of 20 at `c494f1e` (section 6).
S5 and S6 are not started (the brief says to stop after this report).

## 2. Commits on origin/main (each had G1 to G4, G6 and G7 PASS on a clean tree before the push; M1 NOT RUN)

| Commit | Content | Gate evidence |
|---|---|---|
| `dc9e955`, `cf223cd`, `38d5db8` | S4a to S4c: LOCAL STEP label, mock PSP, T-105 decline, order, decline UI, `m01_ready.sh` | `gates-dc9e955/`, `gates-cf223cd/`, `gates-38d5db8/` (G1 to G4, G7 in the S3 slice) |
| `79412f9` | Order webhooks, response signatures, Get Order, gate G6 (AC-64 to AC-75, AC-113) | G6 in every later gates run |
| `9b5e411` | CI-only test seam for the same-key Complete check | `gates-c1/` |
| `1ed4fbf` | S4 UI of spec 15.8 rows 1 to 10 | `gates-c2/` |
| `8b64705` | AC-44 Complete with no response, ADR 0012 | `gates-c3/` |
| `6637b73` | Jaeger 2.22.0 release binary (T-106), ADR 0013 | `gates-c4/` |
| `729dbb6` | OpenTelemetry, trace IDs in log rows (AC-42, AC-54, AC-56), ADR 0014 | `gates-c5/` |
| `2eff73a` | Audit record for each payment attempt (AC-55) | `gates-c6/` |
| `d194756` | AC-39, AC-45, AC-57, AC-91, AC-93 | `gates-c7/` |
| `c494f1e` | Log-order check for AC-115, Jaeger ports in `m01_ready.sh` | `gates-c8/` |

Gate result at `c494f1e` (`gates-c8/summary.md`): G1 PASS, G2 PASS, G3 PASS, G4 PASS, G6 PASS (16 tests), G7 PASS (44 tests), G5 and G8 not in the slice, M1 NOT RUN.
Bundles (in `<backup folder>/`, sha256): `20261028T161251+0000-c8-log-order-c494f1ee59dd.bundle` e1b07ee2a1376ab080dcac8c007a880c099e8d4ee0e1ef962a0c41a57cb91cee; `20261028T155845+0000-c7-closure-d194756a9bce.bundle` 5cbb1cca31bf47c04e486f1ec0df336421a729e3e488700201559239b84b3de3; `20261028T153308+0000-c6-audit-2eff73af5999.bundle` 6dd4d379cc5ba18c487d9ab56ad3d79cdb11c4682362eb5807985ab89710ae31; `20261028T152301+0000-c5-otel-729dbb630ef5.bundle` e26d54f3987dd0443a1acd50e901f036c96ade7f35a0ea9220401231bb4ef56f; c1 58c4c4e5…518cfb; c2 0772b21b…f7c8; c3 ee60d0fe…28b3; c4 01312298…45d4. (`.bundle.sha256` files are next to each bundle.)

## 3. S4 AC table

Test paths are in `tests/`. The evidence files of this report are local run records. They are not in this repository.

| AC | Result | Commit | Test and evidence | Reason or note |
|---|---|---|---|---|
| AC-31 | PASS | `cf223cd` | `tests/s4/unit/test_complete.py`, `tests/s3/e2e/test_g7_s4_ux.py`; `g7/ux-ac31-decline-keys.json` | One instrument, checkout `handler_id`, token shown as `[REDACTED]`. The token is Google's documented example token. |
| AC-32 | PASS | `cf223cd` | `test_ac32_undeclared_handler_rejected_no_charge` | HTTP 400, no PSP charge. |
| AC-33 | PARTIAL | `cf223cd` | `test_ac33_ac112_*`, G7 happy path | Needs the M-03 `PaymentData` fixture. M-03 is BLOCKED (needs Mark). The test uses the documented example token. |
| AC-34 | PASS | `cf223cd` | `test_ac34_t105_*`; `g7/st13-psp-attempts.json` | HTTP 200, `ready_for_complete`, no `order`, `payment_failed` `recoverable`, same key gives the stored response. |
| AC-35 | PASS | `cf223cd` | `test_ac35_*`, G7 `test_ac34_ac35_st13_*`; `g7/st13-ops.json` | New token, new key (3 keys). |
| AC-39 | PASS (unit level) | `d194756` | `tests/s2/unit/test_out_of_stock_ac39.py` | HTTP 200 and HTTP 409 give one view state `out_of_stock`, `send_get` is true, one Complete only. A 409 idempotency conflict does not match. No browser test for this state (UNVERIFIED in the UI). |
| AC-44 | PASS | `8b64705` | `tests/s2/unit/test_complete_recovery.py`, `test_g7_s4_ux.py`; `g7/ac44-response-lost.json` | Get with backoff 0.5/1/2 s, stop at `expires_at`, at most one same-key Complete. Basis uses UCP 2026-08-25 (see section 8). |
| AC-45 | PASS | `d194756` | `tests/s2/unit/test_in_progress_ac45.py` | CI-only switch `BUSINESS_FAULTS=complete_in_progress=N,in_progress_gets=K`. The Platform polls Get, sends no Update and no second Complete, PSP has one charge. Cap of 30 Get calls when `expires_at` is absent. |
| AC-46 | PASS | `cf223cd` | `test_ac46_*` | Stored response, one charge. |
| AC-54 | PARTIAL | `729dbb6` | `tests/s4/contract/test_traces.py`; `traces/ac54-span-scan.json` | Logs, spans, files, SQLite, PSP records, page, console and export have no token. v1 has no LLM, so the LLM part waits for S7 (build plan). |
| AC-55 | PASS | `2eff73a` | `tests/s4/unit/test_audit.py` (10), G7 ST13; `g7/ac55-audit-records.json` | One record for each attempt, all fields of 02-design section 12, no forbidden field. |
| AC-56 | PASS | `729dbb6` | `tests/s4/contract/test_traces.py`, `test_live_traces.py`; `traces/ac56-trace-report.json`, `ac56-live-trace.json` | Client and server span with one trace ID, same ID in each log line. Jaeger `/api/v3/*`. |
| AC-57 | PASS | `d194756` | `tests/s4/contract/test_smoke_payloads.py`; `ac57/ac57-smoke-payloads.json` | 7 payloads (create, update, complete, get, cancel, instrument) valid against the pinned schemas. |
| AC-64 | PASS | `79412f9` | `tests/s4/g6/test_webhooks.py::test_ac64_*` | Flag on: checked. Flag off: "not signed". |
| AC-65 | PASS | `79412f9` | `test_ac64_ac65_flag_off_not_signed_but_webhooks_signed` | |
| AC-66 | PARTIAL | `79412f9` | `test_ac66_ac74_ac75_three_signed_events_applied_in_order` | Signature, 2xx and apply tested. No test of the Business client span and the Platform server span for the webhook. |
| AC-67 | PASS | `79412f9` | `test_ac67_bad_signature_401_nothing_processed` | |
| AC-68 | PASS | `79412f9` | `test_ac68_missing_or_partial_signature_401` | |
| AC-69 | PASS | `79412f9` | `test_ac69_signer_does_not_own_order_403` | |
| AC-70 | PASS | `79412f9` | `test_ac70_same_webhook_id_no_second_effect` | |
| AC-71 | PASS | `79412f9` | `test_ac71_shipped_after_delivered_does_not_move_back` | |
| AC-72 | PARTIAL | `79412f9` | `test_ac72_503_then_retry_same_id_and_timestamp` | Same `Webhook-Id` and `Webhook-Timestamp`, 2xx. No test that the trace shows each attempt. |
| AC-73 | PASS | `79412f9` | `test_ac73_reconcile_get_order_same_state` | |
| AC-74 | PASS | `79412f9`, `cf223cd` | `test_ac66_ac74_ac75_*`, G7 `test_ac64_ac73_ac74_*`; `g7/ac74-webhooks.json`, `g7/ac74-order-events.png` | Three signed events in order. UI labels "Simulated". |
| AC-75 | PASS | `79412f9` | same as AC-74 | Confirmation e-mail goes to a log. |
| AC-90 | PASS | `cf223cd` | `test_ac90_*` | |
| AC-91 | PASS | `d194756` | `tests/s4/unit/test_complete.py::test_ac91_*` (3) | Lowercase brand becomes uppercase and one log row has the old and the new value. A brand outside the enum gives HTTP 400 and no charge. |
| AC-93 | PASS | `d194756` | `tests/s2/unit/test_response_token_ac93.py` | Validation fails. Event on logger `platform.security`. Token value absent from log, problem list, view and timeline row. |
| AC-97 | PASS | `cf223cd` | `test_ac97_*` | |
| AC-102 | PARTIAL | `1ed4fbf` | `tests/s3/e2e/test_g7_flow.py::test_ac102_banner_after_stub_approval` | Banner text tested with the CI stub. A real TEST sheet token needs M-01 (UNVERIFIED). |
| AC-112 | PASS | `cf223cd` | `test_ac33_ac112_*` | One PSP call, `order` with `id` and `permalink_url`, instrument echoed with no `credential`. |
| AC-113 | PASS | `79412f9` | `tests/s4/g6/test_webhooks.py::test_ac113_*`, `tests/s4/g6/test_request_signatures.py` | G6 PASS. |
| AC-115 | PASS (with a pause note) | `c494f1e` | local run records (not in this repository) | 2 loops of 20 of 20, exit 0, no rerun, no raised timeout, log-order check included. 3 runs span a box pause (section 6). |
| M-02 | BLOCKED | none | none | Needs Mark. Not done. |
| M-03 | BLOCKED | none | none | Needs Mark. Not done. |

Other S4 items: UX-U-18 PASS (`g7/ux-u-18-contrast-*.json`, lowest ratio 6.66:1). AC-63 PASS (`g7/ac63-labels.json`). AC-42 PASS (`traces/ac42-replayed-attribute.json`, `729dbb6`).

## 4. Decisions and records

### ADR 0010 item 10 against "Try again" (ADR 0012, `8b64705`)
The code was right and ADR 0010 item 10 was wrong. "Try again" stays for Create and Update only (AC-52 has no Complete). A Complete with no response is recovered by the Platform itself: one Complete, then Get with backoff 0.5, 1 and 2 s, stop at `expires_at`. Get `completed` or `canceled` ends it. Get `complete_in_progress` starts no new Complete. Get `ready_for_complete` or no Get answer: one identical Complete with the same key. ADR 0010 item 10 now points to ADR 0012. The 4 lines that cite UCP 2026-08-25 carry `g1-allow-unpinned`. This use is PROPOSED (ADR 0012, spec 15.9 row 3 and 4).

### Jaeger (T-106, ADR 0013, `6637b73`)
- Version 2.22.0, official release binary `jaeger-2.22.0-linux-amd64`, started by `tools/jaeger.sh`.
- Archive sha256 `cb0c0be9a4b8fba424bbbc6217b0feb0adeea3bca5b73a83db1af31bb7d34389`.
- Binary sha256 `fa574f53e2f739301f301f66e5608c84d0b9a90cdd08e4f6cba8809d171854e1`.
- gpg: "Good signature" from "Jaeger Tracing Artifact Signing <jaeger-tracing@googlegroups.com>", key BD0B 0260 14C7 2526 1C94 7887 B42D 1DB0 F079 690F (not certified by a trusted chain: gpg warning, the fingerprint is pinned in `pins/PINS.toml`).
- Evidence: local run records (not in this repository).

### OpenTelemetry pins (ADR 0014, `729dbb6`; in `uv.lock`)
| Package | Version | Documentation URL |
|---|---|---|
| opentelemetry-api | 1.45.1 | https://opentelemetry.io/docs/languages/python/getting-started/ |
| opentelemetry-sdk | 1.45.1 | https://opentelemetry.io/docs/languages/python/getting-started/ |
| opentelemetry-exporter-otlp-proto-http | 1.45.1 | https://opentelemetry.io/docs/languages/python/exporters/ |
| opentelemetry-instrumentation-fastapi | 0.66b1 | https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html |
| opentelemetry-instrumentation-httpx | 0.66b1 | https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html |

The last two pages are the `latest` pages. That they match 0.66b1 is UNVERIFIED. Version-pinned sources (ADR 0014, spec T-107 PROPOSED and Appendix A.2; each URL answered HTTP 200 on 2026-10-28): the PyPI page at each exact version (for example https://pypi.org/project/opentelemetry-sdk/1.45.1/ and https://pypi.org/project/opentelemetry-instrumentation-fastapi/0.66b1/) and the Git tags https://github.com/open-telemetry/opentelemetry-python/tree/v1.45.1 and https://github.com/open-telemetry/opentelemetry-python-contrib/tree/v0.66b1. Pages with a version path on Read the Docs answer HTTP 404. The `opentelemetry.io` and `latest` pages stay UNVERIFIED as version-pinned. The transitive packages are in ADR 0014.

### Diffs of the other design files (T-106; not in git)
`02-design.md` (section 13 network rule, line 599):
- before: "Docker Compose runs only helper tools that fetch no UCP profile, for example Jaeger (T-02). AC-122 tests the rule."
- after: "Jaeger is the official 2.22.0 release binary, started by `tools/jaeger.sh` (T-106, ADR 0013). It also listens on `127.0.0.1` only. It fetches no UCP profile. AC-122 tests the rule."

`04-build-plan.md` (S4 table, line 82), "Services and files": the old Compose file (Jaeger 2.22.0, removed by T-106) is now `tools/jaeger.sh` (Jaeger 2.22.0 release binary, T-106).
Backups of the old files: `backups/docs-edits/*.pre-t106-20261028T150440`.

### G1 marker (`g1-allow-unpinned`; spec v1.1.8 T-108 and AC-118 clauses 2 to 4: PROPOSED)
Status: PROPOSED, not approved. I did not change `tools/gates/g1.py`. ADR 0012 has the same text.

Marker lines (`rg`, 2026-10-28). With the August URL (4): `platform/backend/src/platform_app/checkout_client.py` lines 14 and 148; `tests/s2/unit/test_complete_recovery.py` line 5; `docs/adr/0012-s4-complete-recovery-and-try-again.md` line 16. Alias lines (2): `libs/ucp_core/schema_registry.py` lines 33 and 34. The earlier counts (4 in the ADR, 5 in this report) were wrong. T-108 expects 3 in `.py` files (the 4th line is a doc line).

Check of the 3 expected lines (each cites a the `ucp.dev` URL of version 2026-08-25 URL: yes for all 3):
- `checkout_client.py` line 14: URL yes. The marker is inside a docstring, not in a `#` comment. `AC-44` is on lines 13 and 15, not on line 14.
- `checkout_client.py` line 148: URL yes. Docstring text. `AC-45` is on line 143 (first line of the same docstring), not on line 148.
- `tests/s2/unit/test_complete_recovery.py` line 5: URL yes. Docstring text. `AC-44` is on line 1, not on line 5.
So no line has an AC ID in the same line or the same comment now.

What `g1.py` can do now, and the exact change (lines 62, 105 to 106 are the only marker code; `files()` scans all text suffixes):
1. Marker only on a line that cites a the `ucp.dev` URL of version 2026-08-25 URL: NO. Change: in the loop, if the marker is on the line and the `ucp.dev` URL of version 2026-08-25 is not in the line, add an error `file:line`.
2. Skip only the `ucp.dev` version check on a marked line: NO. Line 105 uses `continue`, which skips all 3 checks. Change: remove the `continue`. In the `UCP_URL_RE` loop, skip only when the line is marked and `ver == "2026-08-25"`. The GitHub commit check and the Google Pay check run on every line.
3. Fail if the marker is on any other line: NO. Same change as 1 (an error for a marked line without the URL).
(a) Marker comments only in `.py` files outside `tools/gates/`: NO. Change: look for the marker only when `p.suffix == ".py"` and `rel.parts[:2] != ("tools", "gates")`. Effects: (i) the constant at `g1.py` line 62 is not read; (ii) the doc lines (ADR 0012 line 16 and the prose lines) lose the skip. ADR 0012 line 16 cites the August URL, so G1 would then fail on it. I must write that line without the URL pattern (for example "ucp.dev 2026-08-25, page 'Complete Checkout'"). (iii) The marker must be a real comment. The 3 lines are docstring text. A `tokenize` COMMENT test, or a regex `#\s*g1-allow-unpinned` at the end of the line, is needed. With `tokenize` the 3 lines fail. Then the URL must move to a `#` comment, or the regex test is used.
(b) The same comment must contain `AC-44` or `AC-45`: NO. Change: require `re.search(r"AC-4[45]\b", comment)` in the same comment. The 3 lines must change to put the ID in the marker comment (the marker, then AC-44, in a hash comment). This touches the demo source files (`checkout_client.py`, a test), so it goes on branch `s5-s6`. Line length: ruff must still pass.
4. Count equals 3 (AC-118 clause 4): NO. Change: count marked lines under (a) and fail if the count is not 3. Needs negative tests for a marker without URL, with another version, in a doc file, without an AC ID, and a wrong count.
(c) `schema_registry.py` lines 33 and 34 without the marker: G1 FAILS. I checked it on a copy of the tree in `/tmp` (the repo was not changed): `libs/ucp_core/schema_registry.py:33: the `ucp.dev` alias `latest` is not pinned` and line 34 (`draft`). Reason that the lines exist: `FORBIDDEN` (line 32) is the refusal list of AC-87 and TC-MV6. It is used with `startswith` at line 82 (an `$id` in a contract file) and line 102 (`validator()` refuses a schema URL). The code needs these exact strings. History: added in commit `106f10a` (S1). G1 flags a `ucp.dev` alias outside `tests/` (`g1.py` lines 111 to 114). I will not build the string in parts to hide it, because that is a hack of G1. So the marker stays for now, and T-108 as written makes G1 fail on these 2 lines. A decision is needed: a separate approved marker (for example `g1-allow-refusal-list`, only in `libs/ucp_core/schema_registry.py`, only for `latest` and `draft`), or a move of the list to a data file that G1 does not scan. This is a decision for Mark McCalla (spec 15.9 row 4). A reason comment will go in `schema_registry.py` on branch `s5-s6`.
Feasibility: yes, about 20 lines in `g1.py`, 3 small edits in source comments and 5 negative tests. A variant without a marker in code: a `[ucp_reference_only]` table in `pins/PINS.toml` (version `2026-08-25`, file list).

### M-01 impact
- The M-01 procedure (not in this repository) has no text about Jaeger or Compose. No change.
- `tools/m01_ready.sh`: the loopback check (DM-26) did not list the Jaeger ports. Commit `c494f1e` adds 16686, 16685 and 4318. I did not run the script again after this edit (UNVERIFIED); the shell syntax check passed. M-01 itself is not done (needs Mark).
- Tracing does not change the M-01 payment steps. `run_local.sh` turns on OTLP only when Jaeger answers (`UCP_TRACING=0` turns it off).

## 5. Where the AC list differs from the work
- AC-66 and AC-72 trace parts have no test. They need one more test each (webhook spans). Not done in this run.
- The local evidence README (not in this repository) is older than this report. This report replaces its "Results per AC" table.

## 6. AC-115: two loops of 20 runs (commit `c494f1e`)

Command for each run: `uv run --no-sync pytest -q tests/s3/e2e` (44 tests, the scripted flow with the Google Pay stub, headless Chrome, loopback). The run includes the log-order check (discovery, create, update, complete in this order, `completed` and an order ID). No rerun. No timeout was raised. Script: `ac115-final/run_loops.sh`.

### Loop 1: 20 of 20 runs with exit 0

| Run | Start (GMT) | Exit | Result | pytest s | Wall s | `uptime -s` |
|---|---|---|---|---|---|---|
| 1 | 16:12:57 | 0 | 44 passed | 74.36 | 77 | 10:38:34 |
| 2 | 16:14:14 | 0 | 44 passed | 74.03 | 76 | 10:38:35 |
| 3 | 16:15:30 | 0 | 44 passed | 71.85 | 74 | 10:38:34 |
| 4 | 16:16:44 | 0 | 44 passed | 73.54 | 76 | 10:38:34 |
| 5 | 16:18:00 | 0 | 44 passed | 72.33 | 75 | 10:38:34 |
| 6 | 16:19:15 | 0 | 44 passed | 71.83 | 74 | 10:38:34 |
| 7 | 16:20:29 | 0 | 44 passed | 71.21 | 74 | 10:38:34 |
| 8 | 16:21:43 | 0 | 44 passed | 71.74 | 73 | 10:38:34 |
| 9 | 16:22:56 | 0 | 44 passed | 72.27 | 75 | 10:38:35 |
| 10 | 16:24:11 | 0 | 44 passed | 138.32 | 141 | 10:38:35 |
| 11 | 16:26:32 | 0 | 44 passed | 87.34 | 1135 | 10:56:00 |
| 12 | 16:45:27 | 0 | 44 passed | 76.21 | 78 | 10:56:00 |
| 13 | 16:46:45 | 0 | 44 passed | 74.24 | 78 | 10:56:00 |
| 14 | 16:48:03 | 0 | 44 passed | 70.99 | 73 | 10:56:00 |
| 15 | 16:49:16 | 0 | 44 passed | 72.05 | 75 | 10:56:00 |
| 16 | 16:50:31 | 0 | 44 passed | 72.57 | 75 | 10:56:00 |
| 17 | 16:51:46 | 0 | 44 passed | 71.96 | 74 | 10:56:00 |
| 18 | 16:53:00 | 0 | 44 passed | 72.57 | 75 | 10:56:00 |
| 19 | 16:54:15 | 0 | 44 passed | 73.36 | 76 | 10:56:00 |
| 20 | 16:55:31 | 0 | 44 passed | 74.07 | 76 | 10:56:00 |

### Loop 2: 20 of 20 runs with exit 0

| Run | Start (GMT) | Exit | Result | pytest s | Wall s | `uptime -s` |
|---|---|---|---|---|---|---|
| 1 | 16:56:47 | 0 | 44 passed | 119.98 | 490 | 11:02:08 |
| 2 | 17:04:57 | 0 | 44 passed | 71.13 | 74 | 11:02:08 |
| 3 | 17:06:11 | 0 | 44 passed | 75.89 | 78 | 11:02:08 |
| 4 | 17:07:29 | 0 | 44 passed | 74.63 | 77 | 11:02:08 |
| 5 | 17:08:46 | 0 | 44 passed | 74.25 | 77 | 11:02:08 |
| 6 | 17:10:03 | 0 | 44 passed | 75.66 | 78 | 11:02:08 |
| 7 | 17:11:21 | 0 | 44 passed | 74.59 | 77 | 11:02:08 |
| 8 | 17:12:38 | 0 | 44 passed | 72.79 | 75 | 11:02:08 |
| 9 | 17:13:53 | 0 | 44 passed | 74.20 | 77 | 11:02:08 |
| 10 | 17:15:10 | 0 | 44 passed | 72.26 | 74 | 11:02:08 |
| 11 | 17:16:24 | 0 | 44 passed | 71.58 | 74 | 11:02:08 |
| 12 | 17:17:38 | 0 | 44 passed | 71.22 | 73 | 11:02:08 |
| 13 | 17:18:51 | 0 | 44 passed | 70.72 | 73 | 11:02:08 |
| 14 | 17:20:04 | 0 | 44 passed | 70.77 | 73 | 11:02:08 |
| 15 | 17:21:17 | 0 | 44 passed | 70.84 | 73 | 11:02:08 |
| 16 | 17:22:30 | 0 | 44 passed | 70.63 | 73 | 11:02:08 |
| 17 | 17:23:43 | 0 | 44 passed | 70.77 | 73 | 11:02:08 |
| 18 | 17:24:56 | 0 | 44 passed | 71.20 | 73 | 11:02:08 |
| 19 | 17:26:09 | 0 | 44 passed | 70.86 | 73 | 11:02:08 |
| 20 | 17:27:22 | 0 | 44 passed | 69.77 | 72 | 11:02:08 |

Verdict: PASS. 40 of 40 runs exit 0 in two consecutive loops of 20 of 20.

Pause evidence (the box is a virtual machine that the platform pauses and forks; I did not restart it):
- `dmesg`: "random: crng reseeded due to virtual machine fork" at 19476, 20049, 20883 and 21704 seconds after boot.
- `uptime -s` moved from 10:38:34 to 10:56:00 (during loop 1) and to 11:02:08 (during loop 2). `/proc/uptime` was 20898 s at 16:44.
- Loop 1 run 10: pytest 138 s (the normal run is about 72 s). Loop 1 run 11: wall 1135 s for pytest 87 s. Loop 2 run 1: wall 490 s for pytest 120 s. All 3 runs passed. The earlier loops at `38d5db8` (2026-10-25, 18 of 20 and 19 of 20, FAIL) had the same pattern of slow runs. The cause of those failures is UNVERIFIED. The 3 slow runs here passed, so the pauses did not cause a failure in this run.
- A reader who requires a run with no pause should count the 37 other runs: all passed.

## 7. Spec rules and standards

- UCP 2026-04-08 at `9c9d6fc`, read from https://ucp.dev/2026-04-08/specification/ pages named in each ADR. UCP 2026-08-25 is used only for the AC-44 and AC-45 rules (no response to Complete, no new Complete). This use is PROPOSED, not approved: spec v1.1.7 section 15.9 rows 3 and 4 are open (see section 4, "The marker `g1-allow-unpinned`"). It carries `g1-allow-unpinned` on 4 lines with the August URL (and 2 alias lines).
- Google Pay handler 2026-01-23: https://pay.google.com/gp/p/ucp/2026-01-23/ and `card_payment_instrument.json`.
- OpenTelemetry: section 4. Jaeger: section 4.
- No spec rule blocked work in this run.

## 8. UNVERIFIED items and blockers

UNVERIFIED:
1. The 2026-08-25 retry rule (AC-44) and the AC-45 rule. The pinned 2026-04-08 files have no such rule and no conflicting rule (checked). Approval is PROPOSED: spec 15.9 row 3. DM-02 covers the retry. It does not name the AC-45 rule. The marker has no rule in the spec (row 4).
2. The error screen for a Complete with no answer (reuses `error.network`). UX-U-20 and UX-U-21 (no UCP marker for a stored response).
3. The OTel instrumentation pages are `latest`, not 0.66b1.
4. The Jaeger loopback check ran in an isolated network namespace. The host instance (pid 289102, another agent) shows only 127.0.0.1 listeners.
5. Copy proposals: `replay.gpay.button`, `replay.gpay.result`, the `order.id` explanation, "Google Pay returned this code:", the "Problem:" label.
6. AC-102 banner source (handler spec section 5.2) and any behaviour with a real `TEST` token (needs M-01).
7. The audit field "escalation" format is a design choice (`input-agent-control.md` section 7).
8. AC-39 in the browser (only view and client tests). AC-66 and AC-72 webhook trace parts (no test).
9. `tools/m01_ready.sh` after the Jaeger port edit (syntax check only).
10. The cause of the 2026-10-25 AC-115 failures (pause suspected). No evidence found. UNVERIFIED.

Blockers (need Mark):
- M-01 (a browser and a Google Account): not done. Gate M1 shows NOT RUN.
- M-02 and M-03 records: not done. AC-33 stays PARTIAL because of M-03.
- The layout started by `tools/run_local.sh` and Jaeger (pid 289102, gpg-agent 287110) of another agent are left running. I did not stop the other agent's processes.

Notes:
- The system said the user's computer was offline during this run. My browsing and downloads (docs, Jaeger archive, OTel pages) ran from the box network, not from the user's computer.
- No push failed. No force-push. No pull request. No token was printed. All services bind to 127.0.0.1.
- S5 and S6 are not started.
