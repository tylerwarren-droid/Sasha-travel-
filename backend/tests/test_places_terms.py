"""Sasha 64 · Google Maps content is never stored; a call never speaks it; a listing number is only dialled. Offline.

    cd backend && python -m unittest tests.test_places_terms -v
"""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from booking_signer import places_terms as PT
from booking_signer.call_store import MemoryCallStore
from booking_signer.ladder_store import MemoryLadderStore
from tests.test_booking_ladder import LadderRoutes, R, Web

PID = "ChIJ-ink-studio-0001"
NAME, ADDRESS, NUMBER = "Inkredible Secret Studio", "Calle Escondida 9, 28004 Madrid", "+34911223344"


def listing(phone="+34 911 22 33 44", website=None):
    return {"id": PID, "displayName": {"text": NAME}, "formattedAddress": ADDRESS, "internationalPhoneNumber": phone,
            "addressComponents": [{"shortText": "ES", "types": ["country", "political"]}],
            **({"websiteUri": website} if website else {})}


class ListingWeb(Web):
    """Web, plus Place Details (GET places/{id}) answering from the same listing."""
    async def __call__(self, method, url, headers=None, json=None):
        if method == "GET" and url.startswith("https://places.googleapis.com/v1/places/"):
            self.requests.append((method, url, json))
            return R(200, self.listing)
        return await super().__call__(method, url, headers, json)


class PlacesTerms(unittest.TestCase):
    def make_stores(self):
        return MemoryCallStore(), MemoryLadderStore()

    def setUp(self):
        LadderRoutes.setUp(self)
        self.keys = mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "places-test"})
        self.keys.start()
        web = ListingWeb(pages=self.web.pages)
        web.listing = listing()
        self.web.__class__, self.web.__dict__ = ListingWeb, {**web.__dict__}

    def tearDown(self):
        self.keys.stop()
        LadderRoutes.tearDown(self)

    BOOKING = LadderRoutes.BOOKING

    def pick(self):
        r = self.c.post("/api/booking/venues/read", json={"name": NAME, "city": "Madrid", "place_id": PID, "asked_for": "tattoo studio"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def assert_no_listing_content(self, obj, where):
        text = json.dumps(obj, default=str)
        for s in (NAME, ADDRESS, NUMBER, "911 22 33 44", "Calle Escondida"):
            self.assertNotIn(s, text, f"{where} stores the listing's {s!r}")

    def test_a_picked_listing_is_shown_once_and_stored_as_its_place_id_only(self):
        v = self.pick()
        self.assertEqual((v["listing"]["name"], v["listing"]["attribution"]), (NAME, "Google Maps"))   # shown, attributed
        self.assertIn(NUMBER, [f["value"] for f in v["facts"]])
        row = self.ladder.reads[v["read_id"]]
        self.assert_no_listing_content(row, "the venue read")
        self.assertEqual(row["venue_name"], "tattoo studio in Madrid")            # the guest's words, not the listing's
        self.assertEqual(row["read"]["listing"], {"place_id": PID})
        again = self.c.get(f"/api/booking/venues/read/{v['read_id']}").json()      # re-read from Google, not from storage
        self.assertIn(NUMBER, [f["value"] for f in again["facts"]])

    def test_a_listing_number_is_dialled_never_stored_never_shown_never_spoken(self):
        v = self.pick()
        prep = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING})
        self.assertEqual(prep.status_code, 200, prep.text)
        lines = prep.json()["read_back"]["lines"]
        self.assertEqual(lines[0], "I'll phone tattoo studio in Madrid on the number its Google Maps listing gives.")
        call = self.calls.calls[prep.json()["call_id"]]
        self.assert_no_listing_content({k: call[k] for k in ("brief", "read_back_lines", "dialled_number")}, "the call")
        self.assertEqual(call["dialled_number"], PT.number_key(NUMBER))
        self.assertEqual((call["brief"]["number_source_kind"], call["brief"]["number_ref"]["place_id"]), ("places", PID))
        self.assert_no_listing_content(self.calls.trip_items, "the reservation")
        r = self.c.post(f"/api/booking/calls/{prep.json()['call_id']}/place",
                        json={"read_back_sha256": prep.json()["read_back"]["sha256"], "approval": {"how": "button"}})
        self.assertEqual(r.json()["status"], "placed", r.text)
        bland = [b for m, u, b in self.web.requests if u.startswith("https://api.bland.ai")][0]
        self.assertEqual(bland["phone_number"], NUMBER)                                          # dialled
        for spoken in (bland["task"], bland["first_sentence"]):                                  # never spoken
            for s in (NAME, ADDRESS, NUMBER):
                self.assertNotIn(s, spoken)
        self.assert_no_listing_content(self.calls.calls[prep.json()["call_id"]], "the placed call")

    def test_a_changed_listing_number_is_not_dialled(self):
        v = self.pick()
        prep = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING}).json()
        self.web.listing = listing(phone="+34 999 00 00 00")
        r = self.c.post(f"/api/booking/calls/{prep['call_id']}/place",
                        json={"read_back_sha256": prep["read_back"]["sha256"], "approval": {"how": "button"}})
        self.assertEqual((r.status_code, r.json()["rule"]), (422, "listing_number_changed"))
        self.assertFalse([u for m, u, b in self.web.requests if u.startswith("https://api.bland.ai")])
        self.assertEqual(self.calls.calls[prep["call_id"]]["status"], "awaiting_approval")

    def test_a_cancellation_re_reads_the_listing_number_and_stores_it_the_same_way(self):
        v = self.pick()
        prep = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING}).json()
        self.calls.calls[prep["call_id"]].update(status="answered", outcome="yes")   # the venue said yes
        c = self.c.post("/api/booking/calls", json={"cancels_call_id": prep["call_id"]})
        self.assertEqual(c.status_code, 200, c.text)
        cancel = self.calls.calls[c.json()["call_id"]]
        self.assert_no_listing_content({k: cancel[k] for k in ("brief", "read_back_lines", "dialled_number")}, "the cancel call")
        self.assertEqual((cancel["dialled_number"], cancel["brief"]["number_ref"]["place_id"]), (PT.number_key(NUMBER), PID))
        self.assertEqual(c.json()["read_back"]["lines"][0], "I'll phone tattoo studio in Madrid on the number its Google Maps listing gives.")

    def test_the_venues_own_number_is_preferred_and_kept(self):
        self.web.listing = listing(website="https://www.lacontra.test/")           # its own site lists +34915001122
        v = self.pick()
        prep = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING}).json()
        call = self.calls.calls[prep["call_id"]]
        self.assertEqual((call["dialled_number"], call["brief"]["number_source_kind"]), ("+34915001122", "site"))
        self.assertEqual(prep["read_back"]["lines"][0], "I'll phone tattoo studio in Madrid, +34915001122 — the number on their website, lacontra.test.")

    def test_stored_name_rules(self):
        from booking_signer.venue_read import Fact, stored_name
        site = Fact("name", "Calma Spa", "site", "https://calma.test/", "their website, calma.test", "", "", "")
        self.assertEqual(stored_name("Calma", None, [site], None, "Madrid"), "Calma")             # typed: the guest's words
        self.assertEqual(stored_name(NAME, PID, [site], "massage", "Madrid"), "Calma Spa")       # picked: the site's own
        self.assertEqual(stored_name(NAME, PID, [], "massage", "Madrid"), "massage in Madrid")   # else what was asked for
        seo = Fact("name", "Ink Sweet Tattoo Studio | Mejor estudio de tatuajes en Madrid", "site", "u", "l", "", "", "")
        self.assertEqual(stored_name(NAME, PID, [seo], None, "Madrid"), "Ink Sweet Tattoo Studio")   # live, 1 Oct


if __name__ == "__main__":
    unittest.main()


from tests import test_booking_ladder as TBL  # noqa: E402
from tests.test_booking_ladder import PG_URL  # noqa: E402


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class PlacesTermsOnPostgres(unittest.TestCase):
    """The live schema's checks hold the stored form too (013 met the old dialled_number check on 1 Oct)."""
    setUpClass = classmethod(TBL.OnPostgres.setUpClass.__func__)
    make_stores = TBL.OnPostgres.make_stores
    _q = TBL.OnPostgres._q
    setUp, tearDown, pick = PlacesTerms.setUp, PlacesTerms.tearDown, PlacesTerms.pick
    BOOKING = PlacesTerms.BOOKING

    def test_a_listing_number_call_is_recorded_hashed(self):
        v = self.pick()
        prep = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING})
        self.assertEqual(prep.status_code, 200, prep.text)
        row = self._q("select dialled_number, brief from booking_calls where call_id = $1::uuid", prep.json()["call_id"])[0]
        self.assertEqual(row["dialled_number"], PT.number_key(NUMBER))
        stored = self._q("select read from venue_reads where read_id = $1::uuid", v["read_id"])[0]["read"]
        self.assertNotIn(NUMBER, json.dumps(stored, default=str))
