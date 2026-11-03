"""EDGAR full-submission archive — every document of every filing, as filed.

One request per filing fetches SEC's complete submission file
  https://www.sec.gov/Archives/edgar/data/<cik>/<acc-no-dashes>/<acc>.txt
which bundles every document (primary doc, exhibits, XBRL, graphics — binaries
uuencoded) in SGML wrappers. Stored gzipped and immutable at
  raw/edgar/filings/<YYYY>/<accession>.txt.gz
Documents are split out on demand by split_documents() (pure).
"""
from __future__ import annotations

import binascii
import re
import sys
import time
from pathlib import Path

from .. import archive
from ..net import FetchError, Fetcher

ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{acc}.txt"


def rel_path(accession: str, filed: str) -> str:
    return f"edgar/filings/{filed[:4]}/{accession}.txt.gz"


def local_path(base: Path, accession: str, filed: str) -> Path:
    return base / "raw" / rel_path(accession, filed)


def download_all(base: Path, cik: int, filings: list[dict], fetcher: Fetcher,
                 forms: set[str] | None = None, limit: int | None = None) -> dict:
    """Fetch every filing not yet archived. Resumable: existing files are skipped."""
    todo = [f for f in filings
            if (forms is None or f["form"] in forms)
            and not local_path(base, f["accession"], f["filed"]).exists()]
    if limit is not None:
        todo = todo[:limit]
    stats = {"todo": len(todo), "ok": 0, "failed": [], "bytes": 0}
    t0 = time.monotonic()
    for i, f in enumerate(todo, 1):
        acc = f["accession"]
        url = ARCHIVE_URL.format(cik=cik, nodash=acc.replace("-", ""), acc=acc)
        try:
            data = fetcher.get(url)
        except FetchError as e:
            stats["failed"].append((acc, str(e)))
            print(f"  [{i}/{len(todo)}] FAILED {f['form']} {acc}: {e}", file=sys.stderr)
            continue
        archive.write_raw(base, rel_path(acc, f["filed"]), data, url, compress=True)
        stats["ok"] += 1
        stats["bytes"] += len(data)
        if i % 25 == 0 or i == len(todo):
            el = time.monotonic() - t0
            eta = el / i * (len(todo) - i)
            print(f"  [{i}/{len(todo)}] {stats['bytes'] / 1e6:,.0f} MB  "
                  f"elapsed {el / 60:.1f}m  eta {eta / 60:.1f}m", file=sys.stderr)
    return stats


# --------------------------------------------------------------------- parsing

_DOC_RX = re.compile(rb"<DOCUMENT>(.*?)</DOCUMENT>", re.S)
_TAG_RX = {k: re.compile(rb"<" + k.encode() + rb">([^\r\n<]*)")
           for k in ("TYPE", "SEQUENCE", "FILENAME", "DESCRIPTION")}
_TEXT_RX = re.compile(rb"<TEXT>\r?\n?(.*?)</TEXT>", re.S)
_BINARY_EXT = {".jpg", ".jpeg", ".gif", ".png", ".pdf", ".zip", ".xlsx", ".xls", ".doc", ".docx"}


def _kind(filename: str, body: bytes) -> str:
    fn = filename.lower()
    ext = fn[fn.rfind("."):] if "." in fn else ""
    if ext in _BINARY_EXT or body.lstrip()[:6] == b"begin ":
        return "binary"
    if ext in (".htm", ".html"):
        return "html"
    if ext in (".xml", ".xsd") or body.lstrip()[:5] in (b"<XML>", b"<?xml"):
        return "xml"
    return "text"


def split_documents(raw: bytes, with_body: bool = True) -> list[dict]:
    """Split a full submission into documents: {seq, doc_type, filename, description, kind, bytes, body}."""
    docs = []
    for m in _DOC_RX.finditer(raw):
        block = m.group(1)
        head = block[:2000]
        meta = {}
        for k, rx in _TAG_RX.items():
            t = rx.search(head)
            meta[k] = t.group(1).decode("latin-1").strip() if t else ""
        tm = _TEXT_RX.search(block)
        body = tm.group(1) if tm else b""
        kind = _kind(meta["FILENAME"], body)
        doc = {
            "seq": int(meta["SEQUENCE"]) if meta["SEQUENCE"].isdigit() else len(docs) + 1,
            "doc_type": meta["TYPE"],
            "filename": meta["FILENAME"],
            "description": meta["DESCRIPTION"] or None,
            "kind": kind,
            "bytes": len(body),
        }
        if with_body:
            doc["body"] = body
        docs.append(doc)
    return docs


def unwrap_xml(body: bytes) -> bytes:
    """Strip the <XML>…</XML> SGML wrapper SEC puts around XML documents."""
    s = body.strip()
    if s.startswith(b"<XML>"):
        s = s[5:]
    if s.endswith(b"</XML>"):
        s = s[:-6]
    return s.strip()


def uudecode(body: bytes) -> bytes:
    """Decode a uuencoded binary document (graphics, PDFs, zips)."""
    out = bytearray()
    started = False
    for line in body.splitlines():
        if not started:
            if line.startswith(b"begin "):
                started = True
            continue
        if line.strip() in (b"end", b"`") or not line.strip():
            if line.strip() == b"end":
                break
            continue
        try:
            out += binascii.a2b_uu(line)
        except binascii.Error:
            # Some encoders pad short lines; tolerate by computing the length byte.
            n = (line[0] - 32) & 63
            out += binascii.a2b_uu(line[: ((n + 2) // 3) * 4 + 1])
    return bytes(out)


def parse_header(raw: bytes) -> dict:
    """Key fields from the <SEC-HEADER> block."""
    end = raw.find(b"</SEC-HEADER>")
    head = raw[: end if end > 0 else 20000].decode("latin-1")
    out = {}
    for key, label in (("period", "CONFORMED PERIOD OF REPORT"),
                       ("doc_count", "PUBLIC DOCUMENT COUNT"),
                       ("form", "CONFORMED SUBMISSION TYPE")):
        m = re.search(label + r":\s*(\S+)", head)
        if m:
            out[key] = m.group(1)
    m = re.search(r"<ACCEPTANCE-DATETIME>(\d{14})", head)
    if m:
        out["accepted"] = m.group(1)
    return out
