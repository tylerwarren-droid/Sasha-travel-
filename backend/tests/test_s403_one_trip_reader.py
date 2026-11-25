"""Sasha 403 · THE TRIP READER IS ACTUALLY ONE (EU 292 claim 1; root test: mailbox row 2138).

Measured (EU 292, verified): journeys._plans read trips with its own SQL and was not on NOT_YET_CLEAN (398's ratchet saw CALLS only);
groups.movement(owner) picked "the OPEN trip" by its own pointer (group_movements.opened_at) beside the conversation's; nothing stopped a
file being ADDED to NOT_YET_CLEAN. Also found: seven copies of "the general-bookings trip" (title, order by created_at limit 1);
plan_store._edit edited the newest CREATED plan and plan_store.save revised the newest made in 6 h, while every reader showed the
newest TOUCHED one (or the conversation's); basket.trip_figures picked PS.latest itself; journeys listed archived trips the rest hid.

THE CLASS: nothing outside booking_signer/trip_record.py PICKS which trip is meant or ASSEMBLES one (T's own writers hold its rows) — by
call or by SQL — and NOT_YET_CLEAN is exactly what the code does, inside a frozen baseline: it can only shrink.

    cd backend && python -m unittest tests.test_s403_one_trip_reader -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from unittest import mock

from booking_signer import groups as G, trip_record as TR
from tests import trip_readers as R

#: Sasha 403 · every file that still assembles or picks a trip itself — each moves onto trip_record next. Exactly what the detector finds.
NOT_YET_CLEAN = {
    "agapi/itinerary.py", "agapi/s2_manage.py", "agapi/s2_status.py", "agapi/s2_tools.py", "agapi/v0.py",
    "booking_signer/basket_book.py", "booking_signer/handoff_phone.py", "booking_signer/itinerary_q.py", "booking_signer/ladder_routes.py",
    "booking_signer/paid_watch.py", "booking_signer/switching.py", "booking_signer/wa_brain.py", "products/relocation/after.py",
}
#: FROZEN — 398's list as it stood (14). NOT_YET_CLEAN may only ever be a subset of it, and smaller. Never add a line here.
BASELINE_398 = frozenset({
    "agapi/itinerary.py", "agapi/s2_manage.py", "agapi/s2_status.py", "agapi/s2_tools.py", "agapi/v0.py",
    "booking_signer/basket_book.py", "booking_signer/groups.py", "booking_signer/handoff_phone.py", "booking_signer/itinerary_q.py",
    "booking_signer/ladder_routes.py", "booking_signer/paid_watch.py", "booking_signer/switching.py", "booking_signer/wa_brain.py",
    "products/relocation/after.py",
})


def run(c):
    return asyncio.run(c)


class Ratchet(unittest.TestCase):
    def test_the_list_is_exactly_what_the_code_does(self):
        hits = set(R.readers())
        self.assertEqual(hits - NOT_YET_CLEAN, set(), "a NEW trip reader outside booking_signer/trip_record (call or SQL)")
        self.assertEqual(NOT_YET_CLEAN - hits, set(), "moved onto trip_record: take it off NOT_YET_CLEAN")

    def test_the_list_only_shrinks(self):
        self.assertTrue(NOT_YET_CLEAN <= BASELINE_398, NOT_YET_CLEAN - BASELINE_398)
        self.assertLess(len(NOT_YET_CLEAN), len(BASELINE_398))

    def test_the_detector_sees_what_398s_could_not(self):
        sees = lambda rel, code: R.findings(rel, code)
        journeys_sql = ('async def _plans(conn, account):\n    return await conn.fetch("select id, title, destinations, depart_date, '
                        'return_date from trips where owner_id = $1 and destinations ? \'plan\' order by updated_at desc", account)\n')
        self.assertTrue(sees("booking_signer/journeys.py", journeys_sql)["assemble"])                           # own SQL over trips
        open_trip = ('    async def movement(self, owner):\n        q = ("select m.* from group_movements m where m.owner = $1 "\n'
                     '             "order by m.opened_at desc limit 1")\n')
        self.assertTrue(sees("booking_signer/groups.py", open_trip)["pick"])                                    # a pointer of its own
        bucket = ('async def put(conn, acct):\n    tid = await conn.fetchval("select id from trips where owner_id = $1 and title = $2 "\n'
                  '                              "order by created_at limit 1", acct, T)\n')
        self.assertTrue(sees("booking_signer/store.py", bucket)["pick"])                                         # a bucket of its own
        self.assertTrue(sees("booking_signer/basket.py", "async def f(a):\n    return await PS.latest(a)\n")["pick"])   # a writer picking
        self.assertFalse(sees("booking_signer/trip_record.py", bucket)["pick"])                                  # the ONE reader may


class OnePointer(unittest.TestCase):
    def setUp(self):
        TR._NOW.clear()
        self.st = G.MemStore()
        p = mock.patch.object(G, "store", lambda: self.st)
        p.start()
        self.addCleanup(p.stop)

        async def none(*a, **k):
            return None
        for q in (mock.patch("agapi.s2_memory.kind", none), mock.patch("agapi.s2_memory.put_kind", none)):
            q.start()
            self.addCleanup(q.stop)

    def made(self, dest):
        return run(self.st.new_movement("acct403", "Fictio SL", dest, "2037-12-01", "2037-12-05", None))

    def test_which_group_trip_is_the_one_pointer_never_the_newest(self):
        lis = self.made("Lisbon")
        self.assertEqual(run(G.store().movement("acct403"))["id"], lis)                         # the only one
        yer = self.made("Yerevan")
        self.assertIsNone(run(G.store().movement("acct403")))                                    # two, none meant: asked, never the newest
        run(G.store().open("acct403", lis))
        self.assertEqual(run(G.store().movement("acct403"))["id"], lis)                         # opened = the ONE pointer
        run(TR.remember("acct403", {"kind": "group", "id": yer}))
        self.assertEqual(run(G.store().movement("acct403"))["id"], yer)                         # the chat's trip, the same pointer
        self.assertEqual([t["id"] for t in run(G.trips("acct403"))["trips"] if t["open"]], [yer])
        run(TR.remember("acct403", {"kind": "personal", "id": "t_own"}))
        self.assertIsNone(run(G.store().movement("acct403")))                                    # his own trip meant: no movement

    def test_no_opened_at_pointer_anywhere(self):
        src = (R.BACKEND / "booking_signer/groups.py").read_text()
        self.assertFalse([q for q in R._sql(src) if "opened_at" in q])                         # no SQL reads or orders by it
        self.assertNotIn("set opened_at", src)                                                   # nor writes it
        self.assertIn("TR.group_now(owner, self)", inspect.getsource(G.PgStore.movement))
        self.assertIn("TR.group_now(owner, self)", inspect.getsource(G.MemStore.movement))


class TheBucketIsOne(unittest.TestCase):
    def test_seven_copies_are_one(self):
        for rel in ("booking_signer/call_store.py", "booking_signer/form_rung.py", "booking_signer/ladder_store.py", "booking_signer/store.py",
                    "products/campus/visits.py", "products/itinerary.py"):
            src = (R.BACKEND / rel).read_text()
            self.assertIn("_TR.bucket(conn, ", src, rel)
            self.assertNotIn("and title = $2 and status in ('draft','active') ", src, rel)


if __name__ == "__main__":
    unittest.main()


class AFlightTapIsItsOffer(unittest.TestCase):
    """Sasha 403 · option B (Tyler): a tap names exactly one offer, so choose_offer runs on the tap BEFORE the model is asked. Found by the
    403 gate: on "the British Airways flight out at 08:30" the model ran get_trip and search_flights first."""
    IB = {"id": "off_ib", "owner": "Iberia", "departs": "2037-01-09T08:00", "arrives": "2037-01-10T06:00", "from": "MAD", "to": "SGN",
          "flights": "IB1", "stops": 1, "minutes": 900, "price_eur": 700}
    BA = {**IB, "id": "off_ba", "owner": "British Airways", "departs": "2037-01-09T08:30", "flights": "BA1"}

    def rows(self, *cards, leg="out"):
        return [{"id": f"r_{c['id']}", "kind": "flight", "state": "suggested", "slice_key": f"{leg}:MAD-SGN", "provider_ref": c["id"],
                 "snapshot": {**c, "name": c["owner"]}} for c in cards]

    def offer(self, words, rows):
        from booking_signer import basket as BK
        with mock.patch.object(TR, "plan_now", mock.AsyncMock(return_value={"trip_id": "t_vn"})), \
                mock.patch.object(BK, "items", mock.AsyncMock(return_value=rows)):
            return run(TR.tapped_offer("acct403", words))

    def test_the_cards_own_words_name_its_one_offer(self):
        from app.agent import sasha as AG
        card = AG.flight_card({"flights": [{"offer_id": c["id"], "airline": c["owner"], "departs": c["departs"], "duration_minutes": 900,
                                            "from": "MAD", "to": "SGN", "stops": 1, "flights": c["flights"], "price_eur": 700}
                                           for c in (self.IB, self.BA)], "leg": "out"}, {"origin": "MAD", "destination": "SGN"})
        ba = next(o for o in card["options"] if o["provider_offer_id"] == "off_ba")
        self.assertEqual(ba["pick"], "the British Airways flight out at 08:30")
        self.assertEqual(self.offer(ba["pick"], self.rows(self.IB, self.BA)), "off_ba")              # the card's words → its offer
        self.assertIsNone(self.offer("the British Airways flight home at 08:30", self.rows(self.IB, self.BA)))   # another leg: none
        self.assertIsNone(self.offer("a cheaper flight please", self.rows(self.IB, self.BA)))        # not a tap: the model hears it
        twin = {**self.BA, "id": "off_ba2"}
        self.assertIsNone(self.offer(ba["pick"], self.rows(self.IB, self.BA, twin)))                # two offers say it: never a guess

    def test_the_tap_runs_choose_offer_before_the_model(self):
        import os
        import app.services.llm as LLM
        from agapi import v0 as API
        from app.agent import sasha as AG
        from app.agent.fakes import Block, client
        from booking_signer import basket as BK
        calls = []

        async def call(ctx, name, a):
            calls.append((name, dict(a)))
            ctx.calls.append({"tool": name, "ok": True})
            return {"ok": True, "result": {"status": "chosen", "chosen": {"offer_id": a.get("offer_id")}}}
        steps = [[Block(type="text", text="Done — the British Airways flight out at 08:30 is in your trip.")]]

        async def go():
            return [e async for e in AG.turn("acct403", "the British Airways flight out at 08:30", [], "s403-tap", surface="s2")]
        with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call), \
                mock.patch.object(TR, "plan_now", mock.AsyncMock(return_value={"trip_id": "t_vn"})), \
                mock.patch.object(BK, "items", mock.AsyncMock(return_value=self.rows(self.IB, self.BA))), \
                mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "on"}):
            evs = run(go())
        self.assertEqual((calls[0][0], calls[0][1].get("offer_id")), ("choose_offer", "off_ba"))   # by code, first
        tools = [e["name"] for e in evs if e.get("type") == "tool"]                                 # the turn's tools, as the gate counts them
        self.assertEqual(tools, ["choose_offer"])                                                   # nothing re-derived (the turn-end price
        # guard's read-only get_total / get_trip are code's own reads, never a tool of the turn)
