"""Sasha 253 · THE GATE NEVER WRITES TO LIVE (CR 91 found 21 gate rows on the live outcomes ledger: the gate's paid test trips are
finished by the production server, outside the gate's own pin). Live vs the sandbox is decided ONLY in agapi_route.client_for, by
the person's mode: a test person (every guest a suite or a proof makes — Sasha 254: no person_access row) → the sandbox, whoever calls.

    cd backend && python -m unittest tests.test_s253_gate_never_live -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from agapi import agapi_route as AR, s2_outcomes as OC

TEST, REAL = "00000000-0000-4000-8000-0000000002a1", "00000000-0000-4000-8000-0000000002a2"
GUEST = "00000000-0000-4000-8000-0000000002a3"   # a real public guest: no row, no test marker


def admin(meta):
    async def fn(method, path, body=None):
        acct = path.rsplit("/", 1)[-1]
        return 200, {"id": acct, "app_metadata": meta.get(acct, {})}
    return fn


class PersonMode(unittest.TestCase):
    """Sasha 254 item 5 · a person WITH a row: their record's mode. No row (a public guest, every suite guest) or an unreadable record:
    the guest's own marker (app_metadata.kanoe_test — every suite and scratch guest carries it) — a real guest's paid flows never land
    on test inventory."""

    def setUp(self):
        from agapi import person_access as PA
        self.PA = PA
        PA.clear()
        OC._DONE.clear()   # once per row per process: T23 and T29 both run this class
        self.r = mock.patch.object(PA, "RESOLVER", None)   # records only, never the old fixtures' meaning
        self.r.start()
        PA.install({REAL: PA.LIVE_PERSON})
        AR._MODE.clear()
        from booking_signer import ops
        self.admin = mock.patch.object(ops, "ADMIN", admin({TEST: {"kanoe_guest": True, "kanoe_test": True}, GUEST: {"kanoe_guest": True}}))
        self.admin.start()
        self.env = mock.patch.dict(os.environ, {"SASHA_AGAPI_ROUTE": "outcomes=live,venues=live,money=live", "SASHA_OUTCOMES_VIA": "live",
                                                "SASHA_AGAPI_KEY": ""})
        self.env.start()

    def tearDown(self):
        self.admin.stop()
        AR._MODE.clear()
        self.r.stop()
        self.env.stop()
        self.PA.clear()

    def test_a_test_person_goes_to_the_sandbox_in_every_family(self):
        for fam in ("outcomes", "venues", "money", "activities"):
            self.assertEqual(asyncio.run(AR.target_for(fam, TEST)), "sandbox", fam)

    def test_a_real_person_follows_the_route(self):
        self.assertEqual(asyncio.run(AR.target_for("outcomes", REAL)), "live")

    def test_nobody_named_follows_the_route(self):
        self.assertEqual(asyncio.run(AR.target_for("outcomes")), "live")

    def test_an_unreadable_record_falls_to_the_marker(self):
        async def broken(op, body):
            raise RuntimeError("agapi down")
        self.PA.uninstall(REAL)
        with mock.patch.object(self.PA, "CALL", broken):
            self.assertEqual(asyncio.run(AR.target_for("outcomes", REAL)), "live")    # a real person: never dropped to test
            self.assertEqual(asyncio.run(AR.target_for("outcomes", TEST)), "sandbox")  # a suite guest: still the sandbox

    def test_a_public_guest_with_no_row_follows_the_route(self):
        async def no_row(op, body):
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "usr_x"}}
            return {"ok": True, "result": {"mode": "test", "source": "closed"}}
        with mock.patch.object(self.PA, "CALL", no_row):
            for fam in ("money", "venues", "outcomes"):   # the routes this test sets live
                self.assertEqual(asyncio.run(AR.target_for(fam, GUEST)), "live", fam)

    def test_the_ledger_routes_by_the_person_even_from_a_background_writer(self):
        seen = []

        async def call(op, body):   # the ledger's one call — where would it go?
            seen.append(AR._ACCOUNT.get())
            seen.append(await AR.target_for("outcomes"))
            return {"ok": True, "result": {"outcome_id": "o1"}}
        with mock.patch.object(OC, "CALL", call):
            n = asyncio.run(OC.basket_booked(TEST, [{"id": "r1", "state": "booked", "kind": "flight", "booking_reference": "ZZ1",
                                                     "snapshot": {"owner": "Duffel Airways", "flights": "ZZ 1", "to_city": "Hanoi"}}]))
        self.assertEqual(n, 1)
        self.assertEqual(seen, [TEST, "sandbox"])


class SuiteGuestsAreTest(unittest.TestCase):
    def test_only_real_peoples_guests_are_live(self):
        from booking_signer import guest_accounts as GA
        self.assertEqual(GA.REAL_ORIGINS, ("web", "whatsapp"))
        made = []

        async def admin_post(method, path, body=None):
            made.append(body["app_metadata"])
            return 201, {"id": "x"}
        from booking_signer import ops
        with mock.patch.object(ops, "ADMIN", admin_post), mock.patch.object(GA, "allowed", lambda ip: None):
            for origin in ("venue-suite", "web", "whatsapp", "flight-suite"):
                try:
                    asyncio.run(GA.create_guest(origin))
                except Exception:
                    pass
        self.assertEqual([m.get("kanoe_test", False) for m in made], [True, False, False, True])


if __name__ == "__main__":
    unittest.main()
