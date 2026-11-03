"""archive.py — the immutable raw archive.

Layout under data/companies/<TICKER>/raw/:
  snapshots   <source>/<YYYY-MM-DD>/<name>   (things that change: submissions, facts, prices)
  immutables  edgar/filings/<YYYY>/<accession>.txt.gz  (a filing never changes once accepted)

Every write appends a line to the company's manifest.jsonl:
  {path, url, fetched_at, sha256 (of uncompressed bytes), bytes}
Files are never edited in place. The normalized DB is rebuilt from these.
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .fsutil import atomic_write_bytes, sha256


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _manifest_append(base: Path, rec: dict) -> None:
    base.mkdir(parents=True, exist_ok=True)
    with open(base / "manifest.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def write_raw(base: Path, relpath: str, data: bytes, url: str, compress: bool = False) -> Path:
    """Write raw bytes to base/raw/relpath (gzipped if compress). base = company or reference dir."""
    path = base / "raw" / relpath
    payload = gzip.compress(data, compresslevel=6, mtime=0) if compress else data
    atomic_write_bytes(path, payload)
    _manifest_append(base, {
        "path": str(path.relative_to(base)),
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": sha256(data),
        "bytes": len(data),
    })
    return path


def write_snapshot(base: Path, source: str, name: str, data: bytes, url: str,
                   compress: bool = False) -> Path:
    rel = f"{source}/{today()}/{name}" + (".gz" if compress else "")
    return write_raw(base, rel, data, url, compress=compress)


def read_raw(path: Path) -> bytes:
    data = Path(path).read_bytes()
    return gzip.decompress(data) if str(path).endswith(".gz") else data


def latest_snapshot(base: Path, source: str, name: str) -> Path | None:
    """Newest dated snapshot of `name` under base/raw/source/, or None."""
    root = base / "raw" / source
    if not root.is_dir():
        return None
    for day in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        for cand in (day / name, day / (name + ".gz")):
            if cand.exists():
                return cand
    return None


def company_base(ticker: str) -> Path:
    return config.company_dir(ticker)


def reference_base() -> Path:
    return config.REFERENCE_DIR
