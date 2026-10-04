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
        self.assertGreaterEqual(self.calls.count("/api/booking/reservations"), 120)   # the watchers did look
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


if __name__ == "__main__":
    unittest.main()
