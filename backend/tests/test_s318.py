"""Sasha 318 · CR 147 (row 1567) · "Allow" on a WhatsApp call-permission request reaches AgAPI.

AgAPI's interview (CR 147 (3)) asks the subject for permission to call (VOICE_CALL_REQUEST). Their answer is a tapped button: Twilio posts
ButtonPayload (ACCEPTED / REJECTED) and CallPermissionIsPermanent ("true" / "false") to Sasha's ONE webhook. AgAPI's
messages.whatsapp_inbound takes it as button {payload, permanent}. Before this, Sasha passed {from, text} only, so the "Allow" arrived
as an empty message and the call could never be placed.
Root test: (1) ONE inbound mapper — venue_submit.button_of / whatsapp_inbound, the only reader of Twilio's button fields for AgAPI;
(2) no button-specific branch elsewhere: both callers (the webhook's first hand-over, AD's space) pass Twilio's fields as they are;
(3) proved with Twilio's webhook form for a call-permission answer, signed, through the real route. Offline.

    cd backend && python -m unittest tests.test_s318 -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import unittest
from unittest import mock

from agapi import venue_submit as VS
from booking_signer import guest_whatsapp as GW
from tests import test_inbound_phone as TIP

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBJECT = "+447700900135"
# Twilio's inbound WhatsApp webhook for a tap on the call-permission request (the fields Twilio documents for a button reply plus
# CallPermissionIsPermanent). It wasn't captured live: no call-permission request has been sent from Kanoe's number yet.
ALLOW = {"SmsMessageSid": "SM5b1c0e3a4f7d4b2a9c1e0f6a7b8c9d01", "NumMedia": "0", "ProfileName": "Jon", "MessageType": "button",
         "SmsSid": "SM5b1c0e3a4f7d4b2a9c1e0f6a7b8c9d01", "WaId": SUBJECT[1:], "SmsStatus": "received", "Body": "",
         "To": "whatsapp:+447915914215", "NumSegments": "1", "ReferralNumMedia": "0", "MessageSid": "SM5b1c0e3a4f7d4b2a9c1e0f6a7b8c9d01",
         "AccountSid": "AC00000000000000000000000000000000", "From": f"whatsapp:{SUBJECT}", "ApiVersion": "2010-04-01",
         "ButtonPayload": "ACCEPTED", "CallPermissionIsPermanent": "true",
         "OriginalRepliedMessageSid": "MM0f1e2d3c4b5a69788796a5b4c3d2e1f0", "OriginalRepliedMessageSender": "whatsapp:+447915914215"}


class TheMapper(unittest.TestCase):
    def test_button_of(self):
        self.assertEqual(VS.button_of(ALLOW), {"payload": "ACCEPTED", "permanent": True})
        self.assertEqual(VS.button_of({**ALLOW, "ButtonPayload": "REJECTED", "CallPermissionIsPermanent": "false"}),
                         {"payload": "REJECTED", "permanent": False})
        self.assertEqual(VS.button_of({**ALLOW, "CallPermissionIsPermanent": ""}), {"payload": "ACCEPTED"})   # not said: not guessed
        self.assertIsNone(VS.button_of({**ALLOW, "ButtonPayload": ""}))                                    # typed words: no button
        self.assertIsNone(VS.button_of(None))

    def test_one_reader_no_second_branch(self):
        for f in (ROOT / "agapi").rglob("*.py"):
            if f.name != "venue_submit.py":
                self.assertNotIn("CallPermissionIsPermanent", f.read_text(), f)
        src = inspect.getsource(VS)
        self.assertEqual(src.count('"ButtonPayload"'), 1)                                               # button_of, once
        self.assertIn("twilio=p", (ROOT / "booking_signer" / "inbound_phone.py").read_text())             # the webhook's hand-over
        self.assertIn('twilio=ctx.get("twilio")', (ROOT / "products" / "diligence.py").read_text())       # AD's space


class ThroughTheWebhook(TIP.InboundPhone):
    """The signed form, through Sasha's real /api/booking/twilio/sms → AgAPI's messages.whatsapp_inbound, as sent."""

    def go(self, form):
        sent = []

        async def call(op, body, approval=None, account=None):
            sent.append((op, body))
            return {"ok": True, "result": {"matched": True, "kept": True, "ad": "interview"}}
        with mock.patch.object(VS, "CALL", call), mock.patch.object(GW, "first_time", mock.AsyncMock(return_value=True)), \
                mock.patch.object(GW, "linked", mock.AsyncMock(return_value=False)):
            r = self.post("sms", form)
        self.assertEqual(r.status_code, 200)
        return [b for op, b in sent if op == "messages.whatsapp_inbound"]

    def test_allow_reaches_agapi_as_button(self):
        got = self.go(ALLOW)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["button"], {"payload": "ACCEPTED", "permanent": True})
        self.assertEqual((got[0]["from"], got[0]["text"], got[0]["message_id"]), (SUBJECT, "", ALLOW["MessageSid"]))

    def test_not_now_and_a_temporary_allow(self):
        self.assertEqual(self.go({**ALLOW, "ButtonPayload": "REJECTED", "CallPermissionIsPermanent": "false"})[0]["button"],
                         {"payload": "REJECTED", "permanent": False})

    def test_a_typed_message_carries_no_button(self):
        got = self.go({k: v for k, v in ALLOW.items() if k not in ("ButtonPayload", "CallPermissionIsPermanent", "MessageType")}
                      | {"Body": "I'm free after 5"})
        self.assertNotIn("button", got[0])

    for _k in [k for k in dir(TIP.InboundPhone) if k.startswith("test_")]:   # the harness only: its own tests run in their module
        locals()[_k] = None


class InADsSpace(unittest.TestCase):
    def test_the_space_hands_the_same_fields_to_the_same_mapper(self):
        from products import diligence as DG
        sent = []

        async def call(op, body, approval=None, account=None):
            sent.append(body)
            return {"ok": True, "result": {"matched": True, "ad": "door"}}

        class Out:
            def text(self, t):
                pass
        with mock.patch.object(VS, "CALL", call):
            asyncio.run(DG.hand_over({"ch": {"number_e164": SUBJECT}, "frm": "whatsapp", "out": Out(), "sid": "SM1", "twilio": ALLOW}, "", []))
        self.assertEqual(sent[0]["button"], {"payload": "ACCEPTED", "permanent": True})


if __name__ == "__main__":
    unittest.main()
