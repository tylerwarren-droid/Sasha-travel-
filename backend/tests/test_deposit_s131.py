"""Sasha 131 (4) · one-touch deposits: the test venue's deposit is a Stripe TEST-mode Payment Link, labelled a test
payment; a live key is refused; "paid" is Stripe's own completed checkout, never assumed.

    cd backend && python -m unittest tests.test_deposit_s131 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from booking_signer import test_deposit as TD


class Deposit(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.saved = TD.HTTP
        TD._LINK.clear()

        async def http(method, path, data=None):
            self.calls.append((method, path, dict(data or {})))
            if path == "/products":
                return 200, {"id": "prod_1"}
            if path == "/prices":
                return 200, {"id": "price_1"}
            if path == "/payment_links":
                return 200, {"id": "plink_1", "url": "https://buy.stripe.com/test_abc", "livemode": False}
            if path == "/checkout/sessions":
                return 200, {"data": self.sessions}
            return 404, {}
        TD.HTTP = http
        self.sessions = []

    def tearDown(self):
        TD.HTTP = self.saved
        TD._LINK.clear()

    def test_a_live_key_is_refused_and_no_key_says_so(self):
        for k in ("", "sk_live_123", "rk_live_9"):
            with mock.patch.dict(os.environ, {"STRIPE_TEST_SECRET_KEY": k}):
                self.assertIsNone(TD.key())
                self.assertIn("no Stripe TEST key", asyncio.run(TD.link())["why"])
        self.assertEqual(self.calls, [])

    def test_the_link_is_made_once_in_test_mode_and_labelled(self):
        with mock.patch.dict(os.environ, {"STRIPE_TEST_SECRET_KEY": "sk_test_x", "SASHA_TEST_DEPOSIT_EUR": "10"}):
            got = asyncio.run(TD.link())
            again = asyncio.run(TD.link())
        self.assertEqual(got, {"id": "plink_1", "url": "https://buy.stripe.com/test_abc"})
        self.assertEqual(again, got)
        self.assertEqual([c[1] for c in self.calls], ["/products", "/prices", "/payment_links"])     # once
        self.assertIn("TEST payment", self.calls[0][2]["name"])
        self.assertEqual(self.calls[1][2]["unit_amount"], 1000)
        m = TD.message(got["url"])
        self.assertIn("⚠ TEST payment — nothing is charged", m)
        self.assertIn("Apple Pay or your phone's saved card — I never see your card", m)

    def test_paid_is_stripes_completed_checkout_only(self):
        with mock.patch.dict(os.environ, {"STRIPE_TEST_SECRET_KEY": "sk_test_x"}):
            self.sessions = [{"status": "open", "payment_status": "unpaid", "created": 200}]
            self.assertIsNone(asyncio.run(TD.paid_since("plink_1", 100)))
            self.sessions = [{"status": "complete", "payment_status": "paid", "created": 50, "amount_total": 1000}]   # before: not this one
            self.assertIsNone(asyncio.run(TD.paid_since("plink_1", 100)))
            self.sessions = [{"status": "complete", "payment_status": "paid", "created": 150, "amount_total": 1000, "currency": "eur",
                              "payment_intent": "pi_1", "id": "cs_1", "livemode": False}]
            self.assertEqual(asyncio.run(TD.paid_since("plink_1", 100)), {"amount": 10.0, "currency": "EUR", "payment": "pi_1", "session": "cs_1"})
