"""The booking routes, end to end — against the in-memory store AND a real Postgres.

    cd backend && python -m unittest tests.test_booking_routes -v

The Postgres half runs when BOOKING_TEST_DATABASE_URL names a THROWAWAY database whose name contains "test": it
wipes that database, loads tests/fixtures/model_a_live_2026-09-28.sql (auth.users and model A exactly as read
live), then runs booking_signer/sql/001_booking_storage.sql — the very block that is applied to Sasha's Supabase. ⚠ Without that variable the Postgres half is
SKIPPED, and says so — a skip is not a pass.

Keys are the public RFC 8032 test keys (signer: TEST 1, device: TEST 2), never real. Nothing here reaches a
venue, a helper, or any network.
"""
import asyncio
import base64
import json
import os
import pathlib
import re
import unittest

os.environ.setdefault("SASHA_BOOKING_KEY", "test-booking-key")   # S-41: the gate (gate.py)
os.environ.setdefault("SASHA_CALL_SWEEP", "0")
from urllib.parse import urlsplit, urlunsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import routes
from booking_signer.account import DEMO_ACCOUNT_ID
from booking_signer.canonical import canonical_bytes
from booking_signer.keys import ENV_VAR, load_signing_key
from booking_signer.store import MemoryStore, PostgresStore
from booking_signer.venues import PSI, build_for_venue, parse_particulars
from booking_signer.verify import pairing_statement

HERE = pathlib.Path(__file__).parent
BACKEND = HERE.parent
VEC = json.loads((HERE / "booking_signer_vectors.json").read_text(encoding="utf-8"))
SIGNER_SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
DEVICE = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"))
DEVICE_SPKI, DEVICE_ID = VEC["device_public_spki"], VEC["device_id"]
PG_URL = os.getenv("BOOKING_TEST_DATABASE_URL", "")
SQL = (BACKEND / "booking_signer" / "sql" / "001_booking_storage.sql").read_text(encoding="utf-8")
FIXTURE = (HERE / "fixtures" / "model_a_live_2026-09-28.sql").read_text(encoding="utf-8")
SQL_002 = (BACKEND / "booking_signer" / "sql" / "002_prepared_status.sql").read_text(encoding="utf-8")

ANA = {"venue": "restaurante-psi", "date": "2026-10-02", "time": "20:00", "party": 2, "name": "Ana Guest",
       "email": "ana.guest@example.org", "phone": "+351 000 000 000", "mode": "dry_run"}
b64 = lambda b: base64.b64encode(b).decode("ascii")


def sign_device(value) -> str:
    return b64(DEVICE.sign(canonical_bytes(value)))


class BookingRoutes:
    """Mixed into one TestCase per store. `make_store` returns a fresh, empty store."""

    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        self._saved = (routes.STORE, routes.KEY, routes.KEY_ERROR, routes.PINNED_FINGERPRINT)
        self.store = self.make_store()
        routes.STORE = self.store
        routes.KEY = load_signing_key({ENV_VAR: b64(SIGNER_SEED)})
        routes.KEY_ERROR = None
        routes.PINNED_FINGERPRINT = routes.KEY.fingerprint  # the test key stands in for the pinned one
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app, headers={"x-sasha-booking-key": "test-booking-key", "x-sasha-session": "founder"})
        self.client.__enter__()

    def tearDown(self):
        if isinstance(self.store, PostgresStore):
            self.client.portal.call(self.store.close)
        self.client.__exit__(None, None, None)
        routes.STORE, routes.KEY, routes.KEY_ERROR, routes.PINNED_FINGERPRINT = self._saved

    # ── helpers ──
    def post(self, path, body):
        return self.client.post(f"/api/booking{path}", json=body)

    def pair(self):
        ch = self.post("/pairing/challenge", {}).json()["challenge"]
        stmt = pairing_statement(ch, DEVICE_ID, "https://project.kanoe.ai")
        return self.post("/pairing", {"challenge": ch, "device_id": DEVICE_ID, "device_public_spki": DEVICE_SPKI,
                                      "origin": "https://project.kanoe.ai", "signature": sign_device(stmt)})

    def intent(self, **over):
        r = self.post("/intents", {**ANA, **over})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def issued(self):
        self.assertEqual(self.pair().status_code, 200)
        i = self.intent()
        r = self.post(f"/intents/{i['intent_id']}/issue", {"device_id": DEVICE_ID, "approval": {"how": "voice", "said": "yes, book it"}})
        self.assertEqual(r.status_code, 200, r.text)
        signed = r.json()
        digest = __import__("hashlib").sha256(canonical_bytes(signed["payload"])).hexdigest()
        return i, signed, digest

    def report(self, digest, body):
        signed = {"report": body, "task_digest": digest, "device_id": DEVICE_ID}
        return self.post("/reports", {**signed, "device_signature": sign_device(signed)})

    def dry_run_report(self, intent_id):
        return {"agent": "sasha-helper/0.1.0", "intent_id": intent_id, "ok": True, "phase": "captured_not_sent",
                "rule": "captured_not_sent", "sent": False, "tab_opened": True,
                "user_words": "I've filled in their form on your computer and stopped just before sending, as planned. Nothing was sent.",
                "why": "dry run"}

    def sent_report(self, intent_id, matched=None, phase="submitted_and_read", quoted="the page's words"):
        body = {"agent": "sasha-helper/0.1.0", "intent_id": intent_id, "ok": True, "phase": phase, "rule": "read_x",
                "sent": True, "tab_opened": True, "user_words": None, "why": "test"}
        if matched:
            body["reading"] = {"observed_by": "the user's device", "intent_id": intent_id, "matched": matched,
                               "quoted": quoted, "reference": None, "read_at": "2026-09-28T10:00:05.000Z"}
        return body

    # ── health ──
    def test_health_reports_the_signer_and_the_storage(self):
        h = self.client.get("/api/booking/health").json()
        self.assertEqual([h["mounted"], h["signer"]["matches_pinned"], h["storage"]["provisioned"], h["live_issue_enabled"]],
                         [True, True, True, False])

    # ── pairing ──
    def test_a_browser_pairs_once_per_challenge(self):
        ch = self.post("/pairing/challenge", {}).json()["challenge"]
        self.assertGreaterEqual(len(ch), 32)
        stmt = pairing_statement(ch, DEVICE_ID, "https://project.kanoe.ai")
        body = {"challenge": ch, "device_id": DEVICE_ID, "device_public_spki": DEVICE_SPKI,
                "origin": "https://project.kanoe.ai", "signature": sign_device(stmt)}
        self.assertEqual(self.post("/pairing", body).json()["device_id"], DEVICE_ID)
        again = self.post("/pairing", body)
        self.assertEqual([again.status_code, again.json()["rule"]], [422, "pairing_invalid"])  # a challenge is spent
        self.assertEqual(self.client.get("/api/booking/devices").json()["devices"], [DEVICE_ID])

    def test_pairing_refusals(self):
        r = self.post("/pairing", {"challenge": "x" * 40, "device_id": DEVICE_ID, "device_public_spki": DEVICE_SPKI,
                                   "origin": "https://project.kanoe.ai", "signature": "AA=="})
        self.assertEqual(r.json()["rule"], "pairing_invalid")  # a challenge this server never issued
        ch = self.post("/pairing/challenge", {}).json()["challenge"]
        stmt = pairing_statement(ch, DEVICE_ID, "https://evil.example")
        r = self.post("/pairing", {"challenge": ch, "device_id": DEVICE_ID, "device_public_spki": DEVICE_SPKI,
                                   "origin": "https://evil.example", "signature": sign_device(stmt)})
        self.assertEqual(r.json()["rule"], "pairing_wrong_origin")
        self.assertEqual(self.client.get("/api/booking/devices").json()["devices"], [])

    # ── intents ──
    def test_an_intent_is_recorded_with_the_contract_read_back(self):
        # P807mv-S1: lines 1–4 are the contract's; line 5 of a DRY RUN never promises to send
        i = self.intent()
        lines = i["read_back"]["lines"]
        self.assertEqual(lines[:4], VEC["payload"]["read_back"]["lines"][:4])
        self.assertEqual(lines[4], "I will open their booking page on this machine, fill it in, and stop before sending. Shall I?")
        self.assertNotIn("send it from here", " ".join(lines))
        self.assertEqual(i["read_back"]["sha256"], __import__("hashlib").sha256("\n".join(lines).encode()).hexdigest())

    def test_live_is_refused_before_anything_is_recorded(self):
        r = self.post("/intents", {**ANA, "mode": "live"})
        self.assertEqual([r.status_code, r.json()["rule"]], [422, "live_submit_disabled_in_this_build"])

    def test_particulars_refusals(self):
        for over, rule in [({"date": "02/10/2026"}, "date_invalid"), ({"time": "8pm"}, "time_invalid"),
                           ({"party": 0}, "party_invalid"), ({"party": "2"}, "party_invalid"),
                           ({"email": "  "}, "email_missing"), ({"venue": "elsewhere"}, "venue_not_specified")]:
            self.assertEqual(self.post("/intents", {**ANA, **over}).json()["rule"], rule, over)

    # ── issuing ──
    def test_a_yes_signs_exactly_the_contract_task_once(self):
        i, signed, digest = self.issued()
        p = signed["payload"]
        signer_public = Ed25519PublicKey.from_public_bytes(base64.b64decode(VEC["signer_public_spki"])[12:])
        signer_public.verify(base64.b64decode(signed["signature"]), canonical_bytes(p))  # raises if it does not verify
        strip = lambda t: {k: v for k, v in t.items() if k not in ("intent_id", "issued_at", "expires_at")}
        self.assertEqual(canonical_bytes(strip(p["task"])), canonical_bytes(strip(VEC["payload"]["task"])))
        self.assertEqual([p["task"]["intent_id"], p["mode"], p["device_id"], p["approval"]["by"], p["spec_standing"]],
                         [i["intent_id"], "dry_run", DEVICE_ID, DEMO_ACCOUNT_ID, VEC["payload"]["spec_standing"]])
        again = self.post(f"/intents/{i['intent_id']}/issue", {"device_id": DEVICE_ID, "approval": {"how": "button", "said": None}})
        self.assertEqual([again.status_code, again.json()["rule"]], [409, "intent_already_issued"])

    def test_issue_refusals(self):
        i = self.intent()
        r = self.post(f"/intents/{i['intent_id']}/issue", {"device_id": DEVICE_ID, "approval": {"how": "button"}})
        self.assertEqual(r.json()["rule"], "no_paired_device")  # not paired yet
        self.pair()
        r = self.post(f"/intents/{i['intent_id']}/issue", {"device_id": DEVICE_ID, "approval": {"how": "voice", "said": " "}})
        self.assertEqual(r.json()["rule"], "approval_voice_without_words")
        # ⚠ a refused issue signs nothing, so the SAME intent can still be approved
        r = self.post(f"/intents/{i['intent_id']}/issue", {"device_id": DEVICE_ID, "approval": {"how": "button", "said": None}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.post("/intents/00000000-0000-4000-8000-00000000dead/issue", {"device_id": DEVICE_ID, "approval": {}}).status_code, 404)

    def test_a_key_the_helper_does_not_pin_signs_nothing(self):
        self.pair()
        i = self.intent()
        routes.PINNED_FINGERPRINT = "525f7027ed4f62b2"  # the real pin; the test key is not it
        r = self.post(f"/intents/{i['intent_id']}/issue", {"device_id": DEVICE_ID, "approval": {"how": "button"}})
        self.assertEqual([r.status_code, r.json()["rule"]], [503, "signing_key_not_pinned_in_helper"])
        routes.KEY, routes.KEY_ERROR = None, "SigningKeyNotConfigured: not set"
        r = self.post(f"/intents/{i['intent_id']}/issue", {"device_id": DEVICE_ID, "approval": {"how": "button"}})
        self.assertEqual([r.status_code, r.json()["rule"]], [503, "signer_not_configured"])

    # ── reports ──
    def test_an_intent_outside_this_accounts_trips_records_nothing(self):
        r = self.post("/intents", {**ANA, "trip_id": "00000000-0000-4000-8000-00000000beef"})
        self.assertEqual([r.status_code, r.json()["rule"]], [404, "trip_unknown"])

    def test_a_dry_run_records_no_outcome_and_leaves_the_reservation_prepared(self):
        # S-26: nothing was sent, so there is no OUTCOME and no attempt — but the form WAS filled and checked on
        # the device, so the reservation reads "prepared": never requested, never confirmed.
        i, _, digest = self.issued()
        r = self.report(digest, self.dry_run_report(i["intent_id"])).json()
        self.assertEqual([r["outcome"], r["reservation_id"]], [None, i["trip_item_id"]])
        self.assertIn("Nothing was sent", r["say"])
        again = self.report(digest, self.dry_run_report(i["intent_id"])).json()  # re-sent on PENDING
        self.assertEqual([again["already_recorded"], again["outcome"]], [True, None])
        res = self.client.get("/api/booking/reservations").json()["reservations"]
        self.assertEqual([(x["id"], x["status"], x["status_words"], x["date"], x["time"], x["party"], x["booking_reference"], x["venue_words"])
                          for x in res],
                         [(i["trip_item_id"], "prepared", "Prepared — not sent (demo)", "2026-10-02", "20:00", 2, None, None)])
        self.assertEqual(res[0]["sasha_reference"], i["intent_id"][:8])  # Sasha's OWN reference, from the intent
        self.assertNotIn("confirm", res[0]["status_words"].lower().replace("to confirm", ""))

    def test_a_refusal_before_anything_ran_leaves_the_reservation_pending(self):
        # a report where the helper refused (nothing captured) is NOT a prepared dry run
        i, _, digest = self.issued()
        body = {**self.dry_run_report(i["intent_id"]), "ok": False, "phase": "refused", "rule": "intent_already_run", "tab_opened": False}
        self.report(digest, body)
        self.assertEqual(self.client.get("/api/booking/reservations").json()["reservations"], [])

    def test_the_contract_outcome_mapping_makes_a_reservation_only_when_something_was_sent(self):
        # ⚠ The helper cannot send today (live is off in it AND here), so these reports are ones no helper can
        # produce yet. They pin the §7 mapping so the day live is enabled, the reservation is already right.
        cases = [("accepted", "submitted_and_read", "requested", "the page's words"),
                 ("refused", "submitted_and_read", "declined", "the page's words"),
                 ("neither", "submitted_and_read", "unreachable", None),
                 (None, "submitted_unread", "failed", None)]
        for matched, phase, want, words in cases:
            i, _, digest = self.issued()
            r = self.report(digest, self.sent_report(i["intent_id"], matched, phase)).json()
            self.assertEqual(r["outcome"], want, matched)
            self.assertIsNotNone(r["reservation_id"])
            res = next(x for x in self.client.get("/api/booking/reservations").json()["reservations"] if x["intent_id"] == i["intent_id"])
            self.assertEqual([res["id"], res["date"], res["time"], res["timezone"], res["party"], res["status"],
                              res["observed_by"], res["booking_reference"], res["venue_words"], res["task_digest"]],
                             [i["trip_item_id"], "2026-10-02", "20:00", "Europe/Lisbon", 2, want,
                              "the user's device", None, words, digest])
        self.assertNotIn("confirmed", {x["status"] for x in self.client.get("/api/booking/reservations").json()["reservations"]})

    def test_report_refusals_record_nothing(self):
        i, _, digest = self.issued()
        body = self.dry_run_report(i["intent_id"])
        signed = {"report": body, "task_digest": digest, "device_id": DEVICE_ID}
        sig = sign_device(signed)
        edited = {**signed, "report": {**body, "sent": True}, "device_signature": sig}  # the page altered it
        self.assertEqual(self.post("/reports", edited).json()["rule"], "report_signature_invalid")
        other = {"report": body, "task_digest": "0" * 64, "device_id": DEVICE_ID}
        self.assertEqual(self.post("/reports", {**other, "device_signature": sign_device(other)}).json()["rule"], "report_of_another_task")
        stranger = {"report": body, "task_digest": digest, "device_id": "a" * 64, "device_signature": sig}
        self.assertEqual(self.post("/reports", stranger).json()["rule"], "report_from_another_device")
        # nothing above was recorded, so the genuine report is still the first
        self.assertNotIn("already_recorded", self.report(digest, body).json())

    def test_a_null_digest_report_is_nothing_ran(self):
        self.pair()
        body = {"agent": "sasha-helper/0.1.0", "intent_id": None, "ok": False, "phase": "refused",
                "rule": "task_signature_invalid", "sent": False, "tab_opened": False,
                "user_words": "I couldn't check this booking came from me, so I didn't open anything. Nothing was sent.", "why": "x"}
        r = self.report(None, body).json()
        self.assertEqual([r["outcome"], r["say"]], [None, body["user_words"]])
        claims = self.report(None, {**body, "sent": True}).json()
        self.assertEqual(claims["rule"], "report_claims_an_act_before_verification")


class OnMemory(BookingRoutes, unittest.TestCase):
    def make_store(self):
        return MemoryStore()

    def test_s64_a_national_phone_is_asked_about_once_then_normalised_and_the_form_keeps_what_was_typed(self):
        r = self.post("/intents", {**ANA, "phone": "912 000 000"})
        self.assertEqual((r.status_code, r.json()["rule"]), (422, "phone_country_needed"))
        self.assertIn("which country is the number 912 000 000 from?", r.json()["message"])
        i = self.intent(phone="912 000 000", phone_country="PT")
        rec = self.store.intents[i["intent_id"]]
        item = self.store.trip_items[rec["trip_item_id"]]
        self.assertEqual(item["request"]["who"]["contact"]["mobile_e164"], "+351912000000")
        self.assertIn({"name": "rtb-phone", "value": "912 000 000", "selector": '[name="rtb-phone"]'}, rec["task"]["fields"])


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(BookingRoutes, unittest.TestCase):
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
                await c.execute(FIXTURE)  # auth.users and model A, as read live
                await c.execute(SQL)      # the block, exactly as it is applied to Sasha's Supabase
                await c.execute(SQL_002)  # S-26: the 'prepared' status, as applied after it
                for f in ("003_phone_calls.sql", "004_ladder.sql", "005_slot_links.sql", "011_reservation_request.sql"):   # S-41 G5: reservations read them
                    await c.execute((BACKEND / "booking_signer" / "sql" / f).read_text(encoding="utf-8"))
            finally:
                await c.close()
        asyncio.run(fresh())

    def make_store(self):
        import asyncpg

        async def empty():  # every row but the demo auth user the block created
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute("truncate public.booking_reports, public.booking_tasks, public.booking_intents, "
                                "public.booking_devices, public.booking_pairing_challenges, public.booking_attempts, "
                                "public.trip_items, public.trips restart identity cascade")
            finally:
                await c.close()
        asyncio.run(empty())
        return PostgresStore(PG_URL)

    def sql(self, q, *args):
        import asyncpg

        async def run():
            c = await asyncpg.connect(PG_URL)
            try:
                return await c.fetch(q, *args)
            finally:
                await c.close()
        return asyncio.run(run())

    def test_the_reservation_is_a_trip_item_at_the_right_instant(self):
        i = self.intent()
        row = self.sql("select t.type, t.status, t.provider_name, t.party_size, t.local_timezone, "
                       "to_char(t.date_time at time zone 'UTC', 'YYYY-MM-DD HH24:MI') as utc, p.title, p.owner_id::text as owner "
                       "from trip_items t join trips p on p.id = t.trip_id where t.id = $1::uuid", i["trip_item_id"])[0]
        # 20:00 in Lisbon on 2 October 2026 is summer time (UTC+1): 19:00 UTC
        self.assertEqual(dict(row), {"type": "restaurant", "status": "pending", "provider_name": "Restaurante Psi",
                                     "party_size": 2, "local_timezone": "Europe/Lisbon", "utc": "2026-10-02 19:00",
                                     "title": "Sasha bookings", "owner": DEMO_ACCOUNT_ID})
        self.intent()  # a second booking joins the same trip rather than opening another
        self.assertEqual(self.sql("select count(*) as n from trips")[0]["n"], 1)

    def test_a_dry_run_leaves_the_trip_item_prepared_and_writes_no_attempt(self):
        i, _, digest = self.issued()
        self.report(digest, self.dry_run_report(i["intent_id"]))
        self.assertEqual(self.sql("select status from trip_items where id = $1::uuid", i["trip_item_id"])[0]["status"], "prepared")
        self.assertEqual(self.sql("select count(*) as n from booking_attempts")[0]["n"], 0)

    def test_an_attempt_can_no_longer_be_inserted_without_saying_what_happened(self):
        import asyncpg
        i = self.intent()
        with self.assertRaises(asyncpg.exceptions.NotNullViolationError):
            self.sql("insert into booking_attempts (trip_item_id, method) values ($1::uuid, 'web_form')", i["trip_item_id"])

    def test_a_database_without_the_tables_answers_503_by_name(self):
        routes.STORE = PostgresStore(urlunsplit(urlsplit(PG_URL)._replace(path="/postgres")))  # same server, no tables
        try:
            r = self.post("/pairing/challenge", {})
            self.assertEqual([r.status_code, r.json()["rule"]], [503, "storage_not_provisioned"])
            self.assertEqual(self.client.get("/api/booking/health").json()["storage"]["provisioned"], False)
        finally:
            self.client.portal.call(routes.STORE.close)


class WithoutStorageOrAMount(unittest.TestCase):
    def test_no_database_url_answers_503_by_name(self):
        saved = routes.STORE
        routes.STORE = PostgresStore(dsn="")
        try:
            app = FastAPI()
            app.include_router(routes.router)
            with TestClient(app, headers={"x-sasha-booking-key": "test-booking-key", "x-sasha-session": "founder"}) as c:
                r = c.post("/api/booking/pairing/challenge", json={})
                self.assertEqual([r.status_code, r.json()["rule"]], [503, "storage_not_configured"])
                self.assertEqual(c.get("/api/booking/health").json()["storage"]["configured"], False)
        finally:
            routes.STORE = saved

    def test_the_demo_account_is_the_chat_stores_demo_user(self):
        src = (BACKEND / "app" / "services" / "chat_store.py").read_text(encoding="utf-8")
        self.assertEqual(re.search(r'^DEMO_USER_ID = "([^"]+)"', src, re.M).group(1), DEMO_ACCOUNT_ID)

    def test_main_mounts_the_booking_routes(self):
        # ⚠ Every CTO zip ships main.py WITHOUT this; Stage B re-applies it and Stage E probes /api/booking/health.
        src = (BACKEND / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("from booking_signer.routes import router as booking_signer_router", src)
        self.assertIn("app.include_router(booking_signer_router)", src)

    def test_the_server_builds_the_contract_task_from_particulars(self):
        b = build_for_venue(PSI, parse_particulars(ANA), "live")
        # a LIVE read-back is the contract's, word for word — and its hash is the vector's
        self.assertEqual([b["read_back_lines"], b["read_back_sha256"]], [VEC["payload"]["read_back"]["lines"], VEC["read_back_sha256"]])
        strip = lambda t: {k: v for k, v in t.items() if k not in ("intent_id", "issued_at", "expires_at")}
        self.assertEqual(canonical_bytes(b["task"]), canonical_bytes(strip(VEC["payload"]["task"])))
        self.assertEqual(b["filled_values_sha256"], VEC["filled_values_sha256"])


if __name__ == "__main__":
    unittest.main()
