"""Sasha 262 · T44 — the last two S2 items (row 911, EU 257's run 20:27Z), each said by code from voice.py, in the one place:
  item 10 · after "Handle it" she said "I haven't booked it yet. I need a clear yes first. Shall I go ahead…" (3 sentences) in place of
            the one read-back line — the model had called book_venue (no yes yet → no_explicit_yes). Now book_venue on their answer to
            the one question reads it back as hold_venue does, and the read-back's ONE line is said by code and ends the turn.
  item 3  · her reply carried no € total ("€?") while the Trip tab said ALL IN €482. A turn that priced the trip says the one total
            (basket.trip_figures) by code when she leaves it out.
Offline.

    cd backend && python -m unittest tests.test_s262 -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import datetime, timezone
from unittest import mock

from app.agent import voice as V

ACCT = "00000000-0000-4000-8000-000000000262"
RB = {"status": "awaiting_yes", "venue": "Sasha Test Venue", "read_back": ["· Día: 2026-10-22"], "ask": V.READ_BACK_ASK.format(venue="Sasha Test Venue")}


class TheReadBackIsOneLineSaidByCode(unittest.TestCase):
    def test_the_line_from_a_read_back_result(self):
        self.assertEqual(V.read_back_line("hold_venue", {"ok": True, "result": RB}), "Shall I send this to Sasha Test Venue? Every detail is on the card.")
        self.assertEqual(V.read_back_line("book_venue", {"ok": True, "result": RB}), RB["ask"])

    def test_nothing_else_is_a_read_back(self):
        self.assertEqual(V.read_back_line("search_venues", {"ok": True, "result": RB}), "")
        self.assertEqual(V.read_back_line("hold_venue", {"ok": True, "result": {**RB, "status": "yes_heard"}}), "")
        self.assertEqual(V.read_back_line("hold_venue", {"ok": True, "result": {**RB, "read_back": []}}), "")   # WhatsApp: no card
        self.assertEqual(V.read_back_line("hold_venue", {"ok": False, "error": {"code": "x"}}), "")

    def test_venues_uses_the_one_line(self):
        from agapi import venues as VN
        self.assertIs(VN.READ_BACK_ASK, V.READ_BACK_ASK)

    def test_the_turn_says_it_and_ends_on_it(self):
        from app.agent import sasha as S
        src = inspect.getsource(S.turn)
        self.assertIn('rb = (_V.read_back_line(u.name, r) or _V.yes_line(u.name, r) or _V.page_line(u.name, r)\n                  or _V.discover_line(u.name, r) or _V.fine_print_line(u.name, r) or _V.flight_line(u.name, r)) if honest else ""', src)   # 263 · + the yes's line; 264 · + a page; 276 · + discover's say_text · 302 · + the fine print · 305 MOVED · + a flight's change / cancel
        self.assertIn("if agapi_out or read_back_said:", src)


class OnlyAYesSends(unittest.TestCase):
    """Sasha 378 · CR 188: "Handle it" answered Sasha's own ONE question — gone with her decider. book_venue sends only on a yes, and
    holds nothing of its own (no route picked from their words, no second memory)."""

    def ctx(self, said):
        class Ctx:
            account, user_said, surface, session = ACCT, said, "s2", "s"
            started = datetime.now(timezone.utc)
        return Ctx()

    def test_handle_it_and_other_words_are_no_yes(self):
        from agapi import venues as VN
        with mock.patch.object(VN, "one_path", lambda ctx: True):
            for said in ("Handle it", "hmm"):
                with self.assertRaises(Exception) as cm:
                    asyncio.run(VN.book_venue(self.ctx(said), {"name": "X", "party": 2, "approval": {"said": said}}))
                self.assertEqual(getattr(cm.exception, "code", ""), "no_explicit_yes", said)

    def test_no_route_from_their_words(self):
        from agapi import venues as VN
        src = inspect.getsource(VN.book_venue)
        self.assertNotIn('"route": picked', src)
        self.assertNotIn("chosen_route", src)


class TheOneTotalIsSaid(unittest.TestCase):
    F = {"total_eur": 482.4}

    def test_left_out_it_is_said(self):
        self.assertEqual(V.total_line(self.F, "Here's a Lisbon weekend: two nights in Alfama and Sintra on Monday."), "All in, that's about €482.")

    def test_said_it_is_not_said_twice(self):
        for t in ("about €482 for the two of you", "That comes to €482.40 all in.", "roughly 483 euros"):
            self.assertEqual(V.total_line(self.F, t), "", t)

    def test_only_a_part_named_the_total_is_said(self):
        self.assertEqual(V.total_line(self.F, "The hotel is about €312 for two nights."), "All in, that's about €482.")

    def test_no_priced_trip_nothing(self):
        self.assertEqual(V.total_line({}, "x"), "")
        self.assertEqual(V.total_line({"total_eur": None}, "x"), "")

    def test_the_turn_says_it_only_when_it_priced_the_trip(self):
        from app.agent import sasha as S
        src = inspect.getsource(S.turn)
        self.assertIn('tline = _V.total_line(figures, text) if honest and tstate.get("priced") and not agapi_out else ""', src)
        self.assertEqual(set(V.TOTAL_TOOLS), {"propose_trip", "swap_stay", "choose_offer"})   # never a venue booking (item 10's 2 sentences)


if __name__ == "__main__":
    unittest.main()
