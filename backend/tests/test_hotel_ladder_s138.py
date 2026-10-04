"""Sasha 138 · the hotel booking ladder: the hotel's OWN booking engine (recognised on its own site, never fetched), its dates
in the link where the engine's usual URL takes them (said to be unverified), one tap on the guest's phone to pay there; a room
request by email; a call after 24 h or when arriving within 24 h; "Reserve (TEST)" kept alongside.

    cd backend && python -m unittest tests.test_hotel_ladder_s138 -v
"""
from __future__ import annotations

import unittest
from datetime import date
from urllib.parse import parse_qs, urlsplit

from booking_signer import guest_whatsapp as GW, slot_link as SL, venue_read as V
from tests import test_guest_whatsapp_s75 as TG


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
                                              "source_url": "https://thehatmadrid.com/contacto/", "detail": {"embed": "https://app.mews.com"}}]}
        link = SL.build_hotel(read, date(2026, 10, 20), 2, 2)
        self.assertEqual(link.url, "https://thehatmadrid.com/contacto/")
        self.assertIn("their Mews booking widget", link.source_label)


class OnWhatsApp(TG.Base):
    def setUp(self):
        super().setUp()
        self.link()
        self.links, api = [], GW.api

        async def fake(account, method, path, body=None, timeout=90.0):
            if path == "/api/booking/venues/read":
                return 200, {"read_id": "r-h", "venue": "Hotel Test", "country": "ES", "listing": {"name": "Hotel Test Madrid"}, "say": "x", "facts": [],
                             "rungs": [{"rung": "link", "available": True, "fact_index": 1, "value": "SynXis"},
                                       {"rung": "email", "available": True, "fact_index": 2, "value": "res@hoteltest.es"}]}
            if path == "/api/booking/links":
                self.links.append(body)
                return 200, {"link_id": "l-h", "platform": "SynXis", "slot_filled": False, "prefill_tried": True,
                             "url": "https://be.synxis.com/?hotel=1&arrive=2026-10-20&depart=2026-10-22&adult=2&rooms=1",
                             "read_back": {"lines": ["Hotel Test books rooms through its own booking engine (SynXis)."]}}
            return await api(account, method, path, body, timeout)
        fake.calls = api.calls
        GW.api = fake
        self.addCleanup(setattr, GW, "api", api)

    def test_book_with_hotel_sends_its_own_engine_with_the_stay(self):
        self.say("a hotel in Madrid from 20 to 22 October for 2")
        _, cards = GW.SENDER.contents[-1]
        self.say("x", payload=cards[0][1])
        body, choice = GW.SENDER.contents[-1]
        self.assertEqual([t for t, _ in choice], ["Test booking", "Book with hotel"])
        self.say("Book with hotel", payload=choice[1][1])
        said = "\n".join(self.bodies())
        self.assertIn("They book through SynXis.", said)
        self.assertEqual(self.links[0]["nights"], 2)
        self.assertIn("One tap: Hotel Test Madrid's own booking engine (SynXis).", said)
        self.assertIn("https://be.synxis.com/?hotel=1&arrive=2026-10-20", said)

    def test_a_call_says_the_stay_in_spanish_in_spain(self):
        self.say("a hotel in Madrid from 20 to 22 October for 2")
        d = (TG.run(GW.STORE.get_state(GW.wa_key(TG.GUEST))).get("pending") or {}).get("draft") or {}
        self.assertEqual(d["what"]["activity_venue_lang"], "una habitación para 2 noches (salida el 2026-10-22)")
