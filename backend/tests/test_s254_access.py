"""Sasha 254 item 5 · ACCESS FROM THE ONE RECORD (CR 92, mailbox row 823): every founder / calls / mailbox / demo / real-venue /
mode decision reads AgAPI's person_access record (agapi.person_access → access.get on agapi-live), cached ≤ 60 s, closed on any
failure. Tyler and Jon are live through the record; a scratch account (no row) is test. No network: the transport is replaced.

    cd backend && python -m unittest tests.test_s254_access -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import pathlib
import re
import unittest
from unittest import mock

from agapi import person_access as PA

TYLER = "00000000-0000-4000-8000-0000000254a1"
JON = "00000000-0000-4000-8000-0000000254a2"
INVITED = "00000000-0000-4000-8000-0000000254a3"   # tylerwarren+eu234 / falguni: invited, test, everything off
SCRATCH = "00000000-0000-4000-8000-0000000254a4"   # a suite guest: no row

#: what access.get answers on agapi-live today (row 823), as the wire carries it
WIRE = {TYLER: {"mode": "live", "calls": "on", "real_venue_sends": "on", "mailboxes": ["gmail", "outlook"], "real_money": "off",
                "founder": True, "demo": None, "source": "person_access"},
        JON: {"mode": "live", "calls": "on", "real_venue_sends": "on", "mailboxes": ["gmail", "outlook"], "real_money": "off",
              "source": "person_access"},
        INVITED: {"mode": "test", "calls": "off", "real_venue_sends": "off", "mailboxes": [], "real_money": "off",
                  "source": "person_access"}}


def run(c):
    return asyncio.run(c)


class Wire:
    """agapi-live as the reader sees it: users.register then access.get. No row → the record's closed answer."""

    def __init__(self, records=None, fail=None):
        self.records, self.fail, self.calls = dict(records or WIRE), fail, []

    async def __call__(self, op, body):
        self.calls.append(op)
        if self.fail == "raise":
            raise RuntimeError("down")
        if self.fail == "error":
            return {"ok": False, "error": {"code": "unavailable", "message": "x", "retryable": True}}
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "usr_" + body["external_ref"].split(":", 1)[1]}}
        if op == "access.get":
            acct = body["end_user"][4:]
            return {"ok": True, "result": self.records.get(acct) or {**PA.CLOSED, "mailboxes": [], "source": "closed"}}
        return {"ok": False, "error": {"code": "unknown"}}


class Base(unittest.TestCase):
    def setUp(self):
        PA.clear()
        self.patches = [mock.patch.object(PA, "RESOLVER", None), mock.patch.dict(os.environ, {"SASHA_AGAPI_KEY": "", "SASHA_SWITCHING": ""})]
        for p in self.patches:
            p.start()
        self.wire = Wire()
        self.call = mock.patch.object(PA, "CALL", self.wire)
        self.call.start()
        from agapi import agapi_route as AR
        from booking_signer import ops
        AR._MODE.clear()

        async def admin(method, path, body=None):   # the guest marker (no row): a suite guest carries kanoe_test
            return 200, {"app_metadata": {"kanoe_test": True} if path.endswith(SCRATCH) else {}}
        self.admin = mock.patch.object(ops, "ADMIN", admin)
        self.admin.start()

    def tearDown(self):
        self.admin.stop()
        self.call.stop()
        for p in reversed(self.patches):
            p.stop()
        PA.clear()

    def read(self, *accts):
        for a in accts:
            run(PA.warm(a))


class TheRecordGrantsEachPower(Base):
    def test_tyler_and_jon_are_live_through_the_record(self):
        from app.services import accounts as AC
        self.read(TYLER, JON, INVITED, SCRATCH)
        for a in (TYLER, JON):
            r = PA.cached(a)
            self.assertEqual((r["mode"], r["calls"], r["real_venue_sends"], r["mailboxes"], r["real_money"], r["source"]),
                             ("live", "on", "on", ["gmail", "outlook"], "off", "person_access"), a)
            for power in ("calls", "gmail", "outlook", "real_venue_sends"):
                self.assertTrue(AC.has(a, power), (a, power))
        self.assertTrue(AC.is_founder(TYLER))
        self.assertFalse(AC.is_founder(JON))
        for a in (INVITED, SCRATCH):   # invited (test, everything off) and a scratch guest (no row): nothing
            self.assertEqual(PA.cached(a)["mode"], "test")
            self.assertFalse(any(AC.has(a, p) for p in AC.POWERS), a)

    def test_each_reader_maps_to_its_field(self):
        from booking_signer import guest_accounts as GA, guest_whatsapp as GW, ladder_routes as LR, limits as LM, mailbox as MB
        from booking_signer import outlook as OL, switching as SW, handover as HO
        from agapi import s2_tools as S2
        with PA.records({"c": {"calls": "on"}, "g": {"mailbox": "gmail"}, "o": {"mailboxes": "outlook"}, "d": {"demo": "s2_demo"},
                         "r": {"demo": "founder_rehearsal"}, "f": {"founder": True}, "v": {"mode": "live", "real_venue_sends": "on"},
                         "vt": {"mode": "test", "real_venue_sends": "on"}}):
            self.assertEqual([a for a in "cgodrfv" if LM.calls_on(a)], ["c"])
            self.assertEqual([a for a in "cgodrfv" if MB.invited(a)], ["g"])
            self.assertEqual([a for a in "cgodrfv" if OL.invited(a)], ["o"])
            self.assertEqual([a for a in "cgodrfv" if LR._s2_demo_account(a)], ["d"])
            self.assertEqual([a for a in "cgodrfv" if LR.standin(a)], ["r"])
            self.assertEqual([a for a in "cgodrfv" if GW.rehearsal(a)], ["r"])
            for rule in (GA.founder, LM.exempt, SW.on, HO.founder_override):
                self.assertEqual([a for a in "cgodrfv" if rule(a)], ["f"], rule.__name__)
            self.assertEqual([a for a in ("c", "f", "v", "vt") if GA.real_venue_sends(a)], ["v"])   # mode live AND sends on
            self.assertEqual([a for a in ("c", "f", "v", "vt") if S2.live_for(a)], ["v"])
            with mock.patch.dict(os.environ, {"SASHA_SWITCHING": "all"}):   # the global kill switch, never a person list
                self.assertTrue(SW.on("c"))

    def test_the_founders_email_is_his_records(self):
        from app.services import accounts as AC
        with mock.patch.object(AC, "founder_account", lambda: TYLER), PA.records({TYLER: {**PA.FOUNDER_PERSON, "email": "T@X.test"}}):
            self.assertEqual(AC.founder_email(), "t@x.test")
        with mock.patch.object(AC, "founder_account", lambda: TYLER), PA.records({TYLER: PA.LIVE_PERSON}):   # not founder: none
            self.assertIsNone(AC.founder_email())


class ClosedOnFailure(Base):
    def test_any_failure_is_closed_and_not_cached(self):
        t = [1000.0]
        with mock.patch.object(PA.time, "time", lambda: t[0]):
            for fail in ("raise", "error"):
                PA.clear()
                self.wire.fail, self.wire.calls = fail, []
                self.assertEqual(run(PA.get(TYLER)), PA.closed(), fail)
                self.assertEqual(PA.cached(TYLER), PA.closed())
                self.wire.fail = None
                n = len(self.wire.calls)
                self.assertEqual(run(PA.get(TYLER)), PA.closed(), "a moment later: still closed, no call")
                self.assertEqual(len(self.wire.calls), n)
                t[0] += PA.FAILED_TTL_S + 1
                self.assertEqual(run(PA.get(TYLER))["mode"], "live", "read again after FAILED_TTL_S")

    def test_no_key_no_network_closed(self):
        self.call.stop()
        try:
            with mock.patch("httpx.AsyncClient", side_effect=AssertionError("no network without a key")):
                self.assertEqual(run(PA.get(TYLER)), PA.closed())
        finally:
            self.call.start()

    def test_nobody_and_malformed_are_closed(self):
        self.assertEqual(run(PA.get(None)), PA.closed())
        self.assertEqual(PA.normalise("x"), PA.closed())
        self.assertEqual(PA.normalise({"mode": "LIVE?", "calls": "maybe"})["mode"], "test")


class TheCache(Base):
    def test_cached_at_most_60_seconds(self):
        self.assertLessEqual(PA.TTL_S, 60)
        t = [1000.0]
        with mock.patch.object(PA.time, "time", lambda: t[0]):
            run(PA.get(JON))
            run(PA.get(JON))
            self.assertEqual(self.wire.calls, ["users.register", "access.get"])
            t[0] += PA.TTL_S - 1
            self.assertEqual(PA.cached(JON)["mode"], "live")
            t[0] += 2
            self.assertEqual(PA.cached(JON), PA.closed())                          # stale: closed until read again
            run(PA.get(JON))
            self.assertEqual(self.wire.calls, ["users.register", "access.get", "access.get"])   # the end user is kept

    def test_the_end_user_is_sashas(self):
        seen = []

        async def wire(op, body):
            seen.append((op, body))
            return await Wire()(op, body)
        with mock.patch.object(PA, "CALL", wire):
            run(PA.get(JON))
        self.assertEqual(seen[0], ("users.register", {"external_ref": f"sasha:{JON}"}))
        self.assertEqual(seen[1], ("access.get", {"end_user": f"usr_{JON}"}))


class WarmAtEntry(Base):
    def test_chat_account_warms_the_record(self):
        from app.services import chat_account as CA
        with mock.patch.object(CA, "_resolve", mock.AsyncMock(return_value=JON)):
            self.assertEqual(run(CA.chat_account(mock.Mock())), JON)
        self.assertEqual(PA.cached(JON)["calls"], "on")   # a sync check right after reads the fresh record

    def test_every_entry_warms(self):
        from app.agent import sasha as AG
        from booking_signer import guest_whatsapp as GW, voice_turn as VT, proactive as PR
        for fn in (AG.turn, GW.turn, GW._inner_app, VT.turn, PR.tick, PR.no_reply_offers):
            self.assertIn("PA.warm(", inspect.getsource(fn), fn.__qualname__)
        from app.services import chat_account as CA
        self.assertIn("PA.warm(", inspect.getsource(CA.chat_account))


class TheRulesAccess(Base):
    def test_a_granted_person_reaches_an_allowed_real_venue(self):
        from agapi import booking_decide as BD
        from booking_signer import guest_accounts as GA
        self.read(JON, SCRATCH)
        self.assertEqual(run(BD.access_of(JON)), {"mode": "live", "calls": "on", "real_venue_sends": "on"})
        self.assertEqual(BD.access_cached(JON), {"mode": "live", "calls": "on", "real_venue_sends": "on"})
        self.assertIsNone(GA.real_contact_refusal(JON, to_test_venue=False))
        self.assertEqual(GA.real_contact_refusal(SCRATCH, to_test_venue=False).status_code, 403)
        self.assertIsNone(GA.real_contact_refusal(SCRATCH, to_test_venue=True))   # our test venues: anyone
        self.assertEqual(run(BD.access_of(SCRATCH)), {"mode": "test", "calls": "off", "real_venue_sends": "off"})

    def test_a_test_record_reaches_the_sandbox(self):
        from agapi import agapi_route as AR
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_ROUTE": "venues=live,outcomes=live"}):
            self.assertEqual(run(AR.person_mode(SCRATCH)), "test")
            self.assertEqual(run(AR.target_for("venues", SCRATCH)), "sandbox")
            self.assertEqual(run(AR.target_for("venues", INVITED)), "sandbox")
            self.assertEqual(run(AR.target_for("venues", JON)), "live")
            self.assertEqual(run(AR.target_for("venues")), "live")   # no person: the family's route


class PlatformCheckIsAFixture(Base):
    def test_empty_in_production_filled_by_tests(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from booking_signer import ladder_routes as LR
        self.assertEqual(LR.PLATFORM_CHECK_ACCOUNTS, set())
        app = FastAPI()
        app.include_router(LR.router, prefix="/api/booking")
        with mock.patch.object(LR, "account_for", lambda r: SCRATCH), \
                mock.patch.dict(os.environ, {"SASHA_PLATFORM_CHECK_ACCOUNTS": SCRATCH}):   # the old env list admits nobody
            self.assertEqual(TestClient(app).get("/api/booking/platform/check", params={"url": "https://x.test/"}).status_code, 403)
            with mock.patch.object(LR, "PLATFORM_CHECK_ACCOUNTS", {SCRATCH}):
                r = TestClient(app).get("/api/booking/platform/check", params={"url": "https://x.test/"})
                self.assertEqual((r.status_code, r.json()["rule"]), (422, "not_named_platform"))


class NoEnvListDecidesAccess(unittest.TestCase):
    """No code (outside the tests, scripts/cr1_demo.py and scripts/live_suite.py tooling) reads an env person list; SASHA_SWITCHING
    is a kill switch compared only to "all"; SASHA_PLATFORM_CHECK_ACCOUNTS is read nowhere."""
    LISTS = ("SASHA_CALLS_ACCOUNTS", "SASHA_GMAIL_ACCOUNTS", "SASHA_S2_DEMO_ACCOUNTS", "SASHA_OUTLOOK_ACCOUNTS",
             "SASHA_REAL_CONTACT_ACCOUNTS", "SASHA_DEMO_STANDIN", "SASHA_REHEARSAL", "SASHA_FOUNDER_EMAIL", "SASHA_PLATFORM_CHECK_ACCOUNTS")
    ALLOWED = {"scripts/cr1_demo.py", "scripts/live_suite.py"}

    def sources(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        for p in root.rglob("*.py"):
            rel = p.relative_to(root).as_posix()
            if rel.startswith(("tests/", "agapi/booking_rules/")) or "/." in rel or rel.startswith(".") or "venv" in rel:
                continue
            yield rel, p.read_text(encoding="utf-8", errors="replace")

    def test_no_env_person_list_is_read(self):
        bad = []
        for rel, src in self.sources():
            for name in self.LISTS:
                if re.search(r"""["']%s["']""" % name, src) and rel not in self.ALLOWED:
                    bad.append((rel, name))
        self.assertEqual(bad, [])

    def test_switching_is_only_compared_to_all(self):
        uses = []
        for rel, src in self.sources():
            for line in src.splitlines():
                if re.search(r"""["']SASHA_SWITCHING["']""", line):
                    uses.append((rel, line.strip()))
        self.assertTrue(uses)
        for rel, line in uses:
            self.assertRegex(line, r"""os\.getenv\(["']SASHA_SWITCHING["'], ["']["']\)\s*==\s*["']all["']""", rel)


if __name__ == "__main__":
    unittest.main()
