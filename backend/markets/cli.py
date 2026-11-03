"""markets CLI — add / universe / update / rebuild / status / serve.

Tiers (per ticker, in data/companies.json):
  full  everything, incl. every filing & exhibit (TSLA ≈ 2 GB raw)
  lite  + ownership/proxy filings + per-filing XBRL instances (segments) — no full archive
  core  prices + XBRL facts + filing index + short interest — for broad universes (S&P 500)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, db, registry
from .net import Fetcher

LITE_FORMS = {"SC 13G", "SC 13G/A", "SC 13D", "SC 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A", "SCHEDULE 13D",
              "SCHEDULE 13D/A", "DEF 14A"}
SOURCES = ["submissions", "xbrl", "prices", "shorts", "news", "macro", "13f", "segments", "filings"]
GLOBAL_SOURCES = {"macro", "13f"}           # shared across companies: fetched once per run
TIER_SOURCES = {
    "full": set(SOURCES),
    "lite": set(SOURCES),
    "core": {"submissions", "xbrl", "prices", "shorts"},
}
UNIVERSES = {"sp500": Path(__file__).with_name("universes_sp500.json")}


def _tier_arg(a) -> str | None:
    return "full" if getattr(a, "full", False) else "lite" if getattr(a, "lite", False) else \
        "core" if getattr(a, "core", False) else None


def cmd_add(a) -> int:
    rec = registry.add(a.ticker, Fetcher(), ch_number=a.ch, tier_=_tier_arg(a))
    if rec.get("cik"):
        print(f"tracking {rec['ticker']}: {rec['name']} (CIK {rec['cik']}, {rec.get('exchange')}) · "
              f"tier {registry.tier(rec)}")
    else:
        print(f"tracking {rec['ticker']} ({rec.get('exchange')}, non-SEC): prices + news + macro"
              + (f" + Companies House {rec['ch_number']}" if rec.get("ch_number") else
                 " — add --ch <Companies House number> for officers, PSCs and filings"))
    print(f"next: ./markets update {rec['ticker']}")
    return 0


def cmd_universe(a) -> int:
    """Track every member of a universe at the given tier (never downgrades existing tickers)."""
    members = json.loads(UNIVERSES[a.name].read_text())
    f = Fetcher()
    added, missing = 0, []
    for m in members:
        t = (m.get("yahoo_ticker") or m["ticker"]).upper()
        try:
            registry.add(t, f, tier_=a.tier, sector=m.get("sector"))
            added += 1
        except SystemExit:
            missing.append(t)
    print(f"{a.name}: {added} tracked at tier '{a.tier}' (existing full/lite tickers kept)"
          + (f"; not in SEC map: {', '.join(missing)}" if missing else ""))
    print("next: ./markets update all   (core tier ≈ 3 requests/ticker; ~15 min for the S&P 500)")
    return 0


def _update_sources(a, reg) -> set[str]:
    only = set(a.only.split(",")) if a.only else set(TIER_SOURCES[registry.tier(reg)])
    if a.skip_filings:
        only.discard("filings")
    if not reg.get("cik"):
        # non-SEC listing: no EDGAR sources; Companies House instead when we know the number
        if reg.get("ch_number") and not a.only:
            only.add("ch")
        only &= {"prices", "news", "macro", "ch"}
    return only


def cmd_update(a) -> int:
    if a.ticker.lower() == "all":
        return _update_many(a, sorted(registry.load()))
    reg = registry.get(a.ticker)
    rc = _update_one(argparse.Namespace(**{**vars(a), "no_rebuild": True}), reg)
    if not a.no_rebuild:
        from .normalize import build
        build.rebuild_global()
        print("rebuild…", file=sys.stderr)
        build.rebuild(reg, include_global=False)
    return rc


def _update_many(a, tickers: list[str]) -> int:
    rc, failed = 0, []
    reg_all = registry.load()
    f = Fetcher()
    for i, t in enumerate(tickers):
        print(f"=== [{i + 1}/{len(tickers)}] {t}", file=sys.stderr)
        a2 = argparse.Namespace(**{**vars(a), "ticker": t})
        if i:
            only = (set(a.only.split(",")) if a.only else set(SOURCES)) - GLOBAL_SOURCES
            a2.only = ",".join(sorted(only & (TIER_SOURCES[registry.tier(reg_all[t])] | {"ch"})))
        a2.no_rebuild = True  # fetch everything first; rebuild after the shared tables are fresh
        try:
            rc |= _update_one(a2, reg_all[t], f)
        except Exception as e:  # one ticker failing never stops the rest
            print(f"  {t} FAILED: {e}", file=sys.stderr)
            failed.append(t)
            rc = 1
    if not a.no_rebuild:
        from .normalize import build
        build.rebuild_global()
        for i, t in enumerate(tickers):
            print(f"rebuild [{i + 1}/{len(tickers)}] {t}…", file=sys.stderr)
            try:
                build.rebuild(reg_all[t], include_global=False, quiet=True)
            except Exception as e:
                print(f"  {t} rebuild FAILED: {e}", file=sys.stderr)
                failed.append(t)
    if failed:
        print(f"{len(failed)} failed: {', '.join(failed)}", file=sys.stderr)
    return rc


def _update_one(a, reg: dict, f: Fetcher | None = None) -> int:
    from .normalize import build
    from .sources import edgar_filings, edgar_submissions, edgar_xbrl, prices
    base = config.company_dir(reg["ticker"])
    f = f or Fetcher()
    tier = registry.tier(reg)
    only = _update_sources(a, reg)
    if "ch" in only:
        from .sources import companies_house
        print("Companies House…", file=sys.stderr)
        try:
            companies_house.fetch(base, reg["ch_number"], f)
        except Exception as e:
            print(f"  Companies House skipped: {e}", file=sys.stderr)
    if only & {"submissions", "filings", "segments"}:
        print("submissions…", file=sys.stderr)
        edgar_submissions.fetch(base, reg["cik"], f)
    if "xbrl" in only:
        print("xbrl companyfacts…", file=sys.stderr)
        edgar_xbrl.fetch(base, reg["cik"], f)
    if "prices" in only:
        print("prices…", file=sys.stderr)
        snap = prices.fetch(base, reg["ticker"], f)
        if reg.get("cik") and tier != "core":  # cross-check is advisory, and doubles requests on big universes
            try:
                from . import archive
                nsnap = prices.fetch_nasdaq(base, reg["ticker"], f)
                rec = prices.reconcile(prices.parse_yahoo(archive.read_raw(snap))["bars"],
                                       prices.parse_nasdaq(archive.read_raw(nsnap)))
                flag = "OK" if not rec["mismatches"] else f"{len(rec['mismatches'])} MISMATCHES"
                print(f"  yahoo vs nasdaq: {rec['shared']} shared closes, {flag}", file=sys.stderr)
            except Exception as e:
                print(f"  nasdaq cross-check skipped: {e}", file=sys.stderr)
    if "shorts" in only:
        from .sources import short_interest
        try:
            short_interest.fetch(base, reg["ticker"], f)
        except Exception as e:
            print(f"  short interest skipped: {e}", file=sys.stderr)
    if "news" in only:
        from .sources import news
        print("news (Google News RSS + GDELT)…", file=sys.stderr)
        try:
            news.fetch(base, reg["ticker"].split(".")[0], reg.get("name") or _quote_name(base) or reg["ticker"], f)
        except Exception as e:
            print(f"  news skipped: {e}", file=sys.stderr)
    if "macro" in only:
        from .sources import macro
        print("macro (FRED + BoE) + benchmarks (SPY, QQQ)…", file=sys.stderr)
        macro.fetch(f)
        try:
            prices.fetch_benchmarks(f)
        except Exception as e:
            print(f"  benchmarks skipped: {e}", file=sys.stderr)
    if "13f" in only:
        from .sources import sec_13f
        print("13F data sets (shared, ~90 MB each, only new ones)…", file=sys.stderr)
        try:
            sec_13f.fetch(f, periods=a.periods_13f)
        except Exception as e:
            print(f"  13F skipped: {e}", file=sys.stderr)
    if "filings" in only:
        main, pages = edgar_submissions.load_latest(base, reg["cik"])
        rows = edgar_submissions.parse_filings(main, pages)
        forms = set(a.forms.split(",")) if a.forms else (LITE_FORMS if tier == "lite" else None)
        print(f"filings: {len(rows)} on EDGAR{' (lite: ownership + proxy only)' if tier == 'lite' else ''}…",
              file=sys.stderr)
        st = edgar_filings.download_all(base, reg["cik"], rows, f, forms=forms, limit=a.limit)
        print(f"  downloaded {st['ok']}/{st['todo']} ({st['bytes'] / 1e6:,.0f} MB), "
              f"{len(st['failed'])} failed", file=sys.stderr)
    if "segments" in only and tier != "full":
        # full tier parses segments straight from the archived filings; others fetch XBRL instances
        from .sources import xbrl_instance
        main, pages = edgar_submissions.load_latest(base, reg["cik"])
        rows = edgar_submissions.parse_filings(main, pages)
        print("XBRL instances (segments)…", file=sys.stderr)
        st = xbrl_instance.fetch_all(base, reg["cik"], rows, f)
        print(f"  {st['ok']} new, {st['skipped']} unavailable", file=sys.stderr)
    return 0


def _quote_name(base) -> str | None:
    from . import archive
    from .sources import prices
    snap = archive.latest_snapshot(base, prices.SOURCE_Y, "chart_1d.json")
    return prices.parse_yahoo(archive.read_raw(snap))["meta"]["long_name"] if snap else None


def cmd_rebuild(a) -> int:
    from .normalize import build
    tickers = [a.ticker.upper()] if a.ticker else sorted(registry.load())
    only = set(a.only.split(",")) if a.only else None
    if not only or only & build.GLOBAL_STEPS:
        build.rebuild_global()
    for i, t in enumerate(tickers):
        print(f"rebuild [{i + 1}/{len(tickers)}] {t}…", file=sys.stderr)
        try:
            build.rebuild(registry.get(t), only=only, include_global=False, quiet=len(tickers) > 12)
        except Exception as e:
            print(f"  {t} FAILED: {e}", file=sys.stderr)
    return 0


def cmd_status(a) -> int:
    reg = registry.load()
    if not reg:
        print("no companies tracked — ./markets add TSLA")
        return 0
    if not a.ticker and len(reg) > 12:
        from collections import Counter
        tiers = Counter(registry.tier(r) for r in reg.values())
        print(f"{len(reg)} companies · " + " · ".join(f"{n} {t}" for t, n in sorted(tiers.items())))
        for t in sorted(t for t, r in reg.items() if registry.tier(r) != "core"):
            print(f"  {t:<6} {registry.tier(reg[t]):<5} {reg[t].get('name') or ''}")
        print("  (./markets status TICKER for detail)")
        return 0
    conn = db.ensure_schema()
    for t in ([a.ticker.upper()] if a.ticker else sorted(reg)):
        cid = db.company_id(conn, t)
        print(f"{t}  {reg[t].get('name') or ''}  " + (f"CIK {reg[t]['cik']}" if reg[t].get("cik") else reg[t].get("exchange") or "")
              + f"  · {registry.tier(reg[t])}")
        if cid is None:
            print("  (not built yet — ./markets update", t + ")")
            continue
        q = lambda sql: conn.execute(sql, (cid,)).fetchone()[0]  # noqa: E731
        total = q("SELECT COUNT(*) FROM filings WHERE company_id=?")
        have = q("SELECT COUNT(*) FROM filings WHERE company_id=? AND raw_path IS NOT NULL")
        print(f"  filings      {have:,}/{total:,} archived")
        for table in ("facts", "statement_lines", "segment_lines", "earnings", "prices_daily", "insider_txns",
                      "events", "news"):
            try:
                print(f"  {table:<16} {q(f'SELECT COUNT(*) FROM {table} WHERE company_id=?'):,}")
            except Exception:
                pass
        rng = conn.execute("SELECT MIN(date), MAX(date) FROM prices_daily WHERE company_id=?", (cid,)).fetchone()
        if rng[0]:
            print(f"  prices       {rng[0]} → {rng[1]}")
    return 0


def cmd_serve(a) -> int:
    from .api import server
    server.serve(port=a.port, open_browser=a.open)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="markets", description="£0 Bloomberg-style research terminal")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add", help="start tracking a ticker")
    s.add_argument("ticker")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--full", action="store_true", help="everything, incl. every filing (default for new tickers)")
    g.add_argument("--lite", action="store_true", help="no full archive: + ownership/proxy filings + segments")
    g.add_argument("--core", action="store_true", help="prices + XBRL financials only (broad universes)")
    s.add_argument("--ch", help="UK Companies House number (non-SEC listings, needs MARKETS_CH_KEY)")
    s.set_defaults(fn=cmd_add)
    s = sub.add_parser("universe", help="track a whole index, e.g. sp500")
    s.add_argument("name", choices=sorted(UNIVERSES))
    s.add_argument("--tier", default="core", choices=registry.TIERS)
    s.set_defaults(fn=cmd_universe)
    s = sub.add_parser("update", help="fetch new raw data, then rebuild (ticker or 'all')")
    s.add_argument("ticker")
    s.add_argument("--only", help=f"comma list of {','.join(SOURCES)}")
    s.add_argument("--skip-filings", action="store_true", help="skip the (slow) filing archive")
    s.add_argument("--forms", help="only download these form types, e.g. 10-K,10-Q")
    s.add_argument("--limit", type=int, help="download at most N filings this run")
    s.add_argument("--no-rebuild", action="store_true")
    s.add_argument("--periods-13f", type=int, default=8, help="how many quarterly 13F data sets to keep (default 8 ≈ 2y)")
    s.set_defaults(fn=cmd_update)
    s = sub.add_parser("rebuild", help="rebuild markets.db from raw (no network)")
    s.add_argument("ticker", nargs="?")
    s.add_argument("--only", help="comma list of build steps")
    s.set_defaults(fn=cmd_rebuild)
    s = sub.add_parser("status", help="what's archived and built")
    s.add_argument("ticker", nargs="?")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("serve", help="run the dashboard")
    s.add_argument("--port", type=int, default=config.SERVER_PORT)
    s.add_argument("--open", action="store_true", help="open in browser")
    s.set_defaults(fn=cmd_serve)
    a = p.parse_args(argv)
    return a.fn(a)
