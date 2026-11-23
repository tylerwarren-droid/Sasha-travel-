"""Sasha 395 (1) · 388's class on S2 · ONE inbound = ONE answer: each card drawn once, whatever tools ran.

Measured (394's proof, 20 Nov 15:51 UTC, the TEST organiser): "Show me the Yerevan trip" → get_trip then group_list → the trip's card
streamed TWICE. The page hid it with its own copy of a one-card rule; the conversation record kept both (drawn twice on return) and
WhatsApp's own rule (last_of_each_card) covered only a list of kinds.

THE ROOT: ONE rule of what a card is (sasha.card_key) and of one answer's cards (sasha.one_per_card) — the turn's stream draws each card
once (an identical one is not drawn again; a newer one carries the same `card` key and replaces it in place on the page), the record keeps
one per card, WhatsApp draws one per card, and the page replaces by the server's key.

    cd backend && python -m unittest tests.test_s395_one_answer_s2 -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import unittest
from datetime import datetime
from unittest import mock

import app.services.llm as LLM
from agapi import v0 as API
from app.agent import sasha as AG
from app.agent.fakes import Block, client
from booking_signer import guest_whatsapp as GW, wa_agent as WA

ACCOUNT = "00000000-0000-4000-8000-000000000395"
CARD = {"title": "Lusa Obras Demo → Yerevan", "rows": [{"name": "Ani", "status": "booked"}], "counts": "1 booked", "link": "/group",
        "empty": None, "check": "Nothing to sort on this trip that I could check; 4 not checked yet.", "todos": [], "say": "The master list: 1 booked."}


def turn(results):
    async def call(ctx, name, args):
        r = results.get(name, {"ok": True, "result": {}})
        ctx.calls.append({"tool": name, "ok": r["ok"]})
        return r

    async def go():
        return [ev async for ev in AG.turn(ACCOUNT, "Show me the Yerevan trip", [], f"s395-{datetime.now().timestamp()}", surface="s2")]
    steps = [[Block(type="tool_use", id="t1", name="get_trip", input={})],
             [Block(type="tool_use", id="t2", name="group_list", input={})],
             [Block(type="text", text="Here's the Yerevan trip.")]]
    with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call), \
            mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "on"}):
        return asyncio.run(go())


class OneCardPerAnswer(unittest.TestCase):
    def test_the_measured_turn_draws_the_trip_card_once(self):
        same = {"ok": True, "result": {"card": CARD, "say": CARD["say"], "people": 1, "page": "/group"}}
        evs = turn({"get_trip": same, "group_list": same})
        cards = [e for e in evs if e.get("type") == "render" and e.get("kind") == "group_list"]
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["card_key"], "group_list")   # Sasha 402 · its own field

    def test_a_newer_card_replaces_it_in_place(self):
        newer = {**CARD, "counts": "2 booked"}
        evs = turn({"get_trip": {"ok": True, "result": {"card": CARD, "say": "x"}}, "group_list": {"ok": True, "result": {"card": newer, "say": "x"}}})
        cards = [e for e in evs if e.get("type") == "render" and e.get("kind") == "group_list"]
        self.assertEqual({e["card_key"] for e in cards}, {"group_list"})                         # ONE card: the page replaces by its key
        self.assertEqual(AG.one_per_card(cards)[0]["counts"], "2 booked")                    # as it stands at the end

    def test_every_card_kind_twice_is_one_card_in_the_record_and_on_whatsapp(self):
        kinds = sorted({k for k in AG.RENDER.values() if k not in ("inline",)})
        evs = [{"kind": k, "title": "t", "n": i} for i in (1, 2) for k in kinds] + [{"kind": "options", "title": "a"}, {"kind": "options", "title": "b"}]
        one = AG.one_per_card(evs)
        self.assertEqual(len(one), len(kinds) + 2)                                            # each kind once; option lists apart by title
        self.assertTrue(all(e.get("n") == 2 for e in one if "n" in e))                        # the last of each
        self.assertEqual(WA.last_of_each_card(evs), one)                                      # WhatsApp: the SAME rule

    def test_one_rule(self):
        self.assertIn("AG.one_per_card(renders)", inspect.getsource(WA.last_of_each_card))
        self.assertFalse(hasattr(WA, "CARD_KINDS"))                                           # no list of kinds of its own
        src = inspect.getsource(AG)
        self.assertIn('seen["payload"] = one_per_card(', src)                               # the record: one per card
        page = (__import__("pathlib").Path(__file__).resolve().parents[2] / "frontend/app/s2/S2App.tsx").read_text()
        self.assertIn("typeof ev.card_key === 'string'", page)                                 # the page replaces by the server's key (Sasha 402)


if __name__ == "__main__":
    unittest.main()
