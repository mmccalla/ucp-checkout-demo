"""SQLite store of the vendored sample (products, inventory, checkouts, idempotency records).

- The files are in `.run/business/<mode>/` (outside Git), or in BUSINESS_DATA_DIR.
- The sample script `import_csv.py` loads `business/data/demo/*.csv` on the first start.
- Idempotency records: the pinned REST binding says "store the result for at least 24 hours"
  (checkout-rest.md). T-31 sets 24 h minimum and 48 h maximum. Thus the start removes
  records that are older than 48 h.
"""

from __future__ import annotations

import datetime
import os
import pathlib
import sqlite3
import subprocess
import sys

from ucp_core.constants import ROOT

SAMPLE_DIR = ROOT / "business" / "src" / "ucp_sample_server"
DATA_DIR = ROOT / "business" / "data" / "demo"
RETENTION_H = 48


def data_dir(mode: str) -> pathlib.Path:
    d = pathlib.Path(os.environ.get("BUSINESS_DATA_DIR", str(ROOT / ".run" / "business" / mode)))
    d.mkdir(parents=True, exist_ok=True)
    return d


def paths(mode: str) -> tuple[str, str]:
    d = data_dir(mode)
    return str(d / "products.db"), str(d / "transactions.db")


def prepare(mode: str) -> tuple[str, str]:
    products, transactions = paths(mode)
    if not (os.path.exists(products) and os.path.exists(transactions)):
        subprocess.run(
            [
                sys.executable,
                "import_csv.py",
                f"--products_db_path={products}",
                f"--transactions_db_path={transactions}",
                f"--data_dir={DATA_DIR}",
            ],
            cwd=SAMPLE_DIR,
            check=True,
            capture_output=True,
        )
    purge_old_keys(transactions)
    return products, transactions


def _connect(transactions: str) -> sqlite3.Connection:
    # mode=rw: do not make a new empty file if the store is not there (AC-47).
    return sqlite3.connect(f"file:{transactions}?mode=rw", uri=True, timeout=1.0)


def purge_old_keys(transactions: str) -> int:
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=RETENTION_H)
    try:
        con = _connect(transactions)
    except sqlite3.Error:
        return 0
    try:
        cur = con.execute(
            "DELETE FROM idempotency_records WHERE created_at < ?", (cutoff.isoformat(),)
        )
        con.commit()
        return cur.rowcount
    except sqlite3.Error:
        return 0
    finally:
        con.close()


def available(transactions: str) -> bool:
    """Return True if the idempotency store answers a read (readiness and AC-47)."""
    try:
        con = _connect(transactions)
    except sqlite3.Error:
        return False
    try:
        con.execute("SELECT 1 FROM idempotency_records LIMIT 1").fetchall()
        return True
    except sqlite3.Error:
        return False
    finally:
        con.close()


def has_key(transactions: str, key: str) -> bool:
    """Return True if a record for this Idempotency-Key exists (the reply is a replay)."""
    try:
        con = _connect(transactions)
    except sqlite3.Error:
        return False
    try:
        row = con.execute("SELECT 1 FROM idempotency_records WHERE key = ?", (key,)).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        con.close()


def checkout_count(transactions: str) -> int:
    con = _connect(transactions)
    try:
        return int(con.execute("SELECT COUNT(*) FROM checkouts").fetchone()[0])
    finally:
        con.close()


# S4 (order.md "Get Order", Authorization): a platform with platform credentials can read only
# the orders it originated. The gate records the owner at Complete and checks it at Get Order.
_OWNER_SQL = (
    "CREATE TABLE IF NOT EXISTS ucp_demo_order_owner "
    "(order_id TEXT PRIMARY KEY, profile_url TEXT NOT NULL, checkout_id TEXT)"
)


def set_order_owner(transactions: str, order_id: str, profile_url: str, checkout_id: str) -> None:
    con = _connect(transactions)
    try:
        con.execute(_OWNER_SQL)
        con.execute(
            "INSERT OR IGNORE INTO ucp_demo_order_owner VALUES (?, ?, ?)",
            (order_id, profile_url, checkout_id),
        )
        con.commit()
    finally:
        con.close()


def order_owner(transactions: str, order_id: str) -> str | None:
    con = _connect(transactions)
    try:
        con.execute(_OWNER_SQL)
        row = con.execute(
            "SELECT profile_url FROM ucp_demo_order_owner WHERE order_id = ?", (order_id,)
        ).fetchone()
        return None if row is None else str(row[0])
    finally:
        con.close()


def order_exists(transactions: str, order_id: str) -> bool:
    con = _connect(transactions)
    try:
        return con.execute("SELECT 1 FROM orders WHERE id = ?", (order_id,)).fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        con.close()
