"""CR 7 · venue emails in 12 more languages — for EACH language: all five emails exist and fill without a stray brace;
the AI disclosure comes FIRST; the guest's name, the date, the time and the party are in it; it asks for a reply; it is
marked AI-written and unreviewed, with a back-translation of every text and a current review sheet; the counting rule
holds; and the GATE keeps it away from real venues until a reviewer signs (one line).

    cd backend && python -m unittest tests.test_i18n_emails_cr7 -v
"""
from __future__ import annotations

import os
import pathlib
import re
import unittest
from unittest import mock

from booking_signer.i18n import emails as I
from scripts import i18n_review_sheets as RS

NAME, D, T_, ME = "Anna Ejemplo", "2026-10-14", "21:00", "sasha@booking.kanoe.ai"
#: one word per language that only a request to REPLY/CONFIRM contains — checked in each email's body
REPLY_WORD = {"zh": "回复", "ja": "ご返信", "ko": "회신", "ar": "الرد", "hi": "उत्तर", "ru": "ответ", "tr": "yanıtla",
              "nl": "antwoord", "pl": "odpowi", "id": "balas", "sv": "svara", "vi": "trả lời"}
#: the word for "AI" as each disclosure writes it
AI_WORD = {"zh": "人工智能", "ja": "AI", "ko": "AI", "ar": "الذكاء الاصطناعي", "hi": "AI", "ru": "ИИ", "tr": "yapay zekâ",
           "nl": "AI", "pl": "sztucznej inteligencji", "id": "AI", "sv": "AI", "vi": "AI"}


def every(lang):
    core = I.core(lang, what=None, d=D, t=T_, n=4, name=NAME)
    return {"request_table": I.request(lang, table=True, what=None, d=D, t=T_, n=4, name=NAME),
            "request_generic": I.request(lang, table=False, what="massage", d=D, t=T_, n=2, name=NAME),
            "cancel": I.cancel(lang, core_text=core, name=NAME),
            "confirm": I.followup("confirm", lang, core_text=core, name=NAME, me=ME),
            "ask": I.followup("ask", lang, core_text=core, name=NAME, me=ME)}


class EachLanguage(unittest.TestCase):
    def test_the_twelve(self):
        self.assertEqual(set(I.LANGS), {"zh", "ja", "ko", "ar", "hi", "ru", "tr", "nl", "pl", "id", "sv", "vi"})

    def test_every_email_fills_and_carries_what_it_must(self):
        for lang in I.LANGS:
            with self.subTest(lang=lang):
                m = I.mod(lang)
                self.assertEqual(m.STATUS, "ai_unreviewed")
                self.assertIn(AI_WORD[lang], m.DISCLOSURE)
                for kind, (subj, body) in every(lang).items():
                    for text in (subj, body):
                        self.assertNotRegex(text, r"[{}]", f"{lang}/{kind}: a placeholder was left unfilled")
                    first = body.split("\n\n")[0]
                    self.assertIn(m.DISCLOSURE, first, f"{lang}/{kind}: the AI disclosure is not in the first paragraph")
                    self.assertLess(body.index(m.DISCLOSURE), body.index(NAME), f"{lang}/{kind}: the disclosure must come first")
                    self.assertIn(NAME, body)
                    self.assertIn(D, subj + body)
                    self.assertIn(T_, subj + body)
                    self.assertIn(REPLY_WORD[lang], body, f"{lang}/{kind}: no request to reply in writing")
                    self.assertTrue(body.rstrip().split("\n")[-1].startswith(("Sasha", "Саша", "ساشا")), f"{lang}/{kind}: not signed")
                req = every(lang)["request_table"]
                self.assertIn(I.count(lang, 4), req[0] + req[1])
                gen = every(lang)["request_generic"][1]
                self.assertIn("massage", gen)
                self.assertIn(I.count(lang, 2), gen)
                self.assertIn(ME, every(lang)["confirm"][1])

    def test_every_text_has_its_back_translation(self):
        for lang in I.LANGS:
            m = I.mod(lang)
            with self.subTest(lang=lang):
                self.assertEqual(set(m.BACK), set(I.KINDS))
                self.assertTrue(m.CORE_BACK)
                for kind in I.KINDS:
                    self.assertEqual(len(m.BACK[kind][1].split("\n\n")), len(m.T[kind][1].split("\n\n")),
                                     f"{lang}/{kind}: the back-translation must follow the text paragraph by paragraph")

    def test_counting_rules(self):
        self.assertEqual([I.count("ru", n) for n in (1, 2, 5, 11, 12, 21, 22, 25)],
                         ["1 человека", "2 человека", "5 человек", "11 человек", "12 человек", "21 человека", "22 человека", "25 человек"])
        self.assertEqual([I.count("pl", n) for n in (1, 2, 4, 5, 12, 22, 25)],
                         ["1 osobę", "2 osoby", "4 osoby", "5 osób", "12 osób", "22 osoby", "25 osób"])
        self.assertEqual([I.count("ar", n) for n in (1, 2, 3, 10, 11, 25)],
                         ["شخص واحد", "شخصين", "3 أشخاص", "10 أشخاص", "11 شخصًا", "25 شخصًا"])
        self.assertEqual((I.count("nl", 1), I.count("sv", 1), I.count("hi", 1)), ("1 persoon", "1 person", "1 व्यक्ति"))

    def test_turkish_uses_the_same_disclosure_as_its_calls(self):
        from booking_signer.wordings import DISCLOSURE
        self.assertEqual(I.mod("tr").DISCLOSURE, DISCLOSURE["tr"])

    def test_review_sheets_are_current(self):
        for lang in I.LANGS:
            with self.subTest(lang=lang):
                f = RS.OUT / f"{lang}-review.md"
                self.assertTrue(f.exists(), f"run: python -m scripts.i18n_review_sheets")
                self.assertEqual(f.read_text(encoding="utf-8"), RS.sheet(lang), f"{lang}: the review sheet is out of date — regenerate it")
                self.assertIn("NOT been checked by a native speaker", f.read_text(encoding="utf-8"))


class TheGate(unittest.TestCase):
    def test_unreviewed_goes_only_to_our_test_addresses(self):
        with mock.patch.dict(os.environ, {"SASHA_I18N_TEST_TO": "qa@kanoe.ai, test2@kanoe.ai"}):
            for lang in I.LANGS:
                self.assertFalse(I.usable(lang, "reservas@real-restaurant.vn"), lang)
                self.assertTrue(I.usable(lang, "QA@kanoe.ai"), lang)
                self.assertTrue(I.usable(lang, "book@venue.sasha.test"), lang)
            self.assertFalse(I.usable("fr", "qa@kanoe.ai"))          # not one of ours: emailing.py's own six decide

    def test_no_test_list_means_no_unreviewed_email_at_all(self):
        with mock.patch.dict(os.environ, {"SASHA_I18N_TEST_TO": ""}):
            self.assertFalse(any(I.usable(l, "anyone@kanoe.ai") for l in I.LANGS))

    def test_the_one_line_sign_off(self):
        with mock.patch.dict(I.REVIEWED, {"vi": ("Nguyễn Văn A", "2026-10-10")}):
            self.assertTrue(I.usable("vi", "reservas@real-restaurant.vn"))
            self.assertFalse(I.usable("ja", "reservas@real-restaurant.jp"))
        with mock.patch.dict(I.REVIEWED, {"vi": True}):          # a bare True is not a sign-off: it needs who and when
            self.assertFalse(I.usable("vi", "reservas@real-restaurant.vn"))

    def test_nothing_is_signed_off_in_the_repo(self):
        self.assertFalse(any(I.reviewed(l) for l in I.LANGS), "a language was flipped without its review sheet being signed")
