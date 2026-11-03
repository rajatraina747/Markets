"""http.py — the only module that touches the network.

Per-host rate limiting, retries with backoff on 429/5xx/timeouts, transparent
gzip. Everything else in the codebase is pure parsing over bytes on disk.
"""
from __future__ import annotations

import gzip
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config


class FetchError(Exception):
    pass


RETRY_STATUS = {429, 500, 502, 503, 504}


class Fetcher:
    def __init__(self, retries: int = 4, timeout: float = 90.0):
        self.retries = retries
        self.timeout = timeout
        self._last: dict[str, float] = {}

    @staticmethod
    def _profile(host: str) -> tuple[str, float]:
        if host.endswith("sec.gov"):
            return config.SEC_USER_AGENT, config.SEC_MIN_INTERVAL_S
        if host.endswith("stlouisfed.org"):
            # FRED tarpits full browser UA strings (observed 2026-11-04) but serves a bare one instantly
            return "Mozilla/5.0", config.DEFAULT_MIN_INTERVAL_S
        return config.BROWSER_UA, config.DEFAULT_MIN_INTERVAL_S

    def _wait(self, host: str, interval: float) -> None:
        last = self._last.get(host)
        if last is not None:
            delay = interval - (time.monotonic() - last)
            if delay > 0:
                time.sleep(delay)
        self._last[host] = time.monotonic()

    def post_json(self, url: str, body: dict) -> bytes:
        return self.get(url, headers={"Content-Type": "application/json", "Accept": "application/json"},
                        data=json.dumps(body).encode())

    def get(self, url: str, headers: dict | None = None, data: bytes | None = None) -> bytes:
        host = urllib.parse.urlsplit(url).hostname or ""
        ua, interval = self._profile(host)
        hdrs = {"User-Agent": ua, "Accept-Encoding": "gzip"}
        hdrs.update(headers or {})
        err: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait(host, interval)
            try:
                req = urllib.request.Request(url, headers=hdrs, data=data,
                                             method="POST" if data is not None else "GET")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    return body
            except urllib.error.HTTPError as e:
                err = e
                if e.code not in RETRY_STATUS:
                    raise FetchError(f"HTTP {e.code} for {url}") from e
                # SEC throttles with 429/403-ish walls for ~10 min; back off hard.
                pause = int(e.headers.get("Retry-After") or 0) or (2 ** attempt) * 5
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                err = e
                pause = (2 ** attempt) * 3
            if attempt < self.retries:
                print(f"  retry {attempt + 1}/{self.retries} in {pause}s: {url} ({err})",
                      file=sys.stderr)
                time.sleep(pause)
        raise FetchError(f"gave up on {url}: {err}") from err
