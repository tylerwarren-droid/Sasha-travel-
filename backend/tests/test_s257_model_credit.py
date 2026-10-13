"""Sasha 257 · T38 — AN EXHAUSTED MODEL CREDIT IS NAMED (13 Oct 2026, ~10:40 UTC: Sasha went silent for everyone — "Your credit balance
is too low to access the Anthropic API" — people got empty replies, the gate failed 40 unrelated-looking checks, nobody was told).
Now every surface's turn says it plainly (model_health.PLAIN, never empty, never "say that once more") and the founder is emailed once
an hour; the deploy gate's FIRST check is a 1-token preflight that stops it by name. Offline: the model and the mail are stand-ins.

    cd backend && python -m unittest tests.test_s257_model_credit -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from app.agent import sasha as S
from app.services import model_health as MH

CREDIT = RuntimeError("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is "
                      "too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}}")


def run(c):
    return asyncio.run(c)


class Recognised(unittest.TestCase):
    def test_the_billing_refusal_only(self):
        self.assertTrue(MH.is_credit(CREDIT))
        self.assertFalse(MH.is_credit(RuntimeError("Error code: 429 - rate_limit_error")))
        self.assertFalse(MH.is_credit(RuntimeError("Error code: 529 - overloaded_error")))

    def test_the_line_is_plain_and_claims_nothing(self):
        self.assertIn("run out of credit", MH.PLAIN)
        self.assertIn("nothing was booked or sent", MH.PLAIN)


class EveryTurnSaysIt(unittest.TestCase):
    def setUp(self):
        self.sent = []

        async def send(msg):
            self.sent.append(msg)
            return {"sent": True}
        MH._LAST.clear()
        for p in (mock.patch.object(MH, "SEND", send), mock.patch.object(MH, "_founder_address", mock.AsyncMock(return_value="founder@example.test"))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(MH._LAST.clear)

    def turn_events(self):
        async def broken(*a, **k):
            raise CREDIT
            yield {}
        with mock.patch.object(S, "turn", broken):
            async def go():
                return [e async for e in S.turn_with_quiver("00000000-0000-4000-8000-000000000257", "Hello", [], "s257", "s2")]
            return run(go())

    def test_a_turn_says_the_plain_line_and_tells_the_founder_once(self):
        evs = self.turn_events()
        err = [e for e in evs if e.get("type") == "error"]
        self.assertEqual(err[0]["message"], MH.PLAIN)
        self.assertEqual(err[0]["rule"], "model_credit")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]["to"], "founder@example.test")
        self.assertIn("credit is exhausted", self.sent[0]["subject"])
        self.turn_events()
        self.assertEqual(len(self.sent), 1)   # once an hour, not once a message


class TheGateStopsByName(unittest.TestCase):
    def test_preflight_names_it(self):
        class Client:
            def __init__(self, *a, **k):
                self.messages = self

            async def create(self, **k):
                raise CREDIT
        with mock.patch("anthropic.AsyncAnthropic", Client):
            ok, why = run(MH.preflight())
        self.assertFalse(ok)
        self.assertIn("ANTHROPIC CREDIT EXHAUSTED", why)

    def test_other_failures_leave_it_to_the_suites(self):
        class Client:
            def __init__(self, *a, **k):
                self.messages = self

            async def create(self, **k):
                raise RuntimeError("overloaded_error")
        with mock.patch("anthropic.AsyncAnthropic", Client):
            ok, _ = run(MH.preflight())
        self.assertTrue(ok)

    def test_the_gate_asks_first(self):
        import inspect
        from scripts import gate
        src = inspect.getsource(gate.main)
        self.assertLess(src.index("MH.preflight()"), src.index("places_fake.install()"))


if __name__ == "__main__":
    unittest.main()
