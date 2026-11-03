"""queries.py — read-side shaping for the API (pure SQL + small math)."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from ..normalize import statements as stm

FORM_GROUPS = {
    "annual": ("10-K", "10-K/A", "10-KT", "20-F", "ARS"),
    "quarterly": ("10-Q", "10-Q/A"),
    "current": ("8-K", "8-K/A", "6-K"),
    "insider": ("3", "4", "5", "3/A", "4/A", "5/A", "144"),
    "proxy": ("DEF 14A", "DEFA14A", "PRE 14A", "PX14A6G", "DEFM14A", "DFAN14A"),
    "ownership": ("SC 13G", "SC 13G/A", "SC 13D", "SC 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A",
                  "SCHEDULE 13D", "SCHEDULE 13D/A"),
    "registration": ("S-1", "S-1/A", "S-3", "S-3ASR", "S-4", "S-4/A", "S-8", "S-8 POS", "424B2",
                     "424B3", "424B4", "424B5", "FWP"),
}
PER_SHARE = {"eps_basic", "eps_diluted"}
SHARE_COUNT = {"shares_diluted", "shares_outstanding"}


def splits(conn, cid) -> list[tuple[str, float]]:
    return [(r["date"], r["numerator"] / r["denominator"]) for r in conn.execute(
        "SELECT date, numerator, denominator FROM corporate_actions WHERE company_id=? AND kind='split' "
        "ORDER BY date", (cid,))]


def split_factor(spl: list[tuple[str, float]], as_of: str | None) -> float:
    """Cumulative split ratio for splits after `as_of` (a value reported then needs ×factor shares)."""
    f = 1.0
    for d, r in spl:
        if as_of is None or d > as_of:
            f *= r
    return f


def _latest(conn, cid, line, ptype=None):
    sql = "SELECT * FROM statement_lines WHERE company_id=? AND line=?"
    args = [cid, line]
    if ptype:
        sql += " AND period_type=?"
        args.append(ptype)
    return conn.execute(sql + " ORDER BY period_end DESC LIMIT 1", args).fetchone()


def _ttm(conn, cid, line):
    rows = conn.execute("SELECT value, period_end FROM statement_lines WHERE company_id=? AND line=? "
                        "AND period_type='quarterly' ORDER BY period_end DESC LIMIT 4", (cid, line)).fetchall()
    if len(rows) < 4:
        return None, None
    return sum(r["value"] for r in rows), rows[0]["period_end"]


def _ret(closes: list[tuple[str, float]], days: int | None = None, since: str | None = None):
    if not closes:
        return None
    last_d, last = closes[-1]
    target = since or (date.fromisoformat(last_d) - timedelta(days=days)).isoformat()
    base = next((c for d, c in closes if d >= target), None)
    return (last / base - 1) if base else None


def overview(conn: sqlite3.Connection, cid: int) -> dict:
    co = dict(conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone())
    qm = conn.execute("SELECT * FROM quote_meta WHERE company_id=?", (cid,)).fetchone()
    closes = [(r[0], r[1]) for r in conn.execute(
        "SELECT date, close FROM prices_daily WHERE company_id=? ORDER BY date", (cid,))]
    price = (qm["price"] if qm and qm["price"] else closes[-1][1]) if closes else None
    prev = closes[-2][1] if len(closes) >= 2 else None
    if closes and qm and qm["as_of"] and qm["as_of"][:10] > closes[-1][0]:
        prev = closes[-1][1]
    spl = splits(conn, cid)
    sh = _latest(conn, cid, "shares_outstanding")
    shares = sh["value"] * split_factor(spl, sh["filed"] or sh["period_end"]) if sh else None
    mcap = price * shares if price and shares else None
    ttm = {k: _ttm(conn, cid, k)[0] for k in ("revenue", "gross_profit", "operating_income",
                                              "net_income", "free_cash_flow", "cfo", "capex", "rnd")}
    ttm_end = _ttm(conn, cid, "revenue")[1]
    bs = {k: (_latest(conn, cid, k)["value"] if _latest(conn, cid, k) else None)
          for k in ("cash", "short_term_investments", "debt_current", "long_term_debt", "equity",
                    "total_assets", "total_liabilities")}
    bs_row = _latest(conn, cid, "total_assets")
    debt = (bs["debt_current"] or 0) + (bs["long_term_debt"] or 0)
    cash = (bs["cash"] or 0) + (bs["short_term_investments"] or 0)

    def ratio(a, b):
        return a / b if a is not None and b else None

    year_closes = [c for d, c in closes if d >= (date.fromisoformat(closes[-1][0]) - timedelta(days=365)).isoformat()] if closes else []
    counts = {k: conn.execute(sql, (cid,)).fetchone()[0] for k, sql in {
        "filings": "SELECT COUNT(*) FROM filings WHERE company_id=?",
        "filings_archived": "SELECT COUNT(*) FROM filings WHERE company_id=? AND raw_path IS NOT NULL",
        "documents": "SELECT COUNT(*) FROM filing_documents WHERE company_id=?",
        "facts": "SELECT COUNT(*) FROM facts WHERE company_id=?",
        "insider_txns": "SELECT COUNT(*) FROM insider_txns WHERE company_id=?",
        "people": "SELECT COUNT(DISTINCT person_id) FROM roles WHERE company_id=?",
        "price_days": "SELECT COUNT(*) FROM prices_daily WHERE company_id=?",
        "events": "SELECT COUNT(*) FROM events WHERE company_id=?",
    }.items()}
    return {
        "company": co,
        "quote": dict(qm) if qm else None,
        "price": price, "prev_close": prev,
        "change": (price / prev - 1) if price and prev else None,
        "last_bar": closes[-1][0] if closes else None,
        "shares_outstanding": shares, "market_cap": mcap,
        "enterprise_value": mcap + debt - cash if mcap else None,
        "high_52w": max(year_closes) if year_closes else None,
        "low_52w": min(year_closes) if year_closes else None,
        "returns": {
            "1m": _ret(closes, 30), "3m": _ret(closes, 91), "1y": _ret(closes, 365),
            "3y": _ret(closes, 3 * 365), "5y": _ret(closes, 5 * 365),
            "ytd": _ret(closes, since=closes[-1][0][:4] + "-01-01") if closes else None,
            "since_ipo": (closes[-1][1] / closes[0][1] - 1) if closes else None,
        },
        "ttm": dict(ttm, period_end=ttm_end),
        "balance": dict(bs, total_debt=debt, total_cash=cash,
                        as_of=bs_row["period_end"] if bs_row else None),
        "valuation": {
            "pe": ratio(mcap, ttm["net_income"]) if (ttm["net_income"] or 0) > 0 else None,
            "ps": ratio(mcap, ttm["revenue"]),
            "pb": ratio(mcap, bs["equity"]),
            "p_fcf": ratio(mcap, ttm["free_cash_flow"]) if (ttm["free_cash_flow"] or 0) > 0 else None,
            "ev_sales": ratio(mcap + debt - cash, ttm["revenue"]) if mcap else None,
        },
        "margins": {
            "gross": ratio(ttm["gross_profit"], ttm["revenue"]),
            "operating": ratio(ttm["operating_income"], ttm["revenue"]),
            "net": ratio(ttm["net_income"], ttm["revenue"]),
            "fcf": ratio(ttm["free_cash_flow"], ttm["revenue"]),
            "rnd": ratio(ttm["rnd"], ttm["revenue"]),
        },
        "counts": counts,
        "recent_events": [dict(r) for r in conn.execute(
            "SELECT date, kind, title, detail, accession, importance FROM events WHERE company_id=? "
            "AND importance>=2 ORDER BY date DESC LIMIT 15", (cid,))],
    }


def statements_table(conn, cid, period: str) -> dict:
    ptype = "quarterly" if period == "quarterly" else "annual"
    ends = [r[0] for r in conn.execute(
        "SELECT DISTINCT period_end FROM statement_lines WHERE company_id=? AND period_type=? "
        "ORDER BY period_end DESC", (cid, ptype))]
    ends_set = set(ends)
    spl = splits(conn, cid)
    cells: dict[str, dict[str, dict]] = {}
    labels: dict[str, str] = {}
    for r in conn.execute("SELECT * FROM statement_lines WHERE company_id=? AND period_type IN (?, 'instant')",
                          (cid, ptype)):
        if r["period_end"] not in ends_set:
            continue
        v = r["value"]
        if r["line"] in PER_SHARE:
            v = v / split_factor(spl, r["filed"] or r["period_end"])
        elif r["line"] in SHARE_COUNT:
            v = v * split_factor(spl, r["filed"] or r["period_end"])
        cells.setdefault(r["line"], {})[r["period_end"]] = {
            "v": v, "concept": r["concept"], "derived": r["derived"], "acc": r["accession"],
            "fy": r["fy"], "fp": r["fp"]}
    periods = []
    for e in ends:
        meta = next((c[e] for c in cells.values() if e in c), {})
        periods.append({"end": e, "fy": meta.get("fy"), "fp": meta.get("fp")})
    lines = []
    for key in stm.ORDER:
        if key not in cells:
            continue
        st = stm.LINE_BY_KEY[key].statement if key in stm.LINE_BY_KEY else stm.DERIVED[key][0]
        unit = stm.LINE_BY_KEY[key].unit if key in stm.LINE_BY_KEY else "USD"
        lines.append({"key": key, "label": stm.LABELS[key], "statement": st, "unit": unit})
        labels[key] = stm.LABELS[key]
    return {"period": ptype, "periods": periods, "lines": lines, "cells": cells,
            "split_adjusted": bool(spl)}


def filings(conn, cid, q: dict) -> dict:
    where, args = ["company_id=?"], [cid]
    group = q.get("group")
    if group and group in FORM_GROUPS:
        forms = FORM_GROUPS[group]
        where.append(f"form IN ({','.join('?' * len(forms))})")
        args += forms
    elif group == "other":
        allf = [f for g in FORM_GROUPS.values() for f in g]
        where.append(f"form NOT IN ({','.join('?' * len(allf))})")
        args += allf
    if q.get("form"):
        where.append("form=?")
        args.append(q["form"])
    if q.get("year"):
        where.append("substr(filed,1,4)=?")
        args.append(q["year"])
    if q.get("q"):
        where.append("(primary_desc LIKE ? OR form LIKE ? OR items LIKE ? OR accession LIKE ?)")
        args += [f"%{q['q']}%"] * 4
    w = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM filings WHERE {w}", args).fetchone()[0]
    limit, offset = min(int(q.get("limit", 100)), 500), int(q.get("offset", 0))
    rows = [dict(r) for r in conn.execute(
        f"SELECT accession, form, filed, report_date, items, primary_doc, primary_desc, size, "
        f"raw_path IS NOT NULL AS archived, doc_count FROM filings WHERE {w} "
        f"ORDER BY filed DESC, accession DESC LIMIT ? OFFSET ?", args + [limit, offset])]
    groups = {}
    for g, forms in FORM_GROUPS.items():
        groups[g] = conn.execute(
            f"SELECT COUNT(*) FROM filings WHERE company_id=? AND form IN ({','.join('?' * len(forms))})",
            [cid, *forms]).fetchone()[0]
    groups["all"] = conn.execute("SELECT COUNT(*) FROM filings WHERE company_id=?", (cid,)).fetchone()[0]
    groups["other"] = groups["all"] - sum(v for k, v in groups.items() if k != "all")
    years = [r[0] for r in conn.execute("SELECT DISTINCT substr(filed,1,4) FROM filings WHERE company_id=? "
                                        "ORDER BY 1 DESC", (cid,))]
    return {"total": total, "rows": rows, "groups": groups, "years": years}


def _fts_query(s: str) -> str:
    s = s.strip()
    if any(op in s for op in ('"', " AND ", " OR ", " NOT ", "NEAR(", "*")):
        return s
    return " ".join('"' + w.replace('"', "") + '"' for w in s.split())


def search(conn, cid, q: dict) -> dict:
    term = (q.get("q") or "").strip()
    if not term:
        return {"q": term, "results": [], "total": 0}
    form = q.get("form")
    limit = min(int(q.get("limit", 50)), 200)
    sql = ("SELECT accession, seq, form, filed, doc_type, "
           "snippet(filing_text, 0, '\u0002', '\u0003', ' … ', 24) AS snip, bm25(filing_text) AS score "
           "FROM filing_text WHERE filing_text MATCH ? AND company_id=?")
    args = [_fts_query(term), cid]
    if form:
        sql += " AND form=?"
        args.append(form)
    order = " ORDER BY filed DESC" if q.get("sort") == "date" else " ORDER BY score"
    try:
        rows = [dict(r) for r in conn.execute(sql + order + " LIMIT ?", args + [limit])]
        total = conn.execute("SELECT COUNT(*) FROM filing_text WHERE filing_text MATCH ? AND company_id=?",
                             args[:2]).fetchone()[0]
        by_year = [dict(r) for r in conn.execute(
            "SELECT substr(filed,1,4) AS year, COUNT(*) AS n FROM filing_text WHERE filing_text MATCH ? "
            "AND company_id=? GROUP BY 1 ORDER BY 1", args[:2])]
    except sqlite3.OperationalError as e:
        return {"q": term, "results": [], "total": 0, "error": str(e)}
    return {"q": term, "results": rows, "total": total, "by_year": by_year}


def insiders(conn, cid) -> list[dict]:
    people = {}
    for r in conn.execute(
            "SELECT p.id, p.cik, p.name, r.title, r.is_director, r.is_officer, r.is_ten_pct, r.first_seen, "
            "r.last_seen FROM roles r JOIN people p ON p.id=r.person_id WHERE r.company_id=?", (cid,)):
        p = people.setdefault(r["id"], {"id": r["id"], "cik": r["cik"], "name": r["name"], "titles": [],
                                        "is_director": 0, "is_officer": 0, "is_ten_pct": 0,
                                        "first_seen": r["first_seen"], "last_seen": r["last_seen"]})
        if r["title"] and r["title"] not in p["titles"]:
            p["titles"].append(r["title"])
        for k in ("is_director", "is_officer", "is_ten_pct"):
            p[k] = max(p[k], r[k] or 0)
        p["first_seen"] = min(p["first_seen"], r["first_seen"])
        p["last_seen"] = max(p["last_seen"], r["last_seen"])
    spl = splits(conn, cid)
    year_ago = (date.today() - timedelta(days=365)).isoformat()
    for r in conn.execute(
            "SELECT person_id, code, txn_date, shares, price, shares_after FROM insider_txns WHERE company_id=? "
            "AND table_kind='nonDerivative' ORDER BY txn_date", (cid,)):
        p = people.get(r["person_id"])
        if not p:
            continue
        f = split_factor(spl, r["txn_date"])
        p.setdefault("txns", 0)
        p["txns"] += 1
        if r["shares_after"] is not None:
            p["last_holding"] = r["shares_after"] * f
            p["last_holding_date"] = r["txn_date"]
        if r["code"] in ("P", "S") and r["shares"]:
            sign = 1 if r["code"] == "P" else -1
            usd = sign * r["shares"] * (r["price"] or 0)
            p["net_open_market_usd"] = p.get("net_open_market_usd", 0) + usd
            if (r["txn_date"] or "") >= year_ago:
                p["net_open_market_usd_1y"] = p.get("net_open_market_usd_1y", 0) + usd
    return sorted(people.values(), key=lambda p: p["last_seen"] or "", reverse=True)


def insider_txns(conn, cid, q: dict) -> list[dict]:
    where, args = ["t.company_id=?"], [cid]
    if q.get("person"):
        where.append("t.person_id=?")
        args.append(int(q["person"]))
    if q.get("codes"):
        codes = q["codes"].split(",")
        where.append(f"t.code IN ({','.join('?' * len(codes))})")
        args += codes
    spl = splits(conn, cid)
    out = []
    for r in conn.execute(
            f"SELECT t.*, p.name FROM insider_txns t LEFT JOIN people p ON p.id=t.person_id "
            f"WHERE {' AND '.join(where)} ORDER BY t.txn_date DESC, t.accession DESC LIMIT ?",
            args + [min(int(q.get("limit", 500)), 5000)]):
        d = dict(r)
        f = split_factor(spl, d["txn_date"])
        d["split_factor"] = f
        d["shares_adj"] = d["shares"] * f if d["shares"] is not None else None
        d["price_adj"] = d["price"] / f if d["price"] is not None else None
        d["shares_after_adj"] = d["shares_after"] * f if d["shares_after"] is not None else None
        out.append(d)
    return out
