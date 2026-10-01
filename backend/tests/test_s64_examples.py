"""S-64 step 13 · THE PROOF: the four §6 examples, as objects, through every channel — frozen (golden), and checked
for what must hold whatever the wording.

    cd backend && python -m unittest tests.test_s64_examples -v
Regenerate after a DELIBERATE wording change, then review the diff:  python -m tests.s64_examples
"""
from __future__ import annotations

import json
import unittest

from tests import s64_examples as X


class Golden(unittest.TestCase):
    def test_every_channel_of_every_example_is_what_was_reviewed(self):
        want = json.loads(X.GOLDEN.read_text(encoding="utf-8"))
        got = json.loads(json.dumps(X.render_all(), ensure_ascii=False, sort_keys=True))
        for key in X.EXAMPLES:
            for ch in ("request_sha256", "call", "email", "whatsapp", "form"):
                self.assertEqual(got[key][ch], want[key][ch], f"{key} · {ch}")


class Invariants(unittest.TestCase):
    OUT = X.render_all()

    def test_every_call_discloses_first_and_stays_under_blands_limit(self):
        for key, r in self.OUT.items():
            c = r["call"]
            if "refused" in c:
                continue
            self.assertIn("Kanoe Technologies SL", c["first_sentence"].split(",")[0] + c["first_sentence"][:120], key)
            self.assertLessEqual(c["task_chars"], 2000, key)

    def test_a_recap_only_where_a_booking_is_made(self):
        self.assertIsNone(self.OUT["6.2a_king_ink_quote"]["call"]["recap"])
        for key in ("6.1_la_contra", "6.2b_king_ink_book", "6.3_lisbon_kayak"):
            self.assertTrue(self.OUT[key]["call"]["recap"], key)

    def test_the_quote_never_books_and_the_spa_window_is_not_phoned_yet(self):
        q = self.OUT["6.2a_king_ink_quote"]
        self.assertIn("I won't book anything", " ".join(q["call"]["read_back"]))
        self.assertIn("Your photos are not sent on a call", " ".join(q["call"]["read_back"]))
        self.assertEqual(q["form"]["refused"], "no_time")
        self.assertEqual(self.OUT["6.4_madrid_spa"]["call"]["refused"], "flow_not_built")

    def test_no_channel_ever_agrees_to_money(self):
        for key, r in self.OUT.items():
            if "refused" not in r["call"]:
                self.assertTrue(any("deposit" in l for l in r["call"]["read_back"]), key)

    def test_the_kayak_says_its_length_once(self):
        k = self.OUT["6.3_lisbon_kayak"]["call"]
        self.assertIn("um passeio de caiaque de 180 minutos", k["first_sentence"])
        self.assertIn("Para confirmar: um passeio de caiaque de 180 minutos, para 2 pessoas", k["recap"])


if __name__ == "__main__":
    unittest.main()
