"""Sasha 241 · S1 PARITY (Tyler's OK, 11 Oct; EU 232 §2.0): /next keeps ALL its own tools, its "Who she is" and its trip flow, and
gains S2's tools, wrappers, the Keep for every signed-in account, its capability lines (cached), memory + closing, the shared cards
and its 📎 photos. SASHA_S1_PARITY=off is the way back (the old S1 tests run under it). Offline.

    cd backend && python -m unittest tests.test_s1_241 -v
"""
from __future__ import annotations

import asyncio
import base64
import os
import unittest
from unittest import mock

from agapi import v0 as API

ACCT = "00000000-0000-4000-8000-000000000241"
run = asyncio.run
FRONT = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


def seen_by_model(surface: str):
    import app.services.llm as LLM
    from app.agent import sasha as AG
    from app.agent.fakes import Block, client
    seen = []

    async def go():
        async for _ in AG.turn(ACCT, "hello", [], f"s241-{surface}", None, surface):
            pass
    with mock.patch.object(LLM, "client", client([[Block(type="text", text="Hi.")]], seen=seen)), \
            mock.patch("app.services.chat_account.signed_in", lambda a: True):
        run(go())
    return seen[0]


class Parity(unittest.TestCase):
    def test_s1_keeps_all_its_tools_and_gains_s2s(self):
        from app.agent import sasha as AG
        names = [t["name"] for t in seen_by_model("s1")["tools"]]
        self.assertTrue({t["name"] for t in AG.tools_for_model()} <= set(names))                 # nothing of S1's removed
        for n in ("what_i_can_do", "my_plans", "running_late", "hotel_request", "find_subscriptions", "cancel_subscription",
                  "suggest_activities", "entry_documents", "flight_money_back", "bag_money_back", "keep_list", "keep_add"):
            self.assertIn(n, names)
        self.assertEqual(len(names), len(set(names)))                                           # each tool once

    def test_s1_keeps_its_own_who_she_is_and_gains_the_capability_lines_cached(self):
        from app.agent import s2 as S2
        from app.services import persona as P
        sysm = seen_by_model("s1")["system"]
        self.assertTrue(sysm[0]["text"].startswith(P.AGENT_SYSTEM))                             # S1's own persona, first
        self.assertIn(S2.S1_CAN, sysm[0]["text"])
        self.assertEqual(sysm[0].get("cache_control"), {"type": "ephemeral"})                   # in the CACHED part: S1's speed kept
        self.assertNotIn("cancelling a subscription", S2.S1_CAN)

    def test_s1_book_keeps_its_own_words(self):
        tools = {t["name"]: t for t in seen_by_model("s1")["tools"]}
        from app.agent import sasha as AG
        self.assertEqual(tools["book"]["description"], next(t for t in AG.tools_for_model() if t["name"] == "book")["description"])

    @mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "off"})
    def test_off_is_the_old_s1(self):
        from app.agent import sasha as AG
        from app.services import persona as P
        s = seen_by_model("s1")
        self.assertEqual(s["system"][0]["text"], P.AGENT_SYSTEM)
        self.assertNotIn("what_i_can_do", [t["name"] for t in s["tools"]])


class Photos(unittest.TestCase):
    def setUp(self):
        from app.agent import sasha as AG
        AG._PHOTO_SCAN.clear()

    def test_a_passport_photo_is_read_masked_and_saved_on_a_later_yes(self):
        from agapi import keep_scan as SCAN
        from app.agent import sasha as AG
        saved = []

        async def scan(account, kind, raw, mime):
            return {"token": "t1", "kind": kind, "masked": "Passport ES ••••456", "shown": ["Passport ES ••••456", "Expires 2031-05"]}

        async def confirm(account, token):
            saved.append(token)
            return {"item": "Passport ES ••••456"}
        photo = [{"media_type": "image/jpeg", "content_base64": base64.b64encode(b"jpeg").decode()}]
        with mock.patch.object(SCAN, "scan", scan), mock.patch.object(SCAN, "confirm", confirm):
            said, _ = run(AG._photo_turn(ACCT, photo, "my passport"))
            self.assertIn("Passport ES ••••456", said)
            self.assertIn("save it to your Keep?", said)
            said, _ = run(AG._photo_turn(ACCT, [], "Yes"))
        self.assertEqual(saved, ["t1"])
        self.assertIn("Saved to your Keep: Passport ES ••••456", said)

    def test_a_statement_goes_to_subscriptions_then_the_model(self):
        from agapi import s2_subscriptions as SUBS
        from app.agent import sasha as AG
        photo = [{"media_type": "image/jpeg", "content_base64": base64.b64encode(b"x").decode()}]
        with mock.patch.object(SUBS, "keep_statement", lambda a, raw, mime: "st_1"):
            said, msg = run(AG._photo_turn(ACCT, photo, "my bank statement"))
        self.assertIsNone(said)
        self.assertIn("statement_ref st_1", msg)

    def test_no_word_asks_what_it_is(self):
        from app.agent import sasha as AG
        said, _ = run(AG._photo_turn(ACCT, [{"media_type": "image/jpeg", "content_base64": base64.b64encode(b"x").decode()}], "📷 (photo)"))
        self.assertIn("what is it", said)


class Wiring(unittest.TestCase):
    def test_memory_and_closing_on_next(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "app", "agent", "sasha.py")).read()
        self.assertIn('remembers = surface == "s2" or s1_parity()', src)
        self.assertIn('@router.get("/memory")', src)

    @unittest.skipUnless(os.path.exists(FRONT), "the frontend isn't beside the backend here")
    def test_next_draws_the_shared_cards_and_sends_its_photos(self):
        from app.agent import sasha as AG
        chat = open(os.path.join(FRONT, "app", "components", "SashaChat.tsx"), encoding="utf-8").read()
        cards = open(os.path.join(FRONT, "app", "components", "cards", "S2Cards.tsx"), encoding="utf-8").read()
        self.assertIn("<SharedCard", chat)
        self.assertIn("photos: media.map(", chat)
        self.assertIn("/api/sasha-agent/memory", chat)
        for k in AG.KINDS_S2_ONLY:                                                                # every /s2-only card, on /next too
            self.assertIn(f"'{k}'", cards.split("export const SHARED_KINDS", 1)[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
