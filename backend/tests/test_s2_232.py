"""Sasha 232 · (1) real bookings on /s2 for Tyler + Jon: the founder is in the /s2 demo only if listed; S1's founder powers unchanged;
(5) the gate's own Anthropic key and what one run costs. Offline.

    cd backend && python -m unittest tests.test_s2_232 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest import mock

FOUNDER = "11111111-1111-4111-8111-111111111111"
JON = "4ff7c9c1-4215-46fd-a69f-c181d093db97"


class RealOnS2(unittest.TestCase):
    def test_the_founder_is_not_in_the_s2_demo_unless_listed(self):
        from booking_signer import ladder_routes as LR, guest_accounts as GA
        with mock.patch.object(GA, "founder", lambda a: a == FOUNDER), mock.patch.dict(os.environ, {"SASHA_S2_DEMO_ACCOUNTS": ""}):
            self.assertFalse(LR._s2_demo_account(FOUNDER))
            from app.agent import s2 as S2
            self.assertFalse(S2.demo(FOUNDER))

    def test_s1_founder_powers_unchanged(self):
        from booking_signer import ladder_routes as LR, guest_accounts as GA
        with mock.patch.object(GA, "founder", lambda a: a == FOUNDER), mock.patch.dict(os.environ, {"SASHA_DEMO_STANDIN": "1"}):
            self.assertTrue(LR.standin(FOUNDER))                   # /next's stand-in, as before

    def test_calls_for_jon_when_listed(self):
        from booking_signer import limits as L
        with mock.patch("booking_signer.identity.founder_account", lambda: FOUNDER), mock.patch.dict(os.environ, {"SASHA_CALLS_ACCOUNTS": JON}):
            self.assertTrue(L.calls_on(JON))
            self.assertTrue(L.calls_on(FOUNDER))
            self.assertFalse(L.calls_on("00000000-0000-4000-8000-000000000232"))


class GateCost(unittest.TestCase):
    def test_its_own_key_when_set(self):
        from scripts import gate_cost as GC
        with mock.patch.dict(os.environ, {"SASHA_GATE_ANTHROPIC_API_KEY": "sk-ant-gate-xyz", "ANTHROPIC_API_KEY": "sk-ant-live-abc"}):
            GC.use_gate_key()
            self.assertEqual(os.environ["ANTHROPIC_API_KEY"], "sk-ant-gate-xyz")
        with mock.patch.dict(os.environ, {"SASHA_GATE_ANTHROPIC_API_KEY": "", "ANTHROPIC_API_KEY": "sk-ant-live-abc"}):
            GC.use_gate_key()
            self.assertEqual(os.environ["ANTHROPIC_API_KEY"], "sk-ant-live-abc")

    def test_the_fingerprint_never_shows_the_key(self):
        from scripts import gate_cost as GC
        fp = GC.fingerprint("sk-ant-api03-SECRETSECRET")
        self.assertTrue(fp.startswith("sk-ant-"))
        self.assertNotIn("SECRET", fp)

    def test_the_spend_is_counted(self):
        from scripts import gate_cost as GC
        GC._USE.clear()
        GC._add("claude-haiku-4-5-20251001", SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000, cache_creation_input_tokens=0,
                                                             cache_read_input_tokens=1_000_000))
        self.assertAlmostEqual(GC.report(), 1.0 + 0.5 + 0.1)
        GC._USE.clear()

    def test_create_and_streams_are_metered(self):
        from scripts import gate_cost as GC
        from anthropic.resources.messages import AsyncMessages
        GC._USE.clear()
        orig = AsyncMessages.create

        async def fake(self, *a, **kw):
            return SimpleNamespace(model="claude-haiku-4-5", usage=SimpleNamespace(input_tokens=10, output_tokens=5))
        try:
            AsyncMessages.create = fake
            GC.install()
            asyncio.run(AsyncMessages.create(None, model="claude-haiku-4-5"))
            self.assertEqual(GC._USE["claude-haiku-4-5"]["calls"], 1)
        finally:
            AsyncMessages.create = orig
            GC._USE.clear()


class DirectFirstEveryKind(unittest.TestCase):
    """/s2: their own form or booking page → their own WhatsApp (drafted, they send it) → email → phone; any kind of place."""
    def setUp(self):
        from agapi import venues as VN
        from booking_signer import guest_accounts as GA, guest_receipt as GR, guest_whatsapp as GW
        from tests.test_venue_pick_230 import FormApi
        self.ACCT = "00000000-0000-4000-8000-000000000232"
        VN._HELD.pop(self.ACCT, None)
        self.api = FormApi()
        for p in (mock.patch.object(GW, "api", self.api), mock.patch.object(GA, "founder", lambda a: False),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="alex@example.test"))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(VN._HELD.pop, self.ACCT, None)

    def pick(self, surface, rungs, what="a dog walk"):
        from datetime import date, timedelta
        from agapi import v0 as API, venues as VN
        from tests.test_venue_pick_230 import reader
        ctx = API.Ctx(account=self.ACCT, mode="test", user_said="This one", session="s232", surface=surface)
        with mock.patch.object(VN, "_read", reader(rungs)):
            return asyncio.run(VN.hold_venue(ctx, {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": what, "party": 1,
                                                   "day": (date.today() + timedelta(days=6)).isoformat(), "time": "10:00"}))

    def test_s2_their_whatsapp_before_email_and_phone(self):
        out = self.pick("s2", {"whatsapp": {"value": "+34600111222"}, "email": {}, "phone": {"fact_index": 0}})
        self.assertEqual((out["status"], out["route"]), ("draft_message", "whatsapp"))
        self.assertTrue(out["open_in_whatsapp"].startswith("https://wa.me/34600111222?text="))

    def test_s2_their_own_form_still_first(self):
        out = self.pick("s2", {"form": {}, "whatsapp": {"value": "+34600111222"}, "email": {}})
        self.assertNotEqual(out.get("route"), "whatsapp")

    def test_s2_their_booking_page_is_their_form(self):
        out = self.pick("s2", {"link": {"value": "https://www.fresha.com/a/casa-gate"}, "whatsapp": {"value": "+34600111222"}, "email": {}})
        self.assertNotEqual(out.get("route"), "whatsapp")

    def test_s1_unchanged(self):
        out = self.pick("s1", {"whatsapp": {"value": "+34600111222"}, "email": {}, "phone": {"fact_index": 0}})
        self.assertNotEqual(out.get("status"), "draft_message")


class FounderRealOnS2(unittest.TestCase):
    def test_the_stand_in_is_s1_only(self):
        import inspect
        from booking_signer import ladder_routes as LR
        src = inspect.getsource(LR.read_venue)
        self.assertIn("elif not s2_demo and body.get(\"place_id\") and standin(", src)


if __name__ == "__main__":
    unittest.main()
