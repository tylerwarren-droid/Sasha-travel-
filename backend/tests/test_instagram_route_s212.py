"""Sasha 212 · a studio that books only by an Instagram DM: the handle is read from a link or from the listing's website
(never fetched), and becomes a route Sasha drafts the message for — never a booking.

    cd backend && python -m unittest tests.test_instagram_route_s212 -v
"""
import unittest

from booking_signer import ladder as L, venue_read as V


class Instagram(unittest.TestCase):
    def test_a_profile_link_is_a_handle_and_a_post_is_not(self):
        self.assertEqual(V.instagram_of("https://www.instagram.com/inkgate.madrid/"), "inkgate.madrid")
        self.assertEqual(V.instagram_of("https://instagram.com/inkgate_madrid?igsh=abc"), "inkgate_madrid")
        self.assertEqual(V.instagram_of("https://ig.me/m/inkgate"), "inkgate")
        for not_a_profile in ("https://www.instagram.com/p/Cx12/", "https://www.instagram.com/reel/Cx12/", "https://example.com/inkgate",
                              "https://www.instagram.com/"):
            self.assertIsNone(V.instagram_of(not_a_profile), not_a_profile)

    def test_it_is_never_fetched(self):
        import asyncio
        from datetime import datetime, timezone
        fetched = []

        async def http(method, url, **kw):
            fetched.append(url)
            raise AssertionError("fetched")
        facts, sources = asyncio.run(V.read_site(http, "https://www.instagram.com/inkgate.madrid/", "ES", datetime.now(timezone.utc)))
        self.assertEqual(fetched, [])
        self.assertEqual([(f.kind, f.value) for f in facts], [("instagram", "inkgate.madrid")])

    def test_the_ladder_offers_a_drafted_message(self):
        read = {"name": "Ink Gate", "facts": [{"kind": "instagram", "value": "inkgate.madrid", "source_label": "their Instagram"}]}
        got = L.choose(read)
        self.assertEqual([(r["rung"], r["available"]) for r in got["rungs"]], [("instagram", True)])
        self.assertIn("Instagram message for you to send", got["say"])


if __name__ == "__main__":
    unittest.main()
