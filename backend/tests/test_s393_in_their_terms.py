"""Sasha 393 · what Sasha adds to an answer is in the person's terms and only what they asked.

Measured (Tyler's WhatsApp, 20 Nov 07:57 UTC, "Book lunch at Peñalver Callao on Sunday"): "Callao is on screen for Sunday lunch. What time,
and for how many? Two things from your earlier requests aren't booked." — every word the model's:
  · "on screen": search_venues refused to search again with "… is on their screen — that's their pick: call read_booking_route" (an
    internal state label), and the model said it; it then read the route instead of booking, so the term ask was its own, not code's;
  · "two things …": get_status / my_plans were offered on EVERY turn (tool_need's core) and Sasha 392's pointer said "call get_status" —
    the model fetched their open items unasked and appended them (step 1 too: "The earlier 21:45 request … went to the Cava Baja one").

THE CLASS, made impossible:
  · their bookings' state is fetchable only when THEIR message asks about it (tool_need "status") — every other reply kind, whatever the
    history holds, has no tool that can read it; the one reminder path is the morning summary;
  · no internal state word in any reply: the composer's ONE guard (sasha._INTERNAL) drops it;
  · a booking with a term missing is asked by code, in their terms: "Peñalver Callao, Sunday lunch: what time, and for how many?".

    cd backend && python -m unittest tests.test_s393_in_their_terms -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import app.services.llm as LLM
from agapi import s2_memory as MEM, v0 as API
from app.agent import sasha as AG, tool_need as TN, voice as V
from app.agent.fakes import Block, client

ACCOUNT = "00000000-0000-4000-8000-000000000393"
STATUS = {"get_status", "my_plans"}
TOOLS = [{"name": n} for ns in TN.FAMILIES.values() for n in ns]
HISTORY = [{"role": "user", "content": "Book dinner for 4 at La Taberna de Peñalver on Saturday at 21:00"},
           {"role": "assistant", "content": MEM.POINTER},
           {"role": "user", "content": "is it booked?"},
           {"role": "assistant", "content": "Requested — not confirmed yet. Two things aren't booked."}]
#: every reply kind's message (a booking, a term's answer, a yes, a tap, a search, a trip, a payment, chit-chat, a cancel)
NOT_ASKED = ["Book lunch at Peñalver Callao on Sunday", "4 people", "at 14:00", "yes", "go ahead", "the second one",
             "dinner near Sol tonight", "a restaurant in Hoi An on the 27th", "plan me 5 days in Lisbon", "pay", "thanks!", "hi",
             "cancel the table at Casa Lucio", "change it to 22:00", "what can you do?", "send it on WhatsApp",
             "This one: “Taberna de Peñalver Callao” [their tap on the card on their screen: Taberna de Peñalver Callao · place_id ChIJ99]"]
ASKED = ["is it booked?", "did it go through?", "what's coming up?", "my bookings", "what have I got booked this week?", "any news?",
         "is the table at Casa Lucio confirmed?", "what are my plans for Saturday?", "still waiting?", "status?"]


class OpenItemsOnlyWhenAsked(unittest.TestCase):
    def test_every_reply_kind_has_no_status_tool_whatever_the_history(self):
        for said in NOT_ASKED:
            for trip, places in ((None, None), (True, False), (False, True)):
                offered = {t["name"] for t in TN.select(TOOLS, said, HISTORY, trip=trip, places=places)}
                self.assertFalse(offered & STATUS, (said, trip, places))

    def test_their_ask_about_their_bookings_offers_it(self):
        for said in ASKED:
            self.assertLessEqual(STATUS, {t["name"] for t in TN.select(TOOLS, said, [])}, said)

    def test_the_pointer_names_no_tool_and_asks_for_nothing(self):
        import re
        self.assertFalse([n for ns in TN.FAMILIES.values() for n in ns if re.search(rf"\b{n}\b", MEM.POINTER)])
        for word in ("call", "say", "never", "booked"):
            self.assertNotIn(word, MEM.POINTER.lower())

    def test_the_one_reminder_path_is_the_morning_summary(self):
        self.assertNotIn("get_status", TN.FAMILIES["core"])
        self.assertNotIn("my_plans", TN.FAMILIES["core"])


STATE_SAID = ["Callao is on screen for Sunday lunch.", "It's on your screen now.", "The cards on their screen are ready.",
              "That's on the booking record.", "I've put it on the record.", "This request is open.", "Two open items remain."]
PERSON_SAID = ["Peñalver Callao, Sunday lunch: what time, and for how many?", "Booked — reference CM48213.", "Here are three places.",
               "Requested — I'll tell you when they reply.", "Tap the one you like.", "Sent to Casa Lucio: 4 people, Sat 21 Nov at 21:00."]


class NoInternalStateWord(unittest.TestCase):
    def test_every_state_word_is_an_alarm_never_an_edit(self):   # Sasha 395 · 393's filter → an alarm (logged, counted, never editing)
        for x in STATE_SAID:
            self.assertTrue(AG.state_word_alarm(x), x)
            self.assertFalse(AG._INTERNAL.search(x), x)                                  # no longer dropped by the old filter
        for x in PERSON_SAID:
            self.assertIsNone(AG.state_word_alarm(x), x)
        # Sasha 395 · measured on the 395 gate: a TRUE screen sentence (a card drawn this turn, a surface with a screen) is no alarm
        self.assertIsNone(AG.state_word_alarm("The payment is on the card on your screen.", screen_drawn=True))
        self.assertTrue(AG.state_word_alarm("The payment is on the card on your screen."))           # nothing drawn / WhatsApp: a label
        self.assertTrue(AG.state_word_alarm("That's on the booking record.", screen_drawn=True))    # never a fact for the person

    def test_the_refusal_she_reads_is_in_their_terms(self):
        from agapi import venues as VN
        VN.remember_cards(ACCOUNT, [{"name": "Taberna de Peñalver Callao", "place_id": "ChIJ99"}])
        try:
            with self.assertRaises(API.ToolError) as e:
                asyncio.run(API._search_venues(API.Ctx(account=ACCOUNT, surface="s2"), {"what": "Taberna de Peñalver Callao"}))
        finally:
            VN._SHOWN.pop(ACCOUNT, None)
        self.assertNotIn("screen", str(e.exception))
        self.assertIn("hold_venue", str(e.exception))

    def test_one_guard_not_a_second(self):
        self.assertEqual(inspect.getsource(AG).count("_INTERNAL = re.compile("), 1)
        self.assertEqual(inspect.getsource(AG).count("STATE_WORDS = re.compile("), 1)


def _the(word: str) -> str:   # Sasha 398 · the day THE READER takes the word for (on a Sunday, "Sunday" is today — never our own count)
    from agapi import said as SD
    t = date.today()
    return next((t + timedelta(days=i)).isoformat() for i in range(0, 15) if SD.day(word, t + timedelta(days=i), t))


SUNDAY = _the("on Sunday")


def turn(steps, results, message):
    async def call(ctx, name, args):
        r = results.get(name, {"ok": True, "result": {}})
        ctx.calls.append({"tool": name, "ok": r["ok"]})
        return r

    async def go():
        return [ev async for ev in AG.turn(ACCOUNT, message, [], f"s393-{datetime.now().timestamp()}", surface="s2")]
    with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call), \
            mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "on"}):
        evs = asyncio.run(go())
    done = next(e for e in evs if e["type"] == "done")
    return done["text"], done.get("guard") or []


class TheAskIsCodesInTheirTerms(unittest.TestCase):
    def test_the_measured_turn_says_the_ask_and_nothing_else(self):
        about = V.term_about("Peñalver Callao", SUNDAY, "lunch", True)
        ask = V.term_ask(["time", "party"], None, about)
        self.assertEqual(ask, "Peñalver Callao, Sunday lunch: what time, and for how many?")
        need = {"status": "need_term", "terms": ["time", "party"], "venue": "Peñalver Callao", "booked": False, "ask": ask, "about": about}
        text, guard = turn([[Block(type="text", text="Callao is on screen for Sunday lunch."),
                      Block(type="tool_use", id="h1", name="hold_venue", input={"name": "Peñalver Callao", "place_id": "ChIJ99",
                                                                                "what": "lunch", "day": SUNDAY})],
                     [Block(type="text", text="Two things from your earlier requests aren't booked.")]],
                    {"hold_venue": {"ok": True, "result": need}}, "Book lunch at Peñalver Callao on Sunday")
        # Sasha 395 · her words go out as she said them (no edit); the state word is an ALARM in the turn's guard; the ask is code's
        self.assertEqual(text, "Callao is on screen for Sunday lunch. " + ask)
        self.assertTrue(any(g.startswith("ALARM state word: Callao is on screen") for g in guard), guard)

    def test_every_missing_term_set_is_one_question_after_what_its_for(self):
        about = V.term_about("Casa Gate", None, "dinner", False)
        self.assertEqual(V.term_ask(["date", "time", "party"], None, about), "Casa Gate, dinner: which day, what time, and for how many?")
        self.assertEqual(V.term_ask(["party"], None, "Casa Gate, Saturday"), "Casa Gate, Saturday: for how many people?")
        self.assertEqual(V.term_ask(["time"], [9, 0], "Casa Gate, Saturday"), "Casa Gate, Saturday: 9am or 9pm?")


if __name__ == "__main__":
    unittest.main()
