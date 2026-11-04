"""S6 (G8): `Gate._after_complete` must not block the event loop on a SQLite write wait.

Fault found by G8: the sync `set_order_owner` waited for the write lock on the event loop.
The next request of the client held that lock in the shared session, and it could not
finish while the loop was blocked. The result was a wait up to the busy timeout, an
exception after the response, a closed connection and HTTP 502 at the proxy.
"""

from __future__ import annotations

import asyncio
import pathlib
import sqlite3
import threading
import time
from typing import Any

from business_app import gate as gate_mod
from business_app import store

AGENT = 'profile="https://localhost:8443/.well-known/ucp"'


def _db(tmp_path: pathlib.Path) -> str:
    path = str(tmp_path / "t.db")
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()
    return path


def _gate(db: str) -> gate_mod.Gate:
    cfg: Any = gate_mod.GateConfig(
        resolver=None,  # type: ignore[arg-type]
        transactions_db=db,
        verify=None,
        require_signatures=False,
        mode="ci",
    )
    return gate_mod.Gate(None, cfg)  # type: ignore[arg-type]


def test_after_complete_does_not_block_the_loop(tmp_path: pathlib.Path) -> None:
    db = _db(tmp_path)
    holder = sqlite3.connect(db, isolation_level=None, check_same_thread=False)
    holder.execute("BEGIN IMMEDIATE")  # the write lock of another request

    def release() -> None:
        time.sleep(0.4)
        holder.execute("COMMIT")

    threading.Thread(target=release).start()
    ticks: list[float] = [time.monotonic()]

    async def ticker() -> None:
        for _ in range(8):
            await asyncio.sleep(0.05)
            ticks.append(time.monotonic())

    async def run() -> None:
        data = {"id": "chk1", "status": "completed", "order": {"id": "ord1"}}
        t = asyncio.create_task(ticker())
        await _gate(db)._after_complete(data, {"ucp-agent": AGENT}, False)
        await t

    asyncio.run(run())
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(gaps) < 0.25, f"the loop was blocked for {max(gaps):.2f} s"
    assert store.order_owner(db, "ord1") == "https://localhost:8443/.well-known/ucp"
