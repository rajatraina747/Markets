"""Short interest — FINRA consolidated short interest (free, keyless query API).

  POST https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest
Bi-monthly settlement dates; values are as-reported (not split-adjusted).
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import archive
from ..net import Fetcher

URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
SOURCE = "finra/short_interest"
PAGE = 5000


def fetch(base: Path, ticker: str, fetcher: Fetcher) -> Path:
    rows: list = []
    offset = 0
    while True:
        page = json.loads(fetcher.post_json(URL, {"limit": PAGE, "offset": offset, "compareFilters": [
            {"compareType": "equal", "fieldName": "symbolCode", "fieldValue": ticker.upper()}]}) or b"[]")
        rows.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE
    data = json.dumps(rows).encode()
    return archive.write_snapshot(base, SOURCE, "consolidated.json", data, URL, compress=True)


def parse(raw: bytes) -> list[dict]:
    out = {}
    for r in json.loads(raw):
        d = r.get("settlementDate")
        if not d:
            continue
        out[d] = {"settle_date": d, "shares_short": r.get("currentShortPositionQuantity"),
                  "avg_daily_vol": r.get("averageDailyVolumeQuantity"),
                  "days_to_cover": r.get("daysToCoverQuantity")}
    return sorted(out.values(), key=lambda x: x["settle_date"])
