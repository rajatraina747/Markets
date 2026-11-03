"""Macro context — FRED keyless CSV downloads + Bank of England IADB.

  https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>
  https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&...
Cross-company: snapshots live under data/reference/raw/macro/.
"""
from __future__ import annotations

import csv
import io
import sys
from datetime import datetime
from pathlib import Path

from .. import archive
from ..net import Fetcher

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
BOE = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes"
       "&Datefrom=01/Jan/1975&Dateto=now&SeriesCodes={sid}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
SOURCE = "macro"

# key: (provider, series id, label, unit, group)
SERIES = {
    "DGS10": ("fred", "DGS10", "US 10-year Treasury yield", "%", "Rates"),
    "DGS2": ("fred", "DGS2", "US 2-year Treasury yield", "%", "Rates"),
    "T10Y2Y": ("fred", "T10Y2Y", "10y − 2y spread (curve)", "pp", "Rates"),
    "FEDFUNDS": ("fred", "FEDFUNDS", "Fed funds rate", "%", "Rates"),
    "BOE_BANK_RATE": ("boe", "IUDBEDR", "Bank of England Bank Rate", "%", "Rates"),
    "CPIAUCSL": ("fred", "CPIAUCSL", "US CPI (index)", "idx", "Economy"),
    "UNRATE": ("fred", "UNRATE", "US unemployment rate", "%", "Economy"),
    "VIXCLS": ("fred", "VIXCLS", "VIX volatility index", "pts", "Markets"),
    "DCOILWTICO": ("fred", "DCOILWTICO", "WTI crude oil", "$", "Markets"),
    "DTWEXBGS": ("fred", "DTWEXBGS", "US dollar index (broad)", "idx", "Markets"),
    "DEXUSUK": ("fred", "DEXUSUK", "GBP/USD", "$", "Markets"),
}


def fetch(fetcher: Fetcher) -> list[Path]:
    base = archive.reference_base()
    out = []
    for key, (prov, sid, *_rest) in SERIES.items():
        url = FRED.format(sid=sid) if prov == "fred" else BOE.format(sid=sid)
        try:
            out.append(archive.write_snapshot(base, SOURCE, f"{key}.csv", fetcher.get(url), url))
        except Exception as e:  # one series failing never blocks the rest
            print(f"  macro {key} skipped: {e}", file=sys.stderr)
    return out


def parse(raw: bytes, provider: str) -> list[tuple[str, float]]:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig", "replace"))))
    out = []
    for r in rows[1:]:
        if len(r) < 2 or r[1].strip() in ("", "."):
            continue
        d = r[0].strip()
        try:
            if provider == "boe":
                d = datetime.strptime(d, "%d %b %Y").strftime("%Y-%m-%d")
            out.append((d[:10], float(r[1])))
        except ValueError:
            continue
    return out


def load_all() -> dict[str, list[tuple[str, float]]]:
    base = archive.reference_base()
    out = {}
    for key, (prov, *_rest) in SERIES.items():
        snap = archive.latest_snapshot(base, SOURCE, f"{key}.csv")
        if snap:
            out[key] = parse(archive.read_raw(snap), prov)
    return out
