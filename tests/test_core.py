"""Offline tests for parsers and normalizers (fixtures are trimmed real TSLA payloads)."""
from __future__ import annotations

import binascii
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent / "backend"))
os.environ.setdefault("MARKETS_DATA_DIR", tempfile.mkdtemp(prefix="markets-test-"))

from markets import archive, registry  # noqa: E402
from markets.normalize import statements, text  # noqa: E402
from markets.sources import edgar_filings, edgar_submissions, edgar_xbrl, form4, prices  # noqa: E402


class TestSubmissions(unittest.TestCase):
    def setUp(self):
        self.main = json.loads((FIX / "tsla_submissions_trim.json").read_text())

    def test_profile(self):
        p = edgar_submissions.parse_profile(self.main)
        self.assertEqual(p["cik"], 1318605)
        self.assertEqual(p["name"], "Tesla, Inc.")
        self.assertEqual(p["fiscal_year_end"], "1231")

    def test_filings_dedupe_and_order(self):
        rows = edgar_submissions.parse_filings(self.main, [self.main["filings"]["recent"]])
        self.assertEqual(len(rows), 4)  # duplicates across pages collapse
        self.assertEqual(rows, sorted(rows, key=lambda r: (r["filed"], r["accession"]), reverse=True))
        self.assertIn("10-K", {r["form"] for r in rows})


class TestXbrlAndStatements(unittest.TestCase):
    def test_parse_companyfacts(self):
        facts, concepts = edgar_xbrl.parse(json.loads((FIX / "tsla_companyfacts_trim.json").read_text()))
        self.assertTrue(facts)
        self.assertIn("NetIncomeLoss", {c["concept"] for c in concepts})
        self.assertTrue(all(isinstance(f["value"], float) for f in facts))

    def _f(self, concept, start, end, val, filed, form="10-Q", unit="USD"):
        return {"concept": concept, "unit": unit, "value": float(val), "period_start": start,
                "period_end": end, "form": form, "filed": filed, "accession": f"acc-{filed}"}

    def test_q4_derived_and_restatement(self):
        facts = [
            self._f("Revenues", "2024-01-01", "2024-03-31", 10, "2024-04-20"),
            self._f("Revenues", "2024-04-01", "2024-06-30", 20, "2024-07-20"),
            self._f("Revenues", "2024-07-01", "2024-09-30", 30, "2024-10-20"),
            self._f("Revenues", "2024-01-01", "2024-09-30", 60, "2024-10-20"),
            self._f("Revenues", "2024-01-01", "2024-12-31", 100, "2025-01-30", "10-K"),
            # restated in a later 10-K: the later filing wins
            self._f("Revenues", "2024-01-01", "2024-12-31", 101, "2026-01-30", "10-K"),
        ]
        rows = {(r["period_type"], r["period_end"]): r for r in statements.compute(facts, "1231")
                if r["line"] == "revenue"}
        self.assertEqual(rows[("annual", "2024-12-31")]["value"], 101)
        q4 = rows[("quarterly", "2024-12-31")]
        self.assertEqual(q4["value"], 101 - 60)
        self.assertEqual(q4["derived"], 1)
        self.assertEqual(q4["fp"], "Q4")
        self.assertEqual(rows[("quarterly", "2024-06-30")]["derived"], 0)

    def test_cashflow_quarters_from_ytd(self):
        facts = [
            self._f("NetCashProvidedByUsedInOperatingActivities", "2024-01-01", "2024-03-31", 5, "a"),
            self._f("NetCashProvidedByUsedInOperatingActivities", "2024-01-01", "2024-06-30", 12, "b"),
            self._f("PaymentsToAcquirePropertyPlantAndEquipment", "2024-01-01", "2024-03-31", 2, "a"),
            self._f("PaymentsToAcquirePropertyPlantAndEquipment", "2024-01-01", "2024-06-30", 5, "b"),
        ]
        rows = {(r["line"], r["period_end"]): r for r in statements.compute(facts, "1231")
                if r["period_type"] == "quarterly"}
        self.assertEqual(rows[("cfo", "2024-06-30")]["value"], 7)
        self.assertEqual(rows[("free_cash_flow", "2024-06-30")]["value"], 7 - 3)

    def test_ranked_concepts(self):
        facts = [self._f("Revenues", "2024-01-01", "2024-12-31", 100, "x", "10-K"),
                 self._f("RevenueFromContractWithCustomerExcludingAssessedTax",
                         "2024-01-01", "2024-12-31", 90, "y", "10-K")]
        r = [x for x in statements.compute(facts, "1231") if x["line"] == "revenue"][0]
        self.assertEqual((r["value"], r["concept"]), (100, "Revenues"))

    def test_eps_never_derived(self):
        facts = [self._f("EarningsPerShareDiluted", "2024-01-01", "2024-12-31", 4, "x", "10-K",
                         "USD/shares"),
                 self._f("EarningsPerShareDiluted", "2024-01-01", "2024-09-30", 3, "x", "10-Q",
                         "USD/shares")]
        q = [r for r in statements.compute(facts, "1231") if r["period_type"] == "quarterly"]
        self.assertEqual(q, [])

    def test_fiscal_label(self):
        self.assertEqual(statements.fiscal_label("2024-12-31", "1231"), (2024, 4))
        self.assertEqual(statements.fiscal_label("2024-03-31", "1231"), (2024, 1))
        # Apple-style late-September FYE, 52/53-week ends
        self.assertEqual(statements.fiscal_label("2024-09-28", "0928"), (2024, 4))
        self.assertEqual(statements.fiscal_label("2024-12-28", "0928"), (2025, 1))
        self.assertEqual(statements.fiscal_label("2023-10-01", "0930"), (2023, 4))


class TestPrices(unittest.TestCase):
    def test_parse_yahoo(self):
        p = prices.parse_yahoo((FIX / "tsla_yahoo_trim.json").read_bytes())
        self.assertEqual(p["bars"][0]["date"], "2010-06-29")
        self.assertEqual(len(p["bars"]), 10)
        self.assertEqual({s["ratio"] for s in p["splits"]}, {"5:1", "3:1"})
        self.assertEqual(p["meta"]["currency"], "USD")

    def test_schema_drift_fails_loud(self):
        with self.assertRaises(prices.PriceSchemaError):
            prices.parse_yahoo(b'{"chart": {"result": [{"meta": {}}]}}')

    def test_reconcile(self):
        a = [{"date": "2024-01-02", "close": 100.0}, {"date": "2024-01-03", "close": 110.0}]
        b = [{"date": "2024-01-02", "close": 100.2}, {"date": "2024-01-03", "close": 100.0}]
        r = prices.reconcile(a, b)
        self.assertEqual(r["shared"], 2)
        self.assertEqual([m["date"] for m in r["mismatches"]], ["2024-01-03"])

    def test_parse_nasdaq(self):
        raw = json.dumps({"data": {"tradesTable": {"rows": [
            {"date": "01/03/2024", "close": "$1,234.50", "volume": "1,000"}]}}}).encode()
        self.assertEqual(prices.parse_nasdaq(raw), [{"date": "2024-01-03", "close": 1234.5, "volume": 1000}])


class TestFilings(unittest.TestCase):
    def setUp(self):
        self.raw = (FIX / "tsla_form4_submission.txt").read_bytes()

    def test_split_and_header(self):
        docs = edgar_filings.split_documents(self.raw)
        self.assertEqual(len(docs), 1)
        self.assertEqual((docs[0]["doc_type"], docs[0]["kind"]), ("4", "xml"))
        h = edgar_filings.parse_header(self.raw)
        self.assertEqual(h["form"], "4")
        self.assertEqual(h["period"], "20260905")

    def test_form4(self):
        doc = edgar_filings.split_documents(self.raw)[0]
        p = form4.parse(edgar_filings.unwrap_xml(doc["body"]))
        self.assertEqual(p["owners"][0]["cik"], 1771340)
        self.assertIn("Taneja", p["owners"][0]["name"])
        self.assertEqual(p["owners"][0]["is_officer"], 1)
        self.assertTrue(p["txns"])
        self.assertTrue(all(t["txn_date"] for t in p["txns"] if t["table_kind"] != "holding"))

    def test_uudecode_and_binary_kind(self):
        payload = bytes(range(256)) * 3
        lines = [b"begin 644 logo.jpg"]
        for i in range(0, len(payload), 45):
            lines.append(binascii.b2a_uu(payload[i:i + 45]).rstrip(b"\n"))
        lines += [b"`", b"end"]
        body = b"\n".join(lines)
        sub = (b"<DOCUMENT>\n<TYPE>GRAPHIC\n<SEQUENCE>2\n<FILENAME>logo.jpg\n<TEXT>\n" + body +
               b"\n</TEXT>\n</DOCUMENT>")
        d = edgar_filings.split_documents(sub)[0]
        self.assertEqual(d["kind"], "binary")
        self.assertEqual(edgar_filings.uudecode(d["body"]), payload)


class TestText(unittest.TestCase):
    def test_html_to_text_skips_hidden_xbrl(self):
        html = (b"<html><head><title>x</title><style>p{}</style></head><body>"
                b"<div style='display:none'><ix:header>ctx junk</ix:header></div>"
                b"<p>Risk&nbsp;Factors</p><table><tr><td>Revenue</td><td>97,690</td></tr></table>"
                b"<script>evil()</script></body></html>")
        t = text.html_to_text(html)
        self.assertIn("Risk Factors", t)
        self.assertIn("Revenue | 97,690", t)
        self.assertNotIn("ctx junk", t)
        self.assertNotIn("evil", t)


class TestArchiveRegistry(unittest.TestCase):
    def test_snapshot_roundtrip_and_latest(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            archive.write_raw(base, "src/2024-01-01/a.json", b"old", "u")
            archive.write_raw(base, "src/2024-02-01/a.json.gz", b"new", "u", compress=True)
            p = archive.latest_snapshot(base, "src", "a.json")
            self.assertEqual(archive.read_raw(p), b"new")
            lines = (base / "manifest.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[1])["bytes"], 3)

    def test_ticker_map(self):
        m = registry.parse_ticker_map({"fields": ["cik", "name", "ticker", "exchange"],
                                       "data": [[1318605, "Tesla, Inc.", "tsla", "Nasdaq"]]})
        self.assertEqual(m["TSLA"], {"cik": 1318605, "name": "Tesla, Inc.", "exchange": "Nasdaq"})


if __name__ == "__main__":
    unittest.main()
