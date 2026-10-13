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
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
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


class Wildcards(unittest.TestCase):
    """Python's RobotFileParser ignores '*' and '$'; the platforms' files depend on them (read on the server, 10 Oct)."""
    R = ["Disallow: /search*", "Disallow: *booking/time*", "Disallow: /*/booking?*", "Disallow: /*/l/book/", "Allow: /pro/start*",
         "Disallow: /pro/", "Disallow: /x$", "Crawl-delay: 5"]

    def test_fresha_slots_and_search_are_disallowed_its_venue_page_allowed(self):
        self.assertTrue(PR.verdict(self.R, "https://www.fresha.com/a/spa-madrid-1")[0])
        self.assertFalse(PR.verdict(self.R, "https://www.fresha.com/a/spa-madrid-1/booking/time?x=1")[0])
        self.assertFalse(PR.verdict(self.R, "https://www.fresha.com/a/spa-madrid-1/booking?menu=true")[0])
        self.assertFalse(PR.verdict(self.R, "https://www.fresha.com/search?q=spa")[0])

    def test_longest_match_and_allow_on_a_tie(self):
        self.assertFalse(PR.verdict(self.R, "https://booksy.com/es-es/l/book/123")[0])
        self.assertTrue(PR.verdict(self.R, "https://booksy.com/pro/start-now")[0])
        self.assertFalse(PR.verdict(self.R, "https://booksy.com/pro/other")[0])
        self.assertFalse(PR.verdict(self.R, "https://a.fresha.com/x")[0])
        self.assertTrue(PR.verdict(self.R, "https://a.fresha.com/xy")[0])

    def test_crawl_delay(self):
        self.assertEqual(PR.crawl_delay(self.R), 5.0)


BOOKSY_PAGE = """<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"HealthAndBeautyBusiness","name":"Spa Gate",
"makesOffer":[{"@type":"Offer","name":"Masaje deportivo / SPORT RECOVERY MASAJE","priceCurrency":"EUR","price":86},
{"@type":"Offer","name":"Masaje relajante / RELAX MASAJE 60 min","priceCurrency":"EUR","price":86},
{"@type":"Offer","name":"Masaje relajante / RELAX MASAJE 90 min","priceCurrency":"EUR","price":122}]}</script></html>"""
TREATWELL_PAGE = """<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"HealthAndBeautyBusiness",
"hasOfferCatalog":{"@type":"OfferCatalog","itemListElement":[{"@type":"OfferCatalog","name":"Masajes","itemListElement":[
{"@type":"AggregateOffer","itemOffered":{"@type":"Service","name":"Masaje relajante","additionalProperty":{"@type":"PropertyValue",
"name":"Duration","value":"PT30M - PT1H"}},"lowPrice":"25.00","highPrice":"45.00","priceCurrency":"EUR"},
{"@type":"AggregateOffer","itemOffered":{"@type":"Service","name":"Manicura semipermanente","additionalProperty":{"@type":"PropertyValue",
"name":"Duration","value":"PT45M"}},"price":"20.00","priceCurrency":"EUR"}]}]}}]}</script>"""


class ServicesFromTheirPage(unittest.TestCase):
    """Sasha 233 · the service asked for and its price, from the schema.org data the page publishes (shapes read on the server)."""

    def test_booksy_offers(self):
        s = PR.services(BOOKSY_PAGE)
        self.assertEqual(len(s), 3)
        p = PR.pick(s, "a 60-minute relaxing massage")
        self.assertEqual((p["name"], PR.price_words(p)), ("Masaje relajante / RELAX MASAJE 60 min", "60 min, €86"))
        self.assertEqual(PR.pick(s, "relaxing massage 90 min")["name"], "Masaje relajante / RELAX MASAJE 90 min")

    def test_treatwell_catalogue(self):
        s = PR.services(TREATWELL_PAGE)
        self.assertEqual(PR.price_words(PR.pick(s, "a relaxing massage")), "€25–€45")
        self.assertEqual(PR.price_words(PR.pick(s, "a manicure")), "45 min, €20")

    def test_no_overlap_is_no_guess(self):
        self.assertIsNone(PR.pick(PR.services(BOOKSY_PAGE), "a haircut"))
        self.assertEqual(PR.services("<html>no data</html>"), [])

    def test_offer_reads_only_where_robots_allows(self):
        PR._ROBOTS.clear()
        with mock.patch.object(PR.V, "public_url", lambda u, *a: u), mock.patch.object(PR, "_pace", mock.AsyncMock()):
            http, calls = fake({"https://booksy.com/robots.txt": (200, "User-agent: *\nDisallow: /*/l/book/\n", None),
                                "https://booksy.com/es-es/1_spa-gate": (200, BOOKSY_PAGE, None)})
            got = run(PR.offer(http, "https://booksy.com/es-es/1_spa-gate", "a 60-minute relaxing massage"))
            self.assertEqual((got["platform"], got["service"], got["price"], got["slots"]),
                             ("Booksy", "Masaje relajante / RELAX MASAJE 60 min", "60 min, €86", None))
            self.assertIn("robots", got["slots_why"])
            self.assertEqual({c[0] for c in calls}, {"GET"})
            PR._ROBOTS.clear()
            http, calls = fake({"https://booksy.com/robots.txt": (200, "User-agent: *\nDisallow: /\n", None)})
            self.assertIsNone(run(PR.offer(http, "https://booksy.com/es-es/1_spa-gate", "massage")))
            self.assertEqual([c[1] for c in calls], ["https://booksy.com/robots.txt"])   # the page itself never fetched

    def test_rover_and_restaurants_are_never_read_for_an_offer(self):
        http, calls = fake({})
        self.assertIsNone(run(PR.offer(http, "https://www.rover.com/es/search/", "dog walker")))
        self.assertIsNone(run(PR.offer(http, "https://www.thefork.es/restaurante/x", "dinner")))
        self.assertEqual(calls, [])

    def test_wired_s2_only_and_never_for_a_restaurant(self):
        import inspect
        from agapi import venues as VN
        from booking_signer import ladder_routes as LR
        self.assertIn('{"asked_for": _what(a)} if getattr(ctx, "surface", "s1") == "s2"', inspect.getsource(VN._page))   # Sasha 254 · the page executor
        src = inspect.getsource(LR.prepare_link)
        self.assertIn("not eating_out(asked)", src)
        self.assertIn("PR.SLOTS_CLOSED", src)

    def test_a_spa_is_not_a_restaurant(self):
        """Found live (BELMONT, 11 Oct): the guard used is_restaurant(), TRUE for spas too — the read never ran."""
        from booking_signer import ladder_routes as LR
        for spa in ("a 60-minute relaxing massage", "a Thai massage", "manicure", "a facial at a spa"):
            self.assertFalse(LR.eating_out(spa), spa)
        for food in ("dinner for two", "a table for 4", "Thai dinner", "tapas"):
            self.assertTrue(LR.eating_out(food), food)


class CardsUnderTheirLine(unittest.TestCase):
    def test_the_line_that_showed_them_is_marked(self):
        from agapi import s2_memory as MEM
        m = MEM.fold(None, "Indian in Madrid tonight", "Here are five.", {"cards": [{"place_id": "p1", "name": "A"}], "ribbon": "5 Indian in Madrid",
                                                                           "calls": [{"tool": "search_venues", "ok": True}]})
        m = MEM.fold(m, "What's the weather?", "Sunny.", {})
        self.assertEqual([x.get("cards", False) for x in m["recent"]], [False, True, False, False])


class MemoryIsAnObject(unittest.TestCase):
    def test_saved_as_jsonb_object_not_a_json_string(self):
        """041 applied: the pool's jsonb codec encodes once — the memory goes in as a dict (a string landed as a JSON string)."""
        from agapi import s2_memory as MEM
        got = []

        async def run_(fn):
            class C:
                async def execute(self, sql, *args):
                    got.append(args)
            return await fn(C())
        with mock.patch.object(MEM, "RUN", run_):
            run(MEM._save("00000000-0000-4000-8000-000000000233", {"recent": [{"role": "user", "content": "hi"}]}))
        self.assertIsInstance(got[0][1], dict)


class ThanksInterrupts(unittest.TestCase):
    def test_the_closing_line_carries_interrupt(self):
        import inspect
        from app.agent import sasha as AG
        self.assertIn("'interrupt': True", inspect.getsource(AG.agent_turn))


if __name__ == "__main__":
    unittest.main()


class AccidentPlace234(unittest.TestCase):
    """Sasha 234 · live: the model re-sent place "Lisbon" (the city the case opened with) beside facts.place "Rotunda do Marquês";
    the city won and reached the rental company's read-back. The facts' own place wins; the opening city is never re-sent."""

    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        from unittest import mock
        from agapi import s2_fine_print as FP
        from tests.test_s2_fine_print import FakeAgAPI
        self.FP, self.agapi = FP, FakeAgAPI()
        for p in (mock.patch.object(FP, "CALL", self.agapi), mock.patch.dict(FP._USERS, {}, clear=True), mock.patch.dict(FP._ACCIDENT, {}, clear=True),
                  mock.patch.dict(FP._ACCIDENT_CITY, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def last_facts(self):
        return [b for op, b in self.agapi.calls if op == "cards.accident_step"][-1].get("facts")

    def test_the_facts_place_beats_the_city_sent_again(self):
        from tests.test_s2_fine_print import Ctx, run
        run(self.FP.run_tool(Ctx(), "accident", {"country": "PT", "place": "Lisbon", "rental_company": "Example Rentals"}))
        run(self.FP.run_tool(Ctx(said="14:00, Rotunda do Marquês, AA-00-ZZ"), "accident", {"country": "PT", "place": "Lisbon",
            "facts": {"time": "14:00", "place": "Rotunda do Marquês", "other_vehicle_plate": "AA-00-ZZ"}}))
        self.assertEqual(self.last_facts(), {"time": "14:00", "place": "Rotunda do Marquês", "other_vehicle": {"plate": "AA-00-ZZ"}})

    def test_the_opening_city_alone_is_not_a_new_place(self):
        from tests.test_s2_fine_print import Ctx, run
        run(self.FP.run_tool(Ctx(), "accident", {"country": "PT", "place": "Lisbon", "rental_company": "Example Rentals"}))
        run(self.FP.run_tool(Ctx(said="no"), "accident", {"answer": "no", "place": "Lisbon"}))
        self.assertIsNone(self.last_facts())


class PickNotABundle234(unittest.TestCase):
    """Sasha 234 · live (Treatwell, Método Javier Panizo): a plain "60-minute massage" picked the PACK because it was listed first."""
    SVCS = [{"name": "Pack masaje anticelulítico (masaje + presoterapia)", "minutes": 50},
            {"name": "Masaje deportivo", "minutes": 55}, {"name": "Masaje relajante", "minutes": 55},
            {"name": "Masaje express", "minutes": 30}, {"name": "Masaje tailandés tradicional", "minutes": 90}]

    def test_a_plain_massage_is_not_a_bundle(self):
        from booking_signer import platform_read as PR
        self.assertNotIn("Pack", PR.pick(self.SVCS, "a 60-minute massage")["name"])
        self.assertEqual(PR.pick(self.SVCS, "a 60-minute massage")["minutes"], 55)          # the closer duration, not express

    def test_asked_words_still_lead(self):
        from booking_signer import platform_read as PR
        self.assertEqual(PR.pick(self.SVCS, "a relaxing massage")["name"], "Masaje relajante")
        self.assertIn("Pack", PR.pick(self.SVCS, "the massage pack with presoterapia")["name"])
        self.assertEqual(PR.pick(self.SVCS[:1], "a massage")["name"], self.SVCS[0]["name"])   # a lone bundle still qualifies
        self.assertIsNone(PR.pick(self.SVCS, "a haircut"))


class HoursCheck235(unittest.TestCase):
    """Sasha 235 · the page route says the asked time against the venue's listed hours before the link (found in 234: Método Javier
    Panizo closes at 14:00 on Saturdays and the read-back said "pick Saturday at 5 pm")."""
    # Google's periods: day 0 is SUNDAY. Mon–Fri 07:00–21:00, Sat + Sun 08:00–14:00
    PERIODS = [{"open": {"day": d, "hour": 7, "minute": 0}, "close": {"day": d, "hour": 21, "minute": 0}} for d in range(1, 6)] + \
              [{"open": {"day": d, "hour": 8, "minute": 0}, "close": {"day": d, "hour": 14, "minute": 0}} for d in (6, 0)]
    READ = {"facts": [{"kind": "hours", "source_kind": "places", "source_label": "Google", "evidence": {"periods": PERIODS}}]}

    def test_closed_at_the_asked_time_is_said(self):
        from datetime import date, time
        from booking_signer.ladder_routes import hours_check
        h = hours_check(self.READ, date(2026, 10, 17), time(17, 0))
        self.assertFalse(h["open"])
        self.assertIn("closed on Saturday 17 October at 17:00", h["line"])
        self.assertIn("Sat: 08:00–14:00", h["line"])

    def test_open_is_not_a_free_slot(self):
        from datetime import date, time
        from booking_signer.ladder_routes import hours_check
        h = hours_check(self.READ, date(2026, 10, 17), time(12, 0))
        self.assertTrue(h["open"])
        self.assertIn("open isn't the same as a free slot", h["line"])

    def test_no_hours_says_nothing(self):
        from datetime import date, time
        from booking_signer.ladder_routes import hours_check
        self.assertIsNone(hours_check({"facts": []}, date(2026, 10, 17), time(12, 0)))

    def test_a_listing_re_read_for_this_response_is_used(self):   # live: stored reads withhold Google's hours (its terms)
        from datetime import date, time
        from booking_signer.ladder_routes import hours_check
        hydrated = {"facts": [{"kind": "hours", "source_kind": "places", "value": "Monday: 7:00 AM – 9:00 PM",
                               "detail": {"periods": self.PERIODS, "transient": True}}]}
        self.assertFalse(hours_check(hydrated, date(2026, 10, 17), time(17, 0))["open"])
        src = open(__import__("booking_signer.ladder_routes", fromlist=["x"]).__file__).read()
        self.assertIn("hours_check(await PT.hydrate_read(HTTP, read, NOW()), p.on, p.at)", src)

    def test_the_route_puts_it_before_the_link(self):
        src = open(__import__("booking_signer.ladder_routes", fromlist=["x"]).__file__).read()
        self.assertIn("lines.insert(2 if offer else 1, hours[\"line\"])", src)
