"""Sasha 230 · (4) WhatsApp to someone else on /s2: drafted, then the person's OWN WhatsApp pre-filled (wa.me) — they press send;
Sasha's number only inside the 24-hour window (and for the accounts it's live for), as today; one line that says exactly why.
(6) the S1 Trip board: once a leg is booked, only that — never the options chosen before it beside it. Offline.

    cd backend && python -m unittest tests.test_s2_230 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import unquote

from agapi import s2_records as REC, s2_whatsapp as WA, v0 as API

ACCT = "00000000-0000-4000-8000-000000000230"
JON = {"name": "Jon", "number": "+44 7700 900123"}
TEXT = "Running 10 minutes late — see you at Casa Marea."
run = asyncio.run


class TheirOwnWhatsApp(unittest.TestCase):
    def send(self, surface, live, window, said="Message Jon"):
        recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat() if window else None
        contact = {"last_inbound_at": recent} if window else None
        ctx = API.Ctx(account=ACCT, mode="test", user_said=said, session="s230", surface=surface)
        with mock.patch.object(REC, "contact", mock.AsyncMock(return_value=contact)), mock.patch("agapi.s2_tools.live_for", lambda a: live):
            return run(WA.send_whatsapp(ctx, {"to": JON, "text": TEXT}))

    def test_s2_not_live_opens_their_whatsapp_prefilled(self):
        out = self.send("s2", live=False, window=False)
        self.assertEqual(out["status"], "open_in_their_whatsapp")
        self.assertFalse(out["sent_by_sasha"])
        self.assertTrue(out["open"].startswith("https://wa.me/447700900123?text="))
        self.assertEqual(unquote(out["open"].split("text=", 1)[1]), TEXT)
        self.assertEqual(out["why"], WA.WHY_THEIRS["not_live"])

    def test_s2_live_but_no_window_says_exactly_why(self):
        out = self.send("s2", live=True, window=False)
        self.assertEqual((out["status"], out["why"]), ("open_in_their_whatsapp", WA.WHY_THEIRS["no_window"]))
        self.assertIn("24 hours", out["why"])

    def test_s2_inside_the_window_she_sends_as_today(self):
        out = self.send("s2", live=True, window=True)
        self.assertEqual(out["status"], "awaiting_yes")                    # read back first, then their yes — unchanged

    def test_s1_unchanged(self):
        out = self.send("s1", live=False, window=False)
        self.assertNotEqual(out["status"], "open_in_their_whatsapp")

    def test_never_the_set_up_line(self):
        for line in WA.WHY_THEIRS.values():
            self.assertNotRegex(line.lower(), r"set up|isn't set|not set")
            self.assertNotIn("\n", line)

    def test_its_card_is_s2_only(self):
        from app.agent import sasha as AG
        out = self.send("s2", live=False, window=False)
        ev = AG.render("send_whatsapp", out, {})
        self.assertEqual((ev["kind"], ev["open"]), ("wa_open", out["open"]))
        self.assertIn("wa_open", AG.KINDS_S2_ONLY)


class TripBoard(unittest.TestCase):
    def rows(self, *spec):
        return [{"id": f"r{i}", "kind": "flight", "state": st, "slice_key": f"{leg}:x", "snapshot": {"owner": own}}
                for i, (leg, st, own) in enumerate(spec)]

    def test_a_booked_leg_shows_only_what_was_booked(self):
        from booking_signer import basket as BK
        shown = BK.shown_flights(self.rows(("out", "chosen", "easyJet"), ("out", "booked", "Iberia"),
                                           ("back", "chosen", "easyJet"), ("back", "booked", "Iberia")))
        self.assertEqual([(r["slice_key"][:3], r["snapshot"]["owner"]) for r in shown], [("out", "Iberia"), ("bac", "Iberia")])

    def test_before_any_booking_as_before(self):
        from booking_signer import basket as BK
        rows = self.rows(("out", "chosen", "easyJet"), ("back", "chosen", "easyJet"))
        self.assertEqual(len(BK.shown_flights(rows)), 2)

    def test_a_leg_not_booked_keeps_its_choice(self):
        from booking_signer import basket as BK
        shown = BK.shown_flights(self.rows(("out", "booked", "Iberia"), ("back", "chosen", "easyJet")))
        self.assertEqual(len(shown), 2)


if __name__ == "__main__":
    unittest.main()
