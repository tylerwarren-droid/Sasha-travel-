"""Sasha 156 · "restaurants in <anywhere> tonight" is a search (plurals too), and a card with no picture of its own gets
its Google listing's photo — the venue's own first. Offline.

    cd backend && python -m unittest tests.test_search_photos_s156 -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW, venue_read as V
from booking_signer.handoff import booking_handoff


class Plurals(unittest.TestCase):
    def test_anywhere_in_the_world(self):
        for city in ("Madrid", "Lisbon", "New York", "Tokyo", "Hanoi"):
            f = (booking_handoff(f"restaurants in {city} tonight") or {}).get("booking_find")
            self.assertEqual((f or {}).get("where"), city, city)
        for m in ("the best restaurants in Paris", "spas in Madrid", "places to eat in Rome", "bars in Lisbon"):
            self.assertIsNotNone((booking_handoff(m) or {}).get("booking_find"), m)

    def test_a_stay_is_still_the_hotel_flow(self):
        self.assertIsNone(booking_handoff("a hotel in Madrid for 2 nights"))


class _R:
    def __init__(self, status, j):
        self.status_code, self._j = status, j

    def json(self):
        return self._j


NAME = "places/ChIJabcdefghij12/photos/AbCdEfGhIjKlMnOp"


class GooglePhoto(unittest.TestCase):
    def test_the_first_photo_and_its_author(self):
        pl = {"photos": [{"name": NAME, "authorAttributions": [{"displayName": "Ana"}]}]}
        self.assertEqual(V._gphoto(pl), {"name": NAME, "by": ["Ana"]})
        self.assertIsNone(V._gphoto({"photos": [{"name": "../../etc"}]}))
        self.assertIsNone(V._gphoto({}))

    def test_resolved_server_side_never_with_the_key_in_the_url(self):
        seen = {}

        async def http(method, url, headers, json=None):
            seen.update(url=url, headers=headers)
            return _R(200, {"photoUri": "https://lh3.googleusercontent.com/x"})
        with mock.patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "k"}):
            uri = asyncio.run(V.google_photo_uri(http, NAME))
        self.assertEqual(uri, "https://lh3.googleusercontent.com/x")
        self.assertIn("skipHttpRedirect=true", seen["url"])
        self.assertNotIn("key=", seen["url"])

    def test_their_own_picture_first_google_only_when_missing(self):
        c = {"place_id": "p1", "website": "https://their.site", "gphoto": {"name": NAME, "by": []}}

        async def own(c):
            return c["place_id"], "https://their.site/og.jpg"

        async def none(c):
            return c["place_id"], None

        async def goog(http, name, width=480):
            return "https://lh3.googleusercontent.com/g"
        with mock.patch.object(GW, "_own_photo_of", own), mock.patch.object(V, "google_photo_uri", goog):
            self.assertEqual(asyncio.run(GW._photo_of(c)), ("p1", "https://their.site/og.jpg"))
        with mock.patch.object(GW, "_own_photo_of", none), mock.patch.object(V, "google_photo_uri", goog):
            self.assertEqual(asyncio.run(GW._photo_of(c)), ("p1", "https://lh3.googleusercontent.com/g"))
        with mock.patch.object(V, "google_photo_uri", goog):
            self.assertEqual(asyncio.run(GW._photo_of({"place_id": "p2", "gphoto": {"name": NAME}})), ("p2", "https://lh3.googleusercontent.com/g"))


if __name__ == "__main__":
    unittest.main()
