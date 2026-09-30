"""S-65 · "Find venues" (venue_read.find_venues) and reading the EXACT listing picked (read_venue(place_id=…)). Offline.

    cd backend && python -m unittest tests.test_find_venues -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import venue_read as V

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


class R:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        return self._b


def listing(i, **over):
    return {"id": f"ChIJ-tattoo-{i:04d}", "displayName": {"text": f"Ink Studio {i}"}, "formattedAddress": f"{i} Moi Ave, Nairobi, Kenya",
            "internationalPhoneNumber": f"+254 700 000 00{i}", "websiteUri": f"https://ink{i}.example",
            "primaryTypeDisplayName": {"text": "Tattoo shop"}, "businessStatus": "OPERATIONAL",
            "addressComponents": [{"shortText": "KE", "types": ["country", "political"]}], **over}


class Http:
    def __init__(self, search=None, place=None):
        self.search, self.place, self.requests = search, place, []

    async def __call__(self, method, url, headers, json=None):
        self.requests.append((method, url, headers, json))
        if method == "POST":
            return self.search
        return self.place


def run(c):
    return asyncio.run(c)


class Find(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-key"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_up_to_five_candidates_with_their_listing_facts(self):
        http = Http(search=R(200, {"places": [listing(i) for i in range(1, 8)]}))
        out = run(V.find_venues(http, what="tattoo studio", where="Nairobi", country="ke", now=NOW))
        self.assertEqual(len(out["candidates"]), 5)
        c = out["candidates"][0]
        self.assertEqual((c["name"], c["address"], c["phone"], c["website"], c["type"], c["country"]),
                         ("Ink Studio 1", "1 Moi Ave, Nairobi, Kenya", "+254700000001", "https://ink1.example", "Tattoo shop", "KE"))
        method, url, headers, body = http.requests[0]
        self.assertEqual(body, {"textQuery": "tattoo studio in Nairobi", "maxResultCount": 5, "regionCode": "KE"})
        self.assertIn("places.primaryTypeDisplayName", headers["X-Goog-FieldMask"])
        self.assertEqual(len(out["source"]["sha256"]), 64)

    def test_nothing_found_is_an_empty_list_not_an_error(self):
        out = run(V.find_venues(Http(search=R(200, {})), what="tattoo studio", where="Nowhere", country=None, now=NOW))
        self.assertEqual(out["candidates"], [])

    def test_refusals_say_why(self):
        for kw, rule in (({"what": "x"}, "what_invalid"), ({"where": ""}, "where_invalid"), ({"country": "KEN"}, "country_invalid")):
            args = {"what": "tattoo studio", "where": "Nairobi", "country": None, **kw}
            with self.assertRaises(V.ReadRefused) as e:
                run(V.find_venues(Http(), now=NOW, **args))
            self.assertEqual(e.exception.rule, rule)
        with self.assertRaises(V.ReadRefused) as e:
            run(V.find_venues(Http(search=R(403, {"error": {"message": "API key not valid"}})), what="tattoo studio", where="Nairobi", country=None, now=NOW))
        self.assertEqual(e.exception.rule, "places_refused")
        with mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": ""}):
            with self.assertRaises(V.ReadRefused) as e:
                run(V.find_venues(Http(), what="tattoo studio", where="Nairobi", country=None, now=NOW))
            self.assertEqual(e.exception.rule, "places_not_configured")


class Pick(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-key"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_picking_reads_that_exact_listing_never_a_fresh_search(self):
        http = Http(place=R(200, listing(3, websiteUri=None)))
        read = run(V.read_venue(http, name="Ink Studio 3", city="Nairobi", country=None, website=None, now=NOW, place_id="ChIJ-tattoo-0003"))
        self.assertEqual([m for m, *_ in http.requests], ["GET"])                      # no text search at all
        self.assertTrue(http.requests[0][1].endswith("/places/ChIJ-tattoo-0003"))
        self.assertNotIn("places.", http.requests[0][2]["X-Goog-FieldMask"])            # the details mask has no prefix
        self.assertEqual(read.listing["place_id"], "ChIJ-tattoo-0003")
        self.assertEqual(read.country, "KE")
        self.assertIn(("phone", "+254700000003"), [(f.kind, f.value) for f in read.facts])

    def test_a_listing_that_answers_as_another_place_gives_nothing(self):
        http = Http(place=R(200, listing(9)))
        read = run(V.read_venue(http, name="Ink Studio 3", city="Nairobi", country=None, website=None, now=NOW, place_id="ChIJ-tattoo-0003"))
        self.assertEqual(read.facts, [])

    def test_a_bad_place_id_is_refused(self):
        with self.assertRaises(V.ReadRefused) as e:
            run(V.read_venue(Http(), name="X Studio", city="Nairobi", country=None, website=None, now=NOW, place_id="../../x"))
        self.assertEqual(e.exception.rule, "place_id_invalid")


if __name__ == "__main__":
    unittest.main()
