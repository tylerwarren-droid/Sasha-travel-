"""Sasha 89 · the form rung, submitting — proven on OUR test venue only: read the venue, read back every field, send it
once after the yes, keep their answer page word for word; stop at a CAPTCHA or a consent box; never a real venue
until the founder approves one. Offline: the test venue is this app's own route, reached through the test client.

    cd backend && python -m unittest tests.test_form_rung -v
"""
from __future__ import annotations

import os
import unittest
from unittest import mock
from urllib.parse import urlsplit

from booking_signer import form_rung as FR
from booking_signer.call_store import MemoryCallStore
from booking_signer.ladder_store import MemoryLadderStore
from tests.test_booking_ladder import LadderRoutes, R, Web

BASE = "https://venue.sasha.test"
GUEST = {"name": "Tyler Warren", "contact": {"email": "tyler@kanoe.test", "mobile_e164": "+34608445715"}}


def reservation(**kw):
    return {"schema": "reservation/1", "flow": "book", "who": GUEST, "where": {},
            "what": {"activity": "a table", "activity_venue_lang": "una mesa", "category": "restaurant"},
            "when": {"mode": "at", "at": "2026-10-10T21:00"}, "how_many": {"count": 2, "unit": "people"}, **kw}


class TestVenueWeb(Web):
    """The fake web, with the test venue's pages served by the app itself (so the page tested is the page served)."""
    client = None

    async def __call__(self, method, url, headers=None, json=None):
        if url.startswith(BASE + "/api/booking/test-venue/"):
            self.requests.append((method, url, json))
            r = self.client.get(urlsplit(url).path)
            return R(r.status_code, text=r.text)
        return await super().__call__(method, url, headers, json)


class FormRung(unittest.TestCase):   # LadderRoutes' set-up, not its tests
    def make_stores(self):
        return MemoryCallStore(), MemoryLadderStore()

    def setUp(self):
        self.base_env = mock.patch.dict(os.environ, {"SASHA_PUBLIC_BASE": BASE, "SASHA_FORM_HOSTS": "", "SASHA_FORMS_ENABLED": ""})
        self.base_env.start()
        LadderRoutes.setUp(self)
        # the venue is a SEPARATE web server (its own app), as a real venue is — not the app under test calling itself
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        venue_app = FastAPI()
        venue_app.include_router(FR.router, prefix="/api/booking")
        self.venue = TestClient(venue_app)
        web = TestVenueWeb(pages=self.web.pages)
        web.client = self.venue
        self.web.__class__, self.web.__dict__ = TestVenueWeb, {**web.__dict__}
        self.saved_fr = (FR.STORE, FR.FORM_POST)
        FR.STORE = FR.MemoryFormStore(self.calls)
        self.posts = []

        async def post(url, data, headers):
            self.posts.append((url, dict(data)))
            return self.venue.post(urlsplit(url).path, data=data)
        FR.FORM_POST = post
        FR.TEST_SUBMISSIONS.clear()

    def tearDown(self):
        FR.STORE, FR.FORM_POST = self.saved_fr
        LadderRoutes.tearDown(self)
        self.base_env.stop()

    def read(self, variant="plain"):
        r = self.c.post("/api/booking/venues/read", json={"name": "Sasha Test Venue", "city": "Madrid", "country": "ES",
                                                          "website": FR.test_venue_url(variant)})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_the_test_venue_is_read_and_its_form_rung_is_available(self):
        v = self.read()
        form = next(r for r in v["rungs"] if r["rung"] == "form")
        self.assertTrue(form["available"], form)

    def test_the_read_back_shows_every_field_and_the_yes_sends_it_once(self):
        v = self.read()
        prep = self.c.post("/api/booking/forms", json={"read_id": v["read_id"], "reservation": reservation()})
        self.assertEqual(prep.status_code, 200, prep.text)
        lines = prep.json()["read_back"]["lines"]
        for must in ("· Día: 2026-10-10", "· Hora: 21:00", "· Personas: 2", "· Nombre: Tyler Warren", "· Email: tyler@kanoe.test",
                     "· Teléfono: +34608445715", "hidden fields, sent with the page's values: token",
                     "I won't tick any box agreeing to their terms, and I stop at any CAPTCHA."):
            self.assertIn(must, "\n".join(lines))
        self.assertNotIn("website_url", "\n".join(lines))                       # the honeypot is never touched
        self.assertEqual(self.posts, [])                                        # nothing sent before the yes
        sha = prep.json()["read_back"]["sha256"]
        bad = self.c.post(f"/api/booking/forms/{prep.json()['form_id']}/send", json={"read_back_sha256": "0" * 64, "approval": {"how": "button"}})
        self.assertEqual(bad.json()["rule"], "read_back_mismatch")
        sent = self.c.post(f"/api/booking/forms/{prep.json()['form_id']}/send", json={"read_back_sha256": sha, "approval": {"how": "button"}})
        self.assertEqual(sent.status_code, 200, sent.text)
        j = sent.json()
        self.assertEqual((j["status"], j["reading"]["result"]), ("sent", "confirmed"), j)
        self.assertIn("Confirmado: mesa para 2 personas el sábado 10 de octubre a las 21:00, a nombre de Tyler Warren.", j["their_page"])
        self.assertRegex(j["booking_reference"], r"^TV-[0-9A-F]{6}$")
        url, data = self.posts[0]
        self.assertEqual(url, f"{BASE}/api/booking/test-venue/plain")
        self.assertTrue(data["token"]) and self.assertNotIn("website_url", data)
        self.assertEqual(len(FR.TEST_SUBMISSIONS), 1)                           # the venue's own book has it, once
        item = self.calls.trip_items[prep.json()["trip_item_id"]]
        self.assertEqual((item["status"], item["booking_reference"]), ("confirmed", j["booking_reference"]))
        again = self.c.post(f"/api/booking/forms/{prep.json()['form_id']}/send", json={"read_back_sha256": sha, "approval": {"how": "button"}})
        self.assertEqual((again.status_code, again.json()["rule"]), (409, "form_already"))   # once per yes
        self.assertEqual(len(self.posts), 1)

    def test_a_consent_box_or_a_captcha_stops_it_before_anything_is_filled(self):
        for variant, rule in (("consent", "form_consent"), ("captcha", "form_challenge")):
            v = self.read(variant)
            prep = self.c.post("/api/booking/forms", json={"read_id": v["read_id"], "reservation": reservation()})
            self.assertEqual((prep.status_code, prep.json()["rule"]), (422, rule), variant)
        self.assertEqual(self.posts, [])

    def test_the_wizard_reads_back_both_steps_and_sends_step_two_only_after_step_one(self):
        # Sasha 94 · the day on one page, the details on the next
        v = self.read("wizard")
        prep = self.c.post("/api/booking/forms", json={"read_id": v["read_id"], "reservation": reservation()})
        self.assertEqual(prep.status_code, 200, prep.text)
        text = "\n".join(prep.json()["read_back"]["lines"])
        one, two = text.split("Step 2")
        for must in ("· Día: 2026-10-10", "· Hora: 21:00", "· Personas: 2"):
            self.assertIn(must, one)
        for must in ("· Nombre: Tyler Warren", "· Email: tyler@kanoe.test", "· Teléfono: +34608445715"):
            self.assertIn(must, two)
        self.assertIn("only the day and the number of people will have reached them", text)
        self.assertEqual(self.posts, [])
        sent = self.c.post(f"/api/booking/forms/{prep.json()['form_id']}/send",
                           json={"read_back_sha256": prep.json()["read_back"]["sha256"], "approval": {"how": "button"}}).json()
        self.assertEqual((sent["status"], sent["reading"]["result"]), ("sent", "confirmed"), sent)
        (u1, d1), (u2, d2) = self.posts
        self.assertEqual((u1, set(d1) - {"token"}), (f"{BASE}/api/booking/test-venue/wizard/step2", {"fecha", "hora", "personas"}))
        self.assertTrue(u2.endswith("/api/booking/test-venue/wizard/confirm"))
        self.assertEqual((d2["nombre"], d2["fecha"]), ("Tyler Warren", "2026-10-10"))   # its own hidden fields carried the day
        self.assertNotIn("website_url", d2)
        self.assertEqual([x["variant"] for x in FR.TEST_SUBMISSIONS], ["wizard"])

    def test_the_wizard_stops_at_a_step_two_it_was_not_approved_for(self):
        v = self.read("wizard")
        prep = self.c.post("/api/booking/forms", json={"read_id": v["read_id"], "reservation": reservation()}).json()
        saved = FR._WIZARD_TWO
        FR._WIZARD_TWO = saved.replace('<button type="submit">', '<input id="acepto" name="acepto" type="checkbox" required><button type="submit">')
        try:
            sent = self.c.post(f"/api/booking/forms/{prep['form_id']}/send",
                               json={"read_back_sha256": prep["read_back"]["sha256"], "approval": {"how": "button"}}).json()
        finally:
            FR._WIZARD_TWO = saved
        self.assertEqual(sent["status"], "not_sent")
        self.assertIn("Only the day and the number of people reached them; nothing is booked", sent["say"])
        self.assertEqual(len(self.posts), 1)                                    # step 1 only
        self.assertEqual(FR.TEST_SUBMISSIONS, [])

    def test_our_test_venue_is_never_looked_up_on_google(self):
        # Sasha 94 · 2 Oct: "Sasha Test Venue, Madrid" pulled a real restaurant's listing and phone into the read
        with mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "places-test"}):
            v = self.read()
        self.assertFalse([u for m, u, b in self.web.requests if "places.googleapis.com" in u])
        self.assertEqual({f["kind"] for f in v["facts"]}, {"name", "booking_form"})
        self.assertIn("never looked up on Google", " ".join(s["result"] for s in v["sources"]))

    def test_a_real_venue_is_never_sent_until_approved(self):
        self.assertIsNone(FR.form_map("https://www.restaurante-real.es/reservas"))
        FR.FORM_MAPS["www.restaurante-real.es"] = {"fields": FR.TEST_FIELDS, "date_fmt": str, "time_fmt": str}
        try:
            self.assertIsNone(FR.form_map("https://www.restaurante-real.es/reservas"))         # mapped, not approved
            with mock.patch.dict(os.environ, {"SASHA_FORM_HOSTS": "www.restaurante-real.es"}):
                self.assertIsNotNone(FR.form_map("https://www.restaurante-real.es/reservas"))  # approved by the founder
        finally:
            del FR.FORM_MAPS["www.restaurante-real.es"]


if __name__ == "__main__":
    unittest.main()


from tests import test_booking_ladder as TBL  # noqa: E402


@unittest.skipUnless(TBL.PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(unittest.TestCase):
    """The same send against sql/018, with the reservation and its attempt written as the receipt reads them."""
    _q = TBL.OnPostgres._q

    @classmethod
    def setUpClass(cls):
        TBL.OnPostgres.setUpClass.__func__(cls)
        import asyncio, asyncpg, pathlib
        sql = (pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql" / "018_booking_forms.sql").read_text()

        async def apply():
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                if not await c.fetchval("select to_regclass('public.booking_forms') is not null"):
                    await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
            finally:
                await c.close()
        asyncio.run(apply())

    def make_stores(self):
        self._q("delete from booking_forms")
        return TBL.OnPostgres.make_stores(self)

    setUp = FormRung.setUp
    tearDown = FormRung.tearDown
    read = FormRung.read

    def setUp(self):   # noqa: F811 — FormRung's, then the Postgres form store
        FormRung.setUp(self)
        FR.STORE = FR.PostgresFormStore(self.base)

    def test_a_form_sent_in_postgres(self):
        v = self.read()
        prep = self.c.post("/api/booking/forms", json={"read_id": v["read_id"], "reservation": reservation()}).json()
        sent = self.c.post(f"/api/booking/forms/{prep['form_id']}/send", json={"read_back_sha256": prep["read_back"]["sha256"], "approval": {"how": "button"}})
        self.assertEqual(sent.json()["status"], "sent", sent.text)
        row = self._q("select status, http_status, response_sha256, approval from booking_forms where form_id = $1::uuid", prep["form_id"])[0]
        self.assertEqual((row["status"], row["http_status"]), ("sent", 200))
        item = self._q("select status, booking_reference from trip_items where id = $1::uuid", prep["trip_item_id"])[0]
        self.assertEqual((item["status"], item["booking_reference"]), ("confirmed", sent.json()["booking_reference"]))
        att = self._q("select method, status from booking_attempts where trip_item_id = $1::uuid", prep["trip_item_id"])
        self.assertEqual([(a["method"], a["status"]) for a in att], [("web_form", "confirmed")])
