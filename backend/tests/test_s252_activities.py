"""Sasha 252 · THINGS TO DO ARE PLACES (EU 251 FAIL 5: the activity cards had no thumbnails; Tyler: no separate thumbnail code —
the ONE place card, photos from the one source). Offline: activities.verify's answer is given, the venue engine (venue.profile) is
a stand-in at its one call (venue_truth.CALL).

    cd backend && python -m unittest tests.test_s252_activities -v
"""
from __future__ import annotations

import asyncio
import os
import re
import unittest
from unittest import mock

from agapi import s2_fine_print as FP, venue_truth as VT, venues as VN

ACCT = "00000000-0000-4000-8000-000000000252"
PRADO = {"candidate_id": "c-prado", "name": "Museo Nacional del Prado", "official_url": "https://www.museodelprado.es",
         "confidence": "verified", "kind": "visit", "read_at": "2026-10-12",
         "open": {"hours": "10:00–20:00", "quote": "Lunes a sábado de 10:00 a 20:00", "source_url": "https://www.museodelprado.es/visita"},
         "price": {"text": "15 €", "quote": "Entrada general 15 €", "source_url": "https://www.museodelprado.es/entradas"},
         "ticket_url": "https://tickets.museodelprado.es", "say": "The Prado is open 10 to 8."}


async def engine(op, body):   # venue.profile for the Prado's own site: its own photos
    return {"ok": True, "result": {"facts": {"type": {"value": "art museum", "quote": "Museo Nacional del Prado", "source_url": "https://www.museodelprado.es"}},
                                   "photos": [{"url": "https://www.museodelprado.es/img/fachada.jpg"}], "booking": {}}}


class ThingsToDoArePlaces(unittest.TestCase):
    def setUp(self):
        VT._CACHE.clear()
        self.p = mock.patch.object(VT, "CALL", engine)
        self.p.start()
        VN._SHOWN.pop(ACCT, None)

    def tearDown(self):
        self.p.stop()
        VT._CACHE.clear()
        VN._SHOWN.pop(ACCT, None)

    def cards(self):
        return asyncio.run(FP.activity_places(ACCT, [dict(PRADO)], "2026-10-17"))

    def test_the_card_has_a_picture_from_its_own_site(self):
        c = self.cards()[0]
        self.assertEqual(c["place"]["photos"][0], "https://www.museodelprado.es/img/fachada.jpg")
        self.assertEqual(c["place"]["photos_source"], "site")

    def test_the_days_facts_are_quoted_with_their_source(self):
        c = self.cards()[0]
        self.assertEqual(c["place"]["hours"]["value"], "10:00–20:00")
        self.assertEqual(c["place"]["hours"]["source_url"], "https://www.museodelprado.es/visita")
        self.assertEqual(c["place"]["price"]["value"], "15 €")

    def test_the_sheet_reads_the_same_place_and_keeps_the_days_facts(self):
        self.cards()
        card = VN.card_of(ACCT, "act:c-prado", None)   # remembered: /api/place/act:c-prado finds it
        self.assertIsNotNone(card)
        sheet = asyncio.run(VT.profile(card))
        self.assertEqual(sheet["hours"]["value"], "10:00–20:00")
        self.assertTrue(sheet["photos"])

    def test_an_activity_keeps_its_own_name(self):   # its official site may be an umbrella's
        async def umbrella(op, body):
            return {"ok": True, "result": {"facts": {"name": {"value": "Museus e Monumentos de Portugal", "quote": "x", "source_url": "https://x"}},
                                           "photos": [], "booking": {}}}
        with mock.patch.object(VT, "CALL", umbrella):
            VT._CACHE.clear()
            c = asyncio.run(FP.activity_places(ACCT, [dict(PRADO, name="Mosteiro dos Jerónimos")], "2026-10-17"))[0]
            self.assertEqual(c["place"]["name"], "Mosteiro dos Jerónimos")
            self.assertEqual(asyncio.run(VT.profile(VN.card_of(ACCT, c["place_id"], None)))["name"], "Mosteiro dos Jerónimos")

    def test_whatsapp_draws_the_one_place_text(self):
        from booking_signer import wa_agent as WA

        class Out:
            def __init__(self): self.t = []
            def text(self, s): self.t.append(s)
        o = Out()
        WA.KIND_MAP["activities"]({"kind": "activities", "cards": self.cards(), "unread": []}, o)
        self.assertIn("Museo Nacional del Prado", o.t[0])
        self.assertIn("museodelprado.es", o.t[0])

    def test_there_is_no_separate_activity_card(self):
        front = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")
        if not os.path.isdir(front):
            self.skipTest("no frontend checkout")
        for f in ("app/components/cards/S2Cards.tsx", "app/s2/S2App.tsx"):
            src = open(os.path.join(front, f)).read()
            self.assertIsNone(re.search(r"<ActivityCard\b|function ActivityCard", src), f)
            self.assertIn("PlaceCard", src)



class TripTabReadsTheTrip(unittest.TestCase):
    """Sasha 252 · EU 251's noted bug: the Trip tab said "Ask Sasha for flights … book right here" while flights were chosen. The
    flights shown come from the one trip record (trip_figures' lines, via frontend/lib/trip-flights.mjs); the hint only without."""
    def test_the_tab_reads_the_trips_flights_first(self):
        front = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")
        if not os.path.isdir(front):
            self.skipTest("no frontend checkout")
        src = open(os.path.join(front, "app/components/workspace/TripPanel.tsx")).read()
        self.assertIn("tripFlights(tt)", src)
        self.assertRegex(src, r"\{flights\.length \? \(")   # the flights on the trip, before any hint
        lib = open(os.path.join(front, "lib/trip-flights.mjs")).read()
        self.assertIn("chosen: 'chosen — not booked yet'", lib)

    def test_the_lines_carry_kind_state_and_day(self):
        import inspect
        from booking_signer import basket as BK
        src = inspect.getsource(BK.figures_of)
        for k in ('"kind"', '"state"', '"what"', '"day"'):
            self.assertIn(k, src)


if __name__ == "__main__":
    unittest.main()
