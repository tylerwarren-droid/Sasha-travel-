"""Sasha 143 · A HOTEL STAY ON THE WEB (CR's rehearsal: "a hotel in Madrid, Spain from 2027-03-01 to 2027-03-04 for 1" answered
"a brief connection issue"; with a conversation behind it, it promised cards that never came). Now it is found on Google
as on WhatsApp, every card says only what its listing says (no invented price), and "none found" is said. Offline.

    cd backend && python -m unittest tests.test_hotel_web_s143 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import guest_whatsapp as GW, hotel_web as HW

A = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc)
SENTENCE = "a hotel in Madrid, Spain from 2027-03-01 to 2027-03-04 for 1"


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


def cand(i, name, rating=4.6):
    return {"place_id": f"pid-{i}", "name": name, "address": f"Calle {i}, Madrid", "rating": rating, "rating_count": 100 * i,
            "listing_url": f"https://www.google.com/maps/place/?q=place_id:pid-{i}"}


class HotelStayOnTheWeb(unittest.TestCase):
    def found(self, cands, status=200):
        seen = []

        async def api(account, method, path, body=None, timeout=None):
            seen.append((path, body))
            return status, {"candidates": cands, "ranking": {"orders": {"rated": [c["place_id"] for c in cands]}}}
        with mock.patch.object(GW, "api", api):
            return run(HW.web_turn(SENTENCE, A, NOW)), seen

    def test_the_hand_off_finds_real_hotels_with_the_stay_asked_for(self):
        out, seen = self.found([cand(1, "Hotel Uno"), cand(2, "Hotel Dos"), {"place_id": "sasha-test-venue", "name": "Test"}, cand(3, "Hotel Tres"), cand(4, "Hotel Cuatro")])
        self.assertEqual(seen[0][1], {"what": "hotel", "where": "Madrid, Spain", "country": "ES"})
        self.assertEqual([h["name"] for h in out["hotels"]], ["Hotel Uno", "Hotel Dos", "Hotel Tres"])   # never the test venue; 3 shown
        h = out["hotels"][0]
        self.assertEqual((h["checkin"], h["nights"], h["party"], h["city"], h["source"]), ("2027-03-01", 3, 1, "Madrid", "google"))
        self.assertNotIn("price_from", h)                                   # no price is invented
        self.assertIn("TEST", out["response"])
        self.assertIn("no hotel contacted", out["response"])
        self.assertEqual(out["intents"], ["hotel"])

    def test_none_found_is_said_never_promised(self):
        out, _ = self.found([])
        self.assertEqual(out["hotels"], [])
        self.assertIn("none to show", out["response"])
        self.assertNotIn("in a moment", out["response"])

    def test_not_a_stay_is_not_taken(self):
        for m in ("dinner for 2 in Madrid tomorrow at 9", "what hotels are good in Madrid?", "a hotel in Madrid"):
            with mock.patch.object(GW, "api", mock.AsyncMock(side_effect=AssertionError("no search"))):
                self.assertIsNone(run(HW.web_turn(m, A, NOW)), m)

    def test_the_conductor_answers_the_products_hand_off_with_the_cards(self):
        from app.services import conductor as CD

        async def products(*a, **k):
            return {"agent": "products", "response": "Your first nights next.", "quick_replies": [], "media": [], "handoff": SENTENCE}

        async def api(account, method, path, body=None, timeout=None):
            return 200, {"candidates": [cand(1, "Hotel Uno")], "ranking": {"orders": {"rated": ["pid-1"]}}}
        with mock.patch("products.web.web_turn", products), mock.patch.object(GW, "api", api), \
             mock.patch("booking_signer.itinerary_q.web_turn", mock.AsyncMock(return_value=None)):
            out = run(CD.conduct("next", [], user_id=A, signed_in=True))
        self.assertTrue(out["response"].startswith("Your first nights next."))
        self.assertEqual([h["name"] for h in out["hotels"]], ["Hotel Uno"])


if __name__ == "__main__":
    unittest.main()
