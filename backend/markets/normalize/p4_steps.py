"""P4 build steps: 13D/G holders, short interest, exec comp (ecd XBRL), news."""
from __future__ import annotations

import re
import sys
from collections import Counter

from .. import archive
from ..sources import macro, news, ownership_13dg, proxy, sec_13f, short_interest
from .build import _wipe


def build_ownership(conn, cid, reg, base) -> int:
    _wipe(conn, cid, "holders_13dg")
    n = bad = 0
    forms = sorted(ownership_13dg.FORMS)
    for f in conn.execute(
            f"SELECT accession, form, filed, raw_path FROM filings WHERE company_id=? AND raw_path IS NOT NULL "
            f"AND form IN ({','.join('?' * len(forms))}) ORDER BY filed", (cid, *forms)).fetchall():
        p = ownership_13dg.parse(archive.read_raw(base / f["raw_path"]))
        persons = [x for x in p["persons"] if x["shares"] is not None or x["percent"] is not None]
        if not persons:
            bad += 1
            persons = [{"name": p["filer"], "shares": None, "percent": None, "event_date": None}]
        # Joint filings (affiliates, trusts) list several reporting persons for one stake:
        # collapse to the filer, keeping the largest reported position.
        best = max(persons, key=lambda x: (x["shares"] or 0, x["percent"] or 0))
        name = (p["filer"] if len(persons) > 1 and p["filer"] else best["name"] or p["filer"] or "?").strip()
        conn.execute("INSERT INTO holders_13dg VALUES (?,?,?,?,?,?,?,?,?)",
                     (cid, f["accession"], f["form"], f["filed"], name, p["filer_cik"],
                      best["shares"], max((x["percent"] or 0) for x in persons) or best["percent"],
                      best["event_date"]))
        n += 1
    if bad:
        print(f"  ownership: {bad} filings without a parseable cover page (stored filer only)", file=sys.stderr)
    return n


def build_short_interest(conn, cid, reg, base) -> int:
    _wipe(conn, cid, "short_interest")
    snap = archive.latest_snapshot(base, short_interest.SOURCE, "consolidated.json")
    if not snap:
        return 0
    rows = short_interest.parse(archive.read_raw(snap))
    conn.executemany("INSERT OR REPLACE INTO short_interest VALUES (?,?,?,?,?)",
                     [(cid, r["settle_date"], r["shares_short"], r["avg_daily_vol"], r["days_to_cover"]) for r in rows])
    return len(rows)


def build_exec_comp(conn, cid, reg, base) -> int:
    """Pay-versus-performance (Item 402(v)) facts, tagged in the ecd taxonomy since 2022 proxies."""
    _wipe(conn, cid, "exec_comp")
    rows = conn.execute(
        "SELECT concept, value, period_end, filed, accession FROM facts WHERE company_id=? AND taxonomy='ecd' "
        "ORDER BY filed", (cid,)).fetchall()
    latest = {}
    for r in rows:  # later filings restate earlier years — keep the latest-filed per (fy, concept)
        latest[(int(r["period_end"][:4]), r["concept"])] = r
    conn.executemany("INSERT OR REPLACE INTO exec_comp VALUES (?,?,?,?,?,?)",
                     [(cid, fy, c, "", r["value"], r["accession"]) for (fy, c), r in latest.items()])
    return len(latest)


def build_news(conn, cid, reg, base) -> int:
    _wipe(conn, cid, "news")
    items = news.load_all(base)
    conn.executemany("INSERT OR REPLACE INTO news VALUES (?,?,?,?,?,?,?)",
                     [(cid, i["url"], i["published"], i["source"], i["title"], i["tone"], i["feed"]) for i in items])
    return len(items)


# ------------------------------------------------------------------ P4.5 / P5

_CUSIP_RX = re.compile(rb"CUSIP[^0-9A-Z]{0,80}?([0-9]{3}[0-9A-Z]{5}[0-9])(?![0-9A-Z])", re.I | re.S)


def detect_cusip(conn, cid, base) -> str | None:
    """Most common 9-char CUSIP across the company's 13D/G cover pages."""
    votes: Counter = Counter()
    forms = sorted(ownership_13dg.FORMS)
    for f in conn.execute(f"SELECT raw_path FROM filings WHERE company_id=? AND raw_path IS NOT NULL AND form IN "
                          f"({','.join('?' * len(forms))}) ORDER BY filed DESC LIMIT 40", (cid, *forms)):
        raw = archive.read_raw(base / f["raw_path"])
        for m in _CUSIP_RX.finditer(raw[:400_000]):
            votes[m.group(1).decode().upper()] += 1
    return votes.most_common(1)[0][0] if votes else None


def build_proxy(conn, cid, reg, base) -> int:
    _wipe(conn, cid, "proxy_comp", "director_comp")
    n = 0
    rows = conn.execute("SELECT accession, filed, report_date, raw_path FROM filings WHERE company_id=? AND "
                        "raw_path IS NOT NULL AND form IN ('DEF 14A','DEFM14A') ORDER BY filed", (cid,)).fetchall()
    for f in rows:  # oldest first → later proxies overwrite restated years
        p = proxy.parse(archive.read_raw(base / f["raw_path"]))
        for r in p["sct"]:
            conn.execute("INSERT OR REPLACE INTO proxy_comp VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (cid, r["fy"], r["name"], r.get("position"), r.get("salary"), r.get("bonus"), r.get("stock"),
                          r.get("option"), r.get("non_equity"), r.get("pension"), r.get("other"), r.get("total"),
                          f["accession"]))
            n += 1
        if p["directors"]:
            fy = max((r["fy"] for r in p["sct"]), default=int(f["filed"][:4]) - 1)
            for r in p["directors"]:
                conn.execute("INSERT OR REPLACE INTO director_comp VALUES (?,?,?,?,?,?,?,?,?)",
                             (cid, fy, r["name"], r.get("fees"), r.get("stock"), r.get("option"), r.get("other"),
                              r.get("total"), f["accession"]))
                n += 1
    return n


def _extract_cached(z, cusip: str) -> list[dict]:
    """sec_13f.extract with a derived on-disk cache (data/cache/13f) — 13F zips never change."""
    import gzip
    import json as _json
    from .. import config
    cache = config.DATA_DIR / "cache" / "13f" / f"{z.stem}_{cusip}.json.gz"
    if cache.exists() and cache.stat().st_mtime >= z.stat().st_mtime:
        return _json.loads(gzip.decompress(cache.read_bytes()))
    rows = sec_13f.extract(z, {cusip})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(gzip.compress(_json.dumps(rows).encode()))
    return rows


def build_13f(conn, cid, reg, base) -> int:
    _wipe(conn, cid, "inst_holdings")
    cusip = detect_cusip(conn, cid, base)
    conn.execute("UPDATE companies SET cusip=? WHERE id=?", (cusip, cid))
    if not cusip:
        return 0
    # (manager_cik, period) → latest-filed accession; within it, identical rows are de-duplicated
    picked: dict[tuple, dict] = {}
    for z in sorted(sec_13f.zip_dir().glob("*.zip")) if sec_13f.zip_dir().is_dir() else []:
        by_acc: dict[str, list[dict]] = {}
        for r in _extract_cached(z, cusip):
            by_acc.setdefault(r["accession"], []).append(r)
        for acc, rs in by_acc.items():
            r0 = rs[0]
            key = (r0["manager_cik"], r0["period"])
            if key in picked and (picked[key]["filed"] or "") >= (r0["filed"] or ""):
                continue
            uniq = {(x["shares"], x["value"], x["put_call"], x["discretion"]): x for x in rs}.values()
            agg: dict[str, dict] = {}
            for x in uniq:
                a = agg.setdefault(x["put_call"] or "", {"shares": 0.0, "value": 0.0})
                a["shares"] += x["shares"]
                a["value"] += x["value"]
            picked[key] = {"manager": r0["manager"], "filed": r0["filed"], "accession": acc, "agg": agg}
    n = 0
    for (mcik, period), p in picked.items():
        for pc, a in p["agg"].items():
            conn.execute("INSERT INTO inst_holdings VALUES (?,?,?,?,?,?,?,?,?)",
                         (cid, period, p["manager"], mcik, a["shares"], a["value"], pc, p["filed"], p["accession"]))
            n += 1
    return n


def build_macro(conn, cid, reg, base) -> int:
    """Cross-company: rebuilt with every company (cheap) so the table is never stale."""
    conn.execute("DELETE FROM macro")
    n = 0
    for key, pts in macro.load_all().items():
        conn.executemany("INSERT OR REPLACE INTO macro VALUES (?,?,?)", [(key, d, v) for d, v in pts])
        n += len(pts)
    return n


def build_uk(conn, cid, reg, base) -> int:
    """Companies House → filings index, officers (people/roles), persons with significant control."""
    from datetime import date
    from ..sources import companies_house as ch
    if reg.get("cik") or not reg.get("ch_number"):
        return 0
    data = ch.load(base)
    _wipe(conn, cid, "ch_psc", "filings", "roles")
    n = 0
    for f in ch.parse_filings(data.get("filing_history") or {}, reg["ch_number"]):
        conn.execute("INSERT OR REPLACE INTO filings (company_id, accession, form, filed, report_date, primary_desc, "
                     "items, primary_doc) VALUES (?,?,?,?,?,?,?,?)",
                     (cid, f["accession"], f["form"], f["filed"], f["report_date"], f["description"], f["category"],
                      f["url"]))
        n += 1
    today = date.today().isoformat()
    for o in ch.parse_officers(data.get("officers") or {}):
        r = conn.execute("SELECT id FROM people WHERE cik IS NULL AND name=?", (o["name"],)).fetchone()
        pid = r[0] if r else conn.execute("INSERT INTO people (name) VALUES (?)", (o["name"],)).lastrowid
        role = (o["role"] or "").replace("-", " ")
        conn.execute("INSERT OR REPLACE INTO roles VALUES (?,?,?,?,?,?,?,?,?)",
                     (cid, pid, int("director" in role), int("secretary" in role or "officer" in role), 0, 0,
                      (role.title() + (f" · {o['occupation']}" if o["occupation"] else "")),
                      o["appointed"] or today, o["resigned"] or today))
        n += 1
    for p in ch.parse_psc(data.get("psc") or {}):
        conn.execute("INSERT INTO ch_psc VALUES (?,?,?,?,?,?)",
                     (cid, p["name"], p["kind"], p["natures"], p["notified"], p["ceased"]))
        n += 1
    return n


# ------------------------------------------------------------------ breadth / segments / earnings

def build_segments(conn, cid, reg, base) -> int:
    from ..sources import edgar_filings as ef, xbrl_instance as xi
    from . import segments as seg
    _wipe(conn, cid, "segment_lines")
    facts = []
    for f in conn.execute("SELECT accession, filed, raw_path FROM filings WHERE company_id=? AND form IN "
                          "('10-K','10-Q','10-K/A','10-Q/A','10-KT') AND filed >= '2009-06-01' ORDER BY filed",
                          (cid,)).fetchall():
        inst = base / "raw" / xi.rel_path(f["accession"])
        if f["raw_path"]:
            got = xi.from_submission(archive.read_raw(base / f["raw_path"]))
        elif inst.exists():
            got = xi.parse(archive.read_raw(inst).decode("utf-8", "replace"))
        else:
            continue
        for g in got:
            g.update(filed=f["filed"], accession=f["accession"])
        facts += got
    fye = conn.execute("SELECT fiscal_year_end FROM companies WHERE id=?", (cid,)).fetchone()[0]
    rows = seg.compute(facts, fye)
    cols = ["metric", "axis", "member", "label", "period_type", "period_start", "period_end", "fy", "fp", "value",
            "filed", "accession", "derived", "is_subtotal"]
    conn.executemany(f"INSERT OR REPLACE INTO segment_lines (company_id,{','.join(cols)}) VALUES "
                     f"(?,{','.join('?' * len(cols))})", [[cid] + [r[c] for c in cols] for r in rows])
    return len(rows)


def build_earnings(conn, cid, reg, base) -> int:
    from ..normalize import text as tx
    from ..sources import edgar_filings as ef, prices as px
    from . import earnings as er
    _wipe(conn, cid, "earnings")
    filings = [dict(r) for r in conn.execute(
        "SELECT accession, filed, accepted, raw_path FROM filings WHERE company_id=? AND form IN ('8-K','8-K/A') "
        "AND items LIKE '%2.02%'", (cid,))]
    if not filings:
        return 0
    bars = [dict(r) for r in conn.execute("SELECT date, open, close, volume FROM prices_daily WHERE company_id=? "
                                          "ORDER BY date", (cid,))]
    quarters: dict[str, dict] = {}
    for r in conn.execute("SELECT line, period_end, value FROM statement_lines WHERE company_id=? AND "
                          "period_type='quarterly'", (cid,)):
        quarters.setdefault(r["period_end"], {})[r["line"]] = r["value"]
    spy = [dict(r) for r in conn.execute("SELECT date, close FROM benchmark_prices WHERE symbol='SPY' ORDER BY date")]
    texts = {}
    for f in filings:
        if not f["raw_path"]:
            continue
        docs = ef.split_documents(archive.read_raw(base / f["raw_path"]))
        ex = next((d for d in docs if d["doc_type"].upper().startswith("EX-99") and d["kind"] in ("html", "text")), None)
        if ex:
            texts[f["accession"]] = tx.plain_text(ex["body"], ex["kind"], 400_000)
    fye = conn.execute("SELECT fiscal_year_end FROM companies WHERE id=?", (cid,)).fetchone()[0]
    rows = er.compute(filings, bars, quarters, spy, texts, fye)
    cols = ["accession", "filed", "accepted_et", "timing", "kind", "period_end", "fy", "fp", "base_date", "base_close",
            "react_date", "gap", "day", "d5", "d20", "excess_day", "excess_d5", "vol_ratio", "metrics", "guidance"]
    conn.executemany(f"INSERT OR REPLACE INTO earnings (company_id,{','.join(cols)}) VALUES (?,{','.join('?' * len(cols))})",
                     [[cid] + [r[c] for c in cols] for r in rows])
    return len(rows)


def build_summary(conn, cid, reg, base) -> int:
    """Precompute the watchlist/screener row (500 live overviews per request would be slow)."""
    import json as _json
    from .. import registry
    from ..api import queries
    row = queries.summary_row(conn, cid)
    if row is None:
        return 0
    conn.execute("INSERT OR REPLACE INTO company_summary VALUES (?,?,?,?,?,?)",
                 (cid, reg["ticker"], registry.tier(reg), reg.get("sector"), row.get("sic"), _json.dumps(row)))
    return 1


def build_benchmarks(conn, cid, reg, base) -> int:
    from ..sources import prices as px
    conn.execute("DELETE FROM benchmark_prices")
    n = 0
    for sym, bars in px.load_benchmarks().items():
        conn.executemany("INSERT OR REPLACE INTO benchmark_prices VALUES (?,?,?,?)",
                         [(sym, b["date"], b["close"], b["adj_close"]) for b in bars])
        n += len(bars)
    return n
