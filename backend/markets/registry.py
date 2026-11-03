"""registry.py — which companies Markets tracks (data/companies.json)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import archive, config
from .fsutil import atomic_write_json, load_json
from .net import Fetcher

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"


def load() -> dict[str, dict]:
    return load_json(config.REGISTRY_PATH, {}) or {}


def save(reg: dict[str, dict]) -> None:
    atomic_write_json(config.REGISTRY_PATH, dict(sorted(reg.items())))


def parse_ticker_map(payload: dict) -> dict[str, dict]:
    """company_tickers_exchange.json → {TICKER: {cik, name, exchange}}."""
    fields = payload["fields"]
    out: dict[str, dict] = {}
    for row in payload["data"]:
        rec = dict(zip(fields, row))
        t = str(rec["ticker"]).upper()
        out.setdefault(t, {"cik": int(rec["cik"]), "name": rec["name"],
                           "exchange": rec.get("exchange")})
    return out


def ticker_map(fetcher: Fetcher, refresh: bool = False) -> dict[str, dict]:
    global _TMAP
    if _TMAP is not None and not refresh:
        return _TMAP
    _TMAP = _ticker_map(fetcher, refresh)
    return _TMAP


_TMAP: dict | None = None


def _ticker_map(fetcher: Fetcher, refresh: bool = False) -> dict[str, dict]:
    base = archive.reference_base()
    snap = None if refresh else archive.latest_snapshot(base, "sec", "company_tickers_exchange.json")
    if snap is None:
        data = fetcher.get(SEC_TICKERS_URL)
        snap = archive.write_snapshot(base, "sec", "company_tickers_exchange.json", data, SEC_TICKERS_URL)
    return parse_ticker_map(json.loads(archive.read_raw(snap)))


NON_SEC_SUFFIX = {"L": ("GB", "LSE"), "IL": ("GB", "LSE IOB")}


TIERS = ("full", "lite", "core")


def tier(rec: dict) -> str:
    """full = everything; lite = + ownership/proxy filings; core = prices + XBRL + index only."""
    return rec.get("tier") or ("lite" if rec.get("lite") else "full")


def add(ticker: str, fetcher: Fetcher, lite: bool | None = None, ch_number: str | None = None,
        tier_: str | None = None, sector: str | None = None) -> dict:
    ticker = ticker.upper()
    reg = load()
    if tier_ is not None:
        lite = tier_ != "full"
    if ticker in reg and (tier_ or sector):
        changed = False
        if tier_ and tier(reg[ticker]) != tier_ and not (tier_ == "core" and tier(reg[ticker]) != "core"):
            reg[ticker]["tier"] = tier_
            reg[ticker]["lite"] = tier_ != "full"
            changed = True
        if sector and reg[ticker].get("sector") != sector:
            reg[ticker]["sector"] = sector
            changed = True
        if changed:
            save(reg)
    if ticker in reg and ch_number and reg[ticker].get("ch_number") != ch_number:
        reg[ticker]["ch_number"] = ch_number
        save(reg)
    if ticker in reg:
        if lite is not None and tier_ is None and bool(reg[ticker].get("lite")) != lite:
            reg[ticker]["lite"] = lite
            reg[ticker]["tier"] = "lite" if lite else "full"
            save(reg)
        return reg[ticker]
    if "." in ticker and ticker.rsplit(".", 1)[1] in NON_SEC_SUFFIX:
        # Non-SEC listing (e.g. RR.L on the LSE): prices via Yahoo, filings via Companies House if a
        # number is given. Name is filled from the quote on first update.
        country, exchange = NON_SEC_SUFFIX[ticker.rsplit(".", 1)[1]]
        rec = {"ticker": ticker, "cik": None, "name": None, "exchange": exchange, "country": country,
               "ch_number": ch_number, "lite": True,
               "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        reg[ticker] = rec
        save(reg)
        config.company_dir(ticker).mkdir(parents=True, exist_ok=True)
        return rec
    tmap = ticker_map(fetcher)
    if ticker not in tmap:
        tmap = ticker_map(fetcher, refresh=True)
    if ticker not in tmap:
        raise SystemExit(f"{ticker}: not in SEC's ticker map. For London listings use the Yahoo form, e.g. RR.L "
                         f"(optionally --ch <Companies House number>)")
    rec = dict(tmap[ticker], ticker=ticker, lite=bool(lite), tier=tier_ or ("lite" if lite else "full"),
               sector=sector,
               added_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    reg[ticker] = rec
    save(reg)
    config.company_dir(ticker).mkdir(parents=True, exist_ok=True)
    return rec


def get(ticker: str) -> dict:
    reg = load()
    t = ticker.upper()
    if t not in reg:
        raise SystemExit(f"{t} is not tracked — run: ./markets add {t}")
    return reg[t]
