"""News — Google News RSS (personal feed-reader use) + GDELT DOC API, archived daily.

Both only give headlines/links, which is what we store; articles stay at the source.
News text is untrusted data — never treated as instructions.
GDELT asks for at most one request per 5 s.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .. import archive
from ..net import Fetcher

GNEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
GDELT = ("https://api.gdeltproject.org/api/v2/doc/doc?query={q}&mode=artlist&format=json"
         "&maxrecords=250&timespan={span}&sort=datedesc")
SOURCE = "news"


def queries(ticker: str, name: str) -> dict[str, str]:
    short = name.replace(", Inc.", "").replace(" Inc.", "").replace(" Corporation", "").replace(",", "").strip()
    return {"gnews": f'"{short}" OR {ticker} stock when:7d',
            "gdelt": f'"{short}" sourcelang:english'}


def fetch(base: Path, ticker: str, name: str, fetcher: Fetcher) -> list[Path]:
    q = queries(ticker, name)
    paths = []
    url = GNEWS.format(q=urllib.parse.quote(q["gnews"]))
    paths.append(archive.write_snapshot(base, SOURCE, "gnews.xml", fetcher.get(url), url, compress=True))
    url = GDELT.format(q=urllib.parse.quote(q["gdelt"]), span="7d")
    time.sleep(5)
    body = fetcher.get(url)
    if body.lstrip().startswith(b"{"):
        paths.append(archive.write_snapshot(base, SOURCE, "gdelt.json", body, url, compress=True))
    return paths


def parse_gnews(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    out = []
    for it in root.iter("item"):
        src = it.find("source")
        title = (it.findtext("title") or "").strip()
        source = (src.text or "").strip() if src is not None else None
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        pub = it.findtext("pubDate")
        try:
            pub_iso = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat(timespec="minutes") if pub else None
        except (TypeError, ValueError):
            pub_iso = None
        out.append({"url": (it.findtext("link") or "").strip(), "title": title, "source": source,
                    "published": pub_iso, "tone": None, "feed": "gnews"})
    return [o for o in out if o["url"]]


def parse_gdelt(raw: bytes) -> list[dict]:
    try:
        arts = json.loads(raw).get("articles") or []
    except json.JSONDecodeError:
        return []
    out = []
    for a in arts:
        seen = a.get("seendate")  # 20261103T120000Z
        try:
            pub = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat(timespec="minutes")
        except (TypeError, ValueError):
            pub = None
        out.append({"url": a.get("url"), "title": (a.get("title") or "").strip(), "source": a.get("domain"),
                    "published": pub, "tone": None, "feed": "gdelt"})
    return [o for o in out if o["url"]]


def load_all(base: Path) -> list[dict]:
    """Every archived snapshot (news accumulates day by day — never just the latest)."""
    root = base / "raw" / SOURCE
    items: dict[str, dict] = {}
    if not root.is_dir():
        return []
    for day in sorted(p for p in root.iterdir() if p.is_dir()):
        for f in day.iterdir():
            raw = archive.read_raw(f)
            rows = parse_gnews(raw) if f.name.startswith("gnews") else parse_gdelt(raw) if f.name.startswith("gdelt") else []
            for r in rows:
                items.setdefault(r["url"], r)
    return list(items.values())
