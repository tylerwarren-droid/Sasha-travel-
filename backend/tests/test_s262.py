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
        self.assertIn('rb = (_V.read_back_line(u.name, r) or _V.yes_line(u.name, r) or _V.page_line(u.name, r)\n                  or _V.discover_line(u.name, r) or _V.fine_print_line(u.name, r)) if honest else ""', src)   # 263 · + the yes's line; 264 · + a page; 276 · + discover's say_text · 302 · + the fine print
        self.assertIn("if agapi_out or read_back_said:", src)


class HandleItNeverAsksForAClearYes(unittest.TestCase):
    def ctx(self, said):
        class Ctx:
            account, user_said, surface, session = ACCT, said, "s2", "s"
            started = datetime.now(timezone.utc)
        return Ctx()

    def test_book_venue_on_their_answer_reads_it_back(self):
        # Sasha 263 (row 914) · moved onto the card path: the booking is the one she was given (hold_venue's fields), never a
        # booking remembered from an earlier question (262's _ASKED_ROUTE, deleted)
        from agapi import venues as VN
        hold = mock.AsyncMock(return_value=RB)
        b = {"name": "Sasha Test Venue", "day": "2026-10-22", "time": "21:15", "party": 2}
        with mock.patch.object(VN, "hold_venue", hold), mock.patch.object(VN, "one_path", lambda ctx: True):
            out = asyncio.run(VN.book_venue(self.ctx("Handle it"), {**b, "approval": {"said": "Handle it"}}))
        self.assertEqual(out, RB)
        self.assertEqual(hold.call_args[0][1]["route"], "form")
        self.assertEqual(hold.call_args[0][1]["name"], "Sasha Test Venue")

    def test_without_the_question_it_is_still_no_yes(self):
        from agapi import venues as VN
        with mock.patch.object(VN, "one_path", lambda ctx: True):
            with self.assertRaises(Exception) as cm:   # Sasha 263 · no booking given: hold it first — never "a clear yes first"
                asyncio.run(VN.book_venue(self.ctx("Handle it"), {"approval": {"said": "Handle it"}}))
            self.assertEqual(getattr(cm.exception, "code", ""), "hold_first")
            with self.assertRaises(Exception) as cm:   # words that answer nothing: still no yes
                asyncio.run(VN.book_venue(self.ctx("hmm"), {"name": "X", "party": 2, "approval": {"said": "hmm"}}))
            self.assertEqual(getattr(cm.exception, "code", ""), "no_explicit_yes")

    def test_the_question_remembers_its_booking(self):
        # Sasha 263 · moved: the one question keeps NO second memory of its booking — the card (_HELD) is the one record
        from agapi import venues as VN
        self.assertNotIn("_ASKED_ROUTE", inspect.getsource(VN._execute))
        self.assertIn("hold_venue(ctx, {**booking, \"route\": picked})", inspect.getsource(VN.book_venue))


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
