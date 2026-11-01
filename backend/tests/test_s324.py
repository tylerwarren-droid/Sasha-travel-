"""Sasha 324 · outcome logging (docs/sasha/S-324-outcomes.md).

Root test: (1) one truth — the one booking record (AgAPI's act, which records its own outcome on AgAPI's ledger; Sasha's trip item); no
second outcome table; (2) a per-surface log = PATCH — Sasha writes only an attempt that ended BEFORE an act, from ONE choke point (v0.call);
(3) no booking, change or cancel ends without a recorded outcome (an AgAPI cancel / change act: on its record, and the ledger gap named).
Offline.

    cd backend && python -m unittest tests.test_s324 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import outcomes_week as OW, s2_outcomes as OC, venue_submit as VS

ROOT = pathlib.Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def ago(h):
    return (NOW - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")


class OneLedgerNeverTwice(unittest.TestCase):
    def test_an_agapi_act_is_never_recorded_by_sasha(self):
        sent = []

        async def call(op, body):
            sent.append(op)
            return {"ok": True, "result": {}}
        with mock.patch.object(OC, "CALL", call):
            for rung in ("agapi", "agapi_call"):
                asyncio.run(OC.booked("acct", {"rung": rung, "id": "p1", "at": NOW}, "Casa Lucio", "Madrid", result={"status": "requested"}))
        self.assertEqual(sent, [])                                                          # AgAPI's own row is the one

    def test_an_attempt_that_ended_before_an_act_is_recorded_once_with_why(self):
        E = OC.ended_without_act
        self.assertEqual(E("book_venue", True, {"status": "to_tyler", "venue": "X"}, None), "handed to Tyler")
        self.assertEqual(E("cancel_venue", True, {"status": "to_tyler"}, None), "handed to Tyler")
        self.assertEqual(E("hold_venue", False, None, "not_prepared"), "failed: not_prepared")
        self.assertIsNone(E("hold_venue", False, None, "missing_input"))                   # a question back: the attempt goes on
        self.assertIsNone(E("book_venue", True, {"status": "requested", "act_id": "act_1"}, None))   # an act: AgAPI records it
        self.assertIsNone(E("search_venues", True, {"status": "to_tyler"}, None))          # not a booking tool
        # Tyler (1 Nov): a hand-off to Tyler is NEVER sent to AgAPI under another channel's name (until CR 155): the turn's measure only
        sent, noted = [], []

        async def send(op, b, account=None):
            sent.append(op)
        with mock.patch.object(OC, "_send", send), mock.patch("agapi.measure.handed", lambda a, v, k, surface="s2": noted.append((v, k))):
            asyncio.run(OC.no_act("acct", "cancel_venue", "handed to Tyler", {"venue": "Botín"}, {"what": "restaurant"}))
        self.assertEqual(sent, [])                                                         # nothing to AgAPI
        self.assertEqual(noted, [("Botín", "cancel")])
        src = (ROOT / "backend/agapi/s2_outcomes.py").read_text()
        self.assertNotIn('"channel": "handover"', src)
        self.assertNotIn('"channel": "page_handover", "state": "failed"', src)             # never relabelled as a page hand-over

    def test_the_one_choke_point(self):
        v0 = (ROOT / "backend/agapi/v0.py").read_text()
        self.assertEqual(v0.count("_OC.ended_without_act(name,"), 1)
        self.assertLess(v0.index("MS.tool(ctx, name, args, res"), v0.index("_OC.ended_without_act(name,"))


class TheWeek(unittest.TestCase):
    ROWS = [{"state": "confirmed", "rung": "request_reply", "created_at": ago(30)},
            {"state": "sent", "rung": "request_reply", "created_at": ago(30)},              # email-ish, past 24 h → no answer
            {"state": "sent", "rung": "request_reply", "created_at": ago(3)},               # still within its wait → open
            {"state": "sent", "rung": "phone", "created_at": ago(3)},                       # a call past 2 h → no answer
            {"state": "sent", "rung": "human_tap", "created_at": ago(90)},                  # a page handed over: his — never "no answer"
            {"state": "failed", "rung": "human_tap", "failure_reason": "handed to Tyler (booking)", "created_at": ago(5)},
            {"state": "declined", "rung": "request_reply", "created_at": ago(40)},
            {"state": "confirmed", "rung": "zero_touch", "created_at": ago(2), "test": True}]

    def test_classify(self):
        got = [OW.classify(r, NOW) for r in self.ROWS[:7]]
        self.assertEqual(got, ["confirmed", "no_answer", "open", "no_answer", "open", "handed_to_tyler", "declined"])

    def test_week_reads_the_one_ledger_and_the_couldnt_handle_list(self):
        calls = []

        async def call(op, body):
            calls.append(op)
            if op == "outcomes.report":   # AgAPI's schema: by ⊂ {rung, sector, city} — anything else is refused
                assert set(body["by"]) <= {"rung", "sector", "city"}, body["by"]
                return {"ok": True, "result": {"overall": {"attempts": 7, "confirmed": 1, "declined": 1, "failed": 1, "open": 4, "success_rate": 0.333},
                                               "by_rung": [{"rung": "request_reply", "attempts": 4, "confirmed": 1}], "by_sector": [{"sector": "restaurant", "attempts": 7}],
                                               "excluded_test": 1}}
            if op == "outcomes.list":
                return {"ok": True, "result": {"outcomes": self.ROWS}}
            return {"ok": True, "result": {"count": 2, "items": [{"kind_guess": "bus", "request": "a bus to Toledo"}, {"kind_guess": "unknown", "request": "hire a yacht crew"}]}}
        rows = [{"kind": "booking", "data": {"real": True, "stop": {"why": "handed_to_tyler"}}},
                {"kind": "booking", "data": {"real": False, "stop": {"why": "handed_to_tyler"}}},   # a test person: left out
                {"kind": "booking", "data": {"real": True, "stop": None}}]
        with mock.patch.object(OW, "CALL", call), mock.patch("agapi.measure.read_rows", mock.AsyncMock(return_value=rows)):
            w = asyncio.run(OW.week(7, now=NOW))
        self.assertEqual(calls, ["outcomes.report", "outcomes.list", "venue.unhandled"])     # read-only: nothing written
        self.assertIn("request_reply: 1/4", w["say"])
        self.assertEqual((w["count"], w["no_answer"], w["handed_to_tyler"], w["unhandled"]["count"]), (7, 2, 1, 2))
        self.assertEqual(w["unhandled"]["by_kind"], {"bus": 1, "unknown": 1})
        self.assertIn("7 real booking(s)", w["say"])
        self.assertIn("2 no answer yet", w["say"])
        self.assertEqual(w["handed_to_tyler_unrecorded"], 1)
        self.assertIn("Handed to Tyler (not yet recorded in AgAPI): 1.", w["say"])

    def test_where_it_is_read(self):
        self.assertIn('@router.get("/outcomes/week")', (ROOT / "backend/booking_signer/routes.py").read_text())
        self.assertIn('"booking_outcomes"', (ROOT / "backend/app/agent/s2.py").read_text())
        self.assertIn('log.warning("[outcomes] week: %s"', (ROOT / "backend/agapi/measure.py").read_text())


class NoAnswerYetOnce(unittest.TestCase):
    def test_past_its_channels_wait(self):
        t = time.time()
        self.assertTrue(VS.no_answer_yet({"channel": "email", "at": t - 25 * 3600}, t))
        self.assertFalse(VS.no_answer_yet({"channel": "email", "at": t - 3 * 3600}, t))
        self.assertTrue(VS.no_answer_yet({"route": "call", "at": t - 3 * 3600}, t))
        self.assertFalse(VS.no_answer_yet({"channel": "page_handover", "at": t - 300 * 3600}, t))

    def test_said_once_then_remembered(self):
        acct = "acct-324"
        VS._ACTS[acct] = [{"act_id": "act_1", "venue": "Casa Lucio", "when": "2026-11-20T21:00", "party": 2, "state": "sent",
                           "channel": "email", "at": time.time() - 30 * 3600, "words": None, "answered": False}]
        said = []

        async def wa(account, text):
            said.append(text)
            return "sent"
        with mock.patch.object(VS, "status", mock.AsyncMock(return_value=None)), mock.patch("booking_signer.live_events.WA_SEND", wa), \
                mock.patch("booking_signer.live_events.publish", lambda a, e: e), mock.patch("agapi.s2_memory.put_kind", mock.AsyncMock()):
            rows = asyncio.run(VS.bookings(acct))
            asyncio.run(VS.bookings(acct))
        self.assertEqual((rows[0]["status_words"], rows[0]["no_answer_yet"]), ("No answer yet", True))
        self.assertEqual(len(said), 1)                                                       # once, never on the next read
        self.assertTrue(VS._ACTS[acct][0].get("no_answer_told"))


if __name__ == "__main__":
    unittest.main()
