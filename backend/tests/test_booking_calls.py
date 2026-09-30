"""S-33 · the phone rung — the script, Bland's answer READ (never assumed), the reading, and the routes.

    cd backend && python -m unittest tests.test_booking_calls -v

Nothing here reaches Bland, a model or a phone: Bland is a fake that answers what each case needs, and the reader
is a fake returning what a model might. The route half runs against the in-memory store AND, when
BOOKING_TEST_DATABASE_URL names a throwaway database, against Postgres with sql/001 + 002 + 003 applied —
⚠ without that variable the Postgres half is SKIPPED, and says so.
"""
import asyncio
import json
import os
import pathlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import call_routes, calls as C, routes
from booking_signer.call_store import MemoryCallStore, PostgresCallStore
from booking_signer.store import PostgresStore

HERE = pathlib.Path(__file__).parent
SQL_DIR = HERE.parent / "booking_signer" / "sql"
PG_URL = os.getenv("BOOKING_TEST_DATABASE_URL", "")

MONDAY = datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc)
ENV = {"SASHA_BOOKING_KEY": "test-booking-key", "SASHA_CALL_SWEEP": "0", "SASHA_CALLS_ENABLED": "1", "BLAND_API_KEY": "test-key-not-real", "SASHA_TEST_CALL_NUMBER": "+351 912 000 000",
       "SASHA_TEST_CALL_LANGUAGE": "en", "SASHA_TEST_CALL_TIMEZONE": "Europe/Lisbon", "SASHA_CALLS_PER_DAY": "3"}
JOHNSON = {"venue": "test-line", "date": "2026-10-08", "time": "20:00", "party": 4, "name": "Anna Johnson"}


def run(coro):
    return asyncio.run(coro)


class R:
    """A fake HTTP response."""

    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeBland:
    def __init__(self, place=None, details=None):
        self.place_answer = place or R(200, {"status": "success", "message": "Call successfully queued.", "call_id": "bland-1"})
        self.details = details
        self.requests = []

    async def __call__(self, method, url, headers, json=None):
        self.requests.append((method, url, headers, json))
        if method == "POST":
            if isinstance(self.place_answer, Exception):
                raise self.place_answer
            return self.place_answer
        return R(200, self.details)


def done(*turns, status="completed", answered_by="human"):
    return {"completed": True, "status": status, "answered_by": answered_by,
            "transcripts": [{"user": u, "text": t} for u, t in turns]}


def reader_says(obj):
    async def r(_transcript):
        if isinstance(obj, Exception):
            raise obj
        return obj if isinstance(obj, str) else json.dumps(obj)
    return r


# ── 1 · the words ─────────────────────────────────────────────────────────────────────────────

class Script(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_the_founders_opening_sentence(self):
        p = C.parse_call_particulars(JOHNSON)
        self.assertEqual(
            C.opening_sentence(C.LANGUAGES["en"], p, MONDAY.date()),
            "Hello, this is Sasha, an AI assistant, calling on behalf of the Johnson family to book a table for four "
            "on Thursday at eight in the evening. Is that possible?")
        self.assertEqual(C.check_sentence(C.LANGUAGES["en"], p), "I'll need to check that with the Johnsons.")

    def test_every_language_discloses_the_AI_at_the_first_sentence(self):
        p = C.parse_call_particulars(JOHNSON)
        marks = {"en": "AI assistant", "pt": "assistente de IA", "es": "asistente de IA", "fr": "assistante IA",
                 "de": "KI-Assistentin", "it": "assistente IA"}
        self.assertEqual(set(marks), set(C.LANGUAGES))
        for code, mark in marks.items():
            s = C.opening_sentence(C.LANGUAGES[code], p, MONDAY.date())
            # the AI clause comes before anything is asked
            self.assertIn(mark, s, code)
            self.assertLess(s.index(mark), s.index("Johnson"), code)

    def test_a_date_more_than_six_days_away_is_said_with_its_date(self):
        p = C.parse_call_particulars({**JOHNSON, "date": "2026-10-20", "time": "13:30", "party": 1, "name": "Jon Peters"})
        self.assertEqual(C.opening_sentence(C.LANGUAGES["en"], p, MONDAY.date()),
                         "Hello, this is Sasha, an AI assistant, calling on behalf of Jon Peters to book a table for one "
                         "on Tuesday, 20 October, at one thirty in the afternoon. Is that possible?")

    def test_a_date_already_past_at_the_venue_is_refused(self):
        p = C.parse_call_particulars({**JOHNSON, "date": "2026-10-04"})
        with self.assertRaises(C.CallRefused) as e:
            C.build_call(C.test_line(), p, MONDAY)
        self.assertEqual(e.exception.rule, "date_in_the_past")

    def test_the_number_never_comes_from_the_request(self):
        for k in ("number", "phone_number", "venue_phone"):
            with self.assertRaises(C.CallRefused) as e:
                C.parse_call_particulars({**JOHNSON, k: "+15550000000"})
            self.assertEqual(e.exception.rule, "number_from_request")

    def test_a_name_that_is_not_a_name_is_never_read_aloud(self):
        for bad in ("x", "Robert'); drop table", "Call 911 now", "a" * 61, "<b>Ann</b>"):
            with self.assertRaises(C.CallRefused, msg=bad):
                C.parse_call_particulars({**JOHNSON, "name": bad})

    def test_the_brief_carries_every_rule_and_the_read_back_says_what_she_will_do(self):
        b = C.build_call(C.test_line(), C.parse_call_particulars(JOHNSON), MONDAY)
        t = b["brief"]["task"]
        for must in ("Never agree to a different date", "Never agree to a deposit", "I'll need to check that with the Johnsons.",
                     "you are an AI assistant", "Do not leave a voicemail", "no contact number"):
            self.assertIn(must, t)
        self.assertLessEqual(len(t), 2000)
        self.assertEqual(b["brief"]["number"], "+351912000000")
        self.assertIn("+351912000000", b["read_back_lines"][0])
        self.assertIn("deposit", b["read_back_lines"][2])

    def test_a_guest_phone_is_given_only_when_asked_and_the_read_back_says_so(self):
        b = C.build_call(C.test_line(), C.parse_call_particulars({**JOHNSON, "phone": "+351 911 111 111"}), MONDAY)
        self.assertIn("only if — they ask for a contact number", b["brief"]["task"])
        self.assertEqual(b["read_back_lines"][3], "If they ask for a contact number, I'll give yours, +351911111111.")

    def test_the_payload_bland_receives(self):
        b = C.build_call(C.test_line(), C.parse_call_particulars(JOHNSON), MONDAY)
        pl = C.bland_payload(b["brief"], "sasha-1")
        self.assertEqual(pl["phone_number"], "+351912000000")
        self.assertIs(pl["record"], False)
        self.assertEqual(pl["voicemail"], {"action": "hangup"})
        self.assertEqual(pl["first_sentence"], b["brief"]["first_sentence"])
        self.assertTrue(pl["wait_for_greeting"])

    def test_no_number_set_refuses_to_build(self):
        with mock.patch.dict(os.environ, {"SASHA_TEST_CALL_NUMBER": ""}):
            with self.assertRaises(C.CallRefused) as e:
                C.build_call(C.test_line(), C.parse_call_particulars(JOHNSON), MONDAY)
        self.assertEqual(e.exception.rule, "venue_number_not_set")


# ── 2 · Bland's answer, READ ─────────────────────────────────────────────────────────────────

class Placing(unittest.TestCase):
    def place(self, answer):
        return run(C.place_call(FakeBland(place=answer), "k", {"phone_number": "+351912000000"}))

    def test_placed_only_on_200_success_with_a_call_id(self):
        p = self.place(R(200, {"status": "success", "call_id": "c-1"}))
        self.assertTrue(p.placed)
        self.assertEqual(p.bland_call_id, "c-1")

    def test_everything_else_is_not_placed_with_blands_own_words(self):
        cases = [
            (R(400, {"status": "error", "message": "Invalid phone number", "errors": ["phone_number"]}), "Invalid phone number"),
            (R(402, {"status": "error", "message": "Insufficient balance"}), "Insufficient balance"),
            (R(200, {"status": "error", "message": "queue full"}), "queue full"),
            (R(200, {"status": "success"}), "HTTP 200"),              # success with no call id
            (R(200, {"status": "success", "call_id": ""}), "HTTP 200"),
            (R(500, ValueError("not json")), "not JSON"),
            (R(200, ["unexpected"]), "unexpected body"),
            (ConnectionError("down"), "could not be reached"),
        ]
        for answer, words in cases:
            p = self.place(answer)
            self.assertFalse(p.placed, words)
            self.assertIsNone(p.bland_call_id, words)
            self.assertIn(words, p.why)


# ── 3 · reading the finished call ────────────────────────────────────────────────────────────

class Reading(unittest.TestCase):
    YES = done(("assistant", "Hello, this is Sasha… Is that possible?"), ("user", "Yes, that's fine, four at eight on Thursday."),
               ("assistant", "So that's four, Thursday at eight, under Johnson?"), ("user", "Yes, see you then."))

    def read(self, details, reader=None):
        return run(C.read_call(details, reader or reader_says({"reading": "unclear", "quote": "", "raised": []})))

    def test_not_reached(self):
        for d, words in [(done(answered_by="voicemail"), "voicemail"), ({"completed": True, "status": "no-answer"}, "nobody answered"),
                         ({"completed": True, "status": "busy"}, "busy"),
                         ({"completed": True, "status": "failed", "error_message": "carrier blocked"}, "carrier blocked")]:
            r = self.read(d)
            self.assertEqual((r.state, r.outcome), ("not_reached", None), words)
            self.assertIn(words, r.why)

    def test_still_in_progress(self):
        r = self.read({"completed": False, "status": None, "queue_status": "started"})
        self.assertEqual(r.state, "in_progress")

    def test_a_quoted_yes_is_yes(self):
        r = self.read(self.YES, reader_says({"reading": "yes", "quote": "Yes, that's fine, four at eight on Thursday.", "raised": []}))
        self.assertEqual((r.state, r.outcome), ("answered", "yes"))
        self.assertIn("Yes, see you then.", r.venue_words)
        self.assertEqual(r.read_by, C.READ_BY)

    def test_a_yes_quoting_sasha_rather_than_the_venue_is_unclear(self):
        r = self.read(self.YES, reader_says({"reading": "yes", "quote": "So that's four, Thursday at eight, under Johnson?", "raised": []}))
        self.assertEqual(r.outcome, "unclear")
        self.assertIn("could not quote the venue", r.why)

    def test_a_yes_with_an_invented_quote_is_unclear(self):
        r = self.read(self.YES, reader_says({"reading": "yes", "quote": "Absolutely, confirmed for four.", "raised": []}))
        self.assertEqual(r.outcome, "unclear")

    def test_a_yes_with_a_deposit_is_unclear_even_if_the_reader_missed_it(self):
        d = done(("user", "Yes we can, but we need a 20 euro deposit per person."), ("assistant", "I'll need to check that with the Johnsons."))
        r = self.read(d, reader_says({"reading": "yes", "quote": "Yes we can", "raised": []}))
        self.assertEqual(r.outcome, "unclear")
        self.assertIn("deposit", r.why)

    def test_a_yes_with_a_different_time_is_unclear(self):
        d = done(("user", "Eight is full. We can do 9:15 instead."), ("assistant", "I'll need to check that with the Johnsons."))
        r = self.read(d, reader_says({"reading": "yes", "quote": "We can do 9:15 instead.",
                                      "raised": [{"what": "different_time", "quote": "We can do 9:15 instead."}]}))
        self.assertEqual(r.outcome, "unclear")
        self.assertEqual(r.raised[0]["what"], "different_time")

    def test_call_back_tomorrow_is_unclear_with_their_words(self):
        d = done(("user", "The manager is out, call back tomorrow."))
        r = self.read(d, reader_says({"reading": "unclear", "quote": "", "raised": [{"what": "call_back", "quote": "call back tomorrow"}]}))
        self.assertEqual(r.outcome, "unclear")
        self.assertEqual(r.venue_words, "The manager is out, call back tomorrow.")
        self.assertIsNone(r.quote)

    def test_a_quoted_no_is_no(self):
        d = done(("user", "No, sorry, we're fully booked that night."))
        r = self.read(d, reader_says({"reading": "no", "quote": "No, sorry, we're fully booked that night.", "raised": []}))
        self.assertEqual(r.outcome, "no")

    def test_a_reader_that_fails_or_rambles_leaves_it_unclear(self):
        for rd in (reader_says(RuntimeError("model down")), reader_says("I think they said yes"), reader_says({"reading": "probably"})):
            r = self.read(self.YES, rd)
            self.assertEqual(r.outcome, "unclear")
            self.assertIn("Yes, see you then.", r.venue_words)

    def test_an_answered_call_where_the_venue_said_nothing_is_unclear(self):
        r = self.read(done(("assistant", "Hello?")))
        self.assertEqual((r.state, r.outcome, r.venue_words), ("answered", "unclear", ""))


# ── 4 · the routes ───────────────────────────────────────────────────────────────────────────

class CallRoutes:
    def make_store(self):
        raise NotImplementedError

    def trip_status(self, call_id):
        raise NotImplementedError

    def attempts(self, call_id):
        raise NotImplementedError

    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.store = self.make_store()
        self.bland = FakeBland(details={"completed": False, "queue_status": "started"})
        self.reads = 0

        async def reader(t):
            self.reads += 1
            return json.dumps({"reading": "yes", "quote": "Yes, that's fine.", "raised": []})
        self.now = MONDAY
        self.saved = (call_routes.CALL_STORE, call_routes.HTTP, call_routes.READER, call_routes.NOW)
        call_routes.CALL_STORE, call_routes.HTTP, call_routes.READER = self.store, self.bland, reader
        call_routes.NOW = lambda: self.now
        app = FastAPI()
        app.include_router(routes.router)
        self.c = TestClient(app, headers={"x-sasha-booking-key": "test-booking-key"})
        self.c.__enter__()   # one event loop for the whole test, so a Postgres pool stays on it

    def tearDown(self):
        if getattr(self, "base", None) is not None:
            self.c.portal.call(self.base.close)
        self.c.__exit__(None, None, None)
        call_routes.CALL_STORE, call_routes.HTTP, call_routes.READER, call_routes.NOW = self.saved
        self.env.stop()

    def prepare(self, **over):
        r = self.c.post("/api/booking/calls", json={**JOHNSON, **over})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def yes(self, prep):
        return self.c.post(f"/api/booking/calls/{prep['call_id']}/place",
                           json={"read_back_sha256": prep["read_back"]["sha256"], "approval": {"how": "button"}})

    def test_off_means_no_read_back_and_no_call(self):
        with mock.patch.dict(os.environ, {"SASHA_CALLS_ENABLED": "0"}):
            r = self.c.post("/api/booking/calls", json=JOHNSON)
            self.assertEqual((r.status_code, r.json()["rule"]), (422, "calls_disabled"))
        prep = self.prepare()
        with mock.patch.dict(os.environ, {"SASHA_CALLS_ENABLED": ""}):
            self.assertEqual(self.yes(prep).json()["rule"], "calls_disabled")
        with mock.patch.dict(os.environ, {"BLAND_API_KEY": ""}):
            self.assertEqual(self.yes(prep).json()["rule"], "calls_not_configured")
        self.assertEqual(self.bland.requests, [])

    def test_only_a_listed_venue_and_never_a_number_from_the_request(self):
        r = self.c.post("/api/booking/calls", json={**JOHNSON, "venue": "any-restaurant"})
        self.assertEqual(r.json()["rule"], "venue_not_callable")
        r = self.c.post("/api/booking/calls", json={**JOHNSON, "phone_number": "+15555550100"})
        self.assertEqual(r.json()["rule"], "number_from_request")

    def test_the_yes_must_be_for_this_read_back(self):
        prep = self.prepare()
        r = self.c.post(f"/api/booking/calls/{prep['call_id']}/place", json={"read_back_sha256": "0" * 64, "approval": {"how": "button"}})
        self.assertEqual(r.json()["rule"], "approval_void")
        self.assertEqual(self.bland.requests, [])

    def test_a_yes_places_one_call_to_the_venues_number_and_never_a_second(self):
        prep = self.prepare()
        r = self.yes(prep)
        self.assertEqual(r.json()["status"], "placed", r.text)
        self.assertEqual(len(self.bland.requests), 1)
        method, url, headers, body = self.bland.requests[0]
        self.assertEqual((method, url, body["phone_number"]), ("POST", C.BLAND_CALLS_URL, "+351912000000"))
        self.assertEqual(headers["authorization"], "test-key-not-real")
        r2 = self.yes(prep)
        self.assertEqual((r2.status_code, r2.json()["rule"]), (409, "call_already_placed"))
        self.assertEqual(len(self.bland.requests), 1)

    def test_bland_refusing_is_recorded_as_not_placed_never_as_a_call(self):
        self.bland.place_answer = R(402, {"status": "error", "message": "Insufficient balance"})
        prep = self.prepare()
        r = self.yes(prep).json()
        self.assertEqual((r["ok"], r["status"]), (False, "not_placed"))
        self.assertIn("Insufficient balance", r["say"])
        g = self.c.get(f"/api/booking/calls/{prep['call_id']}").json()
        self.assertEqual(g["status"], "not_placed")
        self.assertIn("Insufficient balance", g["why"])
        self.assertEqual(self.trip_status(prep["call_id"]), "pending")

    def test_a_read_back_older_than_15_minutes_cannot_be_approved(self):
        prep = self.prepare()
        self.now = MONDAY + timedelta(minutes=16)
        self.assertEqual(self.yes(prep).json()["rule"], "read_back_expired")
        self.assertEqual(self.bland.requests, [])

    def test_the_daily_ceiling(self):
        with mock.patch.dict(os.environ, {"SASHA_CALLS_PER_DAY": "1"}):
            self.assertEqual(self.yes(self.prepare()).json()["status"], "placed")
            r = self.yes(self.prepare())
            self.assertEqual((r.status_code, r.json()["rule"]), (429, "daily_call_limit"))
        self.assertEqual(len(self.bland.requests), 1)

    def test_a_finished_call_is_read_once_and_the_reservation_follows_the_venues_words(self):
        prep = self.prepare()
        self.yes(prep)
        g = self.c.get(f"/api/booking/calls/{prep['call_id']}").json()
        self.assertEqual((g["status"], g.get("outcome")), ("placed", None))   # still on the phone
        self.bland.details = done(("user", "Yes, that's fine."))
        g = self.c.get(f"/api/booking/calls/{prep['call_id']}").json()
        self.assertEqual((g["status"], g["outcome"], g["quote"]), ("answered", "yes", "Yes, that's fine."))
        self.assertEqual(g["read_by"], C.READ_BY)
        self.assertIn('Their words: "Yes, that\'s fine."', g["say"])
        self.assertEqual(self.trip_status(prep["call_id"]), "confirmed")
        self.assertEqual([(a["method"], a["status"]) for a in self.attempts(prep["call_id"])], [("phone", "confirmed")])
        self.c.get(f"/api/booking/calls/{prep['call_id']}")
        self.assertEqual(self.reads, 1)
        self.assertEqual(len(self.attempts(prep["call_id"])), 1)

    def test_a_call_that_reached_nobody_leaves_the_reservation_pending(self):
        prep = self.prepare()
        self.yes(prep)
        self.bland.details = done(answered_by="voicemail")
        g = self.c.get(f"/api/booking/calls/{prep['call_id']}").json()
        self.assertEqual((g["status"], g["outcome"]), ("not_reached", None))
        self.assertEqual(self.trip_status(prep["call_id"]), "pending")
        self.assertEqual(self.attempts(prep["call_id"]), [])

    def test_unclear_carries_the_venues_words(self):
        prep = self.prepare()
        self.yes(prep)

        async def reader(t):
            return json.dumps({"reading": "unclear", "quote": "", "raised": []})
        call_routes.READER = reader
        self.bland.details = done(("user", "Call back tomorrow, the manager does the bookings."))
        g = self.c.get(f"/api/booking/calls/{prep['call_id']}").json()
        self.assertEqual(g["outcome"], "unclear")
        self.assertEqual(g["venue_words"], "Call back tomorrow, the manager does the bookings.")
        self.assertEqual(self.trip_status(prep["call_id"]), "unclear")

    def test_health_reports_calls_without_the_number(self):
        h = self.c.get("/api/booking/health").json()["calls"]
        self.assertEqual(h["venues"]["test-line"], {"number_set": True, "language": "en"})
        self.assertNotIn("912000000", json.dumps(h))


class Sweeper(unittest.TestCase):
    """S-41 G3 · a placed call is read by the server even if nobody ever polls it."""

    def test_the_sweeper_records_a_finished_call_and_never_twice(self):
        env = mock.patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)
        store = MemoryCallStore()
        saved = (call_routes.CALL_STORE, call_routes.HTTP, call_routes.READER, call_routes.NOW)
        self.addCleanup(lambda: setattr(call_routes, "CALL_STORE", saved[0]) or setattr(call_routes, "HTTP", saved[1])
                        or setattr(call_routes, "READER", saved[2]) or setattr(call_routes, "NOW", saved[3]))
        bland = FakeBland(details={"completed": False, "queue_status": "started"})

        async def reader(t):
            return json.dumps({"reading": "yes", "quote": "Yes, that's fine.", "reference": "Johnson", "raised": []})
        call_routes.CALL_STORE, call_routes.HTTP, call_routes.READER, call_routes.NOW = store, bland, reader, (lambda: MONDAY)
        b = C.build_call(C.test_line(), C.parse_call_particulars(JOHNSON), MONDAY)
        row = {"call_id": "11111111-1111-4111-8111-000000000001", "account_id": "a", "venue_key": "test-line",
               "dialled_number": b["brief"]["number"], "language": "en", "guest_name": "Anna Johnson", "guest_phone": None,
               "brief": b["brief"], "brief_sha256": b["brief_sha256"], "read_back_lines": b["read_back_lines"],
               "read_back_sha256": b["read_back_sha256"], "created_at": MONDAY, "venue_name": "t", "local_date": MONDAY.date(),
               "local_time": MONDAY.time(), "local_timezone": "Europe/Lisbon", "party_size": 4}
        run(store.put_call(row, None))
        run(store.claim("a", row["call_id"], {}, MONDAY, MONDAY - timedelta(minutes=1), 3, MONDAY - timedelta(days=1)))
        run(store.mark_placed(row["call_id"], C.Placed(True, "bland-1", 200, {}, None), MONDAY))
        self.assertEqual(run(call_routes.sweep_once()), 0)          # still on the phone: nothing recorded
        bland.details = done(("user", "Yes, that's fine. It's under Johnson."))
        self.assertEqual(run(call_routes.sweep_once()), 1)
        self.assertEqual(run(call_routes.sweep_once()), 0)          # never recorded twice
        item = store.trip_items[store.calls[row["call_id"]]["trip_item_id"]]
        self.assertEqual((item["status"], item.get("booking_reference")), ("confirmed", "Johnson"))   # G4 · the venue's own words

    def test_a_reference_the_venue_never_said_is_never_stored(self):
        d = done(("user", "Yes, that's fine."))
        r = run(C.read_call(d, reader_says({"reading": "yes", "quote": "Yes, that's fine.", "reference": "ABC123", "raised": []})))
        self.assertIsNone(r.reference)


class OnMemory(CallRoutes, unittest.TestCase):
    def make_store(self):
        return MemoryCallStore()

    def trip_status(self, call_id):
        return self.store.trip_items[self.store.calls[call_id]["trip_item_id"]]["status"]

    def attempts(self, call_id):
        item = self.store.calls[call_id]["trip_item_id"]
        return [a for a in self.store.attempts if a["trip_item_id"] == item]


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(CallRoutes, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import asyncpg
        db = urlsplit(PG_URL).path.lstrip("/")
        if "test" not in db:  # ⛔ this wipes the database: never anything but a throwaway one
            raise unittest.SkipTest(f"refusing to use database {db!r}: its name must contain 'test'")

        async def fresh():
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute("drop schema if exists auth cascade; drop schema public cascade; create schema public;")
                await c.execute((HERE / "fixtures" / "model_a_live_2026-09-28.sql").read_text(encoding="utf-8"))
                for f in ("001_booking_storage.sql", "002_prepared_status.sql", "003_phone_calls.sql", "004_ladder.sql", "005_slot_links.sql"):
                    await c.execute((SQL_DIR / f).read_text(encoding="utf-8"))
            finally:
                await c.close()
        asyncio.run(fresh())

    def make_store(self):
        async def wipe():
            import asyncpg
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute("delete from booking_attempts; delete from booking_calls; delete from trip_items; delete from trips;")
            finally:
                await c.close()
        run(wipe())
        self.base = PostgresStore(PG_URL)
        return PostgresCallStore(self.base)

    def _q(self, sql, *args):
        async def q():
            import asyncpg
            c = await asyncpg.connect(PG_URL)
            try:
                return await c.fetch(sql, *args)
            finally:
                await c.close()
        return run(q())

    def trip_status(self, call_id):
        return self._q("select t.status from trip_items t join booking_calls c on c.trip_item_id = t.id where c.call_id = $1::uuid", call_id)[0]["status"]

    def attempts(self, call_id):
        return [dict(r) for r in self._q("select a.method, a.status from booking_attempts a join booking_calls c "
                                         "on c.trip_item_id = a.trip_item_id where c.call_id = $1::uuid", call_id)]

    def test_a_confirmed_call_is_in_the_reservations_with_the_venues_words(self):
        """S-41 G5 · date, time, party, venue, reference and the venue's own words, on the reservations list."""
        saved = routes.STORE
        routes.STORE = self.base
        self.addCleanup(lambda: setattr(routes, "STORE", saved))

        async def reader(t):
            return json.dumps({"reading": "yes", "quote": "Yes, that's fine.", "reference": "Johnson", "raised": []})
        call_routes.READER = reader
        prep = self.prepare()
        self.yes(prep)
        self.bland.details = done(("user", "Yes, that's fine. Under Johnson."))
        self.c.get(f"/api/booking/calls/{prep['call_id']}")
        res = self.c.get("/api/booking/reservations")
        self.assertEqual(res.status_code, 200, res.text)
        rows = res.json()["reservations"]
        r = [x for x in rows if x["intent_id"] == prep["call_id"]][0]
        self.assertEqual((r["channel"], r["status"], r["date"], r["time"], r["party"], r["booking_reference"]),
                         ("phone", "confirmed", "2026-10-08", "20:00", 4, "Johnson"))
        self.assertEqual(r["venue_words"], "Yes, that's fine. Under Johnson.")

    def test_the_block_refuses_to_run_twice(self):
        import asyncpg

        async def again():
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute((SQL_DIR / "003_phone_calls.sql").read_text(encoding="utf-8"))
            finally:
                await c.close()
        with self.assertRaisesRegex(Exception, "STOP: booking_calls already exists"):
            run(again())


if __name__ == "__main__":
    unittest.main()
