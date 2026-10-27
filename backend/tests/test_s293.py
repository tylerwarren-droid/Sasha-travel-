"""Sasha 293 · T72 — "DETAILS" SHOWS THEIR WEBSITE (Tyler, 26 Oct 11:56: "there is no website link").

ROOT TEST: (1) the ONE field is AgAPI's place option — next.input.place.website (their own site) and link (their site, else their
Google listing); S2 keeps both on the remembered card, and /api/place (venue_truth.shape) hands them to the ONE Details view.
(2) S2 building a URL from the name, or a per-venue link = PATCH. (3) Details always has their site when AgAPI gave one, else their
listing; "Back to Sasha" is pinned in frontend/scripts/details-293.test.mjs.
Cause found: a discover card was remembered with its place_id only — Details had neither a website nor a listing.
Offline: AgAPI's answer below is its v1.34+ shape; nothing reaches AgAPI.
    cd backend && python -m unittest tests.test_s293 -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from unittest import mock

from agapi import v0 as API, venue_submit as VS, venue_truth as VT, venues as VN

ACCT = "00000000-0000-4000-8000-000000002930"
run = asyncio.run
LISTING = "https://www.google.com/maps/search/?api=1&query=Casa+Lista&query_place_id=P2"
ANSWER = {"ok": True, "result": {
    "say_text": "x", "pick": {"ref": "a", "name": "Casa Web (test)", "reason": "r"}, "sources_url": "https://agapi.example.test/sources",
    "groups": [{"id": "places", "label": "places", "refs": ["a", "b"]}],
    "options": [{"ref": "a", "group": "places", "kind": "place", "name": "Casa Web (test)", "place_id": "P1", "link": "https://casaweb.example/",
                 "next": {"operation": "venue.profile", "input": {"place": {"place_id": "P1", "name": "Casa Web (test)", "website": "https://casaweb.example/"}}}},
                {"ref": "b", "group": "places", "kind": "place", "name": "Casa Lista (test)", "place_id": "P2", "link": LISTING,
                 "next": {"operation": "venue.profile", "input": {"place": {"place_id": "P2", "name": "Casa Lista (test)"}}}}]}}


def search():
    async def call(account, op, body, approval=None):
        return ANSWER
    ctx = API.Ctx(account=ACCT, mode="test", user_said="tapas restaurants in Madrid", session="s293", surface="s2", via="page")   # Sasha 297 · MOVED: a specific ask (a vague one now hears her one question first)
    with mock.patch.object(VS, "_call", call), mock.patch("agapi.test_venues.search", mock.AsyncMock(return_value=None)), \
            mock.patch.object(VN, "named_on_screen", lambda *a: None):
        return run(API._search_venues(ctx, {"what": "tapas restaurant", "where": "Madrid", "country": "ES"}))   # Sasha 297 · MOVED


class Details(unittest.TestCase):
    def setUp(self):
        VN._SHOWN.pop(ACCT, None)

    def test_their_site_or_their_listing_reaches_details(self):
        out = search()
        web, lst = VN.card_of(ACCT, "P1"), VN.card_of(ACCT, "P2")
        self.assertEqual((web.get("website"), web.get("listing_url")), ("https://casaweb.example/", None))
        self.assertEqual((lst.get("website"), lst.get("listing_url")), (None, LISTING))
        self.assertEqual(VT.shape(web, None)["website"], "https://casaweb.example/")   # /api/place's answer, when the read fails too
        self.assertEqual(VT.shape(lst, None)["listing_url"], LISTING)
        self.assertEqual(out["discover"]["sources_url"], "https://agapi.example.test/sources")

    def test_never_a_url_s2_built(self):
        self.assertEqual(API.place_links({"link": "javascript:alert(1)", "next": {"input": {"place": {"website": "ftp://x"}}}}), {})
        src = inspect.getsource(API.place_links)
        self.assertNotIn("google.com", src)
        self.assertNotIn("quote(", src)


if __name__ == "__main__":
    unittest.main()
