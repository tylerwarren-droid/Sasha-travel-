"""Sasha 135 · hotel "Reserve" as a TEST booking (no hotel contacted), next to the real "request from the hotel".

    cd backend && python -m unittest tests.test_hotel_test_s135 -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from booking_signer import calendar_sync as CS, hotel_test as HT, proactive as PR


class Words(unittest.TestCase):
    def test_the_read_back_never_says_confirmed_and_says_test_first(self):
        q = HT.quote("Tohe Riverside Lodge", "Hoi An", "2026-11-14", 2, 2)
        self.assertTrue(q["lines"][0].startswith("⚠ Test booking: no hotel contacted"))
        self.assertIn("a placeholder, not the hotel's rate", "\n".join(q["lines"]))
        self.assertNotIn("confirm", "\n".join(q["lines"]).lower())
        self.assertEqual(q["eur"], 240.0)

    def test_the_calendar_and_the_brief_say_test(self):
        body = CS.event_body({"date_time": datetime(2026, 11, 14, 15, tzinfo=timezone.utc), "provider_name": f"Tohe {HT.MARK}",
                              "booking_reference": "TEST-ABC123", "duration_minutes": 2640, "local_timezone": "Asia/Ho_Chi_Minh"}, "event")
        self.assertTrue(body["description"].startswith("TEST booking — no hotel or provider was contacted"))
        brief = PR.render("morning_brief", {}, {"items": [{"time": "15:00", "venue": f"Tohe {HT.MARK}", "status": "confirmed",
                                                          "booking_reference": "TEST-ABC123"}]})
        self.assertIn("(TEST booking)", brief)
        self.assertNotIn("(confirmed)", brief)

