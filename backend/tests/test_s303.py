"""Sasha 303 · T81 — ONE GATE OPENS AND CLOSES EVERY AVATAR SESSION (HeyGen / LiveAvatar bills by the minute).

Root test (docs/sasha/s303-avatar-gate.md, written before code): (1) app/avatar_gate.py is the one place a session may open, is held
(its session token, server-side) and is closed (POST /v1/sessions/stop with that token); (2) no second copy — the page keeps no idle
timer, the server's reaper decides quiet / hidden / lost / caps; (3) a session the gate didn't open can't be registered (it is
stopped at once), and every open one is closed by the reaper.

    cd backend && python -m unittest tests.test_s303 -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import unittest
from unittest import mock

from app import avatar_gate as AG

REAL, GUEST, TEST = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"
META = {REAL: {}, GUEST: {"kanoe_guest": True}, TEST: {"kanoe_guest": True, "kanoe_test": True}}


def run(c):
    return asyncio.run(c)


class Base(unittest.TestCase):
    def setUp(self):
        AG.reset()
        self.t = [1_000_000.0]
        self.stopped, self.logged = [], []

        async def stop(token):
            self.stopped.append(token)
            return True

        async def meta(account):
            return META.get(account)

        async def log(row):
            self.logged.append(row)
        self.p = [mock.patch.object(AG, "NOW", lambda: self.t[0]), mock.patch.object(AG, "STOP", stop),
                  mock.patch.object(AG, "META", meta), mock.patch.object(AG, "LOG", log),
                  mock.patch.object(AG, "LEDGER_SAVE", mock.AsyncMock()), mock.patch.object(AG, "LEDGER_LOAD", mock.AsyncMock(return_value={})),
                  mock.patch.dict(os.environ, {"SASHA_AVATAR_PERSON_MIN_DAY": "10", "SASHA_AVATAR_KANOE_MIN_DAY": "60"})]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        AG.reset()

    def later(self, s):
        self.t[0] += s
        run(AG.reap())

    def live(self, account=REAL):
        o = run(AG.open(account, "s2", "tap"))
        self.assertTrue(o["ok"], o)
        self.assertTrue(run(AG.opened(account, o["sid"], "tok-" + o["sid"], "sess-1"))["ok"])
        return o["sid"]


class OnlyARealPersonsTap(Base):
    def test_a_test_or_guest_account_never_opens_one(self):
        for who in (TEST, GUEST, None, AG.DEMO):
            r = run(AG.open(who, "s2", "tap"))
            self.assertFalse(r["ok"], who)
            self.assertEqual(r["rule"], "not_a_person")
        self.assertEqual(AG.open_count(), 0)

    def test_only_a_tap_on_s2_opens_one(self):
        for surface, why in (("s2", "arrival"), ("s2", "prefetch"), ("next", "tap"), ("vietnam", "tap"), ("whatsapp", "tap")):
            r = run(AG.open(REAL, surface, why))
            self.assertEqual((r["ok"], r["rule"]), (False, "not_a_tap"), (surface, why))
        self.assertTrue(run(AG.open(REAL, "s2", "tap"))["ok"])

    def test_a_session_the_gate_did_not_open_is_stopped_at_once(self):
        r = run(AG.opened(REAL, "sid_nobody_opened", "tok-x", "sess-x"))
        self.assertFalse(r["ok"])
        self.assertEqual(self.stopped, ["tok-x"])
        sid = run(AG.open(REAL, "s2", "tap"))["sid"]
        self.assertFalse(run(AG.opened(GUEST, sid, "tok-y", "s"))["ok"])   # another account's sid: stopped too
        self.assertEqual(self.stopped, ["tok-x", "tok-y"])


class AQuietClose(Base):
    def test_sixty_seconds_with_nobody_talking_ends_it_on_the_server(self):
        sid = self.live()
        for _ in range(5):   # the page's beats say it is open — but nobody is talking
            self.later(10)
            run(AG.beat(REAL, sid, talking=False, visible=True))
        self.assertEqual(self.stopped, [])
        self.later(11)   # 61 s since the last talk
        self.assertEqual(self.stopped, ["tok-" + sid])
        self.assertEqual(self.logged[-1]["closed_why"], "quiet")

    def test_talking_keeps_it_open(self):
        sid = self.live()
        for _ in range(9):
            self.later(15)
            run(AG.beat(REAL, sid, talking=True, visible=True))
        self.assertEqual(self.stopped, [])

    def test_his_turn_counts_as_talking(self):
        sid = self.live()
        for _ in range(2):
            self.later(25)
            run(AG.beat(REAL, sid, talking=False, visible=True))
        AG.touch(REAL)   # 50 s in: his turn
        for _ in range(2):
            self.later(25)
            run(AG.beat(REAL, sid, talking=False, visible=True))
        self.assertEqual(self.stopped, [])   # 50 s since his turn: not quiet yet
        from app.agent import sasha as S
        self.assertIn("_AVATAR.touch(account)", inspect.getsource(S.agent_turn))

    def test_a_hidden_tab_ends_it(self):
        sid = self.live()
        run(AG.beat(REAL, sid, talking=False, visible=False))
        self.assertEqual(self.stopped, ["tok-" + sid])
        self.assertEqual(self.logged[-1]["closed_why"], "hidden")

    def test_a_closed_tab_ends_it_without_a_word_from_the_page(self):
        sid = self.live()
        self.later(31)
        self.assertEqual(self.stopped, ["tok-" + sid])
        self.assertEqual(self.logged[-1]["closed_why"], "lost")

    def test_camera_off_ends_the_session_not_only_the_video(self):
        sid = self.live()
        self.later(5)
        run(AG.close(REAL, sid, "camera_off"))
        self.assertEqual(self.stopped, ["tok-" + sid])
        self.assertEqual(AG.open_count(), 0)

    def test_a_mint_that_never_arrives_is_dropped(self):
        run(AG.open(REAL, "s2", "tap"))
        self.later(21)
        self.assertEqual(AG.open_count(), 0)
        self.assertEqual(self.stopped, [])   # nothing to stop: no session started
        self.assertEqual(self.logged[-1]["closed_why"], "never_started")


class Caps(Base):
    def test_unset_caps_open_nothing(self):
        with mock.patch.dict(os.environ, {"SASHA_AVATAR_PERSON_MIN_DAY": "", "SASHA_AVATAR_KANOE_MIN_DAY": ""}):
            r = run(AG.open(REAL, "s2", "tap"))
        self.assertEqual((r["ok"], r["rule"]), (False, "cap_kanoe"))

    def test_his_minutes_today_switch_her_to_voice_and_she_says_so(self):
        with mock.patch.dict(os.environ, {"SASHA_AVATAR_PERSON_MIN_DAY": "1"}):
            sid = self.live()
            for _ in range(5):
                self.later(10)
                run(AG.beat(REAL, sid, talking=True, visible=True))
            self.assertEqual(self.stopped, [])
            self.later(11)   # 61 s of a 60 s day
            self.assertEqual(self.stopped, ["tok-" + sid])
            self.assertEqual(self.logged[-1]["closed_why"], "cap_person")
            r = run(AG.open(REAL, "s2", "tap"))
        self.assertEqual((r["ok"], r["rule"]), (False, "cap_person"))
        self.assertEqual(r["say"], AG.CAP_LINE)
        self.assertEqual(AG.CAP_LINE.count("."), 1)   # one line

    def test_kanoes_ceiling_holds_for_everyone(self):
        with mock.patch.dict(os.environ, {"SASHA_AVATAR_KANOE_MIN_DAY": "1"}):
            sid = self.live()
            for s in (30, 20):
                self.later(s)
                run(AG.beat(REAL, sid, talking=True, visible=True))
            other = "44444444-4444-4444-8444-444444444444"
            META[other] = {}
            try:
                self.later(11)   # 61 s of Kanoe's 60 s day
                self.assertEqual(self.logged[-1]["closed_why"], "cap_kanoe")
                r = run(AG.open(other, "s2", "tap"))
            finally:
                META.pop(other)
        self.assertEqual((r["ok"], r["rule"]), (False, "cap_kanoe"))

    def test_the_caps_are_settings_never_numbers_in_the_code(self):
        src = inspect.getsource(AG.caps)
        self.assertIn("SASHA_AVATAR_PERSON_MIN_DAY", src)
        self.assertIn("SASHA_AVATAR_KANOE_MIN_DAY", src)
        self.assertNotRegex(src, r"or \d|, \d+\)|default=\d")


class TheLog(Base):
    def test_one_row_per_session_with_its_seconds(self):
        sid = self.live()
        for _ in range(4):
            self.later(10)
            run(AG.beat(REAL, sid, talking=True, visible=True))
        self.later(2)
        run(AG.close(REAL, sid, "left"))
        self.assertEqual(len(self.logged), 1)
        row = self.logged[0]
        self.assertEqual((row["seconds"], row["opened_why"], row["surface"], row["closed_why"]), (42, "tap", "s2", "left"))
        self.assertNotIn(REAL, str(row))   # who is hashed
        self.assertTrue(row["who"])
        self.assertLess(row["opened_at"], row["closed_at"])
        self.assertEqual(AG.today()["seconds"], 42)

    def test_the_ledger_counts_the_day_not_the_log(self):
        src = inspect.getsource(AG)
        self.assertNotIn("read_rows", src)
        self.assertNotIn("read_week", src)   # S275: measures are never an authority


if __name__ == "__main__":
    unittest.main()
