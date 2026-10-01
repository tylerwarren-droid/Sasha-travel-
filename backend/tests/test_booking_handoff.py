"""S-26 · Sasha hands a Psi booking to her booking tab — and reads nothing she was not plainly told.

    cd backend && python -m unittest tests.test_booking_handoff -v
"""
import asyncio
import pathlib
import unittest
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from booking_signer.handoff import booking_handoff, is_psi_booking, plain_date, plain_party, plain_time

NOW = datetime(2026, 9, 29, 18, 0, tzinfo=timezone.utc)  # a Tuesday evening in Lisbon
BACKEND = pathlib.Path(__file__).parent.parent


class Recognition(unittest.TestCase):
    def test_only_a_booking_at_psi(self):
        for m, want in [("book a table at Psi", True), ("Can you reserve Psi for Saturday?", True),
                        ("tell me about Psi", False), ("book a table at Bom", False), ("psilocybin table", False)]:
            self.assertEqual(is_psi_booking(m), want, m)


class PlainValuesOnly(unittest.TestCase):
    def test_dates(self):
        for m, want in [("on 5 October", "2026-10-05"), ("the 5th of October", "2026-10-05"), ("October 5th", "2026-10-05"),
                        ("2026-10-05", "2026-10-05"), ("tomorrow", "2026-09-30"), ("on 1 September", "2027-09-01"),
                        ("next Friday", None), ("soon", None), ("31 February", None)]:
            self.assertEqual(plain_date(m, NOW), want, m)

    def test_times_only_on_psis_slots(self):
        for m, want in [("at 8pm", "20:00"), ("8:30 pm", "20:30"), ("20:00", "20:00"), ("1pm", "13:00"),
                        ("at 8", None), ("5pm", None), ("19:45", None)]:
            self.assertEqual(plain_time(m), want, m)

    def test_party(self):
        for m, want in [("for 2", 2), ("for two", 2), ("table for 4", 4), ("3 people", 3), ("party of six", 6),
                        ("for 8pm", None), ("for 30", None), ("a table", None)]:
            self.assertEqual(plain_party(m), want, m)


class TheTurn(unittest.TestCase):
    """S-66 (EU) step 5 · any kind of place, in any place: `booking_find` for the chat; the Psi link is retired."""

    def test_find_x_in_y_for_any_kind_of_place(self):
        for m, want in [("Find me a tattoo studio in Nairobi", {"what": "tattoo studio", "where": "Nairobi"}),
                        ("book a massage in Madrid for 2 on Friday", {"what": "massage", "where": "Madrid"}),
                        ("Can you reserve a kayak tour near Lisbon?", {"what": "kayak tour", "where": "Lisbon"}),
                        ("find a tattoo studio in Nairobi, KE", {"what": "tattoo studio", "where": "Nairobi", "country": "KE"}),
                        ("look for a restaurant in Hanoi tonight", {"what": "restaurant", "where": "Hanoi"})]:
            t = booking_handoff(m, [], NOW)
            self.assertEqual(t["booking_find"], want, m)
            self.assertIn("nobody is contacted by looking", t["response"])
            self.assertEqual(t["bookings"], [])                      # no console link, no card to the tab
            self.assertEqual(t["messages"][-1], {"role": "assistant", "content": t["response"]})

    def test_the_psi_link_is_retired_and_ordinary_chat_is_untouched(self):
        self.assertIsNone(booking_handoff("Book a table at Psi on 5 October at 8pm for 2", [], NOW))   # no "in Y": the drafts ask which place
        self.assertIsNone(booking_handoff("tell me about Hanoi", [], NOW))
        self.assertIsNone(booking_handoff("what's the weather in Madrid", [], NOW))

    def test_the_rest_of_the_message_is_kept_as_the_draft(self):
        t = booking_handoff("book a massage in Madrid for 2 on 3 October at 11:00", [], NOW)
        self.assertEqual(t["reservation_draft"]["parts"]["when"], {"mode": "at", "at": "2026-10-03T11:00"})
        self.assertEqual(t["reservation_draft"]["parts"]["how_many"], {"count": 2, "unit": "people"})


class TheHook(unittest.TestCase):
    def test_the_conductor_calls_it_before_anything_else_can(self):
        src = (BACKEND / "app" / "services" / "conductor.py").read_text(encoding="utf-8")
        self.assertIn("from booking_signer.handoff import booking_handoff", src)
        self.assertLess(src.index("_handoff = booking_handoff(user_message, conversation_history)"),
                        src.index("# ── Card choice (second half of a booking)"))

    def test_the_real_conduct_returns_the_find(self):
        from app.services.conductor import conduct  # the real one — the hook returns before any model is called
        t = asyncio.run(conduct("Find me a tattoo studio in Nairobi"))
        self.assertEqual(t["booking_find"], {"what": "tattoo studio", "where": "Nairobi"})


if __name__ == "__main__":
    unittest.main()
