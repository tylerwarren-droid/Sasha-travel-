"""Sasha 236 · S2 parity (EU 232 §2.1) + delete everything: the purge of an account's Keep and /s2 records; /s2's own words for
`book` (S1's untouched); the handover and trip cards drawn on /s2. Offline.

    cd backend && python -m unittest tests.test_s2_236 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from unittest import mock

from booking_signer import purge as PG

ACCT = "00000000-0000-4000-8000-000000000236"
run = asyncio.run
S2APP = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app", "s2", "S2App.tsx")


class Conn:
    def __init__(self, missing=()):
        self.sql, self.missing = [], set(missing)

    async def execute(self, q, *a):
        t = q.split("public.")[1].split()[0]
        if t in self.missing:
            raise type("UndefinedTableError", (Exception,), {})()
        self.sql.append((t, a))
        return "DELETE 2"


class Purge(unittest.TestCase):
    def go(self, conn):
        async def runner(fn):
            return await fn(conn)
        with mock.patch.object(PG, "RUN", runner):
            return run(PG.purge(ACCT))

    def test_every_table_by_the_account(self):
        c = Conn()
        counts = self.go(c)
        self.assertEqual(list(counts), ["keep_fills", "keep_items", "keep_keys", "s2_acts", "s2_wa_replies", "s2_wa_contacts", "s2_memory"])
        self.assertTrue(all(n == 2 for n in counts.values()))
        self.assertTrue(all(a == (uuid.UUID(ACCT),) for _, a in c.sql))          # scoped to this account only

    def test_a_table_not_applied_counts_zero(self):
        counts = self.go(Conn(missing={"s2_memory"}))
        self.assertEqual(counts["s2_memory"], 0)

    def test_this_process_forgets_them_too(self):
        from agapi import s2_memory as MEM, s2_records as REC
        MEM._MEM[ACCT] = {"thing": "x"}
        REC.ACTS.append({"account_id": ACCT, "kind": "email"})
        self.go(Conn())
        self.assertNotIn(ACCT, MEM._MEM)
        self.assertFalse([r for r in REC.ACTS if r.get("account_id") == ACCT])

    def test_the_accounts_own_delete_calls_it(self):
        src = open(os.path.join(os.path.dirname(PG.__file__), "vault", "gdpr.py")).read()
        self.assertIn("counts.update(await PG.purge(account))", src)

    def test_the_migration_cascades_all_six(self):
        sql = open(os.path.join(os.path.dirname(PG.__file__), "sql", "042_account_purge.sql")).read()
        for t in ("keep_fills", "keep_items", "keep_keys", "s2_acts", "s2_wa_replies", "s2_wa_contacts"):
            self.assertIn(f"alter table public.{t:<15}"[:len(f"alter table public.{t}")], sql)
            self.assertIn(f"{t}_account_fkey", sql)
        self.assertEqual(sql.count("references auth.users(id) on delete cascade"), 6)


class FlightNumber(unittest.TestCase):
    def test_the_airline_code_isnt_doubled(self):   # found live: "Flight: EXEX123"
        from agapi.s2_fine_print import flight_number
        self.assertEqual(flight_number("EX", "EX123"), "123")
        self.assertEqual(flight_number("EX", "ex 123"), "123")
        self.assertEqual(flight_number("EX", "123"), "123")
        self.assertEqual(flight_number("IB", "EX123"), "EX123")   # another airline's code is left alone

    def test_bag_check_says_to_claim_through_the_tool(self):
        src = open(__import__("agapi.s2_fine_print", fromlist=["x"]).__file__).read()
        self.assertIn("When they want to claim, CALL file_bag_claim", src)


class BookSaysThisScreen(unittest.TestCase):
    def test_s2_book_is_its_own_s1_untouched(self):
        from agapi import v0 as API
        from app.agent import s2 as S2
        self.assertIn("sent to their phone", API.BY_NAME["book"]["description"])     # S1's own words, unchanged
        self.assertIn("the pay card on this screen", S2.S2_BOOK)
        src = open(os.path.join(os.path.dirname(S2.__file__), "sasha.py")).read()
        self.assertIn('"description": S2.S2_BOOK} if t["name"] == "book"', src)


@unittest.skipUnless(os.path.exists(S2APP), "the frontend isn't beside the backend here")
class S2Draws(unittest.TestCase):
    def test_handover_and_the_trip(self):
        src = open(S2APP, encoding="utf-8").read()
        self.assertIn("ev.kind === 'handover'", src)
        self.assertIn("Tap to finish", src)
        self.assertIn("<TripPanel", src)                                               # S1's board itself, on the same records
        for k in ("flights", "stays", "flight_chosen", "total", "trip", "trip_changed"):
            self.assertIn(f"'{k}'", src)


if __name__ == "__main__":
    unittest.main()
