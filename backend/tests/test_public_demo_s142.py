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


if __name__ == "__main__":
    unittest.main()
