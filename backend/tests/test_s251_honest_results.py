"""Sasha 251 · HONEST RESULTS — found live on /s2: search_venues failed (ok: false) and she still said "Have a look whenever you like
and tap one if it tempts you" about cards that were never drawn. One rule in voice.py, and the agent loop holds it: when a showing
tool failed and nothing reached their screen, a claim that something did is never said — she says it didn't work, and what next.
Offline: a scripted model, no network, no Places."""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime
from unittest import mock

import app.services.llm as LLM
from agapi import v0 as API
from app.agent import sasha as AG
from app.agent import voice as V
from app.agent.fakes import Block, client

ACCOUNT = "00000000-0000-4000-8000-000000000251"
CLAIM = "Here are a few spots near Sol. Have a look whenever you like and tap one if it tempts you."
FAIL = {"ok": False, "error": {"code": "unavailable", "message": "the places search isn't answering right now"}}


def turn(steps, results, surface="s2", parity="on"):
    """One scripted turn → (events, the reply that reaches the person)."""
    async def call(ctx, name, args):
        r = results.get(name, {"ok": True, "result": {}})
        ctx.calls.append({"tool": name, "ok": r["ok"]})
        return r

    async def go():
        out = []
        async for ev in AG.turn(ACCOUNT, "Dinner near Sol tonight for two?", [], f"s251-{datetime.now().timestamp()}", surface=surface):
            out.append(ev)
        return out
    with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call), \
            mock.patch.dict(os.environ, {"SASHA_S1_PARITY": parity}):
        evs = asyncio.run(go())
    return evs, next(e["text"] for e in evs if e["type"] == "done")


def spoken(evs):
    return " ".join(e["text"] for e in evs if e["type"] == "say")


SEARCH = Block(type="tool_use", id="t1", name="search_venues", input={"what": "dinner", "where": "Sol, Madrid"})


class TheRule(unittest.TestCase):
    def test_the_rule_is_in_her_voice_on_every_surface(self):
        from app.agent import s2 as S2
        self.assertIn("When a tool fails", V.RULES)
        self.assertIn(V.RULES.strip(), S2.s2_system())
        self.assertIn(V.RULES.strip(), S2.S1_CAN)

    def test_every_tool_is_in_exactly_one_table(self):
        from agapi import s2_fine_print as FP, s2_subscriptions as SUBS
        every = set(API.BY_NAME) | set(FP.TOOL_NAMES) | {t["name"] for t in SUBS.TOOLS}
        self.assertEqual(every, set(V.SHOWS) | set(V.SAYS))
        self.assertFalse(set(V.SHOWS) & set(V.SAYS))

    def test_every_tool_that_renders_a_card_is_a_showing_tool(self):
        shows = {t for t, k in AG.RENDER.items() if k != "inline"} | set(AG._fine_print_tools())
        self.assertLessEqual(shows, set(V.SHOWS))

    def test_her_failed_lines_are_plain_and_clean(self):
        for t in V.SHOWS:
            line = V.failed_line(t, "")
            self.assertIn("didn't work", line)
            self.assertFalse(AG._INTERNAL.search(line), line)
            self.assertEqual(V.check([line]), [])
            self.assertEqual(V.claims_shown(line), [])

    def test_only_plain_words_from_the_error(self):
        self.assertEqual(V.failed_line("search_venues", "the places search isn't answering right now"),
                         "That search didn't work — the places search isn't answering right now. Say the word and I'll try again.")
        for m in ("search_venues failed (TimeoutError) — a lookup only", "no more tool calls this turn — answer with what you have",
                  "missing_input", "x" * 120):
            self.assertEqual(V.failed_line("search_venues", m), "That search didn't work. Say the word and I'll try again.", m)

    def test_claims(self):
        for s in (CLAIM, "Done — it's on your screen, tap to confirm.", "Sent. I'll tell you when they reply.", "The options are below.",
                  "I've found you three lovely places."):
            self.assertTrue(V.claims_shown(s), s)
        for s in ("That search didn't work. Say the word and I'll try again.", "What time would you like?",
                  "I couldn't pull the places up — have a look again in a minute?"):
            self.assertFalse(V.claims_shown(s), s)

    def test_the_gate_check(self):
        bad = V.honest_faults([{"said": CLAIM, "calls": [{"tool": "search_venues", "ok": False}], "rendered": False}])
        self.assertTrue(bad and "search_venues failed" in bad[0], bad)
        self.assertEqual(V.honest_faults([{"said": V.failed_line("search_venues"), "calls": [{"tool": "search_venues", "ok": False}]}]), [])
        self.assertEqual(V.honest_faults([{"said": CLAIM, "calls": [{"tool": "search_venues", "ok": False},
                                                                     {"tool": "search_venues", "ok": True}], "rendered": True}]), [])
        self.assertEqual(V.honest_faults([{"said": "Lovely.", "calls": [{"tool": "keep_list", "ok": False}]}]), [])


class TheLoop(unittest.TestCase):
    def test_a_failed_search_never_claims_cards(self):
        evs, text = turn([[Block(type="text", text="Let me look."), SEARCH], [Block(type="text", text=CLAIM)]], {"search_venues": FAIL})
        self.assertNotIn("Have a look", text)
        self.assertNotIn("tap one", spoken(evs))
        self.assertIn("didn't work", text)
        self.assertIn("isn't answering", text)
        self.assertTrue(text.startswith("Let me look."), text)
        self.assertEqual(V.honest_faults([{"said": text, "calls": [{"tool": "search_venues", "ok": False}]}]), [])
        done = next(e for e in evs if e["type"] == "done")
        self.assertTrue(any(g.startswith("unshown") for g in done["guard"]), done["guard"])

    def test_a_claim_said_before_the_tool_ran_is_replaced(self):
        evs, text = turn([[Block(type="text", text="Here are some places — have a look."), SEARCH], [Block(type="text", text="")]],
                         {"search_venues": FAIL})
        rep = [e for e in evs if e["type"] == "replace"]
        self.assertTrue(rep, [e["type"] for e in evs])
        self.assertNotIn("have a look", rep[-1]["text"])
        self.assertIn("didn't work", rep[-1]["text"])
        self.assertTrue(rep[-1]["speak"])
        self.assertEqual(text, rep[-1]["text"])

    def test_an_honest_reply_is_left_alone(self):
        honest = "That search didn't work just now. Want me to try again?"
        evs, text = turn([[SEARCH], [Block(type="text", text=honest)]], {"search_venues": FAIL})
        self.assertEqual(text, honest)
        self.assertFalse([e for e in evs if e["type"] == "replace"])

    def test_a_question_after_a_refusal_is_left_alone(self):
        ask = "Which day would you like?"
        _, text = turn([[SEARCH], [Block(type="text", text=ask)]],
                       {"search_venues": {"ok": False, "error": {"code": "missing_input", "message": "missing: when"}}})
        self.assertEqual(text, ask)

    def test_a_retry_that_worked_keeps_the_claim(self):
        calls = iter([FAIL, {"ok": True, "result": {"find": {"what": "dinner"}, "preset": {"all": [], "cards": [{"name": "Casa Marea",
                                                                                                                   "place_id": "p1"}], "show": 1}}}])

        class R(dict):
            def get(self, name, d=None):
                return next(calls) if name == "search_venues" else d
        evs, text = turn([[SEARCH], [SEARCH], [Block(type="text", text="Casa Marea is on your screen — tap it if it tempts you.")]], R())
        self.assertIn("tap it", text)
        self.assertFalse([e for e in evs if e["type"] == "replace"])

    def test_a_failed_booking_never_says_sent(self):
        _, text = turn([[Block(type="tool_use", id="t1", name="hold_venue", input={"place_id": "p1"})],
                        [Block(type="text", text=V.SENT)]],
                       {"hold_venue": {"ok": False, "error": {"code": "no_route", "message": "they don't take bookings"}}})
        self.assertNotIn("Sent.", text)
        self.assertEqual(text, "Getting the booking ready didn't work — they don't take bookings. Say the word and I'll try again.")

    def test_whatsapp_shares_it(self):
        _, text = turn([[SEARCH], [Block(type="text", text=CLAIM)]], {"search_venues": FAIL}, surface="wa")
        self.assertNotIn("Have a look", text)
        self.assertIn("didn't work", text)

    def test_next_with_parity_on_shares_it(self):
        _, text = turn([[SEARCH], [Block(type="text", text=CLAIM)]], {"search_venues": FAIL}, surface="s1", parity="on")
        self.assertIn("didn't work", text)

    def test_next_with_parity_off_is_untouched(self):
        _, text = turn([[SEARCH], [Block(type="text", text=CLAIM)]], {"search_venues": FAIL}, surface="s1", parity="off")
        self.assertEqual(text, CLAIM)


if __name__ == "__main__":
    unittest.main()
