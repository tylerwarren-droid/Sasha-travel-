"""Sasha 263 · T45 — "YES, SEND IT" SENDS EXACTLY THE CARD ON SCREEN (S2 item 10, row 914). EU 258's run: item 7 took Sasha Test Venue
at 20:15 by "Prefilled form"; item 10 asked for 21:15 → "Handle it" → "Yes, send it." → "✅ Booked: … at 20:15". 262's second memory
of "which booking the one question was about" (venues._ASKED_ROUTE) still held item 7's 20:15 and fed it to the read-back. It is gone:
"Handle it" reads back the booking she was given, by the one path (hold_venue → the card); the in-app yes sends ONLY the latest
unanswered card (_HELD: AgAPI's read_back_id + sha, by in_app_tap); no card → "There's nothing waiting to send." and nothing is sent.
Offline.

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


def booking(t):
    return {"name": VENUE, "city": "Madrid", "day": "2026-10-22", "time": t, "party": 2}


class World:
    """The one path, offline: the booking rules ask the ONE question with no route, "page" → their prefilled page (nothing held),
    "form" → AgAPI's read-back card (prepare_booking → submit_booking without an approval). submit records what the yes sent."""

    def __init__(self):
        self.sent = []

    async def rules_for(self, ctx, a, rd, res, at, eng, card, route, now=None):
        act = {None: "ask_one_question", "page": "prepared_link", "form": "fill_form_zero_touch"}[route]
        return {"action": act, "say": act, "say_text": "Prefilled form, or shall I handle it?", "takeover": {"say": ""}, "channels": []}

    async def via_agapi(self, ctx, a, rd, res, at, now, d, card):
        return VN._hold(ctx, "agapi", "prep-" + at, {"lines": [f"· {at}"], "sha256": "sha-" + at}, rd, res,
                        extra={"prepared_id": "prep-" + at, "read_back_id": "rb-" + at, "end_user": "u"})

    async def prepared_now(self, ctx, a, rd, res, at, now, eng, card, d):   # their page, prefilled: their go-ahead, nothing to send
        VN._HELD.pop(ctx.account, None)
        return {"status": "page_on_phone", "venue": VENUE, "booked": False}

    async def submit(self, account, held, said):
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
                mock.patch.object(VN, "read_channel", lambda rd, card=None, **k: None), mock.patch.object(VN, "card_of", lambda *a, **k: None),
                mock.patch.object(VN, "rules_for", self.rules_for), mock.patch.object(VN, "_said", lambda out, d, **k: out),
                mock.patch.object(VN, "_via_agapi", self.via_agapi), mock.patch.object(VN, "_prepared_now", self.prepared_now),
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


ITEM_7 = [("Book Sasha Test Venue Thursday 22 October at 20:15 for 2", "hold_venue", booking("20:15")),
          ("Prefilled form", "hold_venue", booking("20:15"))]


class TheYesSendsTheCardOnScreen(unittest.TestCase):
    def test_gate_item_7_then_a_new_booking_handle_it_yes(self):
        """THE GATE (row 914): fails on 262's code — "Handle it" read back item 7's 20:15 and the yes sent it."""
        w, out = play(ITEM_7 + [("Handle it", "book_venue", booking("21:15")),        # the model answered the one question it asked
                                ("Yes, send it.", "book_venue", {})])                  # for 21:15 (no new hold): the booking she was given
        self.assertEqual(out[2]["status"], "awaiting_yes")
        self.assertEqual(out[2]["read_back"], ["· 2026-10-22T21:15"])                  # the card on screen is 21:15
        self.assertEqual(w.sent, [{"when": "2026-10-22T21:15", "read_back_id": "rb-2026-10-22T21:15", "sha": "sha-2026-10-22T21:15"}])
        self.assertEqual(out[3]["status"], "confirmed")                                # 21:15 sent, 20:15 untouched
        self.assertIn("21:15", out[3]["line"])

    def test_gate_with_the_new_booking_held_first(self):
        w, out = play(ITEM_7 + [("Thursday at 21:15 instead, for 2", "hold_venue", booking("21:15")),
                                ("Handle it", "hold_venue", booking("21:15")), ("Yes, send it.", "book_venue", {})])
        self.assertEqual([s["when"] for s in w.sent], ["2026-10-22T21:15"])

    def test_a_prefilled_form_is_never_sent_by_a_later_yes(self):
        w, out = play(ITEM_7 + [("Yes, send it.", "book_venue", {})])
        self.assertEqual(w.sent, [])
        self.assertEqual(out[2], {"status": "nothing_waiting", "booked": False, "in_app": True})
        self.assertEqual(V.yes_line("book_venue", {"ok": True, "result": out[2]}), "There's nothing waiting to send.")

    def test_no_card_waiting_nothing_is_sent(self):
        w, out = play([("Yes, send it.", "book_venue", {})])
        self.assertEqual((w.sent, out[0]["status"]), ([], "nothing_waiting"))

    def test_whatsapp_has_no_card_and_is_as_it_was(self):
        w, out = play([("Yes, send it.", "book_venue", {})], in_app=False)
        self.assertEqual((w.sent, out[0]), ([], {"error": "nothing_held"}))

    def test_a_card_is_answered_once(self):
        w, out = play(ITEM_7[:1] + [("Handle it", "book_venue", booking("20:15")), ("Yes, send it.", "book_venue", {}),
                                    ("Yes, send it.", "book_venue", {})])
        self.assertEqual(len(w.sent), 1)
        self.assertEqual(out[3]["status"], "already_sent")


class HandleItReadsBackByTheOnePath(unittest.TestCase):
    """Rule 0b · 262's capability (book_venue on "Handle it" reads back as hold_venue does), moved onto the card path."""

    def test_book_venue_on_handle_it_is_hold_venue_with_its_booking(self):
        w, a = play(ITEM_7[:1] + [("Handle it", "book_venue", booking("21:15"))])
        w, b = play(ITEM_7[:1] + [("Handle it", "hold_venue", booking("21:15"))])
        self.assertEqual(a[1], b[1])
        self.assertEqual(a[1]["ask"], V.READ_BACK_ASK.format(venue=VENUE))

    def test_no_booking_given_hold_first_never_a_clear_yes(self):
        w, out = play(ITEM_7[:1] + [("Handle it", "book_venue", {})])
        self.assertEqual(out[1], {"error": "hold_first"})

    def test_other_words_are_still_no_yes(self):
        w, out = play(ITEM_7[:1] + [("hmm, maybe", "book_venue", booking("21:15"))])
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
        w, out = play(ITEM_7[:1] + [("Handle it", "book_venue", booking("21:15")), ("Yes, send it.", "book_venue", {})])
        line = V.yes_line("book_venue", {"ok": True, "result": out[2]})
        self.assertEqual(line, "✅ Booked: Sasha Test Venue, 2026-10-22 at 21:15 — reference TV-263. Shall I put it in your calendar?")
        self.assertEqual(len(re.split(r"(?<=[.?!])\s+", line)), 2)

    def test_not_in_the_app_she_says_it_as_before(self):
        self.assertEqual(V.yes_line("book_venue", {"ok": True, "result": {"status": "confirmed", "line": "✅ Booked: X."}}), "")
        self.assertEqual(V.yes_line("hold_venue", {"ok": True, "result": {"status": "nothing_waiting", "in_app": True}}), "")

    def test_the_turn_says_it_and_ends_on_it(self):
        from app.agent import sasha as S
        src = inspect.getsource(S.turn)
        self.assertIn('rb = (_V.read_back_line(u.name, r) or _V.yes_line(u.name, r) or _V.page_line(u.name, r)) if honest else ""', src)   # 264: + a page
        self.assertIn("if agapi_out or read_back_said:", src)


if __name__ == "__main__":
    unittest.main()
