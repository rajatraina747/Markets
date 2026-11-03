"""Offline tests for proxy tables, 13F data sets, macro CSVs, partial bars, news names."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
os.environ.setdefault("MARKETS_DATA_DIR", tempfile.mkdtemp(prefix="markets-test-"))

from markets.sources import companies_house, macro, news, prices, proxy, sec_13f  # noqa: E402

SCT_HTML = """<table>
<tr><td>Name and Principal Position</td><td>Year</td><td>Salary ($)</td><td>Bonus ($)</td><td>Stock Awards ($)</td>
<td>Option Awards ($)</td><td>All Other Compensation ($)</td><td>Total ($)</td></tr>
<tr><td>Elon Musk</td><td>2018</td><td>$</td><td>0</td><td>—</td><td>2,283,988,504</td><td>—</td><td>56,380</td><td>2,284,044,884</td></tr>
<tr><td>Chief Executive Officer</td><td>2017</td><td>49,920</td><td>—</td><td>—</td><td>—</td><td>—</td><td>49,920</td></tr>
<tr><td>Jane Doe<br>Chief Financial Officer</td><td>2018</td><td>400,000</td><td>(1)</td><td>—</td><td>—</td><td>1,000,000</td><td>3,000</td><td>1,403,000</td></tr>
</table>
<table><tr><td>Name</td><td>Fees Earned or Paid in Cash ($)</td><td>Option Awards ($)</td><td>Total ($)</td></tr>
<tr><td>Robyn Denholm</td><td>42,670</td><td>6,838,600 (2)</td><td>6,881,270</td></tr></table>"""


class TestProxy(unittest.TestCase):
    def setUp(self):
        self.tabs = proxy.tables(SCT_HTML)

    def test_sct_rows_balance_and_names_carry(self):
        rows = proxy.parse_sct(self.tabs)
        self.assertEqual(len(rows), 3)
        musk17 = next(r for r in rows if r["fy"] == 2017)
        self.assertEqual(musk17["name"], "Elon Musk")          # title-only row continues the person
        self.assertEqual(musk17["position"], "Chief Executive Officer")
        for r in rows:
            parts = sum(v for k, v in r.items() if k not in ("fy", "name", "position", "total"))
            self.assertAlmostEqual(parts, r["total"])
        jane = next(r for r in rows if r["name"] == "Jane Doe")
        self.assertEqual((jane["position"], jane["option"]), ("Chief Financial Officer", 1_000_000))  # footnote (1) ignored

    def test_directors(self):
        d = proxy.parse_directors(self.tabs)
        self.assertEqual(d, [{"name": "Robyn Denholm", "fees": 42670.0, "option": 6838600.0, "total": 6881270.0}])


def _zip_13f() -> Path:
    tmp = Path(tempfile.mkdtemp()) / "01sep2025-30nov2025_form13f.zip"
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT\n"
                   "A1\t14-NOV-2025\t13F-HR\t0001\t30-SEP-2025\nA2\t14-NOV-2022\t13F-HR\t0002\t30-SEP-2022\n")
        z.writestr("COVERPAGE.tsv", "ACCESSION_NUMBER\tFILINGMANAGER_NAME\nA1\tBig Fund\nA2\tOld Fund\n")
        z.writestr("INFOTABLE.tsv", "ACCESSION_NUMBER\tNAMEOFISSUER\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\tINVESTMENTDISCRETION\n"
                   "A1\tTESLA\t88160R101\t1000\t10\tSH\t\tSOLE\n"
                   "A1\tTESLA\t88160R101\t500\t5\tSH\tPut\tSOLE\n"
                   "A1\tAPPLE\t037833100\t9\t9\tSH\t\tSOLE\n"
                   "A2\tTESLA\t88160R101\t7\t7\tSH\t\tSOLE\n")
    return tmp


class Test13F(unittest.TestCase):
    def test_extract_filters_cusip_and_scales_old_values(self):
        rows = sec_13f.extract(_zip_13f(), {"88160r101"})
        self.assertEqual(len(rows), 3)
        new = [r for r in rows if r["accession"] == "A1" and not r["put_call"]][0]
        self.assertEqual((new["manager"], new["period"], new["value"]), ("Big Fund", "2025-09-30", 1000))
        old = [r for r in rows if r["accession"] == "A2"][0]
        self.assertEqual(old["value"], 7000)  # pre-2023 VALUE was in thousands
        self.assertEqual({r["put_call"] for r in rows}, {None, "Put"})


class TestMacroAndPrices(unittest.TestCase):
    def test_fred_and_boe_csv(self):
        self.assertEqual(macro.parse(b"observation_date,DGS10\n2026-10-29,4.9\n2026-10-30,.\n", "fred"), [("2026-10-29", 4.9)])
        self.assertEqual(macro.parse(b"DATE,IUDBEDR\n02 Jan 2020,0.75\n", "boe"), [("2020-01-02", 0.75)])

    def test_inconsistent_live_bar_is_repaired_not_fatal(self):
        t0 = 1793712600  # a session open
        raw = json.dumps({"chart": {"result": [{
            "meta": {"gmtoffset": -18000, "regularMarketTime": t0 + 3600,
                     "currentTradingPeriod": {"regular": {"start": t0, "end": t0 + 23400}}},
            "timestamp": [t0 - 86400, t0],
            "indicators": {"quote": [{"open": [10, 89.9], "high": [11, 89.75], "low": [9, 88], "close": [10.5, 88.1],
                                      "volume": [1, 2]}], "adjclose": [{"adjclose": [10.5, 88.1]}]}}]}}).encode()
        p = prices.parse_yahoo(raw)
        self.assertTrue(p["meta"]["partial"])
        self.assertEqual(p["bars"][-1]["high"], 89.9)

    def test_news_name_cleaning(self):
        self.assertEqual(news.queries("RIVN", "Rivian Automotive, Inc. / DE")["gdelt"], '"Rivian Automotive" sourcelang:english')
        self.assertEqual(news.queries("F", "FORD MOTOR CO")["gdelt"], '"Ford Motor" sourcelang:english')


class TestCompaniesHouse(unittest.TestCase):
    """Shapes from the Companies House public data API docs."""

    def test_profile_officers_psc_filings(self):
        prof = companies_house.parse_profile({
            "company_name": "ROLLS-ROYCE HOLDINGS PLC", "company_number": "07524813", "company_status": "active",
            "sic_codes": ["70100"], "date_of_creation": "2011-02-14", "type": "plc", "jurisdiction": "england-wales",
            "accounts": {"accounting_reference_date": {"day": "31", "month": "12"}},
            "registered_office_address": {"address_line_1": "Kings Place", "address_line_2": "90 York Way",
                                          "locality": "London", "postal_code": "N1 9FX"}})
        self.assertEqual((prof["fiscal_year_end"], prof["sic"], prof["address"]["city"]), ("1231", "70100", "London"))
        off = companies_house.parse_officers({"items": [{"name": "EAST, Warren", "officer_role": "director",
            "appointed_on": "2015-07-02", "links": {"officer": {"appointments": "/officers/AbC123/appointments"}}}]})
        self.assertEqual((off[0]["role"], off[0]["officer_id"], off[0]["resigned"]), ("director", "AbC123", None))
        psc = companies_house.parse_psc({"items": [{"name": "X", "kind": "corporate-entity-person-with-significant-control",
                                                    "natures_of_control": ["ownership-of-shares-75-to-100-percent"]}]})
        self.assertIn("75-to-100", psc[0]["natures"])
        f = companies_house.parse_filings({"items": [{"transaction_id": "MzA0", "type": "AA", "date": "2026-04-01",
            "category": "accounts", "description": "accounts-with-accounts-type-group",
            "description_values": {"made_up_date": "2025-12-31"}}]}, "07524813")
        self.assertEqual((f[0]["accession"], f[0]["report_date"]), ("CH-MzA0", "2025-12-31"))
        self.assertIn("/07524813/filing-history/MzA0/document", f[0]["url"])

    def test_no_key_is_a_clear_error(self):
        os.environ.pop("MARKETS_CH_KEY", None)
        with self.assertRaises(RuntimeError):
            companies_house.fetch(Path(tempfile.mkdtemp()), "07524813", None)


if __name__ == "__main__":
    unittest.main()
