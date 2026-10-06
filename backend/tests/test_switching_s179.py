"""Sasha 179 · automatic switching: the one line with its Back button, the mode label, the ambiguity question's shape."""
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from booking_signer import switching as SW


class Switching(unittest.TestCase):
    def test_a_new_place_is_one_line_with_back_first_and_the_label(self):
        items = [("text", "🎙 I heard: “a spa in Paris”"), ("text", "Here are the best-rated spas in Paris."), ("ask", "Which one?", [])]
        cur = SW.announce(items, {"k": "j", "label": "✈️ Vietnam, Nov"}, {"k": "j", "label": "📍 Paris"}, 1)
        SW.label_first(items, cur)
        self.assertEqual(items[1][0], "ask")
        self.assertIn("↪ Switching to Paris.", items[1][1])
        self.assertEqual(items[1][2], [("Back to Vietnam, Nov", "mback:j:✈️ Vietnam, Nov")])
        self.assertTrue(items[1][1].startswith("_Now: 📍 Paris_\n"))
        self.assertEqual(SW.label_of(items[1][1]), "📍 Paris")

    def test_a_trip_reads_your_x_trip_and_a_product_goes_back_by_its_word(self):
        items = [("text", "🗺 Vietnam")]
        SW.announce(items, {"k": "p", "p": "relocation", "label": "🏠 Move to Madrid"}, {"k": "j", "label": "✈️ Vietnam, Nov"}, 0)
        self.assertEqual(items[0][1], "↪ Switching to your Vietnam trip.")
        self.assertEqual(items[0][2], [("↩ Move to Madrid", "mback:p:relocation")])
        self.assertEqual(SW.back_to("mback:p:relocation"), ("p", "relocation"))

    def test_the_same_mode_says_nothing_and_nothing_named_keeps_it(self):
        items = [("text", "ok")]
        cur = SW.announce(items, {"k": "j", "label": "📍 Paris"}, None, 0)
        self.assertEqual(len(items), 1)
        self.assertEqual(cur["label"], "📍 Paris")

    def test_the_mode_is_read_back_from_the_last_reply(self):
        st = {"pending": None, "history": [{"role": "assistant", "content": "_Now: 📍 Paris_\nHere are…"}]}
        self.assertEqual(SW.before(st, datetime.now(timezone.utc))["label"], "📍 Paris")

    def test_book_my_flights_with_a_relocation_open_and_a_trip_asks_once(self):
        plans = [{"trip_id": "t1", "title": "Vietnam, Nov", "start": "2026-11-12", "cities": ["Hanoi"]}]
        with mock.patch("booking_signer.plan_store.plans", mock.AsyncMock(return_value=plans)):
            q = asyncio.run(SW.ambiguous("a", "book my flights", [], "relocation"))
            self.assertIsNotNone(q)
            self.assertEqual([t for t, _ in q[1]], ["Vietnam trip", "Move to Madrid"])
            self.assertIsNone(asyncio.run(SW.ambiguous("a", "book my flights", [], None)))          # nothing open: not ambiguous
            self.assertIsNone(asyncio.run(SW.ambiguous("a", "flights from Madrid to Hanoi", [], "relocation")))

    def test_product_idle_is_thirty_minutes(self):
        self.assertEqual(SW.PRODUCT_IDLE, timedelta(minutes=30))


if __name__ == "__main__":
    unittest.main()
