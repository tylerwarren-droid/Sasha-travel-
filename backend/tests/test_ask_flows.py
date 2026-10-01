"""S-64 step 9 · the ASKING flows — quote-first and "when do you have space" — from reservation/1.
No booking, so no recap; whatever is offered comes back for a new yes; never "confirmed".

    cd backend && python -m unittest tests.test_ask_flows -v
"""
from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime, timezone

from booking_signer import calls as C, render as R, reservation as RS

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
ACCT = "00000000-0000-4000-8000-000000000001"


def tattoo(flow="quote_first", **over):
    o = {"schema": "reservation/1", "flow": flow, "who": {"name": "Tyler Warren", "account_id": ACCT},
         "what": {"activity": "a fine-line tattoo on the forearm", "activity_venue_lang": "a fine-line tattoo on the forearm",
                  "category": "beauty", "spec": "fine-line, forearm, about 10 cm", "photos": ["asset:1"]},
         "where": {"venue_name": "King Ink", "timezone": "Africa/Nairobi", "venue_ids": []},
         "when": {"mode": "venue_proposes"}, "how_many": {"count": 1, "unit": "pieces"}}
    o.update(over)
    return RS.validate(o)


def venue(code="en"):
    return C.CallVenue(key="read:k", name="King Ink", number_env="", language=code, timezone="Africa/Nairobi",
                       number="+254725909800", source="their Google listing")


class Render(unittest.TestCase):
    def test_a_quote_first_call_asks_and_never_books(self):
        b = R.call_for(tattoo(), venue(), NOW, "+254725909800")
        self.assertEqual(b["brief"]["purpose"], "quote_first")
        self.assertIsNone(b["brief"]["recap"])                           # no booking, no recap
        self.assertEqual(b["brief"]["first_sentence"],
                         "Hello, this is Sasha, an AI concierge operated by Kanoe Technologies SL, calling on behalf of Tyler Warren "
                         "to ask what it would cost and when you could do a fine-line tattoo on the forearm, for one piece. Could you tell me?")
        self.assertIn("Do NOT book anything and do not hold a slot", b["brief"]["task"])
        self.assertIn("If they ask what exactly: fine-line, forearm, about 10 cm.", b["brief"]["task"])
        lines = b["read_back_lines"]
        self.assertIn("I won't book anything, hold a slot, or agree to a deposit, a fee or a card.", lines[2])
        self.assertEqual(lines[3], "Your photos are not sent on a call — only the description.")
        self.assertIn("booking it is a new request and a new yes", lines[-1])

    def test_when_do_you_have_space_in_spanish(self):
        o = tattoo(flow="availability", what={"activity": "a 60-minute massage", "activity_venue_lang": "un masaje de 60 minutos",
                                               "category": "beauty"}, how_many={"count": 1, "unit": "people"},
                   where={"venue_name": "Spa", "timezone": "Europe/Madrid", "venue_ids": []})
        v = C.CallVenue(key="read:s", name="Spa", number_env="", language="es", timezone="Europe/Madrid", number="+34910000000")
        b = R.call_for(o, v, NOW, "+34910000000")
        self.assertEqual(b["brief"]["first_sentence"],
                         "Hola, soy Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL, y llamo de parte de "
                         "Tyler Warren para preguntar cuándo tendrían hueco para un masaje de 60 minutos, para una persona. ¿Me lo podrían decir?")
        self.assertIn("(in Spanish: Hello, this is Sasha", b["read_back_lines"][1])

    def test_every_language_stays_under_blands_limit(self):
        for code in C.LANGUAGES:
            self.assertLessEqual(len(R.call_for(tattoo(), venue(code), NOW, "+254725909800")["brief"]["task"]), 2000, code)

    def test_a_booking_still_needs_a_time(self):
        with self.assertRaises(RS.ReservationRefused):
            tattoo(flow="book")


def details(*venue_lines):
    return {"completed": True, "status": "completed", "answered_by": "human",
            "transcripts": [{"user": "assistant", "text": "Hello, this is Sasha…"}] + [{"user": "user", "text": t} for t in venue_lines]}


def says(reading, quote=""):
    async def r(_t):
        return json.dumps({"reading": reading, "quote": quote, "raised": []})
    return r


class Reading(unittest.TestCase):
    def test_a_quote_comes_back_with_its_times_and_is_never_yes(self):
        line = "It would be 8,000 shillings with a 50% deposit, and we could do Tuesday at 3."
        r = asyncio.run(C.read_call(details(line), says("yes", line), "quote_first", {"mode": "venue_proposes"}))
        self.assertEqual((r.outcome, r.offer["kind"]), ("unclear", "quoted"))
        self.assertEqual(r.offer["quote"], line)
        self.assertIn("nothing is booked", C.say_for("King Ink", r))

    def test_offered_times_come_back_as_proposed(self):
        r = asyncio.run(C.read_call(details("We have Thursday at 4 or Saturday at 11."), says("yes", "We have Thursday at 4"),
                                    "availability", {"mode": "venue_proposes"}))
        self.assertEqual((r.outcome, r.offer["kind"]), ("unclear", "proposed"))
        self.assertIn("Nothing is booked", C.say_for("Spa", r))

    def test_nothing_offered_is_just_unclear_or_no(self):
        r = asyncio.run(C.read_call(details("No, we don't do that, sorry."), says("no", "No, we don't do that, sorry."),
                                    "availability", {"mode": "venue_proposes"}))
        self.assertEqual((r.outcome, r.offer), ("no", None))


if __name__ == "__main__":
    unittest.main()
