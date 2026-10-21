"""Sasha 257 · T37 — THE HOLDING LINE (Tyler, row 863: "a WhatsApp question took 10–15 s before any reply"). Her reply not ready
within voice.HOLD_AFTER_S → ONE short rotating line first (never a claim, never for a fast reply), then the answer — on /s2 and /next
(sasha.with_holding, around the turn's stream) and WhatsApp (guest_whatsapp._brain_turn). Offline; the brain is a stand-in.

    cd backend && python -m unittest tests.test_s257_holding -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from app.agent import sasha as S, voice as V
from booking_signer import guest_whatsapp as GW, wa_agent as WA
from tests import test_guest_whatsapp_s75 as TG


def run(c):
    return asyncio.run(c)


async def gen(delay, events):
    await asyncio.sleep(delay)
    for e in events:
        yield e


async def collect(agen):
    return [e async for e in agen]


CLAIMS = ("found", "booked", "sent", "confirmed", "done", "ready")


class ThePhrasebook(unittest.TestCase):
    def test_short_rotating_never_a_claim(self):
        lines = [V.holding_line("x") for _ in range(6)]
        self.assertEqual(len(set(lines)), 3)
        self.assertNotEqual(lines[0], lines[1])
        for l in V.HOLDING:
            self.assertLessEqual(len(l.split()), 6, l)
            self.assertFalse(any(c in l.lower() for c in CLAIMS), l)


class OnS2AndNext(unittest.TestCase):
    def test_a_slow_reply_gets_one_holding_line_first(self):
        evs = run(collect(S.with_holding(gen(0.25, [{"type": "render", "kind": "venues"}, {"type": "text", "delta": "Here"}, {"type": "done", "text": "Here"}]), "a", after_s=0.05)))
        self.assertEqual(evs[0]["type"], "hold")
        self.assertIn(evs[0]["text"], V.HOLDING)
        self.assertEqual(evs[0]["say"], evs[0]["text"])
        self.assertEqual([e["type"] for e in evs].count("hold"), 1)
        # Sasha 279 · A: + the one "working" state the screen shows (on with the holding line, off when her words begin)
        self.assertEqual([e["type"] for e in evs[1:]], ["working", "render", "working", "text", "done"])
        self.assertEqual([e["on"] for e in evs if e["type"] == "working"], [True, False])

    def test_a_fast_reply_gets_none(self):
        evs = run(collect(S.with_holding(gen(0.0, [{"type": "text", "delta": "Hi"}, {"type": "done", "text": "Hi"}]), "a", after_s=0.2)))
        self.assertNotIn("hold", [e["type"] for e in evs])

    def test_never_once_her_words_have_started(self):
        async def slow_after_text():
            yield {"type": "text", "delta": "Looking"}
            await asyncio.sleep(0.2)
            yield {"type": "done", "text": "Looking"}
        evs = run(collect(S.with_holding(slow_after_text(), "a", after_s=0.05)))
        self.assertNotIn("hold", [e["type"] for e in evs])

    def test_the_stream_uses_it_on_the_s2_shell(self):
        import inspect
        src = inspect.getsource(S)
        self.assertIn('with_holding(turn_events, account, first=_V.first_ack(account, message, said=body.get("said_first"))) if remembers else turn_events', src)   # Sasha 265 · + the first line · 273: once per request (moved)


class OnWhatsApp(TG.Base):
    def setUp(self):
        super().setUp()
        self.link()

    def brain(self, delay):
        async def agent(ch, body, payload, st, out, now, button_text="", voice_in=False):
            await asyncio.sleep(delay)
            out.text("Here are three places near Sol.")
            return "x"
        return mock.patch.object(WA, "agent_turn", agent)

    def test_a_slow_answer_gets_the_holding_line_first(self):
        with self.brain(0.3), mock.patch.object(V, "HOLD_AFTER_S", 0.05):
            n = len(self.bodies())
            # Sasha 265 · item 5: a request for WORK now hears voice.FIRST_LINE at once (test_s265); the holding line stays for the rest
            self.say("what's the weather like near Sol today?")
            said = self.bodies()[n:]
        self.assertIn(said[0], V.HOLDING)
        self.assertEqual(said[1], "Here are three places near Sol.")
        self.assertEqual(sum(1 for b in said if b in V.HOLDING), 1)

    def test_a_fast_answer_gets_none(self):
        with self.brain(0.0), mock.patch.object(V, "HOLD_AFTER_S", 0.5):
            n = len(self.bodies())
            self.say("a table for two tonight near Sol")
            said = self.bodies()[n:]
        self.assertFalse(any(b in V.HOLDING for b in said), said)


if __name__ == "__main__":
    unittest.main()
