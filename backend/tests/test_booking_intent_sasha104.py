"""Sasha 104 · the founder's WhatsApp request was refused as out of scope: "Dinner for 2 on Saturday at 2100 in Chamberi.
Something luxurious and romantic". The area said AFTER the day and time, a 24-hour clock with no colon, no accent, and a
second sentence of qualifiers. Each is now read — that exact message and ten realistic variants, English and Spanish —
and on WhatsApp the fixed out-of-scope sentence is kept for messages with clearly no booking in them; when unsure, one
question. Offline.

    cd backend && python -m unittest tests.test_booking_intent_sasha104 -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from booking_signer import guest_whatsapp as GW, handoff as H

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)   # a Friday: "Saturday" is 3 October
CHAMBERI = "Chamberí, Madrid"
SAT_21 = "2026-10-03T21:00"

CASES = [
    # (message, what, where, open_at, party)
    ("Dinner for 2 on Saturday at 2100 in Chamberi. Something luxurious and romantic",
     "luxurious and romantic Dinner", CHAMBERI, SAT_21, 2),                                       # the founder's, verbatim
    ("Table for two Saturday 9pm in Chamberí, somewhere romantic", "romantic Table", CHAMBERI, SAT_21, 2),
    ("Can you book us dinner for 2 at 21h on Saturday in Chamberi?", "dinner", CHAMBERI, SAT_21, 2),
    ("I'd like a romantic dinner for two in Chamberí on Saturday at 9pm", "romantic dinner", CHAMBERI, SAT_21, 2),
    ("Book a table for 2 in Chamberi saturday 21:00", "table", CHAMBERI, SAT_21, 2),
    ("We need a table for 4 tomorrow at 2030 near Retiro", "table", "Retiro, Madrid", "2026-10-03T20:30", 4),
    ("Cena para 2 el sábado a las 21:00 en Chamberí", "dinner", CHAMBERI, SAT_21, 2),
    ("Quiero reservar una mesa para dos el sábado a las 21h en Chamberi, algo romántico", "romántico table", CHAMBERI, SAT_21, 2),
    ("Reserva cena para 2 en Chamberí el sábado a las 9 de la noche", "dinner", CHAMBERI, SAT_21, 2),
    ("Mesa para 4 mañana a las 14:00 en Malasaña", "table", "Malasaña, Madrid", "2026-10-03T14:00", 4),
    ("Busco un restaurante romántico en Chamberí para el sábado a las 21:00 para dos personas", "restaurant romántico", CHAMBERI, SAT_21, 2),
]


class ReadAsABooking(unittest.TestCase):
    def test_the_founders_message_and_ten_variants(self):
        for msg, what, where, at, party in CASES:
            with self.subTest(msg=msg):
                h = H.booking_handoff(msg, now=NOW)
                self.assertIsNotNone(h, "refused — read as not a booking")
                f = h["booking_find"]
                self.assertEqual((f["what"], f["where"], f.get("country"), f.get("open_at")), (what, where, "ES", at))
                self.assertEqual(h["reservation_draft"]["parts"]["how_many"]["count"], party)

    def test_qualifiers_are_kept_for_the_search(self):
        self.assertIn("luxurious and romantic", H.booking_handoff(CASES[0][0], now=NOW)["booking_find"]["what"])

    def test_qualities_survive_a_request_joined_from_several_lines(self):
        """Live: the qualities sentence was dropped when "Saturday at 2100" was joined with the earlier line."""
        hist = [{"role": "user", "content": CASES[0][0]}, {"role": "assistant", "content": "On WhatsApp I can book…"}]
        f = H.booking_handoff("Saturday at 2100", hist, now=NOW)["booking_find"]
        self.assertIn("luxurious", f["what"]); self.assertIn("romantic", f["what"])

    def test_clocks(self):
        self.assertEqual(H.spoken("at 2100"), "at 21:00")
        self.assertEqual(H.spoken("a las 21h"), "at 21:00")
        self.assertEqual(H.spoken("21h30"), "21:30")
        self.assertEqual(H.spoken("Room 2100 please"), "Room 2100 please")     # a number that is not "at 2100" is left alone

    def test_spanish_cancel_still_reads_the_venue(self):
        self.assertEqual(H.booking_handoff("cancela la reserva en Botavara", now=NOW)["booking_cancel"], {"venue": "Botavara"})

    def test_no_booking_is_still_no_booking(self):
        for msg in ("write me a poem about Madrid", "what's the weather in Madrid on Saturday?", "I want to see the museum in Madrid"):
            self.assertIsNone(H.booking_handoff(msg, now=NOW), msg)


class WhatsAppGate(unittest.TestCase):
    def test_clearly_not_a_booking_vs_unsure(self):
        self.assertFalse(GW.maybe_booking("write me a poem about Madrid"))
        self.assertFalse(GW.maybe_booking("tell me a joke"))
        for msg in ("can you sort out Saturday night for 2?", "mesa para 2", "something nice at 9pm", "change my booking"):
            self.assertTrue(GW.maybe_booking(msg), msg)


if __name__ == "__main__":
    unittest.main()
