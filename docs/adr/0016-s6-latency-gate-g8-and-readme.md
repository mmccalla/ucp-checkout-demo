# ADR 0016: G8 latency gate, readiness check and README

- Status: PROPOSED for S6. S6 entry needs "S5 exit true" (04-build-plan.md), and G5 does not pass yet. This work covers only the parts that do not need M-01.
- Date: 2026-10-28.
- Owner: Mark McCalla.

## Context

AC-117: gate G8 sends 100 calls for each operation. Create p95 must be 4 s or less, Update p95 5 s or less, Complete p95 10 s or less, with an error rate of 0 % in the same run. AC-58: all services report readiness within 120 s. DM-25: the p95 values are the only CI limit. The p50 values are targets only.

Source of the limits: https://developers.google.com/merchant/ucp/guides/overview/native-checkout, section "Service level objectives" (table: Create p50 1 s and p95 4 s, Update p50 1 s and p95 5 s, Complete p50 6 s and p95 10 s; availability 95 %). The page has no UCP version in its URL. I read it on 28 Oct 2026. UNVERIFIED: that the page is the same at the pinned date.

## Decision

1. `tools/latency/run_g8.sh` exports HEAD with `git archive` into a temporary folder. It refuses to run on a dirty tree. The demo in the working tree is not used and is not changed.
2. The script starts a second layout (`tools/run_local.sh start`) in `unshare --map-root-user --net` with only the loopback interface. The fixed ports (8443, 9443, 8101, 8201, 8301, 2019) are free there. All services still bind to 127.0.0.1 (DM-26).
3. `UCP_TRACING=0` for the run. Traces are not part of the limits.
4. `tools/latency/g8_driver.py ready` polls `/readyz` of the Platform, the Business and the mock PSP, and the two TLS endpoints, from the start of `run_local.sh`. It writes `readiness.log`. It fails above 120 s (AC-58).
5. `tools/latency/g8_driver.py run` sends 100 times Create, Update (to `ready_for_complete`) and Complete, one flow after the other, through `platform_app.main.client()`. This is the signed client of the demo. The time of a call includes the signing and the response checks of the client (design choice: the Platform sees the same time).
6. A call is an error if the HTTP status is not 2xx, if there is a transport error, or if the checkout `status` is not the expected one (`incomplete`, `ready_for_complete`, `completed`). If Create or Update fails, the next calls of that flow count as errors.
7. The percentile is the nearest rank (`tools/latency/g8_stats.py`). The verdict has unit tests (`tests/s6/unit`).
8. `tools/gates/g8.py` is the gate. G8 joins the slice list `S6` in `tools/gates/gates.toml`. G5 is not in the list (ADR 0015).
9. `tools/get_caddy.sh` downloads the pinned Caddy (`pins/PINS.toml` `[caddy]`) and checks its sha512, so a new person can start the demo. UNVERIFIED: the download URL pattern on the Caddy release page is not in the pins. The sha512 check makes a wrong file fail.

## Consequences

- The measured values are for a mock PSP on loopback. They show that the Business and the Platform do not add a delay. They do not show real PSP or network time.
- The G8 run adds about 10 s to the gates.
- The README walk-through of 15 minutes by a new person is not yet done by a person. The records are local run records (not in this repository).

## Fault found by G8 (fixed in this commit)

The first G8 runs failed in 17 of 18 runs with 2 to 4 errors per operation (HTTP 502 on `POST /checkout-sessions` through Caddy; local run records (not in this repository)).

- First idea: Caddy reused an idle upstream connection after the 5 s keep-alive of uvicorn. I tried `transport http { keepalive 3s }` in `deploy/tls/Caddyfile`. The 502 stayed (10 of 10 runs failed, local run records (not in this repository)). The idea is REFUTED. The change is not in the commit.
- Real cause (evidence: local run records (not in this repository), a scratch probe with a 10 s busy timeout): `Gate._after_complete` (`business/src/business_app/gate.py`) called the sync functions `store.order_owner` and `store.set_order_owner` on the event loop, after the Complete response. The next Create of the client held the write lock of the shared sample session. It could not finish while the loop waited, so the wait lasted until the busy timeout (1 s). Then `sqlite3.OperationalError: database is locked` ended the request, uvicorn closed the connection, and Caddy sent 502 for the next request on that connection. The probe found one SQLAlchemy session with an uncommitted change at the time of the error.
- Fix: both store calls run with `asyncio.to_thread`. Test: `tests/s6/unit/test_after_complete_loop.py` (fails on the old code, passes on the new code). After the fix: 10 of 10 G8 runs PASS with 0 errors (local run records (not in this repository)), and no `database is locked` in the logs.
- Impact: the same code is on `main`. The demo can show this fault if a client sends a request right after Complete. The running demo is not changed. The fix reaches `main` only with the merge of `s5-s6` (needs the decision of Mark, M-01 first).
- UNVERIFIED: that no other sync SQLite write is on the event loop (other store calls are reads; the database is in WAL mode, so reads do not wait).

## Open items

- A person must read and follow the README within 15 minutes (the build plan S6 test "timed README walk-through"). UNVERIFIED.
- M-01 for the release commit. This needs Mark.
- The S6 exit needs G5 to pass (open items in ADR 0015).

## Exception to the entry rule of S7 (the project owner, 28 Oct 2026)

- The rule: S7 needs "S6 exit true" (`04-build-plan.md`, section S7, row "Entry"). The S6 exit is "G1 to G8 PASS" and an M-01 record for the release commit.
- State on 28 Oct 2026: gates G1 to G4 and G6 to G8 pass on `d3f5864`. G5 passes with 6 approved failures and 7 approved skips (ADR 0015). S6 is blocked only by two items: M-01 (needs Mark McCalla) and the human README walk-through of 15 minutes (not done). The S6 exit is NOT true.
- Ruling: the project owner permits the start of the S7 v1 part on the branch `s7`, from `d3f5864` (the head of `s5-s6`). The v1 part is catalog search and lookup only (DM-11, AC-12, the catalog part of AC-08). The AI agent, MCP and cloud host phases are not in this ruling.
- Limits of the exception:
  - `main` does not change. The M-01 path does not change. The running demo stays as it is.
  - The branch `s7` is not merged into `main` and has no pull request.
  - Each commit passes the gates before a normal push of `s7`.
  - The exception does not close S6, and it does not close S7. S7 closes only when S6 exit is true and all gates pass.
- Rule from the same ruling: when a ruling is open on an item, that item is not pushed.
- Status of this ADR: the S6 part stays PROPOSED. This exception is ACCEPTED (the project owner). I did not see a separate record from Mark McCalla.
