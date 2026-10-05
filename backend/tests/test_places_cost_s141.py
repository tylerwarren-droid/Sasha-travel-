"""Sasha 141 · THE GOOGLE BILL: the minute-by-minute watchers never re-read a phone booking's Google listing. A phone
booking's name lives on its receipt, and the receipt re-reads the listing (an Enterprise Place Details call). Fetched on
every 60 s tick for every upcoming phone booking, that was ≈ 110 calls an hour, all night: 8,255 in two days. The name is
now re-read only for a message actually sent. Offline.

    cd backend && python -m unittest tests.test_places_cost_s141 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from booking_signer import guest_whatsapp as GW, invitations as IV, proactive as PR

ACCOUNT = "55555555-5555-4555-8555-555555555555"
GUEST = "+34600000001"
MAD = ZoneInfo("Europe/Madrid")


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


class WatchersDoNotReadListings(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.env = mock.patch.dict(os.environ, {"SASHA_GUEST_WHATSAPP_TO": "+14155238886", "SASHA_WA_TEMPLATES": "",
                                                "SASHA_NO_REPLY_CALL": "1", "SASHA_TAP_ESCALATION": ""})
        self.env.start()
        self.saved = (GW.STORE, PR.STORE, GW.api, PR.NOW, GW.NOW)
        GW.STORE, PR.STORE = GW.MemoryGuestStore(), PR.MemoryProactiveStore()
        self.now = datetime(2026, 10, 4, 3, 0, tzinfo=MAD)   # the middle of the night: nothing is due
        PR.NOW = GW.NOW = lambda: self.now
        self.calls = []
        far = (self.now + timedelta(days=9)).date().isoformat()
        rows = [{"id": f"t-{i}", "venue": "⟨marker⟩", "date": far, "time": "21:00", "timezone": "Europe/Madrid", "party": 2,
                 "status": st, "channel": "phone", "receipt": f"/api/booking/reservations/t-{i}/receipt"}
                for i, st in enumerate(("confirmed", "pending", "requested", "unclear"))]

        async def api(account, method, path, body=None, timeout=None):
            self.calls.append(path)
            if path == "/api/booking/reservations":
                return 200, {"reservations": [dict(r) for r in rows]}
            if path.endswith("/receipt"):
                return 200, {"venue": {"name": "Casa Lucio"}}
            return 404, {}
        GW.api = api
        run(GW.STORE.link({"account_id": ACCOUNT, "wa_id_sha256": GW.wa_key(GUEST), "number_e164": GUEST, "linked_at": self.now,
                           "consent_at": self.now, "consent_wording_version": "v3", "consent_text_sha256": "x" * 64}))

    def tearDown(self):
        GW.STORE, PR.STORE, GW.api, PR.NOW, GW.NOW = self.saved
        self.env.stop()

    def receipts(self):
        return [p for p in self.calls if p.endswith("/receipt")]

    def test_an_hour_of_ticks_reads_no_receipt(self):
        for m in range(60):
            self.now = datetime(2026, 10, 4, 3, m, tzinfo=MAD)
            run(PR.tick(self.now))
            run(PR.no_reply_offers(self.now))
        self.assertGreaterEqual(self.calls.count("/api/booking/reservations"), 60)    # the watchers did look (the tick, each minute)
        self.assertEqual(self.receipts(), [])                                         # and re-read no listing

    def test_a_guest_asking_still_gets_the_real_name(self):
        rows = run(GW._upcoming(ACCOUNT))
        self.assertEqual({r["venue"] for r in rows}, {"Casa Lucio"})
        self.assertEqual(len(self.receipts()), 4)

    def test_the_watch_scan_keeps_the_marker(self):
        rows = run(GW._upcoming(ACCOUNT, names=False))
        self.assertEqual({r["venue"] for r in rows}, {"⟨marker⟩"})
        self.assertEqual(self.receipts(), [])

    def test_a_morning_brief_sent_names_its_bookings(self):
        today = self.now.date().isoformat()
        GW.api_rows = None

        async def api(account, method, path, body=None, timeout=None):
            self.calls.append(path)
            if path == "/api/booking/reservations":
                return 200, {"reservations": [{"id": "t-9", "venue": "⟨marker⟩", "date": today, "time": "21:00", "timezone": "Europe/Madrid",
                                               "party": 2, "status": "confirmed", "channel": "phone",
                                               "receipt": "/api/booking/reservations/t-9/receipt"}]}
            if path.endswith("/receipt"):
                return 200, {"venue": {"name": "Casa Lucio"}}
            return 404, {}
        GW.api = api
        sent = []

        async def fake_send(ch, kind, b, text, variables, local_day, status):
            if callable(text):
                text, variables = await text()
            sent.append((kind, text))
            return "sent"
        with mock.patch.object(PR, "_send", fake_send):
            for h in (7, 8, 9):
                self.now = datetime(2026, 10, 4, h, 30, tzinfo=MAD)
                run(PR.tick(self.now))
        briefs = [t for k, t in sent if k == "morning_brief"]
        if briefs:   # where a brief goes out, it names the place (one re-read, for the message sent)
            self.assertIn("Casa Lucio", briefs[0])
            self.assertNotIn("⟨marker⟩", briefs[0])
        self.assertLessEqual(len(self.receipts()), 2 * len(sent) + 1)


class AlreadySentCostsNothing(WatchersDoNotReadListings):
    """Sasha 142 · a day-before reminder is 'due' from the evening before until the booking starts; once sent, each
    minute's tick found it 'already sent' only AFTER re-reading every phone booking's listing (≈ 1 call a minute)."""

    def test_a_due_reminder_already_sent_reads_no_listing(self):
        tomorrow = (self.now + timedelta(days=1)).date().isoformat()

        async def api(account, method, path, body=None, timeout=None):
            self.calls.append(path)
            if path == "/api/booking/reservations":
                return 200, {"reservations": [{"id": "t-1", "venue": "⟨marker⟩", "date": tomorrow, "time": "21:00", "timezone": "Europe/Madrid",
                                               "party": 2, "status": "confirmed", "channel": "phone",
                                               "receipt": "/api/booking/reservations/t-1/receipt"}]}
            if path.endswith("/receipt"):
                return 200, {"venue": {"name": "Casa Lucio"}}
            return 404, {}
        GW.api = api
        claimed = []

        async def claim(row):
            claimed.append(row["kind"])
            return None   # already sent

        with mock.patch.object(PR.STORE, "claim", claim):
            for m in range(30):
                self.now = datetime(2026, 10, 4, 19, m, tzinfo=MAD)
                run(PR.tick(self.now))
        self.assertTrue(claimed)                 # it was due, and the dedupe was asked
        self.assertEqual(self.receipts(), [])    # and no listing was re-read for it


class LeaveNowReadsNoListing(WatchersDoNotReadListings):
    """Sasha 146 · a confirmed phone booking within 3 hours, with no address: the tick routed to it by re-reading its
    Google listing for the name — every minute (5 Oct, 07:00 onwards). Now: its stored place ID, and no Routes call once
    leave_now is sent."""

    def test_routed_by_place_id_and_stopped_once_sent(self):
        from booking_signer import ladder_routes as LR
        soon = datetime(2026, 10, 5, 10, 0, tzinfo=MAD)
        self.now = datetime(2026, 10, 5, 8, 30, tzinfo=MAD)

        async def api(account, method, path, body=None, timeout=None):
            self.calls.append(path)
            if path == "/api/booking/reservations":
                return 200, {"reservations": [{"id": "t-7", "venue": "⟨marker⟩", "date": soon.date().isoformat(), "time": "10:00",
                                               "timezone": "Europe/Madrid", "party": 2, "status": "confirmed", "channel": "phone",
                                               "read_id": "r-7", "receipt": "/api/booking/reservations/t-7/receipt"}]}
            if path.endswith("/receipt"):
                return 200, {"venue": {"name": "Casa Lucio"}}
            return 404, {}
        GW.api = api
        routes = []

        async def routes_http(url, headers, body):
            routes.append(body["destination"])
            return 200, {"routes": [{"duration": "600s"}]}
        store = mock.Mock()
        store.get_read = mock.AsyncMock(return_value={"read": {"listing": {"place_id": "ChIJ-casa-lucio"}}})
        run(PR.STORE.save_place(ACCOUNT, "home", "Calle Mayor 1, Madrid"))
        # only leave_now here: a reminder actually SENT re-reads its name, rightly (AlreadySentCostsNothing covers that)
        run(PR.STORE.set_prefs(ACCOUNT, off_kinds=["day_before", "not_confirmed", "morning_brief"]))
        with mock.patch.object(PR, "ROUTES_HTTP", routes_http), mock.patch.object(LR, "LADDER_STORE", store), \
             mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "k"}):
            for m in range(3):
                run(PR.tick(datetime(2026, 10, 5, 8, 30 + m, tzinfo=MAD)))
            self.assertEqual(self.receipts(), [])                       # no listing re-read for the destination
            self.assertTrue(routes and all(d == {"placeId": "ChIJ-casa-lucio"} for d in routes))
            n = len(routes)
            PR.STORE.sent.append({"account_id": ACCOUNT, "trip_item_id": "t-7", "kind": "leave_now", "outcome": "sent",
                                  "local_day": soon.date()})
            for m in range(3):
                run(PR.tick(datetime(2026, 10, 5, 9, m, tzinfo=MAD)))
            self.assertEqual(len(routes), n)                            # sent: no more Routes calls


if __name__ == "__main__":
    unittest.main()
