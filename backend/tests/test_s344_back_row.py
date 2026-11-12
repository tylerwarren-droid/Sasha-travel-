"""Sasha 344 · inside 🔍 Due diligence, the Menu's back row is Sasha's ONE switch — never AD's text (docs/sasha/S-344-back-row.md).
The real /twilio/sms route, a linked number in AD's space, the tap in every shape Twilio can deliver it.
    cd backend && python -m unittest tests.test_s344_back_row -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from agapi import venue_submit as VS
from booking_signer import guest_whatsapp as GW, inbound_phone as IP
from products import tools as TL
from tests.test_cr165_tools import ListSender
from tests.test_guest_whatsapp_s75 import Base, GUEST, SANDBOX

def list_reply(title, description, row_id):
    """A list-picker row tapped on WhatsApp, as Twilio's webhook carries it: Body = the title AND the description, joined (found live,
    Tyler 5 Nov 06:30: "Show my cases\nYour cases, and the status of the one you pick"); ListId / ListTitle = the row."""
    return {"Body": f"{title}\n{description}", "ListId": row_id, "ListTitle": title, "MessageType": "interactive"}


#: AD's Menu rows as AgAPI sends them (agapi ad_menu.rows() at cr/166 292b5f6: BACK first, then ABILITIES — id "ad_<id>")
AD_ROWS = [("Show my cases", "Your cases, and the status of the one you pick", "ad_cases"),
           ("Open a case", "Investigate a company", "ad_open"),
           ("Next steps", "What to do next on the case you're working on", "ad_steps")]
BACK_ROW = list_reply("← All tools", "Kanoe's tools: travel, diligence and more", "kanoe:tools")

SHAPES = {   # the back row in every shape a tap can arrive in
    "list reply (AD's real row: Body joined, ListId, ListTitle)": BACK_ROW,
    "button reply (ButtonPayload)": {"Body": "← All tools", "ButtonPayload": "kanoe:tools", "ButtonText": "← All tools", "MessageType": "button"},
    "title only (Body)": {"Body": "← Everything I can do", "MessageType": "text"},
    "AgAPI's title only (Body)": {"Body": "← All tools", "MessageType": "text"},
}


class TheBackRowAndADsRows(Base):
    def setUp(self):
        super().setUp()
        GW.SENDER = ListSender()
        self.ran = []
        GW._spawn = lambda coro: self.ran.append(coro)
        ch = self.link()
        self.ch = ch   # Sasha 379b · no "inside AD" of Sasha's: AgAPI's one call decides each message (CR 192)
        self._ack = IP.ACK_WAIT_S   # Sasha 379a · the work runs after Twilio's ack: wait for it here
        IP.ACK_WAIT_S = 30.0
        self.addCleanup(setattr, IP, "ACK_WAIT_S", self._ack)
        self.agapi_takes = True

    def webhook(self, fields, sid):
        p = {"From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "MessageSid": sid, "NumMedia": "0", "ProfileName": "Tyler",
             "WaId": GUEST.lstrip("+"), **fields}
        doors = []

        async def agapi(sender, text, **kw):   # AgAPI's inbound door — and AD's (products/diligence goes through the same op)
            doors.append(text)
            return {"matched": self.agapi_takes, "replied": True, "ad": "replied"}
        loop = asyncio.get_event_loop()
        with mock.patch.object(IP, "_verified", mock.AsyncMock(return_value=p)), mock.patch.object(VS, "whatsapp_inbound", agapi), \
                mock.patch.object(GW, "first_time", mock.AsyncMock(return_value=True)), \
                mock.patch.object(GW, "linked", mock.AsyncMock(return_value=True)):
            loop.run_until_complete(IP.sms(None))
            while self.ran:
                loop.run_until_complete(self.ran.pop(0))
        return doors

    def test_every_shape_gives_the_tools_and_never_reaches_a_door(self):
        for i, (shape, fields) in enumerate(SHAPES.items()):
            before = len(GW.SENDER.lists)
            doors = self.webhook(fields, f"SM344{i}")
            self.assertEqual(doors, [], shape)                                                     # AgAPI / AD never called
            self.assertGreater(len(GW.SENDER.lists), before, shape)
            self.assertTrue(GW.SENDER.lists[-1]["body"].startswith(TL.CAN), shape)                # the tools, Sasha's own list
            self.assertEqual([r[2] for r in GW.SENDER.lists[-1]["rows"]], [TL.TOOL_ID + t["id"] for t in TL.TOOLS], shape)

    def test_each_ad_row_reaches_ad_as_its_exact_title_never_the_joined_body(self):
        for i, (title, desc, rid) in enumerate(AD_ROWS):
            doors = self.webhook(list_reply(title, desc, rid), f"SM344ad{i}")
            self.assertEqual(doors, [title], title)                                                # the row's exact title — not "…\n<desc>"

    def test_one_door_even_when_agapi_doesnt_take_it(self):
        self.agapi_takes = False   # Sasha 379b · CR 192: AgAPI's ONE call decides — never a second door (diligence.hand_over is gone)
        for i, (title, desc, rid) in enumerate(AD_ROWS):
            doors = self.webhook(list_reply(title, desc, rid), f"SM344own{i}")
            self.assertEqual(doors, [title], title)                                               # ONE door: the exact title

    def test_an_ordinary_message_in_ads_space_still_goes_to_agapi_first(self):
        doors = self.webhook({"Body": "Show my cases", "MessageType": "text"}, "SM344x")
        self.assertEqual(doors, ["Show my cases"])


class TheOneReader(unittest.TestCase):
    def test_fields(self):
        self.assertEqual(TL.tap_fields(list_reply(*AD_ROWS[0])), ("Show my cases", "ad_cases"))
        self.assertEqual(TL.tap_fields({"Body": "Show my cases\nYour cases, and the status of the one you pick", "ListId": "ad_cases"}),
                         ("Show my cases", "ad_cases"))                                            # no ListTitle: the title line, never the joined Body
        self.assertEqual(TL.normalized(list_reply(*AD_ROWS[1]))["Body"], "Open a case")
        self.assertEqual(TL.tap_fields({"ListTitle": "← All tools", "ListId": "kanoe:tools"}), ("← All tools", "kanoe:tools"))
        self.assertEqual((TL.own_id(list_reply(*AD_ROWS[0])), TL.own_id(BACK_ROW)), ("", "kanoe:tools"))   # by namespace, never by row
        self.assertEqual(TL.switch_tap({"Body": "🔍 Due diligence", "ListId": "kanoe:tool:diligence"})[0], "tool")
        self.assertIsNone(TL.switch_tap({"Body": "Show my cases"}))
        self.assertIsNone(TL.switch_tap({"Body": "← All tools", "ListId": "ad_cases"}))       # another row's id: never matched by title

    def test_sashas_own_menu_rows_too(self):   # every tool's menu: Sasha's rows (a tool's "Start again", travel's chips) by their id
        self.assertEqual(TL.tapped(*TL.tap_fields(list_reply("Start again", "From the beginning", "kanoe:say:start over campus"))),
                         ("say", "start over campus"))
        self.assertEqual(TL.tapped(*TL.tap_fields(list_reply("🔍 Due diligence", "Companies and people", "kanoe:tool:diligence")))[1]["id"], "diligence")

    def test_no_per_tool_exception(self):
        import inspect
        src = inspect.getsource(IP.sms) + inspect.getsource(IP._sms)   # Sasha 350 · the webhook, then its body
        self.assertIn("TL.switch_tap(p)", src)
        self.assertLess(src.index("TL.switch_tap(p)"), src.index("VS.whatsapp_inbound(sender, "))   # BEFORE any door
        self.assertNotIn("diligence", inspect.getsource(TL.switch_tap))


if __name__ == "__main__":
    unittest.main()
