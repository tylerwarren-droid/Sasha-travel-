"""Sasha 363 · MONEY MOVES ONLY ON A CONFIRMED BOOKING — hold → book → capture; release on refusal; never a refund after a capture.

Found (Tyler's dry run, 9 Nov 20:45–20:47, iPhone, TEST, one €41.47 easyJet U2 7640 MAD→LIS): Apple Pay succeeded, THEN Duffel refused the
order ("Field 'phone_number' is invalid": the booking contact was +447700900123, Ofcom's fictional drama range). The money had already
moved.

    cd backend && python -m unittest tests.test_s363_one_confirmation -v
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import re
import unittest
from unittest import mock

from booking_signer import paid_watch as PWT, test_deposit as TD, travel as T

run = asyncio.run
ROOT = pathlib.Path(__file__).resolve().parents[1]


class FakeStripe:
    """Stripe TEST as it answers: a checkout session complete with its PaymentIntent HELD (manual capture)."""

    def __init__(self, amount=4147):
        self.calls, self.amount = [], amount
        self.pi = {"id": "pi_1", "status": "requires_capture", "amount": amount, "livemode": False}

    async def __call__(self, method, path, data=None):
        self.calls.append((method, path, dict(data or {})))
        if path.startswith("/checkout/sessions") and method == "POST":
            return 200, {"id": "cs_1", "url": "https://checkout.stripe.test/cs_1", "livemode": False}
        if path.startswith("/checkout/sessions/"):
            return 200, {"id": "cs_1", "status": "complete", "payment_status": "unpaid", "payment_intent": "pi_1", "amount_total": self.amount,
                         "currency": "eur", "livemode": False}
        if path == "/payment_intents" and method == "POST":
            return 200, {"id": "pi_2", "livemode": False}
        if path.endswith("/capture"):
            self.pi.update(status="succeeded", amount_received=data["amount_to_capture"])
            return 200, dict(self.pi)
        if path.endswith("/cancel"):
            self.pi["status"] = "canceled"
            return 200, dict(self.pi)
        if path.startswith("/payment_intents/"):
            return 200, dict(self.pi)
        return 404, {}

    def moved(self):
        return [(p.rsplit("/", 1)[-1], d.get("amount_to_capture")) for m, p, d in self.calls if p.endswith(("/capture", "/cancel"))]


class Row:
    """paid_watch's row for the session (its claim and its result), in memory."""

    def __init__(self, kind="flight"):
        self.notes = PWT.MARK + json.dumps({"sid": "cs_1", "account": "a1", "kind": kind, "card": {"id": "off_1"}})

    async def run(self, fn):
        return await fn(self)

    async def fetchrow(self, q, *a):
        if q.startswith("select"):
            return {"id": "row1", "status": "pending", "provider_name": None, "booking_reference": None, "escalation_notes": self.notes}
        if q.startswith("update") and "escalation_notes like" in q and self.notes.startswith(PWT.MARK):
            self.notes = PWT.CLAIM + self.notes[len(PWT.MARK):]
            return {"escalation_notes": self.notes}
        return None

    async def execute(self, q, *a):
        return "UPDATE 1"


class HoldThenCapture(unittest.TestCase):
    def setUp(self):
        self.stripe = FakeStripe()
        self.p = [mock.patch.object(TD, "HTTP", self.stripe), mock.patch.object(TD, "key", lambda: "sk_test_x"),
                  mock.patch.object(TD, "note", lambda *a, **k: None)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in reversed(self.p):
            x.stop()

    def settle(self, result, kind="flight"):
        row = Row(kind)

        async def fulfil(row_id, payload):
            return dict(result)
        with mock.patch.object(PWT, "_run", lambda: row.run), mock.patch.object(PWT, "fulfil", fulfil), \
                mock.patch("booking_signer.live_events.on_settled", mock.AsyncMock()):
            return run(PWT.settle("cs_1"))

    def test_every_payment_is_a_hold(self):
        run(TD.checkout("41.47", "EUR", "a flight", "ref1", embedded=True, where="here"))
        run(TD.intent_saved({"customer": "cus_1", "id": "pm_1"}, "41.47", "EUR", "a flight", "ref1"))
        made = [d for m, p, d in self.stripe.calls if m == "POST" and p in ("/checkout/sessions", "/payment_intents")]
        self.assertEqual([d.get("payment_intent_data[capture_method]") or d.get("capture_method") for d in made], ["manual", "manual"])

    def test_confirmed_captures_exactly_the_hold(self):
        r = self.settle({"status": "booked", "say": "✅ Booked: easyJet U2 7640"})
        self.assertEqual(r["status"], "booked")
        self.assertEqual(self.stripe.moved(), [("capture", 4147)])

    def test_refused_releases_and_never_captures(self):
        r = self.settle({"status": "failed", "say": "The flight wasn't booked: x. " + PWT.NOTHING_TAKEN})
        self.assertEqual(self.stripe.moved(), [("cancel", None)])                     # released — no capture, no refund
        self.assertIn("Nothing was taken", r["say"])

    def test_a_partly_booked_trip_captures_only_what_was_confirmed(self):
        self.settle({"status": "booked", "say": "Partly booked:", "booked_eur": 30.0}, kind="trip")
        self.assertEqual(self.stripe.moved(), [("capture", 3000)])                   # the rest of the hold: released by Stripe


class TheSupplierSaysWhy(unittest.TestCase):
    def test_dufffels_own_reason_in_plain_words_and_nothing_taken(self):
        async def refused(*a, **k):
            return {"why": "Duffel (test) refused the order: Field 'phone_number' is invalid"}

        async def none(*a, **k):
            return None
        row = Row()
        with mock.patch.object(PWT, "_run", lambda: row.run), mock.patch.object(T, "order", refused), \
                mock.patch("booking_signer.trip_book._same_or_cheaper", none):
            r = run(PWT.fulfil("row1", {"sid": "cs_1", "account": "a1", "kind": "flight",
                                       "card": {"id": "off_1", "flights": "U2 7640", "from": "MAD", "to": "LIS", "amount": "41.47", "currency": "EUR"}}))
        self.assertEqual(r["status"], "failed")
        self.assertIn("the airline didn't accept the traveller's phone number", r["say"])
        self.assertIn("Nothing was taken", r["say"])
        self.assertNotIn("went through", r["say"])


class ARealMobileBeforeAnyHold(unittest.TestCase):
    """The cause, at its source: Sasha gave Duffel +447700900123 (Ofcom's fictional drama range). Only a mobile a supplier accepts goes to
    one; without it, nothing is held — she asks first."""

    def test_the_suppliers_rule(self):
        from booking_signer.contacts import supplier_mobile
        self.assertIsNone(supplier_mobile("+447700900123"))
        self.assertEqual(supplier_mobile("+44 7911 123456"), "+447911123456")
        self.assertIsNone(supplier_mobile("not a number"))

    def test_pay_asks_for_the_mobile_before_any_hold(self):
        from booking_signer import basket_book as BB, guest_whatsapp as GW, passengers as PX
        stripe = FakeStripe()

        async def contact(account, method, path, body=None):
            return 200, {"contact": {"name": "Sam Fictional", "mobile_e164": "+447700900123"}}

        async def saved(account):
            return [{"given_name": "Sam", "family_name": "Fictional", "phone_e164": None}]
        with mock.patch.object(GW, "api", contact), mock.patch.object(PX, "saved", saved), mock.patch.object(TD, "HTTP", stripe):
            need = run(BB.mobile_needed("a1"))
        self.assertEqual(need["needs"], ["mobile"])
        self.assertIn("+447700900123 isn't a real one", need["why"])
        self.assertIn("Nothing has been held", need["why"])
        self.assertEqual(stripe.calls, [])                                               # no payment of any kind
        self.assertIn("mobile_needed(account)", (ROOT / "booking_signer" / "basket_book.py").read_text())

    def test_no_made_up_number_is_ever_sent(self):
        for f in ("booking_signer/travel.py", "booking_signer/passengers.py"):
            self.assertNotIn("+34600000000", (ROOT / f).read_text(), f)


class OneSource(unittest.TestCase):
    def test_money_moves_in_one_place_and_never_as_a_refund(self):
        """Whole class: a capture or a release is test_deposit.finish's alone; no refund anywhere; every path that books after a payment
        (settle, travel's own, the test hotel's) ends in finish."""
        hits = []
        for f in sorted((ROOT / "booking_signer").rglob("*.py")) + sorted((ROOT / "agapi").rglob("*.py")) + sorted((ROOT / "app").rglob("*.py")):
            s = f.read_text(encoding="utf-8", errors="ignore")
            if "/refunds" in s:   # a Stripe refund (an airline's own refund on a cancelled flight is the airline's, not ours)
                hits.append(f"{f.relative_to(ROOT)}: a Stripe refund")
            if f.name != "test_deposit.py" and re.search(r"/capture['\"]|/payment_intents/[^\"']*/cancel", s):
                hits.append(f"{f.relative_to(ROOT)}: money moved outside finish")
        self.assertEqual(hits, [])
        for f in ("booking_signer/paid_watch.py", "booking_signer/travel.py", "booking_signer/hotel_test.py"):
            self.assertIn("TD.finish(", (ROOT / f).read_text(), f)


if __name__ == "__main__":
    unittest.main()
