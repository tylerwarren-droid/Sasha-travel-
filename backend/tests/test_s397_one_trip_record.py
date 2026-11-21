"""Sasha 397 · 395 (2) · THE ONE TRIP RECORD T and its ONE reader (root test: mailbox row 2087; FOR CR: row 2088).

Measured: a group movement already is a set of T's (groups.trip_of → group_members.trip_id) but the plan readers never saw them; get_trip
merged two records by name (394's _named_movement); booked parts were read from the basket's copy; venue bookings never sent their trip.

THE CLASS: a group trip and a personal trip × every door (S2, desktop /next = S2, WhatsApp) → the same trip, found by its name through
ONE reader (trip_record); two named → never a guess; a booked part read from its own record (the Duffel order — basket.live), never the
basket's copy; a venue booking carries trip:T (the one plan its day is on); the alarm's "on your screen" is THIS conversation's screen.

    cd backend && python -m unittest tests.test_s397_one_trip_record -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from unittest import mock

from agapi import s2_memory as MEM, v0 as API, venue_submit as VS
from app.agent import sasha as AG
from booking_signer import basket as BK, groups as G, plan_store as PS, trip_record as TR

ACCT = "00000000-0000-4000-8000-000000000397"
PLANS = [{"trip_id": "t_lisbon", "title": "3 Days in Lisbon", "start": "2026-12-09", "end": "2026-12-12", "cities": ["Lisbon"]},
         {"trip_id": "t_rioja", "title": "La Rioja wine week", "start": "2026-12-20", "end": "2026-12-27", "cities": [{"name": "Logroño"}]}]
MOVES = [{"id": "mv_yerevan", "destination": "Yerevan", "company": "Lusa Obras Demo", "starts_on": "2026-12-15", "ends_on": "2026-12-20"}]


def run(c):
    return asyncio.run(c)


class Records(unittest.TestCase):
    def setUp(self):
        st = mock.Mock()
        st.trips = mock.AsyncMock(return_value=MOVES)
        for p in (mock.patch.object(PS, "plans", mock.AsyncMock(return_value=PLANS)), mock.patch.object(G, "store", lambda: st)):
            p.start()
            self.addCleanup(p.stop)


class TheTripTheirWordsName(Records):
    def test_one_reader_finds_each_trip_by_its_name(self):
        self.assertEqual(run(TR.find(ACCT, "Show me the Yerevan trip"))["movement_id"], "mv_yerevan")
        self.assertEqual(run(TR.find(ACCT, "What's on my Lisbon trip?"))["trip_id"], "t_lisbon")
        self.assertEqual(run(TR.find(ACCT, "how is Logrono looking"))["trip_id"], "t_rioja")           # a city of the plan
        self.assertIn("several", run(TR.find(ACCT, "Yerevan or Lisbon first?")))                       # never a guess
        self.assertIsNone(run(TR.find(ACCT, "What's on my trip?")))                                    # none named: the latest, as before

    def get(self, said, via):
        cards = []

        async def card(account, mid=None):
            cards.append(mid)
            return {"title": "Lusa Obras Demo → Yerevan", "rows": [], "say": "The master list."}
        lisbon = {"trip_id": "t_lisbon", "title": "3 Days in Lisbon", "start": "2026-12-09", "end": "2026-12-12", "plan": {"days": []}}
        with mock.patch.object(G, "card", card), mock.patch.object(PS, "by_id", mock.AsyncMock(return_value=lisbon)), \
                mock.patch.object(BK, "items", mock.AsyncMock(return_value=[])), \
                mock.patch.object(BK, "trip_figures", mock.AsyncMock(return_value={"total_eur": None, "party": 1})):
            return run(API.get_trip(API.Ctx(account=ACCT, user_said=said, surface="s2", via=via), {})), cards

    def test_every_door_the_same_trip(self):
        for via in ("page", "wa"):   # S2 and desktop /next (one page) · WhatsApp
            got, cards = self.get("Show me the Yerevan trip", via)
            self.assertEqual((cards, got["group_trip"]), (["mv_yerevan"], "Yerevan"), via)
            got, cards = self.get("What's on my Lisbon trip?", via)
            self.assertEqual((cards, got["trip_id"]), ([], "t_lisbon"), via)

    def test_two_named_is_asked_never_guessed(self):
        with self.assertRaises(API.ToolError) as e:
            self.get("Yerevan or Lisbon?", "page")
        self.assertEqual(e.exception.code, "several_trips")


class BookedFromItsOwnRecord(Records):
    def test_a_booked_part_is_read_from_its_record_never_the_basket(self):
        copy = {"kind": "flight", "state": "booked", "order_id": "ord_1", "snapshot": {"departs": "2026-12-09T07:00", "owner": "Iberia"}}
        live = {**copy, "snapshot": {"departs": "2026-12-09T09:30", "owner": "Iberia"}, "live": True}   # the Duffel order, changed since
        lisbon = {"trip_id": "t_lisbon", "title": "3 Days in Lisbon", "plan": {"days": []}}
        with mock.patch.object(PS, "by_id", mock.AsyncMock(return_value=lisbon)), mock.patch.object(BK, "items", mock.AsyncMock(return_value=[copy])), \
                mock.patch.object(BK, "live", mock.AsyncMock(return_value=[live])) as lv, \
                mock.patch.object(BK, "trip_figures", mock.AsyncMock(return_value={"total_eur": 120.0, "party": 1})), \
                mock.patch.object(API, "_flight_out", lambda snap, r: {"departs": snap.get("departs")}):
            got = run(API.get_trip(API.Ctx(account=ACCT, user_said="What's on my Lisbon trip?", surface="s2"), {}))
        lv.assert_awaited()
        self.assertEqual(got["flights"], [{"departs": "2026-12-09T09:30"}])                            # the record's, not the copy's 07:00


class EveryBookingCarriesItsTrip(Records):
    def sent(self, date):
        bodies = []

        async def call(account, op, body, approval=None):
            bodies.append(body)
            return {"ok": True, "result": {"prepared_id": "vpr_" + "0" * 32}}
        with mock.patch.object(VS, "_call", call), mock.patch.object(VS, "end_user", mock.AsyncMock(return_value="eu_1")):
            run(VS.prepare(ACCT, {"name": "Casa"}, {"name": "T"}, date, "21:00", 2))
        return bodies[-1]

    def test_a_venue_booking_carries_the_trip_its_day_is_on(self):
        self.assertEqual(self.sent("2026-12-10")["external_ref"], "trip:t_lisbon")
        self.assertNotIn("external_ref", self.sent("2026-11-30"))                                     # on no trip: none, never a guess


class TheConversationsScreen(unittest.TestCase):
    def test_a_card_on_this_conversations_screen_is_true(self):
        MEM._MEM.clear()
        MEM._MEM[ACCT] = {"messages": [MEM.message("out", "s2", "Here are three places.", cards=[{"kind": "venues"}])]}
        self.assertTrue(run(MEM.screen_has_cards(ACCT)))
        MEM._MEM[ACCT] = {"messages": [MEM.message("out", "wa", "Here are three places.", cards=[{"kind": "venues"}])]}
        self.assertFalse(run(MEM.screen_has_cards(ACCT)))                                             # WhatsApp has no screen
        self.assertIsNone(AG.state_word_alarm("Taverna Correo is on your screen.", screen_drawn=True))
        self.assertIn("screen_before", inspect.getsource(AG.turn))


class Ratchets(unittest.TestCase):
    def test_one_reader_no_merge_of_two_records(self):
        self.assertFalse(hasattr(API, "_named_movement"))
        src = inspect.getsource(API.get_trip)
        self.assertIn("TR.find(", src)
        self.assertIn("TR.booked_parts(", src)


if __name__ == "__main__":
    unittest.main()
