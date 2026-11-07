"""Sasha 355 · ONE INBOUND MESSAGE IS HANDLED EXACTLY ONCE: each message's processing steps in a record of their own
(guest_message_steps, sql/058), keyed as written; the check fails CLOSED on a database error, named.

    cd backend && python -m unittest tests.test_s355_one_message_once -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import pathlib
import tempfile
import unittest
import uuid
from unittest import mock

from agapi import venue_submit as VS
from booking_signer import guest_whatsapp as GW, inbound_phone as IP

run = asyncio.run
SQL = pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql"
SID = "SM" + "ab12" * 8   # a real Twilio SID's shape
TYLER = "+34600000001"


class TheSteps(unittest.TestCase):
    def setUp(self):
        GW._SEEN_STEPS.clear()

    def test_each_step_once(self):
        with mock.patch.object(GW, "STORE", None):
            self.assertTrue(run(GW.first_step(SID, "agapi_in")))
            self.assertFalse(run(GW.first_step(SID, "agapi_in")))                       # a Twilio retry
            self.assertFalse(run(GW.step_done(SID, "agapi_took")))
            self.assertTrue(run(GW.first_step(SID, "agapi_took")))
            self.assertTrue(run(GW.step_done(SID, "agapi_took")))
        with self.assertRaises(ValueError):
            run(GW.first_step(SID, "agapi-in:anything"))                                 # steps are named, never derived keys

    def test_a_database_error_fails_closed_and_is_named(self):
        async def broken(fn):
            raise ConnectionError("the database is away")
        with mock.patch.object(GW, "STORE", mock.Mock(_run=broken)), self.assertLogs("booking_signer.guest_whatsapp", "ERROR") as logs:
            self.assertFalse(run(GW.first_step(SID, "agapi_in")))                       # never handed on again
            self.assertFalse(run(GW.step_done(SID, "agapi_took")))
        self.assertTrue(any("NOT recorded (ConnectionError" in l and "fails closed" in l for l in logs.output))


class ThroughTheWebhook(unittest.TestCase):
    """A Twilio retry of a message AgAPI took never reaches AgAPI twice, and nothing else answers it."""

    def setUp(self):
        GW._SEEN_SIDS.clear(); GW._SEEN_STEPS.clear()

    def deliver(self, matched):
        p = {"From": f"whatsapp:{TYLER}", "To": "whatsapp:+447700900000", "Body": "investigate Acme", "MessageSid": SID}
        handed, flow = [], []

        async def inbound(s, t, message_id=None, guest=False, twilio=None):
            handed.append(message_id)
            return {"matched": matched}

        async def dispatch(p_, call_for):
            flow.append(p_["Body"])
            return ""

        class Store:
            async def call_for_number(self, n, since):
                return None

            async def put(self, row):
                return True
        with mock.patch.object(IP, "_verified", mock.AsyncMock(return_value=p)), mock.patch.object(IP, "STORE", Store()), \
                mock.patch.object(GW, "STORE", None), mock.patch.object(VS, "whatsapp_inbound", inbound), \
                mock.patch.object(GW, "linked", mock.AsyncMock(return_value=True)), mock.patch.object(GW, "dispatch", dispatch):
            run(IP.sms(None))
        return handed, flow

    def test_a_retry_never_reaches_agapi_twice(self):
        self.assertEqual(self.deliver(True), ([SID], []))
        self.assertEqual(self.deliver(True), ([], []))                                  # the retry: AgAPI took it — stops here

    def test_the_webhook_writes_steps_never_derived_keys(self):
        src = inspect.getsource(IP._sms)
        self.assertIn('await GW.first_step(sid, "agapi_in")', src)
        self.assertIn('await GW.step_done(sid, "agapi_took")', src)
        for d in ("booking_signer", "agapi", "products", "app"):
            for f in (pathlib.Path(__file__).resolve().parents[1] / d).rglob("*.py"):
                s = f.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn('first_time(f"agapi-', s, f.name)
                self.assertNotIn('seen(f"agapi-', s, f.name)


PG, _SERVER = os.getenv("BOOKING_TEST_DATABASE_URL", ""), None
if not PG:
    try:
        import pgserver
        _SERVER = pgserver.get_server(tempfile.mkdtemp(prefix="s355pg"), cleanup_mode="stop")
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
class TheSqlOnPostgres(unittest.TestCase):
    def test_058_keyed_as_written_and_idempotent(self):
        import asyncpg
        from tests.test_s336_keep_owners import _block
        loop = asyncio.new_event_loop()
        go = loop.run_until_complete
        db = "s355_" + uuid.uuid4().hex[:8]
        admin = go(asyncpg.connect(PG)); go(admin.execute(f"create database {db}")); go(admin.close())
        c = go(asyncpg.connect(PG, database=db))
        try:
            for role in ("anon", "authenticated"):
                go(c.execute(f"do $$ begin create role {role}; exception when duplicate_object then null; end $$"))
            go(c.execute(_block("058_guest_message_steps.sql")))
            go(c.execute(_block("058_guest_message_steps.sql")))                            # twice: idempotent

            async def runner(fn):
                return await fn(c)
            with mock.patch.object(GW, "STORE", mock.Mock(_run=runner)):
                self.assertTrue(go(GW.first_step(SID, "agapi_in")))
                self.assertFalse(go(GW.first_step(SID, "agapi_in")))
                self.assertTrue(go(GW.first_step(SID, "agapi_took")))
                self.assertTrue(go(GW.step_done(SID, "agapi_took")))
                with self.assertLogs("booking_signer.guest_whatsapp", "ERROR"):
                    self.assertFalse(go(GW.first_step("agapi-in:" + SID, "agapi_in")))     # a derived key: refused, and closed
            self.assertEqual(go(c.fetchval("select count(*) from guest_message_steps")), 2)
            self.assertFalse(go(c.fetchval("select has_table_privilege('anon', 'public.guest_message_steps', 'select')")))
        finally:
            go(c.close())
            admin = go(asyncpg.connect(PG)); go(admin.execute(f"drop database if exists {db}")); go(admin.close())
            loop.close()


if __name__ == "__main__":
    unittest.main()
