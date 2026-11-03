"""Daily prices — Yahoo chart API (primary), Nasdaq historical (cross-check).

Lessons carried over from Ember: Yahoo is unofficial and can silently change
shape, so parse() validates and fails loudly; Nasdaq is the keyless second
source used to reconcile closes; Stooq sits behind an anti-bot wall (skipped).
Note `range=max` downsamples to monthly — always use period1=0 for daily.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import archive
from ..net import Fetcher

YAHOO = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
         "?period1=0&period2={now}&interval=1d&events=div%2Csplit&includeAdjustedClose=true")
NASDAQ = ("https://api.nasdaq.com/api/quote/{sym}/historical?assetclass=stocks"
          "&fromdate={start}&todate={end}&limit=99999")
SOURCE_Y = "prices/yahoo"
SOURCE_N = "prices/nasdaq"


class PriceSchemaError(ValueError):
    pass


def fetch(base: Path, ticker: str, fetcher: Fetcher) -> Path:
    url = YAHOO.format(sym=ticker.upper(), now=int(time.time()))
    data = fetcher.get(url)
    parse_yahoo(data)  # validate before archiving as "good"
    return archive.write_snapshot(base, SOURCE_Y, "chart_1d.json", data, url, compress=True)


def fetch_nasdaq(base: Path, ticker: str, fetcher: Fetcher, years: int = 10) -> Path | None:
    end = datetime.now(timezone.utc).date()
    start = end.replace(year=end.year - years)
    url = NASDAQ.format(sym=ticker.upper().replace("-", "."), start=start, end=end)
    data = fetcher.get(url, headers={"Accept": "application/json"})
    return archive.write_snapshot(base, SOURCE_N, "historical.json", data, url, compress=True)


def _d(ts: int, gmtoffset: int = 0) -> str:
    # Yahoo stamps bars at the session open in exchange time; shift by the
    # exchange offset so the date is the exchange-local trading date.
    return datetime.fromtimestamp(ts + gmtoffset, tz=timezone.utc).strftime("%Y-%m-%d")


def parse_yahoo(raw: bytes) -> dict:
    """→ {meta, bars[], splits[], dividends[]}. Raises PriceSchemaError on drift."""
    try:
        chart = json.loads(raw)["chart"]
        if chart.get("error"):
            raise PriceSchemaError(f"yahoo error: {chart['error']}")
        res = chart["result"][0]
        meta = res["meta"]
        off = int(meta.get("gmtoffset") or 0)
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(ts)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise PriceSchemaError(f"yahoo payload shape changed: {e}") from e
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):
            continue
        bars.append({"date": _d(t, off), "open": float(o), "high": float(h), "low": float(l),
                     "close": float(c), "adj_close": float(adj[i]) if adj[i] is not None else None,
                     "volume": int(v or 0)})
    if not bars:
        raise PriceSchemaError("yahoo returned no bars")
    for b in bars:
        if not (b["low"] <= min(b["open"], b["close"]) and b["high"] >= max(b["open"], b["close"])
                and b["low"] > 0):
            raise PriceSchemaError(f"implausible bar {b}")
    ev = res.get("events") or {}
    splits = [{"date": _d(s["date"], off), "numerator": float(s["numerator"]),
               "denominator": float(s["denominator"]), "ratio": s.get("splitRatio")}
              for s in (ev.get("splits") or {}).values()]
    divs = [{"date": _d(d["date"], off), "amount": float(d["amount"])}
            for d in (ev.get("dividends") or {}).values()]
    return {
        "meta": {
            "as_of": datetime.fromtimestamp(meta.get("regularMarketTime", 0), tz=timezone.utc)
                     .isoformat(timespec="seconds"),
            "price": meta.get("regularMarketPrice"),
            "prev_close": meta.get("chartPreviousClose"),
            "day_high": meta.get("regularMarketDayHigh"),
            "day_low": meta.get("regularMarketDayLow"),
            "volume": meta.get("regularMarketVolume"),
            "high_52w": meta.get("fiftyTwoWeekHigh"),
            "low_52w": meta.get("fiftyTwoWeekLow"),
            "currency": meta.get("currency"),
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
            "long_name": meta.get("longName"),
        },
        "bars": sorted(bars, key=lambda b: b["date"]),
        "splits": sorted(splits, key=lambda s: s["date"]),
        "dividends": sorted(divs, key=lambda s: s["date"]),
    }


def _num(s) -> float:
    return float(str(s).replace("$", "").replace(",", "").strip())


def parse_nasdaq(raw: bytes) -> list[dict]:
    payload = json.loads(raw)
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows")) or []
    out = []
    for r in rows:
        try:
            m, d, y = r["date"].split("/")
            out.append({"date": f"{y}-{m}-{d}", "close": _num(r["close"]),
                        "volume": int(_num(r["volume"]))})
        except (KeyError, ValueError):
            continue
    return sorted(out, key=lambda b: b["date"])


def reconcile(primary: list[dict], secondary: list[dict], tol: float = 0.01) -> dict:
    """Compare closes on shared dates; returns {shared, mismatches[...]}."""
    sec = {b["date"]: b["close"] for b in secondary}
    mism = []
    shared = 0
    for b in primary:
        s = sec.get(b["date"])
        if s is None:
            continue
        shared += 1
        if abs(b["close"] - s) / s > tol:
            mism.append({"date": b["date"], "yahoo": b["close"], "nasdaq": s})
    return {"shared": shared, "mismatches": mism}
