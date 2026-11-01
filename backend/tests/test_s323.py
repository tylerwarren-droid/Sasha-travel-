"""Sasha 323 · the mailbox link never dies silently; "My bookings" is demo-clean (docs/sasha/S-323-mailbox-link.md).

Root test: (1) one truth — the token refresh every sync starts with (mailbox_links.needs_reconnect_at); (2) no reminder on a timer: told
by that result, once (told_reconnect_at), in the sync that finds it; (3) never dead for more than one sync untold — a refusal tells at
once, a link dead before 323 tells on its first sync after, a reconnect re-arms the telling. Offline.

    cd backend && python -m unittest tests.test_s323 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import unittest
from unittest import mock

from booking_signer import journeys as JN, live_events as LE, mailbox as MB
from booking_signer.vault import crypto as VC

ROOT = pathlib.Path(__file__).resolve().parents[2]
ACCT = "11111111-2222-4333-8444-555555555323"


def link(**kw):
    return {"account_id": ACCT, "vault_item_id": "99999999-2222-4333-8444-555555555323", "consent_at": None, "consent_wording_version": "v1",
            "consent_text_sha256": "x", **kw}


class _Run:
    """sync() with the refresh answering `rule` (None: works); what was said, on which door."""
    def __init__(self, rule=None, row=None):
        self.store, self.wa, self.events, self.news = MB.MemoryMailboxStore(), [], [], []
        asyncio.run(self.store.put_link(row or link()))
        self.rule = rule

    async def _use(self, *a, **k):
        raise VC.UseRefused(self.rule, "Google refused the connection's token")

    def sync(self):
        async def wa(account, text):
            self.wa.append(text)
            return "sent"

        async def keep(account, key, text, url=None):
            self.news.append((key, text, url))
        with mock.patch.object(MB, "STORE", self.store), mock.patch.object(VC, "use_connection", self._use), \
                mock.patch.object(LE, "WA_SEND", wa), mock.patch.object(LE, "publish", lambda a, e: self.events.append(e) or e), \
                mock.patch.object(LE, "keep_news", keep):
            return asyncio.run(MB.sync(ACCT))


class TheLinkNeverDiesSilently(unittest.TestCase):
    def test_invalid_grant_tells_once_on_both_doors_in_the_same_sync(self):
        r = _Run("connection_invalid_grant")
        self.assertEqual(r.sync(), [])
        self.assertEqual(r.wa, [f"{MB.RECONNECT_LINE}: {MB.reconnect_url()}"])          # WhatsApp: the line + its one link
        self.assertEqual(r.events[0]["render"], {"kind": "reconnect", "label": "Reconnect Gmail", "url": "/you#gmail"})   # /s2, open now
        self.assertEqual(r.news[0][2], "/you#gmail")                                      # /s2, its next visit
        st = asyncio.run(r.store.get_link(ACCT))
        self.assertTrue(st["needs_reconnect_at"] and st["told_reconnect_at"])
        r.sync(); r.sync()                                                                # and never again
        self.assertEqual(len(r.wa), 1)
        self.assertEqual(len(r.events), 1)

    def test_a_link_dead_before_323_is_told_on_its_first_sync(self):
        from datetime import datetime, timezone
        r = _Run(row=link(needs_reconnect_at=datetime(2026, 10, 20, tzinfo=timezone.utc)))
        r.sync()
        self.assertEqual(len(r.wa), 1)
        r.sync()
        self.assertEqual(len(r.wa), 1)

    def test_google_busy_is_not_a_death(self):
        for rule in ("connection_http_503", "connection_http_429", "connection_http_500"):
            r = _Run(rule)
            r.sync()
            self.assertEqual((r.wa, r.events), ([], []), rule)
            self.assertFalse(asyncio.run(r.store.get_link(ACCT)).get("needs_reconnect_at"), rule)

    def test_any_other_refusal_is_dead_and_told(self):
        for rule in ("connection_invalid_client", "connection_unauthorized_client", "vault_item_unavailable"):
            r = _Run(rule)
            r.sync()
            self.assertEqual(len(r.wa), 1, rule)

    def test_a_reconnect_rearms_the_telling(self):
        r = _Run("connection_invalid_grant")
        r.sync()
        asyncio.run(r.store.put_link(link()))                                             # reconnected (put_link clears both)
        r.sync()
        self.assertEqual(len(r.wa), 2)

    def test_postgres_reconnect_clears_both_stamps(self):
        src = (ROOT / "backend/booking_signer/mailbox.py").read_text()
        self.assertIn("needs_reconnect_at = null, told_reconnect_at = null", src)
        self.assertNotIn("asyncio.sleep(", src[src.index("async def link_dead"):src.index("async def _told_auto")])   # no timer


class MyBookingsDemoClean(unittest.TestCase):
    ROWS = [{"id": "1", "venue": "Casa Lucio", "date": "2026-11-10", "time": "21:00", "status": "requested"},
            {"id": "2", "venue": "Sasha Test Venue", "date": "2026-11-09", "time": "21:00", "status": "confirmed"},
            {"id": "3", "venue": "Taverna Correo", "date": "2026-11-12", "time": "21:00", "status": "requested"},
            {"id": "4", "venue": "Botín", "date": "2026-10-20", "time": "20:00", "status": "confirmed"},
            {"id": "5", "venue": "DiverXO", "date": "2026-11-20", "time": "20:30", "status": "cancelled"},
            {"id": "6", "venue": "Lhardy", "date": "2026-11-05", "time": "14:00", "status": "confirmed"},
            {"id": "7", "venue": "Asador Sandbox (sandbox)", "date": "2026-11-06", "status": "requested"},
            {"id": "8", "venue": "El Club Allard", "date": None, "time": None, "status": "requested"}]

    def test_upcoming_first_history_behind(self):
        up, past = JN.booking_view([r for r in self.ROWS if not JN.is_scratch(r)], today="2026-11-01")
        self.assertEqual([r["id"] for r in up], ["6", "1", "8"])          # soonest first; no day yet last
        self.assertEqual([r["id"] for r in past], ["5", "4"])             # cancelled and past, newest first

    def test_a_real_person_never_sees_a_test_or_scratch_booking(self):
        with mock.patch("agapi.test_venues.mode_of", mock.AsyncMock(return_value="live")):
            shown = asyncio.run(JN.shown_to(ACCT, self.ROWS))
        self.assertEqual({r["id"] for r in shown}, {"1", "4", "5", "6", "8"})
        with mock.patch("agapi.test_venues.mode_of", mock.AsyncMock(return_value="test")):
            self.assertEqual(len(asyncio.run(JN.shown_to(ACCT, self.ROWS))), len(self.ROWS))   # a test person: how they book

    def test_both_screens_read_the_one_rule(self):
        jn = (ROOT / "backend/booking_signer/journeys.py").read_text()
        self.assertIn('"everything": booking_view(rows)[0], "history": booking_view(rows)[1]', jn)
        self.assertIn("rows = await shown_to(account, rows)", jn)
        self.assertIn("bookings = await JN.shown_to(account, list(bookings or []))", (ROOT / "backend/booking_signer/plan_store.py").read_text())
        mine = (ROOT / "frontend/app/booking-helper/MyBookings.tsx").read_text()
        self.assertIn("bookingReq('/api/booking/journeys')", mine)
        self.assertIn("Show history", mine)
        trip = (ROOT / "frontend/app/components/workspace/TripPanel.tsx").read_text()
        self.assertIn("<PastList rows={past} />", trip)
        s2 = (ROOT / "frontend/app/s2/S2App.tsx").read_text()
        self.assertIn("ev.render?.kind === 'reconnect' && ev.render.url", s2)
        self.assertIn("if (c.k === 'reconnect') return (", s2)


if __name__ == "__main__":
    unittest.main()
