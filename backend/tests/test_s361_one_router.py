"""Sasha 361 · ONE PRODUCT ROUTER decides which product every WhatsApp message is for (Sasha · AD · later others) — Tyler, 9 Nov: the router
lives in Sasha, in the registry the Menu reads (products/tools.py).

Found (EU 282 N7, mailbox 1848): 9 Nov 14:04:36Z "do 1-3 on Halfords" from an AD user with an open case was answered by Sasha ("Who's
going?") — the old router read word lists (_INVESTIGATION, _DD, _CASE, _CLAIMS, for_sasha) and current_space = "sasha"; neither matched AD.

The order, over the number's ROLES (Sasha's: her own; AD's: AgAPI's inbound conversation_role, passed through — AgAPI decides nothing):
  an explicit keyword or a Menu tap wins → else the product the person last CHOSE (the router's own record, written only by a keyword or a
  tap) → else, a number with both, ONE question with buttons. A Sasha-only number is unaffected.

    cd backend && python -m unittest tests.test_s361_one_router -v
"""
from __future__ import annotations

import pathlib
import re
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW
from products import tools as TL
from tests import test_inbound_phone as TIP
from tests.test_guest_whatsapp_s75 import ACCOUNT, GUEST, SANDBOX, Base, run

ROOT = pathlib.Path(__file__).resolve().parents[1]
AD_USER = {"resolved": True, "reason": "one", "role": {"kind": "ad_user"}, "roles": [{"kind": "ad_user"}]}
NOBODY_AT_AD = {"resolved": False, "reason": "none", "role": None, "roles": []}


class TheRule(unittest.TestCase):
    def test_keyword_then_last_choice_then_ask(self):
        self.assertEqual(TL.route("diligence do 1-3 on Halfords", NOBODY_AT_AD, None), ("diligence", "diligence"))   # a keyword wins, always
        self.assertEqual(TL.route("do 1-3 on Halfords", NOBODY_AT_AD, None), ("sasha", None))                 # a Sasha-only number: Sasha's
        self.assertEqual(TL.route("do 1-3 on Halfords", None, "diligence"), ("diligence", "diligence"))       # their choice holds, whatever AgAPI said
        self.assertEqual(TL.route("do 1-3 on Halfords", None, None), ("sasha", None))                         # AgAPI said nothing: Sasha's
        self.assertEqual(TL.route("do 1-3 on Halfords", AD_USER, None), ("ask", None))                        # both, never chosen: ASK
        self.assertEqual(TL.route("do 1-3 on Halfords", AD_USER, "diligence"), ("diligence", "diligence"))    # the last choice
        self.assertEqual(TL.route("a table for two tonight", AD_USER, "diligence"), ("diligence", "diligence"))   # never by its words
        self.assertEqual(TL.route("sasha", AD_USER, "diligence"), ("sasha", "sasha"))                         # her word: chosen
        self.assertEqual(TL.route("campus", AD_USER, "diligence"), ("sasha", "sasha"))                        # Sasha's own tools are hers
        self.assertEqual(TL.route("Diligence", AD_USER, "sasha"), ("diligence", "diligence"))

    def test_the_question_is_the_registrys(self):
        q, buttons = TL.ask_which()
        self.assertEqual(buttons, [(TL.title(TL.BY_ID["diligence"]), TL.TOOL_ID + "diligence"), (TL.title(TL.BY_ID["travel"]), TL.TOOL_ID + "travel")])
        self.assertTrue(q.endswith("?"))


class ThroughTheWebhook(Base):
    """The real webhook; AgAPI's inbound stood in: its conversation_role passed through, and AD's door (space=diligence) recording."""

    def setUp(self):
        super().setUp()
        TIP.InboundPhone.setUp(self)
        self.turns, self.to_ad, self.brain_saw = [], [], []
        GW._spawn = lambda coro: self.turns.append(coro)
        self.role = NOBODY_AT_AD

        async def inbound(sender, body, message_id=None, guest=False, twilio=None, **kw):
            if kw.get("space") == "diligence":
                self.to_ad.append(body)
                return {"matched": True, "ad": "answered", "replied": True}
            return {"matched": False, "why": "a guest of the product", "conversation_role": self.role}

        async def brain(ch, body, payload, st, out, now, button_text="", voice_in=False):
            self.brain_saw.append(body)
            out.text(f"agent: {body}")
            return "x"
        from booking_signer import wa_agent as WA
        self.p = [mock.patch("agapi.venue_submit.whatsapp_inbound", inbound), mock.patch.object(WA, "agent_turn", brain)]
        for x in self.p:
            x.start()
        self.link()
        self.n = 0

    def tearDown(self):
        for x in reversed(self.p):
            x.stop()
        TIP.InboundPhone.tearDown(self)
        super().tearDown()

    def msg(self, body, payload=""):
        self.n += 1
        form = {"MessageSid": "SM" + f"{self.n:032x}", "From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "Body": body}
        if payload:
            form["ButtonPayload"] = payload
        self.c.post("/api/booking/twilio/sms", data=form, headers={"X-Twilio-Signature": TIP.sign("sms", form)})
        while self.turns:
            run(self.turns.pop(0))

    def asked(self):
        return [c for c, b in GW.SENDER.contents if TL.ask_which()[0] in c]

    def test_a_sasha_only_number_is_unaffected(self):
        self.msg("do 1-3 on Halfords")
        self.assertEqual((self.brain_saw, self.to_ad), (["do 1-3 on Halfords"], []))

    def test_both_never_chosen_asks_then_the_tap_carries_on_at_ad(self):
        self.role = AD_USER
        self.msg("do 1-3 on Halfords")
        self.assertEqual((self.brain_saw, self.to_ad), ([], []))                          # nobody guessed: the ONE question
        self.assertEqual(len(self.asked()), 1)
        self.msg(TL.title(TL.BY_ID["diligence"]), payload=TL.TOOL_ID + "diligence")   # the tap
        self.assertEqual(self.to_ad, ["do 1-3 on Halfords"])                           # his words, as he sent them, to AD
        self.msg("and 4 as well")                                                      # AD carries on: his choice
        self.assertEqual(self.to_ad, ["do 1-3 on Halfords", "and 4 as well"])
        self.assertEqual(self.brain_saw, [])                                           # never Sasha's brain (nor her group tools)

    def test_an_ad_user_who_chose_ad_hours_ago_reaches_ad(self):
        self.role = AD_USER
        self.msg("diligence")                                                          # chose AD (the keyword) …
        self.now = self.now.replace(hour=self.now.hour + 5)                            # … hours of silence
        self.msg("do 1-3 on Halfords")
        self.assertEqual((self.to_ad, self.brain_saw), (["do 1-3 on Halfords"], []))
        self.msg("sasha")                                                              # her word: Sasha chosen
        self.msg("a table for two tonight")
        self.assertEqual(self.brain_saw[-1], "a table for two tonight")
        self.assertEqual(self.to_ad, ["do 1-3 on Halfords"])


class OneSource(unittest.TestCase):
    def test_no_other_path_picks_the_product(self):
        """Whole class: the old router and its sources are gone — word lists, the 15-minute window, the space and the pending question as
        sources; the router's record is written only by route() (a keyword or a tap)."""
        self.assertFalse((ROOT / "products" / "router.py").exists())
        hits = []
        for d in ("products", "booking_signer", "agapi"):
            for f in sorted((ROOT / d).rglob("*.py")):
                s = f.read_text(encoding="utf-8", errors="ignore")
                for word in (r"\b_INVESTIGATION\b", r"\bAD_TURN\b", r"\bad_at\b", r"\broute_ask\b", r"\bRT\.decide\b",
                             r"from \. import router\b", r"products import router\b"):
                    if re.search(word, s):
                        hits.append(f"{f.relative_to(ROOT)}: {word}")
                if f.name != "tools.py" and re.search(r"set_agent_state\([^)]*\bchose\b", s):
                    hits.append(f"{f.relative_to(ROOT)}: writes the router's record")
        self.assertEqual(hits, [])
        pt = (ROOT / "products" / "whatsapp.py").read_text()
        self.assertIn("TL.route(", pt)
        self.assertNotIn('("diligence", _DILIGENCE)', pt)                                # AD's keyword is the router's, not a product loop's


if __name__ == "__main__":
    unittest.main()
