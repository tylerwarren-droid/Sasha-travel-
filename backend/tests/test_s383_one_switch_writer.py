"""Sasha 383 · CR 202's Sasha half — EVERY product switch on Kanoe's shared WhatsApp number goes to AgAPI's ONE writer
(messages.whatsapp_switch {from, product, message_id}); Sasha keeps no record of her own of which product the CONVERSATION is in.

Found (13 Nov, CR 202's evidence): after "Sasha" AgAPI still forwarded AD's held next-steps list, and AD read a dinner request as its
list's answer — Sasha's switch ran before AgAPI's inbound and AgAPI never knew. Now ONE place tells AgAPI, once per message:
products.space.conversation_switched — called by the webhook for an explicit switch (keyword, tool row, back row; BEFORE AgAPI's
inbound reads the message: entering AD never reaches Sasha's turn) and by space.set_space for every switch Sasha's turn makes (a typo'd
keyword, a reply to a product's message, "switch to RelocateMe").

The real /twilio/sms route, a linked number (tests.test_s344_back_row's harness).
    cd backend && python -m unittest tests.test_s383_one_switch_writer -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import unittest
from unittest import mock

from agapi import venue_submit as VS
from booking_signer import guest_whatsapp as GW, inbound_phone as IP
from products import space as SPC, tools as TL
from tests.test_cr165_tools import ListSender
from tests.test_guest_whatsapp_s75 import Base, GUEST, SANDBOX
from tests.test_s344_back_row import BACK_ROW, list_reply

BACKEND = pathlib.Path(__file__).resolve().parents[1]


class EverySwitchPath(Base):
    def setUp(self):
        super().setUp()
        GW.SENDER = ListSender()
        self.ran = []
        GW._spawn = lambda coro: self.ran.append(coro)
        self.ch = self.link()
        self._ack = IP.ACK_WAIT_S
        IP.ACK_WAIT_S = 30.0
        self.addCleanup(setattr, IP, "ACK_WAIT_S", self._ack)
        SPC._SPACE.clear()
        SPC._TOLD.clear()
        self.addCleanup(SPC._SPACE.clear)

    def webhook(self, fields, sid, agapi_takes=False):
        p = {"From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "MessageSid": sid, "NumMedia": "0", "ProfileName": "Tyler",
             "WaId": GUEST.lstrip("+"), **fields}
        order = []

        async def inbound(sender, text, **kw):
            order.append(("inbound", text))
            return {"matched": agapi_takes, "replied": True, "ad": "replied"} if agapi_takes else {"matched": False}

        async def switch(sender, product, message_id):
            order.append(("switch", sender, product, message_id))
            return {"ok": True, "product": product}
        loop = asyncio.get_event_loop()
        with mock.patch.object(IP, "_verified", mock.AsyncMock(return_value=p)), mock.patch.object(VS, "whatsapp_inbound", inbound), \
                mock.patch.object(VS, "whatsapp_switch", switch), \
                mock.patch.object(GW, "first_time", mock.AsyncMock(return_value=True)), \
                mock.patch.object(GW, "linked", mock.AsyncMock(return_value=True)):
            loop.run_until_complete(IP.sms(None))
            while self.ran:
                loop.run_until_complete(self.ran.pop(0))
        return order

    def switches(self, order):
        return [o[1:] for o in order if o[0] == "switch"]

    def test_each_switch_path_calls_the_one_op_once_with_its_message_id(self):
        paths = [   # (what they sent, AgAPI takes it?, the product)
            ("the back row", BACK_ROW, False, "travel"),
            ("Due diligence's row", list_reply("🔍 Due diligence", "Investigate a company", "kanoe:tool:diligence"), True, "diligence"),
            ("Campus visits' row", list_reply("🎓 Campus visits", "Visits to universities", "kanoe:tool:campus"), False, "campus"),
            ("the keyword diligence", {"Body": "diligence"}, True, "diligence"),
            ("diligence with a question", {"Body": "diligence what's the status of the Sampo case?"}, True, "diligence"),
            ("the keyword Sasha", {"Body": "Sasha"}, False, "travel"),
            ("the keyword campus", {"Body": "campus"}, False, "campus"),
            ("españa", {"Body": "españa"}, False, "health"),
        ]
        for i, (name, fields, takes, product) in enumerate(paths):
            SPC._SPACE.clear()
            sid = f"SM383{i:02d}"
            order = self.webhook(fields, sid, agapi_takes=takes)
            self.assertEqual(self.switches(order), [(GUEST, product, sid)], name)                 # exactly one, with THIS message's id
            first_inbound = next((k for k, o in enumerate(order) if o[0] == "inbound"), None)
            if first_inbound is not None:
                self.assertLess(order.index(("switch", GUEST, product, sid)), first_inbound, name)   # AgAPI knows before it reads

    def test_a_switch_sashas_turn_makes_calls_it_once(self):
        """A switch Sasha's own turn makes (a reply to a product's message, "switch to RelocateMe" in the chat): space.set_space on a
        signed WhatsApp turn tells AgAPI — once per message, however many times the turn writes it; unchanged → nothing."""
        called = []

        async def switch(sender, product, message_id):
            called.append((sender, product, message_id))
            return {"ok": True}
        tok = VS.WA.set({"wa_id": GUEST, "message_id": "SM383turn"})
        try:
            with mock.patch.object(VS, "whatsapp_switch", switch):
                asyncio.run(SPC.set_space(self.ch["account_id"], "relocation", "whatsapp"))
                asyncio.run(SPC.set_space(self.ch["account_id"], "relocation", "whatsapp"))   # unchanged
                asyncio.run(SPC.conversation_switched("relocate"))                          # the same product on the same message
        finally:
            VS.WA.reset(tok)
        self.assertEqual(called, [(GUEST, "relocation", "SM383turn")])

    def test_a_message_that_switches_nothing_calls_nothing(self):
        for i, body in enumerate(("book dinner tonight in Madrid for 2 at 21:00", "ad hoc question about my trip", "thanks")):
            self.assertEqual(self.switches(self.webhook({"Body": body}, f"SM383none{i}")), [], body)

    def test_the_proof_sequence(self):
        """Tyler's proof: "diligence" → a Sampo question (AD's) → "Sasha" → the dinner request: two switches, each once."""
        seq = [({"Body": "diligence"}, True), ({"Body": "what's the status of the Sampo case?"}, True), ({"Body": "Sasha"}, False),
               ({"Body": "Please make me a dinner reservation tomorrow night for two at La Taberna de Peñalver at 21:00"}, False)]
        got = []
        for i, (f, takes) in enumerate(seq):
            got += self.switches(self.webhook(f, f"SM383p{i}", agapi_takes=takes))
        self.assertEqual(got, [(GUEST, "diligence", "SM383p0"), (GUEST, "travel", "SM383p2")])


class OnePlace(unittest.TestCase):
    def test_one_writer(self):
        """Only products.space.conversation_switched calls VS.whatsapp_switch; the webhook and set_space call it."""
        hits = []
        for f in BACKEND.rglob("*.py"):
            rel = f.relative_to(BACKEND).as_posix()
            if rel.startswith(("tests/", "venv/", ".venv/")) or rel == "agapi/venue_submit.py":
                continue
            if "whatsapp_switch(" in f.read_text(errors="ignore"):
                hits.append(rel)
        self.assertEqual(hits, ["products/space.py"])
        self.assertIn("conversation_switched(s)", inspect.getsource(SPC.set_space))
        self.assertIn("SPC.conversation_switched(to)", inspect.getsource(IP._sms))
        self.assertIn("OP.MESSAGES_WHATSAPP_SWITCH", inspect.getsource(VS.whatsapp_switch))

    def test_no_whatsapp_door_no_call(self):
        called = []

        async def switch(*a):
            called.append(a)
        with mock.patch.object(VS, "whatsapp_switch", switch):
            asyncio.run(SPC.conversation_switched("campus"))                    # a web switch: no WhatsApp message, nothing told
        self.assertEqual(called, [])

    def test_the_registry_recognises_only(self):
        self.assertEqual([TL.switched_to(p) for p in ({"Body": "Sasha"}, {"Body": "book dinner"}, {"Body": "ad hoc"})],
                         ["travel", None, None])


if __name__ == "__main__":
    unittest.main()
