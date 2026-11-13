"""Sasha 381i · (1) SASHA NEVER SAYS AN ACT HAPPENED UNLESS IT DID — the line comes from the act's RESULT; (2) A TIME IS READ BY WHAT IT
IS AND HOW IT REACHED SASHA — typed or through speech-to-text, from the ONE door reader. NO PATCHES.

Found by 37dddc70's recording gate (b656d30e, row 1991):
  (1) "the same instruction spoken again" → acts [] (the send-once claim held) yet she said "Booking now: Sasha Test Venue …, 3 people,
      Sat 14 Nov at 21:30. Requested — I'll tell you when they reply." — already_sent had no line said by code, so the model wrote one,
      echoing the act before. Now every venue result where nothing acted (already_sent, not_sent: outside the instruction, no proof,
      the approval refused) says ITS OWN line by code (voice.yes_line), the turn ends on it, and "Booking now" in her own words is a
      guard failure unless a booking acted this turn (sasha.guard_check acted_now).
  (2) VENUE ROUTE ×3 asked "11:37am or 11:37pm?" for a typed "11:37". A typed clock time is the 24-hour clock as written; only words
      that came through speech-to-text are unsure when ≤ 12:59 with no side said. The entry point that transcribes records it
      (venue_submit.SPOKEN: the voice page, S2's and /next's mic — channel "voice", a WhatsApp voice note); door() carries it
      ("words": "spoken" | "typed"); agapi.said reads it there — never a guess.

    cd backend && python -m unittest tests.test_s381i_said_from_the_result -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import unittest
from datetime import timedelta
from unittest import mock

from agapi import said as SD, v0 as API, venues as VN, venue_submit as VS
from app.agent import sasha as S, voice as V
from tests.test_s254_handle_it_live import use_fake_agapi
from tests.test_s254_one_decider import ACCT, ALL4, Base, engine_from, reader

run = asyncio.run
REAL_CLAIM = API.claim
BACKEND = pathlib.Path(__file__).resolve().parents[1]


def said_line(result: dict) -> str:
    return V.yes_line("hold_venue", {"ok": True, "result": result})


class EveryRefusalSaysItsOwnLine(unittest.TestCase):
    def test_already_sent(self):
        with mock.patch.object(VS, "bookings", mock.AsyncMock(return_value=[{"venue": "Casa Gate", "status": "requested"}])):
            out = run(VN._tap_refused(API.Ctx(account=ACCT), {"venue": "Casa Gate"}, "approval_consumed", {}, "Casa Gate"))
        self.assertEqual(out["status"], "already_sent")
        line = said_line(out)
        self.assertTrue(line.startswith(V.TAP_SAYS["approval_consumed"]), line)
        self.assertNotRegex(line, V.ACTING)

    def test_outside_the_instruction(self):
        out = run(VN._not_sent(API.Ctx(account=ACCT), {"venue": "Casa Gate", "rung": "agapi"},
                               {"code": "outside_instruction", "outside": [{"why": "another_time"}]}, "Casa Gate"))
        self.assertEqual((out["status"], said_line(out)), ("not_sent", V.outside_line(["another_time"])))
        self.assertNotRegex(said_line(out), V.ACTING)

    def test_no_proof_and_a_refused_approval(self):
        for code in ("approval_untrusted_origin", "approval_expired", "approval_void"):
            out = run(VN._tap_refused(API.Ctx(account=ACCT), {"venue": "Casa Gate"}, code, {}, "Casa Gate"))
            self.assertEqual((out["status"], said_line(out)), ("not_sent", V.tap_line(code)), code)
            self.assertNotRegex(said_line(out), V.ACTING)

    def test_a_term_missing(self):
        out = VN._ask_terms({"name": "Casa Gate"}, ["date"], "book Casa Gate at 21:00 for 2")
        self.assertEqual(said_line(out), "Which day?")

    def test_only_an_act_says_booking_now(self):
        acted = {"status": "requested", "acted": True, "line": "Booking now: Casa Gate, 2 people, Sat 14 Nov at 21:00. " + V.REQUESTED}
        self.assertRegex(said_line(acted), V.ACTING)

    def test_her_own_booking_now_is_a_guard_failure_unless_acted(self):
        text = "Booking now: Casa Gate, 3 people, Sat 14 Nov at 21:30. Requested — I'll tell you when they reply."
        self.assertTrue(any("Booking now" in b for b in S.guard_check(text, set(), True)))
        self.assertFalse(any("Booking now" in b for b in S.guard_check(text, set(), True, acted_now=True)))


class TheSameInstructionAgain(Base):
    """Through the real turn: the same instruction in the same conversation → its own "already sent" line, never "Booking now"."""

    def setUp(self):
        super().setUp()
        self.agapi = use_fake_agapi(self)
        p = mock.patch("agapi.v0.claim", REAL_CLAIM)   # the base stubs the claim; here it is the real one (in-process, no database)
        p.start()
        self.addCleanup(p.stop)
        API._CLAIMED.clear()
        b = mock.patch.object(VS, "bookings", mock.AsyncMock(return_value=[{"venue": "Casa Gate", "status": "requested"}]))
        b.start()
        self.addCleanup(b.stop)

    def hold(self, words, day):
        args = {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "party": 3, "day": day, "time": "21:30",
                "place_id": "ChIJcasagate254"}
        rungs = {"email": ALL4["email"]}
        with mock.patch.object(VN, "_read", reader(rungs, "Casa Gate")), mock.patch.object(VN, "engine_channel", engine_from(rungs, None)):
            return run(VN.hold_venue(API.Ctx(account=ACCT, mode="test", user_said=words, session="s381i", surface="s2", via="wa"), args))

    def test_twice(self):
        day = (VN._today("ES") + timedelta(days=3)).isoformat()
        words = f"book Casa Gate on {day} at half past nine at night for 3"
        first = self.hold(words, day)
        self.assertRegex(said_line(first), V.ACTING)
        again = self.hold(words, day)
        self.assertIn(again["status"], V.REFUSED)
        self.assertNotRegex(said_line(again), V.ACTING)
        self.assertTrue(said_line(again))


class TheSameCallAgain(TheSameInstructionAgain):
    """Found by d9d75bba's recording gate (39230f4d): the same words in a new talk → the same turn key → the same once-only key: the
    call returned the first act's answer and she said its "Booking now" again, nothing acted (acts []). A replayed act → already sent."""

    def call(self, words, day):
        args = {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "party": 3, "day": day, "time": "21:30",
                "place_id": "ChIJcasagate254", "idempotency_key": "s381i-same-key"}
        rungs = {"email": ALL4["email"]}
        with mock.patch.object(VN, "_read", reader(rungs, "Casa Gate")), mock.patch.object(VN, "engine_channel", engine_from(rungs, None)):
            return run(API.call(API.Ctx(account=ACCT, mode="test", user_said=words, session="s381i-call", surface="s2", via="wa"),
                                "hold_venue", args))

    def test_a_replayed_act_is_already_sent(self):
        API._IDEM.clear()
        self.addCleanup(API._IDEM.clear)
        day = (VN._today("ES") + timedelta(days=3)).isoformat()
        words = f"book Casa Gate on {day} at half past nine at night for 3"
        first = self.call(words, day)
        self.assertRegex(V.yes_line("hold_venue", first), V.ACTING)
        again = self.call(words, day)
        self.assertTrue(again.get("replayed"))
        self.assertEqual(again["result"]["status"], "already_sent")
        line = V.yes_line("hold_venue", again)
        self.assertTrue(line.startswith(V.TAP_SAYS["approval_consumed"]), line)
        self.assertNotRegex(line, V.ACTING)


class TypedOrSpoken(Base):
    """The same "11:37" — typed: booked at 11:37; through speech-to-text: asked "11:37am or 11:37pm?"."""

    def setUp(self):
        super().setUp()
        self.agapi = use_fake_agapi(self)

    def hold(self, words, day, at, spoken):
        args = {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "party": 2, "day": day, "time": at,
                "place_id": "ChIJcasagate254"}
        rungs = {"email": ALL4["email"]}
        tok = VS.SPOKEN.set(spoken)
        try:
            with mock.patch.object(VN, "_read", reader(rungs, "Casa Gate")), mock.patch.object(VN, "engine_channel", engine_from(rungs, None)):
                return run(VN.hold_venue(API.Ctx(account=ACCT, mode="test", user_said=words, session=f"s381i-{spoken}-{words}",
                                                 surface="s2", via="wa"), args))
        finally:
            VS.SPOKEN.reset(tok)

    def scope(self):
        return [b for o, b, _a in self.agapi.calls if o == "approvals.mandate"][-1]["scope"]["booking"]

    def test_typed_11_37_is_11_37(self):
        day = (VN._today("ES") + timedelta(days=3)).isoformat()
        out = self.hold(f"book Casa Gate on {day} at 11:37 for 2", day, "11:37", spoken=False)
        self.assertNotEqual(out.get("status"), "need_term", out)
        self.assertEqual(self.scope()["time"], "11:37")

    def test_spoken_11_37_is_asked(self):
        day = (VN._today("ES") + timedelta(days=3)).isoformat()
        out = self.hold(f"book Casa Gate on {day} at 11:37 for 2", day, "11:37", spoken=True)
        self.assertEqual((out["status"], out["ask"]), ("need_term", "11:37am or 11:37pm?"))

    def test_the_rules(self):
        self.assertEqual(SD.times_in("at 11:37", spoken=False), ["11:37"])
        self.assertEqual(SD.times_in("at 09:00", spoken=False), ["09:00"])
        for w in ("at nine", "at 09:00", "at 12:30"):
            self.assertEqual(SD.times_in(w, spoken=True), [], w)
        for sp in (False, True):
            self.assertEqual(SD.times_in("at 21:30", spoken=sp), ["21:30"])
            for w in ("nine thirty", "at nine thirty", "at 9:30", "half past nine"):
                self.assertNotIn("21:00", SD.times_in(w, spoken=sp), (w, sp))
        self.assertEqual(SD.times_in("dinner at 9:30", spoken=False), ["21:30"])   # a side said wins, typed too


class TheDoorSaysHow(unittest.TestCase):
    def test_door_carries_the_words(self):
        tok, t2 = VS.TAP.set({"kind": "supabase", "token": "t"}), VS.SPOKEN.set(True)
        try:
            self.assertEqual(VS.door(), {"kind": "in_app", "words": "spoken"})
        finally:
            VS.SPOKEN.reset(t2)
            VS.TAP.reset(tok)
        self.assertEqual(VS.words_heard(), "typed")
        self.assertIn("VS.door()", inspect.getsource(SD._heard))

    def test_every_transcribing_entry_point_records_it(self):
        for rel, rec in (("app/api/voice_conductor.py", "_VS.SPOKEN.set(True)"), ("app/api/conductor.py", "_VS.SPOKEN.set(False)"),
                         ("app/agent/sasha.py", '_VS.SPOKEN.set(str(body.get("channel") or "") == "voice")'),
                         ("booking_signer/guest_whatsapp.py", "_VSW.SPOKEN.set(bool(heard))")):
            self.assertIn(rec, (BACKEND / rel).read_text(), rel)
        # /next's and S2's mic (channel "voice") are held by the frontend's prebuild (scripts/check-outcome-surfaces.mjs, Sasha 381i)

if __name__ == "__main__":
    unittest.main()
