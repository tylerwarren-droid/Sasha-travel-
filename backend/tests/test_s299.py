"""Sasha 299 · T77 — THE 11–15 SECONDS: SASHA'S SHARE, AND NEVER A SILENT WAIT (Tyler's real bookings: tap → her answer 11–15 s, one
holding line, "On it", then nothing).

ROOT TEST (written before the code): (1) ONE place a turn's time is spent (sasha.turn: model steps · v0.call tools · agapi_route.post
AgAPI calls), measured in ONE place (agapi/measure.py's turn timeline, observation only); ONE place holding lines are decided
(sasha.with_holding, the rule voice.progress_next). (2) A line for a step that isn't running, a timer saying "still working" whatever
happens, or per-route waits = PATCH. (3) While a step runs, a NEW, TRUE line about it — never silence past STEP_GAP_S + the step's
own still line — never a line twice.
    cd backend && python -m unittest tests.test_s299 -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from agapi import venues as VN
from app.agent import sasha as S, voice as V

ACCT = "00000000-0000-4000-8000-000000002990"
run = asyncio.run


async def collect(gen):
    return [e async for e in gen]


class TheRule(unittest.TestCase):
    def test_only_a_step_that_is_running(self):
        self.assertIsNone(V.progress_next(10, 0, None, {}))                      # nothing running: no step line (279's rule holds)
        self.assertIsNone(V.progress_next(10, 0, "an_unknown_tool", {}))
        self.assertIsNone(V.progress_next(V.STEP_GAP_S - 0.5, 0, "read_booking_route", {}))   # her last words were too recent
        self.assertEqual(V.progress_next(V.STEP_GAP_S, 0, "read_booking_route", {}, "DiverXO"),
                         ("Checking how DiverXO takes bookings.", "route"))
        self.assertEqual(V.progress_next(5, 0, "hold_venue", {"route": 1}, "DiverXO"), ("Getting your booking ready with DiverXO.", "booking"))
        said = {"route": 4.0}
        self.assertIsNone(V.progress_next(10, 4.0, "read_booking_route", said))     # its still line only STEP_STILL_S after its line
        self.assertEqual(V.progress_next(12.0, 4.0, "read_booking_route", said, "DiverXO")[1], "route:still")
        self.assertIsNone(V.progress_next(30, 13, "read_booking_route", {"route": 4, "route:still": 12}))   # then nothing new: quiet
        self.assertEqual(V.progress_wait(0, 0, None, {}), float("inf"))

    def test_the_words_claim_nothing(self):
        for t in ("read_booking_route", "hold_venue", "book_venue", "search_venues"):
            for still in (False, True):
                w = V.step_words(t, "DiverXO", still) or ""
                self.assertNotRegex(w, r"(?i)\b(booked|sent|found|confirmed|done|available)\b", w)
        self.assertEqual(V.step_words("read_booking_route"), "Checking how they take bookings.")   # no venue known: no name invented
        self.assertEqual(V.step_words("hold_venue"), "Getting your booking ready.")


class TheStream(unittest.TestCase):
    def turn(self, plan):
        async def gen():
            for kind, x in plan:
                if kind == "sleep":
                    await asyncio.sleep(x)
                else:
                    yield x
        return gen()

    def test_a_booking_turn_hears_each_step_once_in_its_own_words(self):
        plan = [("ev", {"type": "tool_start", "name": "read_booking_route"}), ("sleep", 0.35),
                ("ev", {"type": "tool", "name": "read_booking_route", "ok": True}),
                ("ev", {"type": "tool_start", "name": "hold_venue"}), ("sleep", 0.35),
                ("ev", {"type": "tool", "name": "hold_venue", "ok": True}), ("sleep", 0.3),
                ("ev", {"type": "text", "delta": "Their page is on your screen."}), ("ev", {"type": "done", "text": "x"})]
        with mock.patch.object(V, "STEP_GAP_S", 0.12), mock.patch.object(V, "STEP_STILL_S", 0.9), mock.patch.object(V, "LONG_WAIT_S", 5.0):
            evs = run(collect(S.with_holding(self.turn(plan), ACCT, after_s=0.05, venue="DiverXO")))
        holds = [e["text"] for e in evs if e["type"] == "hold"]
        self.assertEqual(holds, ["Checking how DiverXO takes bookings.", "Getting your booking ready with DiverXO."], holds)
        self.assertEqual([e["type"] for e in evs][-2:], ["text", "done"])

    def test_no_line_once_her_words_have_begun_and_none_twice(self):
        plan = [("ev", {"type": "tool_start", "name": "search_flights"}), ("sleep", 0.6), ("ev", {"type": "tool", "name": "search_flights", "ok": True}),
                ("ev", {"type": "text", "delta": "Here they are."}), ("sleep", 0.5), ("ev", {"type": "done", "text": "x"})]
        with mock.patch.object(V, "STEP_GAP_S", 0.1), mock.patch.object(V, "STEP_STILL_S", 0.2), mock.patch.object(V, "LONG_WAIT_S", 0.25):
            evs = run(collect(S.with_holding(self.turn(plan), ACCT, after_s=0.05)))
        types = [e["type"] for e in evs]
        holds = [e["text"] for e in evs if e["type"] == "hold"]
        self.assertEqual(len(set(holds)), len(holds), holds)
        self.assertNotIn("hold", types[types.index("text"):])   # after her words begin: no progress line


    def test_a_steps_own_line_never_follows_a_generic_one_about_it(self):
        """Found live (cad2fa6, La Mi Venta): 279's generic second line ("Setting up the booking.") came 4 s before the step's own."""
        plan = [("ev", {"type": "tool_start", "name": "hold_venue"}), ("sleep", 0.5), ("ev", {"type": "tool", "name": "hold_venue", "ok": True}),
                ("ev", {"type": "text", "delta": "Done."}), ("ev", {"type": "done", "text": "x"})]
        with mock.patch.object(V, "STEP_GAP_S", 0.3), mock.patch.object(V, "STEP_STILL_S", 5), mock.patch.object(V, "LONG_WAIT_S", 0.1):
            evs = run(collect(S.with_holding(self.turn(plan), ACCT, after_s=0.02, venue="Casa")))
        holds = [e["text"] for e in evs if e["type"] == "hold"]
        self.assertEqual(holds, ["Getting your booking ready with Casa."], holds)


class TheCuts(unittest.TestCase):
    def test_a_taps_reads_start_at_the_tap_and_are_used_once(self):
        calls = []

        class GW:
            @staticmethod
            async def api(account, method, path, body, timeout=None):
                calls.append(path)
                await asyncio.sleep(0.01)
                return 200, {"read_id": "r1", "venue": "Casa (test)", "rungs": [], "facts": []}

            @staticmethod
            def _hours_of(rd, now):
                return {}

        async def go():
            with mock.patch.object(VN, "_API", lambda: GW), mock.patch.object(VN, "card_of", lambda *a: {"name": "Casa (test)", "place_id": "PZ", "address": "Calle Falsa 1, 28012 Madrid, Spain"}), \
                    mock.patch("agapi.venue_truth.profile", mock.AsyncMock(return_value={})):
                VN._READS.pop(ACCT, None)
                self.assertTrue(VN.read_ahead(ACCT, "PZ"))
                self.assertFalse(VN.read_ahead(ACCT, "PZ"))           # once per tap: never a second read started
                ctx = type("C", (), {"account": ACCT, "surface": "s2"})()
                rd = await VN._read(ctx, {"name": "Casa (test)", "place_id": "PZ", "city": "Madrid"})
                return rd
        rd = run(go())
        self.assertEqual(rd["read_id"], "r1")
        self.assertEqual(calls, ["/api/booking/venues/read"])          # the read started at the tap IS the route's read

    def test_an_early_read_that_fails_is_read_again_never_passed_on(self):
        """Found live (cad2fa6): the read started at the tap had no city, the venue read refused it (city_invalid), and that refusal
        became read_booking_route's answer. Now the card's own address gives the city, and any early failure is simply read again."""
        answers = [(400, {"rule": "city_invalid"}), (200, {"read_id": "r2", "venue": "Casa (test)", "rungs": [], "facts": []})]
        calls = []

        class GW:
            @staticmethod
            async def api(account, method, path, body, timeout=None):
                calls.append(body.get("city"))
                return answers[len(calls) - 1]

            @staticmethod
            def _hours_of(rd, now):
                return {}

            @staticmethod
            def refusal_words(rd, status):
                return "refused"

        async def go():
            with mock.patch.object(VN, "_API", lambda: GW), mock.patch.object(VN, "card_of", lambda *a: {"name": "Casa (test)", "place_id": "PQ", "address": "C. Uno 2, 28005 Madrid, España"}), \
                    mock.patch("agapi.venue_truth.profile", mock.AsyncMock(return_value={})):
                VN._READS.pop(ACCT, None)
                VN._AHEAD.pop((ACCT, "PQ"), None)
                VN.read_ahead(ACCT, "PQ")
                ctx = type("C", (), {"account": ACCT, "surface": "s2"})()
                return await VN._read(ctx, {"name": "Casa (test)", "place_id": "PQ", "city": "Madrid"})
        self.assertEqual(run(go())["read_id"], "r2")
        self.assertEqual(calls, ["Madrid", "Madrid"])   # the early read had the card's city; its failure → the route's own read
        self.assertIsNone(VN.city_of("Madrid"))         # no address to read a city from: no early read at all

    def test_the_platform_cards_line_is_said_by_code(self):
        r = {"ok": True, "result": {"status": "page_link", "in_app": True, "page_url": "https://x.example/p",
                                    "prepared": {"filled": True, "url": "https://x.example/p"}, "page_says": "AgAPI's own line (test)."}}
        self.assertEqual(V.page_line("hold_venue", r), "AgAPI's own line (test).")   # the turn ends on it — no model step to say it
        r["result"]["prepared"]["filled"] = False
        self.assertEqual(V.page_line("hold_venue", r), V.NOT_FILLED)


if __name__ == "__main__":
    unittest.main()
