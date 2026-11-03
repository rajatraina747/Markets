"""sections.py — split 10-K text into Items and diff them year over year.

Item headings appear twice (table of contents, then the body); for each item we
keep the longest chunk between consecutive headings, which is the body.
"""
from __future__ import annotations

import difflib
import re

ITEMS = {
    "1": "Business", "1A": "Risk Factors", "1B": "Unresolved Staff Comments", "1C": "Cybersecurity",
    "2": "Properties", "3": "Legal Proceedings", "4": "Mine Safety", "5": "Market for Equity",
    "6": "[Reserved]", "7": "MD&A", "7A": "Market Risk", "8": "Financial Statements",
    "9": "Accountant Changes", "9A": "Controls and Procedures", "9B": "Other Information",
    "9C": "Foreign Jurisdictions", "10": "Directors & Governance", "11": "Executive Compensation",
    "12": "Security Ownership", "13": "Relationships & Independence", "14": "Accountant Fees",
    "15": "Exhibits", "16": "10-K Summary",
}
_HEAD = re.compile(r"(?im)^\s*(?:part\s+[iv]+\s*[,.\-–—]?\s*)?item\s*(\d{1,2}[a-c]?)\s*[.:\-–—]?\s*(.{0,220})$")


def split_items(text: str) -> dict[str, str]:
    heads = [(m.start(), m.group(1).upper()) for m in _HEAD.finditer(text) if m.group(1).upper() in ITEMS]
    best: dict[str, str] = {}
    for i, (pos, key) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        chunk = text[pos:end].strip()
        if len(chunk) > len(best.get(key, "")):
            best[key] = chunk
    return best


def paragraphs(s: str) -> list[str]:
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n|\n(?=[A-Z•])", s)]
    return [p for p in paras if len(p) > 25 and not re.fullmatch(r"[\d\s|]+", p)]


def _words_diff(a: str, b: str) -> list[list]:
    aw, bw = a.split(), b.split()
    out: list[list] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, aw, bw, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(["=", " ".join(aw[i1:i2])])
        else:
            if i2 > i1:
                out.append(["-", " ".join(aw[i1:i2])])
            if j2 > j1:
                out.append(["+", " ".join(bw[j1:j2])])
    return out


def diff(a_text: str, b_text: str) -> dict:
    """Paragraph-level diff (a = older, b = newer) with word-level detail on changed paragraphs."""
    a, b = paragraphs(a_text), paragraphs(b_text)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    blocks: list[dict] = []
    stats = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            stats["unchanged"] += i2 - i1
            blocks.append({"op": "equal", "n": i2 - i1, "first": a[i1][:160]})
        elif op == "replace":
            # pair up similar paragraphs, the rest are pure adds/removes
            olds, news = a[i1:i2], b[j1:j2]
            for k in range(max(len(olds), len(news))):
                o = olds[k] if k < len(olds) else None
                n = news[k] if k < len(news) else None
                if o and n and difflib.SequenceMatcher(None, o, n).quick_ratio() > 0.5:
                    stats["changed"] += 1
                    blocks.append({"op": "change", "words": _words_diff(o, n)})
                else:
                    if o:
                        stats["removed"] += 1
                        blocks.append({"op": "remove", "text": o})
                    if n:
                        stats["added"] += 1
                        blocks.append({"op": "add", "text": n})
        elif op == "delete":
            stats["removed"] += i2 - i1
            blocks += [{"op": "remove", "text": p} for p in a[i1:i2]]
        elif op == "insert":
            stats["added"] += j2 - j1
            blocks += [{"op": "add", "text": p} for p in b[j1:j2]]
    stats["similarity"] = round(sm.ratio(), 4)
    stats["words_a"] = len(a_text.split())
    stats["words_b"] = len(b_text.split())
    return {"stats": stats, "blocks": blocks}
