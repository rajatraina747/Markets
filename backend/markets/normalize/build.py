"""build.py — raw archive → markets.db, per company, zero network.

Each step deletes the company's rows in its tables and re-inserts them inside
one transaction, so a rebuild is idempotent and a crash leaves the old data.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import archive, config, db
from ..sources import edgar_filings, edgar_submissions, edgar_xbrl, prices

STEPS: list[tuple[str, callable]] = []


def step(name):
    def deco(fn):
        STEPS.append((name, fn))
        return fn
    return deco


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _wipe(conn: sqlite3.Connection, cid: int, *tables: str) -> None:
    for t in tables:
        conn.execute(f"DELETE FROM {t} WHERE company_id=?", (cid,))


def upsert_company(conn: sqlite3.Connection, reg: dict, base: Path) -> int:
    main, _ = edgar_submissions.load_latest(base, reg["cik"])
    prof = edgar_submissions.parse_profile(main)
    prof.update(ticker=reg["ticker"], exchange=reg.get("exchange"), updated_at=_now())
    cols = list(prof)
    conn.execute(
        f"INSERT INTO companies ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
        f"ON CONFLICT(ticker) DO UPDATE SET {','.join(f'{c}=excluded.{c}' for c in cols)}",
        [prof[c] for c in cols])
    return db.company_id(conn, reg["ticker"])


@step("filings")
def build_filings(conn, cid, reg, base) -> int:
    main, pages = edgar_submissions.load_latest(base, reg["cik"])
    rows = edgar_submissions.parse_filings(main, pages)
    _wipe(conn, cid, "filings")
    for f in rows:
        p = edgar_filings.local_path(base, f["accession"], f["filed"])
        f["raw_path"] = str(p.relative_to(base)) if p.exists() else None
        f["company_id"] = cid
        f["doc_count"] = None
    cols = ["company_id", "accession", "form", "filed", "accepted", "report_date", "act",
            "file_number", "items", "size", "is_xbrl", "is_inline_xbrl", "primary_doc",
            "primary_desc", "raw_path", "doc_count"]
    conn.executemany(f"INSERT INTO filings ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                     [[f[c] for c in cols] for f in rows])
    return len(rows)


@step("documents")
def build_documents(conn, cid, reg, base) -> int:
    _wipe(conn, cid, "filing_documents")
    n = 0
    for r in conn.execute("SELECT accession, raw_path FROM filings WHERE company_id=? "
                          "AND raw_path IS NOT NULL", (cid,)).fetchall():
        docs = edgar_filings.split_documents(archive.read_raw(base / r["raw_path"]), with_body=False)
        conn.executemany(
            "INSERT OR REPLACE INTO filing_documents VALUES (?,?,?,?,?,?,?,?)",
            [(cid, r["accession"], d["seq"], d["doc_type"], d["filename"], d["description"],
              d["kind"], d["bytes"]) for d in docs])
        conn.execute("UPDATE filings SET doc_count=? WHERE company_id=? AND accession=?",
                     (len(docs), cid, r["accession"]))
        n += len(docs)
    return n


@step("facts")
def build_facts(conn, cid, reg, base) -> int:
    payload = edgar_xbrl.load_latest(base, reg["cik"])
    _wipe(conn, cid, "facts", "concepts")
    if payload is None:
        return 0
    facts, concepts = edgar_xbrl.parse(payload)
    conn.executemany("INSERT OR REPLACE INTO concepts VALUES (?,?,?,?,?)",
                     [(cid, c["taxonomy"], c["concept"], c["label"], c["description"])
                      for c in concepts])
    cols = ["taxonomy", "concept", "unit", "value", "period_start", "period_end", "fy", "fp",
            "form", "filed", "accession", "frame"]
    conn.executemany(f"INSERT INTO facts (company_id,{','.join(cols)}) "
                     f"VALUES (?,{','.join('?' * len(cols))})",
                     [[cid] + [f[c] for c in cols] for f in facts])
    return len(facts)


@step("prices")
def build_prices(conn, cid, reg, base) -> int:
    snap = archive.latest_snapshot(base, prices.SOURCE_Y, "chart_1d.json")
    _wipe(conn, cid, "prices_daily", "corporate_actions", "quote_meta")
    if snap is None:
        return 0
    p = prices.parse_yahoo(archive.read_raw(snap))
    conn.executemany("INSERT OR REPLACE INTO prices_daily VALUES (?,?,?,?,?,?,?,?,?)",
                     [(cid, b["date"], b["open"], b["high"], b["low"], b["close"],
                       b["adj_close"], b["volume"], "yahoo") for b in p["bars"]])
    conn.executemany("INSERT OR REPLACE INTO corporate_actions VALUES (?,?,?,?,?,?,?)",
                     [(cid, s["date"], "split", s["ratio"], s["numerator"], s["denominator"], None)
                      for s in p["splits"]] +
                     [(cid, d["date"], "dividend", None, None, None, d["amount"])
                      for d in p["dividends"]])
    m = p["meta"]
    # chartPreviousClose refers to the bar before period1 (i.e. 2010) — use the bars.
    bars = p["bars"]
    m["prev_close"] = bars[-2]["close"] if len(bars) >= 2 else None
    if m["as_of"] and m["as_of"][:10] > bars[-1]["date"]:
        m["prev_close"] = bars[-1]["close"]
    conn.execute("INSERT INTO quote_meta VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (cid, m["as_of"], m["price"], m["prev_close"], m["day_high"], m["day_low"],
                  m["volume"], m["high_52w"], m["low_52w"], m["currency"], m["exchange"],
                  m["long_name"]))
    return len(p["bars"])


def register_step(name: str, fn) -> None:
    """Later phases plug extra steps in (statements, insiders, events, fts...)."""
    STEPS.append((name, fn))


def rebuild(reg: dict, only: set[str] | None = None, conn: sqlite3.Connection | None = None) -> dict:
    from . import extra_steps  # noqa: F401 — registers P2+ steps
    conn = conn or db.ensure_schema()
    base = config.company_dir(reg["ticker"])
    out = {}
    with conn:
        cid = upsert_company(conn, reg, base)
    for name, fn in STEPS:
        if only and name not in only:
            continue
        t0 = time.monotonic()
        with conn:
            rows = fn(conn, cid, reg, base)
            secs = time.monotonic() - t0
            conn.execute("INSERT INTO build_log VALUES (?,?,?,?,?)", (cid, name, rows, secs, _now()))
        out[name] = rows
        print(f"  {name:<12} {rows:>9,} rows  {secs:6.1f}s", file=sys.stderr)
    return out
