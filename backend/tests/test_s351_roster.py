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


class OneVaultFold(unittest.TestCase):
    def test_a_second_copy_folds_into_the_person_newest_per_kind(self):
        with V.World() as w:
            m = w.members()[0]
            copy = str(uuid.uuid4())
            P = lambda n: {"number": n, "country": "ES", "expires_on": "2031-05-01", "name": "TEST", "born_on": "1990-01-01"}
            run(KEEP.put(copy, "passport", P("CPOLD0001")))
            run(KEEP.put(copy, "loyalty", {"program": "Iberia Plus", "number": "IB00351"}))
            run(KEEP.put(m["person_id"], "passport", P("PSNEW0002")))
            w.keep.copies = {copy: m["person_id"]}
            r = run(KEEP.fold_second_copies())
            self.assertEqual((r["copies"], r["moved"], r["left"]), (1, 1, 0))
            kinds = sorted(i["type"] for i in run(KEEP.list_(m["person_id"])))
            self.assertEqual(kinds, ["loyalty", "passport"])                                # one per kind
            self.assertEqual(run(KEEP.list_(copy)), [])                                     # the copy shredded, key and all
            self.assertIsNone(run(w.keep.key(copy)))


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


class TheModelIsToldTheRoster(unittest.TestCase):
    """Found live (6 Nov): "Then ask for the list" made the model ask for every person's details again, and one named person went
    through the LIST path (which asked for her dates). The tool registry is the one source of what the model is told."""

    def test_the_tools_say_roster_never_re_type(self):
        from agapi import v0 as API
        d = {t["name"]: t["description"] for t in API.TOOLS}
        self.assertNotIn("ask for the list", d["group_start"])
        self.assertIn("ROSTER", d["group_start"])
        self.assertIn("group_person_add", d["group_upload"])
        self.assertIn("group_choose", d["group_person_add"])


PG, _SERVER = os.getenv("BOOKING_TEST_DATABASE_URL", ""), None
if not PG:
    try:
        import pgserver   # a real Postgres, local and throwaway — this module's own
        _SERVER = pgserver.get_server(tempfile.mkdtemp(prefix="s351pg"), cleanup_mode="stop")
        PG = _SERVER.get_uri()
    except Exception:
        PG = ""


@unittest.skipUnless(PG, "no real Postgres (BOOKING_TEST_DATABASE_URL / pgserver) — the migration proof did NOT run")
class MigrationOnPostgres(unittest.TestCase):
    """053 on real Postgres: duplicated per-trip rows → one person each, the vault moved to the person, every row archived."""

    def test_053_dedupes_moves_the_vault_and_loses_nothing(self):
        import asyncpg
        from tests import test_s336_keep_owners as KO
        blk = KO._block
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

            # ── ONE vault per person: the second copies (vaults still owned by old trip rows) → 054 archive → the fold → 055 ──
            from agapi import keep as K
            kms = K.LocalKms(b"\x05" * 32)

            async def runc(fn):
                return await fn(c)

            async def no_owner_row(self, account):   # the copies' owner rows are made by hand below, as 050 made them before 053
                return None
            luis_person = go(c.fetchval("select id from public.group_people where name = 'Luis Pérez'"))
            P = lambda n: {"number": n, "country": "ES", "expires_on": "2031-05-01", "name": "TEST", "born_on": "1990-01-01"}
            with mock.patch.object(KEEP, "STORE", KEEP.PostgresKeepStore(runc)), mock.patch("booking_signer.vault.kms.kek", lambda: kms), \
                    mock.patch.object(KEEP.PostgresKeepStore, "ensure_owner", no_owner_row), mock.patch("agapi.s2_records.RUN", None):
                for copy in (ids[0], ids[2]):
                    go(c.execute("insert into public.keep_owners (id, member_id) values ($1, $1)", copy))
                go(c.execute("insert into public.keep_owners (id, person_id) values ($1, $1) on conflict do nothing", luis_person))
                go(KEEP.put(str(ids[0]), "passport", P("AAOLD0001")))                       # Ana's copy: OLDER than her own
                go(KEEP.put(str(ids[0]), "loyalty", {"program": "Iberia Plus", "number": "IB00351"}))   # a kind only the copy has
                go(KEEP.put(str(ids[1]), "passport", P("AANEW0002")))                       # Ana's own: newer → kept
                go(KEEP.put(str(luis_person), "passport", P("LUOLD0003")))                  # Luis's own: older
                go(KEEP.put(str(ids[2]), "passport", P("LUNEW0004")))                       # Luis's copy: NEWER → moved to him
                items_before = go(c.fetchval("select count(*) from keep_items"))
                with self.assertRaises(Exception):
                    go(c.execute(blk("055_keep_owners_no_member.sql")))                     # refuses while copies remain
                go(c.execute("rollback"))
                go(c.execute(blk("054_vault_copies_archive.sql")))
                self.assertEqual(go(c.fetchval("select count(*) from keep_items_archive_351b")), items_before)   # archived FIRST, all of it
                r = go(KEEP.fold_second_copies())
                self.assertEqual((r["copies"], r["moved"], r["left"]), (2, 2, 0))
                self.assertEqual(go(KEEP.fold_second_copies())["copies"], 0)                # idempotent
                go(c.execute(blk("055_keep_owners_no_member.sql")))
                go(c.execute(blk("055_keep_owners_no_member.sql")))                          # idempotent

                def opened(owner):
                    out = {}
                    for it in go(KEEP._store().items_of(str(owner))):
                        dek = go(KEEP._dek(str(owner), create=False))
                        out[it["type"]] = K.open_(dek, K.item_aad(str(owner), str(owner), str(it["id"]), it["type"]), bytes(it["nonce"]),
                                                  bytes(it["ciphertext"]))["number"]
                    return out
                self.assertEqual(opened(ids[1]), {"passport": "AANEW0002", "loyalty": "IB00351"})   # one per kind, the newest
                self.assertEqual(opened(luis_person), {"passport": "LUNEW0004"})
                self.assertEqual(go(c.fetchval("select count(*) from keep_keys where account_id = any($1::uuid[])", [ids[0], ids[2]])), 0)
                self.assertEqual(go(c.fetchval("select count(*) from information_schema.columns where table_name = 'keep_owners' "
                                               "and column_name = 'member_id'")), 0)
            link = go(c.fetchval("select id from public.group_members where person_id = $1 and id <> $1 limit 1", luis_person))
            with mock.patch.object(KEEP, "STORE", KEEP.PostgresKeepStore(runc)), mock.patch("booking_signer.vault.kms.kek", lambda: kms), \
                    mock.patch("agapi.s2_records.RUN", None), self.assertRaises(KEEP.KeepError) as e:
                go(KEEP.put(str(link), "passport", P("ZZ0000001")))                         # a trip's row never owns a vault again
            self.assertEqual(e.exception.rule, "keep_owner_unknown")
        finally:
            go(c.close())
            admin = go(asyncpg.connect(PG))
            go(admin.execute(f"drop database if exists {db}"))
            go(admin.close())
            loop.close()


def tearDownModule():
    if _SERVER is not None:
        _SERVER.cleanup()


if __name__ == "__main__":
    unittest.main()
