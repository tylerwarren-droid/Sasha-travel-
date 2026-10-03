"""CR 1 · product_cases ON POSTGRES (sql/028): the store's real SQL. Written after the CR 2 rehearsal found that the case
insert passed its 30-day expiry as the string "30 days", which asyncpg refuses (DataError) — every case write on
production would have failed while every memory-store test passed. Only a real database catches that class of bug.

    BOOKING_TEST_DATABASE_URL=postgresql://…/sasha_test  python -m unittest tests.test_products_pg_cr1 -v
"""
from __future__ import annotations

import asyncio
import unittest
import uuid
from datetime import date

from booking_signer.store import PostgresStore
from products import store as ST
from products.campus import visits as VS
from tests import test_booking_ladder as TBL

run = TBL.run
from booking_signer.account import DEMO_ACCOUNT_ID as ACCOUNT  # noqa: E402  (a user in the model-A fixture)


@unittest.skipUnless(TBL.PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class CasesOnPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TBL.OnPostgres.setUpClass.__func__(cls)
        import asyncpg

        async def apply():
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                sql = (TBL.SQL_DIR / "028_products.sql").read_text()
                await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
            finally:
                await c.close()
        asyncio.run(apply())

    def setUp(self):
        self.saved = (ST.STORE, ST.BASE)
        base = PostgresStore(TBL.PG_URL)
        self.assertEqual(run(ST.choose(base)), "postgres")

    def tearDown(self):
        ST.STORE, ST.BASE = self.saved

    def test_put_get_update_and_the_expiry_is_thirty_days(self):
        cid = run(ST.STORE.put("campus", ACCOUNT, "k", {"watch": {"open": True, "schools": ["yale"], "month": [2027, 4]}}))
        row = run(ST.STORE.get(cid))
        self.assertEqual(row["state"]["watch"]["schools"], ["yale"])
        self.assertEqual((row["expires_at"] - row["created_at"]).days, 30)
        self.assertEqual([r["id"] for r in run(ST.STORE.watching())], [cid])
        run(ST.STORE.update(cid, {"watch": {"open": False}}))
        self.assertEqual(run(ST.STORE.watching()), [])
        self.assertEqual(len(run(ST.STORE.of_product("campus"))), 1)
        self.assertIsNone(run(ST.STORE.get("no-such-case-id-xxxxxx")))

    def test_a_registered_visit_is_a_booking_and_confirms(self):
        from products.campus import schools as SC
        x = {"day": "2026-11-01", "start": "11:30", "end": "12:30", "title": "Campus Tour", "location": "Visitor Center",
             "form_url": "https://apps.admissions.yale.edu/register/?id=x"}
        item = run(VS.record(ACCOUNT, SC.SCHOOLS["yale"], x, 2))
        self.assertTrue(item)
        run(VS.confirm(item))

        async def status():
            import asyncpg
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                return await c.fetchrow("select status, type, party_size, (date_time at time zone local_timezone)::time as t "
                                        "from trip_items where id = $1", uuid.UUID(item))
            finally:
                await c.close()
        r = run(status())
        self.assertEqual((r["status"], r["type"], r["party_size"], str(r["t"])), ("confirmed", "experience", 2, "11:30:00"))
