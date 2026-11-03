"""config.py — paths, identity and rate limits. One place to change them."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Everything fetched or derived lives under DATA_DIR (gitignored). Overridable so
# tests and experiments never touch the real archive.
DATA_DIR = Path(os.environ.get("MARKETS_DATA_DIR", ROOT / "data"))

COMPANIES_DIR = DATA_DIR / "companies"   # data/companies/<TICKER>/raw/...
REFERENCE_DIR = DATA_DIR / "reference"   # cross-company raw (SEC ticker map, ...)
DB_PATH = DATA_DIR / "markets.db"         # derived — rebuildable from raw
JOURNAL_DB_PATH = DATA_DIR / "journal.db" # user-authored — NOT rebuildable, back it up
REGISTRY_PATH = DATA_DIR / "companies.json"

# SEC fair-access policy: a declared User-Agent with contact info, <=10 req/s.
# Same contact Rajat already declares for Ember's EDGAR calls.
SEC_USER_AGENT = os.environ.get(
    "MARKETS_SEC_UA", "Markets personal research (https://github.com/rajatraina747/Markets)")
SEC_MIN_INTERVAL_S = 0.125  # 8 req/s ceiling, under SEC's 10

# Unofficial endpoints (Yahoo, Nasdaq) stall on default urllib UAs.
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
DEFAULT_MIN_INTERVAL_S = 0.5

SERVER_PORT = int(os.environ.get("MARKETS_PORT", "5800"))


def company_dir(ticker: str) -> Path:
    return COMPANIES_DIR / ticker.upper()


def raw_dir(ticker: str) -> Path:
    return company_dir(ticker) / "raw"
