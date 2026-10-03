"""S-62 step 5 · a guest's name and mobile, stored once with the consent shown; changed and deleted on request; each
account sees only its own. In memory and, with BOOKING_TEST_DATABASE_URL, on Postgres with sql/015 applied.

    cd backend && python -m unittest tests.test_contacts -v
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import unittest
from datetime import datetime, timezone
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import contacts as CT, identity as I, routes
from booking_signer.store import PostgresStore
from tests import test_booking_ladder as TBL
from tests.test_booking_ladder import PG_URL
from tests.test_identity import JWK, token

NOW = datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc)
SQL = pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql" / "015_guest_contacts.sql"


class Contacts:
    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": "k", "SASHA_CALL_SWEEP": "0", "FOUNDER_ACCOUNT_ID": "",
                                               "SASHA_SUPABASE_URL": "https://testref.supabase.co"})
        self.env.start()
        self.saved = (CT.STORE, CT.NOW, I.FETCH)
        CT.STORE, CT.NOW = self.make_store(), (lambda: NOW)

        async def fetch():
            return {"keys": [JWK]}
        I.FETCH = fetch
        I.reset_cache()
        app = FastAPI()
        app.include_router(routes.router)
        self.c = TestClient(app, headers={"x-sasha-booking-key": "k", "x-sasha-session": "founder"})
        self.c.__enter__()
        self.c0 = consent = self.c.get("/api/booking/contact").json()["consent"]
        self.ok = {"name": "Anna  Johnson", "mobile": "+44 7700 900123", "consent_version": consent["version"], "consent_sha256": consent["sha256"]}

    def tearDown(self):
        self.c.__exit__(None, None, None)
        CT.STORE, CT.NOW, I.FETCH = self.saved
        I.reset_cache()
        self.env.stop()

    def test_saved_once_with_the_consent_shown(self):
        self.assertEqual(self.c0["text"], CT.CONSENT["v1"])
        self.assertIsNone(self.c.get("/api/booking/contact").json()["contact"])
        r = self.c.put("/api/booking/contact", json=self.ok)
        self.assertEqual(r.status_code, 200, r.text)
        got = self.c.get("/api/booking/contact").json()["contact"]
        self.assertEqual((got["name"], got["mobile_e164"], got["consent_version"]), ("Anna Johnson", "+447700900123", "v1"))

    def test_sasha118_the_name_as_typed_never_upper_cased(self):
        """2 Oct: "TYLER WARREN" was saved, and venues read "a nombre de WARREN"."""
        for typed, kept in (("TYLER WARREN", "Tyler Warren"), ("Tyler McDonald", "Tyler McDonald"), ("ana de la Vega", "ana de la Vega"),
                            ("JOSÉ-MARÍA O'NEILL", "José-María O'Neill")):
            self.assertEqual(self.c.put("/api/booking/contact", json={**self.ok, "name": typed}).status_code, 200)
            self.assertEqual(self.c.get("/api/booking/contact").json()["contact"]["name"], kept, typed)
        self.c.delete("/api/booking/contact")                                    # the next test starts with none

    def test_a_stale_or_altered_consent_saves_nothing(self):
        for bad in ({"consent_sha256": "0" * 64}, {"consent_version": "v0"}, {"consent_sha256": None}):
            r = self.c.put("/api/booking/contact", json={**self.ok, **bad})
            self.assertEqual((r.status_code, r.json()["rule"]), (422, "consent_not_current"), bad)
        for bad, rule in (({"mobile": "07700 900123"}, "mobile_invalid"), ({"name": "  "}, "name_invalid")):
            self.assertEqual(self.c.put("/api/booking/contact", json={**self.ok, **bad}).json()["rule"], rule)
        self.assertIsNone(self.c.get("/api/booking/contact").json()["contact"])

    def test_change_then_delete(self):
        self.c.put("/api/booking/contact", json=self.ok)
        self.c.put("/api/booking/contact", json={**self.ok, "mobile": "0044 7700 900999"})
        self.assertEqual(self.c.get("/api/booking/contact").json()["contact"]["mobile_e164"], "+447700900999")
        d = self.c.delete("/api/booking/contact").json()
        self.assertEqual((d["deleted"], self.c.get("/api/booking/contact").json()["contact"]), (True, None))
        self.assertFalse(self.c.delete("/api/booking/contact").json()["deleted"])

    def test_another_account_sees_none_of_it(self):
        self.c.put("/api/booking/contact", json=self.ok)
        b = {"authorization": f"Bearer {token()}", "x-sasha-session": ""}
        self.assertIsNone(self.c.get("/api/booking/contact", headers=b).json()["contact"])
        self.assertFalse(self.c.delete("/api/booking/contact", headers=b).json()["deleted"])
        self.assertIsNotNone(self.c.get("/api/booking/contact").json()["contact"])           # A's is untouched
        self.assertEqual(self.c.get("/api/booking/contact", headers={"x-sasha-session": ""}).status_code, 401)


class OnMemory(Contacts, unittest.TestCase):
    def make_store(self):
        return CT.MemoryContactStore()


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgresContacts(Contacts, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TBL.OnPostgres.setUpClass.__func__(cls)
        import asyncpg

        async def apply():
            c = await asyncpg.connect(PG_URL)
            try:
                sql = SQL.read_text()
                await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
            finally:
                await c.close()
        asyncio.run(apply())

    def make_store(self):
        self.base = PostgresStore(PG_URL)
        return CT.PostgresContactStore(self.base)

    def tearDown(self):
        self.c.portal.call(self.base.close)
        super().tearDown()


if __name__ == "__main__":
    unittest.main()
