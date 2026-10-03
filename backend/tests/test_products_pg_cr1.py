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

    async def _with_store(self, body):
        """One event loop for the whole test: the pool is made, used and closed on it (run() makes a new loop per call)."""
        saved = (ST.STORE, ST.BASE)
        base = PostgresStore(TBL.PG_URL)
        try:
            self.assertEqual(await ST.choose(base), "postgres")
            return await body()
        finally:
            ST.STORE, ST.BASE = saved
            await base.close() if hasattr(base, "close") else None

    def test_put_get_update_and_the_expiry_is_thirty_days(self):
        async def body():
            cid = await ST.STORE.put("campus", ACCOUNT, "k", {"watch": {"open": True, "schools": ["yale"], "month": [2027, 4]}})
            row = await ST.STORE.get(cid)
            self.assertEqual(row["state"]["watch"]["schools"], ["yale"])
            self.assertEqual((row["expires_at"] - row["created_at"]).days, 30)
            self.assertIn(cid, [r["id"] for r in await ST.STORE.watching()])
            await ST.STORE.update(cid, {"watch": {"open": False}})
            self.assertNotIn(cid, [r["id"] for r in await ST.STORE.watching()])
            self.assertTrue(await ST.STORE.of_product("campus"))
            self.assertIsNone(await ST.STORE.get("no-such-case-id-xxxxxx"))
        run(self._with_store(body))

    def test_a_registered_visit_is_a_booking_and_confirms(self):
        from products.campus import schools as SC
        x = {"day": "2026-11-01", "start": "11:30", "end": "12:30", "title": "Campus Tour", "location": "Visitor Center",
             "form_url": "https://apps.admissions.yale.edu/register/?id=x"}

        async def body():
            item = await VS.record(ACCOUNT, SC.SCHOOLS["yale"], x, 2)
            self.assertTrue(item)
            await VS.confirm(item)
            return item
        item = run(self._with_store(body))

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

    def test_cr10_a_self_booked_appointment_is_guest_booked_in_sasha_bookings(self):
        from datetime import date as _d
        from products import itinerary as IT

        async def body():
            return await IT.guest_booked(ACCOUNT, type_="visa", provider_name=IT.CONSULATE, on=_d(2026, 11, 12), at="10:00",
                                         tz="Europe/London", location="Spanish Consulate General, London")
        item = run(self._with_store(body))

        async def row():
            import asyncpg
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                return await c.fetchrow("select ti.status, ti.type, t.title, (ti.date_time at time zone ti.local_timezone)::time as t "
                                        "from trip_items ti join trips t on t.id = ti.trip_id where ti.id = $1", uuid.UUID(item))
            finally:
                await c.close()
        r = run(row())
        self.assertEqual((r["status"], r["type"], r["title"], str(r["t"])), ("guest_booked", "visa", "Sasha bookings", "10:00:00"))

    def test_cr13_a_skill_conversation_lives_under_a_real_product_and_never_touches_its_row(self):
        """028's CHECK allows campus/relocation/health only: the trip plan is stored under the product it serves,
        marked state.skill — and the product's own conversation row is a different row."""
        wa = "cr13-" + uuid.uuid4().hex[:8]

        async def body():
            await ST.STORE.put_conversation(wa, ACCOUNT, "relocation", {"step": "appointments"})
            await ST.STORE.put_conversation(wa, ACCOUNT, "trip", {"for": "relocation", "step": "origin"})
            await ST.STORE.put_conversation(wa, ACCOUNT, "trip", {"for": "relocation", "step": "handed"})
            got = {r["product"]: r["state"]["pending"]["step"] for r in await ST.STORE.conversations(wa)}
            await ST.STORE.drop_conversation(wa, "trip")
            left = [r["product"] for r in await ST.STORE.conversations(wa)]
            await ST.STORE.drop_conversation(wa, "relocation")
            return got, left
        got, left = run(self._with_store(body))
        self.assertEqual(got, {"relocation": "appointments", "trip": "handed"})
        self.assertEqual(left, ["relocation"])
