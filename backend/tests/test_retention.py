"""S-53/S-54 · the retention job and the append-only opt-in table — on a throwaway Postgres (001–008 applied).

    cd backend && BOOKING_TEST_DATABASE_URL=… python -m unittest tests.test_retention -v
⚠ Without BOOKING_TEST_DATABASE_URL this suite is SKIPPED, and says so.
"""
import asyncio
import json
import os
import pathlib
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import urlsplit

from booking_signer import retention as RT

HERE = pathlib.Path(__file__).parent
SQL_DIR = HERE.parent / "booking_signer" / "sql"
PG_URL = os.getenv("BOOKING_TEST_DATABASE_URL", "")
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
ACCT = "11111111-1111-4111-8111-111111111111"
H64 = "a" * 64


def run(c):
    return asyncio.run(c)


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the retention suite did NOT run")
class Retention(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import asyncpg
        if "test" not in urlsplit(PG_URL).path.lstrip("/"):
            raise unittest.SkipTest("refusing a database whose name does not contain 'test'")

        async def fresh():
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute("drop schema if exists auth cascade; drop schema public cascade; create schema public;")
                await c.execute((HERE / "fixtures" / "model_a_live_2026-09-28.sql").read_text(encoding="utf-8"))
                for f in ("001_booking_storage.sql", "002_prepared_status.sql", "003_phone_calls.sql", "004_ladder.sql",
                          "005_slot_links.sql", "007_retention_log.sql", "008_venue_optins.sql", "009_venue_optin_requests.sql"):
                    await c.execute((SQL_DIR / f).read_text(encoding="utf-8"))
            finally:
                await c.close()
        run(fresh())

    def q(self, fn):
        async def go():
            import asyncpg
            c = await asyncpg.connect(PG_URL, statement_cache_size=0)
            await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
            try:
                return await fn(c)
            finally:
                await c.close()
        return run(go())

    def setUp(self):
        async def wipe(c):
            await c.execute("set booking.retention = 'on'; delete from venue_optins; reset booking.retention; delete from venue_optin_requests;"
                            "delete from retention_log; delete from booking_attempts; delete from booking_calls; delete from trip_items; delete from trips;")
        self.q(wipe)

    def item(self, when: datetime, sasha: bool, read_at=None, words=None) -> str:
        async def mk(c):
            tid = await c.fetchval("insert into trips (owner_id, title) values ($1, 'Sasha bookings') returning id", uuid.UUID(ACCT))
            iid = await c.fetchval("insert into trip_items (trip_id, type, status, provider_name, date_time, local_timezone, party_size) "
                                   "values ($1,'restaurant','confirmed','V',$2,'Europe/Madrid',2) returning id", tid, when)
            if sasha:
                await c.execute(
                    "insert into booking_calls (call_id, account_id, trip_item_id, venue_key, dialled_number, language, guest_name, brief, "
                    "brief_sha256, read_back_lines, read_back_sha256, status, created_at, outcome, venue_words, bland_details, reading, read_at) "
                    "values ($1,$2,$3,'v','+34910000000','es','T',$4,$5,$6,$5,'answered',$7,'yes',$8,$9,$10,$11)",
                    uuid.uuid4(), uuid.UUID(ACCT), iid, {"purpose": "book"}, H64, ["l"], when - timedelta(days=5),
                    words, {"transcripts": ["t"]} if words else None, {"quote": "q", "raised": [], "outcome": "yes"}, read_at)
            return str(iid)
        return self.q(mk)

    def optin(self, venue, status, when, **kw):
        async def mk(c):
            await c.execute(
                "insert into venue_optins (venue_id, channel, scope, status, recorded_at, agreed_at, method, wording_version, wording_sha256, "
                "wording_text, evidence, withdrawn_at, withdrawn_how) values ($1,'whatsapp','+34600000000',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                venue, status, when, when if status == "active" else None, "whatsapp_inbound" if status == "active" else None,
                "v2" if status == "active" else None, H64 if status == "active" else None, "I agree…" if status == "active" else None,
                {"message_id": "m"} if status == "active" else None, when if status == "withdrawn" else None,
                "STOP" if status == "withdrawn" else None)
        self.q(mk)

    def count(self, sql, *a):
        return self.q(lambda c: c.fetchval(sql, *a))

    def go(self):
        return self.q(lambda c: RT.run_once(c, NOW))

    def test_an_old_sasha_booking_goes_and_a_non_sasha_trip_item_stays(self):
        old = self.item(NOW - timedelta(days=800), sasha=True)
        other = self.item(NOW - timedelta(days=800), sasha=False)
        recent = self.item(NOW - timedelta(days=30), sasha=True)
        self.go()
        left = {str(r["id"]) for r in self.q(lambda c: c.fetch("select id from trip_items"))}
        self.assertNotIn(old, left)
        self.assertIn(other, left)
        self.assertIn(recent, left)
        self.assertEqual(self.count("select count(*) from booking_calls"), 1)

    def test_transcripts_older_than_12_months_are_emptied_and_the_record_stays(self):
        self.item(NOW + timedelta(days=10), sasha=True, read_at=NOW - timedelta(days=400), words="Sí, perfecto.")
        self.item(NOW + timedelta(days=10), sasha=True, read_at=NOW - timedelta(days=30), words="Vale.")
        self.go()
        rows = self.q(lambda c: c.fetch("select venue_words, bland_details, reading, outcome from booking_calls order by read_at"))
        self.assertEqual((rows[0]["venue_words"], rows[0]["bland_details"], rows[0]["outcome"]), (None, None, "yes"))
        self.assertNotIn("quote", rows[0]["reading"])
        self.assertEqual(rows[1]["venue_words"], "Vale.")

    def test_consent_an_active_opt_in_is_never_touched_and_old_withdrawals_go(self):
        self.optin("ancient-active", "active", NOW - timedelta(days=3000))                 # active for 8 years: stays
        self.optin("gone", "active", NOW - timedelta(days=2000))
        self.optin("gone", "withdrawn", NOW - timedelta(days=1500))                        # withdrawn 4 years ago: the chain goes
        self.optin("recent-stop", "active", NOW - timedelta(days=900))
        self.optin("recent-stop", "withdrawn", NOW - timedelta(days=365))                  # withdrawn 1 year ago: stays
        self.optin("back", "active", NOW - timedelta(days=2000))
        self.optin("back", "withdrawn", NOW - timedelta(days=1800))
        self.optin("back", "active", NOW - timedelta(days=100))                            # re-opted in: latest is active, stays
        self.go()
        venues = [r["venue_id"] for r in self.q(lambda c: c.fetch("select distinct venue_id from venue_optins order by 1"))]
        self.assertEqual(venues, ["ancient-active", "back", "recent-stop"])
        self.assertEqual(self.count("select count(*) from venue_optins where venue_id = 'back'"), 3)

    def test_the_table_is_append_only(self):
        self.optin("v", "active", NOW)
        import asyncpg
        with self.assertRaisesRegex(asyncpg.exceptions.RaiseError, "append-only"):
            self.q(lambda c: c.execute("update venue_optins set scope = 'x'"))
        with self.assertRaisesRegex(asyncpg.exceptions.RaiseError, "only the retention job may delete"):
            self.q(lambda c: c.execute("delete from venue_optins"))

    def test_every_run_is_logged_and_the_periods_are_config(self):
        self.item(NOW - timedelta(days=800), sasha=True)
        with mock.patch.dict(os.environ, {"RETENTION_BOOKINGS_MONTHS": "48"}):
            self.go()
        self.assertEqual(self.count("select count(*) from trip_items"), 1)                 # 26 months old < 48: kept
        self.assertGreater(self.count("select count(*) from retention_log"), 10)
        self.go()
        self.assertEqual(self.count("select count(*) from trip_items"), 0)                 # back to 24: gone
        self.assertEqual(self.count("select sum(rows_affected) from retention_log where rule = 'bookings' and table_name = 'trip_items'"), 1)

    def test_a_page_request_never_confirmed_goes_30_days_after_its_link_expired_and_a_confirmed_one_stays(self):
        async def mk(c, n, expired_days_ago, confirmed):
            exp = NOW - timedelta(days=expired_days_ago)
            await c.execute(
                "insert into venue_optin_requests (request_id, token_sha256, created_at, expires_at, lang, venue_id, venue_name, "
                "contact_name, contact_role, email, channels, submitted, email_status, confirmed_at) "
                "values ($1,$2,$3,$4,'en','host:v.test','V','N','owner','n@v.test',$5,$6,'sent',$7)",
                uuid.uuid4(), f"{n:064x}", exp - timedelta(hours=48), exp, [], {}, (exp - timedelta(hours=1)) if confirmed else None)
        self.q(lambda c: mk(c, 1, 40, False))    # never confirmed, expired 40 days ago: goes
        self.q(lambda c: mk(c, 2, 10, False))    # never confirmed, expired 10 days ago: stays for now
        self.q(lambda c: mk(c, 3, 400, True))    # confirmed: its link is how the venue withdraws — stays
        self.go()
        left = [r["token_sha256"][-1] for r in self.q(lambda c: c.fetch("select token_sha256 from venue_optin_requests order by 1"))]
        self.assertEqual(left, ["2", "3"])
        self.assertEqual(self.count("select rows_affected from retention_log where rule = 'consent' and table_name = 'venue_optin_requests'"), 1)

    def test_without_the_log_table_nothing_is_deleted(self):
        self.item(NOW - timedelta(days=800), sasha=True)
        self.q(lambda c: c.execute("alter table retention_log rename to retention_log_away"))
        try:
            out = self.go()
        finally:
            self.q(lambda c: c.execute("alter table retention_log_away rename to retention_log"))
        self.assertIn("retention_log missing", out[0]["note"])
        self.assertEqual(self.count("select count(*) from trip_items"), 1)


if __name__ == "__main__":
    unittest.main()
