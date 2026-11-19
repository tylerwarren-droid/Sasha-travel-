"""Sasha 391 · what the person sees after a booking — (2) Book pressed with no on-page confirmation is SENT, never a refusal; (3) one
photo per place, each from its own place.

Measured (Tyler, 19 Nov 13:53–13:56 UTC): he picked listing 1 (ChIJnx_…, Barrio Salamanca); AgAPI pressed Book on CoverManager, the page
showed no confirmation → AgAPI's Stop("no_confirmation") as a FAILED act with a hand-over → Sasha said "check their email … Here's their
page" + "Tap to finish" (an invitation to book again) — CoverManager had confirmed it by email. The list's three Peñalver places showed
ONE photo: the picture of the website they share.

    cd backend && python -m unittest tests.test_s391_after_a_booking -v
"""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest import mock

from agapi import venues as VN
from booking_signer import guest_whatsapp as GW, venue_read as V

HELD = {"summary": "Thursday 19 November at 21:45, 2 people", "when": "2026-11-19T21:45", "party": 2, "venue": "La Taberna de Peñalver"}
PRESSED = {"status": "failed", "submitted": True, "say": "I pressed Book but their page didn't show a confirmation — check their email "
                                                         "before booking again.",
           "hand_over": {"link": "https://www.latabernadepenalver.com/", "copy": [], "why": "no_confirmation"}}
REFUSED = {"status": "failed", "submitted": True, "say": "Their page stopped me before Book.",
           "hand_over": {"link": "https://www.latabernadepenalver.com/", "copy": [], "why": "captcha"}}


class EveryOutcome(unittest.TestCase):
    """every booking outcome → one answer, the right state, a page handed only on a real refusal."""

    def result(self, r):
        return asyncio.run(VN._platform_result(type("C", (), {"account": "acct391"})(), dict(HELD), r, "La Taberna de Peñalver", "x"))

    def test_pressed_without_a_page_confirmation_is_sent_never_a_page(self):
        for r in (PRESSED, {**PRESSED, "status": "sent", "hand_over": None}):   # AgAPI's stop code today; its own "sent" (FOR CR) tomorrow
            got = self.result(r)
            self.assertEqual(got["status"], "sent_unconfirmed")
            self.assertEqual(got["line"], "Sent to La Taberna de Peñalver: Thursday 19 November at 21:45, 2 people. Their confirmation comes "
                                          "by email — don't book it again while it's on its way.")
            flat = json.dumps(got, ensure_ascii=False)
            for gone in ("page_url", "open", "Tap to finish", "http"):
                self.assertNotIn(gone, flat)

    def test_a_real_refusal_hands_their_own_page(self):
        got = self.result(REFUSED)
        self.assertEqual((got["status"], got.get("page_url")), ("not_booked", "https://www.latabernadepenalver.com/"))

    def test_confirmed_on_the_page_is_booked(self):
        got = self.result({"status": "confirmed", "reference": "CM48213", "act_id": "act_1"})
        self.assertEqual(got["status"], "confirmed")
        self.assertNotIn("page_url", got)


class OnePhotoPerPlace(unittest.TestCase):
    """N places → N photos, each from its own place (never the website a group's branches share)."""

    def test_three_branches_three_photos(self):
        cards = [{"place_id": f"p{i}", "website": "https://www.latabernadepenalver.com/", "gphoto": {"name": f"places/p{i}/photos/x"}}
                 for i in (1, 2, 3)]

        async def goog(http, name, width=480):
            return f"https://lh3.googleusercontent.com/{name.split('/')[1]}"

        async def site(c):
            return c["place_id"], "https://www.latabernadepenalver.com/arroz.jpg"
        with mock.patch.object(V, "google_photo_uri", goog), mock.patch.object(GW, "_own_photo_of", site):
            got = asyncio.run(GW._photos_within(cards, 2.0))[0]
        self.assertEqual(got, {f"p{i}": f"https://lh3.googleusercontent.com/p{i}" for i in (1, 2, 3)})
        self.assertEqual(len(set(got.values())), 3)


if __name__ == "__main__":
    unittest.main()
