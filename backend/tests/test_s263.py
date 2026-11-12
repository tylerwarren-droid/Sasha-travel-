"""Sasha 263 · T45 — "YES, SEND IT" SENDS EXACTLY THE CARD ON SCREEN (S2 item 10, row 914). EU 258's run: item 7 took Sasha Test Venue
at 20:15; item 10 asked for 21:15 → "Yes, send it." → "✅ Booked: … at 20:15". A second memory of "which booking the question was
about" fed the old one to the read-back. It is gone: every hold reads back the booking she was given, by the one path (hold_venue →
AgAPI's card); the in-app yes sends ONLY the latest unanswered card (_HELD: AgAPI's read_back_id + sha, by in_app_tap); no card →
"There's nothing waiting to send." and nothing is sent. Sasha 378 · CR 188: the route is AgAPI's decision (send_form here) — the ONE
question of Sasha's own ("Prefilled form / Handle it") is gone with her decider. Offline.

    cd backend && python -m unittest tests.test_s263 -v
"""
from __future__ import annotations

import asyncio
import inspect
import re
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import venue_submit as VS, venues as VN
from app.agent import voice as V

ACCT = "00000000-0000-4000-8000-000000000263"
VENUE = "Sasha Test Venue"


class GW:   # the summary / lines / name helpers _hold and _execute use, offline
    @staticmethod
    def summary(res):
        return res["when"]["at"].replace("T", " at ")

    @staticmethod
    def guest_lines(rung, lines):
        return list(lines)

    @staticmethod
    def plain_venue(v):
        return v


class Ctx:
    surface, session, mode = "s2", "s", "test"

    def __init__(self, said, at):
        self.account, self.user_said, self.started = ACCT, said, at
        self.idem = self.act_name = self.claimed = None
        self.turn, self.said_before = "turn_" + __import__("uuid").uuid4().hex, ""   # Sasha 381 · the instruction's own id


def booking(t):
    return {"name": VENUE, "city": "Madrid", "day": "2026-10-22", "time": t, "party": 2}


class World:
    """The one path, offline: AgAPI's decision (send_form) → AgAPI's read-back card (prepare_booking → submit_booking without an
    approval). submit records what the yes sent."""
    DEC = {"route": "send_form", "channel": "their own booking form", "how_far": "zero_touch", "say_text": "I can send it — just say yes.",
           "button": {"label": "Send my request", "link": "https://sashatest.example/", "sends": True}}

    def __init__(self):
        self.sent = []

    async def via_agapi(self, ctx, a, rd, res, at, now, d, card, **kw):   # Sasha 381 · AgAPI's prepared booking, acted on the instruction
        return await VN._act(ctx, "agapi", {"prepared_id": "prep-" + at, "venue": VENUE},
                             {"read_back_id": "rb-" + at, "sha256": "sha-" + at, "lines": [f"· {at}"], "end_user": "u"}, rd, res)

    async def submit(self, account, held, said, instruction=None):   # Sasha 381 · + the instruction (the approval)
        self.sent.append({"when": held["when"], "read_back_id": held["read_back_id"], "sha": held["sha"]})
        return {"ok": True, "status": "confirmed", "reference": "TV-263"}

    async def read(self, ctx, a):
        return {"venue": VENUE, "place_id": "p-tv", "read_id": "r-tv", "rungs": {"form": {}}}

    async def reservation(self, ctx, a, rd):
        return {"when": {"at": f"{a['day']}T{a['time']}"}, "how_many": {"count": a["party"]}, "who": {"name": "Test Person", "contact": {}},
                "what": {"category": "restaurant"}}

    def patches(self):
        from agapi import test_venues as TV, s2_outcomes as OC
        from booking_signer import wa_brain as WB
        import agapi.v0 as V0
        return [mock.patch.object(TV, "vet", mock.AsyncMock(side_effect=lambda ctx, a: a)),
                mock.patch.object(VN, "_API", lambda: GW), mock.patch.object(VN, "_read", self.read),
                mock.patch.object(VN, "_reservation", self.reservation), mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=None)),
                mock.patch("agapi.venue_truth.decision", lambda p: dict(self.DEC)), mock.patch.object(VN, "card_of", lambda *a, **k: None),
                mock.patch.object(VN, "_said", lambda out, d, **k: out), mock.patch.object(VN, "_via_agapi", self.via_agapi),
                mock.patch.object(VS, "submit", self.submit), mock.patch.object(V0, "claim", mock.AsyncMock()),
                mock.patch.object(OC, "booked", mock.AsyncMock()), mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value=None)),
                mock.patch.dict(VN._HELD, {}, clear=True), mock.patch.dict(VN._PREV, {}, clear=True), mock.patch.dict(VN._SENT, {}, clear=True)]


def play(turns, in_app=True):
    """Each turn: (what they said, tool, args). Turns are a minute apart (a yes always answers a card from an EARLIER turn)."""
    w, out = World(), []
    t0 = datetime.now(timezone.utc) + timedelta(minutes=1)   # each turn starts after every hold made before it

    async def go():
        tok = VS.TAP.set("their-session") if in_app else None
        try:
            for i, (said, tool, args) in enumerate(turns):
                ctx = Ctx(said, t0 + timedelta(minutes=i))
                try:
                    out.append(await getattr(VN, tool)(ctx, {**args, **({"approval": {"said": said}} if tool == "book_venue" else {})}))
                except Exception as e:
                    out.append({"error": getattr(e, "code", type(e).__name__)})
        finally:
            if tok is not None:
                VS.TAP.reset(tok)
    with ExitStack() as st:
        for p in w.patches():
            st.enter_context(p)
        asyncio.run(go())
    return w, out


ITEM_7 = [("Book Sasha Test Venue Thursday 22 October at 20:15 for 2", "hold_venue", booking("20:15"))]


class EachInstructionBooksItsOwnSlot(unittest.TestCase):
    def test_gate_item_7_then_a_new_booking(self):
        """THE GATE (row 914), Sasha 381: no card — each instruction books the slot IT gave (21:15 is 21:15, never item 7's 20:15)."""
        w, out = play(ITEM_7 + [("Thursday 22 October at 21:15 for 2 too", "hold_venue", booking("21:15"))])
        self.assertEqual([x["when"] for x in w.sent], ["2026-10-22T20:15", "2026-10-22T21:15"])
        self.assertEqual(out[1]["status"], "confirmed")
        self.assertIn("at 21:15", out[1]["line"])

    def test_no_card_waiting_nothing_is_sent(self):
        w, out = play([("Yes, send it.", "book_venue", {})])
        self.assertEqual((w.sent, out[0]["status"]), ([], "nothing_waiting"))

    def test_whatsapp_has_no_card_and_is_as_it_was(self):
        w, out = play([("Yes, send it.", "book_venue", {})], in_app=False)
        self.assertEqual((w.sent, out[0]), ([], {"error": "nothing_held"}))


class NoQuestionOfHerOwn(unittest.TestCase):
    """Sasha 378 · CR 188: 262's "Handle it" capability went with the ONE question — AgAPI decides one way; only a yes sends."""

    def test_handle_it_is_not_a_yes(self):
        w, out = play(ITEM_7 + [("Handle it", "book_venue", booking("21:15"))])
        self.assertEqual(out[1], {"error": "no_explicit_yes"})
        self.assertEqual(len(w.sent), 1)                                               # item 7's own instruction only (Sasha 381)

    def test_other_words_are_still_no_yes(self):
        w, out = play(ITEM_7 + [("hmm, maybe", "book_venue", booking("21:15"))])
        self.assertEqual(out[1], {"error": "no_explicit_yes"})

    def test_no_second_memory(self):
        self.assertFalse(hasattr(VN, "_ASKED_ROUTE"))
        src = inspect.getsource(VN)
        self.assertNotIn("_ASKED_ROUTE[", src)
        self.assertNotIn("_ASKED_ROUTE.get(", src)

    def test_the_schema_names_the_booking_on_the_one_path_only(self):
        from agapi import v0 as API
        bv, hv = API.BY_NAME["book_venue"], VN.with_under(API.BY_NAME["hold_venue"])
        got = VN.with_booking(bv, hv)["input_schema"]
        self.assertTrue({"name", "day", "time", "party", "approval"} <= set(got["properties"]))
        self.assertNotIn("route", got["properties"])
        self.assertEqual(got["required"], bv["input_schema"]["required"])   # nothing more required: a yes passes only the approval
        self.assertNotIn("day", bv["input_schema"]["properties"])   # old S1's own schema, untouched
        from app.agent import sasha as S
        self.assertIn('_VN.with_booking(t, hv) if t["name"] == "book_venue" and hv else t', inspect.getsource(S.turn))


class TheConfirmationIsTwoSentencesSaidByCode(unittest.TestCase):
    def test_booked_and_the_one_question(self):
        w, out = play([("Book Sasha Test Venue Thursday 22 October at 21:15 for 2", "hold_venue", booking("21:15"))])
        line = V.yes_line("hold_venue", {"ok": True, "result": {**out[0], "in_app": True}})
        # Sasha 381 · Tyler's ONE line, then (Sasha 279 · C) the closing line and the one question
        self.assertTrue(line.startswith("Booking now: Sasha Test Venue, 2 people, Thu 22 Oct at 21:15. Booked — reference TV-263. "), line)
        self.assertTrue(line.endswith(" Shall I put it in your calendar?"), line)   # (279's closing between them when it's its first time)

    def test_not_in_the_app_she_says_it_as_before(self):
        self.assertEqual(V.yes_line("book_venue", {"ok": True, "result": {"status": "confirmed", "line": "✅ Booked: X."}}), "")
        self.assertEqual(V.yes_line("hold_venue", {"ok": True, "result": {"status": "nothing_waiting", "in_app": True}}), "")

    def test_the_turn_says_it_and_ends_on_it(self):
        from app.agent import sasha as S
        src = inspect.getsource(S.turn)
        self.assertIn('rb = (_V.read_back_line(u.name, r) or _V.yes_line(u.name, r) or _V.page_line(u.name, r)\n                  or _V.discover_line(u.name, r) or _V.fine_print_line(u.name, r) or _V.flight_line(u.name, r)) if honest else ""', src)   # 264: + a page; 276: + discover's say_text; 302: + the fine print; 305 MOVED: + a flight's change / cancel
        self.assertIn("if agapi_out or read_back_said:", src)


if __name__ == "__main__":
    unittest.main()
