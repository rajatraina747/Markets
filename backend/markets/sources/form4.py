"""Forms 3/4/5 — insider ownership XML (inside the archived full submission).

parse(xml_bytes) → {form, period, owners[{cik,name,is_director,is_officer,
is_ten_pct,is_other,title}], txns[...]} — pure, stdlib ElementTree.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

CODE_LABELS = {
    "P": "Open-market buy", "S": "Open-market sale", "A": "Grant/award", "M": "Option exercise",
    "F": "Tax withholding", "G": "Gift", "C": "Conversion", "D": "Disposition to issuer",
    "X": "Option exercise (in-the-money)", "J": "Other", "W": "Will/inheritance",
    "I": "Discretionary", "K": "Equity swap", "V": "Voluntary report", "E": "Expiration (short)",
    "H": "Expiration (long)", "O": "Exercise (out-of-the-money)", "U": "Tender disposition",
    "Z": "Voting trust", "L": "Small acquisition",
}


def _txt(el, path: str) -> str | None:
    if el is None:
        return None
    n = el.find(path)
    if n is None:
        return None
    v = n.find("value")
    s = (v.text if v is not None else n.text) or ""
    s = s.strip()
    return s or None


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _flag(s: str | None) -> int:
    return 1 if (s or "").strip().lower() in ("1", "true") else 0


def _footnotes(el) -> str | None:
    ids = sorted({f.get("id") for f in el.iter("footnoteId") if f.get("id")})
    return ",".join(ids) or None


def parse(xml: bytes) -> dict:
    root = ET.fromstring(xml)
    out = {"form": _txt(root, "documentType") or root.findtext("documentType"),
           "period": root.findtext("periodOfReport"),
           "aff_10b5_1": _flag(root.findtext("aff10b5One")),
           "owners": [], "txns": [], "footnotes": {}}
    for ro in root.findall("reportingOwner"):
        rid, rel = ro.find("reportingOwnerId"), ro.find("reportingOwnerRelationship")
        cik = (rid.findtext("rptOwnerCik") or "").strip() if rid is not None else ""
        out["owners"].append({
            "cik": int(cik) if cik.isdigit() else None,
            "name": ((rid.findtext("rptOwnerName") if rid is not None else "") or "").strip(),
            "is_director": _flag(rel.findtext("isDirector")) if rel is not None else 0,
            "is_officer": _flag(rel.findtext("isOfficer")) if rel is not None else 0,
            "is_ten_pct": _flag(rel.findtext("isTenPercentOwner")) if rel is not None else 0,
            "is_other": _flag(rel.findtext("isOther")) if rel is not None else 0,
            "title": ((rel.findtext("officerTitle") or rel.findtext("otherText") or "")
                      .strip() or None) if rel is not None else None,
        })
    for fn in root.iter("footnote"):
        out["footnotes"][fn.get("id")] = " ".join("".join(fn.itertext()).split())
    for table_kind, table, rows in (
            ("nonDerivative", "nonDerivativeTable", ("nonDerivativeTransaction", "nonDerivativeHolding")),
            ("derivative", "derivativeTable", ("derivativeTransaction", "derivativeHolding"))):
        t = root.find(table)
        if t is None:
            continue
        for tag in rows:
            for r in t.findall(tag):
                holding = tag.endswith("Holding")
                coding = r.find("transactionCoding")
                amts = r.find("transactionAmounts")
                post = r.find("postTransactionAmounts")
                own = r.find("ownershipNature")
                out["txns"].append({
                    "table_kind": "holding" if holding else table_kind,
                    "security": _txt(r, "securityTitle"),
                    "txn_date": _txt(r, "transactionDate"),
                    "code": (coding.findtext("transactionCode") or "").strip() or None
                    if coding is not None else None,
                    "acq_disp": _txt(amts, "transactionAcquiredDisposedCode"),
                    "shares": _num(_txt(amts, "transactionShares")),
                    "price": _num(_txt(amts, "transactionPricePerShare")),
                    "shares_after": _num(_txt(post, "sharesOwnedFollowingTransaction")),
                    "ownership": _txt(own, "directOrIndirectOwnership"),
                    "nature": _txt(own, "natureOfOwnership"),
                    "footnotes": _footnotes(r),
                })
    return out
