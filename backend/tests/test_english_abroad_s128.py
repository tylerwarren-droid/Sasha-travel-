"""Sasha 128 · ENGLISH ABROAD: a call to a country whose language Sasha has no script in is made in English (the
guest's language), the AI disclosure first, in English — and the read-back says so, and why, before the yes.

    cd backend && python -m unittest tests.test_english_abroad_s128 -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from booking_signer import calls as C

NOW = datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc)


def vn_venue(chosen=None):
    lang, why = C.spoken_language("vi", chosen)
    return C.CallVenue(key="read:r-1", name="Mate", number_env="", language=lang, timezone="Asia/Ho_Chi_Minh",
                       number="+84935123456", source="their website, materes.com", language_why=why)


class EnglishAbroad(unittest.TestCase):
    def test_the_rule(self):
        self.assertEqual(C.spoken_language("es"), ("es", None))                      # the country's own, when scripted
        self.assertEqual(C.spoken_language("vi")[0], "en")                            # none for Vietnamese → English
        self.assertIn("no Vietnamese voice", C.spoken_language("vi")[1])
        self.assertEqual(C.spoken_language("es", "en"), ("en", "English, as you asked"))   # an explicit choice
        self.assertEqual(C.spoken_language("vi", "xx")[0], "en")                      # an unknown choice changes nothing
        self.assertEqual(C.spoken_language("es", "es"), ("es", None))

    def test_a_vietnam_call_is_english_with_the_disclosure_first_and_said_before_the_yes(self):
        p = C.parse_call_particulars({"date": "2026-10-05", "time": "19:00", "party": 2, "name": "Tyler Warren"})
        built = C.with_language_note(C.build_call(vn_venue(), p, NOW), vn_venue())
        b = built["brief"]
        self.assertEqual((b["language"], b["timezone"], b["number"]), ("en", "Asia/Ho_Chi_Minh", "+84935123456"))
        self.assertTrue(b["first_sentence"].startswith("Hello, this is Sasha, an AI concierge from Kanoe Technologies SL"))
        self.assertIn("for two on Monday at seven in the evening", b["first_sentence"])   # the venue's day, in Hoi An
        lines = built["read_back_lines"]
        self.assertTrue(lines[1].startswith("I'll say: \"Hello, this is Sasha"))
        self.assertEqual(lines[2], "I'll speak English: I have no Vietnamese voice, so I'll speak your language — they may not speak English.")
        self.assertEqual(built["read_back_sha256"], C._sha256hex("\n".join(lines)))   # the yes binds to the note
        self.assertLessEqual(len(b["task"]), 2000)

    def test_no_note_when_the_countrys_own_language_is_spoken(self):
        v = C.CallVenue(key="read:r-2", name="Araia", number_env="", language="es", timezone="Europe/Madrid", number="+34610000000")
        p = C.parse_call_particulars({"date": "2026-10-05", "time": "21:00", "party": 2, "name": "Tyler Warren"})
        built = C.build_call(v, p, NOW)
        self.assertEqual(C.with_language_note(built, v), built)


class EnglishEmail(unittest.TestCase):
    def test_vietnamese_venues_are_written_to_in_english(self):
        from booking_signer import emailing as E
        self.assertNotIn("vi", E.TEMPLATE_LANGS)
        self.assertIn("es", E.TEMPLATE_LANGS)
        from datetime import date, time
        p = E.EmailParticulars(on=date(2026, 10, 5), at=time(19, 0), party=2, name="Tyler Warren", guest_email="guest@example.com")
        mail = E.compose("vi", "Mate", "contact@materes.com", p, "x")
        self.assertTrue(mail["text"].startswith("Hello, this is Sasha, an AI concierge"))
