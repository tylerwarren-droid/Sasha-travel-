"""Sasha 249 · THE CONSISTENCY TEST (EU 245, docs/sasha/one-truth-spec.md §3) — T1–T14, offline, in the deploy gate (it runs with the
unit suite). Each T names the ONE place a fact is decided and checks every surface reads it from there.

    cd backend && python -m unittest tests.test_one_truth -v
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW, wa_agent as WA
from tests.test_guest_whatsapp_s75 import ACCOUNT, GUEST, SANDBOX, Base, run


class T9_WhatsAppReachesTheBrain(Base):
    """With the flag on, every message type reaches sasha.turn (a photo through its intake, which is the brain's); none reaches
    wa_brain.web_turn or HELP. STOP / opt-out and the space switch (Tyler's keyword rule, T11) stay in front."""

    def setUp(self):
        super().setUp()
        self.seen = []

        async def agent(ch, body, payload, st, out, now, button_text="", voice_in=False):
            self.seen.append(("agent", body, payload))
            out.text("ok")
            return "x"

        async def photo(ch, p, st, out, now):
            self.seen.append(("photo", "", ""))
            out.text("ok")
            return "x"

        async def web(ctx, body):
            self.seen.append(("web_turn", body, ""))
            return True
        from booking_signer import wa_brain as WB
        self.ps = [mock.patch.object(WA, "agent_turn", agent), mock.patch.object(WA, "photo_intake", photo),
                   mock.patch.object(WB, "web_turn", web), mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "agent"})]
        for p in self.ps:
            p.start()
        self.link()

    def tearDown(self):
        for p in reversed(self.ps):
            p.stop()
        super().tearDown()

    def send(self, **extra):
        ch = run(GW.STORE.channel_for(GW.wa_key(GUEST)))
        run(GW.turn(ch, SANDBOX, {"From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "Body": "", "ButtonPayload": "", "ButtonText": "", **extra}))

    def test_every_message_type(self):
        self.send(Body="a table for two tonight")                                     # text
        self.send(ButtonPayload="yn:yes", ButtonText="Yes")                           # her own button
        self.send(ButtonPayload="call:abc:yes", ButtonText="Yes")                     # an old flow's button nothing waits on
        self.send(NumMedia="1", MediaContentType0="image/jpeg", MediaUrl0="https://x.test/p.jpg")      # image
        self.send(NumMedia="1", MediaContentType0="application/pdf", MediaUrl0="https://x.test/d.pdf")  # document
        self.send()                                                                   # empty
        self.assertEqual([k for k, *_ in self.seen], ["agent", "agent", "agent", "photo", "agent", "agent"], self.seen)
        self.assertNotIn(GW.HELP, self.bodies())

    def test_stop_stays_in_front(self):
        self.send(Body="STOP")
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main()
