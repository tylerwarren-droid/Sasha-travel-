"""Sasha 253 · OFFERED = BOOKABLE (EU's S2 scoreboard item 11). Offline: fakes only (no Duffel, no model, no database).

The scoreboard's step, word for word (scripts/scoreboard/sasha-scoreboard.mjs, item 11):
    "EU251 check: for the Lisbon trip, what flights home on Monday 2 November could we take instead? List the times."
    "EU251 check: swap our flight home to the <last time she named> one. Don't book."
She names departures AND landings ("Air Europa also flies at 11:35, landing at 13:50, and at 20:05, landing at 22:20"), so the
last time in her reply can be a landing time. Every time she names resolves to a stored, bookable option; a fare that went away
is said, with what's there now (stored first); a time never offered is "not one of the options", with the options.

    cd backend && python -m unittest tests.test_s253_offered -v
"""
from __future__ import annotations

import asyncio
import re
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import v0 as API
from booking_signer import basket as BK, basket_book as BB

ACCOUNT = "00000000-0000-4000-8000-000000000253"
TRIP = "11111111-1111-4111-8111-111111111253"
DAY = "2026-11-02"   # Monday 2 November: the flight home
run = asyncio.run
PLAN = {"trip_id": TRIP, "title": "3 Days in Lisbon", "plan": {"party": 2, "days": [{"day": 1, "date": "2026-10-31", "city": "Lisbon"}]}}
ASK = "EU251 check: for the Lisbon trip, what flights home on Monday 2 November could we take instead? List the times."
SWAP = "EU251 check: swap our flight home to the {} one. Don't book."


def card(i, owner, dep, arr, eur, day=DAY, expires=None):
    return {"id": f"off_{i}", "owner": owner, "flights": f"{owner[:2].upper()} {i}", "from": "LIS", "to": "MAD",
            "departs": f"{day}T{dep}:00", "arrives": f"{day}T{arr}:00", "stops": 0, "minutes": 75, "amount": f"{eur:.2f}",
            "currency": "EUR", **({"expires_at": expires} if expires else {})}


def lisbon_cards(expires=None):   # the six fares EU's run was offered (Duffel TEST)
    return [card("aa", "American Airlines", "00:46", "03:02", 61.0, expires=expires), card("ib", "Iberia", "00:46", "03:02", 64.0, expires=expires),
            card("zz", "Duffel Airways", "00:46", "03:02", 66.0, expires=expires), card("ba", "British Airways", "00:46", "03:02", 70.0, expires=expires),
            card("ux1", "Air Europa", "11:35", "13:50", 88.0, expires=expires), card("ux2", "Air Europa", "20:05", "22:20", 95.0, expires=expires)]


class Basket:
    """The trip's basket, in memory: suggest() stores, items() reads, choose() picks one per leg."""

    def __init__(self, rows=None):
        self.rows, self.n, self.stored = list(rows or []), 0, []

    async def suggest(self, account, trip, kind, found, slice_key=None, replace=True):
        ids = []
        for f in found:
            self.n += 1
            rid = f"00000000-0000-4000-8000-{self.n:012d}"   # choose_offer reads row ids as UUIDs
            self.rows.append({"id": rid, "kind": kind, "state": "suggested", "slice_key": slice_key, "day": f.get("day"),
                              "party": f.get("party"), "provider_ref": f["provider_ref"], "price_amount": f["price_amount"],
                              "price_currency": "EUR", "expires_at": f.get("expires_at"), "snapshot": dict(f["snapshot"]),
                              "created_at": f"2026-10-12T20:{self.n:02d}:00+00:00"})
            ids.append(rid)
        self.stored.append([f["provider_ref"] for f in found])
        return ids

    async def items(self, account, trip_id, states=BK.LIVE):
        return [r for r in self.rows if r["state"] in states]

    async def by_ref(self, account, trip_id, ref):
        return next((r for r in reversed(self.rows) if r["provider_ref"] == ref), None)

    async def choose(self, account, item_id):
        r = next(r for r in self.rows if r["id"] == item_id)
        for o in self.rows:
            if o["kind"] == "flight" and o["state"] == "chosen" and o.get("slice_key") == r.get("slice_key"):
                o["state"] = "suggested"
        r["state"] = "chosen"
        return r

    async def go(self, fn):   # choose_offer's "other leg's chosen back to suggested": applied to the rows
        class Conn:
            async def execute(_, sql, oid):
                for o in self.rows:
                    if o["id"] == str(oid):
                        o["state"] = "suggested"
        return await fn(Conn())

    def chosen(self, leg="back"):
        return [r for r in self.rows if r["state"] == "chosen" and str(r.get("slice_key") or "").startswith(leg + ":")]


def proposal_back():   # the proposal's flight home, chosen (the 21:00 the scoreboard ignores)
    return {"id": "00000000-0000-4000-8000-999999999999", "kind": "flight", "state": "chosen", "slice_key": f"back:Lisbon→Madrid {DAY}", "day": DAY, "party": 2,
            "provider_ref": "off_p", "price_amount": 99.0, "price_currency": "EUR",
            "snapshot": card("p", "TAP", "21:00", "23:15", 99.0), "created_at": "2026-10-12T19:00:00+00:00"}


class Harness(unittest.TestCase):
    def setUp(self):
        self.bk = Basket([proposal_back()])
        self.search = mock.AsyncMock(return_value=({"cards": lisbon_cards()}, DAY))
        self.validate = mock.AsyncMock(side_effect=AssertionError("an unexpired fare is put in without a call"))
        for p in (mock.patch.object(BK, "suggest", self.bk.suggest), mock.patch.object(BK, "items", self.bk.items),
                  mock.patch.object(BK, "by_ref", self.bk.by_ref), mock.patch.object(BK, "choose", self.bk.choose),
                  mock.patch.object(BK, "_go", self.bk.go), mock.patch.object(API, "_search_healed", self.search),
                  mock.patch.object(API, "_latest", mock.AsyncMock(return_value=PLAN)),
                  mock.patch.object(API, "_plan", mock.AsyncMock(return_value=PLAN)),
                  mock.patch.object(API, "_total", mock.AsyncMock(return_value={"total_eur": 456.0})),
                  mock.patch.object(BB, "_validate_flight", self.validate)):
            p.start()
            self.addCleanup(p.stop)

    def say(self, said, tool, args):
        return run(API.call(API.Ctx(account=ACCOUNT, user_said=said), tool, args))

    def offered(self):   # the scoreboard's ask: search_flights for the leg home on Monday 2 November → the times she can say
        r = self.say(ASK, "search_flights", {"origin": "Lisbon", "destination": "Madrid", "date": DAY})
        self.assertTrue(r["ok"], r)
        fl = r["result"]["flights"]
        self.assertTrue(all(f.get("option_id") for f in fl))                  # every one shown is stored first
        return fl

    def swap(self, t, **extra):
        return self.say(SWAP.format(t), "choose_offer", {"departs": t, "idempotency_key": f"s253-{uuid.uuid4()}", **extra})


class EveryOfferedTimeBooks(Harness):
    def test_the_scoreboard_sequence_move_our_flight_home_to_the_2005(self):
        self.offered()
        r = self.swap("20:05")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["chosen"]["departs"], f"{DAY}T20:05:00")
        self.assertEqual([c["provider_ref"] for c in self.bk.chosen()], ["off_ux2"])   # one flight home, the 20:05

    def test_every_time_she_names_departure_or_landing_can_be_booked(self):
        fl = self.offered()
        reply = " ".join(f"{f['airline']} at {f['departs'][11:16]}, landing at {f['arrives'][11:16]}." for f in fl)
        times = [t for t in re.findall(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", reply) if t != "21:00"]   # the runner's own regex
        self.assertEqual(sorted(set(times)), ["00:46", "03:02", "11:35", "13:50", "20:05", "22:20"])
        for t in times:
            r = self.swap(t)
            self.assertTrue(r["ok"], (t, r))
            got = r["result"]["chosen"]
            self.assertIn(t, (got["departs"][11:16], got["arrives"][11:16]), t)

    def test_the_landing_time_is_that_flight(self):
        self.offered()
        r = self.swap("22:20")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["chosen"]["offer_id"], "off_ux2")

    def test_a_time_as_the_model_may_pass_it(self):
        self.offered()
        for t in (f"{DAY}T20:05:00", "8:05pm", "20.05", "the 20:05"):
            r = self.swap(t, leg="back")
            self.assertTrue(r["ok"], (t, r))
            self.assertEqual(r["result"]["chosen"]["offer_id"], "off_ux2", t)
        self.assertEqual(API._said_hhmm(f"{DAY}T20:05:00"), "20:05")
        self.assertIsNone(API._said_hhmm("noon"))

    def test_four_airlines_at_one_time_the_cheapest_unless_named(self):
        self.offered()
        self.assertEqual(self.swap("00:46")["result"]["chosen"]["offer_id"], "off_aa")
        self.assertEqual(self.swap("00:46", airline="British Airways")["result"]["chosen"]["offer_id"], "off_ba")

    def test_the_same_time_on_two_searched_days_is_the_one_listed_last(self):
        self.bk.rows.append({**proposal_back(), "id": "00000000-0000-4000-8000-999999999998", "state": "suggested", "slice_key": "back:Lisbon→Madrid 2026-11-01",
                             "provider_ref": "off_old", "price_amount": 40.0, "created_at": "2026-10-12T18:00:00+00:00",
                             "snapshot": card("old", "Air Europa", "20:05", "22:20", 40.0, day="2026-11-01")})
        self.offered()
        self.assertEqual(self.swap("20:05")["result"]["chosen"]["offer_id"], "off_ux2")   # Monday's, not Sunday's cheaper one


class AFareThatWentAway(Harness):
    def test_gone_is_said_with_what_is_there_now_stored_first(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        self.search.return_value = ({"cards": lisbon_cards(expires=past)}, DAY)
        self.offered()
        fresh = [card("ux3", "Air Europa", "20:40", "22:55", 97.0), card("ux4", "Air Europa", "11:35", "13:50", 90.0)]
        self.search.return_value = ({"cards": fresh}, DAY)
        self.validate.side_effect = None
        self.validate.return_value = {"why": "the Air Europa flight AI ux2 you picked is no longer offered — shall I look again?"}
        r = self.swap("20:05")
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["error"]["code"], "not_choosable")
        msg = r["error"]["message"]
        self.assertIn("Air Europa at 20:05 fare is no longer offered", msg)
        self.assertIn("unchanged", msg)
        self.assertIn("departs 20:40", msg)
        self.assertIn("departs 11:35", msg)
        self.assertEqual(self.bk.stored[-1], ["off_ux3", "off_ux4"])           # what she offers next is stored first
        self.assertEqual([c["provider_ref"] for c in self.bk.chosen()], ["off_p"])   # the trip's flight home untouched
        r = self.swap("20:40")                                                 # and the new time she names books
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["chosen"]["offer_id"], "off_ux3")

    def test_an_expired_fare_still_offered_is_put_in_and_a_price_move_said(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        self.search.return_value = ({"cards": lisbon_cards(expires=past)}, DAY)
        self.offered()
        self.validate.side_effect = lambda account, row, party: {"row": row, "note": " (its price moved up €4.00 since you picked it)"}
        r = self.swap("20:05")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["price_moved"], "its price moved up €4.00 since you picked it")

    def test_the_airline_not_answering_keeps_the_choice(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        self.search.return_value = ({"cards": lisbon_cards(expires=past)}, DAY)
        self.offered()
        self.validate.side_effect = None
        self.validate.return_value = {"why": "can't reach", "outage": True}
        r = self.swap("20:05")
        self.assertTrue(r["ok"], r)                                            # hold_booking re-checks before any payment
        self.assertEqual(r["result"]["chosen"]["offer_id"], "off_ux2")


class ATimeNeverOffered(Harness):
    def test_not_one_of_the_options_with_the_options(self):
        self.offered()
        r = self.swap("06:00")
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["error"]["code"], "offer_not_in_trip")
        msg = r["error"]["message"]
        self.assertIn("not one of the options", msg)
        for t in ("00:46", "11:35", "20:05", "21:00"):
            self.assertIn(f"departs {t}", msg)
        self.assertNotIn("couldn't find", msg)
        self.assertEqual([c["provider_ref"] for c in self.bk.chosen()], ["off_p"])

    def test_nothing_stored_on_the_leg_search_first_as_before(self):
        self.bk.rows.clear()
        r = self.swap("20:05")
        self.assertIn("search_flights for that leg first", r["error"]["message"])


if __name__ == "__main__":
    unittest.main()
