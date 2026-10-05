"""CR 22 · the prefill library: links built from a venue page string only (nothing fetched), in each engine's own format;
taps to book, measured only where it was. python -m unittest tests.test_engine_library_cr22 -v"""
from __future__ import annotations

import unittest
from datetime import date, time
from urllib.parse import parse_qs, urlsplit

from booking_signer import engine_library as EL


def q(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query, keep_blank_values=True).items()}


class Build(unittest.TestCase):
    def test_tablecheck_date_time_party(self):
        url, carried = EL.build("TableCheck", "https://www.tablecheck.com/en/the-hill-station-vietnam/reserve",
                                date=date(2026, 11, 20), time=time(19, 0), party=2)
        self.assertEqual(q(url), {"start_date": "2026-11-20", "start_time": "19:00", "pax": "2"})
        self.assertEqual(carried, ["date", "time", "party"])

    def test_omnibees_ddmmyyyy_and_the_venue_query_kept(self):
        url, _ = EL.build("Omnibees", "https://book.omnibees.com/hotelresults?q=17958&lang=en-US",
                          checkin=date(2026, 11, 20), checkout=date(2026, 11, 22), rooms=1, adults=2)
        self.assertEqual(q(url), {"q": "17958", "lang": "en-US", "CheckIn": "20112026", "CheckOut": "22112026", "NRooms": "1", "ad": "2"})

    def test_synxis_leaves_out_children_zero_and_siteminder_adds_infants(self):
        url, carried = EL.build("SynXis", "https://be.synxis.com/?hotel=1&chain=2", checkin=date(2026, 11, 20),
                                checkout=date(2026, 11, 22), adults=2, children=0)
        self.assertNotIn("child", q(url))
        self.assertNotIn("children", carried)
        url, _ = EL.build("SiteMinder", "https://direct-book.com/properties/x", checkin=date(2026, 11, 20),
                          checkout=date(2026, 11, 22), adults=2, children=0)
        self.assertEqual(q(url)["items[0][infants]"], "0")
        self.assertEqual(q(url)["items[0][adults]"], "2")

    def test_cloudbeds_children_is_kids(self):
        url, _ = EL.build("Cloudbeds", "https://hotels.cloudbeds.com/reservation/nAuZCf", checkin=date(2026, 11, 20),
                          checkout=date(2026, 11, 22), adults=2, children=1)
        self.assertEqual(q(url)["kids"], "1")

    def test_no_template_means_the_page_unchanged(self):
        page = "https://www.covermanager.com/reserve/module_restaurant/restaurante-nomada-madrid/spanish"
        self.assertEqual(EL.build("CoverManager", page, date=date(2026, 11, 20), party=2), (page, []))
        self.assertEqual(EL.build("Unknown", page, party=2), (page, []))

    def test_verified_only_where_the_founder_checked(self):
        self.assertEqual({n for n, e in EL.LIBRARY.items() if e.verified}, {"TableCheck"})   # 1 of 6 answered (5 Oct)


class Taps(unittest.TestCase):
    def test_measured_only_where_it_was(self):
        self.assertEqual(EL.taps_to_book(None, test_venue=True), {"taps": 1, "how": "measured",
                         "why": "our test venue: Sasha filled its form, the guest presses Book"})
        t = EL.taps_to_book("TableCheck", ["date", "time", "party"])
        self.assertEqual((t["taps"], t["how"]), (6, "estimated"))              # verified it FILLS; the taps are still an estimate
        self.assertIn("(verified)", t["why"])
        self.assertEqual(EL.taps_to_book("TableCheck", ["date"])["taps"], 9)   # the slot not fully carried: the page count
        self.assertEqual(EL.taps_to_book("CoverManager")["taps"], 9)
        self.assertEqual(EL.taps_to_book("nobody")["how"], "unknown")

    def test_per_engine_summary(self):
        rows = [{"engine": "TableCheck", "taps": 6}, {"engine": "TableCheck", "taps": 8}, {"engine": "Mews", "taps": 11},
                {"engine": "Mews", "taps": None}]
        self.assertEqual(EL.per_engine(rows), [{"engine": "Mews", "bookings": 1, "median_taps": 11},
                                               {"engine": "TableCheck", "bookings": 2, "median_taps": 7.0}])
