"""S-40 · the form measurement job — offline. No Overture query, no venue, no database: fakes throughout.

    cd backend && python -m unittest tests.test_measure_forms -v
"""
import asyncio
import gzip
import json
import random
import unittest

from booking_signer import measure_forms as M

PUBLIC = lambda host: ["93.184.216.34"]


class R:
    def __init__(self, status, text="", headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {"content-type": "text/html"}


class Web:
    def __init__(self, pages):
        self.pages, self.got = pages, []

    async def __call__(self, method, url):
        self.got.append(url)
        return self.pages.get(url, R(404, ""))


class Where(unittest.TestCase):
    OK = {"MEASURE_FORMS_RUN": "1", "RAILWAY_REPLICA_ID": "r", "RAILWAY_DEPLOYMENT_ID": "d", "DATABASE_URL": "postgresql://x"}

    def test_it_never_runs_on_a_mac_even_with_railways_variables(self):
        with self.assertRaisesRegex(M.Refused, "Mac"):
            M.must_be_on_railway(self.OK, "darwin")

    def test_railway_run_is_local_and_refused(self):
        env = {k: v for k, v in self.OK.items() if k != "RAILWAY_REPLICA_ID"}   # `railway run` has no replica
        with self.assertRaisesRegex(M.Refused, "railway run"):
            M.must_be_on_railway(env, "linux")

    def test_the_switch_is_required(self):
        with self.assertRaisesRegex(M.Refused, "MEASURE_FORMS_RUN"):
            M.must_be_on_railway({**self.OK, "MEASURE_FORMS_RUN": ""}, "linux")

    def test_a_railway_deployment_with_the_switch_runs(self):
        M.must_be_on_railway(self.OK, "linux")


class Hosts(unittest.TestCase):
    def test_booking_platforms_restaurant_and_activity_are_never_fetched(self):
        for h in ("www.thefork.es", "www.opentable.es", "widget.covermanager.com", "fareharbor.com", "www.getyourguide.com",
                  "www.viator.com", "www.tiqets.com", "civitatis.com", "feverup.com", "www.eventbrite.es"):
            self.assertIn("booking platform", M.classify_host(h), h)

    def test_social_and_aggregators_are_not_venue_hosts(self):
        for h in ("www.instagram.com", "linktr.ee", "www.tripadvisor.es", "sites.google.com"):
            self.assertIsNotNone(M.classify_host(h), h)
        self.assertIsNone(M.classify_host("www.lacontra.es"))

    def test_registrable_domains(self):
        self.assertEqual(M.registrable("www.shop.example.co.uk"), "example.co.uk")
        self.assertEqual(M.registrable("almagro.labuganvilla.es"), "labuganvilla.es")


class Draw(unittest.TestCase):
    def rows(self):
        rows = []
        for i in range(400):
            rows.append({"id": f"f{i:04d}", "name": f"R{i}", "cat": "restaurant", "websites": [f"https://r{i}.test/"]})
            rows.append({"id": f"a{i:04d}", "name": f"M{i}", "cat": "art_museum", "websites": [f"https://m{i}.test/"]})
        rows += [{"id": "x1", "name": "IG", "cat": "cafe", "websites": ["https://instagram.com/x"]},
                 {"id": "x2", "name": "Fork", "cat": "restaurant", "websites": ["https://www.thefork.es/r/x"]},
                 {"id": "x3", "name": "Chain2", "cat": "restaurant", "websites": ["https://r1.test/other"]}]
        return rows

    def test_own_hosts_one_per_domain_and_the_draw_is_reproducible(self):
        a, ca = M.draw(self.rows(), "Madrid", "ES", random.Random(M.SAMPLE_SEED))
        b, _ = M.draw(self.rows(), "Madrid", "ES", random.Random(M.SAMPLE_SEED))
        self.assertEqual([v.host for v in a], [v.host for v in b])
        self.assertEqual((ca["not_own_host"], ca["duplicate_domain"]), (2, 1))
        self.assertEqual(sum(1 for v in a if v.kind == "food"), M.PER_CITY["food"])
        self.assertEqual(sum(1 for v in a if v.kind == "activity"), M.PER_CITY["activity"])
        self.assertTrue(all(not M.classify_host(v.host) for v in a))

    def test_the_sql_prunes_by_bbox_and_takes_activities_by_pattern(self):
        s = M.places_sql("2026-08-19.0", {"xmin": 1, "xmax": 2, "ymin": 3, "ymax": 4})
        self.assertIn("bbox.xmin BETWEEN 1 AND 2", s)
        self.assertIn("regexp_matches(categories.primary", s)
        self.assertIn("len(websites) > 0", s)


class Boxes(unittest.TestCase):
    B = lambda self, w: {"xmin": 0, "xmax": w, "ymin": 0, "ymax": w}

    def test_the_most_specific_level_wins_and_every_candidate_is_kept(self):
        rows = [("c1", "Lisboa", "county", self.B(9)), ("a1", "Lisboa", "localadmin", self.B(2)), ("a2", "Lisboa", "localadmin", self.B(1))]
        chosen, cands = M.pick_box(rows)
        self.assertEqual((chosen["id"], chosen["subtype"]), ("a1", "localadmin"))
        self.assertEqual([c["id"] for c in cands], ["c1", "a1", "a2"])

    def test_a_locality_beats_a_larger_county(self):
        chosen, _ = M.pick_box([("c1", "X", "county", self.B(9)), ("l1", "X", "locality", self.B(1))])
        self.assertEqual(chosen["id"], "l1")

    def test_no_candidate_is_no_box(self):
        self.assertEqual(M.pick_box([]), (None, []))

    def test_the_query_asks_every_name_and_level(self):
        q = M.box_sql("2026-08-19.0", ("Lisboa", "Lisbon"), "PT")
        self.assertIn("names.primary IN ('Lisboa', 'Lisbon')", q)
        self.assertIn("subtype IN ('locality', 'localadmin', 'county')", q)


class Reading(unittest.TestCase):
    HOME = """<html><a href="/reservas">Reservas</a><a href="https://other.test/book">x</a><a href="/about">About</a>
    <iframe src="https://widget.covermanager.com/x"></iframe><form action="/c"><label for="n">Nombre</label><input id="n" name="n"></form></html>"""

    def venue(self, site="https://venue.test/"):
        return M.Venue("Madrid", "ES", "food", "o1", "V", "restaurant", site, "venue.test")

    def test_robots_first_own_host_only_fragments_kept(self):
        web = Web({"https://venue.test/robots.txt": R(200, "User-agent: *\nAllow: /"), "https://venue.test/": R(200, self.HOME),
                   "https://venue.test/reservas": R(200, "<form><input name='d' type='date'></form>")})
        M.PER_HOST_DELAY_S = 0
        log, pages = asyncio.run(M.read_host(web, self.venue(), PUBLIC))
        self.assertEqual(web.got, ["https://venue.test/robots.txt", "https://venue.test/", "https://venue.test/reservas"])
        f = json.loads(gzip.decompress(pages[0]["fragments_gz"]))
        self.assertEqual(len(f["forms"]), 1)
        self.assertEqual(f["frame_script_hosts"], ["widget.covermanager.com"])
        self.assertIn("covermanager", f["platforms_seen"])
        self.assertEqual(len(pages[0]["sha256"]), 64)

    def test_robots_disallow_means_nothing_is_fetched(self):
        web = Web({"https://venue.test/robots.txt": R(200, "User-agent: *\nDisallow: /")})
        log, pages = asyncio.run(M.read_host(web, self.venue(), PUBLIC))
        self.assertEqual(web.got, ["https://venue.test/robots.txt"])
        self.assertIn("robots.txt disallows", pages[0]["note"])

    def test_a_redirect_to_a_platform_or_another_domain_is_refused(self):
        for target, why in (("https://www.thefork.es/r/x", "booking platform"), ("https://elsewhere.test/", "not the venue's own domain")):
            web = Web({"https://venue.test/robots.txt": R(404), "https://venue.test/": R(302, "", {"location": target})})
            log, pages = asyncio.run(M.read_host(web, self.venue(), PUBLIC))
            self.assertNotIn(target, web.got)
            self.assertIn(why, pages[0]["note"])

    def test_a_non_public_host_is_never_fetched(self):
        web = Web({})
        log, pages = asyncio.run(M.read_host(web, self.venue("http://intranet.test/"), lambda h: ["10.0.0.1"]))
        self.assertEqual(web.got, [])
        self.assertIn("non-public", log["result"])


if __name__ == "__main__":
    unittest.main()
