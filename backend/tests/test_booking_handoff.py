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
    def test_everything_stated_goes_into_the_tab_link(self):
        t = booking_handoff("Book a table at Psi on 5 October at 8pm for 2", [], NOW)
        url = t["bookings"][0]["options"][0]["book_url"]
        self.assertEqual(urlsplit(url).path, "/booking-helper")
        self.assertEqual(parse_qs(urlsplit(url).query), {"venue": ["restaurante-psi"], "date": ["2026-10-05"], "time": ["20:00"], "party": ["2"], "profile": ["demo"]})
        self.assertNotIn("offer_id", t["bookings"][0]["options"][0])  # so the card renders a LINK, not a payment button
        self.assertIn("dry run", t["response"])
        self.assertIn("Monday 5 October", t["response"])
        self.assertEqual(t["messages"][-1], {"role": "assistant", "content": t["response"]})

    def test_what_was_not_said_is_asked_for_not_guessed(self):
        t = booking_handoff("book me a table at psi", [], NOW)
        self.assertEqual(parse_qs(urlsplit(t["bookings"][0]["options"][0]["book_url"]).query), {"venue": ["restaurante-psi"], "profile": ["demo"]})
        self.assertIn("Add the date, the time, how many people there", t["response"])

    def test_nothing_else_is_touched(self):
        self.assertIsNone(booking_handoff("find me a restaurant in Hanoi", [], NOW))


class TheHook(unittest.TestCase):
    def test_the_conductor_calls_it_before_anything_else_can(self):
        src = (BACKEND / "app" / "services" / "conductor.py").read_text(encoding="utf-8")
        self.assertIn("from booking_signer.handoff import booking_handoff", src)
        self.assertLess(src.index("_handoff = booking_handoff(user_message, conversation_history)"),
                        src.index("# ── Card choice (second half of a booking)"))

    def test_the_real_conduct_returns_the_handoff(self):
        from app.services.conductor import conduct  # the real one — the hook returns before any model is called
        t = asyncio.run(conduct("Book a table at Psi on 5 October at 8pm for 2"))
        self.assertEqual(t["bookings"][0]["options"][0]["name"], "Open my booking tab")


if __name__ == "__main__":
    unittest.main()
