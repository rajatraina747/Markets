"""journal.py — USER-AUTHORED notes and paper trades (data/journal.db).

Unlike markets.db this is NOT rebuildable: it is the one file to back up.
Writes are small and synchronous; every change is also appended to
journal.log.jsonl so nothing typed is ever lost to a bad edit.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, title TEXT, body TEXT NOT NULL DEFAULT '',
  tags TEXT, pinned INTEGER DEFAULT 0, created TEXT NOT NULL, updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('long','short')),
  qty REAL NOT NULL CHECK (qty > 0), entry_date TEXT NOT NULL, entry_price REAL NOT NULL CHECK (entry_price > 0),
  stop REAL, target REAL, thesis TEXT,
  exit_date TEXT, exit_price REAL, exit_reason TEXT,
  created TEXT NOT NULL, updated TEXT NOT NULL
);
"""
NOTE_FIELDS = ("title", "body", "tags", "pinned")
TRADE_FIELDS = ("side", "qty", "entry_date", "entry_price", "stop", "target", "thesis",
                "exit_date", "exit_price", "exit_reason")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    """Commit on success, roll back on error, ALWAYS close (sqlite3's own `with` doesn't close)."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.JOURNAL_DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def _log(action: str, kind: str, payload: dict) -> None:
    with open(config.DATA_DIR / "journal.log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": _now(), "action": action, "kind": kind, **payload}) + "\n")


class Invalid(ValueError):
    pass


def _clean_trade(d: dict, partial: bool = False) -> dict:
    out = {k: d[k] for k in TRADE_FIELDS if k in d}
    for k in ("qty", "entry_price", "stop", "target", "exit_price"):
        if k in out and out[k] not in (None, ""):
            try:
                out[k] = float(out[k])
            except (TypeError, ValueError):
                raise Invalid(f"{k} must be a number")
        elif k in out:
            out[k] = None
    if not partial:
        for k in ("side", "qty", "entry_date", "entry_price"):
            if out.get(k) in (None, ""):
                raise Invalid(f"{k} is required")
    if "side" in out and out["side"] not in ("long", "short"):
        raise Invalid("side must be long or short")
    if bool(out.get("exit_price")) != bool(out.get("exit_date")) and ("exit_price" in out or "exit_date" in out):
        raise Invalid("close a trade with both exit_date and exit_price")
    return out


def list_notes(ticker: str) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM notes WHERE ticker=? ORDER BY pinned DESC, updated DESC",
                                           (ticker.upper(),))]


def save_note(ticker: str, d: dict, note_id: int | None = None) -> dict:
    fields = {k: d[k] for k in NOTE_FIELDS if k in d}
    if note_id is None and not (fields.get("body") or fields.get("title")):
        raise Invalid("empty note")
    now = _now()
    with connect() as c:
        if note_id is None:
            cur = c.execute("INSERT INTO notes (ticker, title, body, tags, pinned, created, updated) VALUES (?,?,?,?,?,?,?)",
                            (ticker.upper(), fields.get("title"), fields.get("body") or "", fields.get("tags"),
                             int(bool(fields.get("pinned"))), now, now))
            note_id = cur.lastrowid
        else:
            if fields:
                c.execute(f"UPDATE notes SET {', '.join(f'{k}=?' for k in fields)}, updated=? WHERE id=? AND ticker=?",
                          [*fields.values(), now, note_id, ticker.upper()])
        row = dict(c.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone())
    _log("save", "note", row)
    return row


def delete(kind: str, ticker: str, item_id: int) -> None:
    table = {"note": "notes", "trade": "trades"}[kind]
    with connect() as c:
        row = c.execute(f"SELECT * FROM {table} WHERE id=? AND ticker=?", (item_id, ticker.upper())).fetchone()
        if row:
            _log("delete", kind, dict(row))
            c.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))


def list_trades(ticker: str) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM trades WHERE ticker=? ORDER BY entry_date DESC, id DESC",
                                           (ticker.upper(),))]


def save_trade(ticker: str, d: dict, trade_id: int | None = None) -> dict:
    fields = _clean_trade(d, partial=trade_id is not None)
    now = _now()
    with connect() as c:
        if trade_id is None:
            cols = list(fields)
            cur = c.execute(f"INSERT INTO trades (ticker, {', '.join(cols)}, created, updated) "
                            f"VALUES (?, {', '.join('?' * len(cols))}, ?, ?)", [ticker.upper(), *fields.values(), now, now])
            trade_id = cur.lastrowid
        elif fields:
            c.execute(f"UPDATE trades SET {', '.join(f'{k}=?' for k in fields)}, updated=? WHERE id=? AND ticker=?",
                      [*fields.values(), now, trade_id, ticker.upper()])
        row = dict(c.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone())
    _log("save", "trade", row)
    return row


def trade_pnl(t: dict, mark: float | None) -> dict:
    """P&L for one trade: realized if closed, else marked to `mark` (latest close)."""
    px = t["exit_price"] if t.get("exit_price") else mark
    if px is None:
        return {"mark": None, "pnl": None, "pnl_pct": None, "open": not t.get("exit_price")}
    sign = 1 if t["side"] == "long" else -1
    pnl = sign * (px - t["entry_price"]) * t["qty"]
    r_mult = None
    if t.get("stop"):
        risk = abs(t["entry_price"] - t["stop"]) * t["qty"]
        r_mult = pnl / risk if risk else None
    return {"mark": px, "pnl": pnl, "pnl_pct": sign * (px / t["entry_price"] - 1), "r": r_mult,
            "open": not t.get("exit_price")}
