"""Sasha 101 · a SPOKEN booking request reaches the same booking as a typed one — the founder's voice retry got no cards
and "9am on Saturday" for dinner. Speech arrives in fragments, without "book", with a bare "at nine". Offline.

    cd backend && python -m unittest tests.test_spoken_booking_sasha101 -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from booking_signer import handoff as H

FRIDAY = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)
USER = lambda t: {"role": "user", "content": t}
SASHA = lambda t: {"role": "assistant", "content": t}


class Spoken(unittest.TestCase):
    def find(self, said, history=()):
        r = H.booking_handoff(said, list(history), FRIDAY)
        return (r or {}).get("booking_find"), (((r or {}).get("reservation_draft") or {}).get("parts") or {}).get("when")

    def test_said_without_book_keeping_every_qualifier(self):
        f, when = self.find("I'd like to book a luxury dinner for two in Chamberí on Saturday at nine")
        self.assertEqual(f, {"what": "luxury dinner", "where": "Chamberí", "open_at": "2026-10-03T21:00"})
        self.assertEqual(when, {"mode": "at", "at": "2026-10-03T21:00"})
        f, _ = self.find("Can you get us a table for 2 at a luxury restaurant in Chamberí, Saturday at 9?")
        self.assertEqual(f, {"what": "luxury restaurant", "where": "Chamberí", "open_at": "2026-10-03T21:00"})

    def test_a_request_said_in_two_pieces_is_one_request(self):
        f, when = self.find("In Chamberí on Saturday at nine.", [USER("Book a luxury dinner for two."), SASHA("Of course.")])
        self.assertEqual((f["what"], f["where"], when["at"]), ("luxury dinner", "Chamberí", "2026-10-03T21:00"))

    def test_nine_for_dinner_is_21_00_two_for_lunch_is_14_00_nine_for_breakfast_is_09_00(self):
        self.assertEqual(H.context_time("dinner for two on Saturday at nine"), "21:00")
        self.assertEqual(H.context_time("a table at 9"), "21:00")
        self.assertEqual(H.context_time("lunch at two"), "14:00")
        self.assertEqual(H.context_time("breakfast at nine"), "09:00")
        self.assertEqual(H.context_time("dinner at nine in the morning"), "09:00")
        self.assertIsNone(H.context_time("see the museum at nine"))                  # no meal: asked, never guessed

    def test_what_is_not_a_booking_stays_out(self):
        self.assertEqual(self.find("I want to see the museum in Madrid"), (None, None))
        self.assertEqual(self.find("I like the food in Hanoi"), (None, None))


if __name__ == "__main__":
    unittest.main()
