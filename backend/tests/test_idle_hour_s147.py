"""Sasha 147 · AN IDLE HOUR COSTS NOTHING. Every background loop body — the proactive tick, the no-reply and tap offers,
the invitations watcher, the call sweeper (with the email-reply re-reader), the calendar drain — run once a minute for an
hour over an account with real-looking bookings, none of them due. Every outbound HTTP request is caught at httpx itself
(Google Places/Routes, Bland, Anthropic/OpenAI, Twilio, Resend all go through it), and every in-process listing read is
counted. Idle → zero. Then: a confirmed booking inside its last 3 hours asks Routes at most every 5 minutes, and never
once leave-now is sent. Offline.

    cd backend && python -m unittest tests.test_idle_hour_s147 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

import httpx

from booking_signer import (calendar_sync as CAL, call_routes as CRT, call_store as CS, guest_whatsapp as GW, invitations as IV,
                            ladder_routes as LR, ladder_store as LS, proactive as PR)

A = "55555555-5555-4555-8555-555555555555"
GUEST = "+34600000001"
MAD = ZoneInfo("Europe/Madrid")
PAID = ("places.googleapis.com", "routes.googleapis.com", "api.bland.ai", "api.anthropic.com", "api.openai.com", "api.twilio.com",
        "api.resend.com")


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


class IdleHour(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.env = mock.patch.dict(os.environ, {"BLAND_API_KEY": "k", "GOOGLE_PLACES_API_KEY": "k", "SASHA_NO_REPLY_CALL": "1",
                                                "SASHA_TAP_ESCALATION": "1", "SASHA_GUEST_WHATSAPP_TO": "+14155238886",
                                                "SASHA_WA_TEMPLATES": "", "ANTHROPIC_API_KEY": "k"})
        self.env.start()
        self.saved = (GW.STORE, GW.SENDER, GW.api, PR.STORE, PR.NOW, GW.NOW, CRT.CALL_STORE, CRT.NOW, LR.LADDER_STORE, IV.STORE, CAL.STORE)
        GW.STORE, PR.STORE, CRT.CALL_STORE = GW.MemoryGuestStore(), PR.MemoryProactiveStore(), CS.MemoryCallStore()
        LR.LADDER_STORE, IV.STORE, CAL.STORE = LS.MemoryLadderStore(), IV.MemoryInviteStore(), CAL.MemoryCalendarStore()
        PR._ROUTED.clear()
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=MAD)
        PR.NOW = GW.NOW = CRT.NOW = lambda: self.now
        self.sent, self.hosts, self.in_process = [], [], []

        class Sender:
            async def send(s, frm, to, **kw):
                self.sent.append(to)
                return "sent"

            async def quick_reply(s, body, buttons):
                return None
        GW.SENDER = Sender()
        run(GW.STORE.link({"account_id": A, "wa_id_sha256": GW.wa_key(GUEST), "number_e164": GUEST, "linked_at": self.now,
                           "consent_at": self.now, "consent_wording_version": "v3", "consent_text_sha256": "x" * 64}))
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": self.now, "link_tries": []}))
        run(PR.STORE.save_place(A, "home", "Calle Mayor 1, Madrid"))
        in2days = (self.now + timedelta(days=2)).date().isoformat()
        self.rows = [
            {"id": "t-phone", "venue": "⟨marker⟩", "date": in2days, "time": "21:00", "timezone": "Europe/Madrid", "party": 2,
             "status": "confirmed", "channel": "phone", "read_id": "r-1", "receipt": "/api/booking/reservations/t-phone/receipt"},
            {"id": "t-email", "venue": "Casa Lucio", "date": in2days, "time": "14:00", "timezone": "Europe/Madrid", "party": 2,
             "status": "requested", "channel": "email", "read_id": "r-2", "requested_at": (self.now - timedelta(hours=1)).isoformat()},
        ]

        async def api(account, method, path, body=None, timeout=None):
            if path == "/api/booking/reservations":
                return 200, {"reservations": [dict(r) for r in self.rows]}
            self.in_process.append(path)   # anything else in-process (a receipt, a venue read) may reach Google
            return 404, {}
        GW.api = api

        async def caught(client, request, *a, **k):
            self.hosts.append(request.url.host)
            return httpx.Response(200, json={}, request=request)
        self.http = mock.patch.object(httpx.AsyncClient, "send", caught)
        self.http.start()

    def tearDown(self):
        self.http.stop()
        (GW.STORE, GW.SENDER, GW.api, PR.STORE, PR.NOW, GW.NOW, CRT.CALL_STORE, CRT.NOW, LR.LADDER_STORE, IV.STORE, CAL.STORE) = self.saved
        self.env.stop()

    def hour(self, start):
        for m in range(60):
            self.now = start + timedelta(minutes=m)
            run(PR.tick(self.now))
            run(PR.no_reply_offers(self.now))
            run(PR.tap_offers(self.now))
            run(IV.tick())
            run(CRT.sweep_once())
            run(CAL.drain_once())

    def test_an_idle_hour_makes_no_paid_call(self):
        self.hour(self.now)
        self.assertEqual([h for h in self.hosts if h in PAID], [])
        self.assertEqual(self.hosts, [])                      # nothing at all left the process
        self.assertEqual(self.in_process, [])                 # no receipt, no venue read: no Google listing
        self.assertEqual(self.sent, [])                       # no WhatsApp (Twilio)

    def test_inside_a_bookings_last_3_hours_routes_is_asked_every_5_minutes_and_never_after_leave_now(self):
        self.rows[0].update(date=self.now.date().isoformat(), time="14:30", address="Calle Cava Baja 35, Madrid")
        self.hour(self.now)                                   # 12:00–13:00, the booking at 14:30
        routes = [h for h in self.hosts if h == "routes.googleapis.com"]
        self.assertLessEqual(len(routes), 12)
        self.assertGreater(len(routes), 0)
        self.assertEqual([h for h in self.hosts if h in PAID and h != "routes.googleapis.com"], [])
        PR.STORE.sent.append({"account_id": A, "trip_item_id": "t-phone", "kind": "leave_now", "outcome": "sent",
                              "local_day": self.now.date()})
        self.hosts.clear()
        self.hour(self.now + timedelta(minutes=1))
        self.assertEqual([h for h in self.hosts if h == "routes.googleapis.com"], [])


if __name__ == "__main__":
    unittest.main()
