"""Sasha 296 · T74 — COMING BACK, AND "STILL HERE." (Tyler, 26 Oct: "when you come back after say thirty seconds… it's just not entirely
clear what needs to happen" · "20 times would get tedious… a slight pause on both ends").

ROOT TEST: (1) the ONE place stays frontend/lib/opening-rule.mjs (held by frontend/scripts/opening-rule.test.mjs): a return is her
still with "Tap to continue"; every move into the corner is settle() — the camera line once a session, then a pause, "Still here.", a
pause. Its WORDS are the backend's — held here. (2) A resume screen, a per-visit timer or a per-device branch = PATCH. (3) After the tap
on a return she speaks first, ONE line that picks up where they were — from her memory, read only (no recall, no handover, no news).
    cd backend && python -m unittest tests.test_s296 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import timedelta
from unittest import mock

from agapi import s2_memory as MEM
from app.agent import sasha as S
from app.agent import voice as V


class TheCornersWords(unittest.TestCase):
    def test_still_here_in_english_and_spanish(self):
        self.assertEqual(V.STILL_HERE, "Still here.")
        self.assertEqual(V.STILL_HERE_ES, "Aquí sigo.")
        self.assertLess(len(V.STILL_HERE), len(V.CAMERA_OFF))   # the short one, after the first time

    def test_the_page_reads_them_with_the_first_line_rule(self):
        got = asyncio.run(S.first_line_rule())
        self.assertEqual((got["still_here"], got["still_here_es"], got["camera_off"]), (V.STILL_HERE, V.STILL_HERE_ES, V.CAMERA_OFF))


class ThePickup(unittest.TestCase):
    def test_her_line_picks_up_where_they_were(self):
        self.assertEqual(V.pickup_line("dinner in Madrid"), "Still on dinner in Madrid?")
        self.assertEqual(V.pickup_line("dinner in Madrid.", ready=True), "Still on dinner in Madrid? It's ready — just say yes.")
        self.assertEqual(V.pickup_line(None), V.PICKUP_NONE)
        self.assertEqual(V.pickup_line("   "), V.PICKUP_NONE)
        self.assertIn("book", V.PICKUP_NONE)   # nothing remembered: still says what she does

    def test_from_her_memory(self):
        now = MEM.NOW().isoformat()
        self.assertEqual(MEM.pickup_of({"thing": "Indian restaurants in Madrid, tonight 21:00", "updated_at": now}, "a"),
                         "Still on Indian restaurants in Madrid, tonight 21:00?")
        self.assertEqual(MEM.pickup_of(None, "a"), V.PICKUP_NONE)
        old = (MEM.NOW() - MEM.OFFER_FOR - timedelta(minutes=1)).isoformat()
        self.assertEqual(MEM.pickup_of({"thing": "x", "updated_at": old}, "a"), V.PICKUP_NONE)   # the same 24 h as line_for
        held = {"thing": "Trebbiano — it's ready, waiting for your yes", "updated_at": now,
                "pending": {"kind": "hold", "tool": "hold_venue", "what": "Trebbiano, today at 21:00", "at": now}}
        with mock.patch.object(MEM, "_hold_live", return_value=True):
            self.assertEqual(MEM.pickup_of(held, "a"), "Still on Trebbiano, today at 21:00? It's ready — just say yes.")
        with mock.patch.object(MEM, "_hold_live", return_value=False):
            self.assertEqual(MEM.pickup_of(held, "a"), "Still on Trebbiano, today at 21:00?")

    def test_read_only(self):
        saved = []
        async def load(_a):
            return {"thing": "a spa on Saturday", "updated_at": MEM.NOW().isoformat()}
        async def save(*a):
            saved.append(a)
        with mock.patch.object(MEM, "_load", load), mock.patch.object(MEM, "_save", save), \
                mock.patch.object(MEM, "put_kinds", side_effect=AssertionError("no handover on a pickup")):
            self.assertEqual(asyncio.run(MEM.pickup("acct")), "Still on a spa on Saturday?")
        self.assertEqual(saved, [])   # nothing kept: the load's recall stays the one that hands over and takes news

    def test_the_route_is_s2_only_and_signed_in(self):
        route = [r for r in S.router.routes if getattr(r, "path", "").endswith("/s2/pickup")]
        self.assertEqual(len(route), 1)
        self.assertEqual(route[0].methods, {"GET"})


if __name__ == "__main__":
    unittest.main()
