"""Form 13F institutional holdings — SEC's quarterly bulk data sets.

  https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
Each ~90 MB zip covers three months of 13F-HR filings (every institutional
manager with >$100M). Stored once under data/reference/sec/13f/ and shared by
every company; per-company rows are filtered by CUSIP at rebuild time.
VALUE is in dollars from 2023-01-03 onward, thousands before.
"""
from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from pathlib import Path

from .. import archive
from ..net import Fetcher

INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
BASE_URL = "https://www.sec.gov"
SOURCE = "sec/13f"
_ZIP_RX = re.compile(r'href="(/files/[^"]*form-13f-data-sets/([0-9a-z]+-[0-9a-z]+)_form13f\.zip)"')


def zip_dir() -> Path:
    return archive.reference_base() / "raw" / SOURCE


def list_periods(fetcher: Fetcher) -> list[tuple[str, str]]:
    html = fetcher.get(INDEX_URL).decode("utf-8", "replace")
    seen, out = set(), []
    for href, name in _ZIP_RX.findall(html):
        if name not in seen:
            seen.add(name)
            out.append((name, href))
    return out  # newest first, as listed


def fetch(fetcher: Fetcher, periods: int = 8) -> list[Path]:
    """Download the newest `periods` data sets not already archived (write-once)."""
    out = []
    for name, href in list_periods(fetcher)[:periods]:
        path = zip_dir() / f"{name}_form13f.zip"
        if path.exists():
            out.append(path)
            continue
        print(f"  13F data set {name}…", file=sys.stderr)
        data = fetcher.get(BASE_URL + href)
        out.append(archive.write_raw(archive.reference_base(), f"{SOURCE}/{name}_form13f.zip", data, BASE_URL + href))
    return out


def _tsv(zf: zipfile.ZipFile, name: str):
    member = next(m for m in zf.namelist() if m.upper().endswith(name))
    with zf.open(member) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, "utf-8", errors="replace"), delimiter="\t")


def extract(path: Path, cusips: set[str]) -> list[dict]:
    """Holdings rows for the given CUSIPs from one data set, joined to manager + period."""
    cusips = {c.upper() for c in cusips}
    rows = []
    with zipfile.ZipFile(path) as zf:
        for r in _tsv(zf, "INFOTABLE.TSV"):
            if (r.get("CUSIP") or "").upper() in cusips:
                rows.append(r)
        if not rows:
            return []
        accs = {r["ACCESSION_NUMBER"] for r in rows}
        sub = {r["ACCESSION_NUMBER"]: r for r in _tsv(zf, "SUBMISSION.TSV") if r["ACCESSION_NUMBER"] in accs}
        cover = {r["ACCESSION_NUMBER"]: r for r in _tsv(zf, "COVERPAGE.TSV") if r["ACCESSION_NUMBER"] in accs}
    out = []
    for r in rows:
        s, c = sub.get(r["ACCESSION_NUMBER"], {}), cover.get(r["ACCESSION_NUMBER"], {})
        if (s.get("SUBMISSIONTYPE") or "").upper() not in ("13F-HR", "13F-HR/A"):
            continue
        filed = _date(s.get("FILING_DATE"))
        try:
            value = float(r.get("VALUE") or 0)
        except ValueError:
            value = 0.0
        if filed and filed < "2023-01-03":
            value *= 1000
        try:
            shares = float(r.get("SSHPRNAMT") or 0)
        except ValueError:
            shares = 0.0
        out.append({
            "accession": r["ACCESSION_NUMBER"], "period": _date(s.get("PERIODOFREPORT")), "filed": filed,
            "amendment": (s.get("SUBMISSIONTYPE") or "").upper().endswith("/A"),
            "manager": (c.get("FILINGMANAGER_NAME") or "").strip(), "manager_cik": s.get("CIK"),
            "value": value, "shares": shares, "share_type": r.get("SSHPRNAMTTYPE"),
            "put_call": (r.get("PUTCALL") or "").strip() or None,
            "discretion": r.get("INVESTMENTDISCRETION"),
        })
    return out


_MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def _date(s: str | None) -> str | None:
    """SEC 13F TSVs use DD-MON-YYYY."""
    if not s:
        return None
    m = re.match(r"(\d{2})-([A-Za-z]{3})-(\d{4})", s.strip())
    if not m:
        return s.strip()[:10]
    return f"{m.group(3)}-{_MONTHS[m.group(2).upper()]:02d}-{m.group(1)}"
