"""Sasha 294 · let Tyler's WhatsApp reach AD: EVERY inbound WhatsApp goes to AgAPI's ONE inbound op first (messages.whatsapp_inbound,
CR 127's classifier), with Twilio's MessageSid and whether the sender is a linked guest. Matched → AgAPI has it; unmatched → the guest
flow and the old paths, exactly as before. A Twilio retry is decided once."""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from agapi import venue_submit as VS
from booking_signer import guest_whatsapp as GW, inbound_phone as IP

TYLER = "+34600000001"


def run(c):
    return asyncio.run(c)


class EveryWhatsAppGoesToAgAPIFirst(unittest.TestCase):
    def setUp(self):
        GW._SEEN_SIDS.clear()

    def deliver(self, body, *, matched, linked=True, sid="SM294"):
        p = {"From": f"whatsapp:{TYLER}", "To": "whatsapp:+447700900000", "Body": body, "MessageSid": sid}
        handed, guest_flow = [], []

        async def inbound(s, t, message_id=None, guest=False, twilio=None):   # Sasha 318 · Twilio's fields go to the one mapper
            handed.append({"from": s, "text": t, "message_id": message_id, "guest": guest})
            return {"matched": matched}

        async def dispatch(p_, call_for):
            guest_flow.append(p_["Body"])
            return ""

        class Store:
            async def call_for_number(self, n, since):
                return None

            async def put(self, row):
                return True
        with mock.patch.object(IP, "_verified", mock.AsyncMock(return_value=p)), mock.patch.object(IP, "STORE", Store()), \
                mock.patch.object(GW, "STORE", None), mock.patch.object(VS, "whatsapp_inbound", inbound), \
                mock.patch.object(GW, "linked", mock.AsyncMock(return_value=linked)), mock.patch.object(GW, "dispatch", dispatch):
            run(IP.sms(None))
        return handed, guest_flow

    def test_a_a_guests_booking_reply_still_reaches_the_guest_flow(self):
        handed, flow = self.deliver("Sí, a las 21:00 para dos", matched=False)
        self.assertEqual(handed, [{"from": TYLER, "text": "Sí, a las 21:00 para dos", "message_id": "SM294", "guest": True}])
        self.assertEqual(flow, ["Sí, a las 21:00 para dos"])   # unmatched: the guest flow, exactly as before

    def test_b_a_guests_investigate_goes_to_agapi_and_nowhere_else(self):
        handed, flow = self.deliver("investigate Lehman Brothers and Richard Fuld", matched=True)
        self.assertEqual(len(handed), 1)
        self.assertEqual(flow, [])   # AgAPI took it: the guest flow never sees it

    def test_c_a_retried_message_sid_is_handled_once(self):
        handed1, flow1 = self.deliver("investigate Lehman Brothers", matched=True, sid="SM-RETRY")
        handed2, flow2 = self.deliver("investigate Lehman Brothers", matched=True, sid="SM-RETRY")   # Twilio retries the same SID
        self.assertEqual((len(handed1), len(handed2), flow1, flow2), (1, 0, [], []))   # AgAPI asked once; the retry stops at its verdict
        handed3, flow3 = self.deliver("hola", matched=False, sid="SM-RETRY-2")
        handed4, flow4 = self.deliver("hola", matched=False, sid="SM-RETRY-2")
        self.assertEqual((len(handed3), len(handed4), flow3), (1, 0, ["hola"]))   # unmatched: the guest flow's own SID de-dupe decides

    def test_d_the_hand_off_says_guest_and_carries_the_sid(self):
        got = []

        async def call(op, body, approval=None, account=None):
            got.append((op, body))
            return {"ok": True, "result": {"matched": True, "ad": "door", "replied": True}}
        with mock.patch.object(VS, "CALL", call):
            r = run(VS.whatsapp_inbound(TYLER, "investigate Acme", message_id="SM1", guest=True))
        self.assertEqual(got, [("messages.whatsapp_inbound", {"from": TYLER, "text": "investigate Acme", "message_id": "SM1", "guest": True})])
        self.assertEqual((r["matched"], r["ad"]), (True, "door"))

    def test_e_no_whatsapp_skips_the_classifier(self):
        """Root test (3): the only early exit before AgAPI's op is a message without a SID (refused) — no sender filter, no keywords."""
        import inspect
        src = inspect.getsource(IP.sms)
        import re as _re
        code = "\n".join(_re.sub(r"#.*$", "", ln) for ln in src.splitlines())   # the code, not its comments
        head = code[:code.index("VS.whatsapp_inbound(")]
        self.assertNotIn("linked(sender) and", head)
        self.assertNotRegex(head, r"investigate|ASK_RE|re\.search")


if __name__ == "__main__":
    unittest.main()
