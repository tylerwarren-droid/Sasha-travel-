"""Sasha 86 · the founder's exact message, "book dinner for 2 in Chamberí on Saturday at 9pm", read back wrong on 1 Oct
2026: the venue was "dinner for 2 in Chamberí", the day "jueves 8 de octubre, a las 0:00", the table "a table" inside
Spanish, the name "tyler". This replays it — the message as the chat parses it, the card picked, the object the details
card sends — and holds every line of the read-back to what he asked for. Offline.

    cd backend && python -m unittest tests.test_chat_readback_sasha86 -v
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from booking_signer import call_routes as CRT, chat_request as CR, handoff as H
from tests.test_booking_ladder import NOW
from tests import test_places_terms as TPT   # the module, not its class: a TestCase imported here would run twice

MESSAGE = "book dinner for 2 in Chamberí on Saturday at 9pm"
THURSDAY_1_OCT = datetime(2026, 10, 1, 17, 0, tzinfo=timezone.utc)
TABERNA = "La Taberna de Paula"


class TheMessage(unittest.TestCase):
    def test_saturday_at_9pm_said_on_thursday_1_october_is_saturday_3_october_at_21_00(self):
        r = H.booking_handoff(MESSAGE, now=THURSDAY_1_OCT)
        self.assertEqual(r["booking_find"], {"what": "dinner", "where": "Chamberí", "open_at": "2026-10-03T21:00"})
        p = r["reservation_draft"]["parts"]
        self.assertEqual(p["when"], {"mode": "at", "at": "2026-10-03T21:00"})
        self.assertEqual(p["how_many"], {"count": 2, "unit": "people"})
        self.assertEqual(r["reservation_draft"]["missing"], [])
        self.assertNotIn("who", p)                                         # no name said: none invented

    def test_a_name_said_plainly_is_the_name_and_saturday_on_a_saturday_is_today(self):
        p = CR.draft("book a table for 2 in Chamberí on Saturday at 9pm under Warren", datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc))["parts"]
        self.assertEqual((p["who"], p["when"]["at"]), ({"name": "Warren"}, "2026-10-03T21:00"))

    def test_the_activity_is_said_in_the_venues_language(self):
        en = {"activity": "a table", "activity_venue_lang": "a table", "category": "restaurant"}
        self.assertEqual(CR.in_venue_language(en, "es")["activity_venue_lang"], "una mesa")
        self.assertEqual(CR.in_venue_language({**en, "activity_venue_lang": "mesa en la terraza"}, "es")["activity_venue_lang"],
                         "mesa en la terraza")                             # the guest's own wording is kept


class TheReadBack(unittest.TestCase):
    """The card picked (a Google Maps listing), then the object the chat's details card sends — as on 1 Oct."""
    make_stores = TPT.PlacesTerms.make_stores
    tearDown = TPT.PlacesTerms.tearDown

    def setUp(self):
        TPT.PlacesTerms.setUp(self)
        self.web.listing = {**TPT.listing(), "displayName": {"text": TABERNA}}

    def test_the_read_back_names_the_place_chosen_on_the_day_asked_in_spanish_under_the_name_given(self):
        find = H.booking_handoff(MESSAGE, now=NOW)       # the suite's clock: Monday 5 Oct, so Saturday is the 10th
        draft = find["reservation_draft"]["parts"]
        r = self.c.post("/api/booking/venues/read", json={"name": TABERNA, "city": "Chamberí", "place_id": TPT.listing()["id"],
                                                          "asked_for": find["booking_find"]["what"]})
        self.assertEqual(r.status_code, 200, r.text)
        reservation = {"schema": "reservation/1", "flow": "book", "who": {"name": "Warren"},
                       "what": draft["what"],                            # "a table" both ways, as the chat's draft has it
                       "where": {}, "when": draft["when"], "how_many": draft["how_many"]}
        prep = self.c.post("/api/booking/calls", json={"read_id": r.json()["read_id"], "reservation": reservation})
        self.assertEqual(prep.status_code, 200, prep.text)
        shown = prep.json()["read_back"]["lines"]
        text = "\n".join(shown)
        self.assertTrue(shown[0].startswith(f"I'll phone {TABERNA} "), shown[0])
        self.assertNotIn("dinner for 2", text)
        self.assertIn("el sábado a las 21:00", text)                       # Saturday 10 Oct, said as the venue says it
        self.assertNotIn("8 de octubre", text)
        self.assertNotIn("0:00,", text)
        self.assertIn("una mesa", text)
        self.assertNotIn("a table", shown[1].split(" (in ")[0])          # the Spanish sentence carries no English
        self.assertIn("Warren", text)
        self.assertNotIn("tyler", text.lower())
        # Sasha 64 · shown and approved, never stored: the call keeps a marker and the hash of exactly what was shown
        call = self.calls.calls[prep.json()["call_id"]]
        self.assertNotIn(TABERNA, json.dumps(call, default=str))
        self.assertIn(CRT.LISTING_NAME_STORED, call["read_back_lines"][0])
        self.assertEqual(call["read_back_sha256"], prep.json()["read_back"]["sha256"])
        request = self.calls.trip_items[prep.json()["trip_item_id"]]["request"]
        self.assertEqual((request["what"]["activity_venue_lang"], request["who"]["name"]), ("una mesa", "Warren"))
        self.assertNotIn(TABERNA, json.dumps(request, default=str))
        placed = self.c.post(f"/api/booking/calls/{prep.json()['call_id']}/place",
                             json={"read_back_sha256": prep.json()["read_back"]["sha256"], "approval": {"how": "button"}})
        self.assertEqual(placed.json()["status"], "placed", placed.text)   # the yes to the shown words dials


if __name__ == "__main__":
    unittest.main()
