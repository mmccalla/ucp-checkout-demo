# SQLite calls reachable from the event loop (audit)

Date: 28 Oct 2026, Europe/London (GMT). Code: branch `s5-s6` at a195981 (the fix `asyncio.to_thread` is in). Method: `rg` for `sqlite3`, `store.`, `aiosqlite`, `.execute(`, `.commit()` in `business/src/business_app`, `platform/backend/src`, `libs`, `psp-mock/src`; then a read of each caller. SQLite 3.53.1 on the box, WAL mode (set by the vendored sample, `db.py` lines 81-98).

## Rule used for the risk

The deadlock of G8 needs two things at the same time:
1. A sync SQLite call that waits for the **write** lock, on the event loop.
2. Another request that holds the write lock across an `await` (the vendored sample session after a flush and before the commit).

A **read** does not wait for the write lock in WAL mode. A scratch test on the box (sqlite 3.53.1, writer holds `BEGIN IMMEDIATE`): `SELECT` and `CREATE TABLE IF NOT EXISTS` on an existing table returned at once (0.0 s). `INSERT OR IGNORE` and `CREATE TABLE IF NOT EXISTS` on a new table waited the whole timeout (0.2 s) and failed with `database is locked`.

## Business: callers on the event loop

| # | file:line | Call | Read or write | Sync or thread | Risk (write lock held while the loop is blocked?) |
|---|---|---|---|---|---|
| 1 | `business/src/business_app/gate.py:136` | `store.has_key` (`store.py:94`: connect, `SELECT 1 FROM idempotency_records`) | read | sync, on the loop (in `Gate.__call__`) | LOW. A read does not wait for the writer in WAL. It blocks the loop only if SQLite is busy for a read (WAL recovery, a checkpoint at close). Then the wait is up to 1 s (`store.py:58`, `timeout=1.0`). The error is caught (`return False`): the result is a wrong "no replay". It never holds a write lock. |
| 2 | `gate.py:365` (inside `_check`, called at `gate.py:119`) | `store.available` (`store.py:79`: `SELECT 1 ... LIMIT 1`) | read | sync, on the loop | LOW. Same as 1. On a busy error the result is a wrong HTTP 503 `store_unavailable` for a POST or PUT. |
| 3 | `gate.py:391` (in `_order_access`, called from `_check` at `gate.py:355`) | `store.order_owner` (`store.py:138`: `CREATE TABLE IF NOT EXISTS ucp_demo_order_owner`, then `SELECT`) | read, but see the note | sync, on the loop (Get Order only) | LOW to MEDIUM. On an existing table the `CREATE ... IF NOT EXISTS` is a read (scratch test). **The first call on a new database creates the table: a write on the loop**, and it can wait for the write lock (once only). `set_order_owner` makes the table in the first Complete, so in the normal flow the table exists before the first Get Order. Not proven for a Get Order before any Complete. |
| 4 | `gate.py:392` | `store.order_exists` (`store.py:150`: `SELECT 1 FROM orders`) | read | sync, on the loop | LOW. Same as 1. The error is caught (`return False`). |
| 5 | `gate.py:256` | `store.order_owner` | read (table exists after the first Complete) | **`asyncio.to_thread`** (fixed in a195981 and in the hotfix on main) | NONE for the loop. |
| 6 | `gate.py:259-264` | `store.set_order_owner` (`store.py:125`: `INSERT OR IGNORE`, commit) | **write** | **`asyncio.to_thread`** (fixed) | NONE for the loop. This was the fault. The call waits in a thread now, and the other request can commit. |

## Business: other callers

| # | file:line | Call | Read or write | Sync or thread | Risk |
|---|---|---|---|---|---|
| 7 | `main.py:188` (`readyz`) | `store.available` | read | `def` route: FastAPI runs it in the thread pool | NONE for the loop. |
| 8 | `main.py:101` and `store.py:52` | `store.prepare`, `purge_old_keys` (`DELETE`, commit) | **write** | sync, at start-up, before the loop serves requests | NONE. No other request exists. |
| 9 | `store.py:109` `checkout_count` | `SELECT COUNT(*)` | read | no caller in `business/src` or `libs` (`rg`). Used only by tests, if at all | NONE now. If a route calls it later, use a thread. |
| 10 | `order_events.py:166-173` (`simulate_fulfilment`) | The vendored `CheckoutService` with `async with ps() as p, ts() as t` | read and **write** (`ship_order`, `deliver_order`; commits at `checkout_service.py:1270` and `:1303`) | async (SQLAlchemy `aiosqlite`): does not block the loop | The **holder side** of the lock. It holds the write lock between a flush and a commit, across `await`. Runs inside the request through `cfg.after_complete` (`gate.py:267`), only if the simulation is on. |
| 11 | `business/src/ucp_sample_server/db.py`, `services/checkout_service.py` (commits at lines 495, 1233, 1270, 1303, 1395; `db.commit_with_idempotency` at `db.py:~608`) | SQLAlchemy async sessions on the transactions DB | read and **write** | async (`aiosqlite` thread): does not block the loop | The **holder side**. The G8 probe found one session with `dirty=1` and an open transaction at the time of the error. UNVERIFIED: which statement left it open. The vendored code is not changed here (ADR 0007, T-103). |
| 12 | `events.py`, `order_events.py` `_append` | Append to JSONL files | not SQLite | sync file write on the loop | Not a lock risk. A short blocking write. Out of scope. |

## Platform

| # | file:line | Call | Read or write | Sync or thread | Risk |
|---|---|---|---|---|---|
| 13 | `platform/backend/src/platform_app/webhooks.py:94-98` (`_seen`) | `INSERT OR IGNORE INTO seen`, commit (`timeout=1.0`) | **write** | called from `Receiver.receive`, which `main.py:643-644` runs with `run_in_threadpool` | NONE for the loop. |
| 14 | `platform_app/audit.py:167` (`write`; `_connect` at `:72` makes the table at `:76`) | `INSERT INTO audit` (`timeout` 5 s default) | **write** | called at `main.py:612` inside `_pay_now`; the route runs it with `run_in_threadpool` (`main.py:510`) | NONE for the loop. A thread lock (`_lock`) serialises the writers. |
| 15 | `audit.py:175` `read_all`, `:182` `purge` | `SELECT`, `DELETE` | read, write | no caller in `platform/backend/src` (`rg`); tests and tools only | NONE now. |

## Mock PSP and libs

`psp-mock/src` and `libs` have no SQLite call (`rg`). `libs/ucp_core` has none.

## Result

- After the fix, no **write** to SQLite runs on the event loop in `business_app` or `platform_app`. The write at `gate.py:259` was the only one.
- Four **read** calls still run sync on the Business loop (#1, #2, #3, #4). In WAL mode they do not wait for a writer. Risk is low. The one open case is #3: the first `order_owner` call on a database without the table is a write.
- Recommended (PROPOSED, not done): move #1 to #4 into `asyncio.to_thread` too, or create the table `ucp_demo_order_owner` in `store.prepare`. The hotfix on main does not do this (the order of the project owner: ONE commit with only the fix).
- The holder side (#10, #11) is in the vendored sample. It is not changed.

## UNVERIFIED

- Which vendored statement leaves a session with an open write transaction (#11).
- The case of a Get Order before any Complete (#3).
- That a read in WAL never gets `SQLITE_BUSY` on this box under load. I did not see one in about 40 G8 runs (local run records (not in this repository)), but I did not test for it.
