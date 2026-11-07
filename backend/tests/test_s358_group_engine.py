"""Sasha 358 · ONE GROUP ENGINE — the company's ROSTER + a trip's SELECTION — that every door uses (the /group page, its upload, [Go], and
the chat's group tools). Found (Tyler's dry run, 7 Nov 09:43–10:05): a new trip could only be started in the chat; "Add these" put all 20
straight ON the open trip; "✓ on it" was a label (nobody could be taken off); Edit → Save never answered; six "London 2026-11-17" trips,
three of them empty.

The engine (booking_signer/groups.py): the roster (group_people, with ROLE beside grade) and each trip's selection (the links, 351), changed
ONLY by set_on_trip(person, trip, on|off) and create_trip(destination, dates, area, selection). state() is what every view renders.

    cd backend && python -m unittest tests.test_s358_group_engine -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest

from booking_signer import group_outcome as GO, groups as G
from tests import test_s332 as W

run = asyncio.run
OWNER = W.OWNER
ROOT = pathlib.Path(__file__).resolve().parents[1]
CITIES = list(W.FARE)   # the fixture's priced home cities (fictional people)
COMPANY = "Acme Components (fictional)"


def _in_world(scenario):
    """The organiser's world (test_s332.World: the group in memory, fixture fares) entered first; the scenario runs in ONE loop (planning
    runs in the background on it)."""
    with W.World() as w:
        return run(scenario(w))


def _people(n=25):
    roles = ["engineer", "engineer", "executive", "technician", "sales"]
    return [{"name": f"Person {i:02d} (fictional)", "home_city": CITIES[i % 18], "grade": "worker" if i % 4 else "supervisor",
             "role": roles[i % 5]} for i in range(n)]


class Engine(unittest.TestCase):
    """roster 25 → new trip Lisbon → tick 12 → Go → planned from each home → one off (said) → one from the roster + one brand-new on."""

    def test_the_whole_walk(self):
        async def walk(w):
            if True:
                r = await GO.run(OWNER, "person_add", {"rows": _people(), "company": COMPANY})
                self.assertTrue(r["done"], r["say"])
                st = await G.state(OWNER)
                self.assertEqual(len(st["roster"]), 25)
                self.assertEqual({p["role"] for p in st["roster"]}, {"engineer", "executive", "technician", "sales"})   # ROLE beside grade
                ids = [p["id"] for p in st["roster"]][:12]
                # [Go]: creates, selects, plans — the ONE create path
                go = await GO.run(OWNER, "create", {"destination": "Lisbon", "starts_on": "2026-11-17", "ends_on": "2026-11-21",
                                                    "hotel_area": "near the client in Oeiras", "who": ids})
                self.assertTrue(go["done"], go["say"])
                self.assertIn("12", go["say"])
                await G.planned(OWNER)
                st = await G.state(OWNER)
                self.assertEqual(st["trip"]["destination"], "Lisbon")
                self.assertEqual(sorted(p["id"] for p in st["roster"] if p["on"]), sorted(ids))   # every switch IS the record
                self.assertEqual(len(st["list"]["rows"]), 12)
                self.assertTrue(all(r["status"] == "planned" or r["status"] == "needs vault" for r in st["list"]["rows"]))
                self.assertTrue(all(r["transport"] and r["transport"].split()[1].startswith(r["home_city"][:3].upper())
                                    for r in st["list"]["rows"]))                                  # each from their own home
                # one switched off: said, off the record, the roster keeps them
                off = await GO.run(OWNER, "switch", {"person": ids[0], "on": False})
                self.assertTrue(off["done"], off["say"])
                self.assertIn("off the Lisbon trip", off["say"])
                # one from the roster, one brand-new (onto the roster AND the trip, said)
                on = await GO.run(OWNER, "switch", {"person": [p["id"] for p in st["roster"]][20], "on": True})
                self.assertTrue(on["done"], on["say"])
                new = await GO.run(OWNER, "person_add", {"rows": [{"name": "Nadia Newcomer (fictional)", "home_city": "Porto",
                                                                   "grade": "worker", "role": "engineer"}], "on_trip": True})
                self.assertTrue(new["done"], new["say"])
                self.assertIn("roster and the Lisbon trip", new["say"])
                await G.planned(OWNER)
                st = await G.state(OWNER)
                self.assertEqual(len(st["roster"]), 26)
                self.assertEqual(sum(1 for p in st["roster"] if p["on"]), 13)
                self.assertEqual({p["id"] for p in st["roster"] if p["on"]}, {r["person_id"] for r in st["list"]["rows"]})
                self.assertFalse(next(p for p in st["roster"] if p["id"] == ids[0])["on"])
        _in_world(walk)

    def test_off_a_booked_trip_offers_cancel_and_keeps_them(self):
        async def go(w):
            if True:
                await GO.run(OWNER, "person_add", {"rows": _people(3), "company": COMPANY})
                ids = [p["id"] for p in (await G.state(OWNER))["roster"]]
                await GO.run(OWNER, "create", {"destination": "Lisbon", "starts_on": "2026-11-17", "ends_on": "2026-11-21", "who": ids})
                await G.planned(OWNER)
                for rows in w.trips.values():
                    for x in rows:
                        x["state"] = "booked"
                r = await GO.run(OWNER, "switch", {"person": ids[0], "on": False})
                self.assertFalse(r["done"])
                self.assertIn("booked", r["say"])
                self.assertEqual([a["tool"] for a in r.get("actions") or []], ["group_cancel"])     # Cancel offered (352)
                self.assertTrue(next(p for p in (await G.state(OWNER))["roster"] if p["id"] == ids[0])["on"])
        _in_world(go)

    def test_no_door_can_make_a_trip_with_nobody_on_it(self):
        """The ONE trip writer refuses a trip with nobody on it — [Go] with nobody ticked, names not on the roster, the chat without who,
        an upload in a new trip: nothing is made. The last one switched off ends the trip (said). Nothing is ever deleted on a read."""
        from agapi import v0 as API

        async def go(w):
            if True:
                await GO.run(OWNER, "person_add", {"rows": _people(2), "company": COMPANY})
                ids = [p["id"] for p in (await G.state(OWNER))["roster"]]
                before = len(w.store.movements)
                for who in ([], ["Nobody Atall"], None):
                    r = await G.create_trip(OWNER, COMPANY, "London", "2026-11-17", "2026-11-21", None, who)
                    self.assertIn("who's going", r["why"])
                r = await GO.run(OWNER, "create", {"destination": "London", "starts_on": "2026-11-17", "ends_on": "2026-11-21", "who": ["Nobody Atall"]})
                self.assertFalse(r["done"])
                self.assertIn("not on your roster: Nobody Atall", r["say"])
                await API.group_start(API.Ctx(account=OWNER), {"company": COMPANY, "destination": "London"})
                await GO.run(OWNER, "add", {"rows": G.read_text("Cy Example, Lisbon"), "on_trip": False})
                self.assertEqual(len(w.store.movements), before)                          # not one trip made by any of them
                for _ in range(3):
                    await G.state(OWNER); await G.trips(OWNER)
                self.assertEqual(len(w.store.movements), before)                          # and none deleted by reading (World's own is there)
                await GO.run(OWNER, "create", {"destination": "Lisbon", "starts_on": "2026-11-17", "ends_on": "2026-11-21", "who": [ids[0]]})
                await G.planned(OWNER)
                r = await GO.run(OWNER, "switch", {"person": ids[0], "on": False})       # the last one off: the trip ends, said
                self.assertIn("isn't kept", r["say"])
                self.assertNotIn("Lisbon", [t["destination"] for t in (await G.trips(OWNER))["trips"]])
        _in_world(go)

    def test_go_needs_who_and_where(self):
        async def go(w):
            if True:
                r = await GO.run(OWNER, "create", {"destination": "Lisbon", "starts_on": "2026-11-17", "ends_on": "2026-11-21", "who": []})
                self.assertFalse(r["done"])
                self.assertIn("who's going", r["say"])
                r = await GO.run(OWNER, "create", {"who": ["x"]})
                self.assertIn("where", r["say"])
        _in_world(go)

    def test_upload_in_a_new_trip_fills_the_roster_and_ticks_never_a_trip(self):
        async def go(w):
            if True:
                before = (await G.state(OWNER))["trip"]
                r = await GO.run(OWNER, "add", {"rows": G.read_text("Name, Home city, Role\nAna Example, Lisbon, engineer\nBo Example, Porto, sales"),
                                                "on_trip": False})
                self.assertTrue(r["done"], r["say"])
                self.assertEqual(len(r["people"]), 2)                                      # their ids: the page ticks them
                st = await G.state(OWNER)
                self.assertFalse(any(p["on"] for p in st["roster"]))                       # on NO trip until [Go]
                self.assertEqual((st["trip"] or {}).get("id"), (before or {}).get("id"))
                self.assertEqual({p["role"] for p in st["roster"]}, {"engineer", "sales"})
        _in_world(go)

    def test_edit_save_always_answers(self):
        async def go(w):
            if True:
                await GO.run(OWNER, "person_add", {"rows": _people(1), "company": COMPANY})
                pid = (await G.state(OWNER))["roster"][0]["id"]
                same = await GO.run(OWNER, "person_edit", {"person_id": pid, "fields": {}})          # nothing changed: still answered
                self.assertTrue(same["done"], same["say"])
                self.assertIn("Nothing changed", same["say"])
                r = await GO.run(OWNER, "person_edit", {"person_id": pid, "fields": {"home_airport": "opo", "role": "Engineer"}})
                self.assertTrue(r["done"], r["say"])
                p = (await G.state(OWNER))["roster"][0]
                self.assertEqual((p["home_airport"], p["role"]), ("OPO", "engineer"))
                bad = await GO.run(OWNER, "person_edit", {"person_id": pid, "fields": {"home_airport": "Porto airport"}})
                self.assertFalse(bad["done"])
                self.assertIn("home airport", bad["say"])
        _in_world(go)


class TheChatUsesTheEngine(unittest.TestCase):
    def test_start_without_who_makes_no_trip_with_who_it_does(self):
        from agapi import v0 as API

        async def go(w):
            if True:
                n0 = len((await G.trips(OWNER))["trips"])
                await GO.run(OWNER, "person_add", {"rows": _people(3), "company": COMPANY})
                ctx = API.Ctx(account=OWNER)
                r = await API.group_start(ctx, {"company": COMPANY, "destination": "Lisbon", "starts_on": "2026-11-17", "ends_on": "2026-11-21"})
                self.assertIn("Who's going", r["say"])
                self.assertEqual(len((await G.trips(OWNER))["trips"]), n0)                  # nothing made: who's going first
                names = [p["name"] for p in (await G.state(OWNER))["roster"]][:2]
                r = await API.group_start(ctx, {"company": COMPANY, "destination": "Lisbon", "starts_on": "2026-11-17",
                                                "ends_on": "2026-11-21", "who": names})
                self.assertIn("2", r["say"])
                await G.planned(OWNER)
                st = await G.state(OWNER)
                self.assertEqual((st["trip"]["destination"], sum(p["on"] for p in st["roster"])), ("Lisbon", 2))
        _in_world(go)


class OneSource(unittest.TestCase):
    def test_only_the_engine_changes_the_selection_or_makes_a_trip(self):
        """Whole class: the group store's writers of a trip and its selection (select / remove_member / new_movement / delete_movement)
        are called ONLY by the engine's own functions (create_trip, set_on_trip) — every door goes through them."""
        hits = []
        for d in ("booking_signer", "agapi", "products", "app"):
            for f in sorted((ROOT / d).rglob("*.py")):
                s = f.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(r"\b(?:st|store\(\)|self\.store|G\.store\(\))\.(select|remove_member|new_movement|delete_movement)\(", s):
                    fn = re.findall(r"\n(?:    )?(?:async )?def (\w+)", s[:m.start()])
                    owner = fn[-1] if fn else "?"
                    if f.name == "groups.py" and owner in ("create_trip", "set_on_trip"):
                        continue
                    hits.append(f"{f.relative_to(ROOT)}:{owner} .{m.group(1)}(")
        self.assertEqual(hits, [])

    def test_the_page_holds_no_logic_and_uses_the_one_component(self):
        fe = ROOT.parent / "frontend" / "app"
        page = (fe / "group" / "page.tsx").read_text()
        self.assertIn("GroupView", page)
        self.assertLess(len(page.splitlines()), 20)                                       # the page renders the component, nothing more
        comp = (fe / "components" / "group" / "GroupView.tsx").read_text()
        self.assertIn("/api/booking/group/state", comp)
        self.assertIn("/api/booking/group/switch", comp)
        self.assertIn("/api/booking/group/create", comp)
        self.assertIn('role="switch"', comp)
        self.assertNotIn("✓ on it", comp)                                                  # a switch, never a label
        # every press answers in words: a press that only changes the page (New trip, Edit) says what it did — never a bare "Edit…"
        for name in re.findall(r"press\('([^']+)', async \(\) => \{(.*?) \}\)\}", comp):
            self.assertIn("setSaid(", name[1], f"{name[0]}: a press that says nothing")
        self.assertEqual(sorted(n for n, _ in re.findall(r"press\('([^']+)', async \(\) => \{(.*?) \}\)\}", comp)), ["Edit", "New trip"])


PG, _SERVER = __import__("os").getenv("BOOKING_TEST_DATABASE_URL", ""), None
if not PG:
    try:
        import tempfile
        import pgserver
        _SERVER = pgserver.get_server(tempfile.mkdtemp(prefix="s358pg"), cleanup_mode="stop")
        PG = _SERVER.get_uri()
    except Exception:
        PG = ""


def tearDownModule():
    if _SERVER is not None:
        try:
            _SERVER.cleanup()
        except Exception:
            pass


@unittest.skipUnless(PG, "no real Postgres (BOOKING_TEST_DATABASE_URL / pgserver) — the SQL proof did NOT run")
class OnPostgres(unittest.TestCase):
    """059 on real Postgres (twice: idempotent), and the engine's store writes as Postgres runs them: the role kept; a trip deleted only
    while nobody is on it."""

    def test_059_and_the_stores_writes(self):
        import asyncpg
        import uuid
        from tests import test_s336_keep_owners as KO
        loop = asyncio.new_event_loop()
        go = loop.run_until_complete
        db = "s358_" + uuid.uuid4().hex[:8]
        admin = go(asyncpg.connect(PG)); go(admin.execute(f"create database {db}")); go(admin.close())
        c = go(asyncpg.connect(PG, database=db))
        try:
            for role in ("anon", "authenticated"):
                go(c.execute(f"do $$ begin create role {role}; exception when duplicate_object then null; end $$"))
            go(c.execute("create schema if not exists auth; create table auth.users (id uuid primary key)"))
            go(c.execute("create table public.trips (id uuid primary key)"))
            for f in ("036_s2_activity_whatsapp.sql", "037_keep.sql", "048_group_movement.sql", "049_traveller_vault.sql", "050_keep_owners.sql",
                      "053_group_roster.sql", "056_group_open_trip.sql", "059_group_role.sql", "059_group_role.sql"):
                go(c.execute(KO._block(f)))
            org = uuid.uuid4()
            go(c.execute("insert into auth.users (id) values ($1)", org))

            async def runc(fn):
                return await fn(c)
            st = G.PgStore(runc)
            mid = go(st.new_movement(str(org), COMPANY, "Lisbon", "2026-11-17", "2026-11-21", "Oeiras"))
            gid = go(st.company(str(org)))["id"]
            pid = go(st.add_person(gid, {"name": "Ana Example", "role": "engineer", "home_airport": "MAD"}))
            self.assertEqual(go(st.people(gid))[0]["role"], "engineer")
            with self.assertRaises(asyncpg.CheckViolationError):
                go(c.execute("update public.group_people set role = '' where id = $1", uuid.UUID(pid)))
            go(st.select(mid, [pid]))
            self.assertEqual(go(st.members(mid))[0]["role"], "engineer")
            self.assertFalse(go(st.delete_movement(str(org), mid)))                       # someone is on it: refused by the statement
            go(st.remove_member(mid, go(st.members(mid))[0]["id"]))
            self.assertFalse(go(st.delete_movement(str(uuid.uuid4()), mid)))              # another organiser's: never
            self.assertTrue(go(st.delete_movement(str(org), mid)))                        # nobody on it: not kept
            self.assertEqual(go(c.fetchval("select count(*) from public.group_movements")), 0)
        finally:
            go(c.close())
            admin = go(asyncpg.connect(PG)); go(admin.execute(f"drop database if exists {db}")); go(admin.close())
            loop.close()


if __name__ == "__main__":
    unittest.main()
