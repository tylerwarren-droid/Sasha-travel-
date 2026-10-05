"""Sasha 157 · every state honestly: "Requested — waiting for <venue>", then "Confirmed — <venue>: their words · their
ref" or "Declined — <venue>: their words", in the itinerary (web and chat) and in the calendar. Offline.

    cd backend && python -m unittest tests.test_states_s157 -v
"""
import asyncio
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import calendar_sync as CS, followup as FU, itinerary_q as IQ
from booking_signer.routes import status_words

REQ = {"what": {"activity": "dinner", "category": "restaurant"}, "how_many": {"count": 2, "unit": "people"}}


class Words(unittest.TestCase):
    def test_the_three_states_name_the_venue(self):
        self.assertEqual(status_words("requested", REQ, "Casa Lucio"), "Requested — waiting for Casa Lucio")
        self.assertEqual(status_words("confirmed", REQ, "Casa Lucio", "Confirmada la mesa, localizador 77", "77"),
                         "Confirmed — Casa Lucio: “Confirmada la mesa, localizador 77” · their ref 77")
        self.assertEqual(status_words("declined", REQ, "Casa Lucio", "Lo sentimos, estamos completos"),
                         "Declined — Casa Lucio: “Lo sentimos, estamos completos”")

    def test_without_a_venue_the_old_words_stay(self):
        self.assertEqual(status_words("requested", REQ), "Requested — waiting for the restaurant to confirm")
        self.assertEqual(status_words("proposed", REQ, "X"), "Not booked — they offered a different time or day; read what they said")


class Calendar(unittest.TestCase):
    def test_a_request_is_a_marked_tentative_event(self):
        item = {"date_time": datetime(2026, 12, 15, 20, 0, tzinfo=timezone.utc), "provider_name": "Casa Lucio", "party_size": 2}
        b = CS.event_body(item, CS.calendar_action("requested"))
        self.assertEqual(b["status"], "tentative")
        self.assertTrue(b["summary"].startswith("(requested) Casa Lucio"))
        self.assertIn("Not booked yet", b["description"])
        self.assertEqual(CS.calendar_action("confirmed"), "event")
        self.assertEqual(CS.calendar_action("declined"), "delete")


class Chat(unittest.TestCase):
    def test_the_chat_itinerary_says_the_state(self):
        r = {"time": "21:00", "venue": "Casa Lucio", "party": 2, "status": "requested", "status_words": "Requested — waiting for Casa Lucio"}
        self.assertEqual(IQ._what(r), "21:00 Casa Lucio, 2 people — Requested — waiting for Casa Lucio")


class Reply(unittest.TestCase):
    def test_their_written_no_is_declined(self):
        seen = {}

        class Store:
            async def email_any(self, _):
                return {"account_id": "a", "approval": {}}

            async def request_of_email(self, _):
                return {"when": {"mode": "at", "at": "2026-12-15T21:00"}, "how_many": {"count": 2, "unit": "people"},
                        "what": {"activity": "dinner", "activity_venue_lang": "cena", "category": "restaurant"}, "who": {"name": "T"}}

            async def reply_outcome(self, email_id, trip, attempt, text, now):
                seen.update(trip=trip, attempt=attempt)
        from booking_signer import ladder_routes as LR
        with mock.patch.object(LR, "LADDER_STORE", Store()):
            r = asyncio.run(FU.on_reply("e1", "No, lo sentimos, no tenemos mesa.", datetime.now(timezone.utc)))
        self.assertEqual(r["result"], "declined")
        self.assertEqual(seen, {"trip": "declined", "attempt": "declined"})



class EmailTestVenue(unittest.TestCase):
    def test_the_email_only_page_is_ours_and_has_no_form(self):
        from booking_signer import form_rung as FR, gate
        html = asyncio.run(FR.test_venue("email")).body.decode()
        self.assertIn("mailto:reservas-prueba@", html)
        self.assertIn("No es un restaurante real", html)
        self.assertNotIn("<form", html)
        self.assertIn(("GET", "/api/booking/test-venue/email"), gate.EXEMPT)


if __name__ == "__main__":
    unittest.main()
