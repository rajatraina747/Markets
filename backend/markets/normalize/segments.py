"""segments.py — dimensional XBRL facts → clean segment / product / geography series.

Same rules as statements.py: latest filing wins on restatements; quarters are direct 3-month
facts or derived from cumulative ones (Q4 = FY − 9M, flagged). Additionally each period's
members are checked for subtotals (a member equal to the sum of ≥2 others), so charts can stack
leaves without double counting.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from itertools import combinations

from ..sources.xbrl_instance import label
from .statements import fiscal_label

KEEP_AXES = {"srt:ProductOrServiceAxis", "us-gaap:ProductOrServiceAxis", "us-gaap:StatementBusinessSegmentsAxis",
             "srt:StatementGeographicalAxis", "us-gaap:StatementGeographicalAxis", "us-gaap:SubsegmentsAxis",
             "srt:MajorCustomersAxis"}
# one revenue series per company, whichever concept it tags segments with
REVENUE = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
           "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet")
COUNTRIES = {"US": "United States", "CN": "China", "NO": "Norway", "DE": "Germany", "GB": "United Kingdom",
             "CA": "Canada", "JP": "Japan", "KR": "South Korea", "NL": "Netherlands", "FR": "France",
             "MX": "Mexico", "BR": "Brazil", "IN": "India", "AU": "Australia", "TW": "Taiwan", "CH": "Switzerland",
             "IE": "Ireland", "SG": "Singapore", "HK": "Hong Kong", "IT": "Italy", "ES": "Spain", "SE": "Sweden"}


def member_label(member: str) -> str:
    code = member.split(":", 1)[-1]
    if member.startswith("country:") or (len(code) == 2 and code.isupper()):
        return COUNTRIES.get(code, code)
    return label(member)


def _days(s: str, e: str) -> int:
    return (date.fromisoformat(e) - date.fromisoformat(s)).days + 1


AXIS_ALIAS = {"us-gaap:StatementGeographicalAxis": "srt:StatementGeographicalAxis",
              "us-gaap:ProductOrServiceAxis": "srt:ProductOrServiceAxis"}
METRIC_ALIAS = {"CostOfGoodsAndServicesSold": "CostOfRevenue", "SegmentReportingInformationOperatingIncomeLoss":
                "OperatingIncomeLoss"}


def compute(facts: list[dict], fye: str | None) -> list[dict]:
    """facts: {concept, axis, member, start, end, value, filed, accession} → segment_lines rows."""
    facts = [dict(f, axis=AXIS_ALIAS.get(f["axis"], f["axis"])) for f in facts if f["axis"] in KEEP_AXES]
    # normalize revenue concepts into one 'revenue' series (ranked like statements)
    by_rank = {c: i for i, c in enumerate(REVENUE)}
    best: dict[tuple, dict] = {}
    for f in facts:
        metric = "revenue" if f["concept"] in by_rank else METRIC_ALIAS.get(f["concept"], f["concept"])
        rank = by_rank.get(f["concept"], 0)
        k = (metric, f["axis"], f["member"], f["start"], f["end"])
        cur = best.get(k)
        if cur is None or (rank, -_ord(f["filed"])) < (cur["_rank"], -_ord(cur["filed"])):
            best[k] = dict(f, metric=metric, _rank=rank)
    rows: dict[tuple, dict] = {}
    series: dict[tuple, dict[tuple, dict]] = {}
    for (metric, axis, member, s, e), f in best.items():
        series.setdefault((metric, axis, member), {})[(s, e)] = f
    for (metric, axis, member), pts in series.items():
        for (s, e), f in pts.items():
            if s is None:
                ptype = "instant"
            else:
                n = _days(s, e)
                ptype = "annual" if 350 <= n <= 380 else "quarterly" if 80 <= n <= 100 else None
            if ptype:
                _put(rows, metric, axis, member, ptype, s, e, f, False, fye)
        # derive quarters from cumulative periods sharing a start date
        for (s, e), f in pts.items():
            if s is None or not 150 <= _days(s, e) <= 380:
                continue
            for (s2, e2), f2 in pts.items():
                if s2 == s and 80 <= (date.fromisoformat(e) - date.fromisoformat(e2)).days <= 100:
                    q_start = (date.fromisoformat(e2) + timedelta(days=1)).isoformat()
                    _put(rows, metric, axis, member, "quarterly", q_start, e,
                         dict(f, value=f["value"] - f2["value"]), True, fye)
                    break
    rows = _latest_classification(rows)
    _flag_subtotals(rows)
    return list(rows.values())


def _latest_classification(rows: dict) -> dict:
    """Companies re-classify members over time (Tesla's 'Automobiles' → 'Automotive sales'). Mixing
    filings double counts, so for each (metric, axis, period) keep only the members reported by the
    newest filing that covered that period — one consistent classification per period."""
    newest: dict[tuple, str] = {}
    for r in rows.values():
        k = (r["metric"], r["axis"], r["period_type"], r["period_end"])
        newest[k] = max(newest.get(k, ""), r["filed"] or "")
    return {k: r for k, r in rows.items()
            if (r["filed"] or "") == newest[(r["metric"], r["axis"], r["period_type"], r["period_end"])]}


def _ord(s: str | None) -> int:
    return int((s or "0").replace("-", "")[:8] or 0)


def _put(rows, metric, axis, member, ptype, start, end, f, derived, fye) -> None:
    k = (metric, axis, member, ptype, end)
    if k in rows and not rows[k]["derived"]:
        return
    if k in rows and derived:
        return
    fy, q = fiscal_label(end, fye)
    rows[k] = {"metric": metric, "axis": axis, "member": member, "label": member_label(member), "period_type": ptype,
               "period_start": start, "period_end": end, "fy": fy, "fp": "FY" if ptype == "annual" else f"Q{q}",
               "value": f["value"], "filed": f.get("filed"), "accession": f.get("accession"),
               "derived": 1 if derived else 0, "is_subtotal": 0}


def _flag_subtotals(rows: dict) -> None:
    groups: dict[tuple, list[dict]] = {}
    for r in rows.values():
        groups.setdefault((r["metric"], r["axis"], r["period_type"], r["period_end"]), []).append(r)
    for members in groups.values():
        if len(members) < 3 or len(members) > 16:
            continue
        for m in members:
            if m["axis"].endswith("ProductOrServiceAxis") and re.search(r"segment", m["member"], re.I):
                m["is_subtotal"] = 1  # a business segment tagged on the product axis rolls up products
                continue
            others = [o["value"] for o in members if o is not m and abs(o["value"]) < abs(m["value"])]
            tol = max(abs(m["value"]) * 0.002, 1.0)
            found = False
            for k in range(2, min(len(others), 6) + 1):
                for combo in combinations(others, k):
                    if abs(sum(combo) - m["value"]) <= tol:
                        found = True
                        break
                if found:
                    break
            m["is_subtotal"] = 1 if found else 0
