"""S-59 · what the venue actually said, against what was asked (booking_signer/heard.py) — using the REAL transcript
of the first booking (La Contra, 30 Sept 2026, Bland 5e060af9), exactly as Bland returned it.

    cd backend && python -m unittest tests.test_heard -v
"""
from __future__ import annotations

import asyncio
import json
import unittest

from booking_signer import calls as C, heard as H

LA_CONTRA = [
    ("user", "Diga."),
    ("assistant", "Hola, soy Sasha, una conc-"),
    ("user", "Diga."),
    ("assistant", "Hola, soy Sasha, una concierge de inteligencia artificial de Kanoe Technologies SL, y llamo de parte de la familia Warren para reservar una mesa para 2 personas el viernes a la 13:00. ¿Sería posible?"),
    ("user", "Un momento, por favor."),
    ("assistant", "[Waiting]"),
    ("user", "¿El viernes dos?"),
    ("user", "De octubre"),
    ("assistant", "Sí, el viernes dos -"),
    ("assistant", "Sí, correcto. ¿Tienen disponibilidad para dos personas?"),
    ("user", "Sí, ¿a qué hora?"),
    ("assistant", "A la una de la tarde,-"),
    ("user", "¿A qué hora?"),
    ("assistant", "A la una de l-"),
    ("user", "Vale, a las tres de hora."),
    ("assistant", "Perdón, una de la tarde,-"),
    ("user", "Vale."),
    ("assistant", "Perfecto. ¿-"),
    ("user", "Sí, ok."),
    ("assistant", "¿A qué nombre qu-"),
    ("user", "Ok."),
    ("assistant", "¿Podría decirme a-"),
    ("user", "Ok."),
    ("assistant", "Entiendo. La reserva es a nombre de Tyler Warren. ¿Puede confirmar que es para dos personas, el viernes a la una de la tarde?"),
    ("user", "Sí."),
    ("user", "¿Me puede me puede repetir apellido? Apellido Tyler"),
    ("assistant", "El apellido es Warren, W A R R E N."),
    ("user", "Vale. Pues ya tiene la reserva, ¿vale?"),
    ("assistant", "Perfecto. Muchas gracias. Adiós."),
    ("user", "Sí, adiós."),
]
ASKED = {"date": "2026-10-02", "time": "13:00", "party": 2, "name": "Tyler Warren"}
DETAILS = {"completed": True, "status": "completed", "answered_by": "human",
           "transcripts": [{"user": u, "text": t} for u, t in LA_CONTRA]}


def model_says_yes():
    async def r(_t):
        return json.dumps({"reading": "yes", "quote": "Vale. Pues ya tiene la reserva, ¿vale?", "raised": []})
    return r


class LaContra(unittest.TestCase):
    def test_the_real_transcript_is_unclear_not_accepted_as_asked(self):
        r = asyncio.run(C.read_call(DETAILS, model_says_yes(), "book", ASKED))
        self.assertEqual((r.state, r.outcome), ("answered", "unclear"))
        self.assertIn('"Vale, a las tres de hora."', r.why)
        self.assertIn('"¿Me puede me puede repetir apellido? Apellido Tyler"', r.why)
        self.assertIn("they said 3, asked 13:00", r.why)
        self.assertIn("they said tyler, asked Tyler Warren", r.why)
        self.assertIsNone(r.reference)
        whats = {x["quote"] for x in r.raised}
        self.assertEqual(whats, {"Vale, a las tres de hora.", "¿Me puede me puede repetir apellido? Apellido Tyler"})

    def test_the_lines_that_agree_are_not_flagged(self):
        off = H.mismatches([t for u, t in LA_CONTRA if u == "user"], ASKED)
        self.assertEqual([(m["what"], m["quote"]) for m in off],
                         [("time", "Vale, a las tres de hora."), ("name", "¿Me puede me puede repetir apellido? Apellido Tyler")])

    def test_without_the_request_the_old_reading_stands(self):
        r = asyncio.run(C.read_call(DETAILS, model_says_yes(), "book"))
        self.assertEqual(r.outcome, "yes")


class Mismatches(unittest.TestCase):
    def check(self, line, **asked):
        return [m["what"] for m in H.mismatches([line], {**ASKED, **asked})]

    def test_times(self):
        self.assertEqual(self.check("Sí, a la una perfecto."), [])
        self.assertEqual(self.check("Vale, a las nueve.", time="21:00"), [])
        self.assertEqual(self.check("Perfecto, a las 21:00.", time="21:00"), [])
        self.assertEqual(self.check("Tenemos a las nueve y media.", time="13:00"), ["time"])
        self.assertEqual(self.check("Yes, at eight is fine.", time="20:00"), [])
        self.assertEqual(self.check("We can do 7:30.", time="20:00"), ["time"])
        self.assertEqual(self.check("Às nove, pode ser.", time="20:00"), ["time"])

    def test_party_day_and_name(self):
        self.assertEqual(self.check("Mesa para cuatro personas, ¿no?"), ["party"])
        self.assertEqual(self.check("Para dos, perfecto."), [])
        self.assertEqual(self.check("¿El sábado?"), ["day"])
        self.assertEqual(self.check("¿El viernes dos?"), [])
        self.assertEqual(self.check("¿A nombre de quién?"), [])
        self.assertEqual(self.check("Apuntado a nombre de Warren."), [])
        self.assertEqual(self.check("A nombre de Ramírez, ¿verdad?"), ["name"])

    def test_nothing_parsed_nothing_flagged(self):
        self.assertEqual(self.check("Vale, perfecto, hasta luego."), [])
        self.assertEqual(H.mismatches(["a las tres"], {"date": "garbage"}), [])


if __name__ == "__main__":
    unittest.main()
