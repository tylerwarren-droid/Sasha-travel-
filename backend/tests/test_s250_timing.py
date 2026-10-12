"""Sasha 250 · THE BOOKING TIMING RULE on the ONE engine path, for every venue type (rows 234 + 526; Tyler, 12 Oct) — offline: the
booking API is a recorder (scripts.venue_suite.FakeApi), the venue engine's channel is given, nothing leaves the process.

  T15a own form → book directly, any timing (the one question; "prefilled form" is the go-ahead)
  T15b no form, more than 48 h → a request (email), wait for the reply
  T15c no form, within 48 h → a call AND the email at once, ONE read-back, ONE yes sends both (calls on); calls off → the request, said
  T15d "handle it" within 48 h is the call (+ email), never a request left waiting
  T15e a hotel's email carries the 24-hour no-reply call in its read-back (the yes covers it); a restaurant's doesn't
  T15f calls: the AI disclosure first, no deposit/fee/card/different time, no voicemail, 3 a day by default
  T15g the no-reply sweep reaches every account with a request out, WhatsApp or not

    cd backend && python -m unittest tests.test_s250_timing -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from agapi import venues as VN
from scripts.venue_suite import FakeApi

ACCT = "00000000-0000-4000-8000-000000000250"
MAD = ZoneInfo("Europe/Madrid")


def run(c):
    return asyncio.get_event_loop().run_until_complete(c) if False else asyncio.new_event_loop().run_until_complete(c)


class Ctx:
    def __init__(self, said=""):
        self.account, self.surface, self.user_said = ACCT, "s2", said
        self.started = datetime.now(timezone.utc) + timedelta(seconds=5)
        self.act_name = self.idem = None


def booking(hours: float, what=("restaurant", "table")):
    at = (datetime.now(MAD) + timedelta(hours=hours)).replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    return at, {"who": {"name": "Alex Gate", "contact": {"mobile_e164": "+447700900250"}}, "how_many": {"count": 2},
                "when": {"at": at}, "what": {"category": what[0], "activity": what[1]}}


RD = {"read_id": "r-1", "country": "ES", "venue": "Casa Gate", "place_id": "p1", "facts": [],
      "rungs": {"email": {"value": "reservas@casagate.test"}, "phone": {"value": "+34910000000", "fact_index": 0}}, "say": ""}
REQUEST_ONLY = {"kind": "email", "value": "reservas@casagate.test"}
FORM_AND_EMAIL = {"kind": "own_engine", "url": "https://casagate.test/reservas", "alternative": {"kind": "email", "value": "reservas@casagate.test"},
                  "ask": "x"}


class Base(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()

        class GWStub:
            STORE = None
            api = self.api

            @staticmethod
            def summary(res): return "Thursday at 21:00, 2 people"

            @staticmethod
            def plain_venue(v): return str(v)

            @staticmethod
            def guest_lines(rung, lines): return list(lines)

            @staticmethod
            def refusal_words(j, s): return f"HTTP {s}"

            @staticmethod
            def decision_of(rd, prefer=None, at=None, now=None, account=None):
                from booking_signer import guest_whatsapp as GW
                return GW.decision_of(rd, prefer, at, now, None)
        self.gw = GWStub
        self.ps = [mock.patch.object(VN, "_API", lambda: GWStub)]
        from booking_signer import guest_receipt as GR

        async def addr(a): return "guest@example.com"
        self.ps.append(mock.patch.object(GR, "address_of", addr))
        for p in self.ps:
            p.start()
        VN._HELD.pop(ACCT, None)

    def tearDown(self):
        for p in reversed(self.ps):
            p.stop()
        VN._HELD.pop(ACCT, None)

    def calls_on(self, on: bool):
        from booking_signer import limits as L
        return mock.patch.object(L, "calls_on", lambda a: on)

    def route(self, hours, eng, route=None, calls=True, what=("restaurant", "table")):
        at, res = booking(hours, what)
        with self.calls_on(calls):
            return run(VN._engine_route(Ctx(), {}, dict(RD), res, at, datetime.now(timezone.utc), route, eng, None))

    def posted(self):
        return [p for m, p, b in self.api.calls if m == "POST"]


class T15_Timing(Base):
    def test_a_own_form_is_booked_directly_any_timing(self):
        for hours in (6, 200):
            q = self.route(hours, FORM_AND_EMAIL)
            self.assertEqual(q["status"], "choose_route")
            self.assertEqual(q["options"][0], {"title": "Prefilled form", "route": "page"})

    def test_b_no_form_more_than_48h_is_a_request(self):
        out = self.route(96, REQUEST_ONLY)
        self.assertEqual((out["status"], out["route"]), ("awaiting_yes", "email"))
        self.assertEqual(self.posted(), ["/api/booking/emails"])

    def test_c_no_form_within_48h_is_a_call_and_the_email_on_one_yes(self):
        out = self.route(20, REQUEST_ONLY)
        self.assertEqual(out["route"], "call_email")
        self.assertEqual(self.posted(), ["/api/booking/calls", "/api/booking/emails"])
        self.assertIn("— and at the same time, by email: —", out["read_back"])
        held = VN._HELD[ACCT]
        got = run(VN._book_inner(Ctx("yes"), held, {"how": "voice", "said": "yes"}, "Casa Gate", "call_email"))
        self.assertEqual(self.posted()[-2:], ["/api/booking/emails/e-1/send", "/api/booking/calls/k-1/place"])   # ONE yes, both
        self.assertEqual((got["status"], got["emailed"]), ("placed", True))

    def test_c_calls_off_it_stays_a_request_and_says_so(self):
        out = self.route(20, REQUEST_ONLY, calls=False)
        self.assertEqual(out["route"], "email")
        self.assertIn("can't call them", out.get("note", ""))

    def test_d_handle_it_within_48h_is_the_call(self):
        self.assertEqual(self.route(20, FORM_AND_EMAIL)["options"][1], {"title": "Handle it", "route": "call_email"})
        self.assertEqual(self.route(96, FORM_AND_EMAIL)["options"][1], {"title": "Handle it", "route": "email"})

    def test_e_a_hotels_email_carries_the_24h_call(self):
        self.route(96, REQUEST_ONLY, what=("hotel", "room"))
        body = next(b for m, p, b in self.api.calls if p == "/api/booking/emails")
        self.assertTrue(body.get("auto_plan"))
        self.api.calls.clear(); VN._HELD.pop(ACCT, None)
        self.route(96, REQUEST_ONLY)
        body = next(b for m, p, b in self.api.calls if p == "/api/booking/emails")
        self.assertNotIn("auto_plan", body)


class T15_Calls(unittest.TestCase):
    def test_f_the_call_rules(self):
        from booking_signer import calls as C, call_routes as CR
        src = open(C.__file__).read()
        self.assertIn("the AI disclosure is in English, first", src)
        self.assertIn("Agree to no deposit, give no card", C.DEPOSIT_RULE)
        self.assertIn('"voicemail": {"action": "hangup"}', src)
        with mock.patch.dict(os.environ, {"SASHA_CALLS_PER_DAY": ""}):
            os.environ.pop("SASHA_CALLS_PER_DAY")
            self.assertEqual(CR.cap(), 3)

    def test_g_the_sweep_reaches_accounts_without_whatsapp(self):
        from booking_signer import ladder_store as LS
        st = LS.MemoryLadderStore()
        st.emails = {"e1": {"account_id": "a-web", "status": "sent"}, "e2": {"account_id": "a-x", "status": "awaiting_approval"}}
        self.assertEqual(run(st.request_accounts()), ["a-web"])
        src = open(__import__("booking_signer.proactive", fromlist=["x"]).__file__).read()
        self.assertIn("request_accounts()", src)


if __name__ == "__main__":
    unittest.main()
