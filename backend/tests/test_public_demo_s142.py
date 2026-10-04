"""Sasha 142 · THE PUBLIC DEMO IS NOBODY'S (CR's finding, 4 Oct 2026): a web visitor with no sign-in was the founder's
own account, and a phone that wasn't signed in was shown his itinerary. Now:
  · no token, no founder session → PUBLIC_DEMO_ID, its own empty account;
  · `x-sasha-session: founder` counts only WITH the booking key (the site's proxy, after the founder's cookie);
  · the products and the itinerary questions never run for the public demo. Offline.

    cd backend && python -m unittest tests.test_public_demo_s142 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from starlette.requests import Request

from app.services import chat_account as CA, chat_store
from booking_signer import identity

FOUNDER = chat_store.DEMO_USER_ID


def req(headers: dict) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]})


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


class WhoIsTheVisitor(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": "k-right", "FOUNDER_ACCOUNT_ID": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_no_sign_in_is_the_public_demo_never_the_founder(self):
        a = run(CA.chat_account(req({})))
        self.assertEqual(a, CA.PUBLIC_DEMO_ID)
        self.assertNotEqual(a, FOUNDER)
        self.assertFalse(CA.signed_in(a))

    def test_the_session_header_alone_names_nobody(self):
        self.assertEqual(run(CA.chat_account(req({"x-sasha-session": "founder"}))), CA.PUBLIC_DEMO_ID)

    def test_a_wrong_key_names_nobody(self):
        self.assertEqual(run(CA.chat_account(req({"x-sasha-session": "founder", "x-sasha-booking-key": "k-wrong"}))), CA.PUBLIC_DEMO_ID)

    def test_no_key_configured_names_nobody(self):
        with mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": ""}):
            self.assertEqual(run(CA.chat_account(req({"x-sasha-session": "founder", "x-sasha-booking-key": ""}))), CA.PUBLIC_DEMO_ID)

    def test_the_proxy_with_the_key_is_the_founder(self):
        a = run(CA.chat_account(req({"x-sasha-session": "founder", "x-sasha-booking-key": "k-right"})))
        self.assertEqual(a, identity.founder_account())
        self.assertTrue(CA.signed_in(a))

    def test_the_demo_itinerary_and_offers_are_not_the_publics(self):
        legacy = {"user_id": None}   # no owner recorded = the founder's demo data
        with mock.patch.object(chat_store, "get_itinerary", mock.AsyncMock(return_value=legacy)), \
             mock.patch.object(chat_store, "get_offer", mock.AsyncMock(return_value=legacy)):
            self.assertIsNone(run(CA.own_itinerary("it-1", CA.PUBLIC_DEMO_ID)))
            self.assertIsNone(run(CA.own_offer("of-1", CA.PUBLIC_DEMO_ID)))


class ThePublicDemoAsksAboutBookings(unittest.TestCase):
    def test_the_itinerary_and_products_are_not_run(self):
        from app.services import conductor as CD
        called, products = [], []

        async def spy(*a, **k):
            called.append(a)
            return None

        async def products_spy(*a, **k):
            products.append(k.get("signed_in"))
            return None
        with mock.patch("booking_signer.itinerary_q.web_turn", spy), mock.patch("products.web.web_turn", products_spy):
            try:
                run(CD.conduct("what's my itinerary this week?", [], user_id=CA.PUBLIC_DEMO_ID, signed_in=False))
            except Exception:
                pass   # the model path may be unavailable offline: what matters is what ran before it
        self.assertEqual(called, [])                       # the itinerary is never read for the public demo
        self.assertTrue(all(x is False for x in products))  # the products are told: not signed in (they refuse)


class TheVoicePage(unittest.TestCase):
    """Sasha 143 · /voice/conductor acts for the same account the chat would: the founder through the site's pass-through,
    the public demo for a visitor — it used to call conduct() with no account at all."""

    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        from fastapi.testclient import TestClient
        from app.main import app
        self.env = mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": "k-right", "FOUNDER_ACCOUNT_ID": "", "CONDUCTOR_API_SECRET": ""})
        self.env.start()
        self.c = TestClient(app)

    def tearDown(self):
        self.env.stop()

    def turn(self, headers):
        seen = {}

        async def fake_conduct(transcript, history, **kw):
            seen.update(kw)
            return {"response": "ok", "intents": [], "photos": []}

        async def fake_stt(audio, mime):
            return {"transcript": "what is my itinerary"}

        async def fake_tts(text):
            return b""
        with mock.patch("app.api.voice_conductor.conduct", fake_conduct), \
             mock.patch("app.api.voice_conductor.transcribe_audio", fake_stt), \
             mock.patch("app.api.voice_conductor.text_to_speech", fake_tts, create=True):
            r = self.c.post("/api/voice/conductor", files={"audio": ("r.webm", b"x", "audio/webm")}, data={"conversation_history": "[]"}, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        return seen

    def test_a_visitor_is_the_public_demo(self):
        seen = self.turn({})
        self.assertEqual((seen.get("user_id"), seen.get("signed_in")), (CA.PUBLIC_DEMO_ID, False))

    def test_the_founder_through_the_pass_through_is_himself(self):
        seen = self.turn({"x-sasha-session": "founder", "x-sasha-booking-key": "k-right"})
        self.assertEqual((seen.get("user_id"), seen.get("signed_in")), (identity.founder_account(), True))

    def test_the_header_without_the_key_is_nobody(self):
        seen = self.turn({"x-sasha-session": "founder"})
        self.assertEqual(seen.get("user_id"), CA.PUBLIC_DEMO_ID)


if __name__ == "__main__":
    unittest.main()
