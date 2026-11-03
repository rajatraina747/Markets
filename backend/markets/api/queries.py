"""queries.py — read-side shaping for the API (pure SQL + small math)."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .. import db
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


# ------------------------------------------------------------------ P4

def ownership(conn, cid) -> dict:
    spl = splits(conn, cid)
    holders: dict[str, dict] = {}
    for r in conn.execute("SELECT * FROM holders_13dg WHERE company_id=? ORDER BY filed", (cid,)):
        key = _holder_key(r["filer_name"])
        h = holders.setdefault(key, {"name": r["filer_name"], "filings": []})
        h["name"] = r["filer_name"]
        f = split_factor(spl, r["event_date"] or r["filed"])
        h["filings"].append({"filed": r["filed"], "form": r["form"], "event_date": r["event_date"],
                             "shares": r["shares"], "shares_adj": r["shares"] * f if r["shares"] is not None else None,
                             "percent": r["percent"], "accession": r["accession"]})
    for h in holders.values():
        last = h["filings"][-1]
        h.update(latest_percent=last["percent"], latest_shares_adj=last["shares_adj"], latest_filed=last["filed"],
                 is_13d=any("13D" in (f["form"] or "") for f in h["filings"]))
    si = []
    for r in conn.execute("SELECT * FROM short_interest WHERE company_id=? ORDER BY settle_date", (cid,)):
        f = split_factor(spl, r["settle_date"])
        si.append({"date": r["settle_date"], "shares_short": (r["shares_short"] or 0) * f,
                   "avg_daily_vol": (r["avg_daily_vol"] or 0) * f, "days_to_cover": r["days_to_cover"]})
    sh = _latest(conn, cid, "shares_outstanding")
    shares_out = sh["value"] * split_factor(spl, sh["filed"] or sh["period_end"]) if sh else None
    psc = [dict(r) for r in conn.execute("SELECT name, kind, natures, notified, ceased FROM ch_psc WHERE company_id=? "
                                         "ORDER BY ceased IS NOT NULL, notified DESC", (cid,))]
    return {"holders": sorted(holders.values(), key=lambda h: h["latest_filed"], reverse=True),
            "short_interest": si, "shares_outstanding": shares_out, "psc": psc}


def _holder_key(name: str | None) -> str:
    import re as _re
    n = (name or "?").lower()
    n = _re.sub(r"[^a-z ]", " ", n)
    n = _re.sub(r"\b(inc|the|group|corp|corporation|llc|ltd|co|r)\b", " ", n)
    return " ".join(n.split())[:40]


def news(conn, cid, q: dict) -> dict:
    where, args = ["company_id=?"], [cid]
    if q.get("q"):
        where.append("title LIKE ?")
        args.append(f"%{q['q']}%")
    if q.get("source"):
        where.append("source=?")
        args.append(q["source"])
    w = " AND ".join(where)
    rows = [dict(r) for r in conn.execute(
        f"SELECT url, published, source, title, feed FROM news WHERE {w} ORDER BY published DESC LIMIT ?",
        args + [min(int(q.get("limit", 300)), 2000)])]
    per_day = [dict(r) for r in conn.execute(
        f"SELECT substr(published,1,10) AS day, COUNT(*) AS n FROM news WHERE {w} AND published IS NOT NULL "
        f"GROUP BY 1 ORDER BY 1", args)]
    sources = [dict(r) for r in conn.execute(
        "SELECT source, COUNT(*) AS n FROM news WHERE company_id=? GROUP BY 1 ORDER BY 2 DESC LIMIT 25", (cid,))]
    total = conn.execute("SELECT COUNT(*) FROM news WHERE company_id=?", (cid,)).fetchone()[0]
    span = conn.execute("SELECT MIN(published), MAX(published) FROM news WHERE company_id=?", (cid,)).fetchone()
    return {"rows": rows, "per_day": per_day, "sources": sources, "total": total,
            "first": span[0], "last": span[1]}


ECD_LABELS = {
    "PeoTotalCompAmt": "CEO total comp (summary table)",
    "PeoActuallyPaidCompAmt": "CEO compensation actually paid",
    "NonPeoNeoAvgTotalCompAmt": "Other NEOs avg total comp",
    "NonPeoNeoAvgCompActuallyPaidAmt": "Other NEOs avg comp actually paid",
    "TotalShareholderRtnAmt": "TSR (value of $100)",
    "PeerGroupTotalShareholderRtnAmt": "Peer TSR (value of $100)",
    "CoSelectedMeasureAmt": "Company-selected measure",
}


def exec_comp(conn, cid) -> dict:
    rows = conn.execute("SELECT fy, concept, value, accession FROM exec_comp WHERE company_id=? ORDER BY fy",
                        (cid,)).fetchall()
    years = sorted({r["fy"] for r in rows}, reverse=True)
    table: dict[str, dict] = {}
    for r in rows:
        table.setdefault(r["concept"], {})[str(r["fy"])] = r["value"]
    lines = [{"concept": c, "label": ECD_LABELS.get(c, c), "values": table[c]}
             for c in ECD_LABELS if c in table] + \
            [{"concept": c, "label": c, "values": v} for c, v in table.items() if c not in ECD_LABELS]
    ni = {str(r["fy"]): r["value"] for r in conn.execute(
        "SELECT fy, value FROM statement_lines WHERE company_id=? AND line='net_income' AND period_type='annual'", (cid,))}
    return {"years": years, "lines": lines, "net_income": ni}


def tenk_list(conn, cid) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT f.accession, f.form, f.filed, f.report_date, "
        "EXISTS(SELECT 1 FROM filing_text t WHERE t.company_id=f.company_id AND t.accession=f.accession) AS has_text "
        "FROM filings f WHERE f.company_id=? AND f.form IN ('10-K','10-KT') ORDER BY f.filed DESC", (cid,))]


_SECTION_CACHE: dict[tuple, dict] = {}


def _sections(conn, cid, acc: str) -> dict[str, str]:
    from ..normalize import sections
    key = (cid, acc)
    if key not in _SECTION_CACHE:
        r = conn.execute("SELECT body FROM filing_text WHERE company_id=? AND accession=? ORDER BY length(body) DESC "
                         "LIMIT 1", (cid, acc)).fetchone()
        _SECTION_CACHE[key] = sections.split_items(r["body"]) if r else {}
        if len(_SECTION_CACHE) > 40:
            _SECTION_CACHE.pop(next(iter(_SECTION_CACHE)))
    return _SECTION_CACHE[key]


def tenk_diff(conn, cid, a: str, b: str, item: str) -> dict:
    from ..normalize import sections
    sa, sb = _sections(conn, cid, a), _sections(conn, cid, b)
    item = item.upper()
    out = {"item": item, "label": sections.ITEMS.get(item), "a": a, "b": b,
           "items_a": {k: len(v) for k, v in sa.items()}, "items_b": {k: len(v) for k, v in sb.items()},
           "item_labels": sections.ITEMS}
    if item not in sa or item not in sb:
        out["error"] = f"Item {item} not found in {'both filings' if item not in sa and item not in sb else 'one filing'}"
        return out
    out.update(sections.diff(sa[item], sb[item]))
    return out


# ------------------------------------------------------------------ P4.5 / P5

def proxy_comp(conn, cid) -> dict:
    sct = [dict(r) for r in conn.execute("SELECT * FROM proxy_comp WHERE company_id=? ORDER BY fy DESC, total DESC", (cid,))]
    dirs = [dict(r) for r in conn.execute("SELECT * FROM director_comp WHERE company_id=? ORDER BY proxy_year DESC, total DESC",
                                          (cid,))]
    return {"sct": sct, "directors": dirs}


def institutions(conn, cid) -> dict:
    """13F view. Only quarters where most managers have filed (data sets trail by up to a year
    for late filers, so older quarters are sparse) count as complete."""
    per = [dict(r) for r in conn.execute(
        "SELECT period, COUNT(*) AS managers, SUM(shares) AS shares, SUM(value) AS value FROM inst_holdings "
        "WHERE company_id=? AND put_call='' GROUP BY period ORDER BY period", (cid,))]
    if not per:
        return {"quarters": [], "top": [], "movers": [], "options": [], "shares_outstanding": None}
    peak = max(p["managers"] for p in per)
    quarters = [p for p in per if p["managers"] >= peak * 0.6]
    spl = splits(conn, cid)
    sh = _latest(conn, cid, "shares_outstanding")
    shares_out = sh["value"] * split_factor(spl, sh["filed"] or sh["period_end"]) if sh else None
    for q in quarters:
        q["pct_of_shares"] = q["shares"] / shares_out if shares_out else None
    if not quarters:
        return {"quarters": [], "top": [], "movers": [], "options": [], "shares_outstanding": shares_out}
    last = quarters[-1]["period"]
    prev = quarters[-2]["period"] if len(quarters) > 1 else None

    def book(period):
        return {r["manager_cik"]: dict(r) for r in conn.execute(
            "SELECT manager, manager_cik, shares, value FROM inst_holdings WHERE company_id=? AND period=? AND put_call=''",
            (cid, period))}
    cur, old = book(last), (book(prev) if prev else {})
    top = sorted(cur.values(), key=lambda r: -r["shares"])[:40]
    for r in top:
        o = old.get(r["manager_cik"])
        r["change"] = r["shares"] - o["shares"] if o else None
        r["pct_of_shares"] = r["shares"] / shares_out if shares_out else None
    movers = []
    for k in set(cur) | set(old):
        c, o = cur.get(k), old.get(k)
        delta = (c["shares"] if c else 0) - (o["shares"] if o else 0)
        movers.append({"manager": (c or o)["manager"], "delta": delta, "now": c["shares"] if c else 0,
                       "status": "new" if not o else "exited" if not c else "changed"})
    movers.sort(key=lambda m: -abs(m["delta"]))
    options = [dict(r) for r in conn.execute(
        "SELECT period, put_call, COUNT(*) AS managers, SUM(shares) AS shares, SUM(value) AS value FROM inst_holdings "
        "WHERE company_id=? AND put_call!='' GROUP BY period, put_call ORDER BY period", (cid,))
        if r["period"] in {q["period"] for q in quarters}]
    return {"quarters": quarters, "last": last, "prev": prev, "top": top, "movers": movers[:30],
            "options": options, "shares_outstanding": shares_out}


def macro_series(conn, keys: list[str] | None = None, since: str = "1990-01-01") -> dict:
    from ..sources.macro import SERIES
    out = {}
    for key, (_prov, _sid, label, unit, group) in SERIES.items():
        if keys and key not in keys:
            continue
        pts = [[r[0], r[1]] for r in conn.execute("SELECT date, value FROM macro WHERE series=? AND date>=? ORDER BY date",
                                                  (key, since))]
        if pts:
            out[key] = {"label": label, "unit": unit, "group": group, "points": pts}
    return out


def watchlist(conn) -> list[dict]:
    """One summary row per tracked company (watchlist, screener, compare picker)."""
    out = []
    for c in conn.execute("SELECT id, ticker FROM companies ORDER BY ticker").fetchall():
        try:
            ov = overview(conn, c["id"])
        except Exception:  # half-built company — skip rather than break the list
            continue
        closes = [r[0] for r in conn.execute(
            "SELECT close FROM (SELECT date, close FROM prices_daily WHERE company_id=? ORDER BY date DESC LIMIT 120) "
            "ORDER BY date", (c["id"],))]
        out.append({
            "ticker": c["ticker"], "name": ov["company"]["name"], "sic_desc": ov["company"]["sic_desc"],
            "exchange": ov["company"]["exchange"], "price": ov["price"], "change": ov["change"],
            "partial": bool(ov["quote"] and ov["quote"].get("partial")),
            "market_cap": ov["market_cap"], "enterprise_value": ov["enterprise_value"],
            "returns": ov["returns"], "valuation": ov["valuation"], "margins": ov["margins"],
            "ttm": ov["ttm"], "balance": ov["balance"], "high_52w": ov["high_52w"], "low_52w": ov["low_52w"],
            "spark": closes, "archived_filings": ov["counts"]["filings_archived"], "filings": ov["counts"]["filings"],
            "revenue_growth": _yoy(conn, c["id"], "revenue"),
        })
    return out


def _yoy(conn, cid, line):
    """TTM vs prior-TTM growth from quarterly lines."""
    rows = [r[0] for r in conn.execute("SELECT value FROM statement_lines WHERE company_id=? AND line=? AND "
                                       "period_type='quarterly' ORDER BY period_end DESC LIMIT 8", (cid, line))]
    if len(rows) < 8 or not sum(rows[4:]):
        return None
    return sum(rows[:4]) / sum(rows[4:]) - 1


def compare_prices(conn, tickers: list[str], since: str) -> dict:
    """Closes rebased to 100 at the first common date on/after `since`."""
    series = {}
    for t in tickers:
        cid = db.company_id(conn, t)
        if cid is None:
            continue
        series[t.upper()] = [(r[0], r[1]) for r in conn.execute(
            "SELECT date, adj_close FROM prices_daily WHERE company_id=? AND date>=? AND adj_close IS NOT NULL "
            "ORDER BY date", (cid, since))]
    if not series:
        return {"series": {}}
    start = max(pts[0][0] for pts in series.values() if pts)
    out = {}
    for t, pts in series.items():
        pts = [p for p in pts if p[0] >= start]
        if pts:
            b = pts[0][1]
            out[t] = [[d, round(v / b * 100, 3)] for d, v in pts]
    return {"start": start, "series": out}
