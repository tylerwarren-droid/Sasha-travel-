"""Sasha 225 · /s2's front-of-house, honestly: the capability card names only what /s2's tools do; anything else is "not yet",
noted MASKED for the founder; /next is unchanged. Offline.

    cd backend && python -m unittest tests.test_s2_225 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from agapi import s2_home as HOME, v0 as API

ACCOUNT = "00000000-0000-4000-8000-000000000225"
run = asyncio.run


class Honest(unittest.TestCase):
    def test_every_capability_is_a_tool_s2_has(self):
        from app.agent import s2 as S2
        from agapi import s2_fine_print as FP, s2_subscriptions as SUBS
        own = set(FP.TOOL_NAMES) | {t["name"] for t in SUBS.TOOLS}   # /s2's own tools (run in sasha.py's /s2 block)
        for g in HOME.CAPABILITIES:
            for line, tool in g["items"]:
                self.assertTrue(tool in own or (tool in S2.S2_TOOLS and tool in API.BY_NAME), line)
        self.assertEqual([g["group"] for g in HOME.CAPABILITIES], ["Book", "Plan", "Money", "Messages", "Your documents", "Your bookings",
                                                                   "Trips", "Cards & cover", "If something goes wrong", "Money back",
                                                                   "Subscriptions"])

    def test_subscriptions_are_claimed_because_a_tool_does_it(self):   # Sasha 236 · cancel_subscription exists (CR 72): a "can", not a "not yet"
        from agapi import s2_subscriptions as SUBS
        from app.agent import s2 as S2
        self.assertIn("cancel_subscription", {t["name"] for t in SUBS.TOOLS})
        self.assertIn("cancel subscriptions", HOME.SAY)
        self.assertNotIn("cancelling a subscription", S2.S2_WHO)   # never in her can't-do examples

    def test_every_tool_s2_has_is_on_the_card(self):   # Sasha 236 · what she says she can do matches the real tool list
        lines = {t for g in HOME.CAPABILITIES for _, t in g["items"]}
        for tool in ("my_plans", "change_booking", "running_late", "hotel_request", "entry_documents", "which_card", "rental_cover",
                     "accident", "file_claim", "flight_money_back", "bag_money_back", "find_subscriptions", "cancel_subscription"):
            self.assertIn(tool, lines)

    def test_the_card_renders(self):
        from app.agent import sasha as AG
        res = run(HOME.what_i_can_do(API.Ctx(account=ACCOUNT, surface="s2"), {}))
        ev = AG.render("what_i_can_do", res, {})
        self.assertEqual(ev["kind"], "capabilities")
        self.assertEqual(ev["groups"][0]["group"], "Book")

    def test_s2_persona_never_promises_a_reminder_it_cant_send(self):   # Sasha 227 · found live: "I'll remind you as those dates get close"
        from app.agent import s2 as S2
        self.assertIn("She never says she'll remind them", S2.S2_WHO)

    def test_s2_persona_tries_first_and_never_pretends(self):   # Sasha 268 · item 7: was "I can't do that yet, but I've noted it" first
        from app.agent import s2 as S2
        self.assertNotIn("I can't do that yet, but I've noted it", S2.S2_WHO)
        self.assertIn('she says "Let me see what I can do" and does it', S2.S2_WHO)
        self.assertIn("never pretends", S2.S2_WHO)


class NotYet(unittest.TestCase):
    def setUp(self):
        HOME._MEM.clear()

    def test_masked_and_kept(self):
        with mock.patch.object(HOME, "RUN", None), mock.patch("booking_signer.plan_store._run", lambda: None):
            tried = API.Ctx(account=ACCOUNT, surface="s2", calls=[{"tool": "search_venues", "ok": False}])   # 268: only after a try
            out = run(HOME.note_not_yet(tried,
                                        {"asked": "cancel my Netflix, card 4111 1111 1111 1111, email me at ana@x.com or +34 600 123 456"}))
        self.assertTrue(out["noted"])
        row = HOME._MEM[-1]
        self.assertNotIn("4111", row["asked"])
        self.assertNotIn("ana@x.com", row["asked"])
        self.assertNotIn("600", row["asked"])
        self.assertIn("cancel my Netflix", row["asked"])
        self.assertNotIn(ACCOUNT, row["who"])


class NextIsUnchanged(unittest.TestCase):
    def tools_for(self, surface):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        from app.agent.fakes import Block, client
        seen = []

        async def go():
            async for _ in AG.turn(ACCOUNT, "what can you do?", [], f"s225-{surface}", None, surface):
                pass
        with mock.patch.object(LLM, "client", client([[Block(type="text", text="Lots.")]], seen=seen)):
            run(go())
        return [t["name"] for t in seen[0]["tools"]]

    @mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "off"})   # Sasha 241 · the old S1, exactly, behind its way-back switch
    def test_only_s2_has_them(self):
        s1, s2 = self.tools_for("s1"), self.tools_for("s2")
        self.assertFalse({"what_i_can_do", "note_not_yet"} & set(s1))
        self.assertEqual(s1, [t["name"] for t in API.TOOLS])
        self.assertTrue({"what_i_can_do", "note_not_yet"} <= set(s2))


if __name__ == "__main__":
    unittest.main()
