"""Sasha 256 item 2 · T34 — ONE ROUTE FOR EVERY FAMILY, MONEY INCLUDED. live vs the sandbox is decided only in agapi_route
(target_for / client_for, by the person). Before: s2_fine_print.target() picked its own AgAPI — AR.route("money") / AR.route(family)
/ AR.money_target — so a TEST person's card, entry and activity calls went to LIVE under production's route table (every family
=live); s2_subscriptions, fine print's moment() and accident_photo() did the same. Now every new case opens where target_for says for
THAT person. Two named exceptions: person_access reads the record on LIVE (the record lives there), and a case already open keeps
the AgAPI it was opened on (_MONEY_AT / _CASE_AT).

    cd backend && python -m unittest tests.test_s256_one_route -v
"""
from __future__ import annotations

import asyncio
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from agapi import agapi_route as AR, person_access as PA, s2_fine_print as FP, s2_memory as M, s2_subscriptions as SUBS

TEST, REAL = "00000000-0000-4000-8000-000000000256", "00000000-0000-4000-8000-000000000257"
PROD = {"SASHA_AGAPI_ROUTE": "activities=live,entry=live,cards=live,subscriptions=live,money=live,venues=live",
        "SASHA_OUTCOMES_VIA": "live", "SASHA_AGAPI_KEY": "", "SASHA_AGAPI_TEST_KEY": ""}
ROOT = Path(__file__).resolve().parents[1]

# ── the source scan: who may decide a target ───────────────────────────────────────────────────────────────────────────────────
#: deciding a target outside agapi_route: the family's route, the money rule, an endpoint by name, a fixed using("live"/"sandbox"),
#: a hard-coded AgAPI host, or the URL/key variables read directly
DECIDES = re.compile(r"""\b_?AR\.(?:route|money_target|endpoint|_in_their_basket|person_mode)\(|agapi_route\.(?:route|money_target|endpoint)\("""
                     r"""|\busing\(\s*["'](?:live|sandbox)["']\)|agapi-(?:live|sandbox)-production|getenv\(\s*["']SASHA_AGAPI_(?:TEST_)?(?:URL|KEY)["']"""
                     r"""|getenv\(\s*["']SASHA_\w+_VIA["']""")
#: the allowed exceptions, by file and the exact decision
ALLOWED = {("agapi/person_access.py", 'AR.endpoint("live")')}   # the access record lives on agapi-live, whatever the person's mode


def _scanned():
    for pat in ("agapi/*.py", "app/**/*.py", "booking_signer/**/*.py", "products/**/*.py", "scripts/*.py"):
        for p in ROOT.glob(pat):
            rel = str(p.relative_to(ROOT))
            if p.name == "agapi_route.py" or rel.startswith("agapi/booking_rules/"):
                continue
            yield rel, p


class OnlyTheRouteDecides(unittest.TestCase):
    def test_no_module_but_agapi_route_decides_a_target(self):
        bad = []
        for rel, p in _scanned():
            for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                code = line.split("#", 1)[0]
                m = DECIDES.search(code)
                if m and not any(rel == f and a in code for f, a in ALLOWED):
                    bad.append(f"{rel}:{i}: {m.group(0)}")
        self.assertEqual(bad, [], "only agapi_route decides live vs the sandbox (target_for / client_for)")

    def test_the_scan_sees_what_it_forbids(self):
        for line in ('return AR.route("cards")', 'await AR.money_target(a, f)', 'with AR.using("live"):', 'u = "https://agapi-live-production.up.railway.app"',
                     'os.getenv("SASHA_AGAPI_TEST_URL")', 'os.getenv("SASHA_FINE_PRINT_VIA", "sandbox")', 'AR.endpoint("sandbox")'):
            self.assertTrue(DECIDES.search(line), line)
        for line in ('await AR.target_for("cards", account)', 'await AR.client_for("venues", account)', 'with AR.using(t):',
                     'os.getenv("SASHA_S2_VIA_AGAPI", "0")', 'await self.page.route("**/*", gate)'):
            self.assertFalse(DECIDES.search(line), line)

    def test_the_exceptions_are_still_there_and_named(self):
        src = (ROOT / "agapi/person_access.py").read_text()
        self.assertIn('AR.endpoint("live")', src)
        fp = (ROOT / "agapi/s2_fine_print.py").read_text()
        self.assertIn("_MONEY_AT.get(account) or await AR.target_for(\"money\", account)", fp)
        self.assertIn("_CASE_AT[f\"{case}|{account}\"]", fp)


# ── the behaviour: a test person's calls from fine print and subscriptions reach the sandbox; a live person's follow the route ──

class ByThePerson(unittest.TestCase):
    def setUp(self):
        PA.clear()
        AR._MODE.clear()
        PA.install({TEST: {"mode": "test"}, REAL: PA.LIVE_PERSON})
        self.seen = []

        async def fp_run(ctx, name, args):
            self.seen.append((name, AR.current("cards"), FP.via()))
            return {"ok": True, "result": {}}

        async def subs_run(ctx, name, args):
            self.seen.append((name, AR.current("subscriptions"), SUBS.via()))
            return {"ok": True, "result": {}}

        async def nothing(*a, **k):
            return None

        async def not_in_basket(*a, **k):
            return False

        for p in (mock.patch.dict(os.environ, PROD), mock.patch.object(FP, "_run_tool", fp_run), mock.patch.object(SUBS, "_run_tool", subs_run),
                  mock.patch.object(FP, "_hydrate", nothing), mock.patch.object(FP, "_persist", nothing),
                  mock.patch.object(M, "kind", nothing), mock.patch.object(M, "put_kind", nothing),
                  mock.patch.object(AR, "_in_their_basket", not_in_basket),
                  mock.patch.dict(FP._MONEY_AT, {}, clear=True), mock.patch.dict(FP._CASE_AT, {}, clear=True),
                  mock.patch.dict(FP._ACCIDENT, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(PA.clear)
        self.addCleanup(AR._MODE.clear)

    class Ctx:
        def __init__(self, account):
            self.account, self.user_said = account, ""

    def where(self, account, name, args=None, module=FP):
        self.seen.clear()
        asyncio.run(module.run_tool(self.Ctx(account), name, args or {}))
        (_, current, via), = self.seen
        self.assertEqual(current, via)   # the tool's nested calls share one target (`using`)
        return current

    REAL_FLIGHT = {"flight": {"airline": "IB", "number": "3101", "date": "2026-10-01"}}
    TOOLS = [(FP, "flight_money_back", REAL_FLIGHT), (FP, "bag_money_back", {"bag": {"airline": "IB", "number": "3101"}}),
             (FP, "file_flight_claim", {}), (FP, "money_claim_status", {}), (FP, "rental_cover", {"country": "PT"}),
             (FP, "my_cards", {}), (FP, "accident", {"country": "PT"}), (FP, "entry_documents", {"country": "US"}),
             (FP, "prepare_entry", {}), (FP, "suggest_activities", {"city": "Lisbon"}),
             (SUBS, "find_subscriptions", {}), (SUBS, "cancel_subscription", {})]

    def test_a_test_person_reaches_the_sandbox_in_every_family(self):
        for module, name, args in self.TOOLS:
            self.assertEqual(self.where(TEST, name, args, module), "sandbox", name)

    def test_a_live_person_follows_the_route(self):
        for module, name, args in self.TOOLS:
            self.assertEqual(self.where(REAL, name, args, module), "live", name)
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_ROUTE": "all=sandbox"}):
            for module, name, args in self.TOOLS:
                self.assertEqual(self.where(REAL, name, args, module), "sandbox", name)

    def test_a_live_persons_test_inventory_claim_is_still_the_sandbox(self):
        self.assertEqual(self.where(REAL, "flight_money_back", {"flight": {"airline": "EX", "number": "1"}}), "sandbox")

    def test_an_open_case_stays_where_it_opened(self):
        FP._MONEY_AT[TEST] = "live"            # opened on live (before this change, or before their mode moved)
        FP._CASE_AT[f"claim|{TEST}"] = "live"
        FP._MONEY_AT[REAL] = "sandbox"
        FP._CASE_AT[f"claim|{REAL}"] = "sandbox"
        for name in ("file_flight_claim", "file_bag_claim", "money_claim_status"):
            self.assertEqual(self.where(TEST, name), "live", name)
            self.assertEqual(self.where(REAL, name), "sandbox", name)
        for name in ("file_claim", "claim_status"):
            self.assertEqual(self.where(TEST, name), "live", name)
            self.assertEqual(self.where(REAL, name), "sandbox", name)
        # a NEW money check is a new case: it opens by the person, not on the old case's AgAPI
        self.assertEqual(self.where(TEST, "flight_money_back", self.REAL_FLIGHT), "sandbox")

    def test_moment_and_accident_photo_follow_the_person(self):
        seen = []

        async def call(op, body, approval=None):
            seen.append((op, AR.current("cards")))
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "usr_1"}}
            return {"ok": True, "result": {"speak": False}}

        with mock.patch.object(FP, "CALL", call), mock.patch.dict(FP._USERS, {}, clear=True):
            asyncio.run(FP.moment(TEST, {"kind": "pickup_tomorrow"}))
            self.assertEqual({t for _, t in seen}, {"sandbox"})
            seen.clear()
            asyncio.run(FP.moment(REAL, {"kind": "pickup_tomorrow"}))
            self.assertEqual({t for _, t in seen}, {"live"})
            seen.clear()
            FP._ACCIDENT[TEST] = "acc_1"
            asyncio.run(FP.accident_photo(TEST, "front", "image/jpeg", "AA=="))
            self.assertEqual({t for _, t in seen}, {"sandbox"})
            seen.clear()
            FP._CASE_AT[f"accident|{TEST}"] = "live"   # an accident opened on live keeps its photos there
            asyncio.run(FP.accident_photo(TEST, "front", "image/jpeg", "AA=="))
            self.assertEqual({t for _, t in seen}, {"live"})


if __name__ == "__main__":
    unittest.main()
