"""S-36 · the ladder — what Magellan reads, the chooser's sentence, the phone rung on a READ number, and the email rung
with Resend's answer read and replies matched by address.

    cd backend && python -m unittest tests.test_booking_ladder -v

Offline: venue pages, Google Places, Resend and Bland are fakes; no host is resolved (a fake resolver says public
or private). The route half runs in memory and, with BOOKING_TEST_DATABASE_URL, on Postgres with 001–004 applied —
⚠ without it the Postgres half is SKIPPED, and says so.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import pathlib
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import call_routes, emailing as E, ladder as L, ladder_routes, optins as O, routes, slot_link as SL, stop as S, venue_read as V
from booking_signer.account import DEMO_ACCOUNT_ID
from booking_signer.call_store import MemoryCallStore, PostgresCallStore
from booking_signer.ladder_store import MemoryLadderStore, PostgresLadderStore
from booking_signer.store import PostgresStore, StorageUnavailable

HERE = pathlib.Path(__file__).parent
SQL_DIR = HERE.parent / "booking_signer" / "sql"
PG_URL = os.getenv("BOOKING_TEST_DATABASE_URL", "")
NOW = datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc)   # a Monday
SECRET = "whsec_" + base64.b64encode(b"test-webhook-secret-not-real").decode()
ENV = {"SASHA_BOOKING_KEY": "test-booking-key", "SASHA_CALL_SWEEP": "0", "SASHA_CALLS_ENABLED": "1", "BLAND_API_KEY": "bland-test", "SASHA_TEST_CALL_NUMBER": "+351912000000",
       "SASHA_EMAILS_ENABLED": "1", "SASHA_RESEND_API_KEY": "re_test", "RESEND_API_KEY": "", "SASHA_EMAIL_FROM": "Sasha <sasha@mail.kanoe.test>",
       "SASHA_INBOUND_DOMAIN": "in.kanoe.test", "RESEND_WEBHOOK_SECRET": SECRET, "GOOGLE_PLACES_API_KEY": "",
       "SASHA_PHONE_NUMBER": "", "SASHA_CALLS_PER_DAY": "3", "SASHA_EMAILS_PER_DAY": "5"}

LA_CONTRA_SITE = """<html><head><script type="application/ld+json">{"@type":"Restaurant","telephone":"+34 915 00 11 22","email":"reservas@lacontra.test"}</script></head>
<body><a href="tel:915001122">Llámanos</a> <a href="mailto:hola@lacontra.test?subject=Hi">Escríbenos</a>
<a href="https://wa.me/34600111222">WhatsApp</a> <a href="/contacto">Contacto</a>
<p>Escríbenos a info@lacontra.test o ven a vernos.</p> <img src="logo@2x.png"></body></html>"""
PSI_LIKE = """<html><body><form action="/reservas/"><input type="date" name="rtb-date"><select name="rtb-time"></select>
<input name="rtb-party"><input name="rtb-name"><input type="email" name="rtb-email"></form></body></html>"""
OPENTABLE_SITE = """<html><body><a href="https://www.opentable.es/r/la-contra-madrid?corrid=abc">Reservar</a>
<a href="tel:+34915001122">Tel</a></body></html>"""
PLATFORM_SITE = """<html><body><iframe src="https://widget.thefork.com/abc"></iframe><a href="https://www.opentable.es/r/x">Reserva</a></body></html>"""


def run(c):
    return asyncio.run(c)


class R:
    def __init__(self, status, body=None, text="", headers=None):
        self.status_code, self._body, self.text, self.headers = status, body, text, headers or {}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Web:
    """Pages by URL, robots by host, Places, Resend and Bland — every request recorded."""

    def __init__(self, pages=None, robots=None, places=None):
        self.pages = pages or {}
        self.robots = robots or {}
        self.places = places
        self.resend_send = R(200, {"id": "re_msg_1"})
        self.resend_received = {}
        self.bland = None   # None: a fresh call id per call, as Bland gives
        self.requests = []

    async def __call__(self, method, url, headers=None, json=None):
        self.requests.append((method, url, json))
        if url.startswith(V.PLACES_URL):
            return self.places if isinstance(self.places, R) else R(200, self.places or {})
        if url == E.RESEND_SEND_URL:
            if isinstance(self.resend_send, Exception):
                raise self.resend_send
            return self.resend_send
        if url.startswith("https://api.resend.com/emails/receiving/"):
            pid = url.rsplit("/", 1)[1]
            return R(200, self.resend_received[pid]) if pid in self.resend_received else R(404, {"message": "not found"})
        if url.startswith("https://api.bland.ai"):
            self.bland_n = getattr(self, "bland_n", 0) + 1
            return R(200, {"status": "success", "call_id": f"bland-{self.bland_n}"}) if self.bland is None else self.bland
        u = urlsplit(url)
        if u.path == "/robots.txt":
            return R(200, text=self.robots[u.hostname]) if u.hostname in self.robots else R(404, text="")
        if url in self.pages:
            return self.pages[url]
        return R(404, text="")

    def fetched(self):
        return [u for m, u, _ in self.requests if m == "GET"]


PUBLIC = lambda host: ["93.184.216.34"]


# ── 1 · what a page publishes ───────────────────────────────────────────────────────────────

class Reading(unittest.TestCase):
    def test_every_published_contact_is_a_fact_with_its_source(self):
        facts = V.facts_from_html(LA_CONTRA_SITE, "https://www.lacontra.test/", "ES", NOW.isoformat())
        got = sorted((f.kind, f.value) for f in facts)
        self.assertEqual(got, [("email", "hola@lacontra.test"), ("email", "info@lacontra.test"), ("email", "reservas@lacontra.test"),
                               ("phone", "+34915001122"), ("whatsapp", "+34600111222")])
        for f in facts:
            self.assertEqual((f.source_kind, f.source_url, f.source_label), ("site", "https://www.lacontra.test/", "their website, lacontra.test"))
            self.assertEqual(len(f.sha256), 64)
            self.assertTrue(f.snippet)

    def test_a_booking_form_and_a_platform_are_recognised_but_a_platform_is_never_fetched(self):
        self.assertEqual([f.kind for f in V.facts_from_html(PSI_LIKE, "https://www.restaurante-psi.com/", "PT", "t")], ["booking_form"])
        facts = V.facts_from_html(PLATFORM_SITE, "https://v.test/", "ES", "t")
        self.assertEqual(sorted({f.value for f in facts if f.kind == "platform"}), ["OpenTable", "TheFork"])
        web = Web()
        facts, sources = run(V.read_site(web, "https://www.thefork.es/restaurante/x", "ES", NOW, PUBLIC))
        self.assertEqual(web.requests, [])
        self.assertEqual((facts[0].kind, facts[0].value), ("platform", "TheFork"))

    def test_national_numbers_need_the_country_and_are_never_guessed(self):
        self.assertEqual(V.to_e164("915 00 11 22", "ES"), "+34915001122")
        self.assertEqual(V.to_e164("01 42 00 00 00", "FR"), "+33142000000")
        self.assertEqual(V.to_e164("06 1234 5678", "IT"), "+390612345678")
        self.assertEqual(V.to_e164("0034 915 001 122", None), "+34915001122")
        self.assertIsNone(V.to_e164("915 00 11 22", None))
        self.assertIsNone(V.to_e164("12", "ES"))

    def test_robots_first_and_only_public_hosts(self):
        web = Web(pages={"https://www.lacontra.test/": R(200, text=LA_CONTRA_SITE)},
                  robots={"www.lacontra.test": "User-agent: *\nDisallow: /"})
        facts, sources = run(V.read_site(web, "https://www.lacontra.test/", "ES", NOW, PUBLIC))
        self.assertEqual(facts, [])
        self.assertIn("robots.txt does not allow it", sources[0]["result"])
        self.assertNotIn("https://www.lacontra.test/", web.fetched())
        with self.assertRaises(V.ReadRefused) as e:
            V.public_url("http://intranet.test/", lambda h: ["10.0.0.5"])
        self.assertEqual(e.exception.rule, "host_not_public")
        for bad in ("file:///etc/passwd", "https://user:pw@x.test/", "https://x.test:8443/"):
            with self.assertRaises(V.ReadRefused):
                V.public_url(bad, PUBLIC)

    def test_a_redirect_to_a_private_host_is_refused_mid_flight(self):
        web = Web(pages={"https://www.lacontra.test/": R(302, headers={"location": "http://internal.test/"})})
        resolve = lambda h: ["10.1.2.3"] if h == "internal.test" else ["93.184.216.34"]
        facts, sources = run(V.read_site(web, "https://www.lacontra.test/", "ES", NOW, resolve))
        self.assertEqual(facts, [])
        self.assertTrue(any("non-public" in s["result"] for s in sources))

    def test_the_contact_page_is_followed_on_the_same_host_only(self):
        web = Web(pages={"https://www.lacontra.test/": R(200, text='<a href="/contacto">Contacto</a><a href="https://other.test/contact">x</a>'),
                         "https://www.lacontra.test/contacto": R(200, text='<a href="tel:+34915001122">Tel</a>')})
        facts, _ = run(V.read_site(web, "https://www.lacontra.test/", "ES", NOW, PUBLIC))
        self.assertEqual([(f.kind, f.value, f.source_url) for f in facts], [("phone", "+34915001122", "https://www.lacontra.test/contacto")])
        self.assertNotIn("https://other.test/contact", web.fetched())

    def test_la_contra_with_no_website_is_read_from_its_google_listing(self):
        places = {"places": [{"id": "ChIJ-la-contra", "displayName": {"text": "La Contra"}, "formattedAddress": "Calle de la Contra 1, Madrid",
                              "internationalPhoneNumber": "+34 915 00 11 22",
                              "regularOpeningHours": {"weekdayDescriptions": ["Monday: Closed", "Tuesday: 1:00 – 4:00 PM, 8:00 – 11:30 PM"],
                                                      "periods": [{"open": {"day": 2, "hour": 13, "minute": 0}}]},
                              "addressComponents": [{"shortText": "ES", "types": ["country", "political"]}]}]}
        web = Web(places=places)
        with mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "places-test"}):
            read = run(V.read_venue(web, name="La Contra", city="Madrid", country=None, website=None, now=NOW, resolve=PUBLIC))
        self.assertEqual(read.country, "ES")
        label = "their Google listing (La Contra, Calle de la Contra 1, Madrid)"
        self.assertEqual([(f.kind, f.value, f.source_label) for f in read.facts],
                         [("phone", "+34915001122", label), ("address", "Calle de la Contra 1, Madrid", label),
                          ("hours", "Monday: Closed · Tuesday: 1:00 – 4:00 PM, 8:00 – 11:30 PM", label)])
        for f in read.facts:
            self.assertEqual((f.source_kind, f.source_url, len(f.sha256)), ("places", "https://www.google.com/maps/place/?q=place_id:ChIJ-la-contra", 64))
        self.assertIn("regularOpeningHours", V.PLACES_FIELDS)
        self.assertEqual(read.listing, {"name": "La Contra", "address": "Calle de la Contra 1, Madrid", "place_id": "ChIJ-la-contra"})
        method, url, body = web.requests[0]
        self.assertEqual((method, url, body["textQuery"]), ("POST", V.PLACES_URL, "La Contra, Madrid"))

    def test_without_a_places_key_it_says_so(self):
        read = run(V.read_venue(Web(), name="La Contra", city="Madrid", country="ES", website=None, now=NOW, resolve=PUBLIC))
        self.assertEqual(read.facts, [])
        self.assertIn("GOOGLE_PLACES_API_KEY is not set", read.sources[0]["result"])


# ── 2 · the chooser ─────────────────────────────────────────────────────────────────────────

def a_read(*kinds, country="ES", name="La Contra"):
    vals = {"phone": "+34915001122", "email": "reservas@lacontra.test", "whatsapp": "+34600111222", "platform": "OpenTable",
            "booking_form": "https://lacontra.test/reserva"}
    return {"name": name, "country": country, "facts": [{"kind": k, "value": vals[k], "source_label": "their website, lacontra.test",
                                                           "source_url": "https://lacontra.test/"} for k in kinds]}


class Chooser(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_the_founders_sentence(self):
        self.assertEqual(L.choose(a_read("phone", "email"))["say"],
                         "They have no booking form. I'll call them — or I can email and we wait. Which?")

    def test_one_rung_asks_shall_i(self):
        self.assertEqual(L.choose(a_read("phone"))["say"], "They have no booking form. I'll call them. Shall I?")

    def test_a_rung_that_cannot_run_is_never_offered_and_says_why(self):
        with mock.patch.dict(os.environ, {"SASHA_EMAILS_ENABLED": "0"}):
            c = L.choose(a_read("phone", "email"))
        self.assertEqual(c["say"], "They have no booking form. I'll call them. Shall I?")
        email = [r for r in c["rungs"] if r["rung"] == "email"][0]
        self.assertFalse(email["available"])
        self.assertIn("SASHA_EMAILS_ENABLED", email["why_not"])

    def test_a_platform_and_an_unmapped_form_are_facts_not_rungs(self):
        self.assertTrue(L.choose(a_read("platform", "phone"))["say"].startswith("They book through OpenTable, which I can't use yet. I'll call them."))
        self.assertTrue(L.choose(a_read("booking_form", "email"))["say"].startswith("They have a booking form, but I can't fill it yet."))

    def test_nothing_reachable_says_what_was_found_and_why(self):
        with mock.patch.dict(os.environ, {"SASHA_CALLS_ENABLED": "0"}):
            s = L.choose(a_read("phone"))["say"]
        self.assertIn("I can't reach them myself", s)
        self.assertIn("SASHA_CALLS_ENABLED", s)
        self.assertIn("they publish no phone, email or WhatsApp", L.choose(a_read())["say"])

    def test_the_email_rung_reads_its_own_key_never_payments(self):
        with mock.patch.dict(os.environ, {"SASHA_RESEND_API_KEY": "", "RESEND_API_KEY": "re_payments_key"}):
            why = L.emails_ready()
        self.assertIn("SASHA_RESEND_API_KEY", why)
        with mock.patch.dict(os.environ, {"SASHA_RESEND_API_KEY": "re_sasha", "RESEND_API_KEY": ""}):
            self.assertIsNone(L.emails_ready())
        self.assertEqual(E.KEY_VAR, "SASHA_RESEND_API_KEY")

    def test_a_country_whose_language_she_cannot_speak_is_not_a_phone_rung(self):
        phone = L.choose(a_read("phone", country="VN"))["rungs"][0]
        self.assertFalse(phone["available"])
        self.assertIn("vi", phone["why_not"])


# ── 3 · the email: exact words, hashed, Resend's answer READ, replies by address ─────────────

class Email(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def p(self):
        return E.EmailParticulars(on=NOW.date() + timedelta(days=3), at=datetime(2026, 1, 1, 20, 0).time(), party=4,
                                  name="Anna Johnson", guest_email="anna@example.test")

    def test_the_guest_is_bccd_never_ccd_and_the_read_back_says_so(self):
        """S-52 (supersedes S-32): the venue never sees the guest's address."""
        e = E.compose("es", "La Contra", "reservas@lacontra.test", self.p(), "11111111-2222-4333-8444-555555555555")
        self.assertNotIn("cc", e)
        self.assertNotIn("anna@example.test", e["text"])
        self.assertEqual((e["to"], e["bcc"], e["reply_to"]),
                         ("reservas@lacontra.test", "anna@example.test", "act-11111111-2222-4333-8444-555555555555@in.kanoe.test"))
        self.assertTrue(e["text"].startswith("Hola, soy Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL"))
        self.assertIn("la familia Johnson", e["text"])
        lines = E.read_back(e, "La Contra", "their website, lacontra.test")
        self.assertIn("they won't see your address", lines[1])
        self.assertEqual(lines[4], e["text"])

    def test_the_hash_moves_with_any_byte(self):
        e = E.compose("en", "La Contra", "r@l.test", self.p(), "11111111-2222-4333-8444-555555555555")
        self.assertNotEqual(E.email_sha256(e), E.email_sha256({**e, "text": e["text"] + " "}))

    def test_sent_only_on_200_with_an_id(self):
        e = E.compose("en", "La Contra", "r@l.test", self.p(), "11111111-2222-4333-8444-555555555555")
        for answer, sent in [(R(200, {"id": "re_1"}), True), (R(200, {}), False), (R(422, {"message": "Invalid `to` field"}), False),
                             (R(403, {"message": "domain not verified"}), False), (R(500, ValueError()), False), (ConnectionError("x"), False)]:
            web = Web()
            web.resend_send = answer
            s = run(E.send(web, e))
            self.assertEqual(s.sent, sent, answer)
            if not sent:
                self.assertTrue(s.why)
        web = Web()
        run(E.send(web, e))
        _, _, payload = web.requests[0]
        self.assertEqual((payload["to"], payload["bcc"], payload["reply_to"]), (["r@l.test"], ["anna@example.test"], e["reply_to"]))
        self.assertNotIn("cc", payload)

    def test_svix_signatures(self):
        body = b'{"type":"email.received"}'
        ts = str(int(time.time()))
        key = base64.b64decode(SECRET.removeprefix("whsec_"))
        sig = base64.b64encode(hmac.new(key, f"msg_1.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
        h = {"svix-id": "msg_1", "svix-timestamp": ts, "svix-signature": f"v1,bogus v1,{sig}"}
        self.assertTrue(E.verify_svix(SECRET, h, body))
        self.assertFalse(E.verify_svix(SECRET, h, body + b" "))
        self.assertFalse(E.verify_svix(SECRET, {**h, "svix-timestamp": str(int(ts) - 600)}, body))
        self.assertFalse(E.verify_svix("", h, body))

    def test_only_our_inbound_domain_matches(self):
        i = "11111111-2222-4333-8444-555555555555"
        self.assertEqual(E.act_id_of([f"Sasha <act-{i}@in.kanoe.test>"]), i)
        self.assertIsNone(E.act_id_of([f"act-{i}@elsewhere.test"]))
        self.assertIsNone(E.act_id_of(["info@in.kanoe.test"]))


# ── 3b · the slot link, and the one storage error ─────────────────────────────────────────────

class SlotLinkBuilder(unittest.TestCase):
    READ = {"name": "La Contra", "facts": [{"kind": "platform", "value": "OpenTable", "source_label": "their website, lacontra.test",
                                             "detail": {"link": "https://www.opentable.es/r/la-contra-madrid?corrid=abc"}}]}
    ON, AT = datetime(2026, 10, 8).date(), datetime(2026, 1, 1, 20, 0).time()

    def test_no_recipe_means_their_page_as_linked_and_no_slot_claim(self):
        l = SL.build(self.READ, self.ON, self.AT, 4, recipes={})
        self.assertEqual((l.url, l.slot_filled), ("https://www.opentable.es/r/la-contra-madrid?corrid=abc", False))

    def test_an_unverified_recipe_fills_nothing(self):
        r = SL.Recipe("OpenTable", "d", "t", "p", "%Y-%m-%d", "%H:%M", observed="test", verified=None)
        self.assertFalse(SL.build(self.READ, self.ON, self.AT, 4, recipes={"OpenTable": r}).slot_filled)

    def test_a_verified_recipe_fills_the_slot_and_keeps_the_rest(self):
        r = SL.Recipe("OpenTable", "d", "t", "p", "%Y-%m-%d", "%H:%M", observed="test", verified="test")
        l = SL.build(self.READ, self.ON, self.AT, 4, recipes={"OpenTable": r})
        self.assertEqual((l.url, l.slot_filled), ("https://www.opentable.es/r/la-contra-madrid?corrid=abc&d=2026-10-08&t=20%3A00&p=4", True))

    def test_a_link_off_the_platforms_own_host_is_not_its_page(self):
        read = {"facts": [{"kind": "platform", "value": "OpenTable", "source_label": "x", "detail": {"link": "https://evil.test/opentable"}}]}
        with self.assertRaises(SL.LinkRefused) as e:
            SL.build(read, self.ON, self.AT, 4, recipes={})
        self.assertEqual(e.exception.rule, "platform_page_not_linked")

    def test_the_recipes_are_empty_until_the_founder_captures_and_verifies_them(self):
        self.assertEqual(SL.RECIPES, {})


class StorageMessage(unittest.TestCase):
    def test_the_rule_is_said_once_and_the_hint_names_the_right_block(self):
        e = StorageUnavailable("storage_not_provisioned", 'relation "booking_links" does not exist — run backend/booking_signer/sql/001_booking_storage.sql')
        e = e.rehint("003_phone_calls.sql").rehint("004_ladder.sql").rehint("005_slot_links.sql")
        self.assertEqual(e.detail, 'relation "booking_links" does not exist — run backend/booking_signer/sql/005_slot_links.sql')
        self.assertEqual(str(e).count("storage_not_provisioned"), 1)


# ── 4 · the routes ──────────────────────────────────────────────────────────────────────────

def signed(event: dict):
    body = json.dumps(event).encode()
    ts = str(int(time.time()))
    key = base64.b64decode(SECRET.removeprefix("whsec_"))
    sig = base64.b64encode(hmac.new(key, f"msg_x.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return body, {"svix-id": "msg_x", "svix-timestamp": ts, "svix-signature": f"v1,{sig}", "content-type": "application/json"}


class LadderRoutes:
    def make_stores(self):
        raise NotImplementedError

    def trip_status_of_email(self, email_id):
        raise NotImplementedError

    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.calls, self.ladder = self.make_stores()
        self.web = Web(pages={"https://www.lacontra.test/": R(200, text=LA_CONTRA_SITE)})
        self.now = NOW
        self.saved = (call_routes.CALL_STORE, call_routes.HTTP, call_routes.NOW, ladder_routes.LADDER_STORE,
                      ladder_routes.HTTP, ladder_routes.NOW, ladder_routes.RESOLVE)
        call_routes.CALL_STORE, call_routes.HTTP, call_routes.NOW = self.calls, self.web, (lambda: self.now)
        ladder_routes.LADDER_STORE, ladder_routes.HTTP, ladder_routes.NOW, ladder_routes.RESOLVE = self.ladder, self.web, (lambda: self.now), PUBLIC
        self.saved_optins, self.optins = O.OPTIN_STORE, O.MemoryOptinStore()
        O.OPTIN_STORE = self.optins
        self.saved_stop = S.STOP_STORE
        S.STOP_STORE = S.MemoryStopStore(self.optins, self.ladder, self.calls) if isinstance(self.ladder, MemoryLadderStore) else None
        app = FastAPI()
        app.include_router(routes.router)
        self.c = TestClient(app, headers={"x-sasha-booking-key": "test-booking-key"})
        self.c.__enter__()

    def tearDown(self):
        if getattr(self, "base", None) is not None:
            self.c.portal.call(self.base.close)
        self.c.__exit__(None, None, None)
        (call_routes.CALL_STORE, call_routes.HTTP, call_routes.NOW, ladder_routes.LADDER_STORE,
         ladder_routes.HTTP, ladder_routes.NOW, ladder_routes.RESOLVE) = self.saved
        O.OPTIN_STORE = self.saved_optins
        S.STOP_STORE = self.saved_stop
        self.env.stop()

    def read(self):
        r = self.c.post("/api/booking/venues/read", json={"name": "La Contra", "city": "Madrid", "country": "ES", "website": "https://www.lacontra.test/"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    BOOKING = {"date": "2026-10-08", "time": "20:00", "party": 4, "name": "Anna Johnson"}

    def test_a_read_returns_facts_rungs_and_her_sentence(self):
        v = self.read()
        self.assertEqual(v["say"], "They have no booking form. I'll call them — or I can email and we wait — or you can WhatsApp them — I'll write the message. Which?")
        self.assertEqual({f["kind"] for f in v["facts"]}, {"phone", "email", "whatsapp"})
        self.assertEqual(self.c.get(f"/api/booking/venues/read/{v['read_id']}").json()["say"], v["say"])

    def test_contact_details_are_never_taken_from_the_request(self):
        r = self.c.post("/api/booking/venues/read", json={"name": "X", "city": "Madrid", "phone": "+15550100"})
        self.assertEqual(r.json()["rule"], "contact_from_request")

    def test_the_call_dials_the_number_that_was_read_and_says_where_it_came_from(self):
        v = self.read()
        prep = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING})
        self.assertEqual(prep.status_code, 200, prep.text)
        lines = prep.json()["read_back"]["lines"]
        self.assertEqual(lines[0], "I'll phone La Contra, +34915001122 — the number on their website, lacontra.test.")
        self.assertIn("Hola, soy Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL", lines[1])
        r = self.c.post(f"/api/booking/calls/{prep.json()['call_id']}/place",
                        json={"read_back_sha256": prep.json()["read_back"]["sha256"], "approval": {"how": "button"}})
        self.assertEqual(r.json()["status"], "placed", r.text)
        bland = [b for m, u, b in self.web.requests if u.startswith("https://api.bland.ai")]
        self.assertEqual(bland[0]["phone_number"], "+34915001122")
        self.assertEqual(bland[0]["language"], "es")
        self.assertNotIn("from", bland[0])   # no Sasha number yet: Bland's own caller ID

    def test_once_sashas_number_exists_it_is_the_caller_id_but_never_given_out(self):
        with mock.patch.dict(os.environ, {"SASHA_PHONE_NUMBER": "+44 7700 900123"}):
            v = self.read()
            prep = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING}).json()
            self.c.post(f"/api/booking/calls/{prep['call_id']}/place", json={"read_back_sha256": prep["read_back"]["sha256"], "approval": {"how": "button"}})
        bland = [b for m, u, b in self.web.requests if u.startswith("https://api.bland.ai")][0]
        self.assertEqual(bland["from"], "+447700900123")
        self.assertNotIn("7700900123", bland["task"])

    def test_the_three_a_day_limit_holds_for_read_numbers(self):
        v = self.read()
        for i in range(4):
            prep = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING}).json()
            r = self.c.post(f"/api/booking/calls/{prep['call_id']}/place", json={"read_back_sha256": prep["read_back"]["sha256"], "approval": {"how": "button"}})
        self.assertEqual((r.status_code, r.json()["rule"]), (429, "daily_call_limit"))
        self.assertEqual(len([1 for m, u, b in self.web.requests if u.startswith("https://api.bland.ai")]), 3)

    # ── S-54 · the refusal check: a venue that said stop is never contacted by Sasha again ──────────────────

    def venue_id(self, v):
        return O.venue_id_of(self.c.portal.call(self.ladder.get_read, DEMO_ACCOUNT_ID, v["read_id"])["read"])

    def optin(self, vid, status, channel="whatsapp", scope="+34600111222", at=None):
        at = at or self.now
        run(self.optins.add({"venue_id": vid, "channel": channel, "scope": scope, "status": status, "recorded_at": at,
                             "withdrawn_at": at if status == "withdrawn" else None,
                             "withdrawn_how": "STOP" if status == "withdrawn" else None}))

    def sent(self):
        return [u for m, u, b in self.web.requests if u.startswith("https://api.bland.ai") or u == E.RESEND_SEND_URL]

    def test_a_venue_that_withdrew_on_any_channel_is_refused_a_call_and_an_email(self):
        v = self.read()
        self.optin(self.venue_id(v), "active", at=self.now - timedelta(days=9))
        self.optin(self.venue_id(v), "withdrawn", at=self.now - timedelta(days=2))   # STOP on WhatsApp ends phone and email too
        call = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING})
        mail = self.c.post("/api/booking/emails", json={"read_id": v["read_id"], **self.BOOKING, "email": "anna@example.test"})
        for r in (call, mail):
            self.assertEqual((r.status_code, r.json()["rule"]), (403, "venue_opted_out"), r.text)
            self.assertIn("you can still contact them yourself", r.json()["message"])
        self.assertEqual(self.sent(), [])

    def test_a_withdrawal_between_the_read_back_and_the_yes_stops_the_send(self):
        v = self.read()
        call = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING}).json()
        mail = self.c.post("/api/booking/emails", json={"read_id": v["read_id"], **self.BOOKING, "email": "anna@example.test"}).json()
        self.optin(self.venue_id(v), "withdrawn", channel="email_confirm", scope="reservas@lacontra.test")
        yes = {"approval": {"how": "button"}}
        r1 = self.c.post(f"/api/booking/calls/{call['call_id']}/place", json={"read_back_sha256": call["read_back"]["sha256"], **yes})
        r2 = self.c.post(f"/api/booking/emails/{mail['email_id']}/send", json={"read_back_sha256": mail["read_back"]["sha256"], **yes})
        self.assertEqual([r1.json()["rule"], r2.json()["rule"]], ["venue_opted_out", "venue_opted_out"])
        self.assertEqual(self.sent(), [])

    def test_opting_back_in_is_a_new_row_and_lifts_the_refusal(self):
        v = self.read()
        self.optin(self.venue_id(v), "withdrawn", at=self.now - timedelta(days=30))
        self.optin(self.venue_id(v), "active", at=self.now - timedelta(days=1))
        self.assertEqual(self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING}).status_code, 200)

    def test_another_venues_withdrawal_changes_nothing(self):
        v = self.read()
        self.optin("host:elsewhere.test", "withdrawn")
        self.assertEqual(self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING}).status_code, 200)

    def test_if_the_opt_in_record_cannot_be_read_nothing_is_sent(self):
        v = self.read()

        async def down(venue_id):
            raise StorageUnavailable("storage_unreachable", "the database did not answer")
        self.optins.rows_for = down
        r = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING})
        self.assertEqual((r.status_code, r.json()["rule"]), (503, "storage_unreachable"))
        self.assertIn("could not be checked, so nothing was sent", r.json()["message"])

    def test_the_email_rung_end_to_end(self):
        v = self.read()
        prep = self.c.post("/api/booking/emails", json={"read_id": v["read_id"], **self.BOOKING, "email": "anna@example.test"})
        self.assertEqual(prep.status_code, 200, prep.text)
        p = prep.json()
        self.assertIn("reservas@lacontra.test", p["read_back"]["lines"][0])   # the JSON-LD address, read first
        bad = self.c.post(f"/api/booking/emails/{p['email_id']}/send", json={"read_back_sha256": "0" * 64, "approval": {"how": "button"}})
        self.assertEqual(bad.json()["rule"], "approval_void")
        r = self.c.post(f"/api/booking/emails/{p['email_id']}/send", json={"read_back_sha256": p["read_back"]["sha256"], "approval": {"how": "button"}})
        self.assertEqual(r.json()["status"], "sent", r.text)
        self.assertIn("accepted it", r.json()["say"])
        again = self.c.post(f"/api/booking/emails/{p['email_id']}/send", json={"read_back_sha256": p["read_back"]["sha256"], "approval": {"how": "button"}})
        self.assertEqual(again.json()["rule"], "email_already_sent")
        self.assertEqual(len([1 for m, u, b in self.web.requests if u == E.RESEND_SEND_URL]), 1)
        self.assertEqual(self.trip_status_of_email(p["email_id"]), "attempting")

        # the venue replies to act-{id}@in.kanoe.test
        self.web.resend_received["rcv_1"] = {"text": "Sí, perfecto: mesa para 4 el jueves a las 20:00."}
        body, h = signed({"type": "email.received", "data": {"email_id": "rcv_1", "from": "reservas@lacontra.test",
                                                            "to": [f"act-{p['email_id']}@in.kanoe.test"], "subject": "Re: Solicitud"}})
        self.assertEqual(self.c.post("/api/booking/email/inbound", content=body, headers=h).json(), {"ok": True, "matched": True})
        self.c.post("/api/booking/email/inbound", content=body, headers=h)   # a redelivery is recognised
        g = self.c.get(f"/api/booking/emails/{p['email_id']}").json()
        self.assertEqual([x["text"] for x in g["replies"]], ["Sí, perfecto: mesa para 4 el jueves a las 20:00."])
        self.assertEqual(g["say"], "They replied — here are their words.")
        self.assertEqual(self.trip_status_of_email(p["email_id"]), "attempting")   # a reply never moves the status itself

    def test_resend_refusing_is_not_sent_with_its_words(self):
        self.web.resend_send = R(403, {"message": "The mail.kanoe.test domain is not verified"})
        v = self.read()
        p = self.c.post("/api/booking/emails", json={"read_id": v["read_id"], **self.BOOKING, "email": "anna@example.test"}).json()
        r = self.c.post(f"/api/booking/emails/{p['email_id']}/send", json={"read_back_sha256": p["read_back"]["sha256"], "approval": {"how": "button"}}).json()
        self.assertEqual(r["status"], "not_sent")
        self.assertIn("domain is not verified", r["say"])
        self.assertEqual(self.c.get(f"/api/booking/emails/{p['email_id']}").json()["status"], "not_sent")
        self.assertEqual(self.trip_status_of_email(p["email_id"]), "pending")

    def test_email_off_means_no_read_back(self):
        v = self.read()
        with mock.patch.dict(os.environ, {"SASHA_INBOUND_DOMAIN": ""}):
            r = self.c.post("/api/booking/emails", json={"read_id": v["read_id"], **self.BOOKING, "email": "anna@example.test"})
        self.assertEqual(r.json()["rule"], "emails_disabled")
        self.assertIn("SASHA_INBOUND_DOMAIN", r.json()["message"])

    def test_the_address_is_never_taken_from_the_request(self):
        v = self.read()
        r = self.c.post("/api/booking/emails", json={"read_id": v["read_id"], **self.BOOKING, "email": "anna@example.test", "to": "x@y.test"})
        self.assertEqual(r.json()["rule"], "recipient_from_request")

    def test_an_unsigned_or_unmatched_inbound_is_refused_or_quarantined(self):
        body, h = signed({"type": "email.received", "data": {"email_id": "rcv_9", "to": ["someone@in.kanoe.test"], "from": "x@y.test"}})
        self.assertEqual(self.c.post("/api/booking/email/inbound", content=body, headers={**h, "svix-signature": "v1,AAAA"}).status_code, 401)
        self.assertEqual(self.c.post("/api/booking/email/inbound", content=body, headers=h).json(), {"ok": True, "matched": False})


class SlotLinkRoutes:
    """S-37, mixed into the same two stores."""

    def link_read(self):
        self.web.pages["https://www.lacontra.test/"] = R(200, text=OPENTABLE_SITE)
        return self.read()

    def test_the_chooser_offers_the_platform_page_first(self):
        v = self.link_read()
        self.assertEqual(v["say"], "They book through OpenTable. I'll send you their OpenTable page to book it yourself — or I'll call them. Which?")

    def test_the_link_is_the_page_read_on_their_site_and_says_who_books(self):
        v = self.link_read()
        r = self.c.post("/api/booking/links", json={"read_id": v["read_id"], **self.BOOKING})
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        self.assertEqual((p["platform"], p["slot_filled"]), ("OpenTable", False))
        lines = p["read_back"]["lines"]
        self.assertIn("I can't book there for you", lines[0])
        self.assertIn("Pick Thursday 8 October at 8 pm, for 4, there — it's booked in your name", lines[1])
        self.assertIn("Nothing is reserved until you press their button.", lines[2])
        self.assertIn(f"act-{p['link_id']}@in.kanoe.test", lines[3])
        self.assertFalse(any("opentable" in u for m, u, b in self.web.requests))   # the platform was never contacted
        self.assertEqual(self.c.post("/api/booking/links", json={"read_id": v["read_id"], **self.BOOKING, "url": "https://x"}).json()["rule"],
                         "url_from_request")

    def test_opened_then_booked_then_a_forwarded_confirmation(self):
        v = self.link_read()
        p = self.c.post("/api/booking/links", json={"read_id": v["read_id"], **self.BOOKING}).json()
        self.assertEqual(self.c.post(f"/api/booking/links/{p['link_id']}/opened", json={"read_back_sha256": "0" * 64}).json()["rule"], "approval_void")
        o = self.c.post(f"/api/booking/links/{p['link_id']}/opened", json={"read_back_sha256": p["read_back"]["sha256"]}).json()
        self.assertEqual((o["status"], o["url"]), ("link_sent", "https://www.opentable.es/r/la-contra-madrid?corrid=abc"))
        self.assertEqual(self.trip_status_of_link(p["link_id"]), "link_sent")
        b = self.c.post(f"/api/booking/links/{p['link_id']}/booked", json={"how": "button"}).json()
        self.assertEqual(b["status"], "guest_booked")
        self.assertEqual(self.trip_status_of_link(p["link_id"]), "guest_booked")

        # a forward of the WRONG email is kept, never counted
        self.web.resend_received["fwd_0"] = {"text": "Your parcel has shipped."}
        body, h = signed({"type": "email.received", "data": {"email_id": "fwd_0", "from": "anna@example.test",
                                                            "to": [f"act-{p['link_id']}@in.kanoe.test"], "subject": "Fwd: parcel"}})
        self.assertEqual(self.c.post("/api/booking/email/inbound", content=body, headers=h).json()["counted"], False)
        self.assertEqual(self.trip_status_of_link(p["link_id"]), "guest_booked")

        self.web.resend_received["fwd_1"] = {"text": "OpenTable: your reservation at La Contra is confirmed. Thu 8 Oct, 20:00, 4 people. Conf #1234"}
        body, h = signed({"type": "email.received", "data": {"email_id": "fwd_1", "from": "anna@example.test",
                                                            "to": [f"act-{p['link_id']}@in.kanoe.test"], "subject": "Fwd: Reservation confirmed"}})
        self.assertEqual(self.c.post("/api/booking/email/inbound", content=body, headers=h).json()["counted"], True)
        self.c.post("/api/booking/email/inbound", content=body, headers=h)   # a redelivery is recognised
        g = self.c.get(f"/api/booking/links/{p['link_id']}").json()
        self.assertEqual(g["status"], "confirmed")
        self.assertEqual([c["counted"] for c in g["confirmations"]], [False, True])
        self.assertEqual(self.trip_status_of_link(p["link_id"]), "confirmed")

    def test_a_platform_not_linked_from_their_site_gets_no_link(self):
        self.web.pages["https://www.lacontra.test/"] = R(200, text='<iframe src="https://widget.thefork.com/abc"></iframe>')
        v = self.read()
        r = self.c.post("/api/booking/links", json={"read_id": v["read_id"], **self.BOOKING})
        self.assertEqual(r.json()["rule"], "platform_page_not_linked")


class OnMemory(SlotLinkRoutes, LadderRoutes, unittest.TestCase):
    def make_stores(self):
        return MemoryCallStore(), MemoryLadderStore()

    def trip_status_of_email(self, email_id):
        return self.ladder.trip_items[self.ladder.emails[email_id]["trip_item_id"]]["status"]

    def trip_status_of_link(self, link_id):
        return self.ladder.trip_items[self.ladder.links[link_id]["trip_item_id"]]["status"]

    # ── S-56 · a venue that replies STOP ────────────────────────────────────────────────────────────

    def sent_email(self):
        v = self.read()
        p = self.c.post("/api/booking/emails", json={"read_id": v["read_id"], **self.BOOKING, "email": "anna@example.test"}).json()
        self.c.post(f"/api/booking/emails/{p['email_id']}/send", json={"read_back_sha256": p["read_back"]["sha256"], "approval": {"how": "button"}})
        return v, p

    def reply(self, p, pid, text, to=None):
        self.web.resend_received[pid] = {"text": text}
        body, h = signed({"type": "email.received", "data": {"email_id": pid, "from": "La Contra <Reservas@lacontra.test>",
                                                            "to": [to or f"act-{p['email_id']}@in.kanoe.test"], "subject": "Re: Solicitud"}})
        return self.c.post("/api/booking/email/inbound", content=body, headers=h)

    def acks(self):
        return [b for m, u, b in self.web.requests if u == E.RESEND_SEND_URL and b["to"] == ["reservas@lacontra.test"]
                and b["subject"].startswith("Re:")]   # not Sasha's own booking email to them

    def test_a_stop_reply_is_recorded_verbatim_ends_every_channel_acks_once_and_tells_the_guest(self):
        v, p = self.sent_email()
        r = self.reply(p, "rcv_stop", "PARA\n\nEl mar, 29 sept 2026, Sasha <sasha@kanoe.test> escribió:\n> Hola, soy Sasha…")
        self.assertEqual(r.json(), {"ok": True, "matched": True})
        row = self.optins.rows[-1]
        self.assertEqual((row["status"], row["channel"], row["scope"], row["withdrawn_how"]),
                         ("withdrawn", "email", "reservas@lacontra.test", "said stop by email"))
        self.assertEqual(row["withdrawn_evidence"]["verbatim"], "PARA")
        self.assertEqual(row["withdrawn_evidence"]["provider_id"], "rcv_stop")
        # one acknowledgement, in the venue's language, as a reply
        a = self.acks()
        self.assertEqual(len(a), 1)
        self.assertTrue(a[0]["text"].startswith("Hecho: Sasha no volverá a contactaros."))
        self.assertEqual(a[0]["subject"], "Re: Solicitud")
        # the guest's pending request says so
        self.assertEqual(self.trip_status_of_email(p["email_id"]), "escalated")
        # every channel ends: a call to them is refused now
        call = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **self.BOOKING})
        self.assertEqual((call.status_code, call.json()["rule"]), (403, "venue_opted_out"))
        # a second stop is recorded but gets no second reply: then nothing more
        self.reply(p, "rcv_stop2", "Unsubscribe")
        self.assertEqual(len(self.acks()), 1)

    def test_an_ordinary_reply_is_not_a_stop(self):
        v, p = self.sent_email()
        self.reply(p, "rcv_ok", "Sí, perfecto: mesa para 4 el jueves a las 20:00. Para cualquier cambio, llamadnos.")
        self.assertEqual((self.optins.rows, self.acks()), ([], []))
        self.assertEqual(self.trip_status_of_email(p["email_id"]), "attempting")

    def test_a_stop_quoted_from_below_the_reply_is_not_theirs(self):
        v, p = self.sent_email()
        self.reply(p, "rcv_q", "Gracias, os confirmamos mañana.\n\nOn Tue, 29 Sep 2026 Sasha wrote:\n> Reply STOP to stop.")
        self.assertEqual(self.optins.rows, [])

    def test_a_stop_sent_to_the_wrong_address_still_counts_from_a_venue_sasha_wrote_to(self):
        v, p = self.sent_email()
        r = self.reply(p, "rcv_x", "No nos escribáis más, gracias.", to="hello@in.kanoe.test")
        self.assertEqual(r.json(), {"ok": True, "matched": False})
        self.assertEqual(self.optins.rows[-1]["withdrawn_evidence"]["verbatim"], "No nos escribáis más, gracias.")

    def test_quarantine_is_kept(self):
        body, h = signed({"type": "email.received", "data": {"email_id": "rcv_q", "to": ["hello@in.kanoe.test"], "from": "x@y.test"}})
        self.c.post("/api/booking/email/inbound", content=body, headers=h)
        self.assertEqual([q["provider_id"] for q in self.ladder.quarantined], ["rcv_q"])


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(SlotLinkRoutes, LadderRoutes, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import asyncpg
        if "test" not in urlsplit(PG_URL).path.lstrip("/"):
            raise unittest.SkipTest("refusing a database whose name does not contain 'test'")

        async def fresh():
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute("drop schema if exists auth cascade; drop schema public cascade; create schema public;")
                await c.execute((HERE / "fixtures" / "model_a_live_2026-09-28.sql").read_text(encoding="utf-8"))
                for f in ("001_booking_storage.sql", "002_prepared_status.sql", "003_phone_calls.sql", "004_ladder.sql", "005_slot_links.sql"):
                    await c.execute((SQL_DIR / f).read_text(encoding="utf-8"))
            finally:
                await c.close()
        asyncio.run(fresh())

    def make_stores(self):
        async def wipe():
            import asyncpg
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute("delete from booking_link_confirmations; delete from booking_links; "
                                "delete from booking_email_replies; delete from booking_email_quarantine; delete from booking_emails; "
                                "delete from booking_attempts; delete from booking_calls; delete from venue_reads; delete from trip_items; delete from trips;")
            finally:
                await c.close()
        run(wipe())
        self.base = PostgresStore(PG_URL)
        return PostgresCallStore(self.base), PostgresLadderStore(self.base)

    def _q(self, sql, *a):
        async def q():
            import asyncpg
            c = await asyncpg.connect(PG_URL)
            try:
                return await c.fetch(sql, *a)
            finally:
                await c.close()
        return run(q())

    def trip_status_of_link(self, link_id):
        return self._q("select t.status from trip_items t join booking_links l on l.trip_item_id = t.id where l.link_id = $1::uuid", link_id)[0]["status"]

    def trip_status_of_email(self, email_id):
        return self._q("select t.status from trip_items t join booking_emails e on e.trip_item_id = t.id where e.email_id = $1::uuid", email_id)[0]["status"]

    def test_the_block_refuses_to_run_twice(self):
        import asyncpg

        async def again():
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute((SQL_DIR / "004_ladder.sql").read_text(encoding="utf-8"))
            finally:
                await c.close()
        with self.assertRaisesRegex(Exception, "STOP: the S-36 ladder tables already exist"):
            run(again())


if __name__ == "__main__":
    unittest.main()
