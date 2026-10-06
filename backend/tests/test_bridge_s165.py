"""Sasha 165 · THE BRIDGE: the plan on the account, bookings slotted into its days, one compact text. Offline.

    cd backend && python -m unittest tests.test_bridge_s165 -v
"""
import asyncio
import unittest
from datetime import date

from booking_signer import guest_whatsapp as GW, handoff_phone as HP, itinerary_q as IQ, plan_store as PS

PLAN = {"title": "Vietnam 12–20 Nov", "days": [
    {"day": 1, "city": "Hanoi", "title": "Arrive", "activities": [{"time": "Evening", "name": "Street food dinner in the Old Quarter"}]},
    {"day": 2, "city": "Hanoi", "title": "City", "activities": [{"time": "Afternoon", "name": "Spa afternoon"}]},
    {"day": 3, "city": "Hoi An", "title": "Old town", "activities": [{"time": "Morning", "name": "Lantern walk"}]}]}


class Dates(unittest.TestCase):
    def test_the_guests_own_words(self):
        t = date(2026, 10, 6)
        self.assertEqual(PS.dates_of("build Vietnam 12–20 Nov", 9, t), (date(2026, 11, 12), date(2026, 11, 20)))
        self.assertEqual(PS.dates_of("from 12 to 20 November please", 9, t), (date(2026, 11, 12), date(2026, 11, 20)))
        self.assertEqual(PS.dates_of("Vietnam from 12 Nov", 3, t), (date(2026, 11, 12), date(2026, 11, 14)))
        self.assertEqual(PS.dates_of("a week in Vietnam", 7, t), (None, None))


class Merge(unittest.TestCase):
    def test_bookings_land_on_their_day_and_replace_the_placeholder(self):
        p = {"trip_id": "t", "title": PLAN["title"], "start": date(2026, 11, 12), "end": date(2026, 11, 20), "plan": PLAN}
        rows = [{"id": "b1", "venue": "Chả Cá Thăng Long", "date": "2026-11-12", "time": "20:00", "status": "requested",
                 "status_words": "Requested — waiting for Chả Cá Thăng Long", "category": "restaurant", "type": "restaurant"},
                {"id": "b2", "venue": "Ink Hoi An", "date": "2026-11-14", "time": None, "status": "quoted",
                 "status_words": "Not booked — they gave a quote; read what they said", "category": "other", "type": "other"},
                {"id": "b3", "venue": "Outside", "date": "2026-12-01", "time": "20:00", "status": "confirmed", "category": "restaurant"}]
        m = PS.merge(p, rows)
        d1, d3 = m["days"][0], m["days"][2]
        self.assertEqual(d1["date"], "2026-11-12")
        self.assertEqual(d1["bookings"][0]["venue"], "Chả Cá Thăng Long")
        self.assertEqual(d1["activities"][0]["replaced_by"], "Chả Cá Thăng Long")      # the placeholder dinner, replaced
        self.assertEqual(d3["bookings"][0]["venue"], "Ink Hoi An")
        self.assertFalse(any(b["venue"] == "Outside" for d in m["days"] for b in d["bookings"]))   # outside the trip: as today
        t = "\n".join(PS.text(m))
        self.assertIn("Day 1", t)
        self.assertIn("Chả Cá Thăng Long: Requested", t)
        self.assertNotIn("Street food dinner", t)                                         # replaced, not shown twice


class Words(unittest.TestCase):
    def test_trip_questions_and_handoff(self):
        for m in ("show me my itinerary", "what does my Vietnam trip look like?", "what was I doing?", "carry on"):
            self.assertTrue(IQ.TRIP.search(m), m)
        self.assertFalse(IQ.TRIP.search("a hotel in Hoi An for my trip"))
        for m in ("send this to my phone", "Continue on my phone"):
            self.assertTrue(HP.asked(m), m)

    def test_not_a_voice_note(self):
        self.assertIsNone(asyncio.run(GW.voice_text({"NumMedia": "1", "MediaContentType0": "image/jpeg", "MediaUrl0": "https://x"})))
        self.assertIsNone(asyncio.run(GW.voice_text({"NumMedia": "0"})))


if __name__ == "__main__":
    unittest.main()
