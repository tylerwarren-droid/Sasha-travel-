"""Sasha 230 · THE RESTAURANT LOOP (Tyler, /s2, 10 Oct): a pick must reach the read-back in ONE turn. The venue had one way to book
(its own form): the pick got the ladder's "I can book X directly — shall I?", the yes got the read-back's "shall I send it?" — the
same question twice. On /s2 one route is not a choice: straight to its read-back. A real choice still asks first; S1 unchanged.
Offline: the booking API is the venue suite's fake (nothing leaves the process).

    cd backend && python -m unittest tests.test_venue_pick_230 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import date, timedelta
from unittest import mock

from agapi import v0 as API, venues as VN
from booking_signer import guest_accounts as GA, guest_receipt as GR, guest_whatsapp as GW
from scripts.venue_suite import FakeApi

ACCT = "00000000-0000-4000-8000-000000000230"
run = asyncio.run
LATER = (date.today() + timedelta(days=6)).isoformat()


class FormApi(FakeApi):
    async def __call__(self, account, method, path, body=None, timeout=90.0):
        if path == "/api/booking/forms" and not (body or {}).get("handover"):
            self.calls.append((method, path, body))
            return 200, {"form_id": "f-9", "trip_item_id": "t-9", "read_back": {"lines": ["Casa Gate · 2 people · 21:00"], "sha256": "e" * 64}}
        if path == "/api/booking/forms/f-9/send":
            self.calls.append((method, path, body))
            return 200, {"status": "sent", "reading": {"result": "confirmed"}, "booking_reference": "TV-230"}
        return await super().__call__(account, method, path, body, timeout)


def reader(rungs):
    async def rd(ctx, a):
        return {"read_id": "r-1", "country": "ES", "venue": "Casa Gate", "facts": [], "rungs": rungs, "open_now": True,
                "opens_at": None, "say": ""}
    return rd


class APick(unittest.TestCase):
    def setUp(self):
        VN._HELD.pop(ACCT, None)
        self.api = FormApi()
        for p in (mock.patch.object(GW, "api", self.api), mock.patch.object(GA, "founder", lambda a: False),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="alex@example.test"))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(VN._HELD.pop, ACCT, None)

    def pick(self, surface, rungs, said="Casa Gate, please."):
        ctx = API.Ctx(account=ACCT, mode="test", user_said=said, session="s230", surface=surface)
        with mock.patch.object(VN, "_read", reader(rungs)):
            return run(VN.hold_venue(ctx, {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "party": 2,
                                           "day": LATER, "time": "21:00"}))

    def test_on_s2_one_way_to_book_is_the_read_back_in_one_turn(self):
        out = self.pick("s2", {"form": {}})
        self.assertEqual(out["status"], "awaiting_yes")                       # the read-back, not "shall I?"
        self.assertEqual(out["route"], "form")
        self.assertTrue(out["read_back"])
        self.assertEqual(VN._HELD[ACCT]["rung"], "form")                       # held: the yes (a later turn) books it

    def test_on_s2_a_real_choice_still_asks_first(self):
        out = self.pick("s2", {"link": {"value": "TheFork"}, "email": {}, "phone": {"fact_index": 0}})
        self.assertEqual(out["status"], "choose_route")                       # email them, or book now: theirs to choose
        self.assertNotIn(ACCT, VN._HELD)

    def test_s1_is_unchanged(self):
        out = self.pick("s1", {"form": {}})
        self.assertEqual(out["status"], "choose_route")                       # /next keeps the ladder's question, as before
        self.assertNotIn(ACCT, VN._HELD)

    def test_the_yes_in_a_later_turn_books_it(self):
        self.pick("s2", {"form": {}})
        VN._HELD[ACCT]["at"] -= timedelta(seconds=5)                           # the read-back was said in an earlier turn
        ctx = API.Ctx(account=ACCT, mode="test", user_said="Yes, book it.", session="s230", surface="s2")
        from booking_signer import wa_brain as WB
        with mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value="It's in your bookings")), \
                mock.patch("agapi.v0.claim", mock.AsyncMock()):
            out = run(VN.book_venue(ctx, {"approval": {"said": "Yes, book it."}}))
        self.assertEqual((out["status"], out.get("reference")), ("confirmed", "TV-230"))
        self.assertEqual(self.api.calls[-1][2]["read_back_sha256"], "e" * 64)   # the read-back they heard, and only that

if __name__ == "__main__":
    unittest.main()
