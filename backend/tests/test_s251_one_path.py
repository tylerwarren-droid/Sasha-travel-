"""Sasha 251 → Sasha 378 · ONE BOOKING PATH + BOOK UNDER ANOTHER NAME — offline (the booking API is a recorder; AgAPI's decision is
scripts/agapi_decides, its own shapes).

  D4, found live: a branch the venue engine couldn't read went down Sasha's older page path. Sasha 378 · CR 188: every surface (/s2,
  /next under parity, old S1) follows AgAPI's ONE decision — no question of Sasha's own ("prefilled form or handle it?" is gone).
  read_booking_route says the same decision. "Book it under Alex Gate": the name goes to the one path's person (who.name).

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
    def test_d4_agapis_decision_no_question_of_her_own(self):
        out = self.hold("s2", HAMMAM)                                   # their page, their email, their phone: AgAPI decides ONE way
        self.assertEqual(out["rules"]["action"], "request_email")
        self.assertNotIn("options", out)
        self.assertNotEqual(out.get("ask"), V.ASK_BOOK)

    def test_next_under_parity_is_the_same_path(self):
        self.assertEqual(self.hold("s1", HAMMAM)["rules"]["action"], "request_email")

    def test_old_s1_follows_the_same_decision(self):
        with mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "off"}):
            out = self.hold("s1", HAMMAM)
        self.assertEqual(out["rules"]["action"], "request_email")

    def test_how_it_books_is_the_same_decision(self):
        ctx = API.Ctx(account=ACCT, mode="test", user_said="", session="s251", surface="s2")
        from tests.test_s254_one_decider import engine_from
        with mock.patch.object(VN, "_read", reader(HAMMAM)), mock.patch.object(VN, "engine_channel", engine_from(HAMMAM)):
            r = asyncio.run(VN.read_booking_route(ctx, {"name": "Hammam Al Ándalus Salesas", "city": "Madrid"}))
        self.assertEqual((r["routes"], r["decision"]["route"]), (["message"], "message"))

    def test_nothing_to_book_by_is_the_floor(self):   # AgAPI: none — their website handed over, never "send me their link"
        out = self.hold("s2", {})
        self.assertIn(out["status"], ("page_link", "page_on_phone"))
        self.assertFalse(V.asks_for_link(out.get("say") or ""))
        self.assertFalse(out.get("booked"))


class UnderAnotherName(Base):
    """Sasha 319 · the name goes to AgAPI's booking record (venue.prepare_booking's person) — Sasha's own email is gone."""

    def prepared_as(self, **kw):
        from agapi import venue_submit as VS
        seen = []

        async def prepare(account, place, person, *a, **k):
            seen.append(person)
            return {"ok": False, "error": {"code": "not_configured", "message": "no venues key"}}
        with mock.patch.object(VS, "prepare", prepare):
            out = self.hold("s2", {"email": {"value": "madrid@hammamalandalus.com"}}, **kw)
        return out, seen

    def test_the_name_goes_to_the_person(self):
        out, seen = self.prepared_as(under="Alex Gate")
        self.assertEqual(seen[0]["name"], "Alex Gate")
        self.assertEqual(out["status"], "to_tyler")                     # no venues key in this test: Tyler's, nothing sent
        self.assertNotIn("/api/booking/emails", [c[1] for c in self.api.calls])

    def test_without_it_their_own_name(self):
        out, seen = self.prepared_as()
        self.assertEqual(seen[0]["name"], "Alex Gate")   # FakeApi's contact name — the account's own

    def test_the_field_is_on_s2_and_parity_only(self):
        tool = next(API.schema_for_model(t) for t in API.TOOLS if t["name"] == "hold_venue")
        self.assertNotIn("under", tool["input_schema"]["properties"])          # S1's schema, as it was
        self.assertIn("under", VN.with_under(tool)["input_schema"]["properties"])


if __name__ == "__main__":
    unittest.main()
