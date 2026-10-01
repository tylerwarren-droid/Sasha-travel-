"""S-64 step 11 · the chat produces the object (booking_signer/chat_request.py): the parts a message states, and ONE
question for the first thing missing — the activity, the kind of time, the count and its unit. Nothing guessed.

    cd backend && python -m unittest tests.test_chat_request -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from booking_signer import chat_request as CR, handoff as HO, reservation as RS

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
WHO = {"name": "Tyler Warren", "account_id": "00000000-0000-4000-8000-000000000001"}
WHERE = {"venue_name": "La Contra", "timezone": "Europe/Madrid", "venue_ids": []}


def d(msg, lang="es"):
    return CR.draft(msg, NOW, lang)


class Complete(unittest.TestCase):
    def test_a_table_said_in_full_needs_nothing_more(self):
        x = d("Book a table for 2 on 2 October at 1pm")
        self.assertEqual((x["missing"], x["question"]), ([], None))
        o = CR.complete(x, who=WHO, where=WHERE)
        self.assertEqual((o["what"]["activity_venue_lang"], o["when"], o["how_many"], o["flow"]),
                         ("una mesa", {"mode": "at", "at": "2026-10-02T13:00"}, {"count": 2, "unit": "people"}, "book"))

    def test_a_tattoo_quote_asks_them_when(self):
        x = d("How much would a fine-line tattoo be?", lang="en")
        self.assertEqual(x["missing"], [])
        self.assertEqual((x["parts"]["flow"], x["parts"]["when"], x["parts"]["how_many"]),
                         ("quote_first", {"mode": "venue_proposes"}, {"count": 1, "unit": "pieces"}))

    def test_a_massage_in_a_window(self):
        x = d("A massage for one person on 3 October between 10am and 1pm")
        self.assertEqual(x["parts"]["when"], {"mode": "window", "window": {"earliest": "2026-10-03T10:00", "latest": "2026-10-03T13:00"}})
        self.assertEqual(x["parts"]["how_many"], {"count": 1, "unit": "people"})

    def test_when_do_they_have_space_is_an_availability_call(self):
        x = d("Can you find out when they have space for a massage for 2 people?", lang="en")
        self.assertEqual((x["parts"]["flow"], x["parts"]["when"]["mode"]), ("availability", "venue_proposes"))

    def test_sessions_are_counted_in_sessions(self):
        x = d("2 sessions of massage on 3 October at 11:00")
        self.assertEqual(x["parts"]["how_many"], {"count": 2, "unit": "sessions"})


class AsksOnlyWhatIsMissing(unittest.TestCase):
    def test_the_activity_first(self):
        x = d("I'd like something for 2 on Friday at 8pm")
        self.assertEqual((x["missing"][0], x["question"]), ("activity", "What would you like me to book?"))

    def test_then_the_kind_of_time(self):
        x = d("A table for 4 please")
        self.assertEqual((x["missing"], x["question"]), (["when"], "Which day and time — or shall I ask them when they have space?"))

    def test_then_how_many_in_the_right_unit(self):
        self.assertEqual(d("A table on 2 October at 1pm")["question"], "How many people is it for?")
        self.assertEqual(d("A massage on 3 October at 11:00")["question"], "How many people is it for?")

    def test_between_10_and_1_is_not_guessed(self):
        x = d("A table for 2 on 3 October between 10 and 1")
        self.assertIn("when", x["missing"])

    def test_an_incomplete_draft_is_never_completed(self):
        with self.assertRaises(RS.ReservationRefused):
            CR.complete(d("A table please"), who=WHO, where=WHERE)


class FindCarriesTheDraft(unittest.TestCase):
    def test_the_find_turn_carries_the_draft_and_the_psi_link_is_retired(self):
        turn = HO.booking_handoff("Book a table in Lisbon for 2 on 2 October at 8pm", now=NOW)
        self.assertEqual(turn["booking_find"], {"what": "table", "where": "Lisbon"})
        self.assertEqual(turn["reservation_draft"]["parts"]["how_many"], {"count": 2, "unit": "people"})
        self.assertEqual(turn["bookings"], [])


if __name__ == "__main__":
    unittest.main()
