"""text.py — filing HTML → readable plain text (for search and diffs)."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section"}
_SKIP = {"script", "style", "head", "title"}


class _Extract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0          # inside script/style/head
        self.hidden = 0        # inside display:none (inline-XBRL header)
        self.hidden_stack: list[bool] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _SKIP:
            self.skip += 1
        if tag in ("ix:header",):
            self.hidden += 1
        style = (dict(attrs).get("style") or "").replace(" ", "").lower()
        is_hidden = "display:none" in style
        self.hidden_stack.append(is_hidden)
        if is_hidden:
            self.hidden += 1
        if tag in _BLOCK:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _SKIP and self.skip:
            self.skip -= 1
        if tag == "ix:header" and self.hidden:
            self.hidden -= 1
        if self.hidden_stack:
            if self.hidden_stack.pop() and self.hidden:
                self.hidden -= 1
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br":
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip and not self.hidden:
            self.parts.append(data)


_WS = re.compile(r"[ \t ​]+")
_NL = re.compile(r"\n\s*\n+")


def html_to_text(raw: bytes | str, limit: int | None = None) -> str:
    s = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    p = _Extract()
    try:
        p.feed(s)
        p.close()
    except Exception:  # malformed markup: fall back to tag stripping
        return clean(re.sub(r"<[^>]+>", " ", html.unescape(s)), limit)
    return clean("".join(p.parts), limit)


def clean(s: str, limit: int | None = None) -> str:
    s = _WS.sub(" ", s)
    s = "\n".join(line.strip() for line in s.split("\n"))
    s = _NL.sub("\n\n", s).strip()
    return s[:limit] if limit else s


def plain_text(body: bytes, kind: str, limit: int | None = None) -> str:
    if kind == "html":
        return html_to_text(body, limit)
    s = body.decode("utf-8", "replace")
    if "<html" in s[:2000].lower() or "<p" in s[:5000].lower():
        return html_to_text(s, limit)
    return clean(s, limit)
