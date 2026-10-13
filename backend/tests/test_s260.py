"""Sasha 260 · T42 — Tyler's /s2, 13 Oct 18:27 UTC: "What subscriptions am I paying for?" → a bank statement offered instead.
His 60 receipts reached Sasha in 10 s; AgAPI reads them in ONE model call (its own 180 s limit) and this client hung up at 60 s —
"unreachable" (an exception's class name), and she improvised. A mailbox read is its own job now: in the turn when it's quick; else
she says she's reading and the list reaches the open page by itself. An AgAPI that didn't answer is said as that.
Offline.

    cd backend && python -m unittest tests.test_s260 -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from agapi import s2_gmail_receipts as GR, s2_subscriptions as SUBS

ACCT = "00000000-0000-4000-8000-000000000260"
FOUND = {"ok": True, "result": {"subscriptions": [{"subscription_id": "sub_1", "merchant": "Spotify", "amount": {"currency": "EUR", "amount_minor": 1099},
                                                   "cadence": "monthly", "last_charge": "2026-10-01", "likely_unused": False, "why": None,
                                                   "status": "active"}],
                                "monthly_total": [{"currency": "EUR", "amount_minor": 1099}], "likely_unused": []}}


class Ctx:
    account, user_said = ACCT, "What subscriptions am I paying for?"


def gmail(call):
    return [mock.patch.object(GR, "connected", mock.AsyncMock(return_value=True)),
            mock.patch.object(GR, "receipts", mock.AsyncMock(return_value=[{"message_id": "m1", "text": "Spotify 10.99"}])),
            mock.patch.object(SUBS, "_end_user", mock.AsyncMock(return_value="usr_1")), mock.patch.object(SUBS, "CALL", call)]


def slow(answer, s=0.2):
    calls = []

    async def call(op, body, approval=None):
        calls.append(op)
        await asyncio.sleep(s)
        return answer
    return call, calls


class ASlowReadIsNeverAStatementOffer(unittest.TestCase):
    def setUp(self):
        SUBS._READING.clear()

    def run_with(self, call, *, ask_twice=False, wait_s=0.05):
        from booking_signer import live_events as LE
        published = []

        async def go():
            first = await SUBS._run_tool(Ctx(), "find_subscriptions", {"from_gmail": True})
            again = await SUBS._run_tool(Ctx(), "find_subscriptions", {"from_gmail": True}) if ask_twice else None
            await asyncio.sleep(0.4)                                            # the read finishes after the turn
            return first, again
        ps = gmail(call) + [mock.patch.object(SUBS, "READ_WAIT_S", wait_s),
                            mock.patch.object(LE, "publish", lambda a, e: published.append((a, e)))]
        for p in ps:
            p.start()
        try:
            first, again = asyncio.run(go())
        finally:
            for p in ps:
                p.stop()
        return first, again, published

    def test_she_says_she_is_reading_and_the_list_reaches_the_page(self):
        call, calls = slow(FOUND)
        first, _, published = self.run_with(call)
        self.assertEqual(first["result"]["status"], "reading")
        self.assertTrue(first["result"]["say"].startswith(SUBS.STATEMENT["gmail"]))   # her one statement, said in the turn
        self.assertIn(SUBS.READING_SAY, first["result"]["say"])
        self.assertNotIn("statement", first["result"]["say"].replace(SUBS.STATEMENT["gmail"], ""))
        [(acct, ev)] = published
        self.assertEqual((acct, ev["type"], ev["kind"]), (ACCT, "proactive", "subscriptions"))
        self.assertIn("Spotify", ev["say"])
        self.assertNotIn(SUBS.STATEMENT["gmail"], ev["say"])                   # not said twice
        self.assertEqual(ev["render"]["kind"], "subscriptions")
        self.assertEqual(SUBS._LAST[ACCT][0]["service"], "Spotify")             # "cancel Spotify" finds it afterwards
        self.assertNotIn(ACCT, SUBS._READING)

    def test_asked_again_while_reading_is_the_same_read(self):
        call, calls = slow(FOUND)
        _, again, published = self.run_with(call, ask_twice=True)
        self.assertEqual(calls, ["subscriptions.find"])                         # one read, never two
        self.assertEqual(again["result"]["status"], "reading")
        self.assertEqual(len(published), 1)

    def test_a_quick_read_is_answered_in_the_turn_and_nothing_is_published(self):
        call, _ = slow(FOUND, s=0.0)
        first, _, published = self.run_with(call, wait_s=5)
        self.assertTrue(first["ok"])
        self.assertIn("Spotify", first["result"]["say"])
        self.assertEqual(published, [])

    def test_agapi_not_answering_is_said_plainly_in_the_turn_and_on_the_page(self):
        call, _ = slow({"ok": False, "error": {"code": "timeout", "message": "ReadTimeout"}}, s=0.0)
        first, _, _ = self.run_with(call, wait_s=5)
        self.assertIn(SUBS.NOT_ANSWERED_SAY, first["error"]["message"])
        self.assertNotIn("ReadTimeout", first["error"]["message"])
        call, _ = slow({"ok": False, "error": {"code": "budget_exhausted", "message": "This key's budget for the month is spent."}})
        _, _, published = self.run_with(call)
        self.assertEqual(published[0][1]["say"], SUBS.NOT_ANSWERED_SAY)


class TheReadGetsAgapisOwnTime(unittest.TestCase):
    def test_a_mailbox_body_waits_read_timeout_and_a_timeout_is_named(self):
        import httpx
        seen = {}

        class Client:
            def __init__(self, timeout):
                seen["timeout"] = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers, content):
                raise httpx.ReadTimeout("slow")
        with mock.patch("agapi.agapi_route.client_for", mock.AsyncMock(return_value=("https://agapi.test", "k"))), \
                mock.patch.object(httpx, "AsyncClient", Client), mock.patch("agapi.agapi_health.note", mock.AsyncMock()):   # 261: no email
            r = asyncio.run(SUBS._agapi("subscriptions.find", {"end_user": "u", "emails": {"messages": []}}))
            self.assertEqual(seen["timeout"].read, SUBS.READ_TIMEOUT_S)
            self.assertEqual(r["error"]["code"], "timeout")
            asyncio.run(SUBS._agapi("users.register", {"external_ref": "x"}))
            self.assertEqual(seen["timeout"].read, SUBS.CALL_TIMEOUT_S)
        self.assertGreater(SUBS.READ_TIMEOUT_S, 180)                             # longer than AgAPI's own reader limit


if __name__ == "__main__":
    unittest.main()
