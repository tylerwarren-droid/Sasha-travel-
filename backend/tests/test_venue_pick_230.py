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

from app.agent import voice as V
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
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        VN._HELD.pop(ACCT, None)
        self.api = FormApi()
        for p in (mock.patch.object(GW, "api", self.api), mock.patch.object(GA, "founder", lambda a: False),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="alex@example.test"))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(VN._HELD.pop, ACCT, None)

    def pick(self, surface, rungs, said="Casa Gate, please.", **extra):
        ctx = API.Ctx(account=ACCT, mode="test", user_said=said, session="s230", surface=surface)
        with mock.patch.object(VN, "_read", reader(rungs)):
            return run(VN.hold_venue(ctx, {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "party": 2,
                                           "day": LATER, "time": "21:00", **extra}))

    # Sasha 254 · the booking rules decide (agapi/booking_rules via agapi.booking_decide): a form is the ONE question (R2) — "Handle
    # it" (route form) is the form's read-back, the yes in a later turn books it; own channels before a platform (R1/R14)
    def test_on_s2_a_form_is_the_one_question_then_handle_it_is_the_read_back(self):
        out = self.pick("s2", {"form": {}})
        self.assertEqual((out["status"], out["ask"]), ("choose_route", V.ASK_BOOK))
        self.assertNotIn(ACCT, VN._HELD)
        out = self.pick("s2", {"form": {}}, route="form")
        self.assertEqual(out["status"], "awaiting_yes")                       # the read-back, not "shall I?"
        self.assertEqual(out["route"], "form")
        self.assertTrue(out["read_back"])
        self.assertEqual(VN._HELD[ACCT]["rung"], "form")                       # held: the yes (a later turn) books it

    def test_on_s2_their_own_email_comes_before_a_platform(self):
        out = self.pick("s2", {"link": {"value": "TheFork"}, "email": {}, "phone": {"fact_index": 0}})
        self.assertEqual((out["status"], out["route"], out["rules"]["action"]), ("awaiting_yes", "email", "request_email"))

    def test_old_s1_asks_the_same_rules(self):   # Sasha 254 · old S1 (parity off): the same decision (its schema unchanged)
        with mock.patch.dict("os.environ", {"SASHA_S1_PARITY": "off"}):
            out = self.pick("s1", {"form": {}})
        self.assertEqual((out["status"], out["ask"]), ("choose_route", V.ASK_BOOK))
        self.assertNotIn(ACCT, VN._HELD)

    def test_the_yes_in_a_later_turn_books_it(self):
        self.pick("s2", {"form": {}}, route="form")
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
