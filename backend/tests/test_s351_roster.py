"""Sasha 351 · THE ROSTER (docs/sasha/S-351-roster.md): a company's people are ONE standing roster; every trip is a SELECTION from it.

Offline (the group in memory, the Keep in memory, Sasha 333's world) plus the 053 migration on a real Postgres (pgserver) when present.

    cd backend && python -m unittest tests.test_s351_roster -v
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
import uuid
from unittest import mock

from agapi import s2_keep as KEEP
from booking_signer import group_outcome as GO, groups as G, traveller_vault as TV
from tests import test_s333 as V

run = asyncio.run
OWNER = V.OWNER
COMPANY = "Acme Components (fictional)"


def _roster(w):
    return [p for p in w.store.persons.values()]


class OnePersonOneRecord(unittest.TestCase):
    def test_the_list_becomes_the_roster_and_the_trip_only_links(self):
        with V.World() as w:
            ppl = _roster(w)
            self.assertEqual(len(ppl), 20)                                               # one person per worker
            links = w.members()
            self.assertEqual(len(links), 20)
            raw = w.store.rows[w.mid]
            for x in raw:                                                                # a link: person, movement, dates, trip — nothing copied
                self.assertEqual(set(x), {"id", "movement_id", "person_id", "trip_id", "out_date", "back_date"})
            self.assertEqual({x["person_id"] for x in raw}, {p["id"] for p in ppl})

    def test_a_second_trip_selects_the_same_people_never_copies(self):
        with V.World() as w:
            run(G.start(OWNER, COMPANY, "Lisbon", "2026-11-17", "2026-11-21", "near the client in Oeiras"))
            names = [p["name"] for p in _roster(w)][:3]
            r = run(G.choose(OWNER, names))
            self.assertEqual((r["selected"], r["on_trip"], r["unknown"], r["twice"]), (3, 3, [], []))
            self.assertEqual(len(_roster(w)), 20)                                        # the roster unchanged: no new people
            again = run(G.choose(OWNER, names))                                          # ticking them again: still one link each
            self.assertEqual((again["selected"], again["on_trip"]), (0, 3))
            # the list uploaded again onto this trip: the SAME people (by the organiser's own names), never new ones
            up = run(G.upload(OWNER, G.read_csv(V.W.FIX.read_bytes())[:5]))
            self.assertEqual(up["new_people"], 0)
            self.assertEqual(len(_roster(w)), 20)

    def test_unknown_and_ambiguous_names_are_said_never_guessed(self):
        with V.World() as w:
            gid = next(iter(w.store.groups))
            twin = _roster(w)[0]["name"]
            run(w.store.add_person(gid, {"name": twin, "home_city": "Sevilla"}))
            r = run(G.choose(OWNER, [twin, "Nobody Atall"]))
            self.assertEqual((r["selected"], r["twice"], r["unknown"]), (0, [twin], ["Nobody Atall"]))
            row = next(r for r in G.read_csv(V.W.FIX.read_bytes()) if r["name"] == twin)
            up = run(G.upload(OWNER, [row]))
            self.assertTrue(up["unclear"] and "roster" in up["ask"])


class OneVaultPerPerson(unittest.TestCase):
    def test_a_passport_saved_on_one_trip_serves_the_next_with_no_re_entry(self):
        with V.World() as w:
            ms = w.members()[:3]
            for i, m in enumerate(ms):
                w.fill(m, i)
            for m in ms:                                                                 # the vault is the PERSON's
                self.assertTrue(run(KEEP.list_(m["person_id"])))
                self.assertFalse(run(KEEP.list_(m["id"])) if m["id"] != m["person_id"] else False)
            run(G.start(OWNER, COMPANY, "Lisbon", "2026-11-17", "2026-11-21", "Oeiras"))
            run(G.choose(OWNER, [m["person_id"] for m in ms]))
            v = run(G.view(OWNER))
            self.assertEqual(len(v["rows"]), 3)
            self.assertTrue(all(r["vault"]["passport"] for r in v["rows"]))              # ✓ on trip 2: nothing typed again
            mails = len(w.mails)
            inv = run(GO.run(OWNER, "invite", {}))                                       # no one is asked for a passport they gave
            self.assertNotEqual(inv.get("done"), True)
            self.assertIn("all 3", inv["say"])
            self.assertEqual(len(w.mails), mails)

    def test_a_person_s_own_vault_link_needs_no_trip(self):
        with V.World() as w:
            p = _roster(w)[0]
            link = run(TV.person_link(OWNER, p["id"]))
            self.assertTrue(link)
            self.assertIsNone(run(TV.person_link(OWNER, str(uuid.uuid4()))))           # not theirs → no link


class AChangeIsWhatEveryTripReads(unittest.TestCase):
    def test_a_new_home_airport_is_what_the_next_plan_searches_from(self):
        with V.World() as w:
            p = _roster(w)[0]
            r = run(G.edit_person(OWNER, p["id"], {"home_airport": "svq"}))
            self.assertEqual(r["person"]["home_airport"], "SVQ")
            self.assertIn("couldn't be read", run(G.edit_person(OWNER, p["id"], {"home_airport": "Sevilla"}))["why"])
            m = next(x for x in w.members() if x["person_id"] == p["id"])
            self.assertEqual(m["home_airport"], "SVQ")                                  # every trip reads the person
            seen = []

            async def search(frm, to, day, limit=1):
                seen.append(frm)
                return {"cards": []}
            with mock.patch("booking_signer.travel.search", search):
                run(G._quote(m, {"destination": "Lisbon", "hotel_area": "Oeiras"}))
            self.assertEqual(seen[0], "SVQ")
            self.assertEqual(seen[1], "Lisbon")

    def test_people_added_by_name_and_city_are_checked_as_given(self):
        with V.World() as w:
            r = run(G.add_people(OWNER, [{"name": "Ana García", "home_city": "Madrid", "grade": "worker"},
                                         {"name": "Luis Pérez", "home_airport": "BCN", "email": "not-an-email"},
                                         {"name": "X"}]))
            self.assertEqual(r["added"], 1)
            self.assertEqual(len(r["unclear"]), 2)
            self.assertEqual(len(_roster(w)), 21)


@unittest.skipUnless(V.__name__ and __import__("tests.test_s336_keep_owners", fromlist=["PG"]).PG,
                     "no real Postgres (BOOKING_TEST_DATABASE_URL / pgserver) — the migration proof did NOT run")
class MigrationOnPostgres(unittest.TestCase):
    """053 on real Postgres: duplicated per-trip rows → one person each, the vault moved to the person, every row archived."""

    def test_053_dedupes_moves_the_vault_and_loses_nothing(self):
        import asyncpg
        from tests import test_s336_keep_owners as KO
        PG, blk = KO.PG, KO._block
        loop = asyncio.new_event_loop()
        go = loop.run_until_complete
        db = "s351_" + uuid.uuid4().hex[:8]
        admin = go(asyncpg.connect(PG))
        go(admin.execute(f"create database {db}"))
        go(admin.close())
        c = go(asyncpg.connect(PG, database=db))
        try:
            for role in ("anon", "authenticated"):
                go(c.execute(f"do $$ begin create role {role}; exception when duplicate_object then null; end $$"))
            go(c.execute("create schema if not exists auth; create table auth.users (id uuid primary key)"))
            go(c.execute("create table public.trips (id uuid primary key)"))
            for f in ("036_s2_activity_whatsapp.sql", "037_keep.sql", "048_group_movement.sql", "049_traveller_vault.sql", "050_keep_owners.sql"):
                go(c.execute(blk(f)))
            org = uuid.uuid4()
            go(c.execute("insert into auth.users (id) values ($1)", org))
            gid = go(c.fetchval("insert into public.groups (owner_id, name) values ($1, 'Obras Ejemplo SL') returning id", org))
            m1 = go(c.fetchval("insert into public.group_movements (group_id, destination) values ($1, 'Madrid') returning id", gid))
            m2 = go(c.fetchval("insert into public.group_movements (group_id, destination) values ($1, 'London') returning id", gid))
            rows = [(m1, "Ana García", "ana@example.test"), (m2, " ana garcía ", None), (m1, "Luis Pérez", None),
                    (m2, "Luis Pérez", "luis@example.test"), (m2, "Marta Ruiz", None)]
            ids = [go(c.fetchval("insert into public.group_members (movement_id, name, home_city, email) values ($1, $2, 'Madrid', $3) returning id",
                                 mv, n, e)) for mv, n, e in rows]
            go(c.execute("insert into public.keep_owners (id, member_id) values ($1, $1)", ids[1]))   # Ana's vault: her London row
            go(c.execute(blk("053_group_roster.sql")))
            go(c.execute(blk("053_group_roster.sql")))                                    # idempotent
            self.assertEqual(go(c.fetchval("select count(*) from public.group_people")), 3)
            self.assertEqual(go(c.fetchval("select count(*) from public.group_members")), 5)
            self.assertEqual(go(c.fetchval("select count(*) from public.group_members_archive_351")), 5)
            ana = go(c.fetchrow("select id, email from public.group_people where name ilike 'ana%'"))
            self.assertEqual(ana["id"], ids[1])                                           # the person IS the vault's id: nothing re-keyed
            self.assertEqual(ana["email"], "ana@example.test")                            # the contact given, kept
            self.assertEqual(go(c.fetchval("select person_id from public.keep_owners where id = $1", ids[1])), ids[1])
            self.assertEqual(go(c.fetchval("select count(*) from public.group_members where person_id is null")), 0)
            self.assertEqual(go(c.fetchval("select count(*) from public.group_members where name is not null or email is not null")), 0)
            luis = go(c.fetchval("select email from public.group_people where name = 'Luis Pérez'"))
            self.assertEqual(luis, "luis@example.test")
        finally:
            go(c.close())
            admin = go(asyncpg.connect(PG))
            go(admin.execute(f"drop database if exists {db}"))
            go(admin.close())
            loop.close()


if __name__ == "__main__":
    unittest.main()
