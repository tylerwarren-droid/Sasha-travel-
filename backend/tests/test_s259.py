"""Sasha 259 · T41 — the last S2 product fixes (mailbox rows 883, 884, 888), each at its cause, in the one place every surface reads:
  (2) connecting Gmail IS the consent: she reads at once, one short statement, never a question (tests moved: cr84 / cr86);
  (3) "I lost the connection there" (Tyler's /s2, 13 Oct ~12:12 UTC): the receipts were fetched one after another (30–90 s) past the
      page's 75 s stall — fetched ten at a time now; a Gmail outage is said, never a failed turn; a long turn sends "working" so the
      page never calls it lost;
  (5) S2 item 12: the trip's chosen-not-booked items are on the ONE status (the Trip tab says "not booked yet"; so does the chat);
  (6) the calendar reads the same booking record as get_status (an AgAPI booking by its act_id or reference).
Offline.

    cd backend && python -m unittest tests.test_s259 -v
"""
from __future__ import annotations

import asyncio
import time
import unittest
from unittest import mock

from agapi import s2_gmail_receipts as GR, s2_status as ST, s2_subscriptions as SUBS

ACCT = "00000000-0000-4000-8000-000000000259"


def run(c):
    return asyncio.run(c)


class TheTripsChosenItemsAreOnTheOneStatus(unittest.TestCase):
    def test_booked_tables_and_a_chosen_flight_both_said(self):
        d = ST.decide({"venues": [{"venue": "Sasha Test Venue", "date": "2026-10-15", "time": "21:00", "status": "confirmed", "reference": "TV-1"}],
                       "booked": [], "failed": [], "chosen": ["✈️ Air Europa UX 1153 MAD→LIS · 2026-10-31 · chosen"]})
        self.assertEqual(d["state"], "booked")                                  # the state as it was
        self.assertIn("Booked: Sasha Test Venue", d["line"])
        self.assertIn("Chosen, not booked yet: ✈️ Air Europa UX 1153 MAD→LIS · 2026-10-31.", d["line"])

    def test_nothing_else_the_chosen_items_are_the_line(self):
        d = ST.decide({"venues": [], "booked": [], "failed": [], "chosen": ["✈️ Air Europa UX 1160 LIS→MAD · 2026-11-02 · chosen"]})
        self.assertIn("not booked yet", d["line"])


class ALongJobIsNeverALostConnection(unittest.TestCase):
    def test_a_working_event_while_the_turn_works(self):
        from app.agent import sasha as S

        async def slow():
            yield {"type": "text", "delta": "Looking"}
            await asyncio.sleep(0.35)
            yield {"type": "done", "text": "Looking — found 4."}

        async def go():
            return [e async for e in S.with_holding(slow(), ACCT, after_s=0.05)]
        with mock.patch.object(S, "KEEPALIVE_S", 0.1):
            evs = run(go())
        self.assertIn("working", [e["type"] for e in evs])
        self.assertEqual(evs[-1]["type"], "done")

    def test_the_receipts_are_fetched_at_once_not_one_after_another(self):
        from booking_signer import mailbox as MB
        from booking_signer.vault import crypto as VC

        async def http(method, url, token, params):
            if url.endswith("/messages"):
                return 200, {"messages": [{"id": f"m{i}"} for i in range(20)]}
            await asyncio.sleep(0.1)   # one Gmail fetch
            return 200, {"payload": {"headers": [{"name": "Subject", "value": "Your receipt"}], "mimeType": "text/plain",
                                     "body": {"data": "VG90YWw6IDEwIEVVUg=="}}}
        store = mock.Mock()
        store.get_link = mock.AsyncMock(return_value={"vault_item_id": "v1"})
        with mock.patch.object(MB, "STORE", store), mock.patch.object(MB, "GMAIL_HTTP", http), \
                mock.patch.object(VC, "use_connection", mock.AsyncMock(return_value="tok")):
            t0 = time.perf_counter()
            got = run(GR.receipts(ACCT))
            took = time.perf_counter() - t0
        self.assertEqual(len(got), 20)
        self.assertLess(took, 1.0)                                              # one after another would be 2 s

    def test_gmail_unreachable_is_said_never_a_failed_turn(self):
        class Ctx:
            account, user_said = ACCT, "what subscriptions am I paying for?"
        with mock.patch.object(GR, "connected", mock.AsyncMock(return_value=True)), \
                mock.patch.object(GR, "receipts", mock.AsyncMock(side_effect=GR.Unreachable("ConnectTimeout"))), \
                mock.patch.object(SUBS, "_end_user", mock.AsyncMock(return_value="usr_1")):
            r = run(SUBS._run_tool(Ctx(), "find_subscriptions", {"from_gmail": True}))
        self.assertEqual(r["error"]["code"], "gmail_unreachable")
        self.assertIn("couldn't reach your Gmail", r["error"]["message"])


class ConnectingIsTheConsent(unittest.TestCase):
    def test_no_question_on_any_surface_and_the_statement_says_nothing_is_kept(self):
        for k in ("gmail", "outlook"):
            self.assertIn("never store your emails", SUBS.STATEMENT[k])
            self.assertNotIn("?", SUBS.STATEMENT[k])
        import inspect
        self.assertNotIn('"status": "needs_consent"', inspect.getsource(SUBS._run_tool))


class TheCalendarReadsTheOneBookingRecord(unittest.TestCase):
    def test_an_agapi_booking_by_its_act_id(self):
        from agapi import s2_tools as T, venues as VN

        class Api:
            async def __call__(self, account, method, path, body=None, timeout=90.0):
                return 200, {"reservations": []}
        row = {"trip_item_id": None, "act_id": "act_tv1", "venue": "Sasha Test Venue", "date": "2026-11-06", "time": "20:30", "party": 2,
               "status": "confirmed", "reference": "TV-4BEF26-9C", "country": "ES"}

        class Ctx:
            account = ACCT
        with mock.patch.object(VN, "_API", lambda: mock.Mock(api=Api(), plain_venue=lambda v: v)), \
                mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=[row])), \
                mock.patch("agapi.s2_records.acts", mock.AsyncMock(return_value=[])), mock.patch("agapi.s2_records.record", mock.AsyncMock()):
            for bid in ("act_tv1", "TV-4BEF26-9C"):
                out = run(T.add_to_calendar(Ctx(), {"booking_id": bid}))
                self.assertIn("google", out["links"])


if __name__ == "__main__":
    unittest.main()


class NoRecordReachesTheTestVenue(unittest.TestCase):
    """EU 255 (row 890): a fresh account with NO access record got "Sacha Restaurant", not the test card — the test-venue check read
    the routing mode (no record → the guest marker → live). What a person may book is their RECORD: no record → test (fails closed)."""

    def test_no_record_is_test_a_live_record_is_live(self):
        from agapi import person_access as PA, test_venues as TV
        with mock.patch.object(PA, "get", mock.AsyncMock(return_value={**PA.CLOSED, "source": "no record — closed"})):
            self.assertEqual(run(TV.mode_of(ACCT)), "test")
        with mock.patch.object(PA, "get", mock.AsyncMock(return_value={**PA.CLOSED, "mode": "live", "source": "person_access"})):
            self.assertEqual(run(TV.mode_of(ACCT)), "live")
