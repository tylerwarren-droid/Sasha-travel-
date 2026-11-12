"""Sasha 381 · THE INSTRUCTION IS THE APPROVAL — no separate yes for a venue booking (Tyler, KANOE_DECISIONS.md, 12 Nov 20:11), and a term
the person didn't give is ASKED — only that term — never guessed, never a yes card (12 Nov 20:20, reading B). NO PATCHES.

Found: every venue act (Kanoe's form / email / WhatsApp, the call, the platform's Book) stopped on a read-back card ("Shall I send this to
Casa Gate? Every detail is on the card." · "Casa, Fri 13 Nov 21:00 for 2. Send?" · the call's OK) and waited for a yes in a later turn; a
party the person never gave was 2 (venues._reservation). Now ONE act path (venues._act): AgAPI's prepared booking → its read-back (kept on
the act, never shown) → the approval, which IS the instruction (in the app its proof — CR 196; on WhatsApp its own signed message,
CR 99 §4d) → venue.submit_booking, in the same turn, once. Said in ONE line: "Booking now: <AgAPI's venue (CR 194)>, <N> people, <date> at
<time>." then "Booked — reference X." / "Requested — I'll tell you when they reply."

    cd backend && python -m unittest tests.test_s381_instruction_is_the_approval -v
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import os
import pathlib
import re
import unittest
from datetime import date
from unittest import mock

from agapi import v0 as API, venue_submit as VS, venue_truth as VT, venues as VN
from app.agent import voice as V
from tests.test_s254_handle_it_live import RB, use_fake_agapi
from tests.test_s254_one_decider import ACCT, ALL4, Base, local, reader, engine_from

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]


class TheTermsAreTheirs(unittest.TestCase):
    def ctx(self, said, before=""):
        return API.Ctx(account=ACCT, user_said=said, said_before=before, surface="s2")

    def test_a_term_they_didnt_give_is_asked_only_that_term(self):
        a = {"name": "Casa Gate", "day": "2026-11-20", "time": "21:00", "country": "ES"}
        self.assertEqual(VN.unsaid_term(self.ctx("book Casa Gate 2026-11-20 at 21:00"), a), "people")            # no party: never 2
        self.assertEqual(VN.unsaid_term(self.ctx("book Casa Gate 2026-11-20 at 21:00"), {**a, "party": 2}), "people")   # 2 not said
        self.assertEqual(VN.unsaid_term(self.ctx("book Casa Gate at 21:00 for 2"), {**a, "party": 2}), "day")
        self.assertEqual(VN.unsaid_term(self.ctx("book Casa Gate 2026-11-20 for 2"), {**a, "party": 2}), "time")
        self.assertIsNone(VN.unsaid_term(self.ctx("book Casa Gate 2026-11-20 at 21:00 for 2"), {**a, "party": 2}))

    def test_the_answer_completes_the_instruction_across_turns(self):
        a = {"name": "Casa Gate", "day": "2026-11-20", "time": "21:00", "country": "ES", "party": 4}
        self.assertIsNone(VN.unsaid_term(self.ctx("4 people", before="book Casa Gate on 2026-11-20 at 21:00"), a))

    def test_the_question_is_the_term_only(self):
        self.assertEqual(V.TERM_ASK["people"], "For how many people?")


class ActedOnTheInstruction(Base):
    def setUp(self):
        super().setUp()
        self.agapi = use_fake_agapi(self)
        self.agapi.submit.update(status="sent", venue="La Taberna de Peñalver")

    def instruct(self, said, party=2, **extra):
        day, hhmm = local(72.0)
        args = {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "day": day, "time": hhmm,
                "place_id": "ChIJcasagate254", **({"party": party} if party else {}), **extra}
        rungs = {"email": ALL4["email"]}
        with mock.patch.object(VN, "_read", reader(rungs, "Casa Gate")), mock.patch.object(VN, "engine_channel", engine_from(rungs, None)):
            return run(VN.hold_venue(API.Ctx(account=ACCT, mode="test", user_said=said.format(day=day, hhmm=hhmm), session="s381",
                                             surface="s2", via="wa"), args)), day, hhmm

    def test_no_party_is_asked_and_nothing_is_prepared(self):
        out, _d, _h = self.instruct("book Casa Gate {day} at {hhmm}", party=None)
        self.assertEqual((out["status"], out["ask"]), ("need_term", "For how many people?"))
        self.assertNotIn("venue.prepare_booking", self.agapi.ops())
        self.assertEqual(V.yes_line("hold_venue", {"ok": True, "result": out}), "For how many people?")   # said by code, word for word

    def test_the_whole_instruction_books_in_the_same_turn_in_one_line(self):
        out, day, hhmm = self.instruct("book Casa Gate {day} at {hhmm} for 2")
        self.assertNotEqual(out["status"], "awaiting_yes")                                        # never a yes card
        (body,) = [b for o, b, _a in self.agapi.calls if o == "approvals.in_app_tap"]             # approved and sent, this turn
        self.assertEqual((body["read_back_id"], body["session"]["kind"]), (RB, "in_app"))         # CR 196 · the instruction's proof
        d = date.fromisoformat(day)
        # AgAPI's prepared venue (the fake's "Casa Gate"; CR 194: its identity) — the line is Tyler's, word for word
        self.assertEqual(out["line"], f"Booking now: Casa Gate, 2 people, {d:%a} {d.day} {d:%b} at {hhmm}. "
                                      "Requested — I'll tell you when they reply.")
        self.assertNotIn(ACCT, VN._HELD)                                                          # nothing waits for a yes

    def test_confirmed_says_booked_with_its_reference(self):
        self.agapi.submit.update(status="confirmed", reference="TB-4471")
        out, day, hhmm = self.instruct("book Casa Gate {day} at {hhmm} for 2")
        self.assertIn(". Booked — reference TB-4471.", out["line"])                         # then Sasha 279's closing, as before


class TheProof(unittest.TestCase):
    """CR 196 · the in-app instruction as approvals.in_app_tap's session — signed only for a turn whose request carried a verified session."""

    def test_the_vector(self):
        tok = VS.TAP.set({"kind": "supabase", "token": "t"})
        try:
            with mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": "s381-secret"}):
                got = VS.instruction_session({"instruction_id": "turn_abc", "session_id": "conv_1"}, "acct_1", RB, "f" * 64,
                                             t=1763000000, nonce="n" * 32)
        finally:
            VS.TAP.reset(tok)
        want = hmac.new(b"s381-secret", f"1763000000.{'n' * 32}.in_app.turn_abc.acct_1.{RB}.{'f' * 64}".encode(), hashlib.sha256).hexdigest()
        self.assertEqual(got, {"kind": "in_app", "t": 1763000000, "nonce": "n" * 32, "instruction_id": "turn_abc", "session_id": "conv_1",
                               "signature": want})

    def test_never_signed_without_a_verified_session_or_an_instruction(self):
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": "s381-secret"}):
            self.assertIsNone(VS.instruction_session({"instruction_id": "turn_abc"}, "acct_1", RB, "f" * 64))   # no TAP
            tok = VS.TAP.set({"kind": "supabase", "token": "t"})
            try:
                self.assertIsNone(VS.instruction_session({"instruction_id": ""}, "acct_1", RB, "f" * 64))
            finally:
                VS.TAP.reset(tok)

    def test_the_in_app_act_sends_the_instruction_not_a_tap(self):
        calls = []

        async def call(op, body, approval=None, account=None):
            calls.append((op, body))
            return {"ok": True, "result": {"approval_id": "apv_1", "result": {"status": "sent", "act_id": "act_1"}}}
        tok = VS.TAP.set({"kind": "supabase", "token": "t"})
        try:
            with mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": "s381-secret"}), mock.patch.object(VS, "CALL", call), \
                    mock.patch.object(VS, "_remember", mock.AsyncMock()):
                run(VS.submit("acct_1", {"read_back_id": RB, "prepared_id": "vpr_" + "a" * 32, "sha": "f" * 64, "end_user": "eu_1"},
                              "book it", instruction={"instruction_id": "turn_abc", "session_id": "conv_1"}))
        finally:
            VS.TAP.reset(tok)
        (op, body), = calls
        self.assertEqual((op, body["session"]["kind"], body["session"]["instruction_id"]), ("approvals.in_app_tap", "in_app", "turn_abc"))


class TheCardsName(unittest.TestCase):
    def test_agapis_identity_never_a_page_heading(self):
        site = {"name": {"value": "Restaurante Mediterraneo en Madrid"}, "identity": {"name": "La Taberna de Peñalver", "source": "place"}}
        self.assertEqual(VT.shape({"name": "La Taberna de Peñalver", "place_id": "p1"}, site)["name"], "La Taberna de Peñalver")
        self.assertEqual(VT.shape({"name": "La Taberna de Peñalver", "place_id": "p1"}, {"name": {"value": "Restaurante Mediterraneo"}})["name"],
                         "La Taberna de Peñalver")                                                  # a page's reading never names it


class TheRatchet(unittest.TestCase):
    def test_no_yes_card_for_a_venue_act_and_no_default_party(self):
        src = (BACKEND / "agapi/venues.py").read_text()
        for gone in ("kanoe_card", "_kanoe_now", "BR_ask_call", "OK_CHOICES", "KANOE_CHOICES", "kanoe_ask", "wa_done_line"):
            self.assertNotIn(gone + "(", src.replace("def " + gone, ""), gone)
            self.assertFalse(hasattr(V, gone) or hasattr(VN, gone), gone)
        self.assertIsNone(re.search(r"""a\.get\(["']party["']\)\s*or\s*[1-9]""", src))
        for rung in ('"agapi"', '"agapi_call"'):                                                 # an act is never held for a yes
            self.assertNotIn(f"_hold(ctx, {rung}", src)
        self.assertIn("instruction=instruction_of(ctx)", inspect.getsource(VN._agapi_send))
        self.assertIn("instruction=instruction_of(ctx)", inspect.getsource(VN._agapi_call))


if __name__ == "__main__":
    unittest.main()
