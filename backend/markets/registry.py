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
    base = archive.reference_base()
    snap = None if refresh else archive.latest_snapshot(base, "sec", "company_tickers_exchange.json")
    if snap is None:
        data = fetcher.get(SEC_TICKERS_URL)
        snap = archive.write_snapshot(base, "sec", "company_tickers_exchange.json", data, SEC_TICKERS_URL)
    return parse_ticker_map(json.loads(archive.read_raw(snap)))


def add(ticker: str, fetcher: Fetcher) -> dict:
    ticker = ticker.upper()
    reg = load()
    if ticker in reg:
        return reg[ticker]
    tmap = ticker_map(fetcher)
    if ticker not in tmap:
        tmap = ticker_map(fetcher, refresh=True)
    if ticker not in tmap:
        raise SystemExit(f"{ticker}: not found in SEC's ticker map (US SEC filers only for now)")
    rec = dict(tmap[ticker], ticker=ticker,
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
