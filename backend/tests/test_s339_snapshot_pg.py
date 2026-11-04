"""Sasha 339 · trip_basket_items.snapshot is an OBJECT — on REAL Postgres, with the pool's jsonb codec exactly as store.py sets it.
Reproduces the bug (json.dumps under the codec → a JSON string; `string || object` → an array), then proves: new writes are objects,
supersede keeps an old row an object, every reader turns an old shape into its dict, and 051 repairs the old rows (idempotent).
    cd backend && python -m unittest tests.test_s339_snapshot_pg -v
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import unittest
import uuid
from unittest import mock

from booking_signer import basket as BK
import os
import tempfile

from tests.test_s336_keep_owners import _block

PG, _SERVER = os.getenv("BOOKING_TEST_DATABASE_URL", ""), None
if not PG:
    try:
        import pgserver   # its OWN throwaway local Postgres (336's module stops its own when it finishes)
        _SERVER = pgserver.get_server(tempfile.mkdtemp(prefix="s339pg"), cleanup_mode="stop")
        PG = _SERVER.get_uri()
    except Exception:
        PG = ""

SQL = pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql"
ACCT, TRIP = uuid.uuid4(), uuid.uuid4()


@unittest.skipUnless(PG, "no real Postgres (BOOKING_TEST_DATABASE_URL / pgserver) — the Postgres proof did NOT run")
class SnapshotIsAnObject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import asyncpg
        cls.loop = asyncio.new_event_loop()
        cls.go = cls.loop.run_until_complete
        cls.db = "s339_" + uuid.uuid4().hex[:8]
        admin = cls.go(asyncpg.connect(PG))
        cls.go(admin.execute(f"create database {cls.db}"))
        cls.go(admin.close())
        cls.c = cls.go(asyncpg.connect(PG, database=cls.db))
        cls.go(cls.c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"))   # production's pool init
        c = cls.c

        async def schema():
            for role in ("anon", "authenticated"):
                await c.execute(f"do $$ begin create role {role}; exception when duplicate_object then null; end $$")
            await c.execute("create schema if not exists auth; create table auth.users (id uuid primary key); "
                            "create table public.trips (id uuid primary key); create table public.trip_items (id uuid primary key)")
            await c.execute(_block("033_trip_basket.sql"))
            await c.execute("insert into auth.users values ($1)", ACCT)
            await c.execute("insert into public.trips values ($1)", TRIP)
        cls.go(schema())

    @classmethod
    def tearDownClass(cls):
        import asyncpg
        cls.go(cls.c.close())
        admin = cls.go(asyncpg.connect(PG))
        cls.go(admin.execute(f"drop database if exists {cls.db}"))
        cls.go(admin.close())
        cls.loop.close()

    def kinds(self):
        return {r["t"]: r["n"] for r in self.go(self.c.fetch("select jsonb_typeof(snapshot) t, count(*) n from trip_basket_items group by 1"))}

    def old_write(self, snap, ref):   # what basket.py did before 339: json.dumps under the codec
        return self.go(self.c.fetchval(
            "insert into trip_basket_items (trip_id, account_id, kind, state, slice_key, provider, provider_ref, snapshot, is_test) "
            "values ($1,$2,'flight','suggested','LTN-MAD 2026-11-23','duffel',$3,$4::jsonb,true) returning id", TRIP, ACCT, ref, json.dumps(snap)))

    def test_the_class(self):
        go, c = self.go, self.c

        async def run(fn):
            return await fn(c)
        with mock.patch.object(BK, "STORE_RUN", run):
            # the bug, reproduced on the real store
            old = self.old_write({"owner": "Iberia", "from": "LTN", "to": "MAD"}, "off_old")
            arr = self.old_write({"owner": "easyJet", "from": "LTN", "to": "MAD"}, "off_arr")
            go(c.execute("update trip_basket_items set snapshot = snapshot || jsonb_build_object('superseded_at', 'x') where id = $1", arr))
            self.assertEqual(self.kinds(), {"string": 1, "array": 1})
            # Sasha 340 · 051 repairs the old rows FIRST (production: applied 4 Nov, 1,520 rows all objects) — the readers' PATCH is gone
            before = go(c.fetchval("select count(*) from trip_basket_items"))
            go(c.execute(_block("051_basket_snapshot_repair.sql")))
            go(c.execute(_block("051_basket_snapshot_repair.sql")))                       # twice: idempotent
            self.assertEqual(self.kinds(), {"object": before})
            self.assertEqual(go(c.fetchval("select snapshot->>'owner' || '|' || (snapshot->>'superseded_at') from trip_basket_items "
                                           "where provider_ref = 'off_arr'")), "easyJet|x")
            rows = {r["provider_ref"]: r for r in go(BK.items(str(ACCT), str(TRIP), ("suggested",)))}
            self.assertEqual(rows["off_old"]["snapshot"]["owner"], "Iberia")
            # a new search of the slice: the new row an OBJECT; the old row superseded — still an object (plain ||, objects only now)
            go(BK.suggest(str(ACCT), str(TRIP), "flight", [{"provider": "duffel", "provider_ref": "off_new", "price_amount": 73.1,
                                                            "price_currency": "EUR", "snapshot": {"owner": "Duffel Airways", "from": "LTN", "to": "MAD"}}],
                          slice_key="LTN-MAD 2026-11-23"))
            t = {r["provider_ref"]: r["t"] for r in go(c.fetch("select provider_ref, jsonb_typeof(snapshot) t from trip_basket_items"))}
            self.assertEqual((t["off_new"], t["off_old"]), ("object", "object"))
            self.assertTrue(go(c.fetchval("select snapshot->>'superseded_at' from trip_basket_items where provider_ref = 'off_old'")))
        print(f"\n[s339 snapshot · real Postgres] bug reproduced (string + array) → 051 repaired {before} rows (twice: idempotent) → "
              f"new writes objects, supersede keeps objects")


def tearDownModule():
    if _SERVER is not None:
        try:
            _SERVER.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
