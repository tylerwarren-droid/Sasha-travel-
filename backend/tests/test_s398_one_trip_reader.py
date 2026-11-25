"""Sasha 398 · EVERY TRIP READER ON THE ONE RECORD (root test: mailbox row 2107).

Live symptom (Tyler's /next, 22 Nov): the right-hand panel showed a "Jean Incorporated → Lisbon" movement AND a Madrid → London itinerary
while the chat in the same session answered about his own trips — three "which trip" answers: get_trip (their words), /plan (PS.latest:
the latest TOUCHED plan) and GroupTripNow (the organiser's OPEN movement).

THE CLASS: "which trip is this conversation about?" has ONE answer — booking_signer.trip_record.current (the trip the reader last resolved
in this conversation, a POINTER in the one conversation record; else the latest personal T) — asked by the chat, /plan, /trip/now and the
group card; and a RATCHET: no module outside trip_record (and T's own writers) reads the basket's rows or assembles a trip; NOT_YET_CLEAN
names every file still doing it today and may only shrink.

    cd backend && python -m unittest tests.test_s398_one_trip_reader -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from agapi import s2_memory as MEM, v0 as API
from booking_signer import basket as BK, groups as G, ladder_routes as LR, plan_store as PS, trip_record as TR

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FE = BACKEND.parent / "frontend"
ACCT = "00000000-0000-4000-8000-000000000398"
PLANS = [{"trip_id": "t_london", "title": "Flight Madrid → London", "start": "2026-12-01", "end": "2026-12-03", "cities": ["London"]},
         {"trip_id": "t_lisbon", "title": "3 Days in Lisbon", "start": "2026-12-09", "end": "2026-12-12", "cities": ["Lisbon"]}]
MOVES = [{"id": "mv_jean", "destination": "Lisbon", "company": "Jean Incorporated", "starts_on": "2026-12-15", "ends_on": "2026-12-20"}]
BY_ID = {p["trip_id"]: {**p, "plan": {"days": []}} for p in PLANS}

#: Sasha 403 · the list and the detector are ONE: tests/test_s403_one_trip_reader (NOT_YET_CLEAN) and tests/trip_readers (call AND SQL)


def run(c):
    return asyncio.run(c)


class Records(unittest.TestCase):
    def setUp(self):
        MEM._MEM.clear()
        st = mock.Mock()
        st.trips = mock.AsyncMock(return_value=MOVES)
        latest = mock.AsyncMock(return_value=BY_ID["t_london"])   # the latest TOUCHED plan (what /plan used to show)
        kinds: dict = {}   # the one conversation record's kinds (production: its database row)

        async def put_kind(account, name, value):
            kinds[(account, name)] = value
            return True

        async def kind(account, name):
            return kinds.get((account, name))
        for p in (mock.patch.object(PS, "plans", mock.AsyncMock(return_value=PLANS)), mock.patch.object(G, "store", lambda: st),
                  mock.patch.object(PS, "latest", latest),
                  mock.patch.object(MEM, "put_kind", put_kind), mock.patch.object(MEM, "kind", kind),
                  mock.patch.object(PS, "by_id", mock.AsyncMock(side_effect=lambda a, tid: BY_ID.get(tid)))):
            p.start()
            self.addCleanup(p.stop)


class OneAnswer(Records):
    def test_which_trip_is_this_conversation_about(self):
        self.assertEqual(run(TR.current(ACCT))["id"], "t_london")                                   # nothing resolved yet: the latest
        run(TR.remember(ACCT, {"kind": "personal", "id": "t_lisbon"}))
        self.assertEqual(run(TR.current(ACCT))["id"], "t_lisbon")                                   # the trip the chat resolved
        run(TR.remember(ACCT, {"kind": "group", "id": "mv_jean"}))
        self.assertEqual(run(TR.current(ACCT))["movement_id"], "mv_jean")
        self.assertEqual(run(TR.plan_now(ACCT))["trip_id"], "t_london")                             # personal tools: his own latest
        run(TR.remember(ACCT, {"kind": "personal", "id": "t_gone"}))
        self.assertEqual(run(TR.current(ACCT))["id"], "t_london")                                   # a pointer to nothing: never trusted

    def test_get_trip_points_the_conversation_at_its_trip(self):
        with mock.patch.object(BK, "items", mock.AsyncMock(return_value=[])), \
                mock.patch.object(BK, "trip_figures", mock.AsyncMock(return_value={"total_eur": None, "party": 1})):
            run(API.get_trip(API.Ctx(account=ACCT, user_said="What's on my London trip?", surface="s2"), {}))
        self.assertEqual(run(TR.current(ACCT))["id"], "t_london")
        with self.assertRaises(API.ToolError):   # "my Lisbon trip": his own Lisbon AND the Lisbon movement he organises — asked, never guessed
            run(API.get_trip(API.Ctx(account=ACCT, user_said="What's on my Lisbon trip?", surface="s2"), {}))

    def test_new_chat_forgets_the_pointer(self):
        self.assertIn(TR.NOW, MEM.CONVERSATION_KINDS)


class EveryScreenAsksIt(Records):
    def req(self, **q):
        r = mock.Mock()
        r.query_params = q
        return r

    def test_trip_now_and_plan_name_the_same_trip(self):
        run(TR.remember(ACCT, {"kind": "personal", "id": "t_lisbon"}))
        with mock.patch.object(LR, "account_for", lambda r: ACCT):
            now = run(LR.trip_now(self.req()))
        self.assertEqual((now["kind"], now["id"]), ("personal", "t_lisbon"))
        self.assertIn("TR.plan_now(account)", (BACKEND / "booking_signer/ladder_routes.py").read_text())   # /plan's personal trip

    def test_his_own_trip_never_shows_a_movement(self):
        run(TR.remember(ACCT, {"kind": "personal", "id": "t_lisbon"}))
        with mock.patch.object(LR, "account_for", lambda r: ACCT):
            self.assertEqual(run(LR.trip_now(self.req()))["kind"], "personal")
        card = (FE / "app/components/cards/S2Cards.tsx").read_text()
        i = card.index("export function GroupTripNow")
        body = card[i:i + 2400]
        self.assertIn("'/api/booking/trip/now'", body)                                              # the ONE answer first
        self.assertIn("n.kind !== 'group'", body)                                                    # a movement only for a group trip
        self.assertNotIn("bookingReq('/api/booking/group/list')", body)                             # never "the open movement"


class Ratchet(unittest.TestCase):
    def test_the_one_ratchet(self):
        """Sasha 403 · 398's ratchet saw calls only and kept its own list; the ONE list and detector are 403's."""
        from tests import test_s403_one_trip_reader as R403, trip_readers as R
        self.assertEqual(set(R.readers()), R403.NOT_YET_CLEAN)


if __name__ == "__main__":
    unittest.main()
