"""Sasha 356 · every message's header is composed in ONE place (booking_signer/switching.compose, called in guest_whatsapp._send — every
outbound message). Tyler, 7 Nov 06:57: "Sasha · ✈️ Travel — where would you like to go?" came TWICE in one message (italic + plain).

    cd backend && python -m unittest tests.test_s356_one_header -v
"""
from __future__ import annotations

import pathlib
import re
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW, switching as SW
from products import tools as TL
from tests.test_cr165_tools import ListSender
from tests.test_guest_whatsapp_s75 import Base

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADER = re.compile(r"Sasha · |Now: ")


def headers(body: str) -> int:
    return len(HEADER.findall(body or ""))


class TheComposer(unittest.TestCase):
    def test_once_at_the_top_whatever_was_declared(self):
        out = GW.Out().text("Kept — everything you've given me stays.")
        out.header = ("space", None, True)
        SW.compose(out); SW.compose(out)                                                  # composed twice: still one header
        self.assertEqual(out.items[0][1], "_Sasha · ✈️ Travel — where would you like to go?_\nKept — everything you've given me stays.")
        bare = GW.Out()
        bare.header = ("space", None, True, True)
        SW.compose(bare)                                                                  # the header IS the message (the tool asks)
        self.assertEqual(bare.items, [("text", "_Sasha · ✈️ Travel — where would you like to go?_")])
        quiet = GW.Out()
        quiet.header = ("space", "diligence", False)
        SW.compose(quiet)                                                                 # nothing of its own (AgAPI answers): no message
        self.assertEqual(quiet.items, [])
        old = GW.Out().text("_Sasha · 🎓 Campus visits_\nWhich universities?")              # a header already on the text (an older reply)
        old.header = ("space", "campus", False)
        SW.compose(old)
        self.assertEqual(headers(old.items[0][1]), 1)


class Bodies(ListSender):
    """Every message's words as the person reads them — a list's, AND a message with buttons (quick_reply), whose words go in its content."""

    async def send(self, frm, to, *, body="", media=None, content_sid=None, **kw):
        if content_sid and content_sid.startswith("HX") and not content_sid.startswith("HXlist"):
            body = self.contents[int(content_sid[2:]) - 1][0]
        return await super().send(frm, to, body=body, media=media, content_sid=content_sid)


class OnWhatsAppEveryTool(Base):
    """Every switch (each tool from the Menu, and back to Travel), the welcome and the "Kept" hand-off: each message ONE header at most."""

    def setUp(self):
        super().setUp()
        GW.SENDER = Bodies()
        self.p = [mock.patch.dict("os.environ", {"SASHA_SWITCHING": "all"}),
                  mock.patch("agapi.venue_submit.whatsapp_inbound", mock.AsyncMock(return_value={"matched": True, "ad": "not_linked", "replied": True}))]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in reversed(self.p):
            x.stop()
        super().tearDown()

    def test_each_header_once(self):
        self.link()
        for t in TL.TOOLS:
            if t["product"] and TL.product_of(t) == "sasha":   # Sasha 379b · AD's row is AgAPI's to take on the first call (CR 192)
                self.say(TL.title(t), payload=TL.TOOL_ID + t["id"])                         # into the tool from the Menu
            self.say(TL.title(TL.BY_ID["travel"]), payload=TL.TOOL_ID + "travel")            # back to Travel
        self.say("Campus visits", payload=TL.TOOL_ID + "campus")
        self.say("later")                                                                  # "Kept — …": a hand-off back to Travel
        sent = [s["body"] for s in GW.SENDER.sent]
        self.assertTrue(sent)
        twice = [b for b in sent if headers(b) > 1]
        self.assertEqual(twice, [], "a message carried two headers")
        again = []                                                                         # one level in (Tyler, 7 Nov 08:03): the body under
        for b in sent:                                                                     # the header never re-states its tool or question
            head, _, rest = b.partition("\n")
            for t in TL.TOOLS:
                if f"Sasha · {TL.title(t)}" in head and (TL.title(t) in rest or t["ask"] in rest):
                    again.append(b[:120])
        self.assertEqual(again, [], "a tool's body re-stated the header's tool or question")
        travel = [b for b in sent if "Sasha · ✈️ Travel" in b]
        self.assertTrue(travel)                                                            # the Travel switch says its header…
        for b in sent:
            if headers(b):
                self.assertTrue(b.startswith("_Sasha · ") or b.startswith("_Now: "), b[:80])   # …once, at the top, composed


class NoOtherWriter(unittest.TestCase):
    """Whole class: no outbound text is written with a header in it — only the composer writes one."""

    def test_only_the_composer_writes_a_header(self):
        hits = []
        for d in ("products", "booking_signer"):
            for f in sorted((ROOT / d).rglob("*.py")):
                if f.name == "switching.py":
                    continue
                for i, line in enumerate(f.read_text().splitlines(), 1):
                    code = line.split("#", 1)[0]
                    if re.search(r"\.(text|ask|pick)\([^)]*(space_line|space_label|Sasha · |_Now: )", code):
                        hits.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()[:110]}")
        self.assertEqual(hits, [])

    def test_no_tool_writes_its_own_identity_or_question(self):
        """One level in (Tyler, 7 Nov 08:03): a tool's greeting never re-states the registry's identity ("🇪🇸 España — …") or question."""
        names = "|".join(re.escape(TL.title(t)) + r"\s+—" for t in TL.TOOLS)            # a string that opens with a tool's identity
        asks = "|".join(re.escape(t["ask"]) for t in TL.TOOLS)                             # or carries a tool's question anywhere
        said = re.compile(r"""["'](?:%s)|["'][^"'\n]*(?:%s)""" % (names, asks))
        hits = []
        for d in ("products", "booking_signer"):
            for f in sorted((ROOT / d).rglob("*.py")):
                if f.name in ("switching.py", "tools.py"):                                  # the composer and the ONE registry
                    continue
                for i, line in enumerate(f.read_text().splitlines(), 1):
                    if said.search(line.split("#", 1)[0]):
                        hits.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()[:110]}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
