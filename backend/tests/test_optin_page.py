"""S-55 · the Work-with-Sasha page's server half (booking_signer/optin_page.py). Offline: memory stores, a fake Resend.

    cd backend && python -m unittest tests.test_optin_page -v
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import pathlib
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import emailing as E, optin_page as P, optins as O, routes
from booking_signer.store import PostgresStore
from booking_signer.wordings import optin_wording

HERE = pathlib.Path(__file__).parent
SQL_DIR = HERE.parent / "booking_signer" / "sql"
PG_URL = os.getenv("BOOKING_TEST_DATABASE_URL", "")

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
ENV = {"SASHA_BOOKING_KEY": "test-booking-key", "SASHA_OPTIN_PAGE_ENABLED": "1", "SASHA_RESEND_API_KEY": "re_test",
       "SASHA_EMAIL_FROM": "Sasha <sasha@kanoe.test>", "SASHA_PUBLIC_URL": "https://project.kanoe.test/",
       "SASHA_RETENTION_LOOP": "0", "SASHA_CALL_SWEEP": "0"}


class R:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        return self._b


class FakeResend:
    def __init__(self):
        self.sent, self.refuse = [], None

    async def __call__(self, method, url, headers, json=None):
        assert url == E.RESEND_SEND_URL
        if self.refuse:
            return R(422, {"message": self.refuse})
        self.sent.append(json)
        return R(200, {"id": f"re_{len(self.sent)}"})


def sha(t):
    return hashlib.sha256(t.encode()).hexdigest()


class Page:
    def make_stores(self):
        raise NotImplementedError

    def rows(self):
        raise NotImplementedError

    def requests(self):
        raise NotImplementedError

    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.base = None
        self.optins, self.store = self.make_stores()
        self.mail = FakeResend()
        self.now = NOW
        self.saved = (O.OPTIN_STORE, P.PAGE_STORE, P.HTTP, P.NOW)
        O.OPTIN_STORE, P.PAGE_STORE, P.HTTP, P.NOW = self.optins, self.store, self.mail, (lambda: self.now)
        app = FastAPI()
        app.include_router(routes.router)
        self.c = TestClient(app, headers={"x-sasha-booking-key": "test-booking-key"})
        self.c.__enter__()   # one event loop for the whole test, so a Postgres pool stays on it

    def tearDown(self):
        if self.base is not None:
            self.c.portal.call(self.base.close)
        self.c.__exit__(None, None, None)
        O.OPTIN_STORE, P.PAGE_STORE, P.HTTP, P.NOW = self.saved
        self.env.stop()

    def form(self, lang="en", **over):
        wa = optin_wording("whatsapp", lang)
        ws = optin_wording("web_submit", lang, url="https://lacontra.test/reservas")
        body = {"lang": lang, "venue_name": "La Contra", "country": "ES", "website": "https://www.lacontra.test/",
                "contact_name": "Marta Ruiz", "contact_role": "owner", "email": "Reservas@LaContra.test", "authorised": True,
                "channels": {"whatsapp": {"number": "+34 600 111 222"}, "web_submit": {"url": "https://lacontra.test/reservas"}},
                "shown": {"whatsapp": wa["sha256"], "web_submit": ws["sha256"]}}
        body.update(over)
        return body

    def ask(self, **over):
        return self.c.post("/api/booking/optin/requests", json=self.form(**over))

    def token(self, i=-1):
        return re.search(r"/work-with-sasha/confirm\?t=([A-Za-z0-9_-]+)", self.mail.sent[i]["text"]).group(1)

    # ── the request ──

    def test_the_page_is_closed_until_the_founder_opens_it_and_then_nothing_is_sent(self):
        with mock.patch.dict(os.environ, {"SASHA_OPTIN_PAGE_ENABLED": ""}):
            self.assertFalse(self.c.get("/api/booking/optin/status").json()["open"])
            r = self.ask()
        self.assertEqual((r.status_code, r.json()["rule"]), (503, "page_closed"))
        self.assertEqual((self.mail.sent, self.requests()), ([], []))
        self.assertTrue(self.c.get("/api/booking/optin/status").json()["open"])

    def test_the_wordings_the_page_shows_are_the_v2_texts(self):
        w = self.c.get("/api/booking/optin/wordings?lang=es").json()
        self.assertEqual(w["version"], "v2")
        self.assertIn("una concierge de inteligencia artificial operada por Kanoe Technologies SL", w["wordings"]["whatsapp"])
        self.assertIn("{url}", w["wordings"]["web_submit"])

    def test_a_request_sends_one_email_and_records_no_consent(self):
        r = self.ask()
        self.assertEqual(r.json()["status"], "sent", r.text)
        self.assertEqual(len(self.mail.sent), 1)
        m = self.mail.sent[0]
        self.assertEqual((m["to"], m["subject"]), (["Reservas@LaContra.test"], "Confirm: Sasha for La Contra"))
        self.assertNotIn("bcc", m)
        self.assertIn("https://project.kanoe.test/work-with-sasha/confirm?t=", m["text"])
        self.assertIn("/work-with-sasha/withdraw?t=", m["text"])
        self.assertIn("an AI concierge operated by Kanoe Technologies SL", m["text"])
        self.assertIn(optin_wording("web_submit", "en", url="https://lacontra.test/reservas")["text"], m["text"])
        self.assertEqual(self.rows(), [])                                   # ⛔ not consent until the click
        stored = self.requests()[0]
        self.assertNotIn(self.token(), str(stored))                              # only the token's hash is kept
        self.assertEqual(stored["token_sha256"], sha(self.token()))

    def test_nothing_is_ticked_for_them_and_the_authority_box_is_required(self):
        self.assertEqual(self.ask(channels={}).json()["rule"], "nothing_ticked")
        self.assertEqual(self.ask(authorised="yes").json()["rule"], "not_authorised")
        self.assertEqual(self.mail.sent, [])

    def test_the_words_recorded_must_be_the_words_shown(self):
        r = self.ask(shown={"whatsapp": "0" * 64, "web_submit": "0" * 64})
        self.assertEqual((r.status_code, r.json()["rule"]), (409, "wording_changed"))
        # the URL is part of the wording: a different form URL is different words
        other = optin_wording("web_submit", "en", url="https://elsewhere.test/")["sha256"]
        r = self.ask(shown={"whatsapp": optin_wording("whatsapp", "en")["sha256"], "web_submit": other})
        self.assertEqual(r.json()["rule"], "wording_changed")

    def test_bad_scopes_are_refused(self):
        self.assertEqual(self.ask(channels={"whatsapp": {"number": "600111222"}}).json()["rule"], "number_invalid")
        self.assertEqual(self.ask(channels={"web_submit": {"url": "lacontra.test"}}).json()["rule"], "url_invalid")
        self.assertEqual(self.ask(email="not-an-address").json()["rule"], "email_invalid")

    def test_the_daily_limits_hold(self):
        for _ in range(3):
            self.assertEqual(self.ask().json()["status"], "sent")
        r = self.ask()
        self.assertEqual((r.status_code, r.json()["rule"]), (429, "too_many_for_address"))
        self.assertEqual(len(self.mail.sent), 3)

    def test_a_refused_email_is_said_and_can_never_confirm(self):
        self.mail.refuse = "domain not verified"
        r = self.ask()
        self.assertEqual((r.status_code, r.json()["rule"]), (502, "email_not_sent"))
        self.assertIn("domain not verified", r.json()["message"])
        self.assertEqual(self.requests()[0]["email_status"], "not_sent")

    # ── the confirmation ──

    def test_opening_the_link_writes_nothing_and_confirm_writes_one_row_per_ticked_channel(self):
        self.ask()
        t = self.token()
        v = self.c.post("/api/booking/optin/preview", json={"t": t}).json()
        self.assertEqual([c["channel"] for c in v["request"]["channels"]], ["whatsapp", "web_submit"])
        self.assertNotIn(t, str(v))
        self.assertEqual(self.rows(), [])                                   # a scanner opening it consents to nothing
        r = self.c.post("/api/booking/optin/confirm", json={"t": t})
        self.assertEqual(r.json()["status"], "confirmed", r.text)
        rows = self.rows()
        self.assertEqual([(x["venue_id"], x["channel"], x["scope"], x["status"], x["method"]) for x in rows],
                         [("host:lacontra.test", "whatsapp", "+34600111222", "active", "form"),
                          ("host:lacontra.test", "web_submit", "https://lacontra.test/reservas", "active", "form")])
        w = rows[1]
        self.assertEqual((w["agreed_by_name"], w["agreed_by_role"], w["wording_version"]), ("Marta Ruiz", "owner", "v2"))
        self.assertEqual(w["wording_sha256"], sha(w["wording_text"]))
        self.assertIn("https://lacontra.test/reservas", w["wording_text"])
        ev = w["evidence"]
        self.assertEqual(ev["confirmation_email"], {"to": "Reservas@LaContra.test", "provider_id": "re_1"})
        self.assertEqual(ev["authority"], "stated by the person who ticked the box, not verified")
        self.assertEqual(ev["submitted"]["authorised"], True)
        # twice is once
        self.assertEqual(self.c.post("/api/booking/optin/confirm", json={"t": t}).json()["status"], "already_confirmed")
        self.assertEqual(len(self.rows()), 2)
        # and the refusal check now lets Sasha use WhatsApp at exactly that number, for a read keyed by its listing
        ids = O.venue_ids_of({"listing": {"place_id": "ChIJ-x"}, "name": "La Contra", "country": "ES",
                              "facts": [{"source_kind": "site", "source_url": "https://www.lacontra.test/contacto"}]})
        self.assertIsNone(O.check_send(rows, "whatsapp", "+34600111222"))
        self.assertIn("host:lacontra.test", ids)

    def test_an_expired_or_unknown_link_confirms_nothing(self):
        self.ask()
        t = self.token()
        self.now = NOW + timedelta(hours=49)
        self.assertEqual(self.c.post("/api/booking/optin/confirm", json={"t": t}).json()["rule"], "link_expired")
        self.assertEqual(self.c.post("/api/booking/optin/confirm", json={"t": "x" * 43}).json()["rule"], "link_unknown")
        self.assertEqual(self.rows(), [])

    # ── withdrawal ──

    def test_withdrawing_stops_every_channel_including_phone_and_email(self):
        self.ask()
        t = self.token()
        self.c.post("/api/booking/optin/confirm", json={"t": t})
        self.now = NOW + timedelta(days=3)
        r = self.c.post("/api/booking/optin/withdraw", json={"t": t})
        self.assertEqual((r.json()["status"], r.json()["rows"]), ("withdrawn", 2))
        rows = self.rows()
        self.assertEqual([x["status"] for x in rows], ["active", "active", "withdrawn", "withdrawn"])
        self.assertEqual(rows[-1]["withdrawn_how"], "form_link")
        for ch in ("phone", "email", "whatsapp"):
            self.assertEqual(O.check_send(rows, ch, "+34600111222").rule, "venue_opted_out", ch)

    def test_an_old_link_never_undoes_a_withdrawal(self):
        self.ask()
        t_old = self.token()
        self.now = NOW + timedelta(hours=1)
        self.ask()
        t_new = self.token()
        self.c.post("/api/booking/optin/confirm", json={"t": t_new})
        self.now = NOW + timedelta(hours=2)
        self.c.post("/api/booking/optin/withdraw", json={"t": t_new})
        self.now = NOW + timedelta(hours=3)
        r = self.c.post("/api/booking/optin/confirm", json={"t": t_old})
        self.assertEqual((r.status_code, r.json()["rule"]), (409, "withdrawn_since"))
        self.assertEqual(O.check_send(self.rows(), "phone").rule, "venue_opted_out")

    def test_withdrawing_before_ever_confirming_still_stops_contact(self):
        self.ask()
        self.c.post("/api/booking/optin/withdraw", json={"t": self.token()})
        self.assertEqual(O.check_send(self.rows(), "email").rule, "venue_opted_out")

    def test_the_spanish_email(self):
        self.ask(lang="es")
        m = self.mail.sent[0]
        self.assertEqual(m["subject"], "Confirmad: Sasha para La Contra")
        self.assertIn("una concierge de inteligencia artificial operada por Kanoe Technologies SL", m["text"])
        self.assertIn("&lang=es", m["text"])


class OnMemory(Page, unittest.TestCase):
    def make_stores(self):
        optins = O.MemoryOptinStore()
        return optins, P.MemoryPageStore(optins)

    def rows(self):
        return self.optins.rows

    def requests(self):
        return list(self.store.requests.values())


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(Page, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "test" not in urlsplit(PG_URL).path.lstrip("/"):
            raise unittest.SkipTest("refusing a database whose name does not contain 'test'")

        async def fresh():
            import asyncpg
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute("drop schema if exists auth cascade; drop schema public cascade; create schema public;")
                await c.execute((HERE / "fixtures" / "model_a_live_2026-09-28.sql").read_text(encoding="utf-8"))
                for f in ("001_booking_storage.sql", "002_prepared_status.sql", "003_phone_calls.sql", "004_ladder.sql",
                          "005_slot_links.sql", "011_reservation_request.sql", "007_retention_log.sql", "008_venue_optins.sql", "009_venue_optin_requests.sql"):
                    await c.execute((SQL_DIR / f).read_text(encoding="utf-8"))
            finally:
                await c.close()
        asyncio.run(fresh())

    def _q(self, sql, many=False):
        async def q():
            import asyncpg
            c = await asyncpg.connect(PG_URL)
            try:
                return await c.execute(sql) if many else [dict(r) for r in await c.fetch(sql)]
            finally:
                await c.close()
        return asyncio.run(q())

    def make_stores(self):
        self._q("set booking.retention = 'on'; delete from venue_optins; reset booking.retention; delete from venue_optin_requests;", many=True)
        self.base = PostgresStore(PG_URL)
        return O.PostgresOptinStore(self.base), P.PostgresPageStore(self.base)

    def rows(self):
        out = self._q("select * from venue_optins order by id")
        for r in out:
            for k in ("evidence", "withdrawn_evidence"):
                r[k] = json.loads(r[k]) if isinstance(r[k], str) else r[k]
        return out

    def requests(self):
        return self._q("select * from venue_optin_requests order by created_at")

    def test_the_database_itself_refuses_an_edit_to_consent(self):
        self.ask()
        self.c.post("/api/booking/optin/confirm", json={"t": self.token()})
        with self.assertRaisesRegex(Exception, "append-only"):
            self._q("update venue_optins set scope = 'x'")


if __name__ == "__main__":
    unittest.main()
