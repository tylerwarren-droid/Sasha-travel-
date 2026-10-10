"""Sasha 226 · cancel or change a booked Duffel TEST flight — QUOTE (nothing changes, no money moves) then CONFIRM (only after
the yes). Offline: a fake Duffel answering with canned v2-shaped JSON.

    cd backend && python -m unittest tests.test_flight_manage_226 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from booking_signer import flight_manage as FM

SEG_OUT = {"origin": {"iata_code": "MAD"}, "destination": {"iata_code": "LGW"}, "departing_at": "2026-11-20T08:30:00",
           "arriving_at": "2026-11-20T10:05:00", "marketing_carrier": {"iata_code": "U2"}, "marketing_carrier_flight_number": "7640"}


def order(actions=("cancel", "change"), change_allowed=True, two_way=False):
    slices = [{"id": "sli_out", "origin": {"iata_code": "MAD"}, "destination": {"iata_code": "LGW"}, "segments": [SEG_OUT]}]
    if two_way:
        slices.append({"id": "sli_back", "origin": {"iata_code": "LGW"}, "destination": {"iata_code": "MAD"}, "segments": [
            {**SEG_OUT, "origin": {"iata_code": "LGW"}, "destination": {"iata_code": "MAD"}, "departing_at": "2026-11-27T18:00:00",
             "arriving_at": "2026-11-27T21:20:00", "marketing_carrier_flight_number": "7641"}]})
    return {"id": "ord_1", "live_mode": False, "booking_reference": "ABC123", "owner": {"name": "easyJet"},
            "available_actions": list(actions), "cancelled_at": None, "slices": slices,
            "conditions": {"change_before_departure": {"allowed": change_allowed, "penalty_amount": "45.00", "penalty_currency": "EUR"},
                           "refund_before_departure": {"allowed": True, "penalty_amount": "0.00", "penalty_currency": "EUR"}}}


def change_offer(oid, total, penalty="45.00", fn="7650"):
    return {"id": oid, "live_mode": False, "change_total_amount": total, "change_total_currency": "EUR", "new_total_amount": "200.00",
            "new_total_currency": "EUR", "penalty_total_amount": penalty, "penalty_total_currency": "EUR",
            "expires_at": "2026-10-10T14:05:00Z", "slices": {"add": [{"origin": {"iata_code": "MAD"}, "destination": {"iata_code": "LGW"},
                                                                      "segments": [{**SEG_OUT, "departing_at": "2026-11-27T07:15:00",
                                                                                    "arriving_at": "2026-11-27T08:50:00",
                                                                                    "marketing_carrier_flight_number": fn}]}],
                                                             "remove": [{"id": "sli_out"}]}}


class FakeDuffel:
    def __init__(self, the_order=None, refund="76.41", embed_offers=True, fail=None):
        self.calls, self.order, self.refund, self.embed, self.fail = [], the_order or order(), refund, embed_offers, fail or {}

    def paths(self):
        return [p for _m, p, _b in self.calls]

    async def __call__(self, method, path, body=None, params=None):
        self.calls.append((method, path, body))
        for prefix, answer in self.fail.items():
            if path.startswith(prefix):
                return answer
        if method == "GET" and path == "/air/orders/ord_1":
            return 200, {"data": self.order}
        if path == "/air/order_cancellations":
            return 201, {"data": {"id": "ore_1", "order_id": body["data"]["order_id"], "live_mode": False, "refund_amount": self.refund,
                                  "refund_currency": "EUR", "refund_to": "original_form_of_payment",
                                  "expires_at": "2026-10-10T14:05:00Z", "confirmed_at": None}}
        if path == "/air/order_cancellations/ore_1/actions/confirm":
            return 200, {"data": {"id": "ore_1", "order_id": "ord_1", "live_mode": False, "refund_amount": self.refund,
                                  "refund_currency": "EUR", "refund_to": "original_form_of_payment",
                                  "confirmed_at": "2026-10-10T13:40:00Z"}}
        offers = [change_offer("oco_dear", "120.00", fn="7652"), change_offer("oco_cheap", "60.50"), change_offer("oco_mid", "90.00", fn="7654")]
        if path == "/air/order_change_requests":
            return 201, {"data": {"id": "ocr_1", "order_id": "ord_1", "live_mode": False, "order_change_offers": offers if self.embed else []}}
        if path == "/air/order_change_offers":
            assert params == {"order_change_request_id": "ocr_1"}
            return 200, {"data": offers}
        if path == "/air/order_changes":
            return 201, {"data": {"id": "oce_1", "order_id": "ord_1", "live_mode": False, "change_total_amount": "60.50",
                                  "change_total_currency": "EUR", "confirmed_at": None}}
        if path == "/air/order_changes/oce_1/actions/confirm":
            return 200, {"data": {"id": "oce_1", "order_id": "ord_1", "live_mode": False, "change_total_amount": "60.50",
                                  "change_total_currency": "EUR", "confirmed_at": "2026-10-10T13:41:00Z"}}
        return 404, {"errors": [{"message": "no fake"}]}


def run(c):
    return asyncio.run(c)


class Base(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"DUFFEL_ACCESS_TOKEN": "duffel_test_x"})
        self.env.start()
        self.saved = FM.HTTP

    def tearDown(self):
        FM.HTTP = self.saved
        self.env.stop()

    def fake(self, **kw):
        FM.HTTP = f = FakeDuffel(**kw)
        return f


class Cancel(Base):
    def test_quote_then_confirm(self):
        f = self.fake()
        q = run(FM.cancel_quote("ord_1"))
        self.assertTrue(q["possible"])
        self.assertEqual((q["quote_id"], q["refund_amount"], q["refund_currency"], q["refund_to"]), ("ore_1", "76.41", "EUR", "original_form_of_payment"))
        self.assertEqual(q["lines"], ["I'll cancel your easyJet flight U2 7640 on Fri 20 Nov (booking ABC123).",
                                      "The airline refunds €76.41 to your original payment (Duffel's own quote, valid until 14:05 UTC).",
                                      "This is a TEST booking — no money moves."])
        self.assertFalse(any("confirm" in p for p in f.paths()), f.paths())   # a quote never confirms
        c = run(FM.cancel_confirm(q["quote_id"]))
        self.assertEqual(c["status"], "cancelled")
        self.assertEqual((c["cancellation_id"], c["refund_amount"], c["refund_currency"]), ("ore_1", "76.41", "EUR"))
        self.assertIn("/air/order_cancellations/ore_1/actions/confirm", f.paths())

    def test_zero_refund_is_said_as_no_refund(self):
        self.fake(refund="0.00")
        q = run(FM.cancel_quote("ord_1"))
        self.assertIn("There is no refund", q["lines"][1])
        self.assertNotIn("€", q["lines"][1])

    def test_not_available_is_said_plainly(self):
        f = self.fake(the_order=order(actions=("change",)))
        q = run(FM.cancel_quote("ord_1"))
        self.assertFalse(q["possible"])
        self.assertIn("easyJet doesn't allow cancelling this booking through our booking system (Duffel)", q["say"])
        self.assertEqual(f.paths(), ["/air/orders/ord_1"])   # never asked Duffel to cancel

    def test_provider_error_is_its_own_words(self):
        self.fake(fail={"/air/order_cancellations": (422, {"errors": [{"message": "The order cannot be cancelled after departure"}]})})
        q = run(FM.cancel_quote("ord_1"))
        self.assertIn("The order cannot be cancelled after departure", q["why"])
        self.fake(fail={"/air/order_cancellations/ore_1": (422, {"errors": [{"message": "Cancellation has expired"}]})})
        c = run(FM.cancel_confirm("ore_1"))
        self.assertEqual(c["status"], "not_cancelled")
        self.assertEqual(c["provider_words"], "Cancellation has expired")

    def test_outage_and_garbage_never_raise(self):
        async def boom(*a, **k):
            raise TimeoutError()
        FM.HTTP = boom
        self.assertTrue(run(FM.cancel_quote("ord_1")).get("outage"))
        self.fake(fail={"/air/orders": (200, {"data": "not a dict"})})
        self.assertIn("why", run(FM.cancel_quote("ord_1")))
        self.fake(fail={"/air/order_cancellations": (201, {"data": {"live_mode": True}})})
        self.assertIn("LIVE", run(FM.cancel_quote("ord_1"))["why"])

    def test_live_token_refused_before_any_call(self):
        f = self.fake()
        with mock.patch.dict(os.environ, {"DUFFEL_ACCESS_TOKEN": "duffel_live_x"}):
            self.assertIn("TEST token", run(FM.cancel_quote("ord_1"))["why"])
            self.assertEqual(run(FM.cancel_confirm("ore_1"))["status"], "not_cancelled")
        self.assertEqual(f.calls, [])


class Change(Base):
    def test_quote_picks_the_cheapest_and_says_total_and_penalty(self):
        f = self.fake()
        q = run(FM.change_quote("ord_1", "2026-11-27", "out"))
        self.assertTrue(q["possible"])
        self.assertEqual((q["change_offer_id"], q["change_total_amount"], q["change_total_currency"], q["penalty_amount"]),
                         ("oco_cheap", "60.50", "EUR", "45.00"))
        self.assertEqual(q["new_flights"], "U2 7650")
        self.assertEqual(q["departs"], "2026-11-27T07:15:00")
        self.assertEqual(q["lines"], [
            "I'll move your easyJet flight U2 7640 on Fri 20 Nov to U2 7650, Fri 27 Nov 07:15 MAD → 08:50 LGW (booking ABC123).",
            "The change costs €60.50 in total, including the airline's €45.00 change fee (Duffel's own quote, valid until 14:05 UTC).",
            "This is a TEST booking — no money moves."])
        req = next(b for _m, p, b in f.calls if p == "/air/order_change_requests")["data"]
        self.assertEqual(req["slices"], {"remove": [{"slice_id": "sli_out"}],
                                         "add": [{"origin": "MAD", "destination": "LGW", "departure_date": "2026-11-27", "cabin_class": "economy"}]})
        self.assertFalse(any("confirm" in p or p == "/air/order_changes" for p in f.paths()), f.paths())   # a quote changes nothing

    def test_offers_fetched_when_not_embedded(self):
        f = self.fake(embed_offers=False)
        q = run(FM.change_quote("ord_1", "2026-11-27"))
        self.assertEqual(q["change_offer_id"], "oco_cheap")
        self.assertIn("/air/order_change_offers", f.paths())

    def test_confirm_pays_from_test_balance(self):
        f = self.fake()
        c = run(FM.change_confirm("oco_cheap"))
        self.assertEqual((c["status"], c["order_change_id"], c["booking_reference"]), ("changed", "oce_1", "ABC123"))
        body = next(b for _m, p, b in f.calls if p == "/air/order_changes/oce_1/actions/confirm")
        self.assertEqual(body, {"data": {"payment": {"type": "balance", "amount": "60.50", "currency": "EUR"}}})

    def test_not_allowed_by_conditions_is_said_plainly(self):
        f = self.fake(the_order=order(change_allowed=False))
        q = run(FM.change_quote("ord_1", "2026-11-27", "out"))
        self.assertFalse(q["possible"])
        self.assertIn("easyJet doesn't allow changing this booking through our booking system (Duffel) — the fare doesn't allow changes", q["say"])
        self.assertEqual(f.paths(), ["/air/orders/ord_1"])

    def test_not_in_available_actions(self):
        self.fake(the_order=order(actions=("cancel",)))
        q = run(FM.change_quote("ord_1", "2026-11-27"))
        self.assertFalse(q["possible"])
        self.assertIn("doesn't allow changing", q["say"])

    def test_which_leg_on_a_return(self):
        self.fake(the_order=order(two_way=True))
        self.assertEqual(run(FM.change_quote("ord_1", "2026-11-28"))["ask"], "leg")
        f = self.fake(the_order=order(two_way=True))
        run(FM.change_quote("ord_1", "2026-11-28", "back"))
        req = next(b for _m, p, b in f.calls if p == "/air/order_change_requests")["data"]
        self.assertEqual(req["slices"]["remove"], [{"slice_id": "sli_back"}])
        self.assertEqual(req["slices"]["add"][0]["origin"], "LGW")

    def test_provider_error_is_its_own_words(self):
        self.fake(fail={"/air/order_change_requests": (422, {"errors": [{"message": "Order change is not supported for this airline"}]})})
        q = run(FM.change_quote("ord_1", "2026-11-27"))
        self.assertIn("Order change is not supported for this airline", q["why"])
        self.fake(fail={"/air/order_changes/oce_1": (422, {"errors": [{"message": "Insufficient balance"}]})})
        c = run(FM.change_confirm("oco_cheap"))
        self.assertEqual((c["status"], c["order_change_id"], c["provider_words"]), ("not_changed", "oce_1", "Insufficient balance"))

    def test_bad_date_never_calls(self):
        f = self.fake()
        self.assertIn("YYYY-MM-DD", run(FM.change_quote("ord_1", "27/11"))["why"])
        self.assertEqual(f.calls, [])


if __name__ == "__main__":
    unittest.main()
