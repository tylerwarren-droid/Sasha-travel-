"""Sasha 406b · T IS THE TRIP, AND IT HOLDS REFERENCES ONLY (KANOE finish list lines 3 and 6; Tyler's decisions on SASHA 406, row 2153).

T (booking_signer/trip_record) says which components belong to this journey and in what order. Each component's STATE lives in its own
record (AgAPI's acts / venue_booking_records / group_bookings / flight_orders …): "AgAPI's record is the only booking truth; Sasha keeps no
copy". AgAPI's trip_plans row is trip.plan's OUTPUT (a proposal), not the trip — Sasha reads it nowhere (asserted below).

MEASURED (406b, before any change): 24 modules write a component's state onto T's component tables (trip_items, trip_basket_items) or keep
it as a copy in the person's record (s2_memory venue_acts / prepared_pages / offers) — listed by the ONE detector (tests/component_state),
by SQL and by call. Each is a second copy. Each moves to a reference (a ticket each, several waiting on AgAPI's records); until then this
RATCHET holds the class: a NEW writer of component state onto T fails the build, and the list may only shrink.

    cd backend && python -m unittest tests.test_s406b_t_holds_references -v
"""
from __future__ import annotations

import pathlib
import re
import unittest

from tests import component_state as C

BACKEND = pathlib.Path(__file__).resolve().parents[1]

#: Sasha 406b · every module that still writes a component's state onto T or keeps a copy — exactly what the detector finds. ONLY SHRINKS.
COPIES = {
    "agapi/s2_manage.py", "agapi/v0.py", "agapi/venue_submit.py", "agapi/venues.py",
    "booking_signer/basket.py", "booking_signer/basket_book.py", "booking_signer/call_store.py", "booking_signer/cancel_routes.py",
    "booking_signer/demo_ops.py", "booking_signer/duffel_webhook.py", "booking_signer/form_rung.py", "booking_signer/hotel_test.py",
    "booking_signer/inbound_phone.py", "booking_signer/ladder_routes.py", "booking_signer/ladder_store.py", "booking_signer/mailbox.py",
    "booking_signer/paid_watch.py", "booking_signer/stop.py", "booking_signer/store.py", "booking_signer/trains.py",
    "booking_signer/travel.py", "booking_signer/wa_brain.py", "products/campus/visits.py", "products/itinerary.py",
}
#: FROZEN — the list as 406b measured it (24). COPIES may only ever be a subset of it. Never add a line here.
BASELINE_406B = frozenset(COPIES)


class Ratchet(unittest.TestCase):
    def test_no_new_writer_of_component_state_onto_T(self):
        hits = set(C.writers())
        self.assertEqual(hits - COPIES, set(), "a NEW module writes a component's state onto T (or copies it): reference its own record")
        self.assertEqual(COPIES - hits, set(), "moved to a reference: take it off COPIES")

    def test_the_list_only_shrinks(self):
        self.assertTrue(COPIES <= BASELINE_406B, COPIES - BASELINE_406B)
        self.assertLessEqual(len(COPIES), 24)

    def test_the_detector_sees_a_copy(self):
        self.assertTrue(C.findings("x.py", 'await c.execute("update trip_items set status = $2, booking_reference = $3 where id = $1")'))
        self.assertTrue(C.findings("x.py", 'await c.execute("insert into trip_basket_items (trip_id, state, snapshot) values ($1,$2,$3)")'))
        self.assertTrue(C.findings("x.py", 'await M.put_kind(account, "venue_acts", acts)'))
        self.assertFalse(C.findings("x.py", 'await c.execute("update trip_items set trip_id = $2 where id = $1")'))   # a reference move


class TheTripIsT(unittest.TestCase):
    def test_nothing_in_sasha_reads_trip_plans_as_the_trip(self):
        for d in C.DIRS:
            for p in (BACKEND / d).rglob("*.py"):
                src = p.read_text()
                self.assertNotRegex(src, r"OP\.TRIP_PLAN(_GET)?\b|['\"]trip\.plan(_get)?['\"]|\btrip_plans\b", p.as_posix())

    def test_a_trips_span_is_never_widened_from_a_booking(self):
        """The ONE copy on `trips` itself: plan_store widened depart / return from a booking's day (a component's time onto T). Named here
        so it moves with the rest — it is on COPIES' plan (plan_store), not the detector's tables."""
        src = (BACKEND / "booking_signer/plan_store.py").read_text()
        self.assertEqual(len(re.findall(r"depart_date = least\(depart_date", src)), 1)   # the one known site; a second one fails


if __name__ == "__main__":
    unittest.main()
