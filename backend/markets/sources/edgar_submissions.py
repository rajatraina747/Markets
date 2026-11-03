"""EDGAR submissions API — company profile + the complete filing index.

  https://data.sec.gov/submissions/CIK##########.json        profile + ~1000 recent filings
  https://data.sec.gov/submissions/CIK##########-submissions-NNN.json  older pages

Snapshots are archived per fetch date; parse() is pure.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import archive
from ..net import Fetcher

BASE = "https://data.sec.gov/submissions/"
SOURCE = "edgar/submissions"


def main_name(cik: int) -> str:
    return f"CIK{cik:010d}.json"


def fetch(base: Path, cik: int, fetcher: Fetcher) -> list[Path]:
    """Snapshot the main file and every older page it references."""
    name = main_name(cik)
    main_bytes = fetcher.get(BASE + name)
    paths = [archive.write_snapshot(base, SOURCE, name, main_bytes, BASE + name)]
    for page in json.loads(main_bytes)["filings"].get("files", []):
        pname = page["name"]
        # Older pages are frozen history — fetch once, reuse forever.
        existing = archive.latest_snapshot(base, SOURCE, pname)
        if existing is None:
            data = fetcher.get(BASE + pname)
            existing = archive.write_snapshot(base, SOURCE, pname, data, BASE + pname)
        paths.append(existing)
    return paths


def load_latest(base: Path, cik: int) -> tuple[dict, list[dict]]:
    """(main payload, older page payloads) from the newest snapshots."""
    snap = archive.latest_snapshot(base, SOURCE, main_name(cik))
    if snap is None:
        raise FileNotFoundError(f"no submissions snapshot for CIK {cik} — run update first")
    main = json.loads(archive.read_raw(snap))
    pages = []
    for page in main["filings"].get("files", []):
        p = archive.latest_snapshot(base, SOURCE, page["name"])
        if p is not None:
            pages.append(json.loads(archive.read_raw(p)))
    return main, pages


def parse_profile(main: dict) -> dict:
    addr = main.get("addresses") or {}
    return {
        "cik": int(main["cik"]),
        "name": main.get("name"),
        "sic": main.get("sic"),
        "sic_desc": main.get("sicDescription"),
        "category": main.get("category"),
        "fiscal_year_end": main.get("fiscalYearEnd"),
        "state_of_inc": main.get("stateOfIncorporation"),
        "ein": main.get("ein"),
        "phone": main.get("phone"),
        "website": main.get("website") or main.get("investorWebsite") or None,
        "business_address": json.dumps(addr.get("business")),
        "mailing_address": json.dumps(addr.get("mailing")),
        "former_names": json.dumps(main.get("formerNames") or []),
        "tickers": json.dumps(main.get("tickers") or []),
        "exchanges": json.dumps(main.get("exchanges") or []),
    }


def _columns_to_rows(cols: dict) -> list[dict]:
    keys = list(cols)
    n = len(cols[keys[0]]) if keys else 0
    return [{k: cols[k][i] for k in keys} for i in range(n)]


def parse_filings(main: dict, pages: list[dict]) -> list[dict]:
    """Every filing across the recent block and older pages, de-duplicated, newest first."""
    rows = _columns_to_rows(main["filings"]["recent"])
    for page in pages:
        rows.extend(_columns_to_rows(page))
    seen: dict[str, dict] = {}
    for r in rows:
        acc = r["accessionNumber"]
        if acc in seen:
            continue
        seen[acc] = {
            "accession": acc,
            "form": r["form"],
            "filed": r["filingDate"],
            "accepted": r.get("acceptanceDateTime") or None,
            "report_date": r.get("reportDate") or None,
            "act": r.get("act") or None,
            "file_number": r.get("fileNumber") or None,
            "items": r.get("items") or None,
            "size": r.get("size"),
            "is_xbrl": r.get("isXBRL"),
            "is_inline_xbrl": r.get("isInlineXBRL"),
            "primary_doc": r.get("primaryDocument") or None,
            "primary_desc": r.get("primaryDocDescription") or None,
        }
    return sorted(seen.values(), key=lambda f: (f["filed"], f["accession"]), reverse=True)
