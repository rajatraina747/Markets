"""markets CLI — add / update / rebuild / status / serve."""
from __future__ import annotations

import argparse
import sys

from . import config, db, registry
from .net import Fetcher

SOURCES = ["submissions", "xbrl", "prices", "shorts", "news", "filings"]


def cmd_add(a) -> int:
    rec = registry.add(a.ticker, Fetcher())
    print(f"tracking {rec['ticker']}: {rec['name']} (CIK {rec['cik']}, {rec.get('exchange')})")
    print(f"next: ./markets update {rec['ticker']}")
    return 0


def cmd_update(a) -> int:
    from .normalize import build
    from .sources import edgar_filings, edgar_submissions, edgar_xbrl, prices
    reg = registry.get(a.ticker)
    base = config.company_dir(reg["ticker"])
    f = Fetcher()
    only = set(a.only.split(",")) if a.only else set(SOURCES)
    if a.skip_filings:
        only.discard("filings")
    if "submissions" in only or "filings" in only:
        print("submissions…", file=sys.stderr)
        edgar_submissions.fetch(base, reg["cik"], f)
    if "xbrl" in only:
        print("xbrl companyfacts…", file=sys.stderr)
        edgar_xbrl.fetch(base, reg["cik"], f)
    if "prices" in only:
        print("prices…", file=sys.stderr)
        snap = prices.fetch(base, reg["ticker"], f)
        try:
            from . import archive
            nsnap = prices.fetch_nasdaq(base, reg["ticker"], f)
            rec = prices.reconcile(prices.parse_yahoo(archive.read_raw(snap))["bars"],
                                   prices.parse_nasdaq(archive.read_raw(nsnap)))
            flag = "OK" if not rec["mismatches"] else f"{len(rec['mismatches'])} MISMATCHES"
            print(f"  yahoo vs nasdaq: {rec['shared']} shared closes, {flag}", file=sys.stderr)
        except Exception as e:  # cross-check is advisory, never fatal
            print(f"  nasdaq cross-check skipped: {e}", file=sys.stderr)
    if "shorts" in only:
        from .sources import short_interest
        print("short interest (FINRA)…", file=sys.stderr)
        try:
            short_interest.fetch(base, reg["ticker"], f)
        except Exception as e:
            print(f"  short interest skipped: {e}", file=sys.stderr)
    if "news" in only:
        from .sources import news
        print("news (Google News RSS + GDELT)…", file=sys.stderr)
        try:
            news.fetch(base, reg["ticker"], reg["name"], f)
        except Exception as e:
            print(f"  news skipped: {e}", file=sys.stderr)
    if "filings" in only:
        main, pages = edgar_submissions.load_latest(base, reg["cik"])
        rows = edgar_submissions.parse_filings(main, pages)
        forms = set(a.forms.split(",")) if a.forms else None
        print(f"filings: {len(rows)} on EDGAR…", file=sys.stderr)
        st = edgar_filings.download_all(base, reg["cik"], rows, f, forms=forms, limit=a.limit)
        print(f"  downloaded {st['ok']}/{st['todo']} ({st['bytes'] / 1e6:,.0f} MB), "
              f"{len(st['failed'])} failed", file=sys.stderr)
    if not a.no_rebuild:
        print("rebuild…", file=sys.stderr)
        build.rebuild(reg)
    return 0


def cmd_rebuild(a) -> int:
    from .normalize import build
    tickers = [a.ticker.upper()] if a.ticker else sorted(registry.load())
    only = set(a.only.split(",")) if a.only else None
    for t in tickers:
        print(f"rebuild {t}…", file=sys.stderr)
        build.rebuild(registry.get(t), only=only)
    return 0


def cmd_status(a) -> int:
    reg = registry.load()
    if not reg:
        print("no companies tracked — ./markets add TSLA")
        return 0
    conn = db.ensure_schema()
    for t in ([a.ticker.upper()] if a.ticker else sorted(reg)):
        cid = db.company_id(conn, t)
        print(f"{t}  {reg[t]['name']}  CIK {reg[t]['cik']}")
        if cid is None:
            print("  (not built yet — ./markets update", t + ")")
            continue
        q = lambda sql: conn.execute(sql, (cid,)).fetchone()[0]  # noqa: E731
        total = q("SELECT COUNT(*) FROM filings WHERE company_id=?")
        have = q("SELECT COUNT(*) FROM filings WHERE company_id=? AND raw_path IS NOT NULL")
        print(f"  filings      {have:,}/{total:,} archived")
        for table in ("filing_documents", "facts", "statement_lines", "prices_daily",
                      "insider_txns", "people", "events", "holders_13dg", "news"):
            try:
                print(f"  {table:<16} {q(f'SELECT COUNT(*) FROM {table} WHERE company_id=?'):,}")
            except Exception:
                pass
        rng = conn.execute("SELECT MIN(date), MAX(date) FROM prices_daily WHERE company_id=?",
                           (cid,)).fetchone()
        if rng[0]:
            print(f"  prices       {rng[0]} → {rng[1]}")
    return 0


def cmd_serve(a) -> int:
    from .api import server
    server.serve(port=a.port, open_browser=a.open)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="markets", description="£0 single-company research terminal")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add", help="start tracking a ticker")
    s.add_argument("ticker")
    s.set_defaults(fn=cmd_add)
    s = sub.add_parser("update", help="fetch new raw data, then rebuild")
    s.add_argument("ticker")
    s.add_argument("--only", help=f"comma list of {','.join(SOURCES)}")
    s.add_argument("--skip-filings", action="store_true", help="skip the (slow) filing archive")
    s.add_argument("--forms", help="only download these form types, e.g. 10-K,10-Q")
    s.add_argument("--limit", type=int, help="download at most N filings this run")
    s.add_argument("--no-rebuild", action="store_true")
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
