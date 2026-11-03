"""statements.py — XBRL facts → standard income / balance / cash-flow lines.

Rules:
- Each standard line has a ranked list of candidate us-gaap concepts; per
  period the first candidate with a value wins (companies rename tags over time).
- Restatements: for the same (concept, start, end) the latest-*filed* value wins;
  originals stay in `facts`.
- Fiscal labels are computed from the period end + fiscal-year-end month
  (SEC's `fy` field is the filing's year, not the fact's).
- Quarterly flows: direct ~3-month facts when filed; otherwise derived by
  subtracting cumulative facts (Q4 = FY − 9M, CF quarters from YTD). Derived
  rows are flagged. Per-share and share-count lines are never derived.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Line:
    key: str
    statement: str      # IS | BS | CF
    label: str
    concepts: tuple[str, ...]
    unit: str = "USD"
    additive: bool = True


LINES: tuple[Line, ...] = (
    # Income statement
    Line("revenue", "IS", "Revenue", ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                                      "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax")),
    Line("cost_of_revenue", "IS", "Cost of revenue", ("CostOfRevenue", "CostOfGoodsAndServicesSold",
                                                      "CostOfGoodsSold")),
    Line("gross_profit", "IS", "Gross profit", ("GrossProfit",)),
    Line("rnd", "IS", "Research & development", ("ResearchAndDevelopmentExpense",)),
    Line("sga", "IS", "SG&A", ("SellingGeneralAndAdministrativeExpense",)),
    Line("operating_expenses", "IS", "Total operating expenses", ("OperatingExpenses",)),
    Line("operating_income", "IS", "Operating income", ("OperatingIncomeLoss",)),
    Line("interest_expense", "IS", "Interest expense", ("InterestExpenseNonoperating", "InterestExpense",
                                                        "InterestExpenseDebt")),
    Line("pretax_income", "IS", "Pre-tax income", (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments")),
    Line("income_tax", "IS", "Income tax", ("IncomeTaxExpenseBenefit",)),
    Line("net_income", "IS", "Net income", ("NetIncomeLoss", "NetIncomeLossAttributableToParent",
                                            "ProfitLoss")),
    Line("eps_basic", "IS", "EPS (basic)", ("EarningsPerShareBasic",), "USD/shares", False),
    Line("eps_diluted", "IS", "EPS (diluted)", ("EarningsPerShareDiluted",), "USD/shares", False),
    Line("shares_diluted", "IS", "Diluted shares (wtd avg)",
         ("WeightedAverageNumberOfDilutedSharesOutstanding",), "shares", False),
    # Balance sheet (instants)
    Line("cash", "BS", "Cash & equivalents", ("CashAndCashEquivalentsAtCarryingValue",
                                              "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")),
    Line("short_term_investments", "BS", "Short-term investments", ("ShortTermInvestments",
                                                                    "MarketableSecuritiesCurrent")),
    Line("receivables", "BS", "Accounts receivable", ("AccountsReceivableNetCurrent",)),
    Line("inventory", "BS", "Inventory", ("InventoryNet",)),
    Line("current_assets", "BS", "Total current assets", ("AssetsCurrent",)),
    Line("ppe", "BS", "PP&E (net)", (
        "PropertyPlantAndEquipmentNet",
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization")),
    Line("total_assets", "BS", "Total assets", ("Assets",)),
    Line("accounts_payable", "BS", "Accounts payable", ("AccountsPayableCurrent",)),
    Line("current_liabilities", "BS", "Total current liabilities", ("LiabilitiesCurrent",)),
    Line("debt_current", "BS", "Current debt", ("DebtCurrent", "LongTermDebtCurrent",
                                                "LongTermDebtAndCapitalLeaseObligationsCurrent")),
    Line("long_term_debt", "BS", "Long-term debt", ("LongTermDebtNoncurrent",
                                                    "LongTermDebtAndCapitalLeaseObligations",
                                                    "LongTermDebt")),
    Line("total_liabilities", "BS", "Total liabilities", ("Liabilities",)),
    Line("equity", "BS", "Shareholders' equity", ("StockholdersEquity",
                                                  "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")),
    Line("shares_outstanding", "BS", "Shares outstanding", ("CommonStockSharesOutstanding",
                                                            "EntityCommonStockSharesOutstanding"),
         "shares", False),
    # Cash flow
    Line("cfo", "CF", "Operating cash flow", ("NetCashProvidedByUsedInOperatingActivities",)),
    Line("capex", "CF", "Capital expenditure", ("PaymentsToAcquirePropertyPlantAndEquipment",
                                                "PaymentsToAcquireProductiveAssets")),
    Line("cfi", "CF", "Investing cash flow", ("NetCashProvidedByUsedInInvestingActivities",)),
    Line("cff", "CF", "Financing cash flow", ("NetCashProvidedByUsedInFinancingActivities",)),
    Line("sbc", "CF", "Stock-based comp", ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense")),
    Line("dna", "CF", "Depreciation & amortization", (
        "DepreciationAmortizationAndImpairment", "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization", "Depreciation")),
)
LINE_BY_KEY = {l.key: l for l in LINES}
# Computed after mapping: key -> (statement, label, fn(values dict) -> value|None)
DERIVED = {
    "free_cash_flow": ("CF", "Free cash flow", lambda v: v["cfo"] - v["capex"]
                       if v.get("cfo") is not None and v.get("capex") is not None else None),
}
LABELS = {l.key: l.label for l in LINES} | {k: d[1] for k, d in DERIVED.items()}
ORDER = [l.key for l in LINES] + list(DERIVED)

PERIOD_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F", "10-KT"}


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _days(start: str, end: str) -> int:
    return (_d(end) - _d(start)).days + 1


def fiscal_label(end: str, fye_mmdd: str | None) -> tuple[int, int]:
    """(fiscal year, quarter 1-4) for a period ending `end`. Tolerates 52/53-week years."""
    fye_month = int((fye_mmdd or "1231")[:2])
    d = _d(end)
    # snap to the nearest month end: early-month ends belong to the previous month
    y, m = d.year, d.month
    if d.day < 15:
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    months_after_fye = (m - fye_month) % 12        # 0 = the FYE month itself
    q = 4 if months_after_fye == 0 else (months_after_fye - 1) // 3 + 1
    fy = y if m <= fye_month else y + 1
    return fy, q


def _latest(facts: list[dict]) -> dict[tuple, dict]:
    """(concept, start, end) -> latest-filed fact among period forms."""
    best: dict[tuple, dict] = {}
    for f in facts:
        if f["form"] not in PERIOD_FORMS:
            continue
        k = (f["concept"], f["period_start"], f["period_end"])
        cur = best.get(k)
        if cur is None or (f["filed"] or "") > (cur["filed"] or ""):
            best[k] = f
    return best


def compute(facts: list[dict], fye: str | None) -> list[dict]:
    """Pure: facts rows (from edgar_xbrl.parse) → statement_lines rows (no company_id)."""
    by_concept: dict[str, list[dict]] = {}
    for f in facts:
        by_concept.setdefault(f["concept"], []).append(f)
    out: dict[tuple, dict] = {}

    for line in LINES:
        for concept in line.concepts:  # ranked: earlier concepts claim periods first
            rows = [f for f in by_concept.get(concept, []) if f["unit"] == line.unit]
            if not rows:
                continue
            latest = _latest(rows)
            if line.statement == "BS":
                for (_, start, end), f in latest.items():
                    if start is not None:
                        continue
                    _put(out, line, "instant", None, end, f, concept, False, fye)
                continue
            # duration facts: index by (start, end)
            dur = {(s, e): f for (_, s, e), f in latest.items() if s is not None}
            ends = {}
            for (s, e), f in dur.items():
                ends.setdefault(e, []).append((s, f))
            for (s, e), f in dur.items():
                n = _days(s, e)
                if 350 <= n <= 380:
                    _put(out, line, "annual", s, e, f, concept, False, fye)
                elif 80 <= n <= 100:
                    _put(out, line, "quarterly", s, e, f, concept, False, fye)
            if not line.additive:
                continue
            # derive missing quarters: cumulative(start, e) - cumulative(start, e_prev)
            for (s, e), f in dur.items():
                n = _days(s, e)
                if n < 150 or n > 380:
                    continue
                for (s2, e2), f2 in dur.items():
                    if s2 == s and 80 <= (_d(e) - _d(e2)).days <= 100:
                        q_start = (_d(e2) + timedelta(days=1)).isoformat()
                        _put(out, line, "quarterly", q_start, e,
                             dict(f, value=f["value"] - f2["value"]), concept, True, fye)
                        break

    # computed lines
    periods: dict[tuple, dict] = {}
    for k, r in out.items():
        periods.setdefault((r["period_type"], r["period_end"]), {})[r["line"]] = r
    for key, (stmt, _, fn) in DERIVED.items():
        for (ptype, end), lines in periods.items():
            vals = {lk: lr["value"] for lk, lr in lines.items()}
            v = fn(vals)
            if v is None:
                continue
            src = lines.get("cfo")
            out[(key, ptype, end)] = {
                "statement": stmt, "line": key, "period_type": ptype,
                "period_start": src["period_start"] if src else None, "period_end": end,
                "fy": src["fy"] if src else None, "fp": src["fp"] if src else None, "value": v,
                "concept": "derived", "accession": src["accession"] if src else None,
                "filed": src["filed"] if src else None, "derived": 1}
    return list(out.values())


def _put(out, line, ptype, start, end, fact, concept, derived, fye) -> None:
    key = (line.key, ptype, end)
    if key in out:  # a higher-ranked concept (or a direct fact) already claimed it
        return
    fy, q = fiscal_label(end, fye)
    out[key] = {"statement": line.statement, "line": line.key, "period_type": ptype,
                "period_start": start, "period_end": end, "fy": fy,
                "fp": "FY" if ptype == "annual" else f"Q{q}", "value": fact["value"],
                "concept": concept, "accession": fact["accession"], "filed": fact.get("filed"),
                "derived": 1 if derived else 0}
