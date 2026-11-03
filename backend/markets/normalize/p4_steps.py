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
