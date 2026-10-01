"""S-64 step 4 · the renderers (booking_signer/render.py). ⛔ THE GOLDEN TEST: a restaurant request built from today's
particulars renders today's opening and call read-back BYTE FOR BYTE, in every language, for every shape of booking.

    cd backend && python -m unittest tests.test_render -v
"""
from __future__ import annotations

import itertools
import unittest
from datetime import datetime, timezone

from booking_signer import calls as C, render as R, reservation as RS

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
ACCT = "00000000-0000-4000-8000-000000000001"
CASES = [
    {"date": "2026-10-02", "time": "13:00", "party": 2, "name": "Tyler Warren"},                           # within six days, a family
    {"date": "2026-10-12", "time": "21:30", "party": 1, "name": "Anna Johnson", "phone": "+34 608 445 715"},  # a date, one person, a phone
    {"date": "2026-10-08", "time": "20:00", "party": 4, "name": "Jon O'Neill-Peters"},
    {"date": "2026-09-30", "time": "14:15", "party": 12, "name": "Maria de la Cruz"},                        # today
]


def venue(code):
    return C.CallVenue(key="read:x", name="La Contra", number_env="", language=code, timezone="Europe/Madrid",
                       number="+34910536740", source="their Google listing (Taberna La Contra, Madrid)")


class Golden(unittest.TestCase):
    def test_a_table_renders_todays_opening_and_read_back_byte_for_byte(self):
        n = 0
        for code, case in itertools.product(C.LANGUAGES, CASES):
            p = C.parse_call_particulars(case)
            lang = C.LANGUAGES[code]
            today = NOW.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Madrid")).date()
            built = C.build_call(venue(code), p, NOW)
            o = RS.from_particulars(p, account_id=ACCT, venue_name="La Contra", timezone="Europe/Madrid", lang=lang.code)
            self.assertTrue(R.is_table(o))
            self.assertEqual(R.opening(lang, o, today), built["brief"]["first_sentence"], (code, case))
            self.assertEqual(R.call_read_back(lang, o, "La Contra", "+34910536740", venue(code).source, today),
                             built["read_back_lines"], (code, case))
            n += 1
        self.assertEqual(n, len(C.LANGUAGES) * len(CASES))


class GoldenBrief(unittest.TestCase):
    """S-64 step 5 · the call brief from the object IS today's brief for a table: same dict, so the same sha256."""

    def test_a_tables_brief_is_todays_brief(self):
        from zoneinfo import ZoneInfo
        n = 0
        for code, case in itertools.product(C.LANGUAGES, CASES):
            p = C.parse_call_particulars(case)
            v = C.CallVenue(key="read:x", name="La Contra", number_env="", language=code, timezone="Europe/Madrid",
                            number="+34910536740", source="their Google listing", venue_ids=("places:ChIJ-x",))
            built = C.build_call(v, p, NOW)
            o = RS.from_particulars(p, account_id=ACCT, venue_name="La Contra", timezone="Europe/Madrid", lang=C.LANGUAGES[code].code)
            brief = R.call_brief(o, v, NOW.astimezone(ZoneInfo("Europe/Madrid")).date(), "+34910536740")
            self.assertEqual(brief, built["brief"], (code, case))
            self.assertEqual(C._sha256hex(C._canonical(brief)), built["brief_sha256"])
            n += 1
        self.assertEqual(n, 24)


class Beyond(unittest.TestCase):
    TODAY = NOW.date()

    def obj(self, **over):
        o = {"schema": "reservation/1", "flow": "book", "who": {"name": "Tyler Warren", "account_id": ACCT},
             "what": {"activity": "a 60-minute relaxing massage", "activity_venue_lang": "un masaje relajante", "category": "beauty"},
             "where": {"venue_name": "Spa", "timezone": "Europe/Madrid", "venue_ids": []},
             "when": {"mode": "at", "at": "2026-10-03T11:00", "duration_min": 60}, "how_many": {"count": 1, "unit": "people"}}
        o.update(over)
        return RS.validate(o)

    def test_a_spa_service_with_its_duration(self):
        s = R.opening(C.LANGUAGES["es"], self.obj(), self.TODAY)
        self.assertEqual(s, "Hola, soy Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL, y llamo de parte de "
                            "Tyler Warren para reservar un masaje relajante de 60 minutos para una persona el sábado a las 11:00. ¿Sería posible?")

    def test_a_window_and_venue_proposes(self):
        w = self.obj(when={"mode": "window", "window": {"earliest": "2026-10-03T10:00", "latest": "2026-10-03T13:00"}})
        self.assertIn("el sábado entre las 10:00 y las 13:00", R.opening(C.LANGUAGES["es"], w, self.TODAY))
        q = self.obj(flow="quote_first", when={"mode": "venue_proposes"}, how_many={"count": 1, "unit": "pieces"},
                     what={"activity": "a fine-line tattoo", "activity_venue_lang": "a fine-line tattoo", "category": "beauty"})
        self.assertIn("to book a fine-line tattoo for one piece whenever you have space", R.opening(C.LANGUAGES["en"], q, self.TODAY))

    def test_a_spa_brief_names_the_service_its_length_and_widens_the_rules(self):
        v = C.CallVenue(key="read:s", name="Spa", number_env="", language="es", timezone="Europe/Madrid", number="+34910000000")
        b = R.call_brief(self.obj(), v, self.TODAY, "+34910000000")
        self.assertIn("phoning a venue to book a 60-minute relaxing massage on behalf of a guest", b["task"])
        self.assertIn("a 60-minute relaxing massage (un masaje relajante), 1 people, 2026-10-03 at 11:00 (venue's local time), 60 minutes", b["task"])
        self.assertIn("Never agree to a different date, time, number, service or length.", b["task"])
        self.assertEqual(b["recap"], "Para confirmar: un masaje relajante de 60 minutos, para una persona, sábado 3 de octubre, a las once de la mañana, a nombre de Warren. ¿Correcto?")
        self.assertIn(b["recap"], b["task"])
        self.assertLessEqual(len(b["task"]), 2000)

    def test_a_window_is_not_phoned_from_the_object_yet(self):
        v = C.CallVenue(key="read:s", name="Spa", number_env="", language="es", timezone="Europe/Madrid", number="+34910000000")
        w = self.obj(when={"mode": "window", "window": {"earliest": "2026-10-03T10:00", "latest": "2026-10-03T13:00"}})
        with self.assertRaises(RS.ReservationRefused) as e:
            R.call_brief(w, v, self.TODAY, "+34910000000")
        self.assertEqual(e.exception.rule, "flow_not_built")

    def test_sessions_and_the_extra_read_back_line(self):
        o = self.obj(how_many={"count": 2, "unit": "sessions"})
        lines = R.call_read_back(C.LANGUAGES["es"], o, "Spa", "+34910000000", None, self.TODAY)
        self.assertIn("para 2 sesiones", lines[1])
        self.assertEqual(lines[2], "That is: a 60-minute relaxing massage (un masaje relajante) · 2 sessions · 2026-10-03T11:00 · 60 minutes.")
        self.assertIn("(in Spanish: Hello, this is Sasha", lines[1])
        self.assertIn("to book a 60-minute relaxing massage for 2 sessions", lines[1])   # the duration is said once


if __name__ == "__main__":
    unittest.main()
