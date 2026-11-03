"""P2 build steps: statements, insiders (Forms 3/4/5), events timeline, full-text index.

Imported by build.rebuild(); each step registers itself in build.STEPS.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET

from .. import archive
from ..sources import edgar_filings, form4
from . import p4_steps, statements, text
from .build import _wipe, register_step

INSIDER_FORMS = {"3", "4", "5", "3/A", "4/A", "5/A"}

ITEMS_8K = {
    "1.01": "Material agreement", "1.02": "Agreement terminated", "1.03": "Bankruptcy",
    "1.05": "Cybersecurity incident",
    "2.01": "Acquisition/disposition", "2.02": "Results of operations", "2.03": "New debt obligation",
    "2.04": "Debt acceleration", "2.05": "Exit/restructuring costs", "2.06": "Impairment",
    "3.01": "Listing notice", "3.02": "Unregistered equity sale", "3.03": "Shareholder rights change",
    "4.01": "Auditor change", "4.02": "Non-reliance on financials",
    "5.01": "Change in control", "5.02": "Officer/director change", "5.03": "Charter/bylaws amended",
    "5.05": "Ethics code change", "5.07": "Shareholder vote results", "5.08": "Director nominations",
    "7.01": "Reg FD disclosure", "8.01": "Other events", "9.01": "Financial statements & exhibits",
}
HIGH_ITEMS = {"1.01", "1.03", "2.01", "2.02", "2.05", "2.06", "4.01", "4.02", "5.01", "5.02"}
PERIODIC = {"10-K": 3, "10-Q": 2, "10-K/A": 2, "10-Q/A": 1, "DEF 14A": 2, "S-1": 3, "S-3": 1,
            "S-3ASR": 1, "424B5": 1, "SC 13D": 2, "SC 13D/A": 1, "SC TO-T": 3}


def _company_fye(conn, cid) -> str | None:
    r = conn.execute("SELECT fiscal_year_end FROM companies WHERE id=?", (cid,)).fetchone()
    return r[0] if r else None


def build_statements(conn, cid, reg, base) -> int:
    _wipe(conn, cid, "statement_lines")
    facts = [dict(r) for r in conn.execute(
        "SELECT concept, unit, value, period_start, period_end, form, filed, accession "
        "FROM facts WHERE company_id=?", (cid,))]
    rows = statements.compute(facts, _company_fye(conn, cid))
    cols = ["statement", "line", "period_type", "period_start", "period_end", "fy", "fp", "value",
            "concept", "accession", "filed", "derived"]
    conn.executemany(f"INSERT OR REPLACE INTO statement_lines (company_id,{','.join(cols)}) "
                     f"VALUES (?,{','.join('?' * len(cols))})",
                     [[cid] + [r[c] for c in cols] for r in rows])
    return len(rows)


def _person_id(conn, cik, name) -> int:
    if cik:
        r = conn.execute("SELECT id FROM people WHERE cik=?", (cik,)).fetchone()
        if r:
            if name:
                conn.execute("UPDATE people SET name=? WHERE id=?", (name, r[0]))
            return r[0]
        return conn.execute("INSERT INTO people (cik, name) VALUES (?,?)", (cik, name)).lastrowid
    r = conn.execute("SELECT id FROM people WHERE cik IS NULL AND name=?", (name,)).fetchone()
    return r[0] if r else conn.execute("INSERT INTO people (name) VALUES (?)", (name,)).lastrowid


def build_insiders(conn, cid, reg, base) -> int:
    _wipe(conn, cid, "insider_txns", "roles")
    n = 0
    bad = 0
    rows = conn.execute(
        "SELECT accession, form, filed, raw_path FROM filings WHERE company_id=? AND raw_path IS "
        "NOT NULL AND form IN (%s) ORDER BY filed" % ",".join("?" * len(INSIDER_FORMS)),
        (cid, *INSIDER_FORMS)).fetchall()
    for f in rows:
        raw = archive.read_raw(base / f["raw_path"])
        doc = next((d for d in edgar_filings.split_documents(raw)
                    if d["kind"] == "xml" or d["doc_type"].startswith(("3", "4", "5"))), None)
        if doc is None:
            continue
        try:
            p = form4.parse(edgar_filings.unwrap_xml(doc["body"]))
        except ET.ParseError:
            bad += 1
            continue
        if not p["owners"]:
            continue
        pids = []
        for o in p["owners"]:
            pid = _person_id(conn, o["cik"], o["name"])
            pids.append(pid)
            title = o["title"] or ("Director" if o["is_director"] else
                                   "10% owner" if o["is_ten_pct"] else "")
            conn.execute(
                "INSERT INTO roles VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(company_id, person_id, title) "
                "DO UPDATE SET first_seen=MIN(first_seen, excluded.first_seen), "
                "last_seen=MAX(last_seen, excluded.last_seen), "
                "is_director=MAX(is_director, excluded.is_director), "
                "is_officer=MAX(is_officer, excluded.is_officer), "
                "is_ten_pct=MAX(is_ten_pct, excluded.is_ten_pct)",
                (cid, pid, o["is_director"], o["is_officer"], o["is_ten_pct"], o["is_other"], title,
                 f["filed"], f["filed"]))
        for i, t in enumerate(p["txns"]):
            notes = None
            if t["footnotes"]:
                notes = json.dumps({k: p["footnotes"].get(k) for k in t["footnotes"].split(",")})
            conn.execute("INSERT INTO insider_txns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (cid, f["accession"], i, pids[0], f["form"].replace("/A", ""),
                          t["table_kind"], t["security"], t["txn_date"] or p["period"], t["code"],
                          t["acq_disp"], t["shares"], t["price"], t["shares_after"], t["ownership"],
                          t["nature"], p["aff_10b5_1"], notes))
            n += 1
    if bad:
        print(f"  insiders: {bad} unparseable ownership XML docs skipped", file=sys.stderr)
    return n


def build_events(conn, cid, reg, base) -> int:
    _wipe(conn, cid, "events")
    ev = []
    for f in conn.execute("SELECT accession, form, filed, report_date, items, primary_desc "
                          "FROM filings WHERE company_id=?", (cid,)):
        form = f["form"]
        if form in ("8-K", "8-K/A"):
            codes = [c.strip() for c in (f["items"] or "").split(",") if c.strip()]
            labels = [ITEMS_8K.get(c, c) for c in codes if c != "9.01"]
            if "2.02" in codes:
                ev.append((f["filed"], "earnings", "Results release (8-K 2.02)", ", ".join(labels), f["accession"], 3))
            else:
                imp = 3 if HIGH_ITEMS & set(codes) else 1
                ev.append((f["filed"], "8k", "8-K: " + (", ".join(labels) or "Current report"),
                           ",".join(codes), f["accession"], imp))
        elif form in PERIODIC:
            ev.append((f["filed"], "filing", form + (f" ({f['report_date']})" if f["report_date"] else ""),
                       f["primary_desc"], f["accession"], PERIODIC[form]))
    for a in conn.execute("SELECT date, kind, ratio, amount FROM corporate_actions WHERE company_id=?", (cid,)):
        if a["kind"] == "split":
            ev.append((a["date"], "split", f"Stock split {a['ratio']}", None, None, 3))
        else:
            ev.append((a["date"], "dividend", f"Dividend ${a['amount']:.4f}", None, None, 1))
    # Open-market insider buys/sells, one event per person per day.
    for r in conn.execute(
            "SELECT t.txn_date d, p.name, t.code, SUM(t.shares) sh, SUM(t.shares*COALESCE(t.price,0)) usd, "
            "MIN(t.accession) acc FROM insider_txns t JOIN people p ON p.id=t.person_id "
            "WHERE t.company_id=? AND t.code IN ('P','S') AND t.table_kind='nonDerivative' "
            "GROUP BY t.txn_date, p.id, t.code", (cid,)):
        verb = "bought" if r["code"] == "P" else "sold"
        usd = r["usd"] or 0
        imp = 3 if usd >= 50e6 or r["code"] == "P" else 2 if usd >= 5e6 else 1
        ev.append((r["d"], "insider", f"{r['name']} {verb} {r['sh']:,.0f} sh",
                   f"${usd:,.0f}", r["acc"], imp))
    # >5% holder filings (one event per filing, largest reported stake)
    for r in conn.execute(
            "SELECT filed, form, filer_name, MAX(percent) pct, accession FROM holders_13dg WHERE company_id=? "
            "GROUP BY accession", (cid,)):
        pct = f" · {r['pct']:.1f}%" if r["pct"] is not None else ""
        ev.append((r["filed"], "holder", f"{r['filer_name']} {r['form']}{pct}", None, r["accession"],
                   2 if (r["form"] or "").upper().replace("SCHEDULE", "SC").startswith("SC 13D") else 1))
    conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?)",
                     [(cid, d, k, t, det, acc, imp) for d, k, t, det, acc, imp in ev if d])
    return len(ev)


FTS_SKIP_TYPES = ("GRAPHIC", "ZIP", "EXCEL", "XML", "JSON")
FTS_DOC_LIMIT = 3_000_000  # chars per document


def build_fts(conn, cid, reg, base) -> int:
    conn.execute("DELETE FROM filing_text WHERE company_id=?", (cid,))
    n = 0
    rows = conn.execute("SELECT accession, form, filed, raw_path FROM filings WHERE company_id=? "
                        "AND raw_path IS NOT NULL AND form NOT IN (%s)"
                        % ",".join("?" * len(INSIDER_FORMS)), (cid, *INSIDER_FORMS)).fetchall()
    for i, f in enumerate(rows, 1):
        raw = archive.read_raw(base / f["raw_path"])
        for d in edgar_filings.split_documents(raw):
            if d["kind"] not in ("html", "text") or d["doc_type"].upper().startswith(FTS_SKIP_TYPES):
                continue
            body = text.plain_text(d["body"], d["kind"], FTS_DOC_LIMIT)
            if len(body) < 40:
                continue
            conn.execute("INSERT INTO filing_text (body, company_id, accession, seq, form, filed, doc_type) "
                         "VALUES (?,?,?,?,?,?,?)",
                         (body, cid, f["accession"], d["seq"], f["form"], f["filed"], d["doc_type"]))
            n += 1
        if i % 200 == 0:
            print(f"    fts {i}/{len(rows)} filings", file=sys.stderr)
    return n


register_step("statements", build_statements)
register_step("insiders", build_insiders)
register_step("ownership", p4_steps.build_ownership)
register_step("short_interest", p4_steps.build_short_interest)
register_step("exec_comp", p4_steps.build_exec_comp)
register_step("news", p4_steps.build_news)
register_step("events", build_events)
register_step("fts", build_fts)
