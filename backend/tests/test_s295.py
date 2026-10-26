"""Sasha 295 · T73 — THE FIRST FIVE SECONDS: NO STAND-OFF (Tyler, 26 Oct: "she sits and looks at you… tap the mic to begin").

ROOT TEST: (1) the ONE place S2's opening is defined is frontend/lib/opening-rule.mjs (held by frontend/scripts/opening-rule.test.mjs):
on load her still and ONE action ("Tap to talk to Sasha", "or type", the starters), nothing said until the tap; the tap starts the mic
and her hello. Its WORDS and STARTERS are the backend's — held here. (2) A second welcome overlay, a per-device branch, or a timer that
fakes readiness = PATCH. (3) After it, the hello says what she does, and every starter is one of her chips (a real tool today).
    cd backend && python -m unittest tests.test_s295 -v
"""
from __future__ import annotations

import unittest

from agapi import s2_home as H
from app.agent import voice as V


class TheOpening(unittest.TestCase):
    def test_her_hello_says_what_she_does(self):
        self.assertIn("book", V.HELLO)
        self.assertEqual(V.HELLO_BACK.format(name="Tyler"), "Hi Tyler — what shall I book for you?")
        self.assertNotIn("?.", V.arrival_line("Tyler", back=True))   # a question keeps its own mark

    def test_the_starters_are_her_own_chips(self):
        self.assertTrue(2 <= len(H.STARTERS) <= 3)
        for s in H.STARTERS:
            self.assertIn(s, H.CHIP_TOOLS)   # each starter is a chip with its tool: something she does today

    def test_the_page_gets_them_from_here(self):
        self.assertIn('export const STARTERS = ["A table for two tonight", "A spa on Saturday", "What can you do?"]', H.frontend_module())


if __name__ == "__main__":
    unittest.main()
