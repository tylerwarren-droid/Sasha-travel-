"""CR 54 · CampusMe as Sasha's first skill — the seven AgAPI tools, the visits in the basket, the skill switch, the guards.

Every school read is served from the saved reads (tests/fixtures/campusme, tests/fixtures/cr38) through the same paced Reader:
no request leaves this machine. The hand-over is never opened for real: the cloud browser is stubbed where a test needs it.
The Postgres half (035_basket_visits.sql on the real table) runs when BOOKING_TEST_DATABASE_URL names a test database.

    cd backend && python -m unittest tests.test_campus_skill_cr54 -v
"""
from __future__ import annotations

import asyncio
import os
import re
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest import mock

from agapi import campus as C, skills as K, v0 as V0
from booking_signer import basket as BK, basket_visits as BV, handover as HO, plan_store as PS
from products import store as ST
from products.campus import slate as SL

HERE = Path(__file__).parent
FX1, FX38 = HERE / "fixtures" / "campusme", HERE / "fixtures" / "cr38"
SQL = HERE.parent / "booking_signer" / "sql"
ACCOUNT = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
TOUR_WEEK = "2026-11-15"                       # the week the cr38 reads cover (Yale 15–17 Nov, Brown 16–17 Nov)
FAMILY = {"parent_name": "Padre Ejemplo", "student_name": "Prueba Sasha", "email": "prueba@example.com", "mobile": "202 555 0123",
          "high_school": "Kanoe Test High School", "grad_year": "2027", "major": "Engineering", "birthdate": "14 March 2009",
          "address": "100 Example Street, Princeton, NJ 08540", "party": "3"}


def run(c):
    return asyncio.run(c)


class Web:
    """The schools' hosts, from the saved reads. Every request is recorded — a POST (a submit) would show here."""

    def __init__(self):
        self.calls = []

    async def __call__(self, method, url, form):
        self.calls.append((method, url))
        if url.endswith("/robots.txt"):
            return 200, "User-agent: *\nDisallow:\n"
        if "apps.admissions.yale.edu" in url and "cmd=event_dates" in url:
            return 200, (FX1 / "yale-dates-2026-10.json").read_text()
        for school, host in (("yale", "apps.admissions.yale.edu"), ("brown", "apply.college.brown.edu")):
            if host in url and "cmd=event_list" in url:
                day = url.split("date=")[1][:10]
                for fx in (FX38 / f"{school}-list-{day}.html", FX1 / f"{school}-list-{day}.html"):
                    if fx.exists():
                        return 200, fx.read_text()
                return 200, "<html></html>"
        return 404, "not found"


class Base(unittest.TestCase):
    def setUp(self):
        self.web = Web()
        self.saved = (SL.READER, ST.STORE, BV.STORE, PS.save, C._IDEM.copy())
        SL.READER = SL.Reader(self.web, pace=0)
        ST.STORE = ST.MemoryCaseStore()
        BV.STORE = BV.MemoryVisits()
        self.trips = []

        async def save(account, itinerary, message, now):
            self.trips.append((account, itinerary))
            return str(uuid.uuid4())
        PS.save = save

        async def travel(o, d, depart, mode):
            return 3 * 3600 + 13 * 60 if "Princeton" in o else 2 * 3600 + 5 * 60
        self.p_travel = mock.patch("booking_signer.proactive.travel", travel)
        self.p_travel.start()
        self.p_today = mock.patch.object(C, "_today", lambda: date(2026, 10, 8))
        self.p_today.start()
        self.ctx = V0.Ctx(account=ACCOUNT)
        self.results = []

    def tearDown(self):
        self.p_travel.stop()
        self.p_today.stop()
        SL.READER, ST.STORE, BV.STORE, PS.save, idem = self.saved
        C._IDEM.clear()
        C._IDEM.update(idem)

    def call(self, name, ctx=None, **args):
        t = C.BY_NAME.get(name)
        if t and t["idempotent"] and "idempotency_key" not in args:
            args["idempotency_key"] = uuid.uuid4().hex
        r = run(C.call(ctx or self.ctx, name, args))
        self.results.append(r)
        return r

    def ok(self, name, **args):
        r = self.call(name, **args)
        self.assertTrue(r["ok"], r)
        return r["result"]

    def tour(self, schools=("Yale", "Brown")):
        return self.ok("plan_tour", schools=list(schools), week_of=TOUR_WEEK, party=3)

    def student(self):
        return self.ok("save_student", details=FAMILY)

    def posts(self):
        return [u for m, u in self.web.calls if m != "GET"]


class Tools(Base):
    def test_find_schools_names_read_and_unread_with_their_own_pages(self):
        r = self.ok("find_schools", text="Yale, Brown and Princeton in November")
        by = {s["school"]: s for s in r["schools"]}
        self.assertEqual(set(by), {"yale", "brown", "princeton"})
        self.assertTrue(by["yale"]["calendar_read"])
        self.assertFalse(by["princeton"]["calendar_read"])
        self.assertIn("refuses AI agents", by["princeton"]["why_not_read"])
        self.assertEqual(by["princeton"]["visit_page"], "https://apply.princeton.edu/portal/tours_info")
        self.assertTrue(all(s["url"] for s in r["sources"]))
        self.assertEqual(self.call("find_schools", text="a trip to Lisbon")["error"]["code"], "no_school_named")

    def test_find_visit_sessions_reads_the_schools_own_calendar(self):
        r = self.ok("find_visit_sessions", school="Yale", start_date="2026-10-14", end_date="2026-10-14")
        self.assertTrue(r["sessions"])
        s = r["sessions"][0]
        self.assertRegex(s["start"], r"^\d{2}:\d{2}$")
        self.assertTrue(s["register_page"].startswith("https://apps.admissions.yale.edu/"))
        self.assertEqual(r["sources"][0]["label"], "Yale's own visit calendar")
        self.assertTrue(any("/robots.txt" in u for _, u in self.web.calls))          # robots first
        self.assertEqual(self.posts(), [])
        self.assertEqual(self.call("find_visit_sessions", school="Princeton", start_date="2026-11-16")["error"]["code"],
                         "site_refuses_agents")                                     # never read: it refuses AI agents
        self.assertEqual(self.call("find_visit_sessions", school="Hogwarts", start_date="2026-11-16")["error"]["code"], "school_unknown")
        self.assertEqual(self.call("find_visit_sessions", school="Yale", start_date="16/11/2026")["error"]["code"], "start_date_invalid")

    def test_plan_tour_from_the_reads_lands_as_suggested_visits(self):
        r = self.tour(("Yale", "Brown", "Princeton"))
        self.assertEqual({v["school"] for v in r["visits"]}, {"yale", "brown", "princeton"})
        self.assertTrue(all(v["state"] == "suggested" for v in r["visits"]))
        yale = next(v for v in r["visits"] if v["school"] == "yale")
        self.assertTrue(yale["time_from_school"])
        prin = next(v for v in r["visits"] if v["school"] == "princeton")
        self.assertFalse(prin["time_from_school"])
        self.assertIsNone(prin["start"])                                             # never a guessed time
        self.assertTrue(r["days"] and all(re.match(r"^[A-Z][a-z]{2} \d", d) for d in r["days"]))
        self.assertIn("Google Routes (driving)", [s["label"] for s in r["sources"]])
        rows = run(BV.items(ACCOUNT))
        self.assertEqual(len(rows), 3)
        self.assertEqual({x["state"] for x in rows}, {"suggested"})
        self.assertEqual(run(BV.items(OTHER)), [])                                    # scoped to the account
        self.assertEqual(self.trips[0][1]["kanoe"], "campus-tour/1")                   # the journey, as today's tour saves it

    def test_plan_tour_refuses_honestly(self):
        self.assertEqual(self.call("plan_tour", schools=["Yale"], week_of="2026-09-01")["error"]["code"], "week_of_past")
        self.assertEqual(self.call("plan_tour", schools=["Narnia U"], week_of=TOUR_WEEK)["error"]["code"], "school_unknown")
        self.assertEqual(self.call("plan_tour", week_of=TOUR_WEEK)["error"]["code"], "missing_input")

    def test_save_student_checks_each_answer_and_says_what_is_missing(self):
        r = self.ok("save_student", details={"student_name": "Prueba Sasha", "email": "not-an-email", "grad_year": "2027"})
        self.assertIn("student_name", r["saved"])
        self.assertEqual([i["field"] for i in r["invalid"]], ["email"])
        self.assertIn("email", r["missing"])
        r = self.student()
        self.assertEqual(r["missing"], [])

    def test_prepare_registration_without_details_refuses(self):
        v = self.tour()["visits"][0]
        self.assertEqual(self.call("prepare_registration", visit_id=v["visit_id"])["error"]["code"], "student_details_missing")

    def test_a_guest_without_the_dpa_gets_the_schools_own_page_never_a_fill(self):
        v = next(x for x in self.tour()["visits"] if x["school"] == "yale")
        self.student()
        opened = mock.AsyncMock()
        with mock.patch.dict(os.environ, {"BROWSERBASE_API_KEY": "test-key"}), mock.patch.object(HO, "dpa_ok", lambda a: False), \
                mock.patch("products.campus.tour.open_live", opened):
            r = self.ok("prepare_registration", visit_id=v["visit_id"])
        opened.assert_not_called()                                                   # the cloud browser never opened
        self.assertFalse(r["filled"])
        self.assertEqual(r["handoff"]["kind"], "link")
        self.assertTrue(r["handoff"]["url"].startswith("https://apps.admissions.yale.edu/"))
        self.assertIn("signed data agreement", r["handoff"]["why"])
        self.assertIn("prueba@example.com", r["copy"])
        self.assertEqual(run(BV.get(ACCOUNT, v["visit_id"]))["state"], "suggested")  # nothing prepared by us

    def test_a_pattern_school_is_never_filled(self):
        v = next(x for x in self.tour(("Princeton",))["visits"])
        self.student()
        r = self.ok("prepare_registration", visit_id=v["visit_id"])
        self.assertFalse(r["filled"])
        self.assertEqual(r["handoff"]["url"], "https://apply.princeton.edu/portal/tours_info")

    def test_prepare_registration_fills_stops_before_submit_and_hands_over_to_the_phone(self):
        v = next(x for x in self.tour()["visits"] if x["school"] == "yale")
        self.student()
        rec = {"id": "ho-1", "token": "t0k", "venue": "Yale"}
        with mock.patch.dict(os.environ, {"BROWSERBASE_API_KEY": "test-key"}), mock.patch.object(HO, "dpa_ok", lambda a: True), \
                mock.patch("products.campus.tour.open_live", mock.AsyncMock(return_value=rec)) as opened, \
                mock.patch.object(HO, "tap_phone", mock.AsyncMock(return_value={"sent": True})):
            r = self.ok("prepare_registration", visit_id=v["visit_id"])
        kw = opened.call_args
        self.assertEqual(kw.args[0], "yale")
        self.assertNotIn("fictional", kw.kwargs)                                      # the caller can never mark a student fictional
        self.assertTrue(r["filled"])
        self.assertEqual(r["state"], "prepared")
        self.assertEqual(r["handoff"]["kind"], "handover")
        self.assertTrue(r["handoff"]["sent_to_phone"])
        self.assertIn("/api/booking/handover/ho-1?t=t0k", r["handoff"]["url"])
        self.assertTrue(any("Submit" in x for x in r["left_for_you"]))
        self.assertTrue(any("statement box" in x for x in r["left_for_you"]))
        self.assertEqual(self.posts(), [])

    def test_a_refused_hand_over_is_said_in_plain_words(self):
        v = next(x for x in self.tour()["visits"] if x["school"] == "yale")
        self.student()
        refused = HO.Refused("captcha_on_page", "the school's form shows a CAPTCHA, which only you can answer — here's its page")
        with mock.patch.dict(os.environ, {"BROWSERBASE_API_KEY": "test-key"}), mock.patch.object(HO, "dpa_ok", lambda a: True), \
                mock.patch("products.campus.tour.open_live", mock.AsyncMock(side_effect=refused)):
            r = self.call("prepare_registration", visit_id=v["visit_id"])
        self.assertEqual(r["error"], {"code": "captcha_on_page", "message": refused.say})

    def test_registered_only_from_the_schools_own_confirmation(self):
        v = next(x for x in self.tour()["visits"] if x["school"] == "yale")
        self.student()
        when = date.fromisoformat(v["date"])
        h, m = map(int, v["start"].split(":"))
        clock = f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
        wrong = f"Thank you for registering, Prueba! Yale University Campus Tour on December 2, {when.year} at {clock}."
        r = self.ok("check_confirmation", visit_id=v["visit_id"], text=wrong)
        self.assertFalse(r["confirmed"])
        self.assertEqual(r["state"], "not_confirmed")
        self.assertTrue(r["mismatches"])
        good = (f"Thank you for registering, Prueba! We look forward to seeing you at Yale University on "
                f"{when.strftime('%B')} {when.day}, {when.year} at {clock}. Confirmation number: YL-48213.")
        r = self.ok("check_confirmation", visit_id=v["visit_id"], text=good)
        self.assertTrue(r["confirmed"])
        self.assertEqual((r["state"], r["number"]), ("registered", "YL-48213"))
        self.assertTrue(r["status_line"].startswith("Registered ✓ — Yale"))
        g = self.ok("get_campus")
        self.assertTrue(g["anything_registered"])
        self.assertEqual(next(x for x in g["visits"] if x["visit_id"] == v["visit_id"])["number"], "YL-48213")
        self.assertEqual(self.call("prepare_registration", visit_id=v["visit_id"])["error"]["code"], "already_registered")

    def test_every_visit_is_the_accounts_own(self):
        v = self.tour()["visits"][0]
        other = V0.Ctx(account=OTHER)
        self.assertEqual(self.call("check_confirmation", ctx=other, visit_id=v["visit_id"], text="registered")["error"]["code"],
                         "visit_not_found")
        self.assertEqual(self.ok("get_campus", ctx=other)["visits"], [])

    def test_austen_calls_are_idempotent(self):
        a = self.call("save_student", details={"student_name": "Prueba Sasha"}, idempotency_key="same-key-123")
        b = self.call("save_student", details={"student_name": "Other Name"}, idempotency_key="same-key-123")
        self.assertTrue(b.get("replayed"))
        self.assertEqual(a["result"], b["result"])

    def test_the_contract(self):
        self.assertEqual(self.call("prepare_registration", visit_id="x", idempotency_key="k" * 10, fictional=True)["error"]["code"],
                         "unknown_input")                                            # "fictional" is no input of ours
        self.assertEqual(self.call("nope")["error"]["code"], "unknown_tool")
        live = V0.Ctx(account=ACCOUNT, mode="live")
        self.assertEqual(self.call("get_campus", ctx=live)["error"]["code"], "mode_not_available")
        with mock.patch("products.campus.tour.schedule", mock.AsyncMock(side_effect=RuntimeError("Traceback at 0x7f…"))):
            r = self.call("plan_tour", schools=["Yale"], week_of=TOUR_WEEK)
        self.assertEqual(r["error"]["code"], "internal")
        self.assertNotIn("RuntimeError", r["error"]["message"])                    # no internals in what the person reads
        for t in C.TOOLS:
            m = C.tools_for_model()[[x["name"] for x in C.TOOLS].index(t["name"])]
            self.assertNotIn("idempotency_key", m["input_schema"]["properties"])     # the caller fills it, never the model
            self.assertTrue(t["output_schema"] and t["description"])


class Guards(Base):
    FORBIDDEN = {"submit", "sign", "send", "create", "account", "register", "file", "lodge", "tick", "pay", "book", "email",
                 "call", "consent", "accept"}

    def test_no_tool_submits_signs_sends_or_creates_an_account(self):
        names = [t["name"] for t in C.TOOLS] + [t["name"] for t in K.tools("campus")]
        for n in names:
            self.assertFalse(set(n.split("_")) & self.FORBIDDEN, n)
        for t in C.TOOLS:
            self.assertNotRegex(t["description"], r"(?i)\b(?:we|sasha|it|campusme) (?:submits?|signs?|sends?|registers?|ticks?)\b")
            self.assertNotRegex(t["description"], r"(?i)\bcreates? an account\b")
        self.assertEqual(len(C.TOOLS), 7)

    def test_registered_only_once_recorded(self):
        visits = [{"name": "Yale", "state": "prepared"}, {"name": "Brown", "state": "suggested"}]
        self.assertTrue(C.guard_check("You're registered for Yale on Monday.", [], visits))
        self.assertTrue(C.guard_check("Registration confirmed ✅", [], visits))
        visits[0]["state"] = "registered"
        self.assertEqual(C.guard_check("You're registered for Yale on Monday.", [], visits), [])
        self.assertTrue(C.guard_check("You're registered for Brown too.", [], visits))   # only the school that confirmed
        self.assertEqual(C.guard_check("Yale is filled — press its Submit on your phone.", [], visits), [])

    def test_figures_only_from_the_tools(self):
        r = self.tour(("Yale", "Brown", "Princeton"))
        yale = next(v for v in r["visits"] if v["school"] == "yale")
        h, m = map(int, yale["start"].split(":"))
        clock = f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
        ok = f"Yale at {clock}, then a 3 h 13 drive."
        self.assertEqual(C.guard_check(ok, self.results, []), [], ok)
        bad = C.guard_check("Yale at 6:45 AM, $25 a person, 7 spaces left, a 5 h 50 drive.", self.results, [])
        self.assertEqual(len(bad), 4, bad)
        self.assertEqual(C.guard_check("Nothing to pay — visits are free to register.", self.results, []), [])


class Skills(Base):
    def test_opened_and_closed_only_by_the_word_or_the_tap(self):
        t = run(K.resolve(ACCOUNT, "plan a trip to visit Yale"))
        self.assertIsNone(t.skill)                                                   # Sasha can't open it on her own
        t = run(K.resolve(ACCOUNT, "campus"))
        self.assertEqual((t.skill, t.said, t.consumed), ("campus", "Let's plan your campus tour.", True))
        t = run(K.resolve(ACCOUNT, "book my flights"))
        self.assertEqual((t.skill, t.said), ("campus", None))                         # inside, it stays
        t = run(K.resolve(ACCOUNT, "Sasha"))
        self.assertEqual((t.skill, t.said), (None, "Back to Sasha — your tour is kept."))
        t = run(K.resolve(ACCOUNT, "", tap="skill:campus"))
        self.assertEqual(t.skill, "campus")
        self.assertIsNone(run(K.current(OTHER)))                                      # per account

    def test_inside_a_skill_the_model_sees_only_its_tools(self):
        self.assertEqual({t["name"] for t in K.tools("campus")}, set(C.BY_NAME))
        self.assertTrue({"search_flights", "book"} <= {t["name"] for t in K.tools(None)})
        self.assertFalse(set(C.BY_NAME) & {t["name"] for t in K.tools(None)})
        r = run(K.call(self.ctx, "campus", "book", {}))
        self.assertEqual(r["error"]["code"], "unknown_tool")                          # outside the open skill: never run
        r = run(K.call(self.ctx, None, "plan_tour", {}))
        self.assertEqual(r["error"]["code"], "unknown_tool")

    def test_the_agents_rows_never_show_as_visits_or_reminders(self):
        from products import agenda as AG
        self.student()
        run(K.resolve(ACCOUNT, "campus"))
        self.assertEqual(run(AG.agenda(ACCOUNT, date(2026, 1, 1), date(2027, 12, 31))), [])
        self.assertEqual(run(ST.STORE.conversations(f"wa:{ACCOUNT}")), [])            # nothing under a channel's own key

    def test_offer_is_a_button_the_person_taps(self):
        self.assertEqual(K.offer("campus"), {"title": "Open CampusMe", "payload": "skill:campus"})


PG_URL = os.getenv("BOOKING_TEST_DATABASE_URL", "")


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(unittest.TestCase):
    """035_basket_visits.sql on the real table: the visit states, and the checks that keep them to visits."""

    @classmethod
    def setUpClass(cls):
        import asyncpg
        from urllib.parse import urlsplit
        if "test" not in urlsplit(PG_URL).path.lstrip("/"):
            raise unittest.SkipTest("refusing a database whose name does not contain 'test'")

        async def fresh():
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute("drop schema if exists auth cascade; drop schema public cascade; create schema public;")
                for r in ("anon", "authenticated"):
                    await c.execute(f"do $$ begin if not exists (select 1 from pg_roles where rolname = '{r}') then "
                                    f"create role {r} nologin; end if; end $$")
                await c.execute((HERE / "fixtures" / "model_a_live_2026-09-28.sql").read_text(encoding="utf-8"))
                for f in ("001_booking_storage.sql", "033_trip_basket.sql", "035_basket_visits.sql", "035_basket_visits.sql"):
                    await c.execute((SQL / f).read_text(encoding="utf-8"))   # 035 twice: it is idempotent
                cls.account = str(await c.fetchval("select id from auth.users limit 1"))
                cls.trip = str(await c.fetchval("insert into trips (owner_id, title) values ($1, 'Campus tour') returning id",
                                                uuid.UUID(cls.account)))
            finally:
                await c.close()
        asyncio.run(fresh())

    def setUp(self):
        async def runner(fn):
            import asyncpg
            c = await asyncpg.connect(PG_URL)
            try:
                return await fn(c)
            finally:
                await c.close()
        self.saved = (BK.STORE_RUN, BV.STORE)
        BK.STORE_RUN, BV.STORE = runner, None

    def tearDown(self):
        BK.STORE_RUN, BV.STORE = self.saved

    def test_visits_suggested_prepared_registered(self):
        v = {"school": "yale", "name": "Yale", "date": "2026-11-16", "start": "09:00", "end": "10:30", "title": "Campus Tour",
             "place": "Yale Visitor Center", "read": True, "link": "https://apps.admissions.yale.edu/register/?id=x"}
        self.assertIsInstance(BV.store(), BV.PostgresVisits)
        (i,) = run(BV.suggest(self.account, self.trip, [v], 3))
        r = run(BV.get(self.account, i))
        self.assertEqual((r["kind"], r["state"], r["provider_ref"], r["day"]), ("visit", "suggested", "yale", "2026-11-16"))
        self.assertEqual(r["starts_at"][:16], "2026-11-16T14:00")                    # 9:00 New York, stored in UTC
        self.assertEqual(run(BV.prepared(self.account, i, "ho-1"))["handover_id"], "ho-1")
        with self.assertRaises(BV.VisitError):
            run(BV.registered(self.account, i, None, "x", {"confirmed": False}))
        r = run(BV.registered(self.account, i, "YL-1", "Registered ✓ — Yale, Mon 16 Nov 9am, confirmation #YL-1", {"confirmed": True}))
        self.assertEqual((r["state"], r["booking_reference"]), ("registered", "YL-1"))
        with self.assertRaises(BV.VisitError) as e:
            run(BV.prepared(self.account, i, "ho-2"))
        self.assertEqual(e.exception.code, "visit_registered")
        self.assertIsNone(run(BV.get("44444444-4444-4444-8444-444444444444", i)))      # another account sees nothing

    def test_the_visit_states_belong_to_visits_only(self):
        import asyncpg

        async def bad():
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute("insert into trip_basket_items (trip_id, account_id, kind, state, provider) values ($1, $2, 'flight', "
                                "'registered', 'duffel')", uuid.UUID(self.trip), uuid.UUID(self.account))
            finally:
                await c.close()
        with self.assertRaises(asyncpg.CheckViolationError):
            run(bad())


if __name__ == "__main__":
    unittest.main()
