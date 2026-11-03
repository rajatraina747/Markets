"""Schedules 13D / 13G — holders of >5% (beneficial ownership).

Three generations of format, all handled by parse():
  - since Dec 2024: structured XML (primary_doc.xml, schedule13g / schedule13d namespaces)
  - HTML cover pages (2000s–2024)
  - plain-text cover pages
Filer identity comes from the SEC header's FILED BY block.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..normalize.text import plain_text
from . import edgar_filings

FORMS = {"SC 13G", "SC 13G/A", "SC 13D", "SC 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A",
         "SCHEDULE 13D", "SCHEDULE 13D/A"}


def header_filer(raw: bytes) -> tuple[str | None, int | None]:
    end = raw.find(b"</SEC-HEADER>")
    head = raw[: end if end > 0 else 30000].decode("latin-1")
    m = re.search(r"FILED BY:\s*\n(?:.*\n){0,3}?\s*COMPANY CONFORMED NAME:\s*(.+)\n\s*CENTRAL INDEX KEY:\s*(\d+)", head)
    if m:
        return m.group(1).strip(), int(m.group(2))
    return None, None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _num(s: str | None) -> float | None:
    if not s:
        return None
    s = s.replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_xml(xml: bytes) -> list[dict]:
    """One row per reporting-person block (any element whose child is reportingPersonName)."""
    root = ET.fromstring(xml)
    event = None
    for el in root.iter():
        if _local(el.tag) in ("eventDateRequiresFilingThisStatement", "dateOfEvent") and (el.text or "").strip():
            t = el.text.strip()
            if "/" in t:
                m, d, y = t.split("/")
                event = f"{y}-{m}-{d}"
            else:
                event = t
            break
    persons: list[dict] = []
    for block in root.iter():
        kids = {_local(k.tag): k for k in block}
        if "reportingPersonName" not in kids:
            continue
        rec = {"name": (kids["reportingPersonName"].text or "").strip(), "shares": None, "percent": None,
               "event_date": event}
        for el in block.iter():
            name, txt = _local(el.tag), (el.text or "").strip()
            if not txt:
                continue
            if name in ("reportingPersonBeneficiallyOwnedAggregateNumberOfShares", "aggregateAmountOwned"):
                rec["shares"] = _num(txt)
            elif name in ("classPercent", "percentOfClass"):
                rec["percent"] = _num(txt)
        # The items section repeats reportingPersonName with no stake — only cover-page blocks count.
        if rec["name"] and (rec["shares"] is not None or rec["percent"] is not None):
            persons.append(rec)
    return persons


_NAME_RX = re.compile(r"names?\s+of\s+reporting\s+persons?[^\n]*?[.:]?\s*(?:\n|\|)?\s*(?:I\.?R\.?S\.?[^\n]*\n)?\s*([^\n|]{3,120})", re.I)
_AGG_RX = re.compile(r"aggregate\s+amount\s+beneficially\s+owned\s+by\s+each\s+reporting\s+person[^0-9]{0,80}?([\d,]{3,})", re.I | re.S)
_PCT_RX = re.compile(r"percent\s+of\s+class\s+represented\s+by\s+amount\s+in\s+row\s*\(?\s*\d+\s*\)?[^0-9]{0,80}?(\d{1,3}(?:\.\d+)?)\s*%", re.I | re.S)
_EVENT_RX = re.compile(r"([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})\s*[-\s|]*\(Date of Event", re.S)
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                                         "oct", "nov", "dec"], 1)}


def _event(text: str) -> str | None:
    m = _EVENT_RX.search(text)
    if not m:
        return None
    mm = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2}),\s+(\d{4})", m.group(1))
    mon = _MONTHS.get(mm.group(1)[:3].lower()) if mm else None
    return f"{mm.group(3)}-{mon:02d}-{int(mm.group(2)):02d}" if mon else None


def parse_text(text: str) -> list[dict]:
    """Cover-page extraction from HTML/text filings: first reporting person's row (9)/(11)."""
    names = [re.sub(r"\s*[-–]?\s*\d{2}-\d{7}\s*$", "", n.strip(" .:-|")) for n in _NAME_RX.findall(text)]
    aggs = [_num(a) for a in _AGG_RX.findall(text)]
    pcts = [_num(p) for p in _PCT_RX.findall(text)]
    event = _event(text)
    out = []
    for i in range(max(len(aggs), len(pcts))):
        out.append({"name": names[i] if i < len(names) else (names[0] if names else None),
                    "shares": aggs[i] if i < len(aggs) else None,
                    "percent": pcts[i] if i < len(pcts) else None, "event_date": event})
    return out


def parse(raw: bytes) -> dict:
    filer, filer_cik = header_filer(raw)
    docs = edgar_filings.split_documents(raw)
    persons: list[dict] = []
    for d in docs:
        if d["kind"] == "xml" and b"schedule13" in d["body"][:3000].lower():
            try:
                persons = parse_xml(edgar_filings.unwrap_xml(d["body"]))
            except ET.ParseError:
                persons = []
            break
    if not persons:
        main = next((d for d in docs if d["kind"] in ("html", "text")), None)
        if main:
            persons = parse_text(plain_text(main["body"], main["kind"], 400_000))
    return {"filer": filer, "filer_cik": filer_cik, "persons": persons}
