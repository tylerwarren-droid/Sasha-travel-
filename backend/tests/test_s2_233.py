"""Sasha 233 · (1) the named-platform exception: Fresha, Treatwell, Booksy, Rover — read ONLY where robots.txt allows, GET only,
nothing else fetched; (2) restored cards go back under the line that showed them; "Thanks!" interrupts. Offline (a fake HTTP).

    cd backend && python -m unittest tests.test_s2_233 -v
"""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from booking_signer import platform_read as PR

run = asyncio.run
ROBOTS = """User-agent: Googlebot
Disallow: /

User-agent: *
Disallow: /booking/
Disallow: /account
Allow: /
"""


def fake(pages):
    calls = []

    async def http(method, url, headers, json=None):
        calls.append((method, url, headers))
        st, body, loc = pages.get(url, (404, "", None))
        return SimpleNamespace(status_code=st, text=body, headers={"location": loc} if loc else {})
    return http, calls


class Named(unittest.TestCase):
    def test_only_the_four(self):
        self.assertEqual(PR.named("https://www.fresha.com/a/kamai-madrid-1"), "fresha")
        self.assertEqual(PR.named("https://www.treatwell.es/establecimiento/nail-bar/"), "treatwell")
        self.assertEqual(PR.named("https://booksy.com/es-es/123_nailon"), "booksy")
        self.assertEqual(PR.named("https://www.rover.com/es/search/"), "rover")
        for u in ("https://www.thefork.es/restaurante/x", "https://www.opentable.com/r/x", "https://evilfresha.com.example/x",
                  "https://fresha.com.attacker.io/x"):
            self.assertIsNone(PR.named(u), u)


class Robots(unittest.TestCase):
    def setUp(self):
        PR._ROBOTS.clear()
        p = mock.patch.object(PR.V, "public_url", lambda u, *a: u)
        p.start()
        self.addCleanup(p.stop)

    def test_allowed_and_disallowed_paths(self):
        http, _ = fake({"https://www.treatwell.es/robots.txt": (200, ROBOTS, None)})
        self.assertTrue(run(PR.robots(http, "https://www.treatwell.es/establecimiento/x/"))["allowed"])
        self.assertFalse(run(PR.robots(http, "https://www.treatwell.es/booking/x/"))["allowed"])
        self.assertEqual(run(PR.robots(http, "https://www.treatwell.es/x"))["rules"][:2], ["Disallow: /booking/", "Disallow: /account"])

    def test_unreadable_robots_is_not_permission(self):
        http, _ = fake({"https://booksy.com/robots.txt": (503, "", None)})
        self.assertFalse(run(PR.robots(http, "https://booksy.com/es-es/1_x"))["allowed"])

    def test_fetch_refuses_a_disallowed_path_and_never_fetches_it(self):
        http, calls = fake({"https://www.treatwell.es/robots.txt": (200, ROBOTS, None)})
        with self.assertRaises(PR.Refused) as e:
            run(PR.fetch(http, "https://www.treatwell.es/booking/x/"))
        self.assertEqual(e.exception.rule, "robots_disallow")
        self.assertEqual([c[1] for c in calls], ["https://www.treatwell.es/robots.txt"])

    def test_get_only_no_cookie_and_our_agent(self):
        http, calls = fake({"https://www.treatwell.es/robots.txt": (200, ROBOTS, None),
                            "https://www.treatwell.es/establecimiento/x/": (200, "<html>ok</html>", None)})
        got = run(PR.fetch(http, "https://www.treatwell.es/establecimiento/x/"))
        self.assertEqual(got["text"], "<html>ok</html>")
        for method, _url, headers in calls:
            self.assertEqual(method, "GET")
            self.assertNotIn("cookie", {k.lower() for k in headers})
            self.assertEqual(headers["user-agent"], PR.USER_AGENT)

    def test_a_redirect_off_the_named_platforms_is_refused(self):
        http, calls = fake({"https://www.treatwell.es/robots.txt": (200, ROBOTS, None),
                            "https://www.treatwell.es/establecimiento/x/": (302, "", "https://www.thefork.es/x")})
        with self.assertRaises(PR.Refused) as e:
            run(PR.fetch(http, "https://www.treatwell.es/establecimiento/x/"))
        self.assertEqual(e.exception.rule, "not_named_platform")
        self.assertNotIn("https://www.thefork.es/x", [c[1] for c in calls])

    def test_its_own_client_keeps_no_cookie_jar(self):
        import inspect
        src = inspect.getsource(PR.HTTP)
        self.assertIn("async with httpx.AsyncClient(", src)   # a fresh client per request — nothing carried between requests


class CardsUnderTheirLine(unittest.TestCase):
    def test_the_line_that_showed_them_is_marked(self):
        from agapi import s2_memory as MEM
        m = MEM.fold(None, "Indian in Madrid tonight", "Here are five.", {"cards": [{"place_id": "p1", "name": "A"}], "ribbon": "5 Indian in Madrid",
                                                                           "calls": [{"tool": "search_venues", "ok": True}]})
        m = MEM.fold(m, "What's the weather?", "Sunny.", {})
        self.assertEqual([x.get("cards", False) for x in m["recent"]], [False, True, False, False])


class ThanksInterrupts(unittest.TestCase):
    def test_the_closing_line_carries_interrupt(self):
        import inspect
        from app.agent import sasha as AG
        self.assertIn("'interrupt': True", inspect.getsource(AG.agent_turn))


if __name__ == "__main__":
    unittest.main()
