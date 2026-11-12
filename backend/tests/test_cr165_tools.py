"""CR 165 · KANOE'S TOOLS ON WHATSAPP — ONE registry (products/tools.py) read by the welcome, the switch, the Menu on every reply and the
hints; a menu inside each tool with "← All tools" first; no sentence ever tells someone to "say" another tool's word or "send link"."""
from __future__ import annotations

import pathlib
import re
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW
from products import tools as TL, whatsapp as PW
from tests.test_guest_whatsapp_s75 import Base, FakeSender, GUEST, SANDBOX, run

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ListSender(FakeSender):
    def __init__(self):
        super().__init__()
        self.lists = []

    async def list_picker(self, body, button, rows):
        self.lists.append({"body": body, "button": button, "rows": rows})
        return f"HXlist{len(self.lists)}"

    async def send(self, frm, to, *, body="", media=None, content_sid=None, **kw):
        if content_sid and content_sid.startswith("HXlist"):
            body = self.lists[int(content_sid[6:]) - 1]["body"]
        return await super().send(frm, to, body=body, media=media)


class TheRegistry(unittest.TestCase):
    def test_one_entry_per_tool_and_the_switch_knows_each_word(self):
        self.assertEqual([TL.title(t) for t in TL.TOOLS], ["✈️ Travel", "🔍 Due diligence", "🇪🇸 España", "🏠 Relocation", "🎓 Campus visits"])
        for t in TL.TOOLS:
            if t["product"]:
                self.assertTrue(PW._KEYWORD[t["product"]].match(t["word"]), t["word"])   # the ONE keyword switch opens it
            else:
                self.assertTrue(PW._EXIT.match(t["word"]))                                # travel: Sasha's own word
        self.assertEqual(TL.BACK["id"], "kanoe:tools")   # the contract with AgAPI's ad_menu.BACK (AD's menu, first row)

    def test_only_switched_on_tools_are_listed(self):
        with mock.patch.dict("os.environ", {"KANOE_TOOLS_OFF": "campus,espana"}):
            self.assertEqual([r[0] for r in TL.tools_rows()], ["✈️ Travel", "🔍 Due diligence", "🏠 Relocation"])

    def test_taps(self):
        self.assertEqual(TL.tapped("← Everything I can do", "kanoe:tools"), ("tools", None))
        self.assertEqual(TL.tapped("", "kanoe:tool:diligence")[1]["word"], "diligence")
        self.assertEqual(TL.tapped("🎓 Campus visits", "")[1]["id"], "campus")
        self.assertEqual(TL.tapped("x", "kanoe:say:Book dinner"), ("say", "Book dinner"))
        self.assertIsNone(TL.tapped("dinner for two", ""))


class TheMenuOnEveryReply(unittest.TestCase):
    def out(self, space, *items):
        o = GW.Out()
        o.items = list(items)
        o.space = lambda: space
        GW._with_menu(o)
        return o.items[-1]

    def test_top_level_lists_the_tools(self):
        it = self.out(None, ("text", "Hello"))
        self.assertEqual((it[0], it[1], it[2]), ("list", "Hello", "Menu"))
        self.assertEqual([r[0] for r in it[3]][:5], ["✈️ Travel", "🔍 Due diligence", "🇪🇸 España", "🏠 Relocation", "🎓 Campus visits"])

    def test_inside_a_tool_its_menu_with_all_tools_first(self):
        it = self.out("campus", ("text", "Which universities?"))
        self.assertEqual(it[3][0], ("← Everything I can do", TL.BACK["description"], "kanoe:tools"))
        self.assertIn("start over campus", it[3][1][2])

    def test_a_turn_ending_on_its_own_buttons_keeps_them(self):
        it = self.out(None, ("ask", "Book it?", [("Yes", "y"), ("No", "n")]))
        self.assertEqual(it[0], "ask")


class OnWhatsApp(Base):
    def setUp(self):
        super().setUp()
        GW.SENDER = ListSender()

    def test_all_tools_tap_shows_the_tools(self):
        self.link()
        self.say("← Everything I can do", payload="kanoe:tools")
        self.assertTrue(GW.SENDER.lists[-1]["body"].startswith(TL.CAN))
        self.assertEqual([r[2] for r in GW.SENDER.lists[-1]["rows"]], [TL.TOOL_ID + t["id"] for t in TL.TOOLS])

    # Sasha 379b · test_a_tool_tap_enters_it_through_the_one_switch retired: AD's row reaches AgAPI's ONE call as AD's word, with the
    # guest's email (tests.test_s379b_one_decision) — never AD's space

    def test_a_new_number_gets_the_welcome_and_the_tools_as_taps(self):
        async def not_a_venue(_):
            return False
        r = run(GW.dispatch({"From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "Body": "hi", "MessageSid": "SMnew"}, not_a_venue))
        self.assertEqual(r, "")
        self.assertTrue(GW.SENDER.lists[-1]["body"].startswith(TL.WELCOME))
        self.assertEqual(len(GW.SENDER.lists[-1]["rows"]), len(TL.TOOLS))
        r = run(GW.dispatch({"From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "Body": "🔍 Diligence",
                             "ButtonPayload": "kanoe:tool:diligence", "MessageSid": "SMnew2"}, not_a_venue))
        self.assertIn("To use 🔍 Due diligence here, link this number to your Kanoe account once at", r)


class NoSecondWay(unittest.TestCase):
    """Root test: no reply text names another tool's keyword ("say “sasha”") or asks to "send link" — the Menu is always there instead."""

    def test_no_say_sasha_no_send_link(self):
        bad = re.compile(r"(?i)say\s+[“\"'‘]?(sasha|diligence|campus|relocat\w*|espa[ñn]a)\b|send\s+[“\"'‘]?link\b|\blink\s+<\w")
        hits = []
        for d in ("products", "booking_signer", "agapi", "app"):
            for f in sorted((ROOT / d).rglob("*.py")):
                for i, line in enumerate(f.read_text().splitlines(), 1):
                    if bad.search(line) and not line.lstrip().startswith("#") and "CR 165" not in line:
                        hits.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()[:110]}")
        self.assertEqual(hits, [])
