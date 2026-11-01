"""Sasha 319 · ONE SENDER TO VENUES: AgAPI's acts. The old reservation route's own sends are gone.

Root test (written first): (1) one truth — AgAPI's acts (venue.submit_booking / change_booking / cancel_booking and its call act, row
1569's routes). (2) booking_signer's own senders — the ladder's email and form, its call (/calls/{id}/place), the reservation route's
cancel (link / email / text / call) and its change / running-late notices, hold_venue's _email / _form / _call / _call_and_email
fallbacks, the s2_manage notice call and the health product's /api/booking/calls — were second copies: deleted, not guarded. (3) After
this nothing in Sasha emails, texts or calls a venue except through AgAPI; what AgAPI can't take (no venues key, no slot, a booking on
the old route with no act) is "I'll hand this to Tyler" — nothing sent. Sasha's own messages to the GUEST (receipts) stay.
Offline.

    cd backend && python -m unittest tests.test_s319 -v
"""
from __future__ import annotations
import tests.founder_fixture  # noqa: F401,E402  (the booking routes' founder)

import asyncio
import inspect
import os
import pathlib
import re
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agapi import s2_manage as M, venues as VN
from booking_signer import retired as RT, routes

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ENV = {"SASHA_BOOKING_KEY": "test-booking-key", "SASHA_CALLS_ENABLED": "1", "BLAND_API_KEY": "test-key-not-real"}
RETIRED = [("/api/booking/calls/c-1/place", "a call to the venue"), ("/api/booking/emails/e-1/send", "an email to the venue"),
           ("/api/booking/forms/f-1/send", "the venue's form, sent"), ("/api/booking/forms/f-1/handover", "the venue's form, filled"),
           ("/api/booking/reservations/t-1/cancel", "a cancellation to the venue"),
           ("/api/booking/reservations/t-1/notice", "a change or running-late notice to the venue")]


class TheOldSendersAreGone(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)
        app = FastAPI()
        app.include_router(routes.router)
        self.c = TestClient(app, headers={"x-sasha-booking-key": "test-booking-key", "x-sasha-session": "founder"})

    def test_every_retired_endpoint_refuses_and_sends_nothing(self):
        from booking_signer import calls as C, emailing as E, guest_receipt as GR
        no = mock.AsyncMock(side_effect=AssertionError("a venue was contacted"))
        with mock.patch.object(C, "place_call", no), mock.patch.object(E, "send", no), mock.patch.object(GR, "send_sms", no):
            for path, what in RETIRED:
                r = self.c.post(path, json={"read_back_sha256": "a" * 64, "approval": {"how": "button", "said": "yes"}})
                self.assertEqual((r.status_code, r.json()["rule"], r.json()["sent"], r.json()["what"]), (410, RT.RULE, False, what), path)
                self.assertEqual(r.json()["say"], RT.TO_TYLER)

    def test_no_second_sender_left_in_sasha(self):
        """The whole class: no code path in Sasha's agent, products or the retired handlers reaches a venue's email, text or call."""
        for f in ("agapi/venues.py", "agapi/s2_manage.py", "products/health/turn.py", "products/health/cita.py"):
            src = (BACKEND / f).read_text()
            for bad in ('"/api/booking/calls"', "/api/booking/calls/{", "/api/booking/emails/{", "/api/booking/forms/{", "/notice\"",
                        "/reservations/{tid}/cancel", "/reservations/{held['id']}/cancel"):
                self.assertNotIn(bad, src, f"{f}: {bad}")
        for name in ("_email", "_form", "_call", "_call_and_email", "_place", "_cancel_reservation", "_push_later"):
            self.assertFalse(hasattr(VN, name), name)
        self.assertFalse(hasattr(M, "_reservation_notice_go"))
        from booking_signer import followup as FU, venue_notice as VNT
        self.assertFalse(hasattr(FU, "after_call") or hasattr(FU, "sms_ask") or hasattr(VNT, "after_call"))
        for f, fn in (("booking_signer/call_routes.py", "place"), ("booking_signer/ladder_routes.py", "send_email"),
                      ("booking_signer/form_rung.py", "send"), ("booking_signer/handover.py", "from_prepared_form"),
                      ("booking_signer/cancel_routes.py", "cancel_go"), ("booking_signer/venue_notice.py", "notice_go")):
            body = re.search(rf"async def {fn}\(.*?(?=\n(?:@router|async def |def |class )|\Z)", (BACKEND / f).read_text(), re.S).group(0)
            self.assertIn("refusal(", body, f)
            self.assertNotRegex(body, r"E\.send|send_sms|place_call", f)


class TheCallersAreAgAPIsOrTylers(unittest.TestCase):
    def test_no_key_or_no_slot_is_tylers(self):
        d = {"action": "request_email", "say": "request_email", "say_text": "x", "takeover": {"say": "Or take it over yourself."}, "channels": []}
        out = VN._to_tyler("Casa Gate", d)
        self.assertEqual((out["status"], out["sent"], out["line"]), ("to_tyler", False, VN.TO_TYLER))
        self.assertEqual(VN.TO_TYLER, RT.TO_TYLER)

    def test_the_executors_reach_only_agapi(self):
        src = inspect.getsource(VN._execute)
        self.assertIn("_via_agapi", src)
        self.assertIn("_call_question", src)
        self.assertNotRegex(src, r"await _(email|form|call|call_and_email)\(")
        self.assertNotRegex(inspect.getsource(VN._book_inner), r"/api/booking/(forms|emails|calls)")

    def test_health_calls_through_agapis_call_act(self):
        from products.health import agapi_call as AC
        src = inspect.getsource(AC)
        self.assertIn('route="call"', src)
        self.assertIn("VC.dial", src)
        self.assertNotIn("/api/booking/calls", (BACKEND / "products/health/turn.py").read_text())
        self.assertNotIn("/api/booking/calls", (BACKEND / "products/health/cita.py").read_text())

    def test_health_without_a_venues_key_is_tylers(self):
        from agapi import venue_submit as VS
        from booking_signer import guest_receipt as GR
        from products.health import agapi_call as AC
        from datetime import datetime
        with mock.patch.object(VS, "prepare", mock.AsyncMock(return_value={"ok": False, "error": {"code": "not_configured", "message": "x"}})), \
                mock.patch.object(GR, "address_of", mock.AsyncMock(return_value=None)):
            got = asyncio.run(AC.prepare("acct", "Kanoe Test Clinic", "+34600000000", datetime(2026, 11, 10, 10, 0),
                                         {"name": "Test Guest 319", "mobile_e164": "+15005550319"}, "a GP appointment"))
        self.assertEqual(got, {"ok": False, "say": VN.TO_TYLER})
        with mock.patch.object(VS, "prepare", mock.AsyncMock(return_value={"ok": False, "error": {"code": "invalid_input", "message": "x"}})), \
                mock.patch.object(GR, "address_of", mock.AsyncMock(return_value=None)):   # a phone alone isn't a venue AgAPI can record (yet)
            got = asyncio.run(AC.prepare("acct", "Centro de Salud X", "+34913690491", datetime(2026, 11, 10, 10, 0),
                                         {"name": "Test Guest 319", "mobile_e164": "+15005550319"}, "a GP appointment"))
        self.assertEqual(got, {"ok": False, "say": VN.TO_TYLER})


if __name__ == "__main__":
    unittest.main()
