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


class ErasureIsLogged(unittest.TestCase):
    def test_a_refused_rule_falls_back_to_all_never_unlogged(self):   # found live: 500 after the erasure had run
        from booking_signer.vault import gdpr as G
        from booking_signer import routes
        rows = []

        class C:
            async def execute(self, q, *a):
                if a[2] == "guest_erasure":
                    raise type("CheckViolationError", (Exception,), {})()
                rows.append((a[2], a[3], a[6]))

        async def runner(fn):
            return await fn(C())
        store = type("S", (), {"_run": staticmethod(runner)})()
        from datetime import datetime, timezone
        with mock.patch.object(routes, "STORE", store):
            run(G._log_deletion(ACCT, {"keep_items": 3, "s2_acts": 3}, datetime.now(timezone.utc)))
        self.assertEqual([(r, t) for r, t, _ in rows], [("all", "keep_items"), ("all", "s2_acts")])
        self.assertTrue(all(n.startswith("guest_erasure:") for _, _, n in rows))

    def test_the_migration_allows_guest_erasure(self):
        sql = open(os.path.join(os.path.dirname(PG.__file__), "sql", "042_account_purge.sql")).read()
        self.assertIn("'all', 'guest_erasure'", sql)


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


class SameReadBack(unittest.TestCase):
    """Found live on /s2: a page route's read-back carries a ONE-TIME forwarding address, so each hold looked new and the yes never
    answered a read-back they'd heard (she held again, and again)."""

    def test_hold_venue_keeps_the_superseded_hold_for_the_check(self):   # found live: hold_venue popped it before _hold could compare
        src = open(__import__("agapi.venues", fromlist=["x"]).__file__).read()
        self.assertIn("_PREV[ctx.account] = _HELD.pop(ctx.account, None)", src)
        self.assertIn("prev = _HELD.get(ctx.account) or _PREV.pop(ctx.account, None)", src)

    def test_the_one_yes_gate_binds_a_venue_by_its_words(self):
        from agapi import yes_gate as G
        a = G._current("book_venue", {"sha": "a" * 64, "same": "w" * 64})
        b = G._current("book_venue", {"sha": "b" * 64, "same": "w" * 64})
        self.assertEqual(a["payload"], b["payload"])                              # a new forwarding address: the same read-back
        self.assertNotEqual(G._current("book_venue", {"sha": "a" * 64, "same": "x" * 64})["payload"], a["payload"])
        self.assertEqual(G._current("send_email", {"sha": "c" * 64})["payload"], {"read_back_sha256": "c" * 64})   # others unchanged

    def test_held_again_keeps_its_time(self):
        from agapi import venues as VN, v0 as API
        lines = lambda u: ["Their Treatwell page: pick Saturday 17 October at 12:00, for 1.",
                           f"When the confirmation arrives, forward it to act-{u}@booking.kanoe.ai and I'll put it in your trip."]
        rd = {"venue": "Método Javier Panizo", "read_id": "r1"}
        res = {"when": {"at": "2026-10-17T12:00"}, "how_many": {"count": 1}, "who": {"name": "Alex"}}
        with mock.patch.dict(VN._HELD, {}, clear=True), mock.patch.object(VN, "_API", lambda: type("GW", (), {
                "summary": staticmethod(lambda r: "Sat 17 Oct 12:00, 1"), "guest_lines": staticmethod(lambda rung, l: l),
                "plain_venue": staticmethod(lambda v: v)})):
            ctx = API.Ctx(account=ACCT)
            VN._hold(ctx, "page", "l1", {"sha256": "a" * 64, "lines": lines(uuid.uuid4())}, rd, res)
            first = VN._HELD[ACCT]["at"]
            VN._hold(ctx, "page", "l2", {"sha256": "b" * 64, "lines": lines(uuid.uuid4())}, rd, res)
            self.assertEqual(VN._HELD[ACCT]["at"], first)                      # the same booking: the same time it was said
            from datetime import datetime, timedelta, timezone
            later = API.Ctx(account=ACCT, user_said="Yes, book it.", started=datetime.now(timezone.utc) + timedelta(seconds=5))
            out = VN._hold(later, "page", "l4", {"sha256": "d" * 64, "lines": lines(uuid.uuid4())}, rd, res)
            self.assertEqual(out["status"], "yes_heard")                       # held again in the turn of their yes: book now
            q = API.Ctx(account=ACCT, user_said="Is it free at 12?", started=datetime.now(timezone.utc) + timedelta(seconds=6))
            self.assertEqual(VN._hold(q, "page", "l5", {"sha256": "e" * 64, "lines": lines(uuid.uuid4())}, rd, res)["status"], "awaiting_yes")
            VN._hold(ctx, "page", "l3", {"sha256": "c" * 64, "lines": ["Another venue, another time."]}, rd, res)
            self.assertNotEqual(VN._HELD[ACCT]["at"], first)                   # different words: a new read-back


class PageOnThisScreen(unittest.TestCase):
    def test_not_sent_to_the_phone_is_never_said_to_be_there(self):   # found live: "Their Treatwell page is on your phone"
        src = open(__import__("agapi.venues", fromlist=["x"]).__file__).read()
        self.assertIn("Their page is on this screen — Tap to finish opens it. Never say it's on their phone.", src)


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
