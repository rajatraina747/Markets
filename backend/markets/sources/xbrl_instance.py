"""Dimensional XBRL facts from each 10-K / 10-Q — segment, product and geography breakdowns.

companyfacts only carries un-dimensioned facts, so "revenue by segment" needs the filing's own
XBRL instance:
  - 2009–2018: an EX-101.INS XML document inside the filing
  - 2019 → : inline XBRL (ix:nonFraction tags) in the primary HTML; SEC also publishes the
    extracted instance as <name>_htm.xml in the filing directory
Full-tier companies parse straight from the archived submission. Other tiers fetch just the
instance file (via the filing's index.json) into raw/edgar/xbrl_instances/<accession>.xml.gz.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path

from .. import archive
from ..net import FetchError, Fetcher
from . import edgar_filings

PERIODIC = {"10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT"}
INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/index.json"
FILE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{name}"

# Concepts worth breaking down. Anything else dimensional is ignored (equity roll-forwards etc.).
CONCEPTS = {
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet", "CostOfRevenue", "CostOfGoodsAndServicesSold", "GrossProfit", "OperatingIncomeLoss",
    "SegmentReportingInformationOperatingIncomeLoss", "Assets", "PaymentsToAcquirePropertyPlantAndEquipment",
    "DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
}
SKIP_AXES = {"us-gaap:StatementEquityComponentsAxis", "srt:ConsolidationItemsAxis", "us-gaap:ConsolidationItemsAxis",
             "srt:RestatementAxis", "us-gaap:AdjustmentsForNewAccountingPronouncementsAxis",
             "srt:CumulativeEffectPeriodOfAdoptionAxis"}


def rel_path(accession: str) -> str:
    return f"edgar/xbrl_instances/{accession}.xml.gz"


# --------------------------------------------------------------------- fetch (non-full tiers)

def _pick_instance(names: list[str]) -> str | None:
    htm = [n for n in names if n.endswith("_htm.xml")]
    if htm:
        return htm[0]
    xml = [n for n in names if n.endswith(".xml") and not re.search(r"(_cal|_def|_lab|_pre|FilingSummary|MetaLinks)", n)
           and not re.match(r"R\d+\.xml$", n) and "primary_doc" not in n]
    return xml[0] if xml else None


def fetch_all(base: Path, cik: int, filings: list[dict], fetcher: Fetcher, since: str = "2009-06-01") -> dict:
    todo = [f for f in filings if f["form"] in PERIODIC and f["filed"] >= since and f.get("is_xbrl")
            and not (base / "raw" / rel_path(f["accession"])).exists()]
    st = {"ok": 0, "skipped": 0}
    t0 = time.monotonic()
    for i, f in enumerate(todo, 1):
        nodash = f["accession"].replace("-", "")
        try:
            idx = json.loads(fetcher.get(INDEX_URL.format(cik=cik, nodash=nodash)))
            name = _pick_instance([it["name"] for it in idx["directory"]["item"]])
            if not name:
                st["skipped"] += 1
                continue
            url = FILE_URL.format(cik=cik, nodash=nodash, name=name)
            archive.write_raw(base, rel_path(f["accession"]), fetcher.get(url), url, compress=True)
            st["ok"] += 1
        except (FetchError, KeyError, json.JSONDecodeError) as e:
            print(f"  instance {f['accession']} skipped: {e}", file=sys.stderr)
            st["skipped"] += 1
        if i % 20 == 0:
            print(f"  [{i}/{len(todo)}] {time.monotonic() - t0:.0f}s", file=sys.stderr)
    return st


# --------------------------------------------------------------------- parse

_CTX = re.compile(r"<(?:[\w-]+:)?context\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</(?:[\w-]+:)?context>", re.S)
_MEMBER = re.compile(r"<(?:[\w-]+:)?explicitMember\b[^>]*dimension=\"([^\"]+)\"[^>]*>\s*([^<\s]+)\s*<", re.S)
_TYPED = re.compile(r"<(?:[\w-]+:)?typedMember\b", re.S)
_START = re.compile(r"<(?:[\w-]+:)?startDate>\s*([\d-]{10})")
_END = re.compile(r"<(?:[\w-]+:)?endDate>\s*([\d-]{10})")
_INSTANT = re.compile(r"<(?:[\w-]+:)?instant>\s*([\d-]{10})")
_XML_FACT = re.compile(r"<(us-gaap|ifrs-full):(\w+)\b([^>]*\bcontextRef=\"([^\"]+)\"[^>]*)>([^<]*)</\1:\2>", re.S)
_IX_FACT = re.compile(r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", re.S | re.I)
_ATTR = re.compile(r"([\w:-]+)=\"([^\"]*)\"")


def contexts(text: str) -> dict[str, dict]:
    out = {}
    for cid, body in _CTX.findall(text):
        if _TYPED.search(body):
            continue
        dims = _MEMBER.findall(body)
        s, e, inst = _START.search(body), _END.search(body), _INSTANT.search(body)
        out[cid] = {"dims": dims, "start": s.group(1) if s else None,
                    "end": (e.group(1) if e else inst.group(1) if inst else None)}
    return out


def _ix_value(attrs: dict, inner: str) -> float | None:
    raw = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
    fmt = attrs.get("format", "")
    if "zero" in fmt or raw in ("-", "—", "–"):
        v = 0.0
    else:
        if "comma-decimal" in fmt or "numcommadecimal" in fmt:
            raw = raw.replace(".", "").replace(" ", "").replace(",", ".")
        else:
            raw = raw.replace(",", "").replace(" ", "")
        try:
            v = float(raw)
        except ValueError:
            return None
    v *= 10 ** int(attrs.get("scale") or 0)
    return -v if attrs.get("sign") == "-" else v


def parse(text: str, concepts: set[str] = CONCEPTS) -> list[dict]:
    """→ single-axis dimensional facts: {concept, axis, member, start, end, value}."""
    ctx = contexts(text)
    out = []

    def keep(concept, cref, value):
        c = ctx.get(cref)
        if c is None or value is None or concept not in concepts or len(c["dims"]) != 1 or not c["end"]:
            return
        axis, member = c["dims"][0]
        if axis in SKIP_AXES:
            return
        out.append({"concept": concept, "axis": axis, "member": member, "start": c["start"], "end": c["end"],
                    "value": value})

    if "ix:nonFraction" in text[:5_000_000] or "ix:nonfraction" in text[:200_000].lower():
        for attr_s, inner in _IX_FACT.findall(text):
            attrs = dict(_ATTR.findall(attr_s))
            name = attrs.get("name", "")
            if ":" not in name:
                continue
            prefix, concept = name.split(":", 1)
            if prefix not in ("us-gaap", "ifrs-full"):
                continue
            keep(concept, attrs.get("contextRef"), _ix_value(attrs, inner))
    else:
        for _prefix, concept, _attrs, cref, val in _XML_FACT.findall(text):
            try:
                keep(concept, cref, float(val.strip()))
            except ValueError:
                pass
    # the same fact is often tagged several times in one document
    uniq = {(f["concept"], f["axis"], f["member"], f["start"], f["end"]): f for f in out}
    return list(uniq.values())


def from_submission(raw: bytes) -> list[dict]:
    """Full tier: find the instance inside an archived submission (EX-101.INS or inline primary doc)."""
    docs = edgar_filings.split_documents(raw)
    ins = next((d for d in docs if d["doc_type"].upper() == "EX-101.INS"), None)
    if ins:
        return parse(edgar_filings.unwrap_xml(ins["body"]).decode("utf-8", "replace"))
    for d in docs:
        if d["kind"] == "html" and b"ix:nonFraction" in d["body"][:6_000_000]:
            return parse(d["body"].decode("utf-8", "replace"))
    return []


def label(member: str) -> str:
    """tsla:AutomotiveSalesMember → 'Automotive Sales'."""
    name = member.split(":", 1)[-1]
    name = re.sub(r"(Member|Segment)$", "", name)
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return name.strip()


AXIS_LABELS = {
    "srt:ProductOrServiceAxis": "Product / service", "us-gaap:StatementBusinessSegmentsAxis": "Business segment",
    "srt:StatementGeographicalAxis": "Geography", "us-gaap:SubsegmentsAxis": "Sub-segment",
    "srt:MajorCustomersAxis": "Major customers", "us-gaap:ProductOrServiceAxis": "Product / service",
}
