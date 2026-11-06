"""Sasha 352 · THE NEXT ACTION (docs/sasha/S-352-next-action.md): every card shows its next action as a button, from ONE function of its
item's state; a tap says the words, and the words — typed, spoken or tapped — run that action by code (one path, never a re-plan).

    cd backend && python -m unittest tests.test_s352_next_action -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import types
import unittest
from unittest import mock

from agapi import v0 as API
from app.agent import sasha as AG
from booking_signer import next_actions as NA, wa_agent as WA
from tests.test_agapi_guards import _Block, _Stream

run = asyncio.run
ROOT = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000000352"


class TheOneTable(unittest.TestCase):
    def test_each_trip_state_has_its_next_action(self):
        ids = lambda st: [a["id"] for a in NA.for_trip(st)]
        self.assertEqual(ids("offers"), [])                                         # the options card's own Choose (a tap says the option)
        self.assertEqual(ids("prepared"), ["see"])
        self.assertEqual(ids("chosen"), ["book", "open_trip"])                       # [Book it] beside [See the whole trip]
        self.assertEqual(ids("held"), ["yes", "open_trip"])
        self.assertEqual(ids("pending_payment"), ["pay", "open_trip"])
        self.assertEqual(ids("booked"), ["change", "cancel", "open_trip"])
        self.assertEqual(NA.for_trip(None), [])
        for st in NA.TRIP_STATES:                                                    # no button without an action (or a view) behind it
            for a in NA.for_trip(st):
                self.assertTrue(a.get("say") or a.get("open"), a)
                if a.get("say"):
                    self.assertEqual(NA.heard(a["say"]) or ("change" if "Change" in a["say"] else "cancel" if "Cancel" in a["say"] else None),
                                     a["id"])                                       # the button's words ARE its action

    def test_the_state_is_the_records(self):
        r = lambda *st: [{"state": s} for s in st]
        self.assertEqual(NA.trip_state(rows=r("chosen", "suggested")), "chosen")
        self.assertEqual(NA.trip_state(held=True, rows=r("chosen")), "held")
        self.assertEqual(NA.trip_state(held=True, rows=r("pending_payment")), "pending_payment")   # an old read-back never over a payment
        self.assertEqual(NA.trip_state(held=True, rows=r("booked", "booked")), "booked")
        self.assertEqual(NA.trip_state(prepared=True), "prepared")
        self.assertEqual(NA.trip_state(offers=True), "offers")
        self.assertIsNone(NA.trip_state())

    def test_the_words(self):
        for said, act in (("Book it.", "book"), ("book it please", "book"), ("Ok, book it", "book"), ("Book the whole trip", "book"),
                          ("Yes, book it", "yes"), ("Yes.", "yes"), ("Pay here", "pay"), ("Pay now", "pay"), ("Book all", "book_all"),
                          ("book them all", "book_all"), ("Invite everyone", "invite_all"), ("The invoice", "invoice"),
                          ("Show me the trip", "see")):
            self.assertEqual(NA.heard(said), act, said)
        for said in ("Book it for three of us instead", "Can we book a table at Botín?", "What's the total?", "book a flight to Rome",
                     "Book it, but from Barcelona"):
            self.assertIsNone(NA.heard(said), said)                                 # anything more than the action: the conversation's

    def test_the_group_rows_and_list(self):
        rows = [{"name": "Ana García", "status": "planned"}, {"name": "Luis Pérez", "status": "needs vault"},
                {"name": "Marta Ruiz", "status": "booked"}, {"name": "Javier Moreno", "status": "not planned"}]
        self.assertEqual([[a["id"] for a in NA.for_group_row(r)] for r in rows], [["book_one"], ["invite"], ["cancel_one"], []])
        self.assertEqual(NA.for_group_row(rows[1])[0]["args"], {"who": ["Luis Pérez"]})
        self.assertEqual([a["id"] for a in NA.for_group(rows)], ["book_all", "invite_all", "invoice"])
        self.assertEqual(NA.for_group([{"name": "x", "status": "not planned"}]), [])


class TheWordsAreTheAction(unittest.TestCase):
    """The words → the calls the item's state gives them, by code (agapi.v0.next_uses)."""

    def _uses(self, act, state, prep=None, said="Book it."):
        with mock.patch.object(API, "trip_next", mock.AsyncMock(return_value={"state": state, "actions": NA.for_trip(state)})), \
                mock.patch.dict(API._PREP, {ACCT: prep} if prep else {}, clear=False):
            return run(API.next_uses(ACCT, act, said))

    def test_chosen_holds_held_holds_again(self):
        self.assertEqual(self._uses("book", "chosen"), [("hold_booking", {})])
        held = self._uses("book", "held")                                            # "Book it" after the read-back IS the yes
        self.assertEqual(held, [("book", {"approval": {"said": "Book it."}}) ] if API.yes_to_book("Book it.") else [])

    def test_prepared_is_its_proposal_then_its_read_back_never_a_new_plan(self):
        prep = {"args": {"destination": "Vietnam", "start_date": "2026-12-21", "nights": 8, "party": 2}, "flights": {"madrid": object()}}
        uses = self._uses("book", "prepared", prep)
        self.assertEqual([n for n, _ in uses], ["propose_trip", "hold_booking"])
        self.assertEqual(uses[0][1]["origin"], "Madrid")                             # the prepared flights' origin, as prepared
        self.assertTrue(uses[0][1]["flights"])
        self.assertEqual(self._uses("see", "prepared", prep)[0][0], "propose_trip")
        no_origin = {"args": {"destination": "Vietnam", "start_date": "2026-12-21", "nights": 8, "party": 2}, "flights": {}}
        self.assertEqual(self._uses("book", "prepared", no_origin), [])               # never an assumed home city (283): she asks

    def test_nothing_to_book_is_left_to_the_conversation(self):
        self.assertEqual(self._uses("book", "offers"), [])                           # which one? (349: she asks)
        self.assertEqual(self._uses("book", None), [])
        self.assertEqual(self._uses("book", "booked"), [])
        self.assertEqual(self._uses("pay", "pending_payment", said="Pay here"), [("book", {"approval": {"said": "Pay here"}})])

    def test_book_it_runs_hold_booking_by_code_in_the_turn(self):
        """The turn: "Book it." with a chosen trip → hold_booking runs FIRST, by code; the model only words what came back."""
        steps = [types.SimpleNamespace(content=[_Block(type="text", text="Here's the read-back. Shall I book it?")])]
        seen, models = [], []

        class Msgs:
            def stream(self, **kw):
                models.append(kw.get("model"))
                return _Stream(steps.pop(0))

            async def create(self, **kw):
                return types.SimpleNamespace(content=[_Block(type="text", text="ok")])
        import app.services.llm as LLM
        real_client, real_call = LLM.client, API.call

        async def spy(ctx, name, args):
            seen.append(name)
            return {"ok": True, "result": {"read_back": ["Flight IB 3166 MAD → LHR"], "total_eur": 72.57, "status": "held"}}
        LLM.client, API.call = types.SimpleNamespace(messages=Msgs()), spy
        try:
            with mock.patch.object(API, "next_uses", mock.AsyncMock(return_value=[("hold_booking", {})])) as nu, \
                    mock.patch.object(API, "trip_next", mock.AsyncMock(return_value={"state": "held", "actions": NA.for_trip("held")})):
                evs = run(self._turn("Book it."))
        finally:
            LLM.client, API.call = real_client, real_call
        nu.assert_awaited()
        self.assertEqual(nu.await_args.args[1], "book")
        self.assertEqual(seen[0], "hold_booking")                                    # by code — before any model step
        self.assertEqual(len(models), 1)                                             # the one model step: her words only
        self.assertIn("hold_booking", [e.get("name") for e in evs if e["type"] == "tool"])

    @staticmethod
    async def _turn(message):
        return [ev async for ev in AG.turn(ACCT, message, [], "t352")]


class EveryCardRendersFromTheTable(unittest.TestCase):
    def test_the_trip_cards_carry_their_actions(self):
        src = (ROOT / "app" / "agent" / "sasha.py").read_text()
        self.assertIn('ev = {**ev, "actions": (await API.trip_next(account))["actions"]}', src)
        self.assertEqual(set(AG.TRIP_CARD_TOOLS), {"choose_offer", "get_total", "propose_trip", "swap_stay"})
        routes = (ROOT / "booking_signer" / "ladder_routes.py").read_text()
        self.assertIn('card = {**card, "state": nxt["state"], "actions": nxt["actions"]}', routes)

    def test_whatsapp_taps_say_the_words(self):
        out = types.SimpleNamespace(items=[])
        out.ask = lambda body, buttons: out.items.append(("ask", body, buttons))
        out.text = lambda body: out.items.append(("text", body))
        WA._line({"total": {"total_eur": 72.57}, "actions": NA.for_trip("chosen")}, out)
        self.assertEqual(out.items[0][0], "ask")
        self.assertEqual(out.items[0][2], [("Book it", "say:Book it")])               # the view (the Trip tab) is never a tap

    def test_the_group_view_carries_them(self):
        from tests import test_s333 as V
        from booking_signer import groups as G
        with V.World():
            v = run(G.view(V.OWNER))
            self.assertTrue(all("actions" in r for r in v["rows"]))
            self.assertEqual(v["actions"], NA.for_group(v["rows"]))                    # the list's buttons: the table's, from its rows
            self.assertEqual([a["id"] for a in v["actions"]], ["invite_all"])          # nobody has a passport yet: Invite, never Book all
            self.assertEqual(run(G.card(V.OWNER))["actions"], v["actions"])


if __name__ == "__main__":
    unittest.main()
