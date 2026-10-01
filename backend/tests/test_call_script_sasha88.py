"""Sasha 88 · the first in-chat call (Botavara Chamberí, a1c85ca6, 1 Oct 2026) replayed: what Sasha would now say.

On that call she spelled "W A R R E N" in English letters — the venue wrote "David" — and the task held the guest's
number as "+ 3 4 6 0 8 …"; when the venue asked for a number, she said none was needed. Every one of those is now
in Spanish, as a person in Madrid says it, and both references are asked for and given. Offline.

    cd backend && python -m unittest tests.test_call_script_sasha88 -v
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import calls as C, followup as FU, spoken as SP

NOW = datetime(2026, 10, 1, 17, 56, tzinfo=timezone.utc)
BOTAVARA = C.CallVenue(key="read:5a605d12-3023-4424-94fe-565995fad601", name="dinner in Chamberí", number_env="",
                       language="es", timezone="Europe/Madrid", number="+34910000000", source="its Google Maps listing")
ASKED = {"date": "2026-10-03", "time": "21:00", "party": 2, "name": "Warren", "phone": "+34608445715"}


class TheCallReplayed(unittest.TestCase):
    def setUp(self):
        self.built = C.build_call(BOTAVARA, C.parse_call_particulars(ASKED), NOW)
        self.task = self.built["brief"]["task"]

    def test_the_name_is_spelled_as_madrid_spells_it_not_letter_by_english_letter(self):
        self.assertIn('Name: Warren; if not caught, spell: "W de Washington, A de Alicante, R de Roma, R de Roma, '
                      'E de España, N de Navarra".', self.task)
        self.assertNotIn("W A R R E N", self.task)

    def test_the_guests_number_is_said_in_spanish_digits_when_they_ask(self):
        self.assertIn('Only if asked for a phone number, say: "seis cero ocho, cuatro cuatro cinco, siete uno cinco".', self.task)
        self.assertNotIn("+ 3 4", self.task)
        self.assertNotIn("nine", self.task)

    def test_both_references_are_asked_for_and_given_in_spanish(self):
        ref = self.built["brief"]["own_reference"]
        self.assertRegex(ref, SP.REF_RX)
        self.assertIn('On a yes, ask: "¿Me da un número de reserva o localizador?" and repeat it back.', self.task)
        self.assertIn(f'Then say: "{SP.own_reference_line(ref, "es")}"', self.task)
        self.assertTrue(SP.own_reference_line(ref, "es").startswith("Por nuestra parte, la referencia es K de Kilo, "))
        self.assertIn(f"give them ours, {ref}; both go on your receipt.", "\n".join(self.built["read_back_lines"]))

    def test_the_closing_recap_restates_the_name(self):
        self.assertEqual(self.built["brief"]["recap"],
                         "Para confirmar: sábado 3 de octubre, a las nueve de la noche, dos personas, a nombre de Warren. ¿Correcto?")
        self.assertIn(self.built["brief"]["recap"], self.task)

    def test_the_same_booking_is_the_same_reference_and_another_is_not(self):
        again = C.build_call(BOTAVARA, C.parse_call_particulars(ASKED), NOW)["brief"]["own_reference"]
        other = C.build_call(BOTAVARA, C.parse_call_particulars({**ASKED, "time": "21:30"}), NOW)["brief"]["own_reference"]
        self.assertEqual(again, self.built["brief"]["own_reference"])
        self.assertNotEqual(other, again)

    def test_with_sashas_own_email_it_still_fits_blands_limit(self):
        with mock.patch.dict(os.environ, {"SASHA_EMAIL_FROM": "Sasha <sasha@booking.kanoe.ai>", "SASHA_INBOUND_DOMAIN": "booking.kanoe.ai",
                                     "SASHA_RESEND_API_KEY": "k", "RESEND_WEBHOOK_SECRET": "w"}):
            out = FU.with_own_contact(self.built, "Botavara", None, None)
        self.assertIn("sasha arroba booking punto kanoe punto ai", out["brief"]["task"])
        self.assertLessEqual(len(out["brief"]["task"]), 2000)


if __name__ == "__main__":
    unittest.main()
