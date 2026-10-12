"""Sasha 249 · EU 245 steps 3–4 — ONE TOTAL, ONE CURRENCY, ONE PARTY; OFFERED == BOOKABLE (docs/sasha/one-truth-spec.md §3 T4–T7).
Offline: fakes only (no Duffel, no AgAPI, no Stripe, no Places, no database).

    T4 one total     get_total / the Trip tab / the read-back / the guard read ONE figure (basket.trip_figures, read only);
                     hold_booking is the only re-check (refresh) and says when it moved the total
    T5 one currency  every amount in euros at fx.py's one dated rate; converted at ingestion, never the $ estimate
    T6 one party     the plan's, else the basket rows', else asked — never a silent 1 or 2
    T7 offered == bookable   options stored before shown; a new search appends (supersedes, never deletes in the turn);
                     _find_option matches (leg, time), the leg from the person's words ("home" = back)

    cd backend && python -m unittest tests.test_s249_total_options -v
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from agapi import v0 as API
from app.agent import sasha as AG
from booking_signer import basket as BK, basket_book as BB, fx as FX, ladder_routes as LR

ACCOUNT = "00000000-0000-4000-8000-000000000249"
TRIP = "11111111-1111-4111-8111-111111111249"
run = asyncio.run
D1 = (date.today() + timedelta(days=12)).isoformat()
D3 = (date.today() + timedelta(days=14)).isoformat()
NO_FX_ENV = {"SASHA_USD_EUR": "", "SASHA_FX_AS_OF": "", "SASHA_GBP_EUR": ""}


def ctx(said=None):
    return API.Ctx(account=ACCOUNT, user_said=said)


def flight(i, leg, day, hhmm, eur, state="chosen", owner="Iberia", num="IB 3116", frm="MAD", to="LIS", **kw):
    return {"id": i, "kind": "flight", "state": state, "day": day, "slice_key": f"{leg}:{frm}→{to} {day}" if leg else f"{frm}→{to} {day}",
            "party": 2, "provider_ref": f"off_{i}", "price_amount": eur, "price_currency": "EUR", "price_source": "quoted",
            "snapshot": {"id": f"off_{i}", "owner": owner, "flights": num, "from": frm, "to": to, "departs": f"{day}T{hhmm}:00",
                         "arrives": f"{day}T{hhmm}:00", "stops": 0, "minutes": 75, "amount": f"{eur:.2f}", "currency": "EUR", **kw}}


def stay(i, eur, state="suggested", source="estimate"):
    return {"id": i, "kind": "stay", "state": state, "day": D1, "party": 2, "price_amount": eur, "price_currency": "EUR",
            "price_source": source, "snapshot": {"name": "Memmo Alfama", "city": "Lisbon", "nights": 2, "checkout": D3}}


def rows_496():   # D1's trip: two flights chosen + the stay = €496.10; an option not chosen is never counted
    return [flight("a", "out", D1, "08:30", 85.0), flight("b", "back", D3, "19:05", 98.3, owner="TAP", num="TP 1026", frm="LIS", to="MAD"),
            stay("s", 312.8), flight("c", "back", D3, "17:48", 140.0, state="suggested", owner="TAP", num="TP 1030", frm="LIS", to="MAD")]


PLAN = {"trip_id": TRIP, "title": "Lisbon", "plan": {"party": 2, "days": [{"day": 1, "date": D1, "city": "Lisbon"}]}}


def items_of(rows):
    async def items(account, trip_id, states=BK.LIVE):
        return [r for r in rows if r["state"] in states]
    return items


# ── fx.py · the one dated rate ───────────────────────────────────────────────────────────────────────────────────────────────

class OneRate(unittest.TestCase):
    def test_the_rate_and_its_date(self):
        with mock.patch.dict(os.environ, NO_FX_ENV):
            self.assertEqual(FX.rate("EUR"), 1.0)
            self.assertEqual(FX.rate("usd"), FX.DEFAULT["USD"])
            self.assertIsNone(FX.rate("GBP"))                                 # never a guessed rate
            self.assertIsNone(FX.rate("USD", configured_only=True))           # the cost report: unset is unknown
            self.assertEqual(FX.to_eur("100", "USD"), round(100 * FX.DEFAULT["USD"], 2))
            self.assertEqual(FX.stamp("USD"), {"currency": "USD", "rate": FX.DEFAULT["USD"], "as_of": FX.AS_OF})
        with mock.patch.dict(os.environ, {"SASHA_USD_EUR": "0.9", "SASHA_GBP_EUR": "1.17", "SASHA_FX_AS_OF": "2026-10-01"}):
            self.assertEqual((FX.to_eur(100, "USD"), FX.to_eur(100, "GBP"), FX.as_of()), (90.0, 117.0, "2026-10-01"))
            self.assertEqual(FX.rate("USD", configured_only=True), 0.9)

    def test_every_conversion_site_reads_fx(self):
        from app.services import conductor as C, world_itinerary as W
        from booking_signer import route_costs as RC
        with mock.patch.dict(os.environ, {"SASHA_USD_EUR": "0.5"}):
            self.assertEqual(C._eur190(100), 50)
            self.assertEqual(RC.usd_eur(), 0.5)
        import inspect
        for mod in (W, C, BK, API):   # no second USD→EUR constant left anywhere it used to live
            self.assertNotIn("0.92", inspect.getsource(mod).replace("Sasha 249", ""), mod.__name__)


# ── T5 · one currency ─────────────────────────────────────────────────────────────────────────────────────────────────────────

class OneCurrency(unittest.TestCase):
    def test_a_usd_offer_is_converted_at_ingestion_never_dropped(self):
        with mock.patch.dict(os.environ, NO_FX_ENV):
            got = BK.in_eur([{"id": "u", "amount": "200.00", "currency": "USD"}, {"id": "g", "amount": "50", "currency": "GBP"}])
            self.assertEqual([c["id"] for c in got], ["u"])                  # GBP has no rate: it can't join a euro trip
            self.assertEqual(got[0]["price_eur"], round(200 * FX.DEFAULT["USD"], 2))
            self.assertEqual((got[0]["amount"], got[0]["currency"]), ("200.00", "USD"))   # the airline's own figure kept (order, re-check)
            self.assertEqual(got[0]["fx"]["as_of"], FX.AS_OF)
            row = BK.ingest_flight({"price_amount": 200.0, "price_currency": "USD", "snapshot": {"owner": "UX"}})
            self.assertEqual((row["price_amount"], row["price_currency"]), (round(200 * FX.DEFAULT["USD"], 2), "EUR"))
            self.assertEqual(row["snapshot"]["fx"]["amount"], 200.0)
            self.assertEqual(API._flight_out(got[0])["price_eur"], got[0]["price_eur"])

    def test_every_figure_is_euros_and_the_trip_tab_never_falls_back_to_dollars(self):
        rows = rows_496()
        rows[0] = {**rows[0], "price_amount": 100.0, "price_currency": "USD"}   # an older row stored in dollars
        with mock.patch.dict(os.environ, NO_FX_ENV):
            f = BK.figures_of(rows, TRIP, PLAN)
            self.assertEqual(f["currency"], "EUR")
            self.assertEqual(f["total_eur"], round(100 * FX.DEFAULT["USD"] + 98.3 + 312.8, 2))
            self.assertTrue(all(l["eur"] is not None for l in f["lines"]))
            self.assertEqual(next(l for l in f["lines"] if l["id"] == "a")["fx"]["currency"], "USD")
            with mock.patch.object(BK, "items", items_of(rows)):
                tab = run(LR.trip_total(ACCOUNT, TRIP, PLAN))
        self.assertIsNotNone(tab)                                             # never None (→ the $ estimate) while the basket has rows
        self.assertEqual(tab["total_eur"], f["total_eur"])


# ── T4 · one total ────────────────────────────────────────────────────────────────────────────────────────────────────────────

class OneTotal(unittest.TestCase):
    def setUp(self):
        self.rows = rows_496()
        boom = mock.AsyncMock(side_effect=AssertionError("a read re-priced the trip"))
        for p in (mock.patch.object(BK, "items", items_of(self.rows)), mock.patch.object(API, "_plan", mock.AsyncMock(return_value=PLAN)),
                  mock.patch.object(PS_(), "latest", mock.AsyncMock(return_value=PLAN)),
                  mock.patch.object(BB, "quote", boom), mock.patch.object(BB, "refresh", boom), mock.patch.object(BB, "store_prices", boom)):
            p.start()
            self.addCleanup(p.stop)

    def test_get_total_is_the_figures_and_never_re_prices(self):
        r = run(API.call(ctx(), "get_total", {}))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["total_eur"], 496.1)                    # 85 + 98.3 + 312.8; the unchosen 17:48 not counted
        self.assertEqual((r["result"]["currency"], r["result"]["party"], r["result"]["trip_id"]), ("EUR", 2, TRIP))
        self.assertIn("exactly", r["result"]["how"])
        self.assertEqual(r["result"]["breakdown"]["total_eur"], 496.1)

    def test_chat_trip_tab_and_figures_are_one_number(self):
        chat = run(API.call(ctx(), "get_total", {}))["result"]["total_eur"]
        tab = run(LR.trip_total(ACCOUNT, TRIP, PLAN))["total_eur"]
        figs = run(BK.trip_figures(ACCOUNT, TRIP, PLAN))["total_eur"]
        self.assertEqual({chat, tab, figs}, {496.1})
        self.assertEqual(BB.lines_of(BK.to_book(self.rows), 2)[-2], "Total €496.10 (TEST) — ONE tap to pay on your phone: Apple Pay or "
                                                                     "a saved card on Stripe's TEST page.")   # the read-back header

    def test_the_turn_end_guard_reads_without_re_pricing(self):
        figs: dict = {}
        allowed = run(AG._basket_amounts(ctx(), figs))
        self.assertEqual(figs["total_eur"], 496.1)
        self.assertIn(496.1, allowed)

    def test_the_total_holds_after_payment(self):
        held = [{**r, "state": "pending_payment"} if r["state"] == "chosen" or r["kind"] == "stay" else r for r in self.rows]
        self.assertEqual(BK.figures_of(held, TRIP, PLAN)["total_eur"], 496.1)
        self.assertEqual(BK.figures_of(held, TRIP, PLAN)["to_pay_eur"], 0.0)


def PS_():
    from booking_signer import plan_store as PS
    return PS


class TheGuardChecksTheTotalExactly(unittest.TestCase):
    FIG = {"total_eur": 496.1, "to_pay_eur": 496.1}

    def test_the_trip_total_said_must_be_the_figure(self):
        allowed = {496.1, 479.0, 85.0, 45.0}
        ok = ["About €496 for the two of you, everything included.", "The whole trip comes to €496.10.",
              "Flights are €85 and the total for the trip is €496.10."]
        for s in ok:
            self.assertEqual(AG.guard_check(s, allowed, False, self.FIG), [], s)
        bad = AG.guard_check("The whole trip comes to €479, all in.", allowed, False, self.FIG)   # an earlier total, still "allowed"
        self.assertTrue(bad and bad[0].startswith("total:"), bad)
        self.assertIn("€496.10", bad[0])

    def test_other_prices_keep_the_per_price_allowance(self):
        allowed = {45.0, 250.0}
        for s in ("Dinner at Casa Marea is about €45 a head.", "Your refund total comes to €250.", "Lunch for both of you, about €45."):
            self.assertEqual(AG.guard_check(s, allowed, False, self.FIG), [], s)
        self.assertTrue(AG.guard_check("Dinner is €99.", allowed, False, self.FIG))   # a price no tool gave: refused as before

    def test_without_figures_it_is_the_old_check(self):
        self.assertEqual(AG.guard_check("The whole trip comes to about €1,468.", {1468.14}, False), [])
        self.assertTrue(AG.guard_check("The whole trip comes to about €1,999.", {1468.14}, False))

    def test_a_wrong_total_is_stripped_honestly(self):
        bad = AG.guard_check("The whole trip comes to €479.", {479.0}, False, self.FIG)
        self.assertEqual(AG.guard_strip("The whole trip comes to €479.", bad), "The panel shows the prices.")


class HoldBookingSaysWhenTheTotalMoved(unittest.TestCase):
    def test_refresh_then_figures_and_the_change_said(self):
        from booking_signer import passengers as PX
        rows = rows_496()

        async def refresh(account, origin):   # the airline repriced the flight home: €98.30 → €210.20
            rows[1].update(price_amount=210.2)
            tb = BK.to_book(rows)
            lines = BB.lines_of(tb, 2)
            return {"lines": lines, "sha256": "f" * 64, "eur": BK.total(tb)["amount"]}
        API._HELD.pop(ACCOUNT, None)
        with mock.patch.object(API, "_plan", mock.AsyncMock(return_value=PLAN)), mock.patch.object(BK, "items", items_of(rows)), \
                mock.patch.object(PX, "saved", mock.AsyncMock(return_value=[{}, {}])), \
                mock.patch.object(API, "_s1_passport", mock.AsyncMock(return_value=None)), \
                mock.patch.object(BB, "quote", refresh), mock.patch("agapi.keep_gate.keep_on", lambda *a: False):
            res = run(API.hold_booking(ctx(), {}))
            tab = run(LR.trip_total(ACCOUNT, TRIP, PLAN))
        API._HELD.pop(ACCOUNT, None)
        self.assertEqual(res["total_eur"], 608.0)                              # the read-back's figure
        self.assertEqual(res["trip_total_eur"], 608.0)                         # = trip_figures after the refresh
        self.assertEqual(tab["total_eur"], 608.0)                              # = the Trip tab
        self.assertTrue(any(l.startswith("Total €608.00") for l in res["read_back"]))
        self.assertEqual((res["total_changed"]["from"], res["total_changed"]["to"]), (496.1, 608.0))
        self.assertIn("€608.00 now, not €496.10", res["total_changed"]["say"])
        self.assertEqual(AG.guard_check(res["total_changed"]["say"], {496.1, 608.0}, False, {"total_eur": 608.0}), [])   # sayable


# ── T6 · one party ────────────────────────────────────────────────────────────────────────────────────────────────────────────

class OneParty(unittest.TestCase):
    def test_plan_then_rows_then_ask(self):
        self.assertEqual(BK.figures_of(rows_496(), TRIP, {"plan": {"party": 3}})["party"], 3)
        self.assertEqual(BK.figures_of(rows_496(), TRIP, {"plan": {}})["party"], 2)      # the rows carry it
        f = BK.figures_of([{**r, "party": None} for r in rows_496()], TRIP, {"plan": {}})
        self.assertIsNone(f["party"])                                                    # never a silent 1 or 2
        self.assertIn("ask", f["ask_party"])
        self.assertIsNone(API._party({"plan": {}}, []))

    def test_hold_booking_asks_rather_than_guessing(self):
        rows = [{**r, "party": None} for r in rows_496()]
        with mock.patch.object(API, "_plan", mock.AsyncMock(return_value={"trip_id": TRIP, "plan": {}})), \
                mock.patch.object(BK, "items", items_of(rows)):
            with self.assertRaises(API.ToolError) as e:
                run(API.hold_booking(ctx(), {}))
        self.assertEqual(e.exception.code, "party_unknown")

    def test_the_trip_tab_and_the_read_back_carry_the_same_party(self):
        with mock.patch.object(BK, "items", items_of(rows_496())):
            tab = run(LR.trip_total(ACCOUNT, TRIP, PLAN))
        self.assertEqual(tab["party"], 2)
        self.assertIn("For 2.", BB.lines_of(BK.to_book(rows_496()), tab["party"])[0])
        self.assertNotIn("None", BB.lines_of(BK.to_book(rows_496()), None)[0])


# ── T7 · offered == bookable ─────────────────────────────────────────────────────────────────────────────────────────────────

class _Conn:
    """Just enough of asyncpg for basket.suggest: the slice's suggested rows, the deletes and marks by id, the insert."""
    def __init__(self, rows):
        self.rows, self.sql = rows, []

    def transaction(self):
        class T:
            async def __aenter__(_s):
                return None

            async def __aexit__(_s, *a):
                return False
        return T()

    async def fetch(self, sql, account, trip, slice_key):
        self.sql.append(sql)
        return [r for r in self.rows if r["kind"] == "flight" and r["state"] == "suggested" and (r.get("slice_key") or "") == (slice_key or "")]

    async def execute(self, sql, account, ids, *rest):
        self.sql.append(sql)
        ids = {str(i) for i in ids}
        if sql.startswith("delete"):
            self.rows[:] = [r for r in self.rows if str(r["id"]) not in ids or r["state"] != "suggested"]
        elif "superseded_at" in sql:
            for r in self.rows:
                if str(r["id"]) in ids:
                    r["snapshot"] = {**r["snapshot"], "superseded_at": rest[0]}

    async def fetchval(self, sql, trip, account, kind, slice_key, day, s, e, party, provider, ref, req, snap, exp, amount, cur, src, test):
        i = str(uuid.uuid4())
        self.rows.append({"id": i, "kind": kind, "state": "suggested", "slice_key": slice_key, "provider_ref": ref,
                          "snapshot": json.loads(snap), "price_amount": amount, "price_currency": cur})
        return i


class OfferedIsBookable(unittest.TestCase):
    def suggest(self, conn, refs, amount=120.0, cur="EUR", sk="back:LIS→MAD " + D3):
        async def runner(fn):
            return await fn(conn)
        with mock.patch.object(BK, "STORE_RUN", runner):
            return run(BK.suggest(ACCOUNT, TRIP, "flight", [{"provider": "duffel", "provider_ref": r, "price_amount": amount,
                                                              "price_currency": cur, "snapshot": {"id": r}} for r in refs], slice_key=sk))

    def test_a_new_search_appends_and_never_deletes_what_was_just_shown(self):
        conn = _Conn([])
        first = self.suggest(conn, ["off_1748", "off_1905"])
        self.suggest(conn, ["off_2010"])                                       # a later search of the same leg
        ids = {r["id"] for r in conn.rows}
        self.assertTrue(set(first) <= ids)                                     # 17:48 still in the basket — still choosable
        self.assertEqual(sorted(BK.superseded(r) for r in conn.rows), [False, True, True])
        self.assertFalse(any(s.startswith("delete") for s in conn.sql))       # nothing deleted in the turn

    def test_the_same_offer_shown_again_is_one_row(self):
        conn = _Conn([])
        self.suggest(conn, ["off_1748"])
        self.suggest(conn, ["off_1748", "off_2010"])
        self.assertEqual(sorted(r["provider_ref"] for r in conn.rows), ["off_1748", "off_2010"])

    def test_an_option_superseded_in_an_earlier_turn_goes_later(self):
        now = datetime.now(timezone.utc)
        old = (now - timedelta(seconds=BK.SUPERSEDED_KEEP_S + 60)).isoformat()
        recent = (now - timedelta(seconds=60)).isoformat()
        got = BK.supersede_plan([{"id": "o", "provider_ref": "x", "snapshot": {"superseded_at": old}},
                                 {"id": "r", "provider_ref": "y", "snapshot": {"superseded_at": recent}},
                                 {"id": "n", "provider_ref": "z", "snapshot": {}}], ["new"], now)
        self.assertEqual(got, {"drop": ["o"], "mark": ["n"]})                  # "r" kept as it is — still choosable

    def test_a_usd_fare_is_stored_in_euros(self):
        conn = _Conn([])
        with mock.patch.dict(os.environ, NO_FX_ENV):
            self.suggest(conn, ["off_usd"], amount=200.0, cur="USD")
        r = conn.rows[0]
        self.assertEqual((r["price_amount"], r["price_currency"]), (round(200 * FX.DEFAULT["USD"], 2), "EUR"))
        self.assertEqual(r["snapshot"]["fx"]["currency"], "USD")

    # ── _find_option: (leg, time), the leg from their words ──

    def find(self, said, a, rows):
        with mock.patch.object(BK, "items", items_of(rows)):
            return run(API._find_option(ctx(said), PLAN, a))

    def test_move_our_flight_home_to_the_1748(self):
        rows = rows_496()
        rows[3]["snapshot"]["superseded_at"] = datetime.now(timezone.utc).isoformat()   # offered by an earlier search
        for a in ({"departs": "17:48"}, {"departs": "17:48", "leg": "out"}, {"departs": "5:48pm"}, {"departs": "17.48"}):
            got = self.find("Move our flight home to the 17:48.", a, rows)
            self.assertEqual(got and got["id"], "c", a)

    def test_the_time_alone_finds_the_one_flight_at_it(self):
        self.assertEqual(self.find("the 17:48 please", {"departs": "17:48"}, rows_496())["id"], "c")
        self.assertIsNone(self.find("the 06:00 please", {"departs": "06:00"}, rows_496()))   # never offered: not invented

    def test_no_leg_and_no_time_is_the_flight_out_as_before(self):
        self.assertEqual(self.find("the cheapest", {"pick": "cheapest"}, rows_496())["id"], "a")

    def test_times_as_people_say_them(self):
        for said, want in (("17:48", "17:48"), ("5:48 pm", "17:48"), ("5.48 p.m.", "17:48"), ("1748", "17:48"), ("9am", "09:00"),
                           ("12am", "00:00"), ("8.30", "08:30"), ("noon", None)):
            self.assertEqual(API.hhmm(said), want, said)
        self.assertEqual(API.leg_said("our flight home"), "back")
        self.assertEqual(API.leg_said("the return one"), "back")
        self.assertIsNone(API.leg_said("the flight out"))

    # ── stored before shown: Sasha's own search and /s2's AgAPI source, one basket ──

    def test_search_flights_stores_then_shows_with_option_ids(self):
        order = []
        cards = [{"id": "off_u", "owner": "UX", "flights": "UX 1", "from": "LIS", "to": "MAD", "departs": f"{D3}T17:48:00",
                  "arrives": f"{D3}T19:00:00", "stops": 0, "minutes": 72, "amount": "200.00", "currency": "USD"}]

        async def suggest(account, trip, kind, found, slice_key=None, replace=True):
            order.append(("stored", slice_key, [f["provider_ref"] for f in found]))
            return ["row-1"]
        with mock.patch.dict(os.environ, NO_FX_ENV), \
                mock.patch.object(API, "_search_healed", mock.AsyncMock(return_value=({"cards": cards}, D3))), \
                mock.patch.object(API, "_latest", mock.AsyncMock(return_value=PLAN)), mock.patch.object(BK, "suggest", suggest):
            r = run(API.call(ctx("any flights home that evening?"), "search_flights", {"origin": "Lisbon", "destination": "Madrid", "date": D3}))
        self.assertTrue(r["ok"], r)
        self.assertEqual(order, [("stored", f"back:Lisbon→Madrid {D3}", ["off_u"])])   # the leg from their words; stored first
        f = r["result"]["flights"][0]
        self.assertEqual((f["option_id"], f["price_eur"], f["fare"]["currency"]), ("row-1", round(200 * FX.DEFAULT["USD"], 2), "USD"))
        self.assertTrue(r["result"]["stored"])

    def test_without_a_trip_she_is_told_none_can_be_booked_yet(self):
        cards = [{"id": "off_e", "owner": "IB", "flights": "IB 1", "from": "MAD", "to": "LIS", "departs": f"{D1}T08:30:00",
                  "arrives": f"{D1}T09:45:00", "stops": 0, "minutes": 75, "amount": "85.00", "currency": "EUR"}]
        with mock.patch.object(API, "_search_healed", mock.AsyncMock(return_value=({"cards": cards}, D1))), \
                mock.patch.object(API, "_latest", mock.AsyncMock(return_value=None)):
            r = run(API.call(ctx(), "search_flights", {"origin": "Madrid", "destination": "Lisbon", "date": D1}))
        self.assertFalse(r["result"]["stored"])
        self.assertIn("propose_trip first", r["result"]["how"])

    def test_s2s_agapi_flights_go_into_the_same_basket_in_euros(self):
        from agapi import via_agapi as VIA
        offer = {"offer_ref": "off_ag", "carrier": {"name": "UX"}, "flight_numbers": ["UX 1013"], "from": "LIS", "to": "MAD",
                 "departs": f"{D3}T17:48:00", "arrives": f"{D3}T19:00:00", "stops": 0, "duration_minutes": 72,
                 "price": {"amount_minor": 20000, "currency": "USD"}}
        seen = []

        async def suggest(account, trip, kind, found, slice_key=None, replace=True):
            seen.append((slice_key, found[0]["price_amount"], found[0]["price_currency"]))
            return ["row-ag"]
        with mock.patch.dict(os.environ, NO_FX_ENV), mock.patch.object(API, "_latest", mock.AsyncMock(return_value=PLAN)), \
                mock.patch.object(BK, "suggest", suggest):
            got = run(VIA._flights_from_agapi(ctx("the flight home"), {"origin": "Lisbon", "destination": "Madrid", "date": D3},
                                              {"ok": True, "result": {"offers": [offer]}}))
        self.assertEqual(seen, [(f"back:Lisbon→Madrid {D3}", 200.0, "USD")])   # converted by the basket at ingestion (BK.suggest)
        f = got["result"]["flights"][0]
        self.assertEqual((f["option_id"], f["price_eur"]), ("row-ag", round(200 * FX.DEFAULT["USD"], 2)))

    def test_proposal_options_are_only_stored_ones_each_with_its_id(self):
        cards = [{"id": "x", "amount": "90", "currency": "EUR", "minutes": 80}, {"id": "y", "amount": "80", "currency": "EUR", "minutes": 90}]
        opts = API._options(cards, cards[0], stored={"x": "row-x"})
        self.assertEqual([(o["offer_id"], o["option_id"]) for o in opts], [("x", "row-x")])


if __name__ == "__main__":
    unittest.main()
