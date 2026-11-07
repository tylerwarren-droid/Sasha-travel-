"""Sasha 354 · A REPLY MEANS WHAT IS PENDING NOW, from ONE record (agapi/pending, s2_memory's `pending`), read before any model step.

    cd backend && python -m unittest tests.test_s354_pending_now -v
"""
from __future__ import annotations

import asyncio
import types
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import pending as PEND, s2_memory as MEM, v0 as API
from agapi.s2_status import HELD
from app.agent import sasha as AG
from booking_signer import next_actions as NA, wa_agent as WA
from tests.test_agapi_guards import _Block, _Stream

run = asyncio.run
ACCT = "00000000-0000-4000-8000-000000000354"


class TheRecord(unittest.TestCase):
    def test_the_latest_turn_decides_what_is_pending(self):
        m = MEM.fold({}, "Book it.", "Here's the read-back. Shall I go ahead?", {"calls": [{"tool": "hold_booking", "ok": True, "status": HELD}]})
        self.assertEqual((m["pending"]["kind"], m["pending"]["scope"]), ("yes", "trip"))
        m2 = MEM.fold(m, "What's the baggage?", "One bag each is included. Want me to add a second?", {"calls": []})
        self.assertEqual(m2["pending"]["kind"], "question")                          # a later question is what a yes answers now
        m3 = MEM.fold(m, "Yes", "Pay here, or on your phone?", {"calls": [{"tool": "book", "ok": True, "status": "choose_payment"}]})
        self.assertEqual(m3["pending"]["kind"], "question")                          # the yes was given: the read-back is no longer pending
        m4 = MEM.fold({}, "the Iberia one", "Your earlier pick is waiting for payment. Keep it, or switch?",
                      {"calls": [{"tool": "choose_offer", "ok": True, "status": "pending_pick"}]})
        self.assertEqual(m4["pending"]["kind"], "pick")


class TheTurnWritesIt(unittest.TestCase):
    """Found by the gate: a turn run outside the web routes (the voice pathway, the gate's loops) wrote nothing pending, so its read-back's
    "Yes." met "nothing is waiting". The turn itself notes it (s2_memory.note_pending) — every caller."""

    def test_noted_by_the_turn_and_replaced_by_her_next_question(self):
        rec = {}

        async def load(run, account):
            return dict(rec.get(account) or {})

        async def save(run, account, m):
            rec[account] = dict(m)
        with mock.patch.object(MEM, "_run", lambda: object()), mock.patch.object(MEM, "_db_load", load), mock.patch.object(MEM, "_db_save", save):
            run(MEM.note_pending(ACCT, [{"tool": "hold_booking", "ok": True, "status": HELD}], "Here it is. Shall I go ahead?"))
            self.assertEqual(rec[ACCT]["pending"]["kind"], "yes")
            run(MEM.note_pending(ACCT, [], "No problem — nothing's booked. Tell me when."))      # no question: the read-back still waits
            self.assertEqual(rec[ACCT]["pending"]["kind"], "yes")
            run(MEM.note_pending(ACCT, [], "One bag each is included. Want a second?"))
            self.assertEqual(rec[ACCT]["pending"]["kind"], "question")
        src = __import__("inspect").getsource(AG.turn)
        self.assertIn("await _MEMp.note_pending(account, ctx.calls, text)", src)


class TheReading(unittest.TestCase):
    def _now(self, pending, held=None, kinds=None, pay=None):
        with mock.patch.object(MEM, "_load", mock.AsyncMock(return_value={"pending": pending, "kinds": kinds or {}})), \
                mock.patch.dict(API._HELD, {ACCT: held} if held else {}, clear=True), \
                mock.patch.object(PEND, "payment", mock.AsyncMock(return_value=pay)):
            return run(PEND.now(ACCT))

    def test_a_read_back_is_pending_only_while_it_stands(self):
        now = datetime.now(timezone.utc)
        st = self._now({"kind": "yes", "scope": "trip"}, held={"at": now, "sha": "abc"})
        self.assertEqual(PEND.resolve_yes(st), {"do": "book"})
        st = self._now({"kind": "yes", "scope": "trip"}, held=None)                   # its read-back lapsed / never held here
        self.assertEqual(PEND.resolve_yes(st), {"do": "say", "line": PEND.NOTHING, "card": False})

    def test_a_yes_with_nothing_waiting_is_said_never_a_search(self):
        self.assertEqual(PEND.resolve_yes(self._now(None))["line"], "Nothing is waiting for a yes right now — what would you like to do?")
        pay = {"sid": "cs_test_1", "trip_id": "t", "amount_eur": 55.08, "what": "Air Europa MAD → LGW"}
        r = PEND.resolve_yes(self._now(None, pay=pay))
        self.assertTrue(r["card"])
        self.assertIn("Nothing is waiting for a yes — your payment €55.08 for Air Europa MAD → LGW is still open", r["line"])
        self.assertEqual(PEND.resolve_yes(self._now({"kind": "question", "asked": "Do you need flights too?"}, pay=pay)), {"do": "model"})

    def test_a_pick_waits_for_keep_or_switch_and_lapses(self):
        fresh = datetime.now(timezone.utc).isoformat()
        st = self._now({"kind": "pick"}, kinds={PEND.PICK_KIND: {"offer_id": "off_2", "old": "Air Europa 07:30", "new": "Iberia 17:48", "at": fresh}})
        r = PEND.resolve_yes(st)
        self.assertEqual(r["line"], "Your earlier pick (Air Europa 07:30) is waiting for payment. Keep it, or switch to Iberia 17:48?")
        old = "2026-01-01T00:00:00+00:00"
        self.assertIsNone(self._now({"kind": "pick"}, kinds={PEND.PICK_KIND: {"offer_id": "off_2", "at": old}})["now"])


class ThePick(unittest.TestCase):
    """A new pick against a payment under way — never a second choice written over it (AlreadyRecorded)."""
    ROW = {"id": "r2", "kind": "flight", "state": "suggested", "slice_key": "out:Madrid→London 2026-11-24", "provider_ref": "off_2",
           "snapshot": {"owner": "Iberia", "from": "MAD", "to": "LHR", "departs": "2026-11-24T17:48"}}
    PAID = {"id": "r1", "kind": "flight", "state": "pending_payment", "slice_key": "out:Madrid→London 2026-11-24",
            "snapshot": {"owner": "Air Europa", "from": "MAD", "to": "LGW", "departs": "2026-11-24T07:30"}}

    def _run(self, row, a):
        from booking_signer import basket as BK, basket_book as BB
        held = []
        with mock.patch.object(BK, "items", mock.AsyncMock(return_value=[self.PAID])), \
                mock.patch.object(PEND, "payment", mock.AsyncMock(return_value={"sid": "cs_1", "trip_id": "t1", "amount_eur": 55.08,
                                                                                 "what": "Air Europa MAD → LGW"})), \
                mock.patch.object(PEND, "hold_pick", mock.AsyncMock(side_effect=lambda acct, p: held.append(p))), \
                mock.patch.object(PEND, "drop_pick", mock.AsyncMock()), \
                mock.patch.object(BB, "_supersede", mock.AsyncMock(return_value=None)) as sup:
            ctx = types.SimpleNamespace(account=ACCT)
            out = run(API._pick_against_payment(ctx, {"trip_id": "t1"}, row, a))
        return out, held, sup

    def test_the_pending_card_and_one_question(self):
        out, held, sup = self._run(dict(self.ROW), {})
        self.assertEqual(out["status"], "pending_pick")
        self.assertEqual(out["ask"], "Your earlier pick (Air Europa MAD → LGW 2026-11-24 07:30) is waiting for payment. Keep it, or switch to "
                                     "Iberia MAD → LHR 2026-11-24 17:48?")
        self.assertEqual(held[0]["offer_id"], "off_2")
        sup.assert_not_awaited()                                                       # nothing closed, nothing chosen

    def test_switch_closes_the_earlier_payment_the_baskets_way_then_chooses(self):
        out, held, sup = self._run(dict(self.ROW), {"switch": True})
        self.assertIsNone(out)                                                          # the pick goes on: chosen
        sup.assert_awaited_once()
        self.assertEqual(sup.await_args.args[1], {"sid": "cs_1", "trip_id": "t1"})

    def test_the_same_flight_again_is_its_payment(self):
        out, _, _ = self._run(dict(self.PAID), {})
        self.assertEqual(out["status"], "pending_payment")
        self.assertIn("is still open", out["say"])

    def test_its_card_and_answers(self):
        self.assertEqual([a["id"] for a in NA.for_trip("choice")], ["keep", "switch", "open_trip"])
        self.assertEqual(NA.trip_state(pick=True, rows=[{"state": "pending_payment"}]), "choice")
        self.assertEqual((NA.heard("Keep the earlier one"), NA.heard("Switch to the new one")), ("keep", "switch"))
        ev = AG.render("choose_offer", {"status": "pending_pick", "ask": "Keep it, or switch?"}, {})
        self.assertEqual(ev["kind"], "trip")
        out = types.SimpleNamespace(items=[])
        out.ask = lambda body, buttons: out.items.append(("ask", body, buttons))
        WA._pending({"actions": NA.for_trip("choice")}, out)                              # WhatsApp: the same answers, as taps
        self.assertEqual(out.items[0][2], [("Keep it", "say:Keep the earlier one"), ("Switch", "say:Switch to the new one")])


class TheTurn(unittest.TestCase):
    def _turn(self, message, state, steps=None):
        steps = list(steps or [types.SimpleNamespace(content=[_Block(type="text", text="Done.")])])
        models, seen = [], []

        class Msgs:
            def stream(self, **kw):
                models.append(1)
                return _Stream(steps.pop(0))

            async def create(self, **kw):
                return types.SimpleNamespace(content=[_Block(type="text", text="ok")])
        import app.services.llm as LLM
        real_client, real_call = LLM.client, API.call

        async def spy(ctx, name, args):
            seen.append((name, args))
            return {"ok": True, "result": {"status": "choose_payment", "ask": "Pay here, or on your phone?"}}
        LLM.client, API.call = types.SimpleNamespace(messages=Msgs()), spy
        try:
            with mock.patch.object(PEND, "now", mock.AsyncMock(return_value=state)), \
                    mock.patch.object(API, "trip_next", mock.AsyncMock(return_value={"state": "pending_payment", "actions": NA.for_trip("pending_payment")})):
                evs = run(self._go(message))
        finally:
            LLM.client, API.call = real_client, real_call
        return evs, models, seen

    @staticmethod
    async def _go(message):
        return [ev async for ev in AG.turn(ACCT, message, [], "t354")]

    def test_yes_with_nothing_pending_is_said_by_code_no_model_no_search(self):
        evs, models, seen = self._turn("Yes.", {"now": None, "payment": None})
        self.assertEqual(models, [])
        self.assertEqual(seen, [])
        self.assertEqual(next(e for e in evs if e["type"] == "done")["text"], PEND.NOTHING)

    def test_yes_with_a_payment_open_shows_its_card(self):
        pay = {"sid": "cs", "trip_id": "t", "amount_eur": 28.71, "what": "Transavia MAD → ORY"}
        evs, models, seen = self._turn("yes", {"now": None, "payment": pay})
        self.assertEqual((models, seen), ([], []))
        card = next(e for e in evs if e["type"] == "render")
        self.assertEqual([a["id"] for a in card["actions"]], ["pay", "open_trip"])

    def test_yes_to_a_read_back_books_by_code(self):
        evs, models, seen = self._turn("Yes, go ahead.", {"now": {"kind": "yes", "scope": "trip"}, "payment": None})
        self.assertEqual(seen[0], ("book", {"approval": {"said": "Yes, go ahead."}, "idempotency_key": seen[0][1].get("idempotency_key")}))
        self.assertEqual(len(models), 1)                                                  # her words only

    def test_yes_to_her_question_is_the_conversation(self):
        evs, models, seen = self._turn("Yes", {"now": {"kind": "question", "asked": "Do you need flights too?"}, "payment": None})
        self.assertEqual(len(models), 1)                                                  # the model answers her question
        self.assertFalse([n for n, _ in seen if n not in ("get_total", "get_trip", "get_status")])   # nothing done by code (reads only)


if __name__ == "__main__":
    unittest.main()
