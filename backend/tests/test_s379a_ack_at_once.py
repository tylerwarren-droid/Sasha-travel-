"""Sasha 379a · TWILIO IS ANSWERED AT ONCE; the message's ONE decision runs after it, replying by REST. NO PATCHES.

Found live (12 Nov 14:48 UTC, Tyler's "es" to AD's offer): AgAPI → AD took ~19 s inside Sasha's webhook; Twilio gave up at 15 s (499) and
posted the same message to the sender's fallback URL — an old service (sasha-api-seven, retired since, Tyler's go 16:05) that answered
it with its own travel brain. AD's answer came too: two answers to one message. Now the webhook answers Twilio with empty TwiML at once
(inbound_phone.ACK_WAIT_S = 0 in production), and the message's work — AgAPI's inbound first, then Sasha's own paths — runs in the
background; whatever it says goes by REST (inbound_phone.reply_by_rest → GW.SENDER), once.

    cd backend && python -m unittest tests.test_s379a_ack_at_once -v
"""
from __future__ import annotations

import asyncio
import inspect
import threading
import time
import unittest
from unittest import mock

from agapi import venue_submit as VS
from booking_signer import guest_whatsapp as GW, inbound_phone as IP
from tests import test_guest_whatsapp_s75 as T75, test_inbound_phone as TIP

GUEST, SANDBOX = T75.GUEST, T75.SANDBOX


class SlowAgAPI:
    """messages.whatsapp_inbound that takes as long as the test says (AD answering slowly), then AgAPI's own answer."""

    def __init__(self, matched: bool):
        self.go, self.matched, self.calls = threading.Event(), matched, []

    async def __call__(self, op, body, approval=None, account=None):
        self.calls.append(op)
        if op == "messages.whatsapp_inbound":
            while not self.go.is_set():   # held past Twilio's 15 s — released by the test
                await asyncio.sleep(0.02)
            return {"ok": True, "result": {"matched": self.matched, "kept": self.matched, **({"ad": "replied"} if self.matched else {})}}
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "eu_379"}}
        return {"ok": True, "result": {}}


class AckAtOnce(T75.Webhook):
    def setUp(self):
        super().setUp()
        IP.ACK_WAIT_S = 0.0   # PRODUCTION's timing: the webhook never waits on the message's work
        # one event loop for the app, as uvicorn runs it (a bare TestClient closes its loop after each request — and the work with it)
        from fastapi.testclient import TestClient
        self._client = TestClient(self.c.app)
        self.c = self._client.__enter__()
        self.addCleanup(self._client.__exit__, None, None, None)

    def post(self, sid, body):
        form = {"MessageSid": sid, "From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "Body": body}
        t0 = time.monotonic()
        r = self.c.post("/api/booking/twilio/sms", data=form, headers={"X-Twilio-Signature": TIP.sign("sms", form)})
        return r, time.monotonic() - t0

    def finish(self, slow):
        slow.go.set()
        deadline = time.monotonic() + 10
        while any(not t.done() for t in IP._INBOUND) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse([t for t in IP._INBOUND if not t.done()], "the message's work never finished")

    def test_a_slow_agapi_still_acks_twilio_at_once_and_ad_alone_answers(self):
        slow = SlowAgAPI(matched=True)   # AgAPI routes it to AD (who answers from Kanoe's number): Sasha says nothing more
        self.link()
        with mock.patch.object(VS, "CALL", slow):
            r, took = self.post("SM379ack1", "es")
            self.assertEqual((r.status_code, r.text.endswith("<Response></Response>")), (200, True))
            self.assertLess(took, 3.0)                                                      # never Twilio's 15 s: no fallback can fire
            self.assertEqual(GW.SENDER.sent, [])                                            # nothing said while AgAPI decides
            self.finish(slow)
        self.assertEqual(slow.calls.count("messages.whatsapp_inbound"), 1)                  # ONE decision: AgAPI's, asked once
        self.assertEqual(GW.SENDER.sent, [])                                                # AD's answer is the ONE answer

    def test_a_slow_agapi_then_sashas_one_answer_by_rest(self):
        slow = SlowAgAPI(matched=False)   # not AgAPI's: an unlinked number on the guest number → the one /you line, once, by REST
        with mock.patch.object(VS, "CALL", slow):
            r, took = self.post("SM379ack2", "hello?")
            self.assertLess(took, 3.0)
            self.assertTrue(r.text.endswith("<Response></Response>"))
            self.finish(slow)
        said = [m for m in GW.SENDER.sent if m["to"] == GUEST]
        self.assertEqual(len(said), 1)                                                      # one outbound for one message
        self.assertIn("link this number once", said[0]["body"])
        self.assertEqual(said[0]["from"], SANDBOX)                                          # from the number they wrote to

    def test_the_same_message_again_is_answered_once(self):
        slow = SlowAgAPI(matched=False)
        with mock.patch.object(VS, "CALL", slow):
            self.post("SM379ack3", "hello?")
            self.post("SM379ack3", "hello?")                                                # Twilio's retry of the same message
            self.finish(slow)
        self.assertEqual(len([m for m in GW.SENDER.sent if m["to"] == GUEST]), 1)


for _n in [n for n in vars(T75.Webhook) if n.startswith("test_")]:   # the webhook's harness only — its own tests run in their file
    setattr(AckAtOnce, _n, None)


class TheRatchet(unittest.TestCase):
    def test_production_never_waits_and_whatsapp_never_answers_in_band(self):
        self.assertEqual(IP.ACK_WAIT_S, 0.0)
        src = inspect.getsource(IP.sms)
        self.assertIn("return _twiml()", src)
        self.assertNotIn("_twiml_message", src)                                             # never a WhatsApp reply in Twilio's answer
        self.assertIn("reply_by_rest(", inspect.getsource(IP._whatsapp))


if __name__ == "__main__":
    unittest.main()
