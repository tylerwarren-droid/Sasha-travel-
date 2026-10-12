"""Sasha 251 · RIGHT DATES — found live on /s2 (12 Oct): "Plan a weekend in Lisbon for two, Saturday 24 to Monday 26 October, from
Madrid." → the flight there left FRIDAY 23 (propose_trip searched the out leg on `start - 1 day`); then "Read me back the flights and
hotel." → get_trip had no total, so she gave none.

    RightDates               the trip's dates are decided once (plan_store.dates_for), written on the trip record as they are, and
                             every leg reads that record (plan_store.leg_days): there ON the first day, home ON the last, the stays
                             in between — in propose_trip, in a prefetch, and in the read-back's re-check (basket_book.refresh)
    ReadBackCarriesTheTotal  get_trip carries basket.trip_figures()' total — the same figure as propose_trip, get_total and the
                             Trip tab — with the estimates said as estimates

Offline: fakes only (no Duffel, no Places, no model, no database).
    cd backend && python -m unittest tests.test_s251_dates -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from datetime import date
from unittest import mock

from agapi import v0 as API
from app.agent import sasha as AG
from booking_signer import basket as BK, basket_book as BB, fx as FX, ladder_routes as LR, plan_store as PS, travel as T

ACCOUNT = "00000000-0000-4000-8000-000000000251"
SAID = "Plan a weekend in Lisbon for two, Saturday 24 to Monday 26 October, from Madrid."
ASK = {"destination": "Lisbon, Portugal", "start_date": "2026-10-24", "nights": 2, "party": 2, "origin": "Madrid"}
NO_FX_ENV = {"SASHA_USD_EUR": "", "SASHA_FX_AS_OF": "", "SASHA_GBP_EUR": ""}
run = asyncio.run


def itinerary():
    hotel = {"name": "Memmo Alfama", "price_from": 200, "est": True, "price_label": "est. €180/night"}
    return {"title": "A Weekend in Lisbon", "planner": "world", "country": "Portugal", "country_code": "PT",
            "airports": {"arrive": "LIS", "depart": "LIS"},
            "days": [{"day": 1, "city": "Lisbon", "title": "Alfama", "hotel": dict(hotel)},
                     {"day": 2, "city": "Lisbon", "title": "Belém", "hotel": dict(hotel)},
                     {"day": 3, "city": "Lisbon", "title": "Home", "hotel": ""}]}


class Trips:
    """The `trips` table, just enough of asyncpg for plan_store.save / latest / by_id."""

    def __init__(self):
        self.rows = []

    async def run(self, fn):
        return await fn(self)

    async def fetchrow(self, sql, *args):
        if "and id = $2" in sql:
            return next((r for r in self.rows if str(r["id"]) == str(args[1])), None)
        return None   # no earlier plan to revise

    async def fetchval(self, sql, owner, title, dest, start, end):
        r = {"id": uuid.uuid4(), "title": title, "destinations": dest, "depart_date": start, "return_date": end, "created_at": None}
        self.rows.append(r)
        return r["id"]

    async def fetch(self, sql, *args):
        return list(reversed(self.rows))


class Basket:
    """trip_basket_items in memory: suggest / items / choose / unchoose_flights as basket.py does them."""

    def __init__(self):
        self.rows = []

    async def items(self, account, trip_id, states=BK.LIVE):
        return [r for r in self.rows if r["trip_id"] == trip_id and r["state"] in states]

    async def suggest(self, account, trip_id, kind, found, *, slice_key=None, replace=True):
        if kind == "flight":
            found = [f for f in (BK.ingest_flight(f) for f in found) if f is not None]
        elif replace:
            self.rows = [r for r in self.rows if not (r["trip_id"] == trip_id and r["kind"] == kind and r["state"] == "suggested")]
        ids = []
        for f in found:
            i = str(uuid.uuid4())
            self.rows.append({"id": i, "trip_id": trip_id, "kind": kind, "state": "suggested", "slice_key": slice_key or f.get("slice_key"),
                              "day": f.get("day"), "starts_at": f.get("starts_at"), "ends_at": f.get("ends_at"), "party": f.get("party"),
                              "provider": f["provider"], "provider_ref": f.get("provider_ref"), "snapshot": f.get("snapshot") or {},
                              "price_amount": f.get("price_amount"), "price_currency": f.get("price_currency"),
                              "price_source": f.get("price_source")})
            ids.append(i)
        return ids

    async def choose(self, account, item_id):
        r = next(r for r in self.rows if r["id"] == item_id)
        for o in self.rows:
            if o["kind"] == "flight" and o["state"] == "chosen" and o["slice_key"] == r["slice_key"]:
                o["state"] = "suggested"
        r["state"] = "chosen"
        return r

    async def unchoose_flights(self, account, trip_id):
        for r in self.rows:
            if r["trip_id"] == trip_id and r["kind"] == "flight" and r["state"] == "chosen":
                r["state"] = "suggested"
        return 0


class Duffel:
    """The airline search: two fares on the day ASKED (or none on the days in `empty`) — every search recorded."""

    def __init__(self, empty=()):
        self.asked, self.empty = [], set(empty)

    async def search(self, origin, dest, day, adults=1, limit=3):
        self.asked.append((origin, dest, day))
        if day in self.empty:
            return {"cards": []}
        return {"cards": [
            {"id": f"off_{origin}{dest}{day}_am", "owner": "Duffel Airways", "flights": "ZZ 4029", "from": origin, "to": dest,
             "departs": f"{day}T09:10:00", "arrives": f"{day}T09:25:00", "stops": 0, "minutes": 75, "amount": "92.00", "currency": "EUR"},
            {"id": f"off_{origin}{dest}{day}_pm", "owner": "Duffel Airways", "flights": "ZZ 4031", "from": origin, "to": dest,
             "departs": f"{day}T18:30:00", "arrives": f"{day}T18:45:00", "stops": 0, "minutes": 75, "amount": "104.00", "currency": "EUR"}]}


class World(unittest.TestCase):
    def setUp(self):
        self.trips, self.basket, self.duffel = Trips(), Basket(), getattr(self, "DUFFEL", None) or Duffel()
        API._PREP.pop(ACCOUNT, None)
        self.addCleanup(API._PREP.pop, ACCOUNT, None)
        for p in (mock.patch.dict(os.environ, NO_FX_ENV),
                  mock.patch.object(PS, "STORE_RUN", self.trips.run),
                  mock.patch.object(BK, "items", self.basket.items), mock.patch.object(BK, "suggest", self.basket.suggest),
                  mock.patch.object(BK, "choose", self.basket.choose), mock.patch.object(BK, "unchoose_flights", self.basket.unchoose_flights),
                  mock.patch.object(BB, "store_prices", mock.AsyncMock(return_value=None)),   # the stays keep their estimate
                  mock.patch.object(T, "search", self.duffel.search),
                  mock.patch.object(API, "_build", mock.AsyncMock(side_effect=lambda a, account=None: {
                      "itin": itinerary(), "msg": "Plan a 3-day trip to Lisbon, Portugal for 2 people."}))):   # no date in it: never re-read
            p.start()
            self.addCleanup(p.stop)

    def ctx(self, said=SAID):
        return API.Ctx(account=ACCOUNT, user_said=said, surface="s2")

    def propose(self):
        r = run(API.call(self.ctx(), "propose_trip", dict(ASK)))
        self.assertTrue(r["ok"], r)
        return r["result"]


class RightDates(World):
    def test_lisbon_saturday_24_to_monday_26(self):
        res = self.propose()
        self.assertTrue(res["flight_out"]["departs"].startswith("2026-10-24"), res["flight_out"])   # Saturday — never Friday 23
        self.assertTrue(res["flight_back"]["departs"].startswith("2026-10-26"), res["flight_back"])  # Monday
        self.assertEqual(res["dates"], {"start": "2026-10-24", "end": "2026-10-26", "nights": 2})
        self.assertNotIn("flight_note", res)
        self.assertEqual(sorted(d for _, _, d in self.duffel.asked), ["2026-10-24", "2026-10-26"])   # searched on those days only
        for leg, day in (("out", "2026-10-24"), ("back", "2026-10-26")):
            self.assertTrue(all(o["departs"].startswith(day) for o in res["flight_options"][leg]), leg)
        rec = self.trips.rows[-1]                                                                     # the ONE trip record
        self.assertEqual((rec["depart_date"], rec["return_date"]), (date(2026, 10, 24), date(2026, 10, 26)))
        stays = [r for r in self.basket.rows if r["kind"] == "stay"]
        self.assertEqual([(s["day"], s["snapshot"]["checkout"], s["snapshot"]["nights"]) for s in stays], [("2026-10-24", "2026-10-26", 2)])
        chosen = sorted((r["slice_key"].split(":")[0], r["day"]) for r in self.basket.rows if r["kind"] == "flight" and r["state"] == "chosen")
        self.assertEqual(chosen, [("back", "2026-10-26"), ("out", "2026-10-24")])

    def test_the_plan_carries_its_dates_and_the_store_never_re_reads_them_from_a_sentence(self):
        plan = {**itinerary(), "dates": PS.dates_for("2026-10-24", 2)}
        tid = run(PS.save(ACCOUNT, plan, "Plan a trip from 3 March for 2 people.", __import__("datetime").datetime(2026, 10, 12)))
        rec = next(r for r in self.trips.rows if str(r["id"]) == tid)
        self.assertEqual((rec["depart_date"], rec["return_date"]), (date(2026, 10, 24), date(2026, 10, 26)))
        self.assertEqual(PS.leg_days({"start": date(2026, 10, 24), "end": date(2026, 10, 26)}), ("2026-10-24", "2026-10-26"))
        self.assertEqual(PS.dates_for("2026-10-24", 2), {"start": "2026-10-24", "end": "2026-10-26", "nights": 2})

    def test_flights_prefetched_on_other_days_are_searched_again(self):
        async def done(v):
            return v
        stale = {"legs": [("out", "Madrid", "LIS", "2026-10-23"), ("back", "LIS", "Madrid", "2026-10-26")],
                 "found": [{"cards": []}, {"cards": []}], "asked": {"out": "2026-10-23", "back": "2026-10-26"}}

        async def prep():
            loop = asyncio.get_running_loop()
            API._PREP[ACCOUNT] = {"key": API._prep_key(ASK), "args": dict(ASK),
                                  "itin": loop.create_task(done({"itin": itinerary(), "msg": "Plan a 3-day trip."})),
                                  "flights": {"madrid": loop.create_task(done(stale))}}
            return await API.call(self.ctx(), "propose_trip", dict(ASK))
        r = run(prep())
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["result"]["flight_out"]["departs"].startswith("2026-10-24"))
        self.assertEqual(r["result"]["prefetched"], {"itinerary": True, "flights": False})

    def test_a_prefetch_searches_the_trips_own_days(self):
        async def go():
            await API.call(self.ctx(), "prepare_trip", dict(ASK))
            return await API._PREP[ACCOUNT]["flights"]["madrid"]
        got = run(go())
        self.assertEqual(got["asked"], {"out": "2026-10-24", "back": "2026-10-26"})

    def test_another_day_is_only_taken_when_the_trips_day_has_none_and_it_is_said(self):
        self.duffel.empty = {"2026-10-24"}
        res = self.propose()
        self.assertTrue(res["flight_out"]["departs"].startswith("2026-10-25"))                     # the nearest day after, not before
        self.assertIn("no flight on Sat 24 Oct", res["flight_note"])
        self.assertIn("1 day later; say so", res["flight_note"])

    def test_the_read_backs_recheck_chooses_on_the_records_days(self):
        p = {"trip_id": str(uuid.uuid4()), "title": "Lisbon", "start": date(2026, 10, 24), "end": date(2026, 10, 26),
             "plan": {**itinerary(), "party": 2}}
        days = PS.merge(p, [])["days"]
        picks = mock.AsyncMock(return_value={"id": "x"})
        with mock.patch.object(BB, "_plan_dates", mock.AsyncMock(return_value=(p, days, date(2026, 10, 24)))), \
                mock.patch.object(BB, "_choose_cheapest", picks), mock.patch.object(BB, "price", mock.AsyncMock(return_value={"eur": 1})):
            run(BB.refresh(ACCOUNT, "Madrid"))
        self.assertEqual(sorted(c.args[4] for c in picks.call_args_list), ["2026-10-24", "2026-10-26"])   # not the 23rd, not the 27th


class ReadBackCarriesTheTotal(World):
    def test_get_trip_says_the_one_total(self):
        proposed = self.propose()["total_eur"]
        trip = run(API.call(self.ctx("Read me back the flights and hotel."), "get_trip", {}))["result"]
        total = run(API.call(self.ctx(), "get_total", {}))["result"]["total_eur"]
        figs = run(BK.trip_figures(ACCOUNT))["total_eur"]
        p = run(PS.latest(ACCOUNT))
        tab = run(LR.trip_total(ACCOUNT, p["trip_id"], p))["total_eur"]
        stay = round(200 * 2 * FX.DEFAULT["USD"], 2)
        self.assertEqual({proposed, trip["total_eur"], total, figs, tab}, {round(92.0 + 104.0 + stay, 2)})   # ONE figure everywhere
        self.assertEqual((trip["party"], trip["currency"], trip["start"], trip["end"]), (2, "EUR", "2026-10-24", "2026-10-26"))
        self.assertIn("Memmo Alfama", trip["estimates"])                                               # an estimate said as one
        self.assertIn("end with total_eur", trip["how"])
        self.assertIn("never add", trip["how"].lower())

    def test_the_guard_allows_the_figure_she_reads_back(self):
        self.propose()
        figs: dict = {}
        allowed = run(AG._basket_amounts(self.ctx(), figs))
        trip = run(API.call(self.ctx(), "get_trip", {}))["result"]
        self.assertEqual(trip["total_eur"], figs["total_eur"])
        self.assertIn(trip["total_eur"], allowed)

    def test_nothing_priced_is_said_never_euro_zero(self):
        self.propose()
        self.basket.rows.clear()
        trip = run(API.call(self.ctx(), "get_trip", {}))["result"]
        self.assertIsNone(trip["total_eur"])
        self.assertEqual(trip["total_note"], "nothing in this trip is priced yet")


if __name__ == "__main__":
    unittest.main()
