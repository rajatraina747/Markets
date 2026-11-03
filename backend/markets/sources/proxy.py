"""Proxy statements (DEF 14A) — Summary Compensation Table + Director Compensation.

Proxies are free-form HTML, so this is heuristic but layout-independent:
  1. extract every <table> as rows of cell text (spacer / "$" cells dropped)
  2. a Summary Compensation Table is a table whose header row has Salary + Total
     + (Stock|Option) and whose body has fiscal years; Director Compensation has
     "Fees Earned" + Total
  3. numeric cells in a body row map, in order, onto the header's value columns
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

from . import edgar_filings

_JUNK = re.compile(r"^[\s​ $%()*]*$")


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._stack: list[list[list[str]]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._stack[-1].append([])
        elif tag in ("td", "th") and self._stack:
            self._cell = []
        elif tag in ("br", "p", "div") and self._cell is not None:
            self._cell.append("\n")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._stack:
            txt = "".join(self._cell)
            txt = "\n".join(" ".join(x.split()) for x in txt.replace("​", "").split("\n"))
            txt = re.sub(r"\n+", "\n", txt).strip()
            if self._stack[-1]:
                self._stack[-1][-1].append(txt)
            self._cell = None
        elif tag == "table" and self._stack:
            t = self._stack.pop()
            rows = [[c for c in r if not _JUNK.match(c)] for r in t]
            rows = [r for r in rows if r]
            if rows:
                self.tables.append(rows)

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def tables(html: bytes | str) -> list[list[list[str]]]:
    p = _Tables()
    p.feed(html.decode("utf-8", "replace") if isinstance(html, bytes) else html)
    return p.tables


_ROLE = re.compile(r"\b(senior|chief|officer|president|chair|chairman|vice|director|architect|former|treasurer|secretary|"
                   r"counsel|technoking|founder|controller|svp|evp|head of|engineering|operations|finance)\b", re.I)


def _num(s: str) -> float | None:
    if re.fullmatch(r"\s*\(\s*\d{1,2}\s*\)\s*", s):  # a bare footnote marker, not a value
        return None
    s = s.replace("$", "").replace(",", "").strip()
    s = re.sub(r"\(\d\)$|\s*\(\d+\)", "", s).strip()  # footnote markers like (2)
    if s in ("—", "–", "-", "—", ""):
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


SCT_COLS = [("salary", r"salary"), ("bonus", r"bonus"), ("stock", r"stock\s+award"), ("option", r"option\s+award"),
            ("non_equity", r"non-?\s*equity"), ("pension", r"pension|deferred"), ("other", r"all\s+other"),
            ("total", r"^total")]
DIR_COLS = [("fees", r"fees"), ("stock", r"stock\s+award"), ("option", r"option\s+award"), ("other", r"all\s+other"),
            ("total", r"^total")]


def _header_map(header: list[str], spec) -> list[str | None]:
    out = []
    for h in header:
        hl = h.lower().replace("\n", " ")
        key = next((k for k, rx in spec if re.search(rx, hl)), None)
        out.append(key)
    return out


def _find_header(t: list[list[str]], must: list[str]) -> int | None:
    for i, r in enumerate(t[:6]):
        joined = " ".join(r).lower()
        if all(re.search(m, joined) for m in must):
            return i
    return None


def _assign(value_cols: list[str], nums: list[float]) -> dict:
    """Map numbers onto columns; prefer the alignment whose components sum to Total."""
    cands = [dict(zip(reversed(value_cols), reversed(nums))), dict(zip(value_cols, nums))]
    for c in cands:
        if "total" in c:
            parts = sum(v for k, v in c.items() if k != "total")
            if abs(parts - c["total"]) <= max(2.0, abs(c["total"]) * 0.01):
                return c
    return cands[0]


def parse_sct(tabs: list[list[list[str]]]) -> list[dict]:
    best: list[dict] = []
    for t in tabs:
        hi = _find_header(t, [r"salary", r"total", r"stock|option"])
        if hi is None:
            continue
        cols = [c for c in _header_map(t[hi], SCT_COLS)]
        value_cols = [c for c in cols if c]
        if "total" not in value_cols:
            continue
        rows, name = [], None
        for r in t[hi + 1:]:
            yi = next((i for i, c in enumerate(r) if re.fullmatch(r"(19|20)\d{2}", c.strip())), None)
            if yi is None:
                if r and re.search(r"[A-Za-z]{3}", r[0]) and len(r) <= 2:
                    name = r[0]
                continue
            if yi > 0 and re.search(r"[A-Za-z]{3}", r[0]):
                first = r[0].split("\n")[0]
                if name and _ROLE.search(first) and not re.match(r"^[A-Z][a-z]+\s+[A-Z]", first.split(",")[0]
                                                                 if not _ROLE.match(first) else "x"):
                    # continuation row: a title-only cell under the name — same person
                    if "\n" not in name:
                        name = name + "\n" + r[0]
                else:
                    name = r[0]
            nums = [_num(c) for c in r[yi + 1:]]
            nums = [n for n in nums if n is not None]
            if not name or len(nums) < 2:
                continue
            rec = {"name_raw": name, "fy": int(r[yi].strip()), **_assign(value_cols, nums)}
            rows.append(rec)
        if len(rows) > len(best):
            best = rows
    for r in best:
        parts = r.pop("name_raw").split("\n")
        r["name"] = re.sub(r"\(\d+\)", "", parts[0]).strip()
        r["position"] = " ".join(parts[1:]).strip() or None
        if r["position"] is None:  # "Elon Musk Chief Executive Officer" on one line
            m = re.match(r"^((?:[A-Z][a-zA-Z.'\-]+\s){1,3}[A-Z][a-zA-Z.'\-]+)\s+((?:Chief|President|Chair|Senior|SVP|EVP|Vice|General|Former|Director|Treasurer|Secretary).*)$", r["name"])
            if m:
                r["name"], r["position"] = m.group(1), m.group(2)
    prev = None
    for r in best:
        r["name"] = r["name"].replace("\ufeff", "").strip()
        if _ROLE.match(r["name"]) and prev:  # a title fragment that landed in the name column
            r["position"] = r["position"] or r["name"]
            r["name"] = prev
        prev = r["name"]
    pos: dict[str, str] = {}
    for r in best:
        if r["position"]:
            pos.setdefault(r["name"], r["position"])
    for r in best:
        r["position"] = r["position"] or pos.get(r["name"])
    return best


def parse_directors(tabs: list[list[list[str]]]) -> list[dict]:
    best: list[dict] = []
    for t in tabs:
        hi = _find_header(t, [r"fees\s+earned|fees", r"total"])
        if hi is None or "salary" in " ".join(t[hi]).lower():
            continue
        value_cols = [c for c in _header_map(t[hi], DIR_COLS) if c]
        if "total" not in value_cols:
            continue
        rows = []
        for r in t[hi + 1:]:
            if not r or not re.search(r"[A-Za-z]{3}", r[0]) or r[0].lower().startswith(("total", "name")):
                continue
            nums = [n for n in (_num(c) for c in r[1:]) if n is not None]
            if not nums:
                continue
            rec = {"name": re.sub(r"\(\d+\)", "", r[0].split("\n")[0]).strip().rstrip("."),
                   **_assign(value_cols, nums)}
            rows.append(rec)
        if len(rows) > len(best):
            best = rows
    return best


def parse(raw: bytes) -> dict:
    docs = [d for d in edgar_filings.split_documents(raw) if d["kind"] == "html"]
    if not docs:
        return {"sct": [], "directors": []}
    main = max(docs[:3], key=lambda d: d["bytes"])
    tabs = tables(main["body"])
    return {"sct": parse_sct(tabs), "directors": parse_directors(tabs)}
