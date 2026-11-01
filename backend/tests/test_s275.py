"""Sasha 275 · S1 MEASURE — observation only (agapi/measure.py). The store is a DERIVED copy: ids, timings and enums, never content.
    · the turn stream is yielded byte for byte; one row per turn (failed ones too), with its tokens, tools and timings
    · every booking: how far she got (venue → channel → filled → submitted → confirmed) and why she stopped; the yes → action → outcome;
      submission and confirmation as two things; duplicates and actions after a cancel counted (both must be 0)
    · nothing personal: no name, phone, email or words in any row; person/session/act ids hashed
    · never an authority: no code that decides her behaviour reads the store
Offline: the writer is replaced; no database, no model, no AgAPI.
    cd backend && python -m unittest tests.test_s275 -v
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import re
import types
import unittest

from agapi import measure as MS

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000002750"
PHONE, EMAIL, NAME, WORDS = "+34 600 111 222", "someone@example.test", "Alex Gate", "a table for four at 21:00 under Alex Gate"


class _Rows:
    def __init__(self):
        self.rows = {}

    async def __call__(self, row):
        self.rows[row["id"]] = row


def _ctx(surface="s2"):
    return types.SimpleNamespace(account=ACCT, surface=surface, session="sess-275")


class Base(unittest.TestCase):
    def setUp(self):
        self.w = _Rows()
        MS.WRITE = self.w
        MS._BOOKINGS.clear(); MS._OF.clear(); MS._LAST.clear(); MS._Q = None; MS._WRITER = None

    def tearDown(self):
        MS.WRITE = None
        MS._Q = None; MS._WRITER = None

    def run_(self, coro):
        return asyncio.run(coro)


class Turns(Base):
    def test_stream_is_byte_identical_and_one_row_per_turn(self):
        chunks = ['data: {"type": "timing", "pre": {}}\n\n', 'data: {"type": "hold", "text": "On it"}\n\n',
                  'data: {"type": "text", "delta": "' + WORDS + '"}\n\n', 'data: {"type": "done", "text": "' + WORDS + '"}\n\n']

        async def stream():
            for c in chunks:
                MS.usage("claude-sonnet-5-5", types.SimpleNamespace(input_tokens=100, output_tokens=20, cache_creation_input_tokens=0, cache_read_input_tokens=50))
                yield c

        async def go():
            out = [c async for c in MS.observe(stream(), ACCT, "sess-275", "s2", "voice")]
            await MS.flush()
            return out
        self.assertEqual(self.run_(go()), chunks)                       # exactly what the turn yielded
        rows = [r for r in self.w.rows.values() if r["kind"] == "turn"]
        self.assertEqual(len(rows), 1)
        d = rows[0]["data"]
        self.assertEqual((d["surface"], d["channel"]), ("s2", "voice"))
        self.assertIsNotNone(d["first_visible_ms"]); self.assertIsNotNone(d["done_ms"]); self.assertIsNone(d["error"])
        self.assertEqual(d["usage"]["claude-sonnet-5-5"]["calls"], 4)
        self.assertEqual(d["account"], MS.h(ACCT)); self.assertNotIn(ACCT, json.dumps(rows[0], default=str))
        self.assertEqual(rows[0]["mv"], MS.MEASURE_VERSION)

    def test_a_failed_turn_is_measured_too(self):
        async def stream():
            yield 'data: {"type": "error", "message": "x"}\n\n'

        async def go():
            [c async for c in MS.observe(stream(), ACCT, None, "s1")]
            await MS.flush()
        self.run_(go())
        d = next(r["data"] for r in self.w.rows.values() if r["kind"] == "turn")
        self.assertEqual(d["error"], "error")

    def test_the_pages_clock(self):
        async def go():
            MS.client("abc123", {"channel": "voice", "surface": "s2", "first_audible_ms": 1180, "first_visible_ms": 600, "done_ms": 4100,
                                 "text": WORDS}, ACCT)
            await MS.flush()
        self.run_(go())
        d = self.w.rows["c:abc123"]["data"]
        self.assertEqual((d["first_audible_ms"], d["channel"]), (1180, "voice"))
        self.assertNotIn(WORDS, json.dumps(d))                          # only numbers and ids are kept


class Bookings(Base):
    def _tool(self, name, args, ok, result=None, code=None, ms=40):
        res = {"ok": ok, **({"result": result} if ok else {"error": {"code": code, "message": WORDS}})}
        MS.tool(_ctx(), name, args, res, ms)

    def _env(self, op, body, result):
        MS.agapi_op(op, body, {"ok": True, "result": result}, 120, "https://agapi-sandbox.example.test")

    def _row(self):
        return next(r["data"] for r in self.w.rows.values() if r["kind"] == "booking")

    def test_a_booking_that_confirms(self):
        async def go():
            MS.turn_start(ACCT, "sess", "s2")
            a = {"place_id": "fixture_place_taverna_phone", "name": "Casa Gate", "guest": NAME, "phone": PHONE, "email": EMAIL}
            self._tool("read_booking_route", a, True, {"venue": "Casa Gate", "routes": ["call"], "card": {"place_id": a["place_id"], "google_type": "restaurant"}})
            self._tool("hold_venue", a, True, {"status": "awaiting_yes", "venue": "Casa Gate", "read_back": [WORDS]})
            self._tool("book_venue", {"approval": {"said": "yes"}}, True, {"status": "calling", "act_id": "act-1"})   # a yes carries no place
            self._env("venue.submit_booking", {"act_id": "act-1"}, {"act_id": "act-1"})
            self._env("venue.booking_status", {"act_id": "act-1"}, {"state": "confirmed"})
            await MS.flush()
        self.run_(go())
        d = self._row()
        self.assertEqual(d["furthest"], "confirmed")
        self.assertTrue(d["submitted"]); self.assertTrue(d["confirmed"]); self.assertEqual(d["outcome"], "confirmed")
        self.assertEqual((d["duplicates"], d["after_cancel"], d["venue_type"]), (0, 0, "restaurant"))
        self.assertIsNotNone(d["yes_to_action_ms"]); self.assertIsNotNone(d["yes_to_outcome_s"])
        blob = json.dumps(self.w.rows, default=str)
        for secret in (PHONE, EMAIL, NAME, WORDS, "act-1", ACCT):      # nothing personal, no words, raw ids never
            self.assertNotIn(secret, blob, secret)

    def test_a_hand_over_says_how_far_and_why(self):
        async def go():
            a = {"place_id": "fixture_place_platform"}
            self._tool("read_booking_route", a, True, {"routes": ["page"]})
            self._tool("hold_venue", a, True, {"status": "page_link", "rules": {"say_key": "platform"}})
            await MS.flush()
        self.run_(go())
        d = self._row()
        self.assertEqual(d["furthest"], "channel")
        self.assertEqual(d["stop"]["why"], "platform_handover")
        self.assertFalse(d["submitted"])

    def test_cancel_duplicates_and_actions_after_it_are_counted(self):
        async def go():
            a = {"place_id": "fixture_place_hotel"}
            self._tool("hold_venue", a, True, {"status": "awaiting_yes"})
            self._tool("book_venue", {"approval": {"said": "yes"}}, True, {"status": "sent", "act_id": "act-2"})
            self._env("venue.submit_booking", {"act_id": "act-2"}, {"act_id": "act-2"})
            self._env("venue.submit_booking", {"act_id": "act-2"}, {"act_id": "act-2"})     # a second submit: a duplicate
            self._tool("cancel_venue", a, True, {"status": "cancelled"})
            self._env("venue.call_again", {"act_id": "act-2"}, {"act_id": "act-2"})          # an action after the cancel
            await MS.flush()
        self.run_(go())
        d = self._row()
        self.assertEqual(d["duplicates"], 1)
        self.assertEqual(d["after_cancel"], 1)
        self.assertEqual(d["outcome"], "cancelled")

    def test_a_later_cancel_lands_on_its_own_booking(self):
        # 275b · found by the production gate: a cancel in a later turn named its booking by the act; it made a new row instead
        async def go():
            self._tool("hold_venue", {"place_id": "fixture_place_taverna_phone"}, True, {"status": "awaiting_yes"})
            self._tool("book_venue", {}, True, {"status": "calling", "act_id": "act-9"})
            self._env("venue.booking_status", {"act_id": "act-9"}, {"state": "confirmed"})
            self._tool("cancel_venue", {"act_id": "act-9", "venue": "Taverna Sandbox"}, True, {"status": "awaiting_yes"})
            self._env("venue.cancel_booking", {"act_id": "act-9"}, {"status": "sent"})
            await MS.flush()
        self.run_(go())
        books = [r["data"] for r in self.w.rows.values() if r["kind"] == "booking"]
        self.assertEqual(len(books), 1)                                   # ONE request, one row
        self.assertEqual(books[0]["outcome"], "cancelled")
        self.assertEqual(books[0]["furthest"], "confirmed")

    def test_guest_and_policy_stops(self):
        async def go():
            self._tool("hold_venue", {"place_id": "p-guest"}, True, {"status": "draft_message"})
            self._tool("hold_venue", {"place_id": "p-test"}, True, {"status": "refused", "rules": {"say_key": "not_live"}})
            self._tool("read_booking_route", {"place_id": "p-none"}, True, {"routes": []})
            await MS.flush()
        self.run_(go())
        why = sorted((r["data"].get("stop") or {}).get("why") for r in self.w.rows.values() if r["kind"] == "booking")
        self.assertEqual(why, ["guest_session", "no_channel", "policy_not_permitted"])

    def test_rehydrated_after_a_restart(self):
        async def go():
            a = {"place_id": "p-r"}
            self._tool("book_venue", a, True, {"status": "sent", "act_id": "act-3"})
            await MS.flush()
        self.run_(go())
        kept = self._row()["_src"]
        self.assertIn(MS.h("act-3"), kept["acts"])
        MS._BOOKINGS.clear(); MS._OF.clear()                              # the process restarted
        MS._BOOKINGS[kept["cid"]] = {**kept, "closed": False}            # what _rehydrate loads from the row
        MS._OF["act:" + MS.h("act-3")] = kept["cid"]

        async def go2():
            self._env("venue.booking_status", {"act_id": "act-3"}, {"state": "declined"})
            await MS.flush()
        self.run_(go2())
        self.assertEqual(self._row()["outcome"], "refused")


class Summary(Base):
    def test_week_table_and_daily_line(self):
        rows = [{"kind": "turn", "data": {"first_visible_ms": v, "done_ms": v * 4, "tools": [], "usage": {"m": {"in": 10, "out": 2, "cw": 0, "cr": 0, "calls": 1}}}} for v in range(100, 1100, 10)]
        rows += [{"kind": "booking", "data": {"submitted": True, "confirmed": i % 2 == 0, "outcome": "confirmed" if i % 2 == 0 else "refused",
                                               "furthest": "confirmed" if i % 2 == 0 else "submitted", "venue_type": "restaurant",
                                               "stop": None if i % 2 == 0 else {"why": "venue_declined"}, "duplicates": 0, "after_cancel": 0,
                                               "cost": {"call_minutes": 1.5}}} for i in range(10)]
        s = MS.summarise(rows)
        self.assertEqual(s["rates"], {"submission_success": 1.0, "venue_confirmation": 0.5})
        self.assertEqual(s["responsiveness"]["routine_done_ms"]["n"], 100)
        self.assertTrue(s["responsiveness"]["routine_done_ms"]["p50"] <= s["responsiveness"]["routine_done_ms"]["p95"] <= s["responsiveness"]["routine_done_ms"]["p99"])
        self.assertEqual(s["stop_reasons"], {"venue_declined": 5})
        line = MS.summary_line("2026-10-16", s)
        self.assertLessEqual(len(line), 2000)
        self.assertIn("Submission success 1.0, venue confirmation 0.5", line)


class NeverAnAuthority(unittest.TestCase):
    def test_no_behaviour_code_reads_the_store(self):
        readers = re.compile(r"\b(?:MS|_MS|measure)\.(?:read_week|read_rows|summarise|call_minutes)\b|from agapi\.measure import .*read_")
        allowed = {BACKEND / "agapi" / "measure.py", BACKEND / "app" / "agent" / "sasha.py", BACKEND / "tests" / "test_s275.py"}
        hits = [str(p.relative_to(BACKEND)) for p in BACKEND.rglob("*.py") if p not in allowed and "node_modules" not in str(p)
                and readers.search(p.read_text(encoding="utf-8", errors="ignore"))]
        self.assertEqual(hits, [])
        src = (BACKEND / "app" / "agent" / "sasha.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("_MS.read_week("), 1)                  # the founder route only
        self.assertIn('if not GA.founder(await chat_account(request)):\n        return JSONResponse({"ok": False, "rule": "founder_only"}', src)

    def test_hooks_are_observation_only(self):
        v0 = (BACKEND / "agapi" / "v0.py").read_text(encoding="utf-8")
        self.assertIn('MS.tool(ctx, name, args, res, ctx.calls[-1]["ms"])', v0)
        ar = (BACKEND / "agapi" / "agapi_route.py").read_text(encoding="utf-8")
        self.assertIn("MS.agapi_op(op, body, env, int((time.perf_counter() - t0) * 1000), url, version)\n    return env", ar)
        s = (BACKEND / "app" / "agent" / "sasha.py").read_text(encoding="utf-8")
        self.assertEqual(s.count("StreamingResponse(_MS.observe("), 2)
        self.assertIn("**({'tid': (_MS.current() or {}).get('tid')} if remembers else {})", s)   # old S1's timing event: as before

    def test_no_path_into_another_project(self):
        # the chat (16 Oct 16:37): the daily summary lives in sasha-prod and on the founder page — nothing in AD's project
        src = (BACKEND / "agapi" / "measure.py").read_text(encoding="utf-8")
        for x in ("AD_MAILBOX", "SASHA_MAILBOX", "sasha_mailbox_post", "tab_messages", "/rest/v1/rpc"):
            self.assertNotIn(x, src, x)
        self.assertFalse((BACKEND.parent / "docs" / "sasha" / "sql" / "s275-ad-mailbox-post.sql").exists())

    def test_in_the_gate(self):
        self.assertIn('["tests.test_s275"]', (BACKEND / "scripts" / "one_truth_suite.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
