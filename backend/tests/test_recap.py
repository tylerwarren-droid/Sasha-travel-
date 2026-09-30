"""S-60 · the closing recap: every booking call ends with it, and only an explicit yes to it confirms.

    cd backend && python -m unittest tests.test_recap -v
"""
from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime, timezone

from booking_signer import calls as C, recap as RC
from tests.test_heard import LA_CONTRA

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
P = C.parse_call_particulars({"date": "2026-10-02", "time": "13:00", "party": 2, "name": "Tyler Warren"})
VENUE = C.CallVenue(key="read:x", name="La Contra", number_env="", language="es", timezone="Europe/Madrid", number="+34910536740")
BRIEF = C.build_call(VENUE, P, NOW)["brief"]
RECAP = BRIEF["recap"]


def call(*turns):
    return {"completed": True, "status": "completed", "answered_by": "human", "transcripts": [{"user": u, "text": t} for u, t in turns]}


def says_yes(quote):
    async def r(_t):
        return json.dumps({"reading": "yes", "quote": quote, "raised": []})
    return r


def read(details, quote="Sí, perfecto."):
    return asyncio.run(C.read_call(details, says_yes(quote), "book", BRIEF))


class Sentence(unittest.TestCase):
    def test_the_founders_own_example_word_for_word(self):
        self.assertEqual(RECAP, "Para confirmar: viernes 2 de octubre, a la una de la tarde, dos personas, a nombre de Warren. ¿Correcto?")

    def test_it_is_in_the_brief_the_guest_approves_and_in_the_agents_instructions(self):
        self.assertIn(RECAP, BRIEF["task"])
        self.assertIn("Only a clear yes to it confirms", BRIEF["task"])
        self.assertIsNone(C.build_call(VENUE, P, NOW, purpose="cancel", reference=None)["brief"]["recap"])

    def test_every_language_stays_under_blands_limit(self):
        p = C.parse_call_particulars({"date": "2026-10-12", "time": "21:30", "party": 12,
                                      "name": "Maria-Fernanda de la Cruz Villanueva", "phone": "+34 608 445 715"})
        for code in C.LANGUAGES:
            v = C.CallVenue(key="x", name="V", number_env="", language=code, timezone="Europe/Madrid", number="+34910000000")
            self.assertLessEqual(len(C.build_call(v, p, NOW)["brief"]["task"]), 2000, code)


class Confirmed(unittest.TestCase):
    OPEN = (("user", "Diga."), ("assistant", BRIEF["first_sentence"]), ("user", "Sí, perfecto."))

    def test_an_explicit_yes_to_the_whole_recap_confirms(self):
        r = read(call(*self.OPEN, ("assistant", RECAP), ("user", "Sí, correcto."), ("user", "Hasta luego.")))
        self.assertEqual(r.outcome, "yes", r.why)

    def test_a_conflict_resolved_on_the_call_is_confirmed(self):
        r = read(call(*self.OPEN, ("user", "Vale, a las tres."), ("assistant", "Perdón, es a la una de la tarde."),
                      ("user", "Ah, a la una, vale."), ("assistant", RECAP), ("user", "Sí, eso es.")))
        self.assertEqual(r.outcome, "yes", r.why)

    def test_a_no_or_a_different_answer_to_the_recap_is_not_confirmed(self):
        r = read(call(*self.OPEN, ("assistant", RECAP), ("user", "No, a las tres.")))
        self.assertEqual(r.outcome, "unclear")
        self.assertIn('"No, a las tres."', r.why)
        self.assertTrue(r.why.startswith("not confirmed"))

    def test_something_different_after_the_yes_is_not_confirmed(self):
        r = read(call(*self.OPEN, ("assistant", RECAP), ("user", "Sí."), ("user", "¿Me puede repetir apellido? Apellido Tyler")))
        self.assertEqual(r.outcome, "unclear")
        self.assertIn("Apellido Tyler", r.why)

    def test_a_recap_cut_off_is_not_a_recap(self):
        r = read(call(*self.OPEN, ("assistant", "Para confirmar: viernes 2 de-"), ("user", "Sí.")))
        self.assertEqual(r.outcome, "unclear")
        self.assertIn("never read in full", r.why)

    def test_la_contra_had_no_recap_and_is_not_confirmed(self):
        r = read(call(*LA_CONTRA), quote="Vale. Pues ya tiene la reserva, ¿vale?")
        self.assertEqual(r.outcome, "unclear")
        self.assertIn("never read in full", r.why)


class Written(unittest.TestCase):
    ASKED = {"date": "2026-10-02", "time": "13:00", "party": 2, "name": "Tyler Warren"}

    def test_a_reply_confirms_only_by_restating_day_time_and_party(self):
        self.assertTrue(RC.restates("Perfecto, mesa para dos el viernes 2 a la una.", self.ASKED))
        self.assertFalse(RC.restates("Perfecto, os esperamos.", self.ASKED))
        self.assertFalse(RC.restates("Mesa para dos el viernes a las tres.", self.ASKED))


if __name__ == "__main__":
    unittest.main()
