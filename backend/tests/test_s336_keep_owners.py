"""Sasha 336 · ONE OWNER RECORD PER VAULT, on REAL Postgres (docs/sasha/S-336-group-demo-fixes.md).

Production's schema in order — 036, 037, 042's Keep foreign keys (auth.users), 048 (the group) — then an ACCOUNT's vault saved the old way,
then 050. Proves: the account's vault is unchanged (same rows, still opens); a GROUP MEMBER's vault saves, reads masked, deletes with its
key shredded; the database itself refuses a vault for nobody, an owner that is both or neither, a row without its owner; and deleting the
member (or the account) cascades its vault away. The in-memory store can't hide any of it: this is the store production runs.

Real Postgres: BOOKING_TEST_DATABASE_URL, else a throwaway local server (pip `pgserver`); neither → skipped, and says so.
    cd backend && python -m unittest tests.test_s336_keep_owners -v
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import tempfile
import unittest
import uuid
from unittest import mock

from agapi import keep as K, s2_keep as KEEP, s2_records as REC

SQL = pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql"
ACCT = "00000000-0000-4000-8000-000000000336"
PASSPORT = {"number": "PZZ336001", "country": "GB", "expires_on": "2031-06-30", "name": "TEST WORKER", "born_on": "1990-01-10"}
PG, _SERVER = os.getenv("BOOKING_TEST_DATABASE_URL", ""), None
if not PG:
    try:
        import pgserver   # a real Postgres, local and throwaway
        _SERVER = pgserver.get_server(tempfile.mkdtemp(prefix="s336pg"), cleanup_mode="stop")
        PG = _SERVER.get_uri()
    except Exception:
        PG = ""


def _block(name: str) -> str:
    s = (SQL / name).read_text()
    return s[s.index("begin;"):s.index("commit;") + len("commit;")]


@unittest.skipUnless(PG, "no real Postgres (BOOKING_TEST_DATABASE_URL / pgserver) — the Postgres proof did NOT run")
class KeepOwnersOnPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import asyncpg
        cls.loop = asyncio.new_event_loop()
        cls.go = cls.loop.run_until_complete
        cls.db = "s336_" + uuid.uuid4().hex[:8]
        admin = cls.go(asyncpg.connect(PG))
        cls.go(admin.execute(f"create database {cls.db}"))
        cls.go(admin.close())
        cls.c = cls.go(asyncpg.connect(PG.replace("/postgres?", f"/{cls.db}?") if "/postgres?" in PG else PG, database=cls.db))
        c = cls.c

        async def schema():
            for role in ("anon", "authenticated"):
                await c.execute(f"do $$ begin create role {role}; exception when duplicate_object then null; end $$")
            await c.execute("create schema if not exists auth; create table auth.users (id uuid primary key)")
            await c.execute("create table public.trips (id uuid primary key)")
            await c.execute(_block("036_s2_activity_whatsapp.sql"))
            await c.execute(_block("037_keep.sql"))
            keep_fks = [l for l in (SQL / "042_account_purge.sql").read_text().splitlines()
                        if l.startswith("alter table public.keep_") and "auth.users" in l]   # production's Keep FKs, as 042 added them
            assert len(keep_fks) == 3, keep_fks
            await c.execute("\n".join(keep_fks))
            await c.execute(_block("048_group_movement.sql"))
        cls.go(schema())

    @classmethod
    def tearDownClass(cls):
        import asyncpg
        cls.go(cls.c.close())
        admin = cls.go(asyncpg.connect(PG))
        cls.go(admin.execute(f"drop database if exists {cls.db}"))
        cls.go(admin.close())
        cls.loop.close()

    def _keep(self):
        c = self.c

        async def run(fn):
            return await fn(c)
        kms = K.LocalKms(b"\x07" * 32)
        return [mock.patch.object(KEEP, "STORE", KEEP.PostgresKeepStore(run)), mock.patch.object(REC, "RUN", run),
                mock.patch("booking_signer.vault.kms.kek", lambda: kms)]

    def test_the_whole_class(self):
        go, c = self.go, self.c
        ps = self._keep()
        for p in ps:
            p.start()
        try:
            # ── BEFORE 050: an account's vault, saved the way production saves it today (042: accounts only) ──
            go(c.execute("insert into auth.users (id) values ($1)", uuid.UUID(ACCT)))
            acct_item = go(KEEP.put(ACCT, "passport", {**PASSPORT, "number": "PAC336000"}))
            go(KEEP.put(ACCT, "loyalty", {"program": "Iberia Plus", "number": "IB336000"}))
            before = go(c.fetchrow("select (select count(*) from keep_keys) k, (select count(*) from keep_items) i, (select count(*) from keep_fills) f"))
            # the member's save fails before 050 — SASHA 335's finding, reproduced on the real schema
            org, mv, member = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            go(c.execute("insert into auth.users (id) values ($1)", org))
            gid = go(c.fetchval("insert into public.groups (owner_id, name) values ($1, 'Obras Ejemplo SL') returning id", org))
            mvid = go(c.fetchval("insert into public.group_movements (group_id, destination) values ($1, 'Madrid') returning id", gid))
            go(c.execute("insert into public.group_members (id, movement_id, name) values ($1, $2, 'Test Worker')", member, mvid))
            with self.assertRaises(KEEP.KeepError) as e:
                go(KEEP.put(str(member), "passport", PASSPORT))
            self.assertEqual(e.exception.rule, "keep_owner_unknown")                     # said as itself — never "the key service"

            # ── 050 ──
            go(c.execute(_block("050_keep_owners.sql")))
            go(c.execute(_block("050_keep_owners.sql")))                                  # twice: idempotent
            # Sasha 351 · 053: the roster — the vault belongs to the PERSON (the worker once), never a trip's row
            go(c.execute(_block("049_traveller_vault.sql")))
            go(c.execute(_block("053_group_roster.sql")))
            go(c.execute(_block("053_group_roster.sql")))                                 # twice: idempotent
            link, member = member, go(c.fetchval("select person_id from public.group_members where id = $1", member))
            after = go(c.fetchrow("select (select count(*) from keep_keys) k, (select count(*) from keep_items) i, (select count(*) from keep_fills) f"))
            self.assertEqual(tuple(before), tuple(after))                                 # existing rows preserved
            self.assertEqual(go(c.fetchval("select count(*) from keep_owners where user_id = $1", uuid.UUID(ACCT))), 1)
            # the account's vault, unchanged: the same masks, and its value still opens
            acct_masks = [i["masked"] for i in go(KEEP.list_(ACCT))]
            self.assertEqual(len(acct_masks), 2)
            self.assertTrue(all("••••" in m for m in acct_masks))
            it = go(KEEP._store().item(ACCT, acct_item["item_id"]))
            dek = go(KEEP._dek(ACCT, create=False))
            self.assertEqual(K.open_(dek, K.item_aad(ACCT, ACCT, str(it["id"]), it["type"]), bytes(it["nonce"]), bytes(it["ciphertext"]))["number"], "PAC336000")

            # ── a GROUP MEMBER's vault: saves, reads masked, deletes (key shredded) ──
            saved = go(KEEP.put(str(member), "passport", PASSPORT))
            self.assertTrue(saved["created"])
            masks = [i["masked"] for i in go(KEEP.list_(str(member)))]
            self.assertEqual(len(masks), 1)
            self.assertIn("••••", masks[0])
            self.assertNotIn("PZZ336001", masks[0])
            self.assertEqual(go(c.fetchval("select person_id from keep_owners where id = $1", member)), member)   # the PERSON owns it
            mv2 = go(c.fetchval("insert into public.group_movements (group_id, destination) values ($1, 'Lisbon') returning id", gid))
            link2 = go(c.fetchval("insert into public.group_members (movement_id, person_id) values ($1, $2) returning id", mv2, member))
            with self.assertRaises(KEEP.KeepError) as e:                                  # a trip's link (the same person, another trip)
                go(KEEP.put(str(link2), "passport", PASSPORT))                            # is never a vault owner: one vault, the person's
            self.assertEqual(e.exception.rule, "keep_owner_unknown")
            blob = go(c.fetchval("select string_agg(row_to_json(t)::text, ' ') from (select * from keep_items) t"))
            self.assertNotIn("PZZ336001", blob)                                           # ciphertext only
            self.assertEqual(go(KEEP.delete(str(member))), {"deleted": 1, "key_destroyed": True})
            self.assertEqual(go(c.fetchval("select count(*) from keep_keys where account_id = $1", member)), 0)

            # ── the database refuses the rest of the class ──
            import asyncpg
            nobody = uuid.uuid4()
            with self.assertRaises(KEEP.KeepError) as e:                                  # a vault for nobody
                go(KEEP.put(str(nobody), "passport", PASSPORT))
            self.assertEqual(e.exception.rule, "keep_owner_unknown")
            with self.assertRaises(asyncpg.CheckViolationError):                          # an owner that is both
                go(c.execute("insert into keep_owners (id, user_id, member_id) values ($1, $1, $2)", org, member))
            with self.assertRaises(asyncpg.CheckViolationError):                          # … or neither
                go(c.execute("insert into keep_owners (id) values ($1)", nobody))
            with self.assertRaises(asyncpg.CheckViolationError):                          # … or under another id than its source
                go(c.execute("insert into keep_owners (id, user_id) values ($1, $2)", nobody, org))
            with self.assertRaises(asyncpg.ForeignKeyViolationError):                     # a row without its owner
                go(c.execute("insert into keep_keys (account_id, wrapped_dek, kek_version) values ($1, $2, 'v')", nobody, b"\0" * 40))
            with self.assertRaises(asyncpg.UniqueViolationError):                         # one owner row per source
                go(c.execute("insert into keep_owners (id, person_id) values ($1, $1)", member))

            # ── cascades from BOTH sources ──
            go(KEEP.put(str(member), "passport", PASSPORT))
            go(c.execute("delete from public.group_people where id = $1", member))        # the person leaves the roster
            self.assertEqual(go(c.fetchval("select count(*) from keep_items where account_id = $1", member)), 0)
            self.assertEqual(go(c.fetchval("select count(*) from keep_owners where id = $1", member)), 0)
            go(c.execute("delete from auth.users where id = $1", uuid.UUID(ACCT)))         # the account is deleted
            self.assertEqual(go(c.fetchval("select count(*) from keep_items where account_id = $1", uuid.UUID(ACCT))), 0)
            fks = {r["conname"]: r["d"] for r in go(c.fetch(
                "select conname, pg_get_constraintdef(oid) d from pg_constraint where contype = 'f' and conrelid::regclass::text in "
                "('keep_keys','keep_items','keep_fills')"))}
            self.assertFalse([n for n, d in fks.items() if "auth.users" in d])            # 042's FKs are gone …
            self.assertEqual(sum("keep_owners(id)" in d for d in fks.values()), 3)        # … each table references the one owner
            print(f"\n[s336 proof · real Postgres] counts before/after 050: {tuple(before)} → {tuple(after)} · member vault saved, "
                  f"masked {masks[0]!r}, deleted (key shredded) · refused: nobody / both / neither / not its source / no owner / twice · "
                  f"cascades from group_people (053) and auth.users")
        finally:
            for p in ps:
                p.stop()


def tearDownModule():
    if _SERVER is not None:
        try:
            _SERVER.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
