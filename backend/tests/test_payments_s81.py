"""S-81 · payments: tier 0 and the mock card's removal (§7 tests 1, 2, 3, 6, 7). Offline.

    cd backend && python -m unittest tests.test_payments_s81 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import unittest
from unittest import mock

from booking_signer import calls as C, payments_t0 as PT0, reservation as RS

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACCOUNT = "88888888-8888-4888-8888-888888888888"


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


class TheMockCardIsGone(unittest.TestCase):
    def test_7_no_saved_card_anywhere_it_could_render(self):
        """'I've completed the payment with your card ending in 1003' was said with no payment: a fake success."""
        src = (ROOT / "app" / "services" / "conductor.py").read_text(encoding="utf-8")
        for gone in ("SAVED_CARD_LAST4", "saved_card_payload", "CARD_QUESTION_MARKER", "pay_saved_card", "completed the payment"):
            self.assertNotIn(gone, src, gone)
        self.assertIn('"saved_card": None', src)

    def test_the_book_it_turn_opens_the_real_payment(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        from app.services import conductor
        r = run(conductor.run_book_trip_intent("book the whole trip", []))
        self.assertEqual(r["data"]["action"], "await_payment")
        self.assertIn("nothing is charged or booked", r["response"])

    def test_reserve_refuses_a_saved_card(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        from fastapi.testclient import TestClient
        from app.main import app
        r = TestClient(app).post("/api/payments/reserve", json={"offer_id": "x", "payment_method": "saved_card", "card_last4": "1003"})
        self.assertIn(r.status_code, (401, 404, 422))
        if r.status_code == 422:
            self.assertIn("no card is on file", r.text)


class Reading:
    def __init__(self, words, raised=()):
        self.state, self.outcome, self.venue_words, self.raised = "answered", "unclear", words, list(raised)


class Tier0(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.saved = PT0.STORE
        PT0.STORE = PT0.MemoryPaymentStore()
        self.call = {"account_id": ACCOUNT, "trip_item_id": "t-1", "brief": {"purpose": "book", "date": "2026-10-03", "time": "21:00",
                                                                              "party": 2, "name": "Warren", "language": "es"}}

    def tearDown(self):
        PT0.STORE = self.saved

    def test_2_the_call_agrees_to_no_money_and_a_money_yes_stays_unclear(self):
        self.assertTrue(RS.CONSTRAINTS["no_card"])                              # Sasha never gives a card
        for must in ("Agree to no deposit and give no card", "payment link", "the guest pays them directly"):
            self.assertIn(must, C.DEPOSIT_RULE)
        for never in ("card number", "cvv", "expiry"):
            self.assertNotIn(never, C.DEPOSIT_RULE.lower())
        self.assertIsNotNone(C._MONEY.search("Sí, pero hay que dejar 20 euros de señal"))

    def test_1_one_amount_one_yes(self):
        pr = run(PT0.after_call(self.call, Reading("Sí. / Pero necesitamos una señal de 20 euros por tarjeta."), "Casa Lucio"))
        self.assertEqual((pr["amount_minor"], pr["payee"], pr["tier"]), (2000, "Casa Lucio", "guest_direct"))
        self.assertTrue(pr["read_back_lines"][0].startswith("Casa Lucio needs €20 deposit for 2026-10-03 at 21:00, 2 people."))
        self.assertIn("I never see your card", pr["read_back_lines"][1])
        other = PT0.read_back("Casa Lucio", 3000, "30 euros", "2026-10-03 at 21:00, 2 people")
        self.assertNotEqual(PT0.sha(other), pr["read_back_sha256"])                  # another amount, another yes
        self.assertIsNone(run(PT0.after_call(self.call, Reading("Sí, 20 euros de señal."), "Casa Lucio")))   # once per booking

    def test_3_tier0_flow(self):
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient
        from booking_signer import call_routes as CR, gate
        pr = run(PT0.after_call(self.call, Reading("Hace falta una señal de 20 €."), "Casa Lucio"))
        app = FastAPI()
        app.include_router(PT0.router, prefix="/api/booking")

        async def as_account(request: Request):
            request.state.account = ACCOUNT
        app.dependency_overrides[gate.require_booking_key] = as_account
        call = self.call

        class Rows:
            async def receipt_rows(self, a, t):
                return {"call": call}
        with mock.patch.object(CR, "CALL_STORE", Rows()), mock.patch("booking_signer.account.account_for", lambda r: ACCOUNT), \
                mock.patch.object(PT0, "ask_venue_for_link", mock.AsyncMock(return_value="sms")):
            c = TestClient(app)
            bad = c.post(f"/api/booking/payments/{pr['id']}/approve", json={"read_back_sha256": "0" * 64, "approval": {"how": "button"}})
            self.assertEqual(bad.json()["rule"], "read_back_mismatch")
            r = c.post(f"/api/booking/payments/{pr['id']}/approve",
                       json={"read_back_sha256": pr["read_back_sha256"], "approval": {"how": "whatsapp_button"}})
        self.assertEqual((r.json()["status"], r.json()["payer"]), ("link_sent", "guest_direct"))
        row = PT0.STORE.rows[pr["id"]]
        self.assertEqual((row["status"], row["link_asked_by"], row["approval"]["read_back_sha256"]), ("link_sent", "sms", pr["read_back_sha256"]))

    def test_6_no_column_holds_a_card_number(self):
        import re
        for p in (ROOT / "booking_signer" / "sql").glob("*.sql"):
            self.assertIsNone(re.search(r"\b(pan|card_number|cvc|cvv)\b\s+(text|varchar|bigint)", p.read_text(encoding="utf-8").lower()), p.name)


if __name__ == "__main__":
    unittest.main()
