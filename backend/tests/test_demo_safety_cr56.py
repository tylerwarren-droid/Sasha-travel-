"""CR 56 · THE TWO DEMO SAFETY BEATS, as permanent tests — "what are my cancellation terms?" and "find me dinner options" must
NEVER act (cancel, book, pay, send), whatever the model does. Fixtures only: the model is a script (app/agent/fakes.py), the
venue API is a recorder, and nothing leaves this machine (0 live calls).

What is pinned:
  · the agent loop fills a booking/cancel tool's approval from the person's REAL words of this turn — never the model's;
  · cancel_venue / book_venue / book refuse without an explicit yes, so an over-eager model can't act on a question;
  · a first cancel_venue call only READS the cancellation (its read-back); nothing is sent to the venue.
Known gaps (expectedFailure until fixed — they flip to failures the day they're fixed, so remove the decorator then):
  · explicit_yes() is keyword-based: "Yes — what are my cancellation terms?" and "Sure, find me dinner options" count as a yes;
  · a prepared venue booking/cancellation never goes stale: a yes hours later still acts on it;
  · (fails safe) "yes, cancel it" is NOT a yes ("cancel" is a no-word), so confirming a cancellation loops.

    cd backend && python -m unittest tests.test_demo_safety_cr56 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import v0 as API, venues as VN
from app.agent.fakes import Block, client

ACCOUNT = "00000000-0000-4000-8000-0000000000c6"
CANCEL_TERMS = "what are my cancellation terms?"
DINNER_OPTIONS = "find me dinner options"


def run(c):
    return asyncio.run(c)


class VenueAPI:
    """The booking API the venue tools call (guest_whatsapp.api), recorded. A POST to …/cancel or a send is an ACT."""

    def __init__(self):
        self.calls = []

    async def api(self, account, method, path, body=None, timeout=None):
        self.calls.append((method, path, body))
        if method == "GET" and path.endswith("/cancel"):
            return 200, {"venue": "Casa Lucio", "route": "email",
                         "read_back": {"sha256": "c" * 64, "lines": ["I'll email Casa Lucio to cancel your table on Fri 14 Nov, 21:00."]}}
        return 200, {"status": "cancel_sent", "say": "Sent to Casa Lucio."}

    def acts(self):
        return [c for c in self.calls if c[0] != "GET"]


class Base(unittest.TestCase):
    def setUp(self):
        self.venue = VenueAPI()
        GW = VN._API()
        self.patches = [mock.patch.object(GW, "api", self.venue.api),
                        mock.patch.object(GW, "plain_venue", lambda v: v or ""),
                        mock.patch.object(GW, "refusal_words", lambda j, s: "refused")]
        for p in self.patches:
            p.start()
        self.saved = (dict(VN._HELD), dict(VN._CANCEL), dict(API._HELD))
        VN._HELD.clear(), VN._CANCEL.clear(), API._HELD.clear()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        VN._HELD.clear(), VN._CANCEL.clear(), API._HELD.clear()
        VN._HELD.update(self.saved[0]), VN._CANCEL.update(self.saved[1]), API._HELD.update(self.saved[2])

    def ctx(self, said):
        return API.Ctx(account=ACCOUNT, user_said=said)

    def prepared_cancel(self, minutes_ago=2):
        VN._CANCEL[ACCOUNT] = {"id": "item-1", "sha": "c" * 64, "venue": "Casa Lucio",
                               "at": datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)}

    def prepared_booking(self, minutes_ago=2):
        VN._HELD[ACCOUNT] = {"venue": "Casa Lucio", "rung": "email", "place_id": None,
                             "at": datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)}


# ── 1 · the yes itself ─────────────────────────────────────────────────────────────────────────────────────────────────

class TheYes(unittest.TestCase):
    def test_the_two_demo_lines_are_not_a_yes(self):
        for said in (CANCEL_TERMS, DINNER_OPTIONS, "What would it cost to cancel?", "can I cancel the dinner?",
                     "show me options for tonight", "look up the cancellation policy", "Is it refundable?"):
            self.assertFalse(API.explicit_yes(said), said)

    def test_a_real_yes_is(self):
        for said in ("Yes, book it", "Yes please", "go ahead", "Then book it."):
            self.assertTrue(API.explicit_yes(said), said)

    # Sasha 215 · FIXED (was a CR 56 known gap: CR 56 GAP 3 (fails SAFE, but loops): "cancel" is in the no-words, so a cancellation's own )
    def test_yes_cancel_it_confirms_a_cancellation(self):
        for said in ("yes, cancel it", "Yes please cancel", "go ahead and cancel"):
            self.assertTrue(API.yes_to_cancel(said), said)   # Sasha 217 · AgAPI 1.1: act-aware — a cancellation's own yes

    # Sasha 215 · FIXED (was a CR 56 known gap: CR 56 GAP 1 · fix before the demo: a question or a request for options is never a yes)
    def test_a_yes_that_is_really_a_question_is_not_a_yes(self):
        for said in ("Yes — what are my cancellation terms?", "Sure, find me dinner options", "ok so what are the options?",
                     "yes, what would cancelling cost?"):
            self.assertFalse(API.explicit_yes(said), said)


# ── 2 · the tools refuse without the yes ───────────────────────────────────────────────────────────────────────────────

class Tools(Base):
    def test_cancel_terms_with_a_cancellation_prepared_never_cancels(self):
        self.prepared_cancel()
        r = run(API.call(self.ctx(CANCEL_TERMS), "cancel_venue", {"trip_item_id": "item-1", "approval": {"said": CANCEL_TERMS},
                                                                 "idempotency_key": "k-cancel-terms-1"}))
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"]["code"], "no_explicit_yes")
        self.assertEqual(self.venue.acts(), [])

    def test_a_first_cancel_call_only_reads_the_cancellation(self):
        r = run(API.call(self.ctx(CANCEL_TERMS), "cancel_venue", {"trip_item_id": "item-1", "approval": {"said": CANCEL_TERMS},
                                                                 "idempotency_key": "k-cancel-terms-2"}))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertEqual(self.venue.acts(), [])                                   # a GET of the read-back, nothing sent

    def test_dinner_options_with_a_booking_prepared_never_books(self):
        self.prepared_booking()
        r = run(API.call(self.ctx(DINNER_OPTIONS), "book_venue", {"approval": {"said": DINNER_OPTIONS},
                                                                 "idempotency_key": "k-dinner-1"}))
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"]["code"], "no_explicit_yes")
        self.assertIn(ACCOUNT, VN._HELD)                                           # the prepared booking is untouched
        self.assertEqual(self.venue.acts(), [])

    def test_book_without_a_yes_never_pays(self):
        with mock.patch("booking_signer.basket_book.pay", mock.AsyncMock()) as pay:
            r = run(API.call(self.ctx(DINNER_OPTIONS), "book", {"approval": {"said": DINNER_OPTIONS}, "idempotency_key": "k-book-1"}))
        self.assertEqual(r["error"]["code"], "no_explicit_yes")
        pay.assert_not_called()

    # Sasha 215 · FIXED (was a CR 56 known gap: CR 56 GAP 2 · fix before the demo: a read-back older than its window can't be acted on)
    def test_a_stale_prepared_cancellation_is_never_acted_on(self):
        self.prepared_cancel(minutes_ago=180)                                      # prepared three hours ago
        r = run(API.call(self.ctx("yes"), "cancel_venue", {"trip_item_id": "item-1", "approval": {"said": "yes"},
                                                          "idempotency_key": "k-stale-1"}))
        self.assertEqual(self.venue.acts(), [], r)

    # Sasha 215 · FIXED (was a CR 56 known gap: CR 56 GAP 1 in practice: today this CANCELS)
    def test_yes_then_a_question_never_cancels(self):
        self.prepared_cancel()
        said = "Yes — what are my cancellation terms?"
        run(API.call(self.ctx(said), "cancel_venue", {"trip_item_id": "item-1", "approval": {"said": said}, "idempotency_key": "k-yq-1"}))
        self.assertEqual(self.venue.acts(), [])


# ── 3 · the whole turn, with a model that tries to act ─────────────────────────────────────────────────────────────────

class Turn(Base):
    """The agent loop with a scripted model that calls the acting tool anyway — and even forges an approval."""

    def turn(self, message, steps):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        real_call = API.call

        async def call(ctx, name, args):
            if name in ("get_status", "get_total", "get_trip"):
                return {"ok": True, "result": {"anything_booked": False, "venues": [], "booked": []}}
            return await real_call(ctx, name, args)
        evs = []

        async def go():
            async for ev in AG.turn(ACCOUNT, message, [], f"cr56-{datetime.now().timestamp()}"):
                evs.append(ev)
        with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call):
            run(go())
        return evs

    def tools(self, evs):
        return [(e["name"], e["ok"], e.get("error")) for e in evs if e["type"] == "tool"]

    def test_cancellation_terms_never_cancel_even_if_the_model_tries(self):
        self.prepared_cancel()
        forged = {"trip_item_id": "item-1", "approval": {"said": "yes, cancel it"}}            # the model can't supply the yes
        evs = self.turn(CANCEL_TERMS, [[Block(type="tool_use", id="t1", name="cancel_venue", input=forged)],
                                       [Block(type="text", text="You can cancel free until the day before.")]])
        self.assertEqual(self.tools(evs), [("cancel_venue", False, "no_explicit_yes")])
        self.assertEqual(self.venue.acts(), [])
        self.assertIn(ACCOUNT, VN._CANCEL)                                          # still only prepared

    def test_dinner_options_never_book_even_if_the_model_tries(self):
        self.prepared_booking()
        forged = {"approval": {"said": "yes book it"}}
        evs = self.turn(DINNER_OPTIONS, [[Block(type="tool_use", id="t1", name="book_venue", input=forged)],
                                         [Block(type="tool_use", id="t2", name="book", input=forged)],
                                         [Block(type="text", text="Here are a few places for tonight.")]])
        self.assertEqual([(n, ok) for n, ok, _ in self.tools(evs)], [("book_venue", False), ("book", False)])
        self.assertTrue(all(err == "no_explicit_yes" for _, _, err in self.tools(evs)))
        self.assertEqual(self.venue.acts(), [])
        done = next(e for e in evs if e["type"] == "done")
        self.assertNotRegex(done["text"], r"(?i)\b(booked|confirmed|cancelled)\b")


if __name__ == "__main__":
    unittest.main()
