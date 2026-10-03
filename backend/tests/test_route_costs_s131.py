"""Sasha 131 · cost and outcome per route, per booking; cost per CONFIRMED booking. Every number says its source."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from booking_signer import route_costs as RC


class Costs(unittest.TestCase):
    ROWS = [{"id": "a", "venue": "Botavara", "status": "unclear", "forms": 0, "emails": 1, "links": 0, "calls": [0.021, 0.035]},
            {"id": "b", "venue": "Sasha Test Venue", "status": "confirmed", "forms": 1, "emails": 0, "links": 0, "calls": []},
            {"id": "c", "venue": "Akiro", "status": "guest_booked", "forms": 0, "emails": 0, "links": 1, "calls": []}]

    def test_a_call_is_blands_own_price_and_an_unset_rate_is_unknown_never_zero(self):
        with mock.patch.dict(os.environ, {"SASHA_COST_EMAIL_EUR": "", "SASHA_USD_EUR": ""}):
            b = RC.booking_cost(self.ROWS[0])
        call = next(r for r in b["routes"] if r["route"] == "call")
        self.assertEqual((call["count"], call["usd"], call["eur"]), (2, 0.056, None))
        self.assertEqual(call["source"], "Bland's own price per call")
        email = next(r for r in b["routes"] if r["route"] == "email")
        self.assertIsNone(email["eur"])
        self.assertIn("SASHA_COST_EMAIL_EUR not set", email["source"])
        self.assertIsNone(b["eur"])

    def test_cost_per_confirmed_booking_divides_all_spend_by_the_confirmed(self):
        env = {"SASHA_COST_EMAIL_EUR": "0.001", "SASHA_COST_WHATSAPP_EUR": "0.05", "SASHA_COST_FORM_EUR": "0", "SASHA_USD_EUR": "0.9"}
        with mock.patch.dict(os.environ, env):
            s = RC.summary(self.ROWS)
        self.assertEqual((s["bookings"], s["confirmed"]), (3, 2))                  # guest_booked counts as booked
        self.assertEqual(s["eur_total"], round(0.001 + 0.056 * 0.9 + 0 + 0.05, 4))
        self.assertEqual(s["eur_per_confirmed"], round(s["eur_total"] / 2, 4))
        self.assertIsNone(s["note"])
        self.assertEqual(s["by_route"]["call"]["count"], 2)

    def test_nothing_confirmed_is_said_not_divided_by_zero(self):
        with mock.patch.dict(os.environ, {"SASHA_COST_EMAIL_EUR": "0.001", "SASHA_USD_EUR": "0.9"}):
            s = RC.summary(self.ROWS[:1])
        self.assertIsNone(s["eur_per_confirmed"])
