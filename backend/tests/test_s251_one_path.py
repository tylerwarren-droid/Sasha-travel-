"""Sasha 251 · ONE BOOKING PATH + BOOK UNDER ANOTHER NAME — offline (the booking API is a recorder; Sasha's read is given).

  D4, found live: a branch the venue engine couldn't read (Hammam Al Ándalus Salesas) went down Sasha's older page path ("Shall I
  send it to your phone?"). Now what Sasha's own read found is the engine path's channel: the one question, word for word.
  read_booking_route says the same channel. Old S1 (SASHA_S1_PARITY=off) keeps its ladder, and its schema.
  "Book it under Alex Gate": the name goes to the one path's person (who.name) — the prefilled form, the request, the call.

    cd backend && python -m unittest tests.test_s251_one_path -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import date, timedelta
from unittest import mock

from agapi import v0 as API, venues as VN
from app.agent import voice as V
from booking_signer import guest_accounts as GA, guest_receipt as GR, guest_whatsapp as GW
from tests.test_venue_pick_230 import FormApi, reader

ACCT = "00000000-0000-4000-8000-000000000251"
LATER = (date.today() + timedelta(days=6)).isoformat()
HAMMAM = {"link": {"value": "https://hammamalandalus.com/es/madrid/reservas"}, "email": {"value": "madrid@hammamalandalus.com"},
          "phone": {"fact_index": 0}}


class Base(unittest.TestCase):
    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        VN._HELD.pop(ACCT, None)
        self.api = FormApi()
        for p in (mock.patch.object(GW, "api", self.api), mock.patch.object(GA, "founder", lambda a: False),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="alex@example.test")),
                  mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=None))):   # the engine couldn't read it
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(VN._HELD.pop, ACCT, None)

    def hold(self, surface, rungs, **extra):
        ctx = API.Ctx(account=ACCT, mode="test", user_said="Hammam Al Ándalus, please.", session="s251", surface=surface)
        from tests.test_s254_one_decider import engine_from   # Sasha 270 · MOVED: their own booking page is the engine's read
        with mock.patch.object(VN, "_read", reader(rungs)), mock.patch.object(VN, "engine_channel", engine_from(rungs)):
            return asyncio.run(VN.hold_venue(ctx, {"name": "Hammam Al Ándalus Salesas", "city": "Madrid", "country": "ES",
                                                   "what": "a hammam", "party": 2, "day": LATER, "time": "17:00", **extra}))


class OnePath(Base):
    def test_d4_the_one_question_word_for_word(self):
        out = self.hold("s2", HAMMAM)
        self.assertEqual(out["status"], "choose_route")
        self.assertEqual(out["ask"], V.ASK_BOOK)
        self.assertEqual(out["ask"], "I'll book it. Want a prefilled form you just confirm, or shall I handle it and let you know?")
        self.assertEqual([o["title"] for o in out["options"]], ["Prefilled form", "Handle it"])

    def test_next_under_parity_is_the_same_path(self):
        self.assertEqual(self.hold("s1", HAMMAM)["ask"], V.ASK_BOOK)

    def test_old_s1_asks_the_same_rules(self):   # Sasha 254 · one decider for every surface (old S1's schema unchanged)
        with mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "off"}):
            out = self.hold("s1", HAMMAM)
        self.assertEqual(out.get("ask"), V.ASK_BOOK)

    def test_how_it_books_is_the_same_channel(self):
        ctx = API.Ctx(account=ACCT, mode="test", user_said="", session="s251", surface="s2")
        from tests.test_s254_one_decider import engine_from   # Sasha 270 · MOVED: their own booking page is the engine's read
        with mock.patch.object(VN, "_read", reader(HAMMAM)), mock.patch.object(VN, "engine_channel", engine_from(HAMMAM)):
            r = asyncio.run(VN.read_booking_route(ctx, {"name": "Hammam Al Ándalus Salesas", "city": "Madrid"}))
        self.assertEqual(r["routes"], ["page", "email"])

    def test_nothing_to_book_by_is_said_so(self):   # Sasha 254 · the rules' own words (no_channel) + the take-over, nothing sent
        from agapi.booking_rules import booking_rules as BR
        out = self.hold("s2", {})
        self.assertEqual((out["status"], out["rules"]["say_key"]), ("page_link", "no_channel"))
        # Sasha 270 · MOVED (Tyler, 15 Oct): never "no form". Sasha 286 · MOVED (Tyler, 24 Oct): never "send me their link" — THE FLOOR,
        # their website (else their listing) handed over with the way back
        self.assertTrue(out["say"].startswith("Here's their "))
        self.assertFalse(V.asks_for_link(out["say"]))
        self.assertTrue(out["page_url"].startswith("https://"))
        self.assertEqual(self.api.calls[-1][1], "/api/booking/contact")


class UnderAnotherName(Base):
    def test_the_name_goes_to_the_person(self):
        out = self.hold("s2", {"email": {"value": "madrid@hammamalandalus.com"}}, under="Alex Gate")
        self.assertEqual(out["status"], "awaiting_yes")
        body = next(b for m, p, b in self.api.calls if p == "/api/booking/emails")
        self.assertEqual(body["name"], "Alex Gate")

    def test_without_it_their_own_name(self):
        self.hold("s2", {"email": {"value": "madrid@hammamalandalus.com"}})
        body = next(b for m, p, b in self.api.calls if p == "/api/booking/emails")
        self.assertEqual(body["name"], "Alex Gate")   # FakeApi's contact name — the account's own

    def test_the_field_is_on_s2_and_parity_only(self):
        tool = next(API.schema_for_model(t) for t in API.TOOLS if t["name"] == "hold_venue")
        self.assertNotIn("under", tool["input_schema"]["properties"])          # S1's schema, as it was
        self.assertIn("under", VN.with_under(tool)["input_schema"]["properties"])


if __name__ == "__main__":
    unittest.main()
