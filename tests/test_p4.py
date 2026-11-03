"""Offline tests for P4 parsers: 13D/G, short interest, news, 10-K sections/diff, journal."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
os.environ.setdefault("MARKETS_DATA_DIR", tempfile.mkdtemp(prefix="markets-test-"))

from markets import config, journal  # noqa: E402
from markets.normalize import sections  # noqa: E402
from markets.sources import news, ownership_13dg, short_interest  # noqa: E402

XML_13G = b"""<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g">
<formData><coverPageHeader><eventDateRequiresFilingThisStatement>06/16/2026</eventDateRequiresFilingThisStatement></coverPageHeader>
<coverPageHeaderReportingPersonDetails><reportingPersonName>Elon R. Musk</reportingPersonName>
<reportingPersonBeneficiallyOwnedAggregateNumberOfShares>699580882.00</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
<classPercent>19.9</classPercent></coverPageHeaderReportingPersonDetails>
<items><item2><reportingPersonName>Elon R. Musk</reportingPersonName></item2></items></formData></edgarSubmission>"""

TEXT_13G = """TESLA INC
(Name of Issuer)
December 31, 2021
--------------------------------------------------------
(Date of Event Which Requires Filing of this Statement)
(1)Names of reporting persons. The Vanguard Group - 23-1945930
(9) Aggregate amount beneficially owned by each reporting person
 52,918,395
(11) Percent of class represented by amount in Row 9
 5.3%
"""

HEADER = (b"<SEC-HEADER>\nSUBJECT COMPANY:\n\n\tCOMPANY DATA:\n\t\tCOMPANY CONFORMED NAME:\t\t\tTesla, Inc.\n"
          b"\t\tCENTRAL INDEX KEY:\t\t\t0001318605\n\nFILED BY:\n\n\tCOMPANY DATA:\n"
          b"\t\tCOMPANY CONFORMED NAME:\t\t\tMusk Elon\n\t\tCENTRAL INDEX KEY:\t\t\t0001494730\n</SEC-HEADER>\n")


class TestOwnership(unittest.TestCase):
    def test_xml_blocks_not_confused_by_repeated_names(self):
        p = ownership_13dg.parse_xml(XML_13G)
        self.assertEqual(len(p), 1)
        self.assertEqual((p[0]["shares"], p[0]["percent"], p[0]["event_date"]), (699580882.0, 19.9, "2026-06-16"))

    def test_text_cover_page(self):
        p = ownership_13dg.parse_text(TEXT_13G)
        self.assertEqual(p[0]["name"], "The Vanguard Group")
        self.assertEqual((p[0]["shares"], p[0]["percent"], p[0]["event_date"]), (52918395.0, 5.3, "2021-12-31"))

    def test_full_submission_and_filer(self):
        raw = HEADER + b"<DOCUMENT>\n<TYPE>SCHEDULE 13G/A\n<SEQUENCE>1\n<FILENAME>primary_doc.xml\n<TEXT>\n<XML>\n" + \
            XML_13G + b"\n</XML>\n</TEXT>\n</DOCUMENT>"
        p = ownership_13dg.parse(raw)
        self.assertEqual((p["filer"], p["filer_cik"]), ("Musk Elon", 1494730))
        self.assertEqual(p["persons"][0]["percent"], 19.9)


class TestFeeds(unittest.TestCase):
    def test_short_interest_dedupes_and_sorts(self):
        raw = json.dumps([
            {"settlementDate": "2026-10-15", "currentShortPositionQuantity": 2, "averageDailyVolumeQuantity": 1, "daysToCoverQuantity": 2.0},
            {"settlementDate": "2026-09-30", "currentShortPositionQuantity": 1, "averageDailyVolumeQuantity": 1, "daysToCoverQuantity": 1.0},
            {"settlementDate": "2026-10-15", "currentShortPositionQuantity": 3, "averageDailyVolumeQuantity": 1, "daysToCoverQuantity": 3.0},
        ]).encode()
        rows = short_interest.parse(raw)
        self.assertEqual([r["settle_date"] for r in rows], ["2026-09-30", "2026-10-15"])
        self.assertEqual(rows[1]["shares_short"], 3)

    def test_gnews_strips_source_suffix(self):
        raw = (b'<rss><channel><item><title>Tesla beats estimates - Reuters</title><link>https://x/1</link>'
               b'<pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate><source url="https://reuters.com">Reuters</source></item>'
               b'</channel></rss>')
        r = news.parse_gnews(raw)[0]
        self.assertEqual((r["title"], r["source"], r["published"]), ("Tesla beats estimates", "Reuters", "2026-11-03T14:00+00:00"))

    def test_gdelt(self):
        raw = json.dumps({"articles": [{"url": "https://a", "title": " T ", "domain": "a.com", "seendate": "20261103T120000Z"}]}).encode()
        self.assertEqual(news.parse_gdelt(raw)[0]["published"], "2026-11-03T12:00+00:00")
        self.assertEqual(news.parse_gdelt(b"rate limited"), [])


class TestSections(unittest.TestCase):
    DOC = ("Table of contents\nItem 1. Business 4\nItem 1A. Risk Factors 12\nItem 7. Management's Discussion and "
           "Analysis of Financial Condition and Results of Operations 40\n\n"
           "PART I\nItem 1. Business\n" + "We make cars and batteries for the world.\n\n" * 5 +
           "Item 1A. Risk Factors\n" + "Demand may fall if rates rise sharply this year.\n\n" * 8 +
           "Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations\n" +
           "Revenue grew because deliveries increased a lot.\n\n" * 6 + "Item 8. Financial Statements\nx")

    def test_split_prefers_body_over_toc(self):
        items = sections.split_items(self.DOC)
        self.assertIn("Demand may fall", items["1A"])
        self.assertIn("Revenue grew", items["7"])  # long MD&A heading still matched

    def test_diff_detects_add_remove_change(self):
        a = "Para one is about demand and pricing pressure.\n\nPara two covers supply chain risk in Asia.\n\nOld risk that was removed entirely now."
        b = "Para one is about demand and severe pricing pressure.\n\nPara two covers supply chain risk in Asia.\n\nBrand new risk about tariffs and trade."
        d = sections.diff(a, b)
        ops = [blk["op"] for blk in d["blocks"]]
        self.assertIn("change", ops)
        self.assertIn("equal", ops)
        self.assertEqual(d["stats"]["unchanged"], 1)
        ch = next(blk for blk in d["blocks"] if blk["op"] == "change")
        self.assertIn(["+", "severe"], ch["words"])


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old = (config.DATA_DIR, config.JOURNAL_DB_PATH)
        config.DATA_DIR = Path(self.tmp)
        config.JOURNAL_DB_PATH = Path(self.tmp) / "journal.db"

    def tearDown(self):
        config.DATA_DIR, config.JOURNAL_DB_PATH = self._old

    def test_trade_lifecycle_and_log(self):
        t = journal.save_trade("tsla", {"side": "long", "qty": "10", "entry_date": "2026-01-02", "entry_price": "100", "stop": "90"})
        self.assertEqual(journal.trade_pnl(t, 110.0)["r"], 1.0)
        closed = journal.save_trade("TSLA", {"exit_date": "2026-02-01", "exit_price": 120}, t["id"])
        p = journal.trade_pnl(closed, 999.0)  # closed trades ignore the mark
        self.assertEqual((p["pnl"], p["open"]), (200.0, False))
        journal.delete("trade", "TSLA", t["id"])
        self.assertEqual(journal.list_trades("TSLA"), [])
        log = (Path(self.tmp) / "journal.log.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(log[-1])["action"], "delete")  # nothing is lost

    def test_short_pnl_and_validation(self):
        t = journal.save_trade("TSLA", {"side": "short", "qty": 1, "entry_date": "2026-01-02", "entry_price": 100})
        self.assertEqual(journal.trade_pnl(t, 90.0)["pnl"], 10.0)
        with self.assertRaises(journal.Invalid):
            journal.save_trade("TSLA", {"side": "sideways", "qty": 1, "entry_date": "x", "entry_price": 1})
        with self.assertRaises(journal.Invalid):
            journal.save_trade("TSLA", {"exit_price": 5}, t["id"])  # exit needs a date too

    def test_notes(self):
        n = journal.save_note("TSLA", {"title": "Q3", "body": "margins?"})
        journal.save_note("TSLA", {"body": "margins compressed"}, n["id"])
        self.assertEqual(journal.list_notes("TSLA")[0]["body"], "margins compressed")
        with self.assertRaises(journal.Invalid):
            journal.save_note("TSLA", {})


if __name__ == "__main__":
    unittest.main()
