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


RENFE = {"from": "Renfe <venta@renfe.com>", "subject": "Confirmación de compra - Localizador X7K2PQ", "date": "Sun, 01 Nov 2026 09:12:00 +0100",
         "text": "Localizador: X7K2PQ\nTrayecto: Madrid-Puerta de Atocha → Barcelona-Sants\nFecha: 13 de noviembre de 2026\nSalida: 08:00\n"
                 "Tarifa: Básico\nViajeros: 1\nImporte total: 45,60 €"}   # SYNTHETIC (AgAPI's rail_fixtures shape) — never anyone's mail
TRIP = {"operator": "Renfe", "origin": "Madrid-Puerta de Atocha", "destination": "Barcelona-Sants", "date": "2026-11-13", "departs": "08:00",
        "reference": "X7K2PQ", "fare": "Básico", "passengers": 1, "price_eur": 45.6}
OPTIONS = {"act_id": "act_r1", "kind": "train", "operator": "Renfe", "fare": "Básico", "known": True,
           "where": {"page": "https://www.renfe.com/es/es/gestiona-tu-billete/tus-reservas/consulta-tus-viajes", "reference": "X7K2PQ", "filled": "never"},
           "options": [{"action": "change", "allowed": True, "say": "Change: €10 + the price difference, until 24 hours before departure."},
                       {"action": "cancel", "allowed": False, "say": "This fare can't be cancelled (only within 2 hours of buying)."}]}


class CR152Wired(unittest.TestCase):
    """AgAPI's two ops, answered as v1.52.0 answers them: the ticket lands on his trip, and "cancel my Barcelona train" is its fare + one tap."""
    def calls(self):
        seen = []

        async def call(account, op, body, approval=None):
            seen.append((op, body))
            if op == "venue.confirmation":
                return {"ok": True, "result": {"matched": True, "act_id": "act_r1", "kind": "train", "state": "confirmed", "trip": TRIP,
                                               "say_text": "Got it: your Renfe train Madrid-Puerta de Atocha → Barcelona-Sants, Fri 13 Nov 08:00 — ref X7K2PQ, fare Básico."}}
            if op == "venue.manage_options":
                return {"ok": True, "result": OPTIONS}
            return {"ok": False, "error": {"code": "invalid_input", "message": "x"}}
        return seen, call

    def test_a_renfe_ticket_lands_on_the_trip_and_is_said_once(self):
        from agapi import self_booked as SB, venue_submit as VS
        seen, call = self.calls()
        kept = {}
        with mock.patch.object(VS, "_call", call), mock.patch.object(VS, "end_user", mock.AsyncMock(return_value="eu_1")), \
                mock.patch.object(VS, "_remember", mock.AsyncMock(side_effect=lambda a, act: kept.update(act))):
            got = asyncio.run(SB.from_mail(ACCT, RENFE))
        self.assertEqual((got["matched"], got["act_id"]), (True, "act_r1"))
        self.assertEqual(seen[0][0], "venue.confirmation")
        self.assertNotIn("act_id", seen[0][1])                                            # no act_id: AgAPI's reader opens the record
        self.assertEqual((kept["venue"], kept["when"], kept["reference"]), ("Renfe · Madrid-Puerta de Atocha → Barcelona-Sants", "2026-11-13T08:00", "X7K2PQ"))

    def test_not_a_known_sellers_email_keeps_nothing(self):
        from agapi import self_booked as SB, venue_submit as VS
        async def call(*a, **k):
            return {"ok": False, "error": {"code": "invalid_input", "message": "not a known seller"}}
        with mock.patch.object(VS, "_call", call), mock.patch.object(VS, "end_user", mock.AsyncMock(return_value="eu_1")):
            self.assertIsNone(asyncio.run(SB.from_mail(ACCT, {"from": "x@example.com", "subject": "hi", "text": "hello"})))

    def test_cancel_and_change_answer_from_the_fare_with_the_operators_page_nothing_sent(self):
        from agapi import self_booked as SB
        c = SB.answer(OPTIONS, "cancel")
        self.assertEqual((c["status"], c["sent"], c["button"]["link"]), ("their_page", False, OPTIONS["where"]["page"]))
        self.assertTrue(c["say"].startswith("This fare can't be cancelled"))
        self.assertIn("X7K2PQ", c["say"])
        self.assertTrue(SB.answer(OPTIONS, "change")["say"].startswith("Change: €10"))

    def test_the_hooks(self):
        v = (ROOT / "backend/agapi/venues.py").read_text()
        self.assertIn("m = await SB.manage(ctx.account, a[\"act_id\"])", v)
        self.assertLess(v.index("m = await SB.manage(ctx.account, a[\"act_id\"])"), v.index("r = await VS.cancel_submit(ctx.account, held, said)"))
        self.assertIn("m = await SB.manage(ctx.account, b[\"act_id\"])", (ROOT / "backend/agapi/s2_manage.py").read_text())
        mb = (ROOT / "backend/booking_signer/mailbox.py").read_text()
        self.assertIn("got = await SB.from_mail(account,", mb)
        self.assertNotIn("renfe", mb.lower())                                             # no seller list in Sasha: AgAPI's table decides


class OneReadBackOneYes(unittest.TestCase):
    """VOICE LOOP 5's root (the gate's probe, 1 Nov 14:28 UTC, run 2/6): "Book it." → hold_booking!no_trip, propose_trip,
    hold_booking!travellers_missing → she said "…the whole thing comes to about €2,771." (no ask) → "Yes." → travellers asked AFTER it →
    the read-back needed a second yes. PRODUCT: the turn now ends asking for the travellers, by code."""
    def test_the_failing_turn_asks_for_the_travellers(self):
        from app.agent import sasha as AG
        from booking_signer import passengers as PX
        calls = [{"tool": "hold_booking", "code": "no_trip"}, {"tool": "propose_trip"}, {"tool": "hold_booking", "code": "travellers_missing"}]
        self.assertEqual(AG.travellers_ask(calls, "I've put a trip together for you. The whole thing comes to about €2,771."), PX.ASK)

    def test_never_twice_and_never_after_a_hold_that_worked(self):
        from app.agent import sasha as AG
        self.assertIsNone(AG.travellers_ask([{"tool": "hold_booking", "code": "travellers_missing"}],
                                            "For the airline, I need each traveller's title, full name and date of birth."))
        self.assertIsNone(AG.travellers_ask([{"tool": "hold_booking", "code": "travellers_missing"}, {"tool": "save_travellers"},
                                             {"tool": "hold_booking"}], "Shall I go ahead and book it?"))

    def test_the_gate_holds_it(self):
        vl = (ROOT / "backend/scripts/voice_loop_suite.py").read_text()
        self.assertIn("the travellers were asked after his yes", vl)
        self.assertIn('fail.append(f"payment links on the phone: {len(links)} (want exactly one)', vl)   # still exactly one link


if __name__ == "__main__":
    unittest.main()
