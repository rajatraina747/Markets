"""server.py — stdlib JSON API over markets.db + static frontend (frontend/dist).

Read-only: the API never writes markets.db. Filing documents are streamed out of
the raw archive and served under a strict sandbox CSP — they are untrusted HTML.
"""
from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from .. import archive, config, db
from ..sources import edgar_filings
from . import queries

DIST = config.ROOT / "frontend" / "dist"
DOC_CSP = ("sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
           "font-src 'none'; frame-ancestors 'self'")

ROUTES: list[tuple[re.Pattern, callable]] = []


def route(pattern: str):
    rx = re.compile("^" + pattern + "$")

    def deco(fn):
        ROUTES.append((rx, fn))
        return fn
    return deco


_local = threading.local()


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = db.connect(readonly=True)
        _local.conn = c
    return c


class NotFound(Exception):
    pass


def _cid(ticker: str) -> int:
    cid = db.company_id(conn(), ticker)
    if cid is None:
        raise NotFound(f"{ticker} not built")
    return cid


# ------------------------------------------------------------------ routes

@route(r"/api/companies")
def api_companies(q):
    return [dict(r) for r in conn().execute(
        "SELECT c.ticker, c.name, c.exchange, m.price, m.prev_close FROM companies c "
        "LEFT JOIN quote_meta m ON m.company_id=c.id ORDER BY c.ticker")]


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/overview")
def api_overview(q, t):
    return queries.overview(conn(), _cid(t))


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/prices")
def api_prices(q, t):
    rows = conn().execute("SELECT date, open, high, low, close, volume, adj_close FROM prices_daily "
                          "WHERE company_id=? AND date>=? ORDER BY date",
                          (_cid(t), q.get("from", "0000"))).fetchall()
    return {"cols": ["date", "open", "high", "low", "close", "volume", "adj_close"],
            "rows": [list(r) for r in rows]}


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/events")
def api_events(q, t):
    imp = int(q.get("min_importance", 1))
    return [dict(r) for r in conn().execute(
        "SELECT date, kind, title, detail, accession, importance FROM events WHERE company_id=? "
        "AND importance>=? ORDER BY date DESC", (_cid(t), imp))]


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/statements")
def api_statements(q, t):
    return queries.statements_table(conn(), _cid(t), q.get("period", "annual"))


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/facts/(?P<concept>[A-Za-z0-9_]+)")
def api_facts(q, t, concept):
    rows = conn().execute("SELECT taxonomy, unit, value, period_start, period_end, form, filed, accession, "
                          "frame FROM facts WHERE company_id=? AND concept=? ORDER BY period_end, filed",
                          (_cid(t), concept)).fetchall()
    meta = conn().execute("SELECT label, description FROM concepts WHERE company_id=? AND concept=?",
                          (_cid(t), concept)).fetchone()
    return {"concept": concept, "label": meta["label"] if meta else None,
            "description": meta["description"] if meta else None, "facts": [dict(r) for r in rows]}


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/filings")
def api_filings(q, t):
    return queries.filings(conn(), _cid(t), q)


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/filings/(?P<acc>[0-9\-]+)")
def api_filing(q, t, acc):
    cid = _cid(t)
    f = conn().execute("SELECT * FROM filings WHERE company_id=? AND accession=?", (cid, acc)).fetchone()
    if not f:
        raise NotFound(acc)
    docs = [dict(r) for r in conn().execute(
        "SELECT seq, doc_type, filename, description, kind, bytes FROM filing_documents "
        "WHERE company_id=? AND accession=? ORDER BY seq", (cid, acc))]
    cik = conn().execute("SELECT cik FROM companies WHERE id=?", (cid,)).fetchone()[0]
    return {"filing": dict(f), "documents": docs,
            "sec_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.htm"}


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/search")
def api_search(q, t):
    return queries.search(conn(), _cid(t), q)


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/text/(?P<acc>[0-9\-]+)/(?P<seq>\d+)")
def api_text(q, t, acc, seq):
    r = conn().execute("SELECT body FROM filing_text WHERE company_id=? AND accession=? AND seq=?",
                       (_cid(t), acc, int(seq))).fetchone()
    if not r:
        raise NotFound("no text")
    return {"text": r["body"]}


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/insiders")
def api_insiders(q, t):
    return queries.insiders(conn(), _cid(t))


@route(r"/api/c/(?P<t>[A-Za-z.\-]+)/insiders/txns")
def api_insider_txns(q, t):
    return queries.insider_txns(conn(), _cid(t), q)


# ------------------------------------------------------------------ server

class Handler(BaseHTTPRequestHandler):
    server_version = "Markets/0.1"

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            return
        sys.stderr.write("  " + fmt % args + "\n")

    def _send(self, status, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj, separators=(",", ":"), default=str).encode(),
                   "application/json", {"Cache-Control": "no-store"})

    def do_GET(self):  # noqa: N802
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        q = {k: v[-1] for k, v in parse_qs(parts.query).items()}
        try:
            m = re.match(r"^/api/c/([A-Za-z.\-]+)/files/([0-9\-]+)/([^/]+)$", path)
            if m:
                return self._filing_file(*m.groups())
            for rx, fn in ROUTES:
                mm = rx.match(path)
                if mm:
                    return self._json(fn(q, **mm.groupdict()))
            if path.startswith("/api/"):
                return self._json({"error": "not found"}, 404)
            return self._static(path)
        except NotFound as e:
            self._json({"error": str(e)}, 404)
        except sqlite3.OperationalError as e:
            self._json({"error": f"database not ready: {e} — run ./markets update"}, 503)
        except Exception as e:  # pragma: no cover
            import traceback
            traceback.print_exc()
            self._json({"error": repr(e)}, 500)

    def _filing_file(self, ticker, acc, filename):
        """Serve one document out of an archived submission (relative <img> links resolve here)."""
        cid = _cid(ticker)
        f = conn().execute("SELECT raw_path FROM filings WHERE company_id=? AND accession=?",
                           (cid, acc)).fetchone()
        if not f or not f["raw_path"]:
            raise NotFound("filing not archived")
        raw = archive.read_raw(config.company_dir(ticker) / f["raw_path"])
        for d in edgar_filings.split_documents(raw):
            if d["filename"] != filename:
                continue
            body = d["body"]
            if d["kind"] == "binary":
                body = edgar_filings.uudecode(body)
            elif d["kind"] == "xml":
                body = edgar_filings.unwrap_xml(body)
            ctype = mimetypes.guess_type(filename)[0] or "text/plain"
            if ctype.startswith("text/") or ctype.endswith("xml"):
                ctype += "; charset=utf-8" if b"utf-8" in body[:2000].lower() else "; charset=windows-1252"
            return self._send(200, body, ctype, {"Content-Security-Policy": DOC_CSP,
                                                 "Cache-Control": "max-age=86400"})
        raise NotFound(filename)

    def _static(self, path):
        if not DIST.is_dir():
            return self._send(503, b"Frontend not built: cd frontend && npm install && npm run build",
                              "text/plain")
        rel = path.lstrip("/") or "index.html"
        target = (DIST / rel).resolve()
        if not str(target).startswith(str(DIST.resolve())) or not target.is_file():
            target = DIST / "index.html"  # SPA fallback
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        cache = "no-cache" if target.name == "index.html" else "max-age=31536000, immutable"
        self._send(200, target.read_bytes(), ctype, {"Cache-Control": cache})


def serve(port: int = config.SERVER_PORT, open_browser: bool = False, host: str = "127.0.0.1"):
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://localhost:{port}"
    print(f"Markets on {url}  (ctrl-c to stop)", file=sys.stderr)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
