"""S-64 step 8 · the new outcomes — proposed, quoted, waitlisted. Each is recorded in the reading and the reservation's
status, each has its own true sentence, and none is ever "confirmed".

    cd backend && python -m unittest tests.test_offers -v
"""
from __future__ import annotations

import asyncio
import json
import unittest

from booking_signer import calls as C, routes
from booking_signer.call_store import MemoryCallStore, outcome_effect
from tests.test_heard import LA_CONTRA

ASKED = {"date": "2026-10-02", "time": "13:00", "party": 2, "name": "Tyler Warren"}


def call(*venue_lines):
    return {"completed": True, "status": "completed", "answered_by": "human",
            "transcripts": [{"user": "assistant", "text": "Hola, soy Sasha…"}] + [{"user": "user", "text": t} for t in venue_lines]}


def says(reading, quote=""):
    async def r(_t):
        return json.dumps({"reading": reading, "quote": quote, "raised": []})
    return r


def read(details, reading="unclear", quote="", purpose="book", asked=ASKED):
    return asyncio.run(C.read_call(details, says(reading, quote), purpose, asked))


class Offers(unittest.TestCase):
    def test_another_time_is_proposed_not_booked(self):
        r = read(call("A la una no tenemos, pero a las tres sí."), "no", "A la una no tenemos, pero a las tres sí.")
        self.assertEqual((r.outcome, r.offer["kind"]), ("no", "proposed"))
        self.assertEqual(r.offer["quote"], "A la una no tenemos, pero a las tres sí.")
        say = C.say_for("La Contra", r)
        self.assertIn("they offered something else", say)
        self.assertIn("Nothing is booked", say)
        self.assertNotIn("confirmed", say.replace("didn't confirm", ""))

    def test_a_waiting_list_is_waitlisted(self):
        r = read(call("Estamos completos, le puedo apuntar en la lista de espera."))
        self.assertEqual((r.outcome, r.offer["kind"]), ("unclear", "waitlisted"))
        self.assertIn("that is not a booking", C.say_for("La Contra", r))

    def test_a_quote_on_a_quote_first_call(self):
        r = read(call("It would be 8,000 shillings, 50% deposit."), purpose="quote_first", asked=None)
        self.assertEqual(r.offer["kind"], "quoted")
        self.assertIn("nothing is booked", C.say_for("King Ink", r))
        self.assertIn("I never pay a deposit for you", C.say_for("King Ink", r))

    def test_a_yes_later_contradicted_is_unclear_not_an_offer(self):
        r = read(call(*[t for u, t in LA_CONTRA if u == "user"]), "yes", "Vale. Pues ya tiene la reserva, ¿vale?")
        self.assertEqual(r.outcome, "unclear")
        self.assertIsNone(r.offer)

    def test_a_plain_no_is_still_declined(self):
        r = read(call("No, lo siento, estamos completos."), "no", "No, lo siento, estamos completos.")
        self.assertIsNone(r.offer)
        self.assertEqual(outcome_effect("book", r.outcome, r.offer), ("declined", "declined"))


class Recorded(unittest.TestCase):
    def test_each_offer_sets_its_own_status_and_never_confirmed(self):
        for kind in ("proposed", "quoted", "waitlisted"):
            attempt, trip = outcome_effect("book", "unclear", {"kind": kind})
            self.assertEqual((attempt, trip), ("unclear", kind))
            words = routes.STATUS_WORDS[kind]
            self.assertTrue(words.startswith("Not booked"), words)
            self.assertNotIn("onfirmed", words)

    def test_the_memory_store_records_the_offer_on_the_reservation(self):
        store = MemoryCallStore()
        b = C.build_call(C.CallVenue(key="x", name="La Contra", number_env="", language="es", timezone="Europe/Madrid", number="+34910536740"),
                         C.parse_call_particulars({**ASKED}), __import__("datetime").datetime(2026, 9, 30, 12, tzinfo=__import__("datetime").timezone.utc))
        row = {"call_id": "c1", "account_id": "a", "venue_key": "x", "dialled_number": "+34910536740", "language": "es",
               "guest_name": "Tyler Warren", "guest_phone": None, "brief": b["brief"], "brief_sha256": b["brief_sha256"],
               "read_back_lines": b["read_back_lines"], "read_back_sha256": b["read_back_sha256"], "created_at": None,
               "venue_name": "La Contra", "local_date": None, "local_time": None, "local_timezone": "Europe/Madrid", "party_size": 2}
        asyncio.run(store.put_call(row, None))
        store.calls["c1"]["status"] = "placed"
        r = read(call("Tenemos lista de espera para el viernes."))
        self.assertTrue(asyncio.run(store.record_reading("c1", r, {}, None)))
        self.assertEqual(store.trip_items[store.calls["c1"]["trip_item_id"]]["status"], "waitlisted")
        self.assertEqual(store.calls["c1"]["reading"]["offer"]["kind"], "waitlisted")
        self.assertEqual(store.attempts[-1]["status"], "unclear")


if __name__ == "__main__":
    unittest.main()
