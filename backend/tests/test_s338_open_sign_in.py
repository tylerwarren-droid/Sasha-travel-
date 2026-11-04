"""Sasha 338 · open sign-in, every new person NOT live (docs/sasha/S-338-open-sign-in.md).
    cd backend && python -m unittest tests.test_s338_open_sign_in -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import pathlib
import subprocess
import unittest
from unittest import mock

from agapi import agapi_route as AR, person_access as PA
from booking_signer import ops, sign_up as SU

run = asyncio.run
NEW = "00000000-0000-4000-8000-000000003380"
ROOT = pathlib.Path(__file__).resolve().parents[1]


class Supabase:
    """The admin API as sign-up uses it: a user is created once; again → 422 "already registered"."""

    def __init__(self):
        self.users = {}

    async def __call__(self, method, path, body=None):
        if method == "POST" and path == "/admin/users":
            e = body["email"]
            if e in self.users:
                return 422, {"msg": "A user with this email address has already been registered"}
            self.users[e] = {"id": NEW, "email_confirm": body.get("email_confirm")}
            return 201, {"id": NEW}
        return 404, {}


class WhoMaySignIn(unittest.TestCase):
    def setUp(self):
        SU._BY_IP.clear(); SU._DAY.clear()
        self.sb = Supabase()
        self.p = mock.patch.object(ops, "ADMIN", self.sb)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_a_brand_new_email_gets_an_account_and_nothing_else_is_said(self):
        first = run(SU.open_account("New.Person@Example.com", "1.2.3.4"))
        again = run(SU.open_account("new.person@example.com", "1.2.3.4"))
        self.assertEqual(first, again, "never says whether the address already had an account")
        self.assertEqual(first, {"ok": True})
        self.assertEqual(self.sb.users["new.person@example.com"]["email_confirm"], False)   # their own link confirms it
        self.assertEqual(run(SU.open_account("not an email", "1.2.3.4"))["ok"], False)

    def test_rate_limited_per_ip(self):
        for i in range(SU.SIGNUPS_PER_IP_HOUR):
            self.assertTrue(run(SU.open_account(f"p{i}@example.com", "9.9.9.9"))["ok"])
        self.assertFalse(run(SU.open_account("one.more@example.com", "9.9.9.9"))["ok"])
        self.assertTrue(run(SU.open_account("elsewhere@example.com", "8.8.8.8"))["ok"])

    def test_the_route_is_open_before_sign_in_only_for_itself(self):
        from booking_signer import gate
        src = inspect.getsource(gate.require_booking_key)
        self.assertIn('"/api/booking/sign-up"', src)
        sign_in = (ROOT.parent / "frontend/app/sign-in/SignInForm.tsx").read_text()
        self.assertIn("apiUrl('/api/booking/sign-up')", sign_in)                         # the page asks the ONE place first
        self.assertNotIn("invite-only", sign_in)

    def test_one_place_creates_accounts(self):
        out = subprocess.run(["git", "grep", "-ln", '"/admin/users", {', "--", "*.py"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        out += subprocess.run(["git", "grep", "-ln", "/admin/generate_link", "--", "*.py"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        makers = sorted({p for p in out if not p.startswith("tests/")})
        self.assertTrue(set(makers) <= {"booking_signer/sign_up.py", "booking_signer/ops.py", "booking_signer/guest_accounts.py"}, makers)
        code = inspect.getsource(AR.person_mode).split('"""')[-1]                          # its code, past the docstring
        self.assertNotIn("kanoe_test", code)                                               # no second list decides test vs live
        self.assertNotIn("app_metadata", code)
        self.assertNotIn("ADMIN", code)


class NothingRealForANewPerson(unittest.TestCase):
    """A brand-new person: no person_access row → CLOSED. Chats; nothing real is sent or charged; 60 turns a day."""

    def setUp(self):
        PA.clear()

        async def no_row(op, body):
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "usr_new"}}
            return {"ok": True, "result": {"mode": "test", "source": "closed"}}
        self.ps = [mock.patch.object(PA, "RESOLVER", None), mock.patch.object(PA, "CALL", no_row),
                   mock.patch.dict(os.environ, {"SASHA_AGAPI_ROUTE": "all=live", "SASHA_AGAPI_KEY": ""})]
        for p in self.ps:
            p.start()

    def tearDown(self):
        for p in reversed(self.ps):
            p.stop()
        PA.clear()

    def test_the_record_is_closed_and_every_family_is_the_sandbox(self):
        rec = run(PA.warm(NEW))
        self.assertEqual((rec["mode"], rec["real_venue_sends"], rec["calls"], rec["real_money"], rec.get("platform_submit")),
                         ("test", "off", "off", "off", None))
        self.assertEqual(run(AR.person_mode(NEW)), "test")
        for fam in AR.FAMILIES:
            self.assertEqual(run(AR.target_for(fam, NEW)), "sandbox", fam)                 # payments TEST, venues TEST — every family

    def test_they_chat_and_nothing_real_leaves(self):
        import app.services.llm as LLM
        from app.agent import sasha as S
        from app.agent.fakes import Block, client
        posts, seen = [], []

        async def post(url, key, op, body, headers, timeout):   # anything at all sent to AgAPI during the turn
            posts.append((url, op))
            return {"ok": True, "result": {}}
        run(PA.warm(NEW))

        async def go():
            out = []
            async for ev in S.turn(NEW, "Hi Sasha — what can you do?", [], "s338-chat", None, "s2"):
                out.append(ev)
            return out
        with mock.patch.object(AR, "post", post), mock.patch.object(S, "over_budget", lambda a: asyncio.sleep(0)), \
                mock.patch.object(LLM, "client", client([[Block(type="text", text="I can plan and book your trips.")]], seen=seen)):
            evs = run(go())
        self.assertTrue(any("I can plan and book" in str(e) for e in evs))                  # she answered
        self.assertEqual([p for p in posts if "agapi-live" in p[0]], [])                     # nothing to agapi-live

    def test_their_day_is_60_turns(self):
        from app.agent import sasha as S
        from booking_signer import basket as BK, guest_accounts as GA
        run(PA.warm(NEW))
        self.assertEqual(S.DAILY_BUDGET["new_turns"], 60)
        S._MINUTE.pop(NEW, None)
        with mock.patch.object(BK, "_run", lambda: object()), mock.patch.object(GA, "founder", lambda a: False), \
                mock.patch.object(BK, "count_events", lambda *a: asyncio.sleep(0, result=60)), mock.patch.object(BK, "event", lambda *a, **k: asyncio.sleep(0)):
            self.assertEqual(run(S.over_budget(NEW)), S.BUDGET_LINE)                          # the 61st turn of the day
        S._MINUTE.pop(NEW, None)
        with mock.patch.object(BK, "_run", lambda: object()), mock.patch.object(GA, "founder", lambda a: False), \
                mock.patch.object(BK, "count_events", lambda *a: asyncio.sleep(0, result=59)), mock.patch.object(BK, "event", lambda *a, **k: asyncio.sleep(0)):
            self.assertIsNone(run(S.over_budget(NEW)))
        PA.install({NEW: PA.LIVE_PERSON})                                                     # once Tyler marks them live: 300
        S._MINUTE.pop(NEW, None)
        with mock.patch.object(BK, "_run", lambda: object()), mock.patch.object(GA, "founder", lambda a: False), \
                mock.patch.object(BK, "count_events", lambda *a: asyncio.sleep(0, result=60)), mock.patch.object(BK, "event", lambda *a, **k: asyncio.sleep(0)):
            self.assertIsNone(run(S.over_budget(NEW)))
        PA.uninstall(NEW)


if __name__ == "__main__":
    unittest.main()
