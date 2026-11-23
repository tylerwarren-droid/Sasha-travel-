"""Sasha 402 · EU 294 P1 · A CARD IS COUNTED AS DRAWN ONLY WHERE IT WAS ACTUALLY DRAWN.

Found by EU 294, verified on the real stream before the fix: sasha.py streamed {**ev, "card": key} (395's one-card key), but for flights,
stays and counter_card ev["card"] IS the payload — it became the string "flights". S2 and /next (opts(ev.card)) drew nothing; WhatsApp's
_options called .get on a string and the turn failed; and the server still counted the card as drawn (draws() looked at the KIND only),
so Sasha said the options were on screen. WhatsApp also counted kinds it maps to _nothing (kind_ask, focus, inline, discover) as drawn.

THE CLASS: every card the stream yields × every door → drawn by THAT door's own renderer on THE STREAM'S OWN EVENT (never a hand-built
one): S2 = the real cardsOf (frontend/lib/cards-of.ts, run by node), WhatsApp = the real wa_agent.render. The identity is card_key, its
own field; a payload a door can't draw is never counted as shown.

    cd backend && python -m unittest tests.test_s402_cards_drawn -v
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import shutil
import subprocess
import unittest
from unittest import mock

import app.services.llm as LLM
from agapi import v0 as API
from app.agent import sasha as AG
from app.agent.fakes import Block, client
from booking_signer import guest_whatsapp as GW, wa_agent as WA

BACKEND = pathlib.Path(__file__).resolve().parents[1]
CARDS_OF = BACKEND.parent / "frontend" / "lib" / "cards-of.ts"
ACCOUNT = "00000000-0000-4000-8000-000000000402"

FLIGHTS = {"ok": True, "result": {"party": 1, "leg": "out", "flights": [
    {"offer_id": "off_1", "airline": "Iberia", "departs": "2037-12-01T08:00", "duration_minutes": 150, "from": "MAD", "to": "LHR",
     "stops": 0, "flights": "IB3170", "price_eur": 120.0}]}}
STAYS = {"ok": True, "result": {"city": "London", "stays": [{"name": "Hotel Fictio", "stars": 4, "rating": 4.5, "reviews": 10,
                                                             "estimate_eur_per_night": 150}]}}
COUNTER = {"ok": True, "result": {"say": "Decline the collision cover.", "render": {"kind": "counter_card", "card": {
    "counter": {"decline": [{"say": "Decline the collision cover."}], "check": [], "keep": []}, "framing": "x"}}}}
NO_FLIGHTS = {"ok": True, "result": {"party": 1, "leg": "out", "flights": []}}   # a card with nothing to draw
SCRIPTS = {"search_flights": (FLIGHTS, {"origin": "Madrid", "destination": "London", "date": "2037-12-01"}),
           "search_stays": (STAYS, {"city": "London", "checkin": "2037-12-01", "nights": 2}),
           "rental_cover": (COUNTER, {"country": "es", "rental_company": "Fictio Rent"})}


def stream(tool, result, args, surface):
    """THE STREAM's own events for one scripted turn (the model asks for `tool`, then speaks) — never a hand-built event."""
    seen: list = []
    steps = [[Block(type="tool_use", id="t1", name=tool, input=args)], [Block(type="text", text="Here you are.")]]

    async def call(ctx, name, a):
        ctx.calls.append({"tool": name, "ok": True})
        return result

    async def go():
        return [ev async for ev in AG.turn(ACCOUNT, "Show me", [], f"s402-{tool}-{surface}", surface=surface)]
    from agapi import s2_fine_print as FP   # fine print's card tools run in their own runner (FP.wrap), not API.call
    with mock.patch.object(LLM, "client", client(steps, seen=seen)), mock.patch.object(API, "call", call), \
            mock.patch.object(FP, "run_tool", call), mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "on"}):
        evs = asyncio.run(go())
    return [e for e in evs if e.get("type") == "render"], seen


def cards_of(ev):
    """The REAL cardsOf (the page's /s2 and /next), run by node on the stream's own event."""
    src = f"import('{CARDS_OF.as_posix()}').then(m => process.stdout.write(JSON.stringify(m.cardsOf({json.dumps(ev)}))))"
    out = subprocess.run(["node", "--no-warnings", "-e", src], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def told_on_screen(seen):
    """What the model was told about the tool's result: was it on screen?"""
    blob = json.dumps(seen, default=str)
    return "nothing from this result was shown on their screen" not in blob


@unittest.skipUnless(shutil.which("node"), "node runs the page's own cardsOf")
class TheStreamsOwnEventsAreDrawn(unittest.TestCase):
    def test_s2_and_next_draw_every_card_the_stream_counts(self):
        for tool, (res, args) in SCRIPTS.items():
            evs, seen = stream(tool, res, args, "s2")
            self.assertTrue(evs, tool)
            for ev in evs:
                self.assertIsInstance(ev.get("card_key"), str, tool)                            # the identity, in its own field
                if ev["kind"] in ("flights", "stays", "counter_card"):
                    self.assertIsInstance(ev.get("card"), dict, tool)                           # the payload, never the key
                self.assertTrue(cards_of(ev), f"{tool}: the stream counted a card the page draws nothing of")
            self.assertTrue(told_on_screen(seen), tool)

    def test_whatsapp_draws_every_card_the_stream_counts(self):
        for tool, (res, args) in SCRIPTS.items():
            if tool == "rental_cover":
                continue   # an S2-only kind: WhatsApp's renderer draws its text card — covered by the S2 run's payload below
            evs, _ = stream(tool, res, args, "wa")
            for ev in evs:
                out = GW.Out()
                WA.render(ev, out, {}, None)                                                    # the real renderer: never a crash
                self.assertTrue(out.items, f"{tool}: counted as drawn on WhatsApp, nothing in the message")

    def test_a_card_with_nothing_to_draw_is_never_said_to_be_on_screen(self):
        for surface in ("s2", "wa"):
            evs, seen = stream("search_flights", NO_FLIGHTS, SCRIPTS["search_flights"][1], surface)
            self.assertEqual([e for e in evs if e.get("kind") == "flights"], [], surface)     # not yielded as drawn
            self.assertFalse(told_on_screen(seen), surface)                                    # and she is told it isn't shown


class EveryDoorAsksItsOwnRenderer(unittest.TestCase):
    def test_every_kind_s2_draws_says_what_it_needs(self):
        self.assertEqual(set(AG.S2_DRAWS) - set(AG.S2_NEEDS), set())

    def test_whatsapp_nothing_kinds_are_not_drawn(self):
        for k in ("kind_ask", "focus", "inline", "discover"):
            self.assertFalse(AG.draws("s2", {"kind": k, "choices": ["a"]}, wa=True), k)

    @unittest.skipUnless(shutil.which("node"), "node runs the page's own cardsOf")
    def test_s2_needs_equals_cards_of_on_edge_payloads(self):
        evs = [{"kind": "flights", "card": "flights"}, {"kind": "flights", "card": {"options": []}},
               {"kind": "stays", "card": {"title": "x", "options": [{"name": "a"}]}}, {"kind": "counter_card", "card": "counter_card"},
               {"kind": "counter_card"}, {"kind": "venues", "preset": {"all": [{"place_id": "p"}]}}, {"kind": "venues", "preset": {}},
               {"kind": "pay", "url": "http://x"}, {"kind": "pay", "url": "https://x"}, {"kind": "kind_ask", "choices": []},
               {"kind": "trip"}, {"kind": "trip", "cards": [{"options": []}]}, {"kind": "total", "total": {"eur": 1}}]
        for ev in evs:
            self.assertEqual(AG.draws("s2", ev), bool(cards_of(ev)), ev)

    def test_the_identity_never_overwrites_a_payload(self):
        src = (BACKEND / "app/agent/sasha.py").read_text()
        self.assertNotIn('yield {**ev, "card": key', src)
        self.assertIn('"card_key": key', src)
        page = (BACKEND.parent / "frontend/app/s2/S2App.tsx").read_text()
        self.assertNotIn("card: ev.card }", page)
        self.assertIn("from '@/lib/cards-of'", page)


if __name__ == "__main__":
    unittest.main()
