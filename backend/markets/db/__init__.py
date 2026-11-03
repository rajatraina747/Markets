"""db — connection helpers for the derived store (markets.db).

markets.db is disposable: on a schema version mismatch it is recreated, and
`markets rebuild` repopulates it from the raw archive with zero network.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .. import config

SCHEMA_VERSION = 2
SCHEMA_SQL = Path(__file__).with_name("schema.sql")


def connect(path: Path | None = None, readonly: bool = False) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_schema(path: Path | None = None) -> sqlite3.Connection:
    """Open the DB, recreating it if the schema version is stale."""
    path = Path(path or config.DB_PATH)
    if path.exists():
        conn = connect(path)
        if conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
            return conn
        conn.close()
        for suffix in ("", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
    conn = connect(path)
    conn.executescript(SCHEMA_SQL.read_text())
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()
    return conn


def company_id(conn: sqlite3.Connection, ticker: str) -> int | None:
    row = conn.execute("SELECT id FROM companies WHERE ticker=?", (ticker.upper(),)).fetchone()
    return row["id"] if row else None
