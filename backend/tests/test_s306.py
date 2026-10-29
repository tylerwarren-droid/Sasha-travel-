"""Sasha 306 · a hotel stay's nights / check-in changed by its own route (AgAPI CR 137), said as AgAPI's record has it; and a change or
cancel request always calls its quote tool first, so a price, refund or read-back is said by code before any yes. Offline.

    cd backend && python -m unittest tests.test_s306 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import unittest
from datetime import datetime, timezone
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
STAY = {"check_in": "2026-11-15", "check_out": "2026-11-19", "nights": 4, "arrival": "15:00"}
LINES = ["Kanoe writes to Hotel WhatsApp (sandbox) by WhatsApp asking for a change to 3 nights (check-out Wed 18 Nov) (your booking "
         "2026-11-15 15:00, 1 people): “Hello, could we change the booking to 3 nights, check-out Wednesday 18 November? Thank you.”",
         "It's a request until they answer; you'll be told."]


def run(c):
    return asyncio.run(c)


class Ctx:
    account, session, user_said = "acct-306", "web:1", ""

    def __init__(self):
        self.started = datetime.now(timezone.utc)


class NoListInSasha(unittest.TestCase):
    def test_whatever_was_asked_goes_to_agapi(self):   # the (at, party, arrive) lists dropped a stay's nights
        from agapi import venue_submit as VS
        calls = []

        async def call(account, op, body, approval=None):
            calls.append((op, dict(body), approval))
            if approval is None:
                return {"ok": False, "error": {"code": "approval_required", "details": {"read_back_id": "rb_1", "read_back": {"lines": LINES}}}}
            return {"ok": True, "result": {"status": "sent", "change_act_id": "act_CH"}}
        with mock.patch.object(VS, "_call", call), mock.patch.object(VS, "end_user", mock.AsyncMock(return_value="eu_1")), \
                mock.patch.object(VS, "target", mock.AsyncMock(return_value="sandbox")), \
                mock.patch.object(VS, "_approval", mock.AsyncMock(return_value="apv_1")), \
                mock.patch.object(VS, "acts_of", mock.AsyncMock(return_value=[])), mock.patch.object(VS, "_remember", mock.AsyncMock()):
            rb = run(VS.change_read_back("acct-306", "act_ST", "change", nights=3, check_in=None))
            run(VS.change_submit("acct-306", {**rb, "kind": "change", "ask": {"nights": 3}}, "Yes, ask them"))
        self.assertEqual(calls[0][1], {"end_user": "eu_1", "act_id": "act_ST", "kind": "change", "nights": 3})
        self.assertEqual(calls[1][1]["nights"], 3)
        self.assertTrue(calls[1][2])
        src = (ROOT / "agapi" / "venue_submit.py").read_text()
        self.assertNotIn('in ("at", "party", "arrive")', src)


class TheStayAsTheRecordHasIt(unittest.TestCase):
    def test_my_trips_carries_agapis_stay_and_the_hotels_answer(self):
        from agapi import itinerary as IT
        g = {"act_id": "act_ST", "state": "confirmed", "route": "whatsapp", "venue": {"name": "Hotel WhatsApp (sandbox)"}, "at": "2026-11-15T15:00",
             "party": 1, "stay": {**STAY, "check_out": "2026-11-18", "nights": 3},
             "answers": {"change": {"state": "confirmed", "asked": {"nights": 3},
                                    "venue_words": {"untrusted_text": "Yes, 3 nights is fine — see you on the 15th.", "at": "x"}}}}
        row = IT._from_record(g, {"stay": True})
        self.assertEqual((row["type"], row["stay"]["check_out"], row["stay"]["nights"]), ("hotel", "2026-11-18", 3))
        self.assertEqual(row["change_answer"]["venue_said"]["untrusted_text"], "Yes, 3 nights is fine — see you on the 15th.")
        self.assertEqual(IT.stay_end({"check_out": "2026-11-18", "when": "2026-11-15T15:00", "nights": 99}), "2026-11-18")   # never computed

    def test_the_read_back_is_the_record_then_agapis_lines_with_no_channel(self):
        from agapi import s2_manage as M, venue_submit as VS
        from app.agent import voice as V
        b = {"act_id": "act_ST", "venue": "Hotel WhatsApp (sandbox)", "route": "whatsapp", "route_words": "", "date": "2026-11-15", "stay": STAY}
        rb = {"ok": True, "end_user": "eu_1", "read_back_id": "rb_1", "lines": LINES, "act_id": "act_ST"}
        with mock.patch.object(VS, "change_read_back", mock.AsyncMock(return_value=rb)) as crb:
            r = run(M._act_notice(Ctx(), {"nights": 3}, b, "change", "change_booking"))
        M._HELD.pop("acct-306", None)
        self.assertEqual(crb.call_args.kwargs, {"nights": 3})
        said = V.flight_line("change_booking", {"ok": True, "result": r})
        self.assertTrue(said.startswith("Your stay at Hotel WhatsApp (sandbox) now reads Sun 15 Nov to Thu 19 Nov (4 nights)."))
        self.assertIn("a change to 3 nights (check-out Wed 18 Nov)", said)   # the new check-out is AgAPI's words
        self.assertNotIn("by WhatsApp", said)                               # HER VOICE never names a channel
        self.assertTrue(said.endswith(V.STAY_ASK))


class FoundOnTheWalk(unittest.TestCase):
    def test_no_name_given_his_own_words_name_the_stay(self):   # the forced call gave no name: three hotels, "which_booking"
        from agapi import s2_manage as M
        rows = [{"kind": "hotel", "title": t, "when": "2026-11-15T15:00", "id": i, "source": "venue", "status": "confirmed"}
                for t, i in (("Marriott Test Hotel (sandbox)", "act_M1"), ("Hotel WhatsApp (sandbox)", "act_W"), ("Marriott Test Hotel (sandbox)", "act_M2"))]
        ctx = Ctx()
        ctx.user_said = "Make my stay at Hotel WhatsApp 3 nights instead of 4."
        with mock.patch.object(M, "plans_of", mock.AsyncMock(return_value=rows)):
            self.assertEqual(run(M.booking_meant(ctx, {}, "hotel"))["id"], "act_W")
            ctx.user_said = "make my stay 3 nights"
            with self.assertRaises(Exception):   # nothing names it: asked, never the first taken
                run(M.booking_meant(ctx, {}, "hotel"))

    def test_what_the_record_already_holds_is_not_asked_again(self):   # "a change to check-in Sun 15 Nov and 3 nights"
        from agapi import s2_manage as M, venue_submit as VS
        b = {"act_id": "act_ST", "venue": "Hotel WhatsApp (sandbox)", "route": "whatsapp", "route_words": "", "date": "2026-11-15",
             "party": 1, "stay": STAY}
        rb = {"ok": True, "end_user": "eu_1", "read_back_id": "rb_1", "lines": LINES, "act_id": "act_ST"}
        with mock.patch.object(VS, "change_read_back", mock.AsyncMock(return_value=rb)) as crb:
            run(M._act_notice(Ctx(), {"nights": 3, "check_in": "2026-11-15", "new_party": 1}, b, "change", "change_booking"))
        M._HELD.pop("acct-306", None)
        self.assertEqual(crb.call_args.kwargs, {"nights": 3})


class APriceBeforeEveryChange(unittest.TestCase):
    def test_a_change_or_cancel_request_calls_its_quote_tool_first(self):
        from app.agent import voice as V
        for m, tool in [("Move my flight home from Rio to the 22nd of November.", "change_booking"),
                        ("move it to the 22nd instead — move my flight", "change_booking"),
                        ("Make it 3 nights instead of 4.", "change_booking"),
                        ("Make my Marriott stay 3 nights instead of 4", "change_booking"),
                        ("I'd like to arrive a day later at the hotel", "change_booking"),
                        ("Cancel my flight home.", "cancel_booking"),
                        ("cancel the dinner at Casa Marea", "cancel_venue")]:
            self.assertEqual(V.manage_tool(m), tool, m)
        for m in ("Yes, make this change.", "Yes, cancel it.", "Make a reservation for dinner on Friday", "Find me a hotel in Rio",
                  "I'm running late for dinner", "What's booked on my Rio trip now?"):
            self.assertIsNone(V.manage_tool(m), m)

    def test_the_turn_runs_it_first_by_code(self):   # found live: the agent models refuse a forced tool_choice (400)
        src = (ROOT / "app" / "agent" / "sasha.py").read_text()
        self.assertIn('must = _V.manage_tool(message) if honest and surface == "s2" and not tap_uses else None', src)
        self.assertIn('tap_uses = [_TapUse(f"toolu_must_{turn_key}", must, got)]', src)
        self.assertEqual(src.count("tool_choice="), 1)   # only quote_args' own call — never the agent models' (they refuse it)

    def test_its_arguments_come_from_a_forced_call_without_any_approval(self):
        from app.agent import sasha as SA
        seen = {}

        class Use:
            type, input = "tool_use", {"what": "flight", "name": "Rio", "leg": "back", "new_date": "2026-11-22", "approval": {"said": "x"}}

        class Client:
            class messages:
                @staticmethod
                async def create(**kw):
                    seen.update(kw)
                    return type("R", (), {"content": [Use()]})()
        tool = {"name": "change_booking", "description": "d", "input_schema": {"type": "object"}, "cache_control": {"type": "ephemeral"}}
        got = run(SA.quote_args(Client, tool, [{"role": "user", "content": "move my flight home to the 22nd"}]))
        self.assertEqual(got, {"what": "flight", "name": "Rio", "leg": "back", "new_date": "2026-11-22"})
        self.assertEqual((seen["model"], seen["tool_choice"]), (SA.QUOTE_ARGS_MODEL, {"type": "tool", "name": "change_booking"}))
        self.assertNotIn("cache_control", seen["tools"][0])
        Use.input = {"what": "hotel", "id": "Hotel WhatsApp", "nights": 3, "leg": "<UNKNOWN>"}   # found live (Haiku 4.5)
        self.assertEqual(run(SA.quote_args(Client, tool, [])), {"what": "hotel", "name": "Hotel WhatsApp", "nights": 3})
        Use.input = {"what": "flight", "id": "ord_0000BBtfNeeST96cY4vHwN", "new_date": "2026-11-22"}
        self.assertEqual(run(SA.quote_args(Client, tool, []))["id"], "ord_0000BBtfNeeST96cY4vHwN")


if __name__ == "__main__":
    unittest.main()
