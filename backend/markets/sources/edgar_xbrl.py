"""EDGAR XBRL companyfacts — every numeric fact the company has ever tagged.

  https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import archive
from ..net import Fetcher

URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SOURCE = "edgar/xbrl"


def name(cik: int) -> str:
    return f"companyfacts_CIK{cik:010d}.json"


def fetch(base: Path, cik: int, fetcher: Fetcher) -> Path:
    url = URL.format(cik=cik)
    return archive.write_snapshot(base, SOURCE, name(cik), fetcher.get(url), url, compress=True)


def load_latest(base: Path, cik: int) -> dict | None:
    snap = archive.latest_snapshot(base, SOURCE, name(cik))
    return json.loads(archive.read_raw(snap)) if snap else None


def parse(payload: dict) -> tuple[list[dict], list[dict]]:
    """→ (facts rows, concept rows)."""
    facts, concepts = [], []
    for taxonomy, cmap in (payload.get("facts") or {}).items():
        for concept, body in cmap.items():
            concepts.append({"taxonomy": taxonomy, "concept": concept,
                             "label": body.get("label"), "description": body.get("description")})
            for unit, vals in (body.get("units") or {}).items():
                for v in vals:
                    if v.get("val") is None:
                        continue
                    facts.append({
                        "taxonomy": taxonomy, "concept": concept, "unit": unit,
                        "value": float(v["val"]),
                        "period_start": v.get("start"), "period_end": v["end"],
                        "fy": v.get("fy"), "fp": v.get("fp"), "form": v.get("form"),
                        "filed": v.get("filed"), "accession": v.get("accn"),
                        "frame": v.get("frame"),
                    })
    return facts, concepts
