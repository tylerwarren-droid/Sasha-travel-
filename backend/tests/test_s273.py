"""Sasha 273 · S2 beta fixes from Tyler's live demo with Jon (16 Oct, mailbox rows 1031–1035).
    1  her arrival ends on its own speech-ended event, then ~0.5 s, then the corner — never a duration guessed (frontend; held here too)
    2  ONE card path: a booking an account can't send for (its access closed → the drafted message) shows the SAME booking card
    3  the voice label and the green ring are the mic actually hearing (VoiceButton strict) — never the speaker's "Voice on"
    4  rule 4: she greets only after 30 min quiet, a new day, or with news — the page decides (lib/presence-rule.mjs reappear); the
       return read gives it the last activity (s2_memory.recall last_at) and, on /s2, never tells the model she greeted
    5  the /s2 shell is the dynamic viewport with the safe area at the bottom (frontend)
    6  rule 15: never name OR limit how a place books — read_booking_route says voice.BOOK_IT, a limiting sentence is never said
Offline: no model, no AgAPI, no Places, nothing leaves the process.
    cd backend && python -m unittest tests.test_s273 -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import pathlib
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import s2_memory as M, venues as VN
from agapi.booking_rules import booking_rules as BR
from app.agent import sasha as AG, voice as V

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FRONT = BACKEND.parent / "frontend"
ACCT = "00000000-0000-4000-8000-000000002730"
run = asyncio.run


def _front(case, rel):
    f = FRONT / rel
    if not f.exists():
        case.skipTest("frontend/ is not in this checkout (a backend-only build)")
    return f.read_text(encoding="utf-8")


class ChannelNeverLimited(unittest.TestCase):
    """6 · rule 15 — Tyler's demo (Periplo, four at 21:00): "Periplo takes bookings by phone only", "the only route I can use is a
    phone call". Neither was a voice.py line: the model paraphrased read_booking_route's "By phone." and its routes."""

    DEMO = ["Periplo takes bookings by phone only.", "The only route I can use is a phone call.", "It's by message only.",
            "They only take bookings over the phone.", "Their only way to book is by phone, and it's still a while away."]
    FINE = ["I'll call them now and tell you what they say.", "They take reservations.", "Shall I call them now?",
            "The only way I know is to ask.", "Only one table left at 21:00.", V.BOOK_IT, V.WAIT_TO_CALL, V.CAMERA_OFF, V.SENT]

    def test_the_class_is_caught(self):
        for t in self.DEMO:
            self.assertTrue(V.limits_channel(t), t)
        for t in self.FINE:
            self.assertFalse(V.limits_channel(t), t)
        self.assertTrue(any("limits the channel" in f for f in V.faults([("assistant", self.DEMO[0])])))   # the deploy gate's check
        self.assertEqual(V.faults([("assistant", V.BOOK_IT)]), [])

    def test_no_line_of_hers_limits_it(self):
        for n in dir(V):
            v = getattr(V, n)
            if n.isupper() and isinstance(v, str):
                self.assertFalse(V.limits_channel(v), n)

    def _route(self, eng, one=True):
        ctx = type("Ctx", (), {"account": ACCT, "surface": "s2" if one else "s1"})()
        rd = {"venue": "Periplo", "say": "By phone.", "rungs": {"phone": {"value": "+15005550184"}}}
        with mock.patch("agapi.test_venues.vet", mock.AsyncMock(side_effect=lambda c, a: a)), mock.patch.object(VN, "_read", mock.AsyncMock(return_value=rd)), \
                mock.patch.object(VN, "card_of", lambda *a: None), mock.patch.object(VN, "one_path", lambda c: one), \
                mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=eng)), mock.patch.object(VN, "read_channel", lambda r, c, **k: eng), \
                mock.patch("agapi.venue_truth.reservable_say", lambda c: None):
            return run(VN.read_booking_route(ctx, {"name": "Periplo", "city": "Madrid"}))

    def test_how_they_book_is_said_as_hers_to_do(self):
        for kind in ("phone", "whatsapp", "email", "instagram"):
            how = self._route({"kind": kind})["how"]
            self.assertIn(V.BOOK_IT, how, kind)
            self.assertNotIn("By phone", how)
            self.assertNotIn("By a message", how)
            self.assertFalse(V.limits_channel(how), how)
        self.assertNotIn(V.BOOK_IT, self._route({"kind": "own_engine"})["how"])   # their own form: as before (the form question)
        self.assertEqual(self._route(None)["how"], V.NO_LINK)                    # no way seen: as before

    def test_old_s1_unchanged(self):
        self.assertEqual(self._route({"kind": "phone"}, one=False)["how"], "By phone.")   # parity off: Sasha's own read, as it was
        self.assertEqual(BR.PHRASES["wait_to_call"],
                         "Their only way to book is by phone, and it's still a while away — I'll call them closer to the day.")

    def test_a_limiting_sentence_is_never_said_on_s2(self):
        src = inspect.getsource(AG)
        self.assertIn("if honest and _V.limits_channel(x) and not _V.is_told(x, told):", src)
        self.assertIn('internal_log.append(f"channel limited: {x[:60]}")', src)
        ex = inspect.getsource(VN._execute)
        self.assertIn('o["say"] = o["say"].replace(BR.PHRASES["wait_to_call"], V.WAIT_TO_CALL)', ex)
        self.assertIn("if one_path(ctx):", ex.split("WAIT_TO_CALL")[0][-400:])


class OneCardPath(unittest.TestCase):
    """2 · Jon's account (no access record → closed: nothing sent to venues) got the drafted message for a booking, and the draft drew
    no card — Tyler's got the read-back card. The same booking now shows the same card, whatever the account's access."""

    def _draft(self, one=True):
        ctx = type("Ctx", (), {"account": ACCT, "surface": "s2" if one else "s1"})()
        rd = {"venue": "Periplo", "country": "ES", "rungs": {"whatsapp": {"value": "+15005550184"}}}
        res = {"how_many": {"count": 4}, "who": {"name": "Alex"}, "when": {"at": "2026-10-16T21:00"}}
        with mock.patch.object(VN, "one_path", lambda c: one):
            try:
                return VN._draft(ctx, {"what": "a table"}, rd, res, "2026-10-16T21:00", datetime.now(timezone.utc), "whatsapp")
            finally:
                VN._HELD.pop(ACCT, None)

    def test_the_draft_has_the_booking_card(self):
        out = self._draft()
        self.assertEqual(out["status"], "draft_message")
        self.assertEqual(out["read_back"][0], "Periplo")
        self.assertIn("4 people", out["read_back"][1])
        self.assertTrue(out["read_back"][2].startswith("The message: “Hola"))
        ev = AG.render("hold_venue", out, {})
        self.assertEqual(ev["kind"], "read_back")                    # the ONE booking card (/s2 CardView's read_back)
        self.assertEqual(ev["read_back"], out["read_back"])
        self.assertIsNone(AG.render("hold_venue", {"status": "draft_message"}, {}))   # nothing to read back: nothing drawn

    def test_old_s1_unchanged(self):
        self.assertNotIn("read_back", self._draft(one=False))


class ReturnRead(unittest.TestCase):
    """4 · the 11:03 bug: s2_memory.recall's opening line was appended by /s2 on EVERY load (an iPhone reloading a backgrounded tab
    mid-booking). Rule 4 is the page's; the return read gives it the last activity and doesn't tell the model she greeted."""

    def setUp(self):
        AG._HANDOVER.pop("s273-sess", None)

    def _recall(self, m, surface):
        with mock.patch.object(M, "_load", mock.AsyncMock(return_value=m)), mock.patch.object(M, "opening", mock.AsyncMock(return_value="Hey Alex, what can I help you with?")), \
                mock.patch.object(M, "put_kinds", mock.AsyncMock()), mock.patch.object(M, "line_for", lambda m_, a: "Welcome back" if m_ and m_.get("thing") else None):
            return run(M.recall(ACCT, "s273-sess", surface=surface))

    def test_last_activity_comes_back(self):
        at = "2026-10-16T09:02:40+00:00"
        got = self._recall({"thing": "a table at Periplo", "updated_at": at, "recent": []}, "s2")
        self.assertEqual(got["last_at"], at)
        self.assertEqual(self._recall({"updated_at": at}, "s2")["last_at"], at)          # no topic: still its last activity
        self.assertIsNone(self._recall(None, "s2")["last_at"])                           # a first visit: none (rule 4 (a))

    def test_s2_never_tells_the_model_she_greeted(self):
        self._recall({"thing": "a table at Periplo", "updated_at": "2026-10-16T09:02:40+00:00", "recent": []}, "s2")
        self.assertNotIn("you greeted them", AG._HANDOVER["s273-sess"])
        self.assertIn("They have just come back to the conversation", AG._HANDOVER["s273-sess"])
        self._recall({"thing": "a table at Periplo", "updated_at": "2026-10-16T09:02:40+00:00", "recent": []}, None)
        self.assertIn('you greeted them with "Hey Alex, what can I help you with?"', AG._HANDOVER["s273-sess"])   # /next, WhatsApp: as before

    def test_only_s2s_route_says_s2(self):
        src = inspect.getsource(AG)
        self.assertEqual(src.count('MEM.recall(account, session[:64] or None, surface="s2")'), 1)
        self.assertEqual(src.count("MEM.recall(account, session[:64] or None))"), 1)    # /next's /memory: unchanged

    def test_live_events_carry_when(self):
        self.assertIn("'at': ev.get('_at')", inspect.getsource(AG.agent_events))


class FrontHeld(unittest.TestCase):
    """1, 3, 4, 5 · the page's halves, held from the backend suite too (scripts/presence-rule.test.mjs holds them in node)."""

    def test_presence_rule(self):
        rule = _front(self, "lib/presence-rule.mjs")
        for s in ("export const HOLD_MS = 500", "export const IDLE_MS = 30 * 60 * 1000", "export function reappear(s)", "export function voiceOf(s)",
                  "export function inView(", "words: s.asleep ? PAUSED : live ? VOICE_ON : TAP_TO_TALK"):
            self.assertIn(s, rule)

    def test_arrival_on_speech_ended(self):
        hello = _front(self, "app/s2/S2Hello.tsx")
        self.assertNotIn("secs * 1000", hello)
        self.assertIn("s.on(AgentEventsEnum.AVATAR_SPEAK_ENDED, () => finished('speech ended'))", hello)
        self.assertIn("await f.say(t)   // her live face says it", hello)

    def test_page(self):
        app = _front(self, "app/s2/S2App.tsx")
        self.assertIn("data-s2-shell style={{ height: '100dvh'", app)
        self.assertIn("strict ctlRef={voiceCtl} onConnectedChange={setMicLive}", app)
        self.assertNotIn("'🔊 Voice on'", app)
        self.assertIn("const r = rule4()", app)
        vb = _front(self, "app/components/VoiceButton.tsx")
        self.assertIn("if (!strictRef.current || !hearingRef.current) return", vb)   # strict is /s2's alone: /next unchanged

    def test_in_the_gate(self):
        suite = (BACKEND / "scripts" / "one_truth_suite.py").read_text(encoding="utf-8")
        self.assertIn('["tests.test_s273"]', suite)


if __name__ == "__main__":
    unittest.main()
