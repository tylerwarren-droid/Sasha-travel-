"""Sasha 345 · her words come from the record (docs/sasha/S-345-words-from-the-record.md).
    cd backend && python -m unittest tests.test_s345_words_from_the_record -v
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
import uuid

from agapi import v0 as API
from app.agent import sasha as S, voice as V
from booking_signer import groups as G
from tests import test_s332 as W

run = asyncio.run
OWNER = W.OWNER
FIVE = "\n".join(["Ana Exec, London, 2026-12-01, 2026-12-05, executive", "Ben Exec, London, 2026-12-01, 2026-12-05, executive",
                  "Cai Exec, London, 2026-12-01, 2026-12-05, executive", "Dee Worker, London, 2026-12-01, 2026-12-05, worker",
                  "Eli Worker, London, 2026-12-01, 2026-12-05, worker"])


class TylersWords(unittest.TestCase):
    """ "400 a night, and 250 a night for the workers" → what was SAVED, read back in €; planning starts; "show me the list" → the card."""

    def test_limits_read_back_from_storage_then_planning_starts(self):
        with W.World() as w:
            ctx = API.Ctx(account=OWNER, mode="test")
            run(API.group_upload(ctx, {"text": FIVE}))
            r = run(API.group_limits(ctx, {"by_grade": {"executive": {"hotel_night_eur": 400}, "worker": {"hotel_night_eur": 250}}}))
            run(asyncio.sleep(0))
            mv = run(G.store().movement(OWNER))
        self.assertEqual(r["say"].split(" I'm")[0], "Saved: executive: €400 a night; worker: €250 a night.")   # FROM storage, in €
        self.assertEqual(mv["rules"]["limits"]["by_grade"]["executive"], {"hotel_night_eur": 400.0})
        self.assertTrue(r["planning"])
        self.assertIn("I'm planning all 5 now", r["say"])                                       # the next step, started
        self.assertNotIn("$", r["say"])

    def test_by_person_read_back_by_name(self):
        with W.World():
            ctx = API.Ctx(account=OWNER, mode="test")
            run(API.group_upload(ctx, {"text": FIVE}))
            r = run(API.group_limits(ctx, {"by_person": {"Dee Worker": {"hotel_night_eur": 250, "flight_return_eur": 300}}}))
        self.assertIn("Dee Worker: €250 a night and €300 for the return flight", r["say"])

    def test_show_me_the_list_is_the_card_or_says_nobody_is_planned(self):
        with W.World():
            ctx = API.Ctx(account=OWNER, mode="test")
            run(API.group_upload(ctx, {"text": FIVE}))
            before = run(API.group_list(ctx, {}))
            ev_before = S.render("group_list", before, {})
            run(G.plan(OWNER))
            after = run(API.group_list(ctx, {}))
            ev = S.render("group_list", after, {})
        self.assertEqual(before["say"], "Nobody is planned yet — 5 on the list, not planned.")     # said plainly
        self.assertEqual((ev_before["kind"], ev_before["empty"]), ("group_list", before["say"]))
        self.assertEqual((ev["kind"], len(ev["rows"]), ev["link"]), ("group_list", 5, "/group"))   # the list goes out WITH the list
        self.assertIn("group_list", S.KINDS_S2_ONLY)
        self.assertIn("group_list", V.SHOWS)


class TheGuard(unittest.TestCase):
    def test_a_figure_in_another_currency_must_be_a_tools_in_that_currency(self):
        self.assertTrue(S.guard_check("The hotel limit works out at $729.", {729.0, 400.0, 250.0}, False))
        self.assertTrue(S.guard_check("That's £300 a night.", {300.0}, False))
        self.assertEqual(S.guard_check("Saved: worker: €250 a night.", {250.0}, False), [])
        self.assertEqual(S.guard_check("That fare is $729.", set(), False, other={("USD", 729.0)}), [])
        out = set()
        S._currencies({"price": {"amount_minor": 72900, "currency": "USD"}}, out)
        self.assertIn(("USD", 729.0), out)

    def test_the_phrase_guard_is_retired(self):   # Sasha 349 · one payload per reply (sasha.draws + on_screen), no phrase guard
        self.assertFalse(hasattr(V, "promises_card"))


class OneMovementPerTrip(unittest.TestCase):
    def test_six_starts_one_movement(self):
        with W.World() as w:
            ids = {run(G.start(OWNER, "Jean Incorporated", "London", "2026-11-17", "2026-11-21", "near Canary Wharf"))["movement_id"] for _ in range(6)}
            other = run(G.start(OWNER, "Jean Incorporated", "London", "2026-12-01", "2026-12-05", "near Canary Wharf"))["movement_id"]
        self.assertEqual(len(ids), 1)
        self.assertNotIn(other, ids)                                                             # another trip: its own movement


PG, _SERVER = os.getenv("BOOKING_TEST_DATABASE_URL", ""), None
if not PG:
    try:
        import pgserver
        _SERVER = pgserver.get_server(tempfile.mkdtemp(prefix="s345pg"), cleanup_mode="stop")
        PG = _SERVER.get_uri()
    except Exception:
        PG = ""


@unittest.skipUnless(PG, "no real Postgres — the rules proof did NOT run")
class RulesAreAnObjectOnPostgres(unittest.TestCase):
    def test_set_rules_round_trips_as_an_object_and_052_repairs(self):
        import asyncpg
        from tests.test_s336_keep_owners import _block
        loop = asyncio.new_event_loop()
        go = loop.run_until_complete
        db = "s345_" + uuid.uuid4().hex[:8]
        admin = go(asyncpg.connect(PG)); go(admin.execute(f"create database {db}")); go(admin.close())
        c = go(asyncpg.connect(PG, database=db))
        go(c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"))   # production's pool init
        try:
            for role in ("anon", "authenticated"):
                go(c.execute(f"do $$ begin create role {role}; exception when duplicate_object then null; end $$"))
            go(c.execute("create schema if not exists auth; create table auth.users (id uuid primary key); create table public.trips (id uuid primary key)"))
            go(c.execute(_block("048_group_movement.sql")))
            owner = uuid.uuid4()
            go(c.execute("insert into auth.users values ($1)", owner))

            async def runner(fn):
                return await fn(c)
            st = G.PgStore(runner)
            mid = go(st.new_movement(str(owner), "Jean Incorporated", "London", "2026-11-17", "2026-11-21", None))
            go(c.execute("update group_movements set rules = $1::jsonb", json.dumps({"limits": {"old": 1}})))   # the old write: a string
            self.assertEqual(go(c.fetchval("select jsonb_typeof(rules) from group_movements")), "string")
            go(c.execute(_block("052_group_rules_repair.sql"))); go(c.execute(_block("052_group_rules_repair.sql")))
            self.assertEqual(go(c.fetchval("select jsonb_typeof(rules) from group_movements")), "object")
            go(st.set_rules(str(owner), mid, {"limits": {"by_grade": {"worker": {"hotel_night_eur": 250.0}}}}))
            self.assertEqual(go(c.fetchval("select jsonb_typeof(rules) from group_movements")), "object")              # the new write
            self.assertEqual(go(c.fetchval("select rules #>> '{limits,by_grade,worker,hotel_night_eur}' from group_movements")), "250.0")
            self.assertEqual(go(st.movement(str(owner)))["rules"]["limits"]["by_grade"]["worker"]["hotel_night_eur"], 250.0)
        finally:
            go(c.close())
            admin = go(asyncpg.connect(PG)); go(admin.execute(f"drop database if exists {db}")); go(admin.close())
            loop.close()


def tearDownModule():
    if _SERVER is not None:
        try:
            _SERVER.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
