"""Sasha 280 · T60 — FLIGHT-ONLY MUST WORK (Tyler's demo, 21 Oct 13:44: asked for a flight only, she kept bundling hotels and said she
couldn't do flights alone). His 18 Oct decision: standalone flights and hotels, NO packages. Offline: fakes only (no Duffel, no
database, no model). Each gate fails on 279's code.

THE RULE THAT WAS (and where it lived):
  code    agapi.v0._offer_flights — no trip → "No trip yet, so none of these can be booked: propose_trip first" (Sasha 249 OFFERED ==
          BOOKABLE); v0._plan — "propose_trip first"; booking_signer.basket_book._plan_dates — a record with no itinerary days is not
          bookable; basket_book.refresh — nothing chosen → the cheapest flight out AND back chosen; and a flight searched while ANY trip
          existed went into that trip's basket, so the read-back carried its hotels.
  prompt  the shared text: "Once she knows enough, she puts a proposal together. Somewhere to stay each night…", "The moment she knows
          the destination, dates and party, she calls prepare_trip", "Flights and hotels are one trip".
THE RULE NOW: the trip record holds what the person asked for. One thing is bookable on its own (plan_store.single); it joins a
trip only when it is part of it (v0.flight_fits). /s2 (WhatsApp's brain too) and /next with parity; old S1 (parity off) as before.

    cd backend && python -m unittest tests.test_s280 -v
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import unittest
from datetime import date
from unittest import mock

from agapi import v0 as API
from app.agent import s2 as S2
from booking_signer import basket as BK, basket_book as BB, plan_store as PS
from tests.test_s253_offered import Basket, card

ACCT = "00000000-0000-4000-8000-000000000280"
KENYA = "11111111-1111-4111-8111-111111111280"
run = asyncio.run


def lis(i, eur, day="2026-11-12", frm="MAD", to="LIS"):
    c = card(i, "Iberia", "08:30", "09:45", eur, day=day)
    return {**c, "from": frm, "to": to, "from_city": "Madrid" if frm == "MAD" else "Lisbon", "to_city": "Lisbon" if to == "LIS" else "Madrid"}


class World:
    """Trip records and the basket, in memory. `records`: trip_id → the latest() shape; the newest touched is latest."""

    def __init__(self, proposal=False):
        self.records, self.order, self.basket, self.singles = {}, [], Basket(), []
        if proposal:   # a Kenya proposal with hotels (the kind of trip she kept bundling into)
            self.records[KENYA] = {"trip_id": KENYA, "title": "9 days in Kenya", "start": date(2026, 12, 1), "end": date(2026, 12, 9),
                                   "cities": ["Nairobi", "Mombasa"], "plan": {"party": 2, "days": [
                                       {"date": "2026-12-01", "city": "Nairobi", "hotel": {"name": "Hotel A", "price_from": 100}},
                                       {"date": "2026-12-09", "city": "Mombasa"}]}}
            self.order.append(KENYA)

    async def latest(self, account, hint=None, strict=False):
        return self.records[self.order[-1]] if self.order else None

    async def by_id(self, account, tid):
        return self.records.get(tid)

    async def touch(self, account, tid):
        self.order = [x for x in self.order if x != tid] + [tid]

    async def single(self, account, kind, title, cities, start, end, days=None, party=None, extra=None):
        tid = f"22222222-2222-4222-8222-{len(self.records) + 1:012d}"
        self.records[tid] = {"trip_id": tid, "title": title, "start": start, "end": end, "cities": cities,
                             "plan": {"title": title, "single": kind, "days": list(days or []), **({"party": party} if party else {}), **(extra or {})}}
        self.order.append(tid)
        self.singles.append((kind, title))
        return tid

    def __enter__(self):
        b = self.basket
        self.p = [mock.patch.object(PS, "latest", self.latest), mock.patch.object(PS, "by_id", self.by_id),
                  mock.patch.object(PS, "touch", self.touch), mock.patch.object(PS, "single", self.single),
                  mock.patch.object(BK, "suggest", b.suggest), mock.patch.object(BK, "items", b.items),
                  mock.patch.object(BK, "choose", b.choose)]
        for x in self.p:
            x.start()
        return self

    def __exit__(self, *a):
        for x in self.p:
            x.stop()


def ctx(surface="s2", said="book me a flight from Madrid to Lisbon on 12 November"):
    return API.Ctx(account=ACCT, surface=surface, user_said=said)


def search(c, cards, origin="Madrid", dest="Lisbon", day="2026-11-12"):
    async def healed(o, d, dd, party):
        return {"cards": cards}, dd
    with mock.patch.object(API, "_search_healed", healed):
        return run(API.search_flights(c, {"origin": origin, "destination": dest, "date": day, "passengers": 1}))


class TheRule(unittest.TestCase):
    def test_a_flight_belongs_to_a_trip_only_when_it_is_part_of_it(self):
        kenya = World(proposal=True).records[KENYA]
        w = API._place_words
        self.assertEqual(API.flight_fits(kenya, w("Madrid", "MAD"), w("Nairobi", "NBO"), "2026-12-01"), "out")
        self.assertEqual(API.flight_fits(kenya, w("Mombasa", "MBA"), w("Madrid", "MAD"), "2026-12-09"), "back")
        self.assertIsNone(API.flight_fits(kenya, w("Madrid", "MAD"), w("Lisbon", "LIS"), "2026-12-01"))     # another place
        self.assertIsNone(API.flight_fits(kenya, w("Madrid", "MAD"), w("Nairobi", "NBO"), "2027-02-01"))    # another time
        one = {"plan": {"single": "flight", "route": {"from": sorted(w("Madrid", "MAD")), "to": sorted(w("Lisbon", "LIS"))}}}
        self.assertEqual(API.flight_fits(one, w("Lisbon", "LIS"), w("Madrid", "MAD"), "2026-11-15"), "back")   # its way home
        self.assertIsNone(API.flight_fits({"plan": {"single": "stay"}}, w("Madrid"), w("Lisbon"), "2026-11-12"))


class FlightOnItsOwn(unittest.TestCase):
    def test_gate_a_flight_only_is_bookable_with_no_trip(self):
        """THE GATE (21 Oct 13:44): fails on 279 — "No trip yet, so none of these can be booked: propose_trip first"."""
        with World() as wd:
            r = search(ctx(), [lis("a", 72.0), lis("b", 64.0)])
        self.assertTrue(r["stored"])
        self.assertTrue(all(f.get("option_id") for f in r["flights"]), r["flights"])   # each one bookable
        self.assertNotIn("propose_trip", json.dumps(r))
        self.assertEqual(wd.singles, [("flight", "Flight Madrid → Lisbon")])
        self.assertFalse([x for x in wd.basket.rows if x["kind"] == "stay"])      # no hotel pushed

    def test_gate_it_never_joins_a_trip_it_isnt_part_of(self):
        """A Kenya proposal with hotels exists; a flight to Lisbon is its own — never a leg of Kenya (fails on 279: it joined it)."""
        with World(proposal=True) as wd:
            search(ctx(), [lis("a", 72.0)])
            lat = run(wd.latest(ACCT))
        self.assertNotEqual(lat["trip_id"], KENYA)
        self.assertEqual(PS.is_single(lat), "flight")

    def test_the_way_back_joins_its_own_flight(self):
        with World() as wd:
            search(ctx(), [lis("a", 72.0)])
            search(ctx(said="and a flight back on the 15th"), [lis("r", 70.0, day="2026-11-15", frm="LIS", to="MAD")], "Lisbon", "Madrid", "2026-11-15")
        self.assertEqual(len(wd.singles), 1)
        self.assertEqual(sorted({x["slice_key"].split(":")[0] for x in wd.basket.rows}), ["back", "out"])

    def test_it_books_with_only_what_was_asked(self):
        """The read-back of a flight on its own: nothing chosen → the cheapest SHOWN on its one leg; never a way back, never a hotel."""
        with World() as wd:
            search(ctx(), [lis("a", 72.0), lis("b", 64.0)])
            p = run(wd.latest(ACCT))
            got = run(BB._plan_dates(ACCT))
            self.assertEqual((got[1], got[2]), ([], date(2026, 11, 12)))
            back = mock.AsyncMock()
            with mock.patch.object(BB, "_choose_cheapest", back), mock.patch.object(BB, "store_prices", mock.AsyncMock(return_value=None)), \
                    mock.patch.object(BB, "_validate_flight", mock.AsyncMock(return_value={"note": None})), \
                    mock.patch.object(BB, "price", mock.AsyncMock(return_value={"lines": ["x"], "sha256": "s", "eur": 64.0})):
                run(BB.refresh(ACCT, "Madrid"))
            chosen = [x for x in wd.basket.rows if x["state"] == "chosen"]
        back.assert_not_called()                                    # no flight home searched or added
        self.assertEqual([(x["price_amount"], x["slice_key"].split(":")[0]) for x in chosen], [(64.0, "out")])
        self.assertEqual(p["plan"]["single"], "flight")

    def test_old_s1_parity_off_is_as_before(self):
        with World() as wd, mock.patch("app.agent.sasha.s1_parity", lambda: False):
            r = search(ctx(surface="s1"), [lis("a", 72.0)])
        self.assertEqual(r.get("how"), "No trip yet, so none of these can be booked: propose_trip first, then pick one.")
        self.assertEqual(wd.singles, [])


class HotelOnItsOwn(unittest.TestCase):
    def test_a_hotel_on_its_own(self):
        with World() as wd:
            API._STAYS[ACCT] = {"lisbon": [{"name": "Casa do Rio", "est_eur": 120.0}]}
            synced = mock.AsyncMock(return_value=["s1"])
            with mock.patch.object(BK, "sync_stays", synced), mock.patch.object(BB, "store_prices", mock.AsyncMock(return_value=None)), \
                    mock.patch.object(API, "_total", mock.AsyncMock(return_value={"total_eur": 360.0})):
                with self.assertRaises(API.ToolError) as no_dates:
                    run(API.swap_stay(ctx(said="a hotel in Lisbon"), {"city": "Lisbon", "stay_name": "Casa do Rio"}))
                r = run(API.swap_stay(ctx(said="that one, 3 nights from the 12th"),
                                      {"city": "Lisbon", "stay_name": "Casa do Rio", "check_in": "2026-11-12", "nights": 3}))
        self.assertEqual(no_dates.exception.code, "stay_dates_needed")
        self.assertTrue(r["on_its_own"])
        self.assertEqual(wd.singles, [("stay", "Casa do Rio · Lisbon")])
        days = synced.call_args.args[2]
        self.assertEqual(len(days) - 1, 3)                                       # three nights, then the way home
        self.assertFalse([x for x in wd.basket.rows if x["kind"] == "flight"])   # no flight pushed

    def test_a_hotel_on_its_own_never_gets_flights_chosen(self):
        src = __import__("inspect").getsource(BB.refresh)
        self.assertIn("elif not chosen_fl and not PS.is_single(p):", src)


class HerWords(unittest.TestCase):
    def test_gate_her_prompt_never_ties_a_flight_to_a_hotel(self):
        t = S2.s2_system()
        self.assertNotIn("Flights and hotels are one trip", t)
        self.assertIn("never says she can't book one alone", t)
        self.assertIn("- **When they ask for a trip,** the moment she knows", t)
        from app.services import persona as P
        parity = S2.standalone(P.AGENT_SYSTEM)
        self.assertNotIn("Once she knows enough, she puts a proposal together", parity)   # /next with parity: the same rule

    def test_the_tools_say_it(self):
        by = {t["name"]: t for t in API.TOOLS}
        s = {n: S2.standalone_tool(API.schema_for_model(by[n])) for n in ("search_flights", "propose_trip", "prepare_trip", "swap_stay")}
        self.assertIn("bookable ON ITS OWN", s["search_flights"]["description"])
        self.assertTrue(s["search_flights"]["description"].startswith("[Magellan] "))
        self.assertIn("Never for a flight or a hotel on its own", s["propose_trip"]["description"])
        self.assertTrue({"check_in", "nights"} <= set(s["swap_stay"]["input_schema"]["properties"]))

    def test_old_s1_parity_off_words_untouched(self):
        from app.agent import sasha as S
        from app.services import persona as P
        self.assertIn("Flights and hotels are one trip", P.AGENT_SYSTEM)
        by = {t["name"]: t for t in S.tools_for_model()}
        self.assertTrue(by["propose_trip"]["description"].startswith("[Magellan] THE PROPOSAL: a day-by-day itinerary"))
        self.assertNotIn("check_in", by["swap_stay"]["input_schema"]["properties"])

    def test_the_card_says_each_on_its_own(self):
        from agapi import s2_home as H
        items = [i for g in H.CAPABILITIES for i, _ in g["items"]]
        self.assertIn("A flight or a hotel on its own — or a whole trip", items)
        self.assertNotIn("Flights and hotels for a trip", items)


if __name__ == "__main__":
    unittest.main()
