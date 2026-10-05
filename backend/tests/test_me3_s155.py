"""Sasha 155 · Me3 everywhere: "tell me about RelocateMe / CampusMe / EspañaMe" → two sentences, then that product's mode.
Offline.

    cd backend && python -m unittest tests.test_me3_s155 -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from booking_signer import me3


class Asked(unittest.TestCase):
    def test_the_ways_it_is_asked(self):
        for m, want in (("tell me about RelocateMe", "relocation"), ("what is CampusMe?", "campus"), ("tell me about Españame", "espana"),
                        ("Tell me more about España Me", "espana"), ("open campus me", "campus"), ("RelocateMe", "relocation"),
                        ("switch to EspanaMe", "espana")):
            self.assertEqual(me3.asked(m), want, m)
        for m in ("dinner for 2 in Madrid", "I'm relocating to Madrid", "campus visits at Yale"):
            self.assertIsNone(me3.asked(m), m)

    def test_two_sentences_each_with_its_limits(self):
        for k, s in me3.INTRO.items():
            self.assertLessEqual(s.count(". "), 2, k)
        self.assertIn("never", me3.INTRO["relocation"])
        self.assertIn("concept", me3.INTRO["espana"])
        self.assertIn("test bookings for now", me3.INTRO["campus"])


class OnTheWebAndTheVoice(unittest.TestCase):
    def test_the_conductor_explains_then_opens_the_mode(self):
        from app.services import conductor as CD
        seen = {}

        async def web_turn(user_id, message, mode=None, payload=None, now=None, signed_in=None):
            seen.update(mode=mode, signed_in=signed_in, message=message)
            return {"agent": "products", "response": "Is this your first application, or a renewal?", "quick_replies": [], "media": []}
        with mock.patch("products.web.web_turn", web_turn):
            out = asyncio.new_event_loop().run_until_complete(
                CD.conduct("tell me about RelocateMe", [], user_id="g-1", signed_in=True))
        self.assertEqual(seen, {"mode": "relocation", "signed_in": True, "message": ""})
        self.assertTrue(out["response"].startswith("RelocateMe gets your first Spanish residence application ready"))
        self.assertIn("first application, or a renewal?", out["response"])
        self.assertEqual(out["product_mode"], "relocation")


if __name__ == "__main__":
    unittest.main()
