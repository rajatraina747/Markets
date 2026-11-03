"""P4 build steps: 13D/G holders, short interest, exec comp (ecd XBRL), news."""
from __future__ import annotations

import sys

from .. import archive
from ..sources import news, ownership_13dg, short_interest
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
