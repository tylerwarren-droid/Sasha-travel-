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

    def test_up_to_twenty_candidates_with_their_listing_facts(self):
        http = Http(search=R(200, {"places": [listing(i) for i in range(1, 25)]}))
        out = run(V.find_venues(http, what="tattoo studio", where="Nairobi", country="ke", now=NOW))
        self.assertEqual((len(out["candidates"]), out["show"]), (20, 5))
        c = out["candidates"][0]
        self.assertEqual((c["name"], c["address"], c["phone"], c["website"], c["type"], c["country"]),
                         ("Ink Studio 1", "1 Moi Ave, Nairobi, Kenya", "+254700000001", "https://ink1.example", "Tattoo shop", "KE"))
        method, url, headers, body = http.requests[0]
        self.assertEqual(body, {"textQuery": "tattoo studio in Nairobi", "maxResultCount": 20, "regionCode": "KE"})
        self.assertIn("places.primaryTypeDisplayName", headers["X-Goog-FieldMask"])
        self.assertEqual(len(out["source"]["sha256"]), 64)

    def test_ranking_facts_as_the_listing_gives_them(self):
        """S-68 step 2 · a response shaped as Places (New) documents it. Synthetic, not recorded: the Maps terms forbid
        storing real listing content (docs/sasha/S-68-step1-places-terms.md), and that includes test fixtures."""
        full = listing(1, rating=4.8, userRatingCount=312, priceLevel="PRICE_LEVEL_MODERATE",
                       location={"latitude": 40.4237, "longitude": -3.7004},
                       regularOpeningHours={"openNow": False, "periods": [
                           {"open": {"day": 2, "hour": 10, "minute": 0}, "close": {"day": 2, "hour": 14, "minute": 0}},
                           {"open": {"day": 2, "hour": 17, "minute": 0}, "close": {"day": 2, "hour": 21, "minute": 0}}],
                           "weekdayDescriptions": ["Tuesday: 10:00 AM – 2:00 PM, 5:00 – 9:00 PM"]})
        bare = listing(2)                                              # a listing with none of them: all None, never 0
        odd = listing(3, rating="4.8", userRatingCount=-1, priceLevel="PRICE_LEVEL_UNSPECIFIED",
                      location={"latitude": 91, "longitude": 0}, regularOpeningHours={"periods": []})
        http = Http(search=R(200, {"places": [full, bare, odd]}))
        a, b, c = run(V.find_venues(http, what="tattoo studio", where="Madrid", country="ES", now=NOW))["candidates"]
        self.assertEqual((a["rating"], a["rating_count"], a["price_level"], a["location"]),
                         (4.8, 312, 2, {"lat": 40.4237, "lng": -3.7004}))
        self.assertEqual(len(a["hours_periods"]), 2)                   # the split day stays two intervals
        for x in (b, c):
            self.assertEqual((x["rating"], x["rating_count"], x["price_level"], x["location"], x["hours_periods"]),
                             (None, None, None, None, None))
        mask = http.requests[0][2]["X-Goog-FieldMask"].split(",")
        for f in ("places.rating", "places.userRatingCount", "places.priceLevel", "places.location", "places.regularOpeningHours"):
            self.assertIn(f, mask)
        self.assertNotIn("places.reviews", mask)                       # Enterprise + Atmosphere: never on a search

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


class Near(unittest.TestCase):
    """S-68 step 3 · straight-line distance from the place the guest named — measured per search, never stored."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-key"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    class Two(Http):
        """The venue search and the "near" lookup, told apart by their field masks."""
        def __init__(self, search, near):
            super().__init__(search=search)
            self.near = near

        async def __call__(self, method, url, headers, json=None):
            self.requests.append((method, url, headers, json))
            return self.near if headers["X-Goog-FieldMask"] == V.NEAR_FIELDS else self.search

    SOL = {"latitude": 40.41694, "longitude": -3.70361}             # Puerta del Sol
    def test_haversine_and_its_words(self):
        retiro = {"lat": 40.41528, "lng": -3.68444}                     # El Retiro: ~1.6 km east
        m = V.haversine_m({"lat": 40.41694, "lng": -3.70361}, retiro)
        self.assertTrue(1600 < m < 1650, m)
        self.assertEqual(V.distance_words(m), "1.6 km away (straight line)")
        self.assertEqual(V.distance_words(347), "350 m away (straight line)")
        self.assertEqual(V.distance_words(3), "10 m away (straight line)")
        self.assertEqual(V.distance_words(None), "distance not known")

    def test_distances_from_the_place_named(self):
        near = listing(9, location=self.SOL)
        a = listing(1, location={"latitude": 40.41528, "longitude": -3.68444})
        b = listing(2)                                                    # no location in its listing
        http = self.Two(R(200, {"places": [a, b]}), R(200, {"places": [near]}))
        out = run(V.find_venues(http, what="tattoo studio", where="Madrid", country="ES", now=NOW, near="Hotel Urban"))
        self.assertEqual(out["near"], {"asked": "Hotel Urban", "found": True})
        x, y = out["candidates"]
        self.assertEqual(x["distance"], "1.6 km away (straight line)")
        self.assertEqual((y["distance_m"], y["distance"]), (None, "distance not known"))
        lookup = [r for r in http.requests if r[2]["X-Goog-FieldMask"] == V.NEAR_FIELDS][0]
        self.assertEqual(lookup[3], {"textQuery": "Hotel Urban, Madrid", "maxResultCount": 1, "regionCode": "ES"})

    def test_my_hotel_is_asked_for_never_guessed(self):
        http = self.Two(R(200, {"places": [listing(1)]}), R(200, {"places": [listing(9, location=self.SOL)]}))
        out = run(V.find_venues(http, what="tattoo studio", where="Madrid", country="ES", now=NOW, near="my hotel"))
        self.assertFalse(out["near"]["found"])
        self.assertIn("which hotel?", out["near"]["why"])
        self.assertEqual(len(http.requests), 1)                           # no lookup for a place not named
        c = out["candidates"][0]
        self.assertEqual((c["distance_m"], c["distance"]), (None, None))

    def test_a_place_google_cannot_find_gives_no_distances_and_says_so(self):
        http = self.Two(R(200, {"places": [listing(1, location=self.SOL)]}), R(200, {}))
        out = run(V.find_venues(http, what="tattoo studio", where="Madrid", country="ES", now=NOW, near="Hotel Nowhere"))
        self.assertEqual(out["near"], {"asked": "Hotel Nowhere", "found": False, "why": "Google Maps has no place matching 'Hotel Nowhere' in Madrid"})
        self.assertIsNone(out["candidates"][0]["distance_m"])
        with self.assertRaises(V.ReadRefused) as e:
            run(V.find_venues(http, what="tattoo studio", where="Madrid", country="ES", now=NOW, near="x"))
        self.assertEqual(e.exception.rule, "near_invalid")


class OpenAtFind(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-key"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_each_candidate_says_whether_it_is_open_then(self):
        split = {"periods": [{"open": {"day": 2, "hour": 10, "minute": 0}, "close": {"day": 2, "hour": 14, "minute": 0}},
                             {"open": {"day": 2, "hour": 17, "minute": 0}, "close": {"day": 2, "hour": 21, "minute": 0}}]}
        http = Http(search=R(200, {"places": [listing(1, regularOpeningHours=split), listing(2)]}))
        out = run(V.find_venues(http, what="tattoo studio", where="Madrid", country="ES", now=NOW, open_at="2026-10-06T15:00"))
        self.assertEqual(out["open_at"], "2026-10-06T15:00")
        a, b = out["candidates"]
        self.assertEqual(a["open_at"]["words"], "Closed Tue 15:00 (opens 17:00)")
        self.assertEqual(b["open_at"], {"known": False, "open": None, "words": "hours not listed"})
        with self.assertRaises(V.ReadRefused) as e:
            run(V.find_venues(http, what="tattoo studio", where="Madrid", country="ES", now=NOW, open_at="Tuesday"))
        self.assertEqual(e.exception.rule, "open_at_invalid")
