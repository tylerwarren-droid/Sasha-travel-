"""Sasha 144 · EVERY CALL IN THE LOG, AND ONE PLACE FOR A DISPUTE. Offline.
  · a test-line call is written to the call log BEFORE it is placed (is_test, no reservation), read like any call, and
    never followed up (no venue, no receipt);
  · the log shows each call's venue, time, outcome, words, Bland id — and says what isn't recorded;
  · Bland calls missing from our log are found: the test line's imported, any other number LISTED, never invented;
  · a receipt attempt is recorded, sent or not;
  · a confirmation email's small print is never a venue's name ("cualquier momento").

    cd backend && python -m unittest tests.test_ops_log_s144 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

from booking_signer import call_store as CS, calls as C, call_routes as CRT, guest_receipt as GR, mailbox as M, ops_log as OL

A = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


class TestCallsAreLogged(unittest.TestCase):
    def setUp(self):
        self.saved = (CRT.CALL_STORE, CRT.HTTP)
        CRT.CALL_STORE = CS.MemoryCallStore()
        self.env = mock.patch.dict(os.environ, {"SASHA_TEST_CALL_NUMBER": "+34600111222", "BLAND_API_KEY": "k"})
        self.env.start()

    def tearDown(self):
        CRT.CALL_STORE, CRT.HTTP = self.saved
        self.env.stop()

    def test_written_before_it_is_placed_then_marked_placed(self):
        order = []
        real_put = CRT.CALL_STORE.put_test_call

        async def put(row, approval, now):
            order.append("logged")
            await real_put(row, approval, now)

        async def place(http, key, payload):
            order.append("placed")
            self.assertEqual(payload["max_duration"], 1)
            return C.Placed(True, "bland-1", 200, {"status": "success"}, None)
        with mock.patch.object(CRT.CALL_STORE, "put_test_call", put), mock.patch.object(C, "place_call", place):
            out = run(OL.place_test_call(A, "en"))
        self.assertEqual(order, ["logged", "placed"])
        row = CRT.CALL_STORE.calls[out["call_id"]]
        self.assertTrue(row["is_test"])
        self.assertIsNone(row["trip_item_id"])
        self.assertEqual((row["status"], row["bland_call_id"]), ("placed", "bland-1"))
        self.assertTrue(row["dialled_number"].startswith("sha256:"))          # the founder's mobile: never its digits
        self.assertNotIn("600111222", str(row))

    def test_a_test_call_is_read_but_moves_no_reservation_and_sends_nothing(self):
        CRT.CALL_STORE.calls["c1"] = {"call_id": "c1", "account_id": A, "trip_item_id": None, "is_test": True, "status": "placed",
                                      "brief": {"purpose": "book"}, "bland_call_id": "b1"}
        reading = SimpleNamespace(state="answered", outcome="unclear", venue_words="Yes. Yes.", quote=None, reference=None, raised=None,
                                  why=None, read_by="rules", bland_status="completed", answered_by="human", offer=None)
        self.assertTrue(run(CRT.CALL_STORE.record_reading("c1", reading, {}, NOW)))
        self.assertEqual(CRT.CALL_STORE.attempts, [])
        with mock.patch.object(GR, "send_after_call", mock.AsyncMock(side_effect=AssertionError("no receipt for a test"))), \
             mock.patch.object(CRT, "confirm_unclear", mock.AsyncMock(side_effect=AssertionError("no confirmation call"))):
            run(CRT._follow_up(CRT.CALL_STORE.calls["c1"], reading))


class TheLog(unittest.TestCase):
    CALL = {"c": {"call_id": "c1", "account_id": A, "trip_item_id": "t1", "venue_key": "read:9", "status": "answered", "outcome": "yes",
                  "venue_words": "Sí, perfecto, a las nueve.", "bland_call_id": "b1", "placed_at": "2026-10-03T11:35:00+00:00",
                  "created_at": "2026-10-03T11:34:00+00:00", "language": "es"},
            "brief_venue": "Casa Lucio", "k_ref": "K-MCFA", "purpose": "book", "transcript": None, "recording_url": None,
            "price": "0.09", "minutes": "1.2", "provider_name": "Casa Lucio", "booking_status": "confirmed"}
    TEST = {"c": {"call_id": "c2", "account_id": A, "trip_item_id": None, "is_test": True, "venue_key": "test-line", "status": "placed",
                  "bland_call_id": "ed4770da", "created_at": "2026-10-04T10:16:00+00:00"}, "brief_venue": None}
    BOOKING = {"id": "t1", "account_id": A, "type": "restaurant", "status": "confirmed", "provider_name": "Casa Lucio",
               "booking_reference": "AB12", "date_time": datetime(2026, 10, 3, 19, 0, tzinfo=timezone.utc), "local_timezone": "Europe/Madrid",
               "party_size": 2, "k_call": "K-MCFA", "k_email": None, "calls": 1, "emails": 0, "forms": 0, "links": 0,
               "calendar": {"event_id": "g1", "status": "confirmed", "at": "x"}}

    def test_a_call_shows_what_a_dispute_needs(self):
        out = OL.assemble([self.CALL, self.TEST], [self.BOOKING], None)
        c = out["calls"][0]
        self.assertEqual((c["venue"], c["outcome"], c["venue_words"], c["k_ref"], c["bland_call_id"]),
                         ("Casa Lucio", "yes", "Sí, perfecto, a las nueve.", "K-MCFA", "b1"))
        self.assertEqual(c["recording"], OL.NO_RECORDING)   # said, never a dead link
        t = out["calls"][1]
        self.assertTrue(t["test"])
        self.assertEqual(t["venue"], "the Sasha test line")

    def test_a_booking_shows_its_references_receipt_and_calendar(self):
        b = OL.assemble([], [self.BOOKING], [{"trip_item_id": "t1", "outcome": "sent", "route": "after Sasha's phone call",
                                              "kind": "booking", "sent_at": "x"}])["bookings"][0]
        self.assertEqual((b["venue_reference"], b["k_ref"], b["when_local"]), ("AB12", "K-MCFA", "2026-10-03 21:00"))
        self.assertEqual(b["receipt"][0]["outcome"], "sent")
        self.assertEqual(b["calendar"]["event_id"], "g1")
        old = OL.assemble([], [self.BOOKING], None)["bookings"][0]
        self.assertIn("not recorded", old["receipt"])              # before 032: said, never "none sent"

    def test_filters(self):
        self.assertEqual([c["call_id"] for c in OL.assemble([self.CALL, self.TEST], [], None, tests="only")["calls"]], ["c2"])
        self.assertEqual([c["call_id"] for c in OL.assemble([self.CALL, self.TEST], [], None, tests="exclude")["calls"]], ["c1"])
        self.assertEqual(OL.assemble([self.CALL], [self.BOOKING], None, q="AB12")["bookings"][0]["id"], "t1")
        self.assertEqual(OL.assemble([self.CALL], [self.BOOKING], None, q="nothing-like-this"), {"calls": [], "bookings": [], "receipts_recorded": False})
        self.assertEqual(OL.assemble([self.CALL], [self.BOOKING], None, kind="bookings")["calls"], [])

    def test_bland_calls_missing_from_the_log(self):
        bland = [{"call_id": "b1", "to": "+34 600 111 222"}, {"call_id": "ed4770da", "to": "+34600111222"}, {"call_id": "x9", "to": "+34911000000"}]
        m = OL.missing(bland, {"b1"}, "+34600111222")
        self.assertEqual([b["call_id"] for b in m["test"]], ["ed4770da"])
        self.assertEqual([b["call_id"] for b in m["other"]], ["x9"])   # listed for the founder, never written as a call


class ReceiptsAreRecorded(unittest.TestCase):
    def test_sent_or_not_it_is_recorded(self):
        saved = CRT.CALL_STORE
        CRT.CALL_STORE = CS.MemoryCallStore()
        try:
            with mock.patch("booking_signer.ladder.emails_ready", lambda: "email is off"):
                out = run(GR.send_for_route(A, "Casa Lucio", "their own booking form", "Requested", {"trip_item_id": "t1"}))
            self.assertEqual(out, "not sent: email is off")
            r = CRT.CALL_STORE.receipts[0]
            self.assertEqual((r["trip_item_id"], r["outcome"], r["venue"], r["kind"]), ("t1", "not sent: email is off", "Casa Lucio", "booking"))
        finally:
            CRT.CALL_STORE = saved


class TestReceiptsAreNeverEmailed(unittest.TestCase):
    """Sasha 147 · 4 Oct 08:22–08:34: the speed harness put five "Your booking at Sasha Test Venue: Confirmed by the venue"
    receipts in the founder's inbox. A test or rehearsal booking's receipt is RECORDED as a test send, never emailed."""

    def setUp(self):
        self.saved = CRT.CALL_STORE
        CRT.CALL_STORE = CS.MemoryCallStore()

    def tearDown(self):
        CRT.CALL_STORE = self.saved

    def sends(self):
        return mock.patch.object(GR.E, "send", mock.AsyncMock(side_effect=AssertionError("a test receipt was emailed")))

    def test_the_test_venue_the_demo_spa_and_the_test_line(self):
        with self.sends(), mock.patch("booking_signer.ladder.emails_ready", lambda: None):
            a = run(GR.send_for_route(A, "Sasha Test Venue", "their own booking form", "Confirmed by the venue", {"trip_item_id": "t1"}))
            b = run(GR.send_for_route(A, "Kanoe Demo Spa", "its own member portal", "Confirmed by the venue", {"test": True}))
            c = run(GR.send_for_route(A, "some page", "their own booking form", "Confirmed", {"test": True}))   # by the form's host
            d = run(GR.send_after_call({"account_id": A, "call_id": None, "trip_item_id": "t2", "brief": {"venue_key": "test-line", "purpose": "book"}}))
        for out in (a, b, c, d):
            self.assertTrue(out.startswith("test: not emailed"), out)
        self.assertEqual([r["outcome"][:17] for r in CRT.CALL_STORE.receipts], ["test: not emailed"] * 4)
        self.assertEqual(CRT.CALL_STORE.receipts[0]["trip_item_id"], "t1")

    def test_the_reply_never_promises_a_receipt_that_isnt_coming(self):
        from booking_signer import guest_whatsapp as GW
        with mock.patch("booking_signer.ladder.emails_ready", lambda: None):
            self.assertEqual(GW._receipt_note("Casa Lucio"), " Your receipt is in your email.")
            self.assertEqual(GW._receipt_note("Casa Lucio", sent=False), "")          # a refused send: nothing sent, no receipt
            self.assertTrue(GW._receipt_note("Sasha Test Venue").startswith(" No receipt is emailed"))

    def test_a_cancel_with_no_number_is_refused_in_words_never_a_crash(self):
        from types import SimpleNamespace
        from booking_signer import places_terms as PT
        with self.assertRaises(PT.ListingUnavailable) as e:
            PT.seal_call({"brief": {"number": None}, "read_back_lines": []}, SimpleNamespace(number_kind="places", number=None, place_id="p"))
        self.assertEqual(e.exception.rule, "venue_number_missing")

    def test_a_real_venue_still_gets_its_receipt(self):
        self.assertIsNone(GR.test_reason("Casa Lucio", {"trip_item_id": "t1"}))
        self.assertIsNone(GR.test_reason("Casa Lucio", None, {"brief": {"venue_key": "read:9"}}))


class TheMailboxNeverNamesTheSmallPrint(unittest.TestCase):
    def test_cualquier_momento_is_not_a_venue(self):
        self.assertIsNone(M.venue_in("Tu reserva está confirmada", "Puedes cancelar tu reserva en cualquier momento desde la app."))
        self.assertEqual(M.venue_in("Tu reserva en Casa Lucio está confirmada", ""), "Casa Lucio")
        self.assertEqual(M.venue_in("Reserva confirmada - 100 Montaditos", ""), "100 Montaditos")


if __name__ == "__main__":
    unittest.main()
