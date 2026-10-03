"""Sasha 136 · Stripe's return lands on a PUBLIC page — no sign-in — that says "Paid (TEST) — check WhatsApp" and the booking's
outcome once known; leaving the page says nothing was paid.

    cd backend && python -m unittest tests.test_test_pay_page_s136 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import gate, test_deposit as TD

SID = "cs_test_a1H1t51vSf63YRW53ELoSRZuTn"


class ReturnPage(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(TD.public, prefix="/api/booking")
        self.c = TestClient(app)
        self.saved = TD.HTTP
        TD.OUTCOMES.clear()
        self.session = {"status": "open"}

        async def stripe(method, path, data=None):
            if path.startswith("/checkout/sessions/"):
                return 200, {**self.session, "livemode": False}
            if path == "/checkout/sessions":
                self.made = data
                return 200, {"id": SID, "url": "https://checkout.stripe.com/c/pay/x", "livemode": False}
            return 404, {}
        TD.HTTP = stripe
        p = mock.patch.dict(os.environ, {"STRIPE_TEST_SECRET_KEY": "sk_test_x", "SASHA_PUBLIC_BASE": "https://sasha.test"})
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        TD.HTTP = self.saved

    def test_it_needs_no_sign_in(self):
        self.assertIn(("GET", "/api/booking/test-pay/done"), gate.EXEMPT)
        self.assertIn(("GET", "/api/booking/test-pay/back"), gate.EXEMPT)

    def test_stripe_returns_to_it_with_its_own_session_id(self):
        asyncio.run(TD.checkout("377.90", "EUR", "x", "r"))
        self.assertEqual(self.made["success_url"], "https://sasha.test/api/booking/test-pay/done?s={CHECKOUT_SESSION_ID}")
        self.assertEqual(self.made["cancel_url"], "https://sasha.test/api/booking/test-pay/back?s={CHECKOUT_SESSION_ID}")

    def test_unpaid_paid_then_booked(self):
        t = self.c.get(f"/api/booking/test-pay/done?s={SID}").text
        self.assertIn("Payment not recorded yet", t)
        self.assertIn('http-equiv="refresh"', t)
        self.session = {"status": "complete", "payment_status": "paid", "amount_total": 37790, "currency": "eur", "payment_intent": "pi_1"}
        t = self.c.get(f"/api/booking/test-pay/done?s={SID}").text
        self.assertIn("Paid (TEST). Sasha is booking it — check WhatsApp.", t)
        self.assertIn("TEST — nothing is charged", t)
        TD.note(SID, True, "✅ Booked (TEST): ZZ 3551. Reference B2QEPT.")
        t = self.c.get(f"/api/booking/test-pay/done?s={SID}").text
        self.assertIn("Paid (TEST) — booked (TEST)", t)
        self.assertIn("Reference B2QEPT", t)
        self.assertNotIn('http-equiv="refresh"', t)

    def test_a_made_up_link_says_so_and_back_says_nothing_was_paid(self):
        self.assertIn("a test payment Sasha made", self.c.get("/api/booking/test-pay/done?s=<script>").text)
        self.assertIn("nothing was paid and nothing was booked", self.c.get(f"/api/booking/test-pay/back?s={SID}").text)
