"""Sasha 225 · /s2's front-of-house, honestly: the capability card names only what /s2's tools do; anything else is "not yet",
noted MASKED for the founder; /next is unchanged. Offline.

    cd backend && python -m unittest tests.test_s2_225 -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from agapi import s2_home as HOME, v0 as API

ACCOUNT = "00000000-0000-4000-8000-000000000225"
run = asyncio.run


class Honest(unittest.TestCase):
    def test_every_capability_is_a_tool_s2_has(self):
        from app.agent import s2 as S2
        for g in HOME.CAPABILITIES:
            for line, tool in g["items"]:
                self.assertIn(tool, S2.S2_TOOLS, line)
                self.assertIn(tool, API.BY_NAME, line)
        self.assertEqual([g["group"] for g in HOME.CAPABILITIES], ["Book", "Plan", "Money", "Messages", "Your documents"])

    def test_nothing_about_subscriptions_is_claimed(self):   # no tool does it (yet): it's a "not yet"
        blob = " ".join([HOME.SAY] + [i for g in HOME.CAPABILITIES for i, _ in g["items"]]).lower()
        self.assertNotIn("subscri", blob)

    def test_the_card_renders(self):
        from app.agent import sasha as AG
        res = run(HOME.what_i_can_do(API.Ctx(account=ACCOUNT, surface="s2"), {}))
        ev = AG.render("what_i_can_do", res, {})
        self.assertEqual(ev["kind"], "capabilities")
        self.assertEqual(ev["groups"][0]["group"], "Book")

    def test_s2_persona_never_promises_a_reminder_it_cant_send(self):   # Sasha 227 · found live: "I'll remind you as those dates get close"
        from app.agent import s2 as S2
        self.assertIn("She never says she'll remind them", S2.S2_WHO)

    def test_s2_persona_says_not_yet_and_never_pretends(self):
        from app.agent import s2 as S2
        self.assertIn("I can't do that yet, but I've noted it", S2.S2_WHO)
        self.assertIn("never pretends", S2.S2_WHO)


class NotYet(unittest.TestCase):
    def setUp(self):
        HOME._MEM.clear()

    def test_masked_and_kept(self):
        with mock.patch.object(HOME, "RUN", None), mock.patch("booking_signer.plan_store._run", lambda: None):
            out = run(HOME.note_not_yet(API.Ctx(account=ACCOUNT, surface="s2"),
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

    def test_only_s2_has_them(self):
        s1, s2 = self.tools_for("s1"), self.tools_for("s2")
        self.assertFalse({"what_i_can_do", "note_not_yet"} & set(s1))
        self.assertEqual(s1, [t["name"] for t in API.TOOLS])
        self.assertTrue({"what_i_can_do", "note_not_yet"} <= set(s2))


if __name__ == "__main__":
    unittest.main()
