"""Sasha 305 · change an existing trip: a flight is its Duffel order READ NOW (never a copy kept at booking), a hotel its record on
AgAPI, and ONE resolver finds the booking he means — its own source decides who answers. Offline: a fake Duffel.

    cd backend && python -m unittest tests.test_s305 -v
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import unittest
from unittest import mock

from booking_signer import basket as BK, flight_manage as FM
from tests.test_flight_manage_226 import FakeDuffel, order

ROOT = pathlib.Path(__file__).resolve().parents[1]
NEW_SEG = {"origin": {"iata_code": "MAD"}, "destination": {"iata_code": "LGW"}, "departing_at": "2026-11-27T07:15:00",
           "arriving_at": "2026-11-27T08:50:00", "marketing_carrier": {"iata_code": "U2"}, "marketing_carrier_flight_number": "7650"}


def run(c):
    return asyncio.run(c)


class ChangingDuffel(FakeDuffel):
    """Duffel as it is: once the change is confirmed, the ORDER reads the new flight (and, here, a new reference)."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.changed = self.cancelled = False

    async def __call__(self, method, path, body=None, params=None):
        if method == "GET" and path == "/air/orders/ord_1" and not any(path.startswith(p) for p in self.fail):
            self.calls.append((method, path, body))
            o = dict(self.order)
            if self.changed:
                o = {**o, "booking_reference": "NEW456", "slices": [{"id": "sli_new", "origin": {"iata_code": "MAD"},
                                                                     "destination": {"iata_code": "LGW"}, "segments": [NEW_SEG]}]}
            if self.cancelled:
                o = {**o, "cancelled_at": "2026-10-10T13:40:00Z"}
            return 200, {"data": o}
        got = await super().__call__(method, path, body, params)
        if path == "/air/order_changes/oce_1/actions/confirm":
            self.changed = True
        if path == "/air/order_cancellations/ore_1/actions/confirm":
            self.cancelled = True
        return got


class Base(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"DUFFEL_ACCESS_TOKEN": "duffel_test_x"})
        self.env.start()
        self.saved = FM.HTTP
        FM._SEEN.clear()
        FM.HTTP = self.duffel = ChangingDuffel()

    def tearDown(self):
        FM.HTTP = self.saved
        FM._SEEN.clear()
        self.env.stop()


class TheOrderIsTheTruth(Base):
    def test_one_reader_reads_the_order_and_forgets_on_our_own_change(self):
        v = run(FM.order_now("ord_1"))
        self.assertEqual((v["reference"], v["flights"], v["departs"]), ("ABC123", "U2 7640", "2026-11-20T08:30:00"))
        run(FM.order_now("ord_1"))
        self.assertEqual(self.duffel.paths().count("/air/orders/ord_1"), 1)   # a poll inside FRESH_S reuses the read
        q = run(FM.change_quote("ord_1", "2026-11-27", "out"))
        c = run(FM.change_confirm(q["change_offer_id"]))
        self.assertEqual(c["status"], "changed")
        # the change RE-READS the order: the new flight and reference are Duffel's, never the offer's or the old read's
        self.assertEqual((c["booking_reference"], c["order"]["flights"], c["order"]["departs"]), ("NEW456", "U2 7650", "2026-11-27T07:15:00"))
        self.assertEqual(run(FM.order_now("ord_1"))["reference"], "NEW456")

    def test_no_token_or_no_order_is_said_never_guessed(self):
        self.assertIn("why", run(FM.order_now(None)))
        FM._SEEN.clear()
        with mock.patch.dict(os.environ, {"DUFFEL_ACCESS_TOKEN": ""}):
            self.assertIn("TEST token", run(FM.order_now("ord_1"))["why"])


class NoSecondCopy(Base):
    ROW = {"id": "it1", "kind": "flight", "state": "booked", "order_id": "ord_1", "day": "2026-11-20", "booking_reference": "ABC123",
           "status_line": "✈️ easyJet U2 7640 MAD→LGW · 2026-11-20 · booked · ref ABC123",
           "snapshot": {"owner": "easyJet", "flights": "U2 7640", "from": "MAD", "to": "LGW", "departs": "2026-11-20T08:30:00", "amount": "99.00"}}

    def test_a_changed_flight_reads_as_the_order_stands(self):
        self.duffel.changed = True
        [r] = run(BK.live([dict(self.ROW)]))
        self.assertTrue(r["live"])
        self.assertEqual((r["snapshot"]["flights"], r["snapshot"]["departs"], r["day"], r["booking_reference"]),
                         ("U2 7650", "2026-11-27T07:15:00", "2026-11-27", "NEW456"))
        self.assertEqual(r["snapshot"]["amount"], "99.00")   # what was paid at booking stays the booking's own
        self.assertIn("U2 7650", BK.words(r))
        self.assertNotIn("7640", BK.words(r))                # the line kept at booking named the old flight: built again

    def test_cancelled_at_duffel_is_cancelled_here(self):
        self.duffel.cancelled = True
        [r] = run(BK.live([dict(self.ROW)]))
        self.assertEqual(r["state"], "cancelled")

    def test_unreadable_order_is_marked_never_said_as_now(self):
        self.duffel.fail = {"/air/orders/": (503, {"errors": [{"message": "down"}]})}
        [r] = run(BK.live([dict(self.ROW)]))
        self.assertIs(r["live"], False)
        self.assertIn("isn't answering", r["live_why"])

    def test_every_view_of_a_booked_flight_reads_through_it(self):   # found on the third walk: the banner and Getting there kept the old flight
        pins = {"agapi/itinerary.py": "rows = await BK.live(",                       # My trips
                "booking_signer/plan_store.py": "BK.overlay(m, await BK.live(rows))",  # the Trip tab's days
                "agapi/s2_status.py": "rows = await BK.live(await BK.items(",          # get_status: her answer and the Trip banner
                "booking_signer/ladder_routes.py": "rows = await BK.live(await BK.items(account, trip_id",   # Getting there / the total
                "agapi/s2_tools.py": "await BK.live(await BK.items(ctx.account, p[\"trip_id\"], (\"booked\",)))"}   # add to calendar
        for f, pin in pins.items():
            self.assertIn(pin, (ROOT / f).read_text(), f)

    def test_the_orders_duration_comes_with_it(self):
        o = order()
        o["slices"][0]["duration"] = "PT11H34M"
        self.assertEqual(FM.order_view(o)["minutes"], 694)


class OneBookingOneRow(Base):
    def test_the_ladders_copy_of_a_basket_flight_is_not_listed_again(self):   # found live: each flight twice, once as a "dinner"
        from agapi import itinerary as IT
        from booking_signer import plan_store as PS, rental_moments as RM
        flight = {**NoSecondCopy.ROW, "trip_item_id": "ti-1", "trip_id": "t1"}
        ladder = {"id": "ti-1", "source": "ladder", "venue": "Flight U2 7640 Madrid → London (TEST booking)", "date": "2026-11-20",
                  "time": "08:30", "status": "confirmed", "status_words": "booked", "route": "form", "route_words": "", "manage": "ladder",
                  "type": "flight"}
        with mock.patch.object(PS, "plans", mock.AsyncMock(return_value=[{"trip_id": "t1", "title": "Flight Madrid → London"}])), \
                mock.patch.object(IT, "venue_rows", mock.AsyncMock(return_value=[ladder])), \
                mock.patch.object(BK, "items", mock.AsyncMock(return_value=[flight])), \
                mock.patch.object(RM, "rentals", mock.AsyncMock(return_value=[])), \
                mock.patch.object(IT, "_wallet", mock.AsyncMock(return_value=[])):
            got = run(IT.of("acct-305"))
        self.assertEqual([(i["kind"], i["source"]) for i in got], [("flight", "flight")])
        self.assertTrue(got[0]["live"])


class TheBannerToo(Base):
    def test_a_cancelled_basket_flights_ladder_copy_is_never_said_booked(self):   # found live: "Booked: … ref VMOWK7" after the cancel
        from agapi import s2_status as ST, venues as VN, v0 as API, s2_outcomes as OC
        from booking_signer import paid_watch as PW, plan_store as PS
        self.duffel.cancelled = True
        flight = {**NoSecondCopy.ROW, "trip_item_id": "ti-1", "state": "booked"}
        copy = {"trip_item_id": "ti-1", "venue": "Flight U2 7640 Madrid → London (TEST booking)", "date": "2026-11-20", "time": "08:30",
                "status": "confirmed", "reference": "ABC123"}
        with mock.patch.object(PS, "by_id", mock.AsyncMock(return_value={"trip_id": "t1"})), \
                mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=[copy])), \
                mock.patch.object(BK, "items", mock.AsyncMock(side_effect=lambda a, t, states=None: [dict(flight)] if "booked" in (states or ()) else [])):
            st = run(ST.status_of("acct-305", "t1", sweep=False))
        self.assertEqual(st["venues"], [])                        # the ladder's copy of the basket flight is not a second booking
        self.assertEqual(st["booked"], [])
        self.assertIn("cancelled", " ".join(st["cancelled"]))    # the flight, as Duffel has it: cancelled
        self.assertNotIn("Madrid → London (TEST booking)", ST.decide(st)["line"])


class WhatSheSaysAfter(Base):
    def test_change_words_are_the_order_now_and_the_charge(self):
        from agapi import s2_manage as M
        q = run(FM.change_quote("ord_1", "2026-11-27", "out"))
        said = M.changed_words(run(FM.change_confirm(q["change_offer_id"])))
        for part in ("U2 7650", "07:15", "NEW456", "€60.50 was charged to the Duffel test balance", M.NO_REAL_MONEY):
            self.assertIn(part, said)
        self.assertNotIn("7640", said)

    def test_cancel_words_are_the_refund_and_the_order_reading_cancelled(self):
        from agapi import s2_manage as M
        q = run(FM.cancel_quote("ord_1"))
        self.assertIn("€76.41", q["say"])                     # the refund is said BEFORE anything is done
        said = run(M.cancelled_words(run(FM.cancel_confirm(q["quote_id"]))))
        self.assertIn("Refund: €76.41 to your original payment.", said)
        self.assertIn("Duffel's booking ABC123 now reads cancelled.", said)


class SaidByCode(unittest.TestCase):   # found live: she offered the new times and left out the price
    def test_a_flight_change_read_back_is_said_word_for_word_with_its_price(self):
        from app.agent import voice as V
        lines = ["I'll move your Duffel Airways flight ZZ 9492 on Sat 21 Nov to ZZ 8828, Sun 22 Nov 06:00 SNZ → 17:29 MAD (booking VMOWK7).",
                 "The change costs €61.20 in total, including the airline's €50.00 change fee (Duffel's own quote).", FM.TEST_LINE]
        said = V.flight_line("change_booking", {"ok": True, "result": {"flight": True, "status": "awaiting_yes", "read_back": lines}})
        self.assertTrue(said.startswith(lines[0]))
        self.assertIn("€61.20 in total, including the airline's €50.00 change fee", said)
        self.assertTrue(said.endswith(V.CHANGE_ASK))
        self.assertTrue(V.flight_line("cancel_booking", {"ok": True, "result": {"flight": True, "status": "awaiting_yes",
                                                                               "read_back": ["Refund €76.41."]}}).endswith(V.CANCEL_ASK))

    def test_after_the_yes_the_orders_words_and_only_for_a_flight(self):
        from app.agent import voice as V
        done = {"ok": True, "result": {"flight": True, "status": "changed", "say": "Changed — Duffel confirmed it. …"}}
        self.assertEqual(V.flight_line("change_booking", done), "Changed — Duffel confirmed it. …")
        self.assertEqual(V.flight_line("change_booking", {"ok": True, "result": {"status": "awaiting_yes", "read_back": ["a venue"]}}), "")
        self.assertEqual(V.flight_line("my_plans", done), "")
        self.assertEqual(V.flight_line("change_booking", {"ok": False, "error": {"code": "booking_unknown"}}), "")

    def test_the_chain_says_it(self):
        self.assertIn("or _V.flight_line(u.name, r)) if honest else", (ROOT / "app" / "agent" / "sasha.py").read_text())


class FoundOnTheSecondWalk(unittest.TestCase):
    def test_a_booking_reference_is_spelled_aloud(self):   # found live: "VMOWKseven"
        from app.agent.spoken import speakable
        self.assertIn("V M O W K seven", speakable("(booking VMOWK7)"))
        self.assertIn("E U F three S G", speakable("ref EUF3SG."))
        self.assertEqual(speakable("IB6453"), "IB six four five three")         # a flight number is read as before
        self.assertNotIn("V M O W K", speakable("VMOWK"))                       # a word in capitals isn't a reference

    def test_s2_says_no_real_money_never_a_label_its_screen_drops(self):   # found live: "This is a booking — no money moves."
        from agapi import s2_manage as M
        got = M._s2_lines(["I'll move it.", FM.TEST_LINE])
        self.assertEqual(got, ["I'll move it.", "No real money moves."])
        self.assertNotIn("TEST", " ".join(got))

    def test_each_other_time_once_and_never_the_one_offered(self):   # found live: 06:00 ×2 and 12:00 ×3, the offered 06:00 among them
        from agapi import s2_manage as M
        src = (ROOT / "agapi" / "s2_manage.py").read_text()
        self.assertIn("k = (v[\"time\"], v[\"flights\"], v[\"cost\"])", src)
        opt = lambda oid, t, fn: {"change_offer_id": oid, "departs": f"2026-11-22T{t}:00", "new_flights": fn, "change_total_amount": "125.00",
                                  "change_total_currency": "EUR", "lines": ["I'll move it.", "€125.00.", FM.TEST_LINE]}
        options = [opt("a", "06:00", "ZZ 8828"), opt("b", "06:00", "ZZ 8828"), opt("c", "12:00", "ZZ 5354"), opt("d", "12:00", "ZZ 5354")]
        off = {"order_id": "ord_back", "new_date": "2026-11-22", "leg": None, "options": options, "default": "a",
               "at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)}
        M._CHANGE["acct-305"] = off
        try:
            with mock.patch.object(M, "plans_of", mock.AsyncMock(return_value=[dict(RIO[1])])):
                r = run(M.change_booking(Ctx(), {"what": "flight", "name": "Rio", "new_date": "2026-11-22"}))
        finally:
            M._CHANGE.pop("acct-305", None)
            M._HELD.pop("acct-305", None)
        other = next(l for l in r["read_back"] if l.startswith("Other times"))
        self.assertEqual(other.count("12:00"), 1)
        self.assertNotIn("06:00", other)
        self.assertEqual(r["read_back"][-1], "No real money moves.")


class Ctx:
    account, session, user_said = "acct-305", "web:1", ""

    def __init__(self):
        from datetime import datetime, timezone
        self.started = datetime.now(timezone.utc)


RIO = [{"kind": "flight", "title": "LATAM LA 8065", "when": "2026-11-15T10:00:00", "where": "MAD → GIG", "status": "booked",
        "id": "f-out", "order_id": "ord_out", "trip": "7 Days in Rio", "trip_id": "t1", "source": "flight", "legs": 1},
       {"kind": "flight", "title": "LATAM LA 8064", "when": "2026-11-21T18:00:00", "where": "GIG → MAD", "status": "booked",
        "id": "f-back", "order_id": "ord_back", "trip": "7 Days in Rio", "trip_id": "t1", "source": "flight", "legs": 1},
       {"kind": "hotel", "title": "Marriott Test Hotel (sandbox)", "when": "2026-11-15T15:00", "status": "confirmed",
        "id": "act_01STAY", "source": "venue", "trip": "7 Days in Rio"},
       {"kind": "dinner", "title": "Taverna Correo", "when": "2026-11-16T21:00", "status": "confirmed", "id": "act_01DIN", "source": "venue"}]


class OneResolver(unittest.TestCase):
    def setUp(self):
        from agapi import s2_manage as M
        self.M = M
        self.p = mock.patch.object(M, "plans_of", mock.AsyncMock(return_value=[dict(r) for r in RIO]))
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_its_id_decides_never_the_models_what(self):
        self.assertEqual(run(self.M.booking_meant(Ctx(), {"id": "act_01STAY"}, "flight"))["source"], "venue")
        self.assertEqual(run(self.M.booking_meant(Ctx(), {"id": "ord_back"}, "hotel"))["id"], "f-back")

    def test_my_rio_flight_by_trip_and_leg(self):
        self.assertEqual(run(self.M.booking_meant(Ctx(), {"name": "Rio", "leg": "out"}, "flight"))["id"], "f-out")
        self.assertEqual(run(self.M.booking_meant(Ctx(), {"name": "rio", "leg": "back"}, "flight"))["id"], "f-back")
        with self.assertRaises(Exception) as e:
            run(self.M.booking_meant(Ctx(), {"name": "Rio"}, "flight"))
        self.assertEqual(getattr(e.exception, "code", None), "which_flight")

    def test_a_hotel_on_agapi_is_found_as_the_hotel(self):
        self.assertEqual(run(self.M.booking_meant(Ctx(), {"name": "marriott"}, "hotel"))["id"], "act_01STAY")

    def test_two_stays_of_one_name_are_asked_never_the_first_taken(self):   # found live: the scratch guest's two Marriott stays
        two = RIO + [{**RIO[2], "id": "act_01OLD", "when": "2026-10-30T15:00"}]
        with mock.patch.object(self.M, "plans_of", mock.AsyncMock(return_value=two)):
            with self.assertRaises(Exception) as e:
                run(self.M.booking_meant(Ctx(), {"name": "Marriott"}, "hotel"))
            self.assertEqual(getattr(e.exception, "code", None), "which_booking")
            self.assertIn("2026-11-15", str(e.exception))
            self.assertEqual(run(self.M.booking_meant(Ctx(), {"id": "act_01STAY"}, "hotel"))["id"], "act_01STAY")

    def test_hotel_nights_go_by_its_route(self):   # Sasha 306 MOVED: was "wait for AgAPI" — CR 137 takes a stay's nights
        with mock.patch.object(self.M, "_notice", mock.AsyncMock(return_value={"status": "awaiting_yes"})) as sent:
            run(self.M.change_booking(Ctx(), {"what": "hotel", "name": "Marriott", "nights": 3}))
        a = sent.call_args.args[1]
        self.assertEqual((a["id"], a["nights"], sent.call_args.args[2]), ("act_01STAY", 3, "change"))

    def test_a_hotel_cancel_on_agapi_goes_by_its_route(self):
        from agapi import venues as VN
        with mock.patch.object(VN, "cancel_venue", mock.AsyncMock(return_value={"status": "awaiting_yes"})) as cv:
            run(self.M.cancel_booking(Ctx(), {"what": "hotel", "name": "Marriott"}))
        self.assertEqual(cv.call_args.args[1]["act_id"], "act_01STAY")

    def test_a_one_flight_order_never_asks_duffel_for_a_leg(self):
        with mock.patch.object(FM, "change_quote", mock.AsyncMock(return_value={"why": "stop here"})) as cq:
            with self.assertRaises(Exception):
                run(self.M.change_booking(Ctx(), {"what": "flight", "name": "Rio", "leg": "back", "new_date": "2026-11-22"}))
        self.assertEqual(cq.call_args.args, ("ord_back", "2026-11-22", None))


if __name__ == "__main__":
    unittest.main()
