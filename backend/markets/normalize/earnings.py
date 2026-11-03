"""earnings.py — every results release (8-K item 2.02) with the market's reaction.

No consensus estimates exist for free, so the market's own reaction is the "beat/miss" proxy:
  base   = last close before the news (prior session for before-open/intraday, same day after close)
  react  = first session that could trade on it
  gap / day / +5d / +20d returns, excess vs SPY, reaction-day volume vs the 20-day average
Classification: a 2.02 filed ≥10 days after a quarter end is an earnings release; earlier ones
(e.g. Tesla's production & deliveries report two days after quarter end) are operational updates.
Forward-looking sentences are pulled from the release exhibit (EX-99.1) when it's archived.
"""
from __future__ import annotations

import bisect
import json
import re
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover — tz database missing
    ET = timezone(timedelta(hours=-5))

METRIC_LINES = ("revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "free_cash_flow", "cfo")
_GUIDE = re.compile(r"\b(outlook|guidance|we expect|we anticipate|expected to|we plan|we intend|on track|forecast|"
                    r"we believe .{0,40}(will|should)|target(?:ing)?|reaffirm|raise[sd]? (?:our|the|full)|"
                    r"lower(?:ed|ing)? (?:our|the|full)|next quarter|full[- ]year|2\d{3} (?:volume|deliveries|production))\b", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")


def timing_of(accepted_iso: str | None) -> tuple[str | None, str | None]:
    """(timing, accepted ET iso). SEC acceptanceDateTime is UTC."""
    if not accepted_iso:
        return None, None
    try:
        t = datetime.fromisoformat(accepted_iso.replace("Z", "+00:00")).astimezone(ET)
    except ValueError:
        return None, None
    hm = t.hour * 60 + t.minute
    timing = "bmo" if hm < 9 * 60 + 30 else "amc" if hm >= 16 * 60 else "intraday"
    return timing, t.isoformat(timespec="minutes")


def guidance_sentences(text: str, limit: int = 8) -> list[str]:
    """Forward-looking sentences, preferring an 'Outlook' section if the release has one."""
    if not text:
        return []
    m = re.search(r"\n\s*(outlook|guidance|looking ahead)\s*\n", text, re.I)
    scope = text[m.start(): m.start() + 6000] if m else text
    out, seen = [], set()
    for para in scope.split("\n"):
        for s in _SENT.split(para):
            s = " ".join(s.split())
            if len(re.findall(r"(?<![\d.,$])\d{2}(?![\d.,%])", s)) >= 4:  # a table-of-contents line
                continue
            if 40 <= len(s) <= 420 and _GUIDE.search(s) and not re.search(r"forward-looking statements|safe harbor|"
                                                                          r"actual results (?:may|could)|risks and uncertainties", s, re.I):
                key = s[:80].lower()
                if key not in seen:
                    seen.add(key)
                    out.append(s)
            if len(out) >= limit:
                return out
    return out


def _ret(a: float | None, b: float | None) -> float | None:
    return (b / a - 1) if a and b else None


def compute(filings: list[dict], bars: list[dict], quarters: dict[str, dict], spy: list[dict],
            texts: dict[str, str], fye: str | None) -> list[dict]:
    """filings: 2.02 8-Ks {accession, filed, accepted}; bars: daily {date, open, close, volume};
    quarters: period_end → {line: value} (quarterly statement lines); texts: accession → EX-99.1 text."""
    from .statements import fiscal_label
    dates = [b["date"] for b in bars]
    spy_close = {b["date"]: b["close"] for b in spy}
    q_ends = sorted(quarters)
    out = []
    for f in sorted(filings, key=lambda x: x["filed"]):
        timing, acc_et = timing_of(f.get("accepted"))
        news_day = (acc_et or f["filed"])[:10]
        i = bisect.bisect_left(dates, news_day)           # first session on/after the news day
        if timing == "amc" and i < len(dates) and dates[i] == news_day:
            base_i, react_i = i, i + 1      # after the close: that day's close is the base
        else:
            base_i, react_i = i - 1, i      # before open / intraday / non-trading day
        if base_i < 0 or react_i >= len(dates):
            react_i = None
        # quarter covered: the latest quarter end before the filing
        qi = bisect.bisect_left(q_ends, news_day) - 1
        pe = q_ends[qi] if qi >= 0 else None
        days_after = (date.fromisoformat(news_day) - date.fromisoformat(pe)).days if pe else None
        kind = "earnings" if days_after is not None and 10 <= days_after <= 75 else "update"
        row = {"accession": f["accession"], "filed": f["filed"], "accepted_et": acc_et, "timing": timing,
               "kind": kind, "period_end": pe if kind == "earnings" else None, "fy": None, "fp": None,
               "base_date": None, "base_close": None, "react_date": None, "gap": None, "day": None, "d5": None,
               "d20": None, "excess_day": None, "excess_d5": None, "vol_ratio": None, "metrics": None,
               "guidance": json.dumps(guidance_sentences(texts.get(f["accession"], "")))}
        if pe and kind == "earnings":
            row["fy"], q = fiscal_label(pe, fye)
            row["fp"] = f"Q{q}"
            row["metrics"] = json.dumps(_metrics(quarters, q_ends, pe))
        if react_i is not None:
            b0, r = bars[base_i], bars[react_i]
            row.update(base_date=b0["date"], base_close=b0["close"], react_date=r["date"],
                       gap=_ret(b0["close"], r["open"]), day=_ret(b0["close"], r["close"]))
            if react_i + 4 < len(bars):
                row["d5"] = _ret(b0["close"], bars[react_i + 4]["close"])
            if react_i + 19 < len(bars):
                row["d20"] = _ret(b0["close"], bars[react_i + 19]["close"])
            vols = [b["volume"] for b in bars[max(0, base_i - 19): base_i + 1] if b["volume"]]
            if vols and r["volume"]:
                row["vol_ratio"] = r["volume"] / (sum(vols) / len(vols))
            s0, s1 = spy_close.get(b0["date"]), spy_close.get(r["date"])
            if row["day"] is not None and s0 and s1:
                row["excess_day"] = row["day"] - (s1 / s0 - 1)
            if row["d5"] is not None and s0 and react_i + 4 < len(bars):
                s5 = spy_close.get(bars[react_i + 4]["date"])
                if s5:
                    row["excess_d5"] = row["d5"] - (s5 / s0 - 1)
        out.append(row)
    return out


def _metrics(quarters: dict, q_ends: list[str], pe: str) -> dict:
    cur = quarters.get(pe, {})
    i = q_ends.index(pe)
    prev = quarters.get(q_ends[i - 1], {}) if i > 0 else {}
    yago_end = next((e for e in q_ends if abs((date.fromisoformat(e) - date.fromisoformat(pe)).days + 365) <= 10), None)
    yago = quarters.get(yago_end, {}) if yago_end else {}

    def margin(d, k):
        return d[k] / d["revenue"] if d.get(k) is not None and d.get("revenue") else None

    out = {}
    for k in METRIC_LINES:
        v = cur.get(k)
        out[k] = {"v": v, "yoy": _ret(yago.get(k), v) if k != "eps_diluted" or (yago.get(k) or 0) > 0 else None,
                  "qoq": _ret(prev.get(k), v), "yago": yago.get(k)}
        if k in ("net_income", "operating_income", "free_cash_flow", "eps_diluted") and (yago.get(k) or 0) <= 0:
            out[k]["yoy"] = None  # growth off a loss is meaningless
    for k in ("gross_profit", "operating_income", "net_income"):
        out[k + "_margin"] = {"v": margin(cur, k), "yago": margin(yago, k)}
    return out
