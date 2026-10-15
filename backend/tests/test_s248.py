"""Sasha 248 · ONE VENUE TRUTH — the gate's demo paths as a unit test too (offline: the venue engine's saved answers), and the
removed deciders stay removed."""
from __future__ import annotations

import asyncio
import inspect
import os
import unittest


class DemoPaths(unittest.TestCase):
    def test_the_three_demo_paths(self):
        from scripts import venue_truth_suite as VTS
        self.assertTrue(asyncio.run(VTS.main()))

    def test_in_the_gate(self):
        from scripts import gate
        src = inspect.getsource(gate.main)
        self.assertIn("venue_truth_suite", src)
        self.assertIn("venue_engine_fake.install(", src)   # Sasha 254 · install(submit=True): the booking sender too


class TheSitesWordsStayTheSites(unittest.TestCase):
    def test_a_card_restored_from_memory_is_never_relabelled_as_the_maps(self):   # found live on /s2 (Hammam, restored)
        from agapi import venue_truth as VT, s2_memory as MEM
        card = MEM._card({"place_id": "p", "name": "Hammam", "type": "Arab baths (hammam) and massage centre", "type_source": "site",
                          "google_type": "Spa", "website": "https://madrid.hammamalandalus.com"})
        self.assertEqual((card["type_source"], card["website"]), ("site", "https://madrid.hammamalandalus.com"))
        p = VT.shape(card, None)
        self.assertEqual(p["type"], {"value": "Arab baths (hammam) and massage centre", "source": "site"})
        # Sasha 250 · the map's category is never what it is — not even labelled; it stays on the record as map_says
        p2 = VT.shape({"type": "Korean Restaurant"}, None)
        self.assertEqual((p2["type"], p2["map_says"]), (None, "Korean Restaurant"))
        # … and why a site couldn't be read is one sentence, never the engine's object (it crashed the sheet live)
        p3 = VT.shape({"type": "X"}, {"cant_read": {"rule": "refused", "say": "x.net turned us away.", "evidence": "403", "at": 1.0}})
        self.assertEqual(p3["cant_read"], "x.net turned us away.")


class OneDeciderEach(unittest.TestCase):
    def test_the_question_never_names_a_venue(self):
        from booking_signer.venue_read import stored_name
        self.assertEqual(stored_name("Casa Lucio", "ChIJx", [], "Korean food", "Madrid"), "the place you picked in Madrid")

    def test_headers_describe_the_search_not_every_card(self):
        from agapi import venues as VN
        self.assertEqual(VN.ribbon_line({"what": "Korean food", "where": "Madrid"}, [{"place_id": "a"}] * 3, {}), "3 for “Korean food” in Madrid")
        from agapi import s2_memory as MEM
        self.assertEqual(MEM._thing_of_ribbon("3 for “Korean food” in Madrid"), "Korean food in Madrid")

    def test_the_engine_decides_first(self):
        from agapi import venues as VN
        src = inspect.getsource(VN.hold_venue)
        # Sasha 270 · moved: + their listing on the one path (engine_channel(card or listing_card(rd), …)), Sasha's read without forms
        self.assertLess(src.index("engine_channel(card"), src.index("read_channel(rd, card"))    # Sasha's own read: the fallback only
        self.assertLess(src.index("read_channel(rd, card"), src.index("rules_for("))             # Sasha 254 · then the booking rules

    def test_the_frontend_picks_no_channel(self):
        here = os.path.dirname(__file__)
        src = open(os.path.join(here, "..", "..", "frontend", "app", "components", "ChatBooking.tsx"), encoding="utf-8").read()
        self.assertNotIn("if (em) return <ChatBookingDo", src)
        self.assertIn("<PlaceCard", src)
        s2 = open(os.path.join(here, "..", "..", "frontend", "app", "s2", "S2App.tsx"), encoding="utf-8").read()
        self.assertIn("<PlaceCard", s2)


if __name__ == "__main__":
    unittest.main()
