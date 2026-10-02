"""S-79 · Google Calendar (§7 tests 1–6): the outbox trigger, the status map, use_connection, the OAuth state, the
drainer (create, delete, the 7-day expiry told once), and the free/busy read-back line. Google is faked. The trigger runs
against Postgres (BOOKING_TEST_DATABASE_URL).

    cd backend && python -m unittest tests.test_calendar_s79 -v
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from booking_signer import calendar_sync as CS, guest_whatsapp as GW
from booking_signer.vault import crypto as VC, kms as VK
from booking_signer.vault.store import MemoryVaultStore
from tests import test_booking_ladder as TBL   # a module: its own tests are not collected twice

ACCOUNT = "66666666-6666-4666-8666-666666666666"
OTHER = "77777777-7777-4777-8777-777777777777"


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


class Base(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        fd, self.kek = tempfile.mkstemp(); os.write(fd, base64.b64encode(os.urandom(32))); os.close(fd)
        self.env = mock.patch.dict(os.environ, {"SASHA_VAULT_LOCAL_KEK_FILE": self.kek, "SASHA_VAULT_KMS_KEY": "", "SASHA_VAULT_GCP_SA_JSON": "",
                                                "ENV": "", "RAILWAY_ENVIRONMENT_NAME": "", "SASHA_GOOGLE_OAUTH_CLIENT_ID": "cid",
                                                "SASHA_GOOGLE_OAUTH_CLIENT_SECRET": "csecret",
                                                "SASHA_GOOGLE_OAUTH_REDIRECT": "https://api.test/api/booking/google/callback"})
        self.env.start()
        VK.reset()
        self.saved = (VC.STORE, CS.STORE, CS.GOOGLE_HTTP, VC.GOOGLE_REFRESH, GW.STORE)
        VC.STORE, CS.STORE, GW.STORE = MemoryVaultStore(), CS.MemoryCalendarStore(), GW.MemoryGuestStore()
        self.google = []
        self.refresh_error = None

        async def http(method, url, token=None, json_body=None, data=None):
            self.google.append((method, url, token, json_body))
            if url.endswith("/events") and method == "POST":
                return 200, {"id": f"ev{len(self.google)}", "etag": "e1"}
            if "/events/" in url and method == "PATCH":
                return 200, {"id": url.rsplit("/", 1)[1], "etag": "e2"}
            if "/events/" in url and method == "DELETE":
                return 204, {}
            if url.endswith("/freeBusy"):
                return 200, {"calendars": {"primary": {"busy": [{"start": "2026-10-03T19:00:00Z", "end": "2026-10-03T20:30:00Z"}]}}}
            return 404, {}
        CS.GOOGLE_HTTP = http

        async def refresh(token):
            if self.refresh_error:
                raise VC.UseRefused(self.refresh_error, "Google refused")
            assert token == "1//refresh-SECRET"
            return {"access_token": "ya29.access"}
        VC.GOOGLE_REFRESH = refresh

    def tearDown(self):
        VC.STORE, CS.STORE, CS.GOOGLE_HTTP, VC.GOOGLE_REFRESH, GW.STORE = self.saved
        self.env.stop()
        VK.reset()
        os.unlink(self.kek)

    def connect(self, account=ACCOUNT):
        item = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        sealed = run(VC.seal(account, item, "oauth", json.dumps({"refresh_token": "1//refresh-SECRET"}).encode()))
        run(VC.STORE.create({"id": item, "account_id": account, "provider": "google.com", "label": "Google Calendar", "kind": "oauth",
                             **sealed, "created_at": now, "updated_at": now}))
        c = CS.consent()
        run(CS.STORE.put_link({"account_id": account, "vault_item_id": item, "google_calendar_id": "sasha-cal", "scopes": CS.SCOPES,
                               "consent_at": now, "consent_wording_version": c["version"], "consent_text_sha256": c["sha256"]}))
        return item


class Map(unittest.TestCase):
    def test_2_every_status(self):
        want = {"confirmed": "event", "guest_booked": "event", "proposed": "tentative", "quoted": "tentative", "waitlisted": "tentative",
                "cancelled": "delete", "declined": "delete", "failed": "delete"}
        for s in "pending prepared attempting requested declined unreachable confirmed failed escalated cancelled unclear link_sent guest_booked proposed quoted waitlisted".split():
            self.assertEqual(CS.calendar_action(s), want.get(s, "none"), s)


class Connection(Base):
    def test_3_use_connection(self):
        item = self.connect()
        tok = run(VC.use_connection(ACCOUNT, item, purpose="calendar_sync"))
        self.assertEqual(tok, "ya29.access")
        uses = run(VC.STORE.uses_of(ACCOUNT))
        self.assertEqual([(u["action_kind"], u["status"]) for u in uses], [("calendar_sync", "done")])
        with self.assertRaises(VC.UseRefused):
            run(VC.use_connection(ACCOUNT, item, purpose="booking_login"))        # not a connection purpose
        login = self.connect(OTHER)
        VC.STORE.items[login]["kind"] = "password"
        with self.assertRaises(VC.UseRefused):
            run(VC.use_connection(OTHER, login, purpose="calendar_sync"))         # not an oauth item
        self.refresh_error = "connection_invalid_grant"
        with self.assertRaises(VC.UseRefused):
            run(VC.use_connection(ACCOUNT, item, purpose="calendar_sync"))
        self.assertNotIn("refresh-SECRET", json.dumps(run(VC.STORE.uses_of(ACCOUNT)), default=str))   # never in a log

    def test_4_state(self):
        s = CS.make_state(ACCOUNT, "v1")
        self.assertEqual(CS.read_state(s)["a"], ACCOUNT)
        body, sig = s.split(".")
        forged = base64.urlsafe_b64encode(json.dumps({"a": OTHER, "v": "v1", "n": "x", "e": int(time.time()) + 600}).encode()).decode().rstrip("=")
        self.assertIsNone(CS.read_state(f"{forged}.{sig}"))                       # account B can't ride A's signature
        self.assertIsNone(CS.read_state(CS.make_state(ACCOUNT, "v1", now=time.time() - 700)))   # expired

    def test_4b_the_callback_refuses_a_bad_state(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI(); app.include_router(CS.router)
        r = TestClient(app).get("/google/callback?state=nope&code=x")
        self.assertEqual((r.status_code, r.json()["rule"]), (400, "state_invalid"))

    def test_4c_a_failed_gmail_connect_is_the_gmail_blocks_word(self):
        """2 Oct 2026: a failure on the Gmail sign-in arrived as ?google=failed, over a Calendar that was connected."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI(); app.include_router(CS.router)
        c = TestClient(app)
        for product, want in (("gmail", "?gmail=failed#gmail"), ("calendar", "?google=failed#calendar")):
            r = c.get(f"/google/callback?state={CS.make_state(ACCOUNT, 'v1', product=product)}&code=x", follow_redirects=False)
            self.assertEqual(r.status_code, 303)
            self.assertTrue(r.headers["location"].endswith(want), r.headers["location"])


class Drain(Base):
    def item(self, status, tid="t-1"):
        CS.STORE.items[tid] = {"id": tid, "account_id": ACCOUNT, "status": status, "date_time": datetime(2026, 10, 3, 19, 0, tzinfo=timezone.utc),
                               "duration_minutes": None, "provider_name": "Casa Lucio", "booking_reference": "AB12", "party_size": 2,
                               "local_timezone": "Europe/Madrid"}
        CS.STORE.outbox.append({"id": len(CS.STORE.outbox) + 1, "trip_item_id": tid, "status": status, "done_at": None, "attempts": 0})

    def test_5_created_then_deleted(self):
        self.connect()
        self.item("confirmed")
        self.assertEqual(run(CS.drain_once()), ["done: created (event)"])
        method, url, token, body = self.google[-1]
        self.assertEqual((method, url, token), ("POST", f"{CS.CAL}/calendars/sasha-cal/events", "ya29.access"))
        self.assertEqual(body["summary"], "Casa Lucio")
        self.assertIn("ref AB12", body["description"])
        self.item("cancelled")
        self.assertEqual(run(CS.drain_once()), ["done: deleted"])
        self.assertEqual(CS.STORE.events, {})

    def test_5b_nothing_for_a_booking_that_isnt_one(self):
        self.connect()
        self.item("unclear")
        self.assertEqual(run(CS.drain_once()), ["done: nothing to show"])
        self.assertEqual(self.google, [])

    def test_5c_the_expiry_is_told_once_and_nothing_is_lost(self):
        self.connect()
        self.refresh_error = "connection_invalid_grant"
        self.item("confirmed", "t-1"); self.item("confirmed", "t-2")
        with mock.patch.object(CS, "_expired", wraps=CS._expired) as exp:
            self.assertEqual(run(CS.drain_once()), ["kept: expired (invalid_grant)", "kept: the connection needs reconnecting"])
        self.assertEqual(exp.call_count, 1)
        self.assertEqual(len(run(CS.STORE.take())), 2)                            # kept for after the reconnect
        self.assertIsNotNone(CS.STORE.links[ACCOUNT]["needs_reconnect_at"])

    def test_no_connection_no_sync(self):
        self.item("confirmed")
        self.assertEqual(run(CS.drain_once()), ["done: no calendar connected"])


class FreeBusy(Base):
    def test_6_a_busy_range_is_a_line_inside_the_hash(self):
        from booking_signer import calls as C
        built = {"read_back_lines": ["I'll phone Casa Lucio."], "read_back_sha256": C._sha256hex("I'll phone Casa Lucio.")}
        start = datetime(2026, 10, 3, 21, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        self.assertEqual(run(CS.with_busy_line(ACCOUNT, built, start, 120, "Europe/Madrid")), built)    # no link: identical
        self.connect()
        b2 = run(CS.with_busy_line(ACCOUNT, built, start, 120, "Europe/Madrid"))
        self.assertEqual(b2["read_back_lines"][-1], "Your calendar shows something at that time (21:00–22:30).")
        self.assertNotEqual(b2["read_back_sha256"], built["read_back_sha256"])
        self.assertEqual(b2["read_back_sha256"], C._sha256hex("\n".join(b2["read_back_lines"])))


@unittest.skipUnless(TBL.PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgresTrigger(unittest.TestCase):
    """§7 test 1 · every status change, whichever writer made it, lands in the outbox once; no change, no row."""

    @classmethod
    def setUpClass(cls):
        TBL.OnPostgres.setUpClass.__func__(cls)
        import asyncpg, pathlib

        async def apply():
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                root = pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql"
                await c.execute("drop table if exists calendar_links, booking_calendar_events, calendar_outbox")
                await c.execute("drop trigger if exists trip_items_calendar_outbox on trip_items")
                if not await c.fetchval("select to_regclass('public.vault_items') is not null"):
                    sql = (root / "021_vault.sql").read_text()
                    await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
                sql = (root / "022_calendar.sql").read_text()
                await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
            finally:
                await c.close()
        asyncio.run(apply())

    def test_1_the_trigger(self):
        import asyncpg

        async def go():
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                trip = await c.fetchval("insert into trips (owner_id, title) values ($1, 'cal test') returning id", uuid.UUID(TBL.DEMO_ACCOUNT_ID))
                item = await c.fetchval("insert into trip_items (trip_id, type, status, provider_name) values ($1, 'restaurant', 'requested', 'X') returning id", trip)
                before = await c.fetchval("select count(*) from calendar_outbox where trip_item_id = $1", item)
                await c.execute("update trip_items set status = 'confirmed' where id = $1", item)            # a writer
                await c.execute("update trip_items set provider_name = 'Y' where id = $1", item)            # not status
                await c.execute("update trip_items set status = 'confirmed' where id = $1", item)           # unchanged
                await c.execute("update trip_items set status = 'cancelled', updated_at = now() where id = $1", item)   # another writer's form
                rows = await c.fetch("select status from calendar_outbox where trip_item_id = $1 order by id", item)
                await c.execute("delete from trip_items where id = $1", item)
                await c.execute("delete from trips where id = $1", trip)
                return before, [r["status"] for r in rows]
            finally:
                await c.close()
        before, statuses = asyncio.run(go())
        self.assertEqual((before, statuses), (0, ["confirmed", "cancelled"]))


if __name__ == "__main__":
    unittest.main()
