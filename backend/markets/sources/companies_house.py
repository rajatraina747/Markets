"""UK Companies House public data API (free key: developer.company-information.service.gov.uk).

  /company/{n}                                  profile (status, SIC, address, accounts dates)
  /company/{n}/officers                         directors & secretaries, appointed/resigned
  /company/{n}/persons-with-significant-control >25% owners / controllers
  /company/{n}/filing-history                   every filing (accounts, confirmation, changes)
Auth: HTTP Basic with the key as username. Set MARKETS_CH_KEY. Without it, UK companies
still get prices/news/macro; this source is simply skipped.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from .. import archive
from ..net import Fetcher

API = "https://api.company-information.service.gov.uk"
SOURCE = "companies_house"
DOC_URL = "https://find-and-update.company-information.service.gov.uk/company/{n}/filing-history/{tid}/document?format=pdf"


def key() -> str | None:
    return os.environ.get("MARKETS_CH_KEY") or None


def _auth() -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"{key()}:".encode()).decode()}


def _paged(fetcher: Fetcher, path: str, items_key: str = "items", page: int = 100, cap: int = 5000) -> bytes:
    items, start, total, first = [], 0, None, None
    while total is None or start < min(total, cap):
        sep = "&" if "?" in path else "?"
        body = json.loads(fetcher.get(f"{API}{path}{sep}items_per_page={page}&start_index={start}", headers=_auth()))
        first = first or body
        got = body.get(items_key) or []
        items += got
        total = body.get("total_count") or body.get("total_results") or len(got)
        if not got:
            break
        start += len(got)
    first = dict(first or {}, **{items_key: items})
    return json.dumps(first).encode()


def fetch(base: Path, number: str, fetcher: Fetcher) -> list[Path]:
    if not key():
        raise RuntimeError("MARKETS_CH_KEY not set — get a free key at developer.company-information.service.gov.uk")
    out = [archive.write_snapshot(base, SOURCE, "profile.json", fetcher.get(f"{API}/company/{number}", headers=_auth()),
                                  f"{API}/company/{number}")]
    for name, path in (("officers.json", f"/company/{number}/officers"),
                       ("psc.json", f"/company/{number}/persons-with-significant-control"),
                       ("filing_history.json", f"/company/{number}/filing-history")):
        out.append(archive.write_snapshot(base, SOURCE, name, _paged(fetcher, path), API + path))
    return out


def load(base: Path) -> dict[str, dict]:
    out = {}
    for name in ("profile", "officers", "psc", "filing_history"):
        snap = archive.latest_snapshot(base, SOURCE, f"{name}.json")
        if snap:
            out[name] = json.loads(archive.read_raw(snap))
    return out


def parse_profile(p: dict) -> dict:
    addr = p.get("registered_office_address") or {}
    return {
        "name": p.get("company_name"), "ch_number": p.get("company_number"), "status": p.get("company_status"),
        "sic": ",".join(p.get("sic_codes") or []) or None, "incorporated": p.get("date_of_creation"),
        "type": p.get("type"), "jurisdiction": p.get("jurisdiction"),
        "fiscal_year_end": "{:02d}{:02d}".format(int((p.get("accounts") or {}).get("accounting_reference_date", {}).get("month") or 12),
                                                 int((p.get("accounts") or {}).get("accounting_reference_date", {}).get("day") or 31)),
        "address": {"street1": " ".join(x for x in (addr.get("address_line_1"), addr.get("address_line_2")) if x),
                    "city": addr.get("locality"), "stateOrCountry": addr.get("country") or "UK", "zipCode": addr.get("postal_code")},
        "former_names": [{"name": n.get("name"), "from": n.get("effective_from"), "to": n.get("ceased_on")}
                         for n in p.get("previous_company_names") or []],
    }


def parse_officers(o: dict) -> list[dict]:
    out = []
    for it in o.get("items") or []:
        out.append({"name": it.get("name"), "role": it.get("officer_role"), "appointed": it.get("appointed_on"),
                    "resigned": it.get("resigned_on"), "occupation": it.get("occupation"),
                    "nationality": it.get("nationality"),
                    "officer_id": ((it.get("links") or {}).get("officer") or {}).get("appointments", "").split("/")[2]
                    if ((it.get("links") or {}).get("officer") or {}).get("appointments") else None})
    return out


def parse_psc(p: dict) -> list[dict]:
    return [{"name": it.get("name"), "kind": it.get("kind"), "natures": ",".join(it.get("natures_of_control") or []),
             "notified": it.get("notified_on"), "ceased": it.get("ceased_on")} for it in p.get("items") or []]


def parse_filings(f: dict, number: str) -> list[dict]:
    out = []
    for it in f.get("items") or []:
        tid = it.get("transaction_id")
        out.append({"accession": f"CH-{tid}", "form": (it.get("type") or "?"), "filed": it.get("date"),
                    "report_date": (it.get("description_values") or {}).get("made_up_date"),
                    "category": it.get("category"), "description": (it.get("description") or "").replace("-", " "),
                    "url": DOC_URL.format(n=number, tid=tid) if tid else None})
    return out
