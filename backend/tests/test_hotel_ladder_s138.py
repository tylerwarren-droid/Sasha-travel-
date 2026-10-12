"""Sasha 138 · the hotel booking ladder: the hotel's OWN booking engine (recognised on its own site, never fetched), its dates
in the link where the engine's usual URL takes them (said to be unverified), one tap on the guest's phone to pay there; a room
request by email; a call after 24 h or when arriving within 24 h; "Reserve (TEST)" kept alongside.

    cd backend && python -m unittest tests.test_hotel_ladder_s138 -v
"""
from __future__ import annotations

import unittest
from datetime import date
from urllib.parse import parse_qs, urlsplit

from booking_signer import slot_link as SL, venue_read as V


def read_with(link: str) -> dict:
    return {"name": "Hotel Test", "facts": [{"kind": "platform", "value": V.platform_of(link), "source_label": "their website, hoteltest.es",
                                            "detail": {"link": link}, "evidence": {"link": link}}]}


class Engines(unittest.TestCase):
    def test_the_engines_are_recognised_by_their_hosts(self):
        for url, name in (("https://be.synxis.com/?hotel=12345", "SynXis"), ("https://hotels.cloudbeds.com/reservation/AbC123", "Cloudbeds"),
                          ("https://app.mews.com/distributor/1a2b", "Mews"), ("https://direct-book.com/properties/hoteltest", "SiteMinder"),
                          ("https://www.secure-hotel-booking.com/hotel-test/2ABC/en/", "D-Edge"), ("https://hoteltest.roiback.com/es/", "Roiback"),
                          ("https://apac.littlehotelier.com/properties/hoteltest", "Little Hotelier")):
            self.assertEqual(V.platform_of(url), name, url)
            self.assertIn(name, V.HOTEL_ENGINES)

    def test_dates_go_in_where_the_engine_takes_them_and_are_said_to_be_unverified(self):
        link = SL.build_hotel(read_with("https://be.synxis.com/?hotel=12345&chain=99"), date(2026, 10, 20), 2, 2)
        q = parse_qs(urlsplit(link.url).query)
        self.assertEqual((q["hotel"], q["arrive"], q["depart"], q["adult"]), (["12345"], ["2026-10-20"], ["2026-10-22"], ["2"]))
        self.assertTrue(link.prefill_tried)
        self.assertFalse(link.slot_filled)                                                  # never claimed as filled
        lines = SL.hotel_read_back("Hotel Test", link, date(2026, 10, 20), 2, 2, None)
        self.assertIn("not yet verified, so check them on their page before you pay", lines[1])
        self.assertIn("one tap on your phone, where their page takes Apple Pay or your card", lines[0])

    def test_an_engine_without_a_known_url_gets_the_plain_page_and_the_dates_said(self):
        link = SL.build_hotel(read_with("https://www.secure-hotel-booking.com/hotel-test/2ABC/en/"), date(2026, 10, 20), 2, 2)
        self.assertFalse(link.prefill_tried)
        self.assertEqual(SL.hotel_read_back("Hotel Test", link, date(2026, 10, 20), 2, 2, None)[1],
                         "On their page, choose: check-in Tue 20 Oct, check-out Thu 22 Oct (2 nights), 2 adults.")

    def test_an_engine_page_is_never_fetched(self):
        self.assertTrue(V.platform_of("https://be.synxis.com/?hotel=1"))   # venue_read never fetches a URL platform_of names (S-37)


class Rehearsal1(unittest.TestCase):
    """The read-only rehearsal (4 Oct): three Hoi An hotels' only D-Edge link was the vendor's homepage (a 'powered by' footer);
    Mews and Neobookings were widgets on the hotel's own page."""

    def test_a_vendor_homepage_is_never_the_booking_page(self):
        with self.assertRaises(SL.LinkRefused):
            SL.build_hotel(read_with("https://www.d-edge.com/"), date(2026, 11, 14), 2, 2)
        ok = SL.build_hotel(read_with("https://www.secure-hotel-booking.com/d-edge/The-Signature-Hoi-An/J6S6/en-US?hotelId=32001"),
                            date(2026, 11, 14), 2, 2)
        self.assertTrue(ok.url.startswith("https://www.secure-hotel-booking.com/d-edge/The-Signature-Hoi-An/"))

    def test_an_embedded_engine_sends_the_hotels_own_page(self):
        read = {"name": "The Hat", "facts": [{"kind": "platform", "value": "Mews", "source_label": "their website, thehatmadrid.com",
                                              "source_url": "https://thehatmadrid.com/contacto/?utm_source=google&lang=es",
                                              "detail": {"embed": "https://app.mews.com"}}]}
        link = SL.build_hotel(read, date(2026, 10, 20), 2, 2)
        self.assertEqual(link.url, "https://thehatmadrid.com/contacto/?lang=es")   # Google's tracking dropped, nothing added
        self.assertIn("booking through Mews on their own site", link.source_label)

