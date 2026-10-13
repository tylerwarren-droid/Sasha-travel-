"""Sasha 261 · T43 — AN AGAPI OUTAGE, NAMED (rows 897/900). From 16:59 UTC on 13 Oct the sandbox key's budget was spent: every paid
AgAPI call answered 402 budget_exhausted, and she said "didn't work" (or offered a statement). Now, in the one transport every family's
client sends through (agapi_route.post): a 402 / 429 / timeout / unreachable is noted once — on the tool call in progress, and the
founder emailed at most once an hour (agapi_health) — and sasha.turn says voice.outage_line, by code, never a retry or an alternative.
Offline.

    cd backend && python -m unittest tests.test_s261 -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from unittest import mock

import httpx

from agapi import agapi_health as AH, agapi_route as AR


def run(c):
    return asyncio.run(c)


class Resp:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        if isinstance(self._b, Exception):
            raise self._b
        return self._b


def client(answer):
    class C:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers, content):
            if isinstance(answer, Exception):
                raise answer
            return answer
    return C


class TheOneTransportNamesAnOutage(unittest.TestCase):
    def post(self, answer):
        noted = []

        async def note(kind, op, url, key):
            noted.append(kind)
        with mock.patch.object(httpx, "AsyncClient", client(answer)), mock.patch.object(AH, "note", note):
            env = run(AR.post("https://agapi.test", "k", "venue.prepare_booking", {}, {}, 5.0))
        return env, noted

    def test_402_budget_exhausted_is_a_limit(self):
        env, noted = self.post(Resp(402, {"ok": False, "error": {"code": "budget_exhausted", "message": "This key's budget for the month is spent."}}))
        self.assertEqual((env["error"]["code"], noted), ("budget_exhausted", ["limit"]))

    def test_429_is_a_limit(self):
        self.assertEqual(self.post(Resp(429, {"ok": False, "error": {"code": "rate_limited"}}))[1], ["limit"])

    def test_a_timeout_is_named_and_slow(self):
        env, noted = self.post(httpx.ReadTimeout("slow"))
        self.assertEqual((env["error"]["code"], noted), ("timeout", ["slow"]))

    def test_unreachable_and_a_proxy_page_are_slow(self):
        self.assertEqual(self.post(httpx.ConnectError("down"))[1], ["slow"])
        env, noted = self.post(Resp(502, ValueError("not json")))
        self.assertEqual((env["error"]["code"], env["error"]["message"], noted), ("unreachable", "HTTP 502", ["slow"]))

    def test_an_answer_or_a_venues_own_upstream_is_not_an_agapi_outage(self):
        self.assertEqual(self.post(Resp(200, {"ok": True, "result": {}}))[1], [])
        self.assertEqual(self.post(Resp(502, {"ok": False, "error": {"code": "upstream_unreachable"}}))[1], [])
        self.assertEqual(self.post(Resp(422, {"ok": False, "error": {"code": "invalid_input"}}))[1], [])


class AFailureIsLoggedWithItsCauseOnly(unittest.TestCase):
    """Row 901: Tyler's subscriptions.find answered 502 upstream_failed after ~84 s; AgAPI named the exception in its message, and
    nothing kept it. The one transport logs op, HTTP status, code, ms and the cause's class — never the message's other words."""

    def test_the_class_in_parentheses_and_nothing_else(self):
        env = {"ok": False, "error": {"code": "upstream_failed", "message": "The receipts couldn't be read (RuntimeError); nothing was kept.",
                                      "details": {"service": "ai_reader"}}}
        self.assertEqual(AR.failed_why(env), " · cause RuntimeError, service ai_reader")
        self.assertEqual(AR.failed_why({"ok": False, "error": {"code": "upstream_failed", "message": "FitBox's own pages don't say how to cancel"}}), "")

    def test_a_failed_call_is_logged_once(self):
        env = {"ok": False, "error": {"code": "upstream_failed", "message": "The receipts couldn't be read (BadRequestError); nothing was kept."}}
        with mock.patch.object(httpx, "AsyncClient", client(Resp(502, env))), mock.patch.object(AH, "note", mock.AsyncMock()), \
                self.assertLogs("agapi.route", "WARNING") as cm:
            run(AR.post("https://agapi.test", "k", "subscriptions.find", {"emails": {"messages": [{"text": "PRIVATE"}]}}, {}, 5.0))
        [line] = cm.output
        self.assertIn("subscriptions.find → HTTP 502 upstream_failed in", line)
        self.assertIn("cause BadRequestError", line)
        self.assertNotIn("PRIVATE", line)
        self.assertNotIn("couldn't be read", line)


class EveryFamilySendsThroughIt(unittest.TestCase):
    def test_no_client_keeps_its_own_transport(self):
        from agapi import person_access, s2_fine_print, s2_outcomes, s2_subscriptions, venue_submit, venue_truth, via_agapi
        for m in (person_access, s2_fine_print, s2_outcomes, s2_subscriptions, venue_submit, venue_truth, via_agapi):
            src = inspect.getsource(m._agapi)
            self.assertIn("AR.post(", src, m.__name__)
            self.assertNotIn("AsyncClient", src, m.__name__)


class TheFounderIsToldOnceAnHour(unittest.TestCase):
    def test_one_email_an_hour_and_every_outage_on_the_tool(self):
        sent = []

        async def send(msg):
            sent.append(msg)
            return {"sent": True}

        async def go():
            with AH.watching() as met:
                await AH.note("limit", "venue.prepare_booking", "https://agapi-sandbox.test/x", "secret-key-value")
                await AH.note("slow", "venue.profile", "https://agapi-sandbox.test/x", "secret-key-value")
            return met
        from app.services import model_health as MH
        with mock.patch.dict(AH._LAST, {}, clear=True), mock.patch.object(AH, "SEND", send), \
                mock.patch.object(MH, "_founder_address", mock.AsyncMock(return_value="founder@example.test")):
            met = run(go())
        self.assertEqual(met, ["limit", "slow"])
        self.assertEqual(len(sent), 1)
        self.assertIn("budget", sent[0]["subject"])
        self.assertNotIn("secret-key-value", sent[0]["text"])                  # the fingerprint only, never the key
        self.assertIn(AH.key_print("secret-key-value"), sent[0]["text"])

    def test_outside_a_turn_nothing_is_recorded(self):
        with mock.patch.dict(AH._LAST, {"at": 10 ** 12}):
            self.assertEqual(run(AH.note("limit", "access.get", "https://x", "k"))["why"], "already told within the hour")


class SheSaysItPlainly(unittest.TestCase):
    def test_a_failed_booking_tool_that_met_a_limit_says_the_line(self):
        from app.agent import sasha as S, voice as V
        r = S.agapi_outage({"ok": False, "error": {"code": "unavailable", "message": "the venue booking service didn't answer"}}, ["limit"], "book_venue")
        self.assertEqual(r["error"]["message"], "I can't book right now — the booking service has hit its limit. Kanoe has been told; nothing was sent.")
        self.assertEqual(S.outage(r), r["error"]["message"])                   # said by code, word for word
        hint = S.model_result(r)["how_to_handle"]
        self.assertIn("ALREADY been said", hint)                               # and the model told not to work round it:
        self.assertIn("no retry offer, no alternative", hint)                   # production (o261) offered both before this
        slow = V.outage_line("slow", "search_venues")
        self.assertIn("didn't answer in time", slow)
        for line in (r["error"]["message"], slow):
            self.assertNotIn("didn't work", line)
            self.assertEqual(V.channel_words(line), [])

    def test_a_tool_that_worked_or_failed_otherwise_or_subscriptions_is_as_it_was(self):
        from app.agent import sasha as S
        ok = {"ok": True, "result": {}}
        self.assertIs(S.agapi_outage(ok, ["slow"], "search_venues"), ok)
        other = {"ok": False, "error": {"code": "invalid_input", "message": "x"}}
        self.assertIs(S.agapi_outage(other, [], "book_venue"), other)
        subs = {"ok": False, "error": {"code": "timeout", "message": "260's own line"}}
        self.assertIs(S.agapi_outage(subs, ["slow"], "find_subscriptions"), subs)

    def test_the_turn_wraps_every_tool_and_keeps_parity(self):
        from app.agent import sasha as S
        src = inspect.getsource(S.turn)
        self.assertIn("with _AH.watching() as met:", src)
        self.assertIn("agapi_outage(r, met, u.name) if honest else r", src)
        # production (o261): she carried on after the line — a retry offer, an alternative, the line again. The line ends the turn.
        self.assertIn('agapi_out = agapi_out or (r.get("error") or {}).get("code") == "agapi_unreachable"', src)
        self.assertIn("if agapi_out or read_back_said:", src)   # Sasha 262: the read-back's one line ends the turn the same way


if __name__ == "__main__":
    unittest.main()
