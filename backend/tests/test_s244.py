"""Sasha 244 · AgAPI per operation family: activities / entry / cards / subscriptions / money → live (SASHA_AGAPI_ROUTE), and a money
claim about TEST INVENTORY (Example Air, Duffel Airways, or a flight in the person's own Sasha basket — Duffel test, real airline
codes) always on the sandbox, its claim and status following the case."""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import agapi_route as AR

ACCOUNT = "7536a3f0-0000-4000-8000-000000000244"
LIVE = {"SASHA_AGAPI_ROUTE": "activities=live,entry=live,cards=live,subscriptions=live,money=live",
        "SASHA_FINE_PRINT_VIA": "", "SASHA_SUBSCRIPTIONS_VIA": ""}


class Table(unittest.TestCase):
    def test_per_family_with_the_old_switch_behind_it(self):
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_ROUTE": "activities=live, entry=live,bogus=live,cards=nonsense",
                                          "SASHA_FINE_PRINT_VIA": "", "SASHA_SUBSCRIPTIONS_VIA": "live"}):
            self.assertEqual((AR.route("activities"), AR.route("entry"), AR.route("cards"), AR.route("money"), AR.route("subscriptions")),
                             ("live", "live", "sandbox", "sandbox", "live"))

    def test_nothing_set_changes_nothing(self):
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_ROUTE": "", "SASHA_FINE_PRINT_VIA": "", "SASHA_SUBSCRIPTIONS_VIA": ""}):
            self.assertEqual({AR.route(f) for f in AR.FAMILIES}, {"sandbox"})

    def test_all_sandbox_in_one_line(self):
        with mock.patch.dict(os.environ, {**LIVE, "SASHA_AGAPI_ROUTE": LIVE["SASHA_AGAPI_ROUTE"] + ",all=sandbox"}):
            self.assertEqual({AR.route(f) for f in AR.FAMILIES}, {"sandbox"})


def _basket(rows):
    async def go(fn):
        class C:
            async def fetch(self, *a):
                return rows
        return await fn(C())
    return go


ROWS = [{"snapshot": json.dumps(json.dumps({"flights": "UX 1153", "owner": "Air Europa", "departs": "2026-11-14T10:25:00"})),
         "booking_reference": "TSTREF"}]


class MoneyByTheFlight(unittest.TestCase):
    def target(self, flight, ref=None, rows=ROWS, env=LIVE):
        from booking_signer import basket as BK
        with mock.patch.dict(os.environ, env), mock.patch.object(BK, "_go", _basket(rows)):
            return asyncio.run(AR.money_target(ACCOUNT, flight, ref))

    def test_example_air_is_the_sandbox(self):
        self.assertEqual(self.target({"airline": "EX", "number": "123"}), "sandbox")
        self.assertEqual(self.target({"airline": "ZZ", "number": "1"}), "sandbox")

    def test_a_flight_in_their_sasha_basket_is_test_inventory(self):
        self.assertEqual(self.target({"airline": "UX", "number": "1153", "date": "2026-11-14"}), "sandbox")
        self.assertEqual(self.target({"airline": "UX", "number": "UX1153"}), "sandbox")
        self.assertEqual(self.target({"airline": "IB", "number": "3170"}, ref="tstref"), "sandbox")

    def test_a_real_flight_is_live(self):
        self.assertEqual(self.target({"airline": "UX", "number": "1153", "date": "2026-12-01"}), "live")   # another day
        self.assertEqual(self.target({"airline": "IB", "number": "3170", "date": "2026-11-02"}), "live")

    def test_when_the_basket_cant_be_read_never_live(self):
        from booking_signer import basket as BK

        async def boom(fn):
            raise RuntimeError("db down")
        with mock.patch.dict(os.environ, LIVE), mock.patch.object(BK, "_go", boom):
            self.assertEqual(asyncio.run(AR.money_target(ACCOUNT, {"airline": "IB", "number": "3170"})), "sandbox")

    def test_money_sandbox_route_keeps_everything_on_the_sandbox(self):
        self.assertEqual(self.target({"airline": "IB", "number": "3170"}, env={**LIVE, "SASHA_AGAPI_ROUTE": "money=sandbox"}), "sandbox")


class FinePrintCallsGoWhereTheirFamilyGoes(unittest.TestCase):
    def setUp(self):
        from agapi import s2_fine_print as FP
        self.FP, self.sent = FP, []

        async def call(op, body, approval=None):
            self.sent.append((op, FP.via(), body.get("end_user")))
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "usr_" + ("L" if FP.via() == "live" else "S") * 26}}
            if op == "activities.suggest":
                return {"ok": True, "result": {"candidates": [], "say": "Nothing listed."}}
            if op == "money.flight_check":
                return {"ok": True, "result": {"case_id": "mcase_1", "say": "Delayed 4 hours: EUR 250.", "verdict": "owed", "rules": []}}
            if op == "money.flight_claim":
                return {"ok": False, "error": {"code": "approval_required", "details": {"read_back_id": "rb_1", "read_back": {"lines": ["File …"]}}}}
            if op == "sandbox.simulate_approval":
                return {"ok": True, "result": {"approval_id": "apv_1"}}
            raise AssertionError(op)
        for p in (mock.patch.object(FP, "CALL", call), mock.patch.dict(FP._USERS, {}, clear=True), mock.patch.dict(FP._MONEY, {}, clear=True),
                  mock.patch.dict(FP._MONEY_AT, {}, clear=True), mock.patch.dict(FP._PEND, {}, clear=True), mock.patch.dict(os.environ, LIVE)):
            p.start()
            self.addCleanup(p.stop)

    def run_tool(self, name, args):
        from agapi import v0 as API
        ctx = API.Ctx(account=ACCOUNT, user_said="yes", surface="s2", started=datetime.now(timezone.utc) + timedelta(seconds=1))
        return asyncio.run(self.FP.run_tool(ctx, name, args))

    def test_activities_on_live_with_a_live_end_user(self):
        self.run_tool("suggest_activities", {"city": "Lisbon", "date": "2026-10-24"})
        self.assertEqual([(op, t) for op, t, _ in self.sent], [("users.register", "live"), ("activities.suggest", "live")])

    def test_a_test_flight_claim_stays_on_the_sandbox_end_to_end(self):
        from booking_signer import basket as BK
        with mock.patch.object(BK, "_go", _basket(ROWS)):
            self.run_tool("flight_money_back", {"airline": "EX", "number": "EX123", "date": "2026-10-10", "from": "MAD", "to": "LIS",
                                                "what": "delayed", "arrival_delay_minutes": 240})
        self.assertEqual(self.FP._MONEY_AT[ACCOUNT], "sandbox")
        self.run_tool("file_flight_claim", {})   # the read-back
        self.FP._PEND[f"{ACCOUNT}|file_flight_claim"]["at"] = 0
        self.run_tool("file_flight_claim", {})   # their yes, a later turn: the sandbox's simulated approval
        self.assertEqual({t for op, t, _ in self.sent}, {"sandbox"})
        self.assertIn("sandbox.simulate_approval", [op for op, _, _ in self.sent])
        self.assertTrue(all(u == "usr_" + "S" * 26 for op, _, u in self.sent if u))


class SubscriptionsFollowTheirFamily(unittest.TestCase):
    def test_live_has_no_fake_inbox(self):
        from agapi import s2_subscriptions as SUBS, v0 as API, s2_gmail_receipts as GR
        sent = []

        async def call(op, body, approval=None):
            sent.append((op, SUBS.via()))
            return {"ok": True, "result": {"end_user_id": "usr_" + "L" * 26}}

        async def not_connected(account):
            return False
        with mock.patch.object(SUBS, "CALL", call), mock.patch.dict(SUBS._USERS, {}, clear=True), mock.patch.dict(os.environ, LIVE), \
                mock.patch.dict(SUBS._CONSENTED, {ACCOUNT: {"version": "x"}}), mock.patch.object(GR, "connected", not_connected):
            ctx = API.Ctx(account=ACCOUNT, user_said="", surface="s2", started=datetime.now(timezone.utc))
            r = asyncio.run(SUBS.run_tool(ctx, "find_subscriptions", {"from_gmail": True}))
        self.assertEqual(r["error"]["code"], "gmail_not_connected")
        self.assertEqual(sent, [("users.register", "live")])


if __name__ == "__main__":
    unittest.main()
