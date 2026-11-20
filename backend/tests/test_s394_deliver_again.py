"""Sasha 394 (1) · CR 206 · an inbound WhatsApp message AgAPI couldn't decide is delivered again — never answered by Sasha.

CR 206 (agapi-live b8ea1634): messages.whatsapp_inbound decides the owner once; when it can't, it answers an error (upstream_unreachable),
releases its claim and records nothing — "an error is 'deliver again', never 'no role'". Before: Sasha read any error as {"matched": False}
and answered the message herself (S2's class: AD's message answered as Sasha's). Twilio is answered at once (379a) and its webhook carries no
retry policy (measured 20 Nov), so Tyler chose: Sasha redelivers (booking_signer/redeliver).

THE CLASS: every inbound outcome (matched, unmatched, every error) through the real path (inbound_phone._whatsapp → _sms) → AgAPI's, Sasha's,
or UNDECIDED; UNDECIDED composes nothing, releases the message's step and is delivered again — the same message id, AgAPI asked afresh —
until AgAPI decides (then exactly its owner answers), for at most a day. ONE place decides (venue_submit.inbound_owner).

    cd backend && python -m unittest tests.test_s394_deliver_again -v
"""
from __future__ import annotations

import asyncio
import inspect
import time
import unittest
from unittest import mock

from agapi import venue_submit as VS
from booking_signer import guest_whatsapp as GW, inbound_phone as IP, redeliver as RD
from tests.test_guest_whatsapp_s75 import Base, GUEST, SANDBOX

from agapi import contract_shape as _CS
#: every error AgAPI can answer this op with (its published codes) + the transport's own (AgAPI not answering at all)
ERRORS = tuple(sorted(_CS.KC.ERROR_CODES)) + ("timeout", "unreachable", "not_configured")


class EveryInboundOutcome(Base):
    def setUp(self):
        super().setUp()
        RD._MEM.clear()
        self.addCleanup(RD._MEM.clear)
        self.asked, self.replies, self.dispatched = [], [], []
        self.answer = {"ok": True, "result": {"matched": False}}

        async def call(op, body, approval=None, account=None):
            if op == "messages.whatsapp_inbound":
                self.asked.append(body["message_id"])
                return self.answer
            return {"ok": True, "result": {}}

        async def dispatch(p, call_for):
            self.dispatched.append(p.get("Body"))
            return "Sasha's answer"

        async def by_rest(p, sender, lines):
            self.replies.extend(lines)
        for t in (mock.patch.object(VS, "CALL", call), mock.patch.object(GW, "dispatch", dispatch),
                  mock.patch.object(IP, "reply_by_rest", by_rest), mock.patch.object(GW, "linked", mock.AsyncMock(return_value=True))):
            t.start()
            self.addCleanup(t.stop)

    def inbound(self, sid, body="investigate Northwind"):
        p = {"From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "Body": body, "MessageSid": sid, "_message_id": sid, "NumMedia": "0"}
        asyncio.get_event_loop().run_until_complete(IP._whatsapp(p, "whatsapp", GUEST, body, sid, None))

    def test_every_error_is_undecided_nothing_composed_step_released_held(self):
        for i, code in enumerate(ERRORS):
            sid = f"SM{i:032x}"
            self.replies.clear()
            self.answer = {"ok": False, "error": {"code": code}}
            self.inbound(sid)
            self.assertEqual(self.asked[-1], sid, code)
            self.assertEqual((self.replies, self.dispatched), ([], []), code)                  # nothing of Sasha's answered it
            self.assertIn(sid, RD._MEM, code)                                                 # delivered again later
            self.assertNotIn((sid, "agapi_in"), GW._SEEN_STEPS, code)                         # the next delivery asks AgAPI afresh

    def test_unmatched_is_sashas_matched_is_agapis(self):
        self.inbound("SM" + "a" * 32, "a table for 2 tonight")
        self.assertEqual(self.dispatched, ["a table for 2 tonight"])                        # Sasha's own paths answer it
        self.answer = {"ok": True, "result": {"matched": True}}
        self.inbound("SM" + "b" * 32)
        self.assertEqual(self.dispatched, ["a table for 2 tonight"])                         # AgAPI's: nothing more of Sasha's
        self.assertEqual(RD._MEM, {})

    def test_the_redelivery_asks_again_and_only_its_owner_answers(self):
        sid = "SM" + "c" * 32
        self.answer = {"ok": False, "error": {"code": "upstream_unreachable"}}
        self.inbound(sid)
        RD._MEM[sid]["next_at"] = 0
        asyncio.get_event_loop().run_until_complete(RD.sweep_once())                          # still undecided: held again, counted
        self.assertEqual((self.asked, RD._MEM[sid]["attempts"], self.replies), ([sid, sid], 1, []))
        self.answer = {"ok": True, "result": {"matched": True}}                               # AD is back: AD's
        RD._MEM[sid]["next_at"] = 0
        asyncio.get_event_loop().run_until_complete(RD.sweep_once())
        self.assertEqual((self.asked, RD._MEM, self.replies, self.dispatched), ([sid, sid, sid], {}, [], []))

    def test_a_redelivery_decided_as_sashas_is_answered_once(self):
        sid = "SM" + "d" * 32
        self.answer = {"ok": False, "error": {"code": "unreachable"}}
        self.inbound(sid, "book dinner for 2")
        self.answer = {"ok": True, "result": {"matched": False}}
        RD._MEM[sid]["next_at"] = 0
        asyncio.get_event_loop().run_until_complete(RD.sweep_once())
        self.assertEqual((self.dispatched, RD._MEM), (["book dinner for 2"], {}))

    def test_past_a_day_it_is_given_up_never_answered(self):
        sid = "SM" + "e" * 32
        self.answer = {"ok": False, "error": {"code": "upstream_unreachable"}}
        self.inbound(sid)
        RD._MEM[sid].update(next_at=0, created_at=time.time() - RD.MAX_AGE_S - 1)
        asyncio.get_event_loop().run_until_complete(RD.sweep_once())
        self.assertEqual((RD._MEM, self.replies, self.asked), ({}, [], [sid]))


class OnePlaceDecides(unittest.TestCase):
    def test_the_owner_from_agapis_one_answer(self):
        self.assertEqual(VS.inbound_owner({"matched": True}), VS.AGAPI)
        self.assertEqual(VS.inbound_owner({"matched": False}), VS.SASHA)
        for got in ({"undecided": True, "why": "upstream_unreachable"}, {}, None, {"why": "x"}):
            self.assertEqual(VS.inbound_owner(got), VS.UNDECIDED, got)

    def test_ratchet_the_webhook_reads_no_matched_flag_of_its_own(self):
        src = inspect.getsource(IP._sms)
        self.assertIn("VS.inbound_owner(got)", src)
        self.assertNotIn('got.get("matched")', src)
        self.assertNotIn('"matched": False', inspect.getsource(VS.whatsapp_inbound).split("if not r.get(\"ok\")")[1].split("res = ")[0])


if __name__ == "__main__":
    unittest.main()
