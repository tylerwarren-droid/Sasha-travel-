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
                         "Hello, this is Sasha, an AI concierge from Kanoe Technologies SL, calling on behalf of Tyler Warren "
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
                         "Hola, soy Sasha, una concierge de inteligencia artificial de Kanoe Technologies SL, y llamo de parte de "
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


class CancelAnActivity(unittest.TestCase):
    """S-64 · cancelling a booking made from the object cancels THAT activity — never "una mesa"."""

    def booked(self, code):
        o = RS.validate({"schema": "reservation/1", "flow": "book", "who": {"name": "Tyler Warren", "account_id": ACCT},
                         "what": {"activity": "a 60-minute relaxing massage", "activity_venue_lang": {"es": "un masaje relajante de 60 minutos",
                                  "en": "a 60-minute relaxing massage", "pt": "uma massagem relaxante de 60 minutos", "fr": "un massage relaxant de 60 minutes",
                                  "de": "eine Entspannungsmassage von 60 Minuten", "it": "un massaggio rilassante di 60 minuti"}[code.split("-")[0]],
                                  "category": "beauty"},
                         "where": {"venue_name": "Calma", "timezone": "Europe/Madrid", "venue_ids": []},
                         "when": {"mode": "at", "at": "2026-10-05T10:00", "duration_min": 60}, "how_many": {"count": 1, "unit": "people"}})
        v = C.CallVenue(key="read:c", name="Calma", number_env="", language=code, timezone="Europe/Madrid", number="+34919891916")
        return R.call_for(o, v, NOW, "+34919891916")["brief"], v

    def test_the_cancellation_names_the_massage_in_every_language(self):
        want = {"es": "para cancelar la reserva de un masaje relajante de 60 minutos para una persona",
                "en": "to cancel the booking of a 60-minute relaxing massage for one",
                "pt": "para cancelar a reserva de uma massagem relaxante de 60 minutos",
                "fr": "pour annuler la réservation d'un massage relaxant de 60 minutes",
                "de": "um die Reservierung für eine Entspannungsmassage von 60 Minuten",
                "it": "per cancellare la prenotazione di un massaggio rilassante di 60 minuti"}
        for code in C.LANGUAGES:
            b, v = self.booked(code)
            c = R.cancel_for(b, v, NOW, None)
            self.assertIn(want[code.split("-")[0]], c["brief"]["first_sentence"], code)
            self.assertNotIn("mesa", c["brief"]["first_sentence"])
            self.assertIn("This cancels your a 60-minute relaxing massage for 1 on 2026-10-05 at 10:00", c["read_back_lines"][2])
            self.assertLessEqual(len(c["brief"]["task"]), 2000)

    def test_the_booking_brief_carries_what_its_reply_is_checked_against(self):
        b, _ = self.booked("es")
        self.assertEqual((b["unit"], b["duration_min"], b["category"]), ("people", 60, "beauty"))
        self.assertEqual(b["recap"], "Para confirmar: un masaje relajante de 60 minutos, para una persona, lunes 5 de octubre, a las diez de la mañana, a nombre de Warren. ¿Correcto?")
