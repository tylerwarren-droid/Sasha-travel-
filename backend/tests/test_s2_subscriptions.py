"""CR 72 · S2's subscription radar — /s2 only. Offline: a scripted model and a stand-in AgAPI (no call leaves a test).

    cd backend && python -m unittest tests.test_s2_subscriptions -v
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import s2_subscriptions as SUBS
from agapi import v0 as API
from app.agent.fakes import Block, client

ACCOUNT = "00000000-0000-4000-8000-000000000072"
SUB = {"subscription_id": "sub_calm", "merchant": "Calm", "amount": {"amount_minor": 1499, "currency": "EUR"}, "cadence": "monthly",
       "last_charge": "2026-09-01", "likely_unused": True, "why": ["a free trial on 2026-07-25 that became a paid plan on 2026-08-01"], "status": "active"}


def run(c):
    return asyncio.run(c)


class FakeAgAPI:
    """AgAPI's answers, in its real shapes (the deployed sandbox gave these on 10 Oct)."""

    def __init__(self):
        self.calls, self.approved, self.tapped = [], False, False

    async def __call__(self, op, body, approval=None):
        self.calls.append((op, body, approval))
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "usr_" + "0" * 26}}
        if op == "subscriptions.find":
            return {"ok": True, "result": {"subscriptions": [SUB], "monthly_total": [{"amount_minor": 14577, "currency": "EUR"}], "likely_unused": 1}}
        if op == "subscriptions.cancel_plan":
            return {"ok": True, "result": {"merchant": "Calm", "routes": [{"kind": "email", "value": "cancel@calm.example"}], "never": "never logs in"}}
        if op == "subscriptions.cancel":
            if not approval:
                return {"ok": False, "error": {"code": "approval_required", "details": {"read_back_id": "rb_1", "read_back": {"lines": [
                    "Cancel Calm: EUR 14.99 monthly (last charged 2026-09-01).", "Sasha emails cancel@calm.example …"]}}}}
            return {"ok": True, "result": {"subscription": {**SUB, "status": "cancel_requested"}}}
        if op == "sandbox.simulate_approval":
            said = body["said"].lower()
            if "yes" not in said or "?" in said:
                return {"ok": False, "error": {"code": "no_explicit_yes"}}
            return {"ok": True, "result": {"approval_id": "apv_1"}}
        if op == "approvals.request":
            return {"ok": True, "result": {}}
        if op == "approvals.status":
            return {"ok": True, "result": {"approval": {"approval_id": "apv_tap", "state": "valid"} if self.tapped else None}}
        raise AssertionError(op)


def ctx(said="", ago=0):
    return API.Ctx(account=ACCOUNT, user_said=said, surface="s2", started=datetime.now(timezone.utc) + timedelta(seconds=ago))


class Radar(unittest.TestCase):
    def setUp(self):
        self.agapi = FakeAgAPI()
        for p in (mock.patch.object(SUBS, "CALL", self.agapi), mock.patch.dict(SUBS._USERS, {}, clear=True), mock.patch.dict(SUBS._PENDING, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def test_the_list_from_the_sample(self):
        r = run(SUBS.run_tool(ctx(), "find_subscriptions", {"use_sample": True}))
        self.assertEqual(r["result"]["monthly_total"], "EUR 145.77")
        s = r["result"]["subscriptions"][0]
        self.assertEqual((s["service"], s["amount"], s["how_often"], s["likely_unused"]), ("Calm", "EUR 14.99", "monthly", True))
        self.assertEqual(self.agapi.calls[1][1]["statement"], {"sample": True})

    def test_cancel_needs_their_own_yes_in_a_later_turn(self):
        r = run(SUBS.run_tool(ctx(), "cancel_subscription", {"subscription_id": "sub_calm"}))
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertIn("Cancel Calm: EUR 14.99 monthly (last charged 2026-09-01).", r["result"]["read_back"])
        r = run(SUBS.run_tool(ctx("Yes, cancel it", ago=-60), "cancel_subscription", {"subscription_id": "sub_calm"}))   # the SAME turn (started before the read-back)
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertFalse(any(op == "sandbox.simulate_approval" for op, *_ in self.agapi.calls))
        r = run(SUBS.run_tool(ctx("Wait — what's the refund?", ago=5), "cancel_subscription", {"subscription_id": "sub_calm"}))
        self.assertEqual(r["error"]["code"], "no_explicit_yes")                                           # AgAPI's rule decides, not the model
        r = run(SUBS.run_tool(ctx("Yes, cancel it.", ago=5), "cancel_subscription", {"subscription_id": "sub_calm"}))
        self.assertEqual(r["result"]["status"], "cancel_requested")
        ap = [c for c in self.agapi.calls if c[0] == "sandbox.simulate_approval"][-1]
        self.assertEqual(ap[1]["said"], "Yes, cancel it.")                                                 # their OWN words this turn
        self.assertEqual([c for c in self.agapi.calls if c[0] == "subscriptions.cancel"][-1][2], "apv_1")

    def test_live_the_yes_is_their_tap_and_the_sample_is_refused(self):
        with mock.patch.dict(os.environ, {"SASHA_SUBSCRIPTIONS_VIA": "live"}):
            self.assertEqual(run(SUBS.run_tool(ctx(), "find_subscriptions", {"use_sample": True}))["error"]["code"], "sample_test_only")
            run(SUBS.run_tool(ctx(), "cancel_subscription", {"subscription_id": "sub_calm"}))
            self.assertEqual(self.agapi.calls[-1][0], "approvals.request")                                 # AgAPI's link to their phone
            r = run(SUBS.run_tool(ctx("yes", ago=5), "cancel_subscription", {"subscription_id": "sub_calm"}))
            self.assertEqual(r["result"]["status"], "waiting_for_their_tap")                               # words aren't the yes live
            self.agapi.tapped = True
            r = run(SUBS.run_tool(ctx("done", ago=5), "cancel_subscription", {"subscription_id": "sub_calm"}))
            self.assertEqual(r["result"]["status"], "cancel_requested")
            self.assertFalse(any(op == "sandbox.simulate_approval" for op, *_ in self.agapi.calls))

    def test_an_uploaded_statement_is_read_once_and_only_by_its_account(self):
        ref = SUBS.keep_statement(ACCOUNT, b"date,description,amount\n2026-09-11,SPOTIFY,-10.99\n", "text/csv")
        other = API.Ctx(account="00000000-0000-4000-8000-000000000999", surface="s2")
        self.assertEqual(run(SUBS.run_tool(other, "find_subscriptions", {"statement_ref": ref}))["error"]["code"], "statement_unknown")
        run(SUBS.run_tool(ctx(), "find_subscriptions", {"statement_ref": ref}))
        sent = [b for op, b, _ in self.agapi.calls if op == "subscriptions.find"][-1]["statement"]
        self.assertEqual(base64.b64decode(sent["content_base64"]), b"date,description,amount\n2026-09-11,SPOTIFY,-10.99\n")
        self.assertNotIn(ref, SUBS._STATEMENTS)                                                            # read once, then gone
        with self.assertRaises(ValueError):
            SUBS.keep_statement(ACCOUNT, b"x" * (SUBS.MAX_BYTES + 1), "text/csv")
        with self.assertRaises(ValueError):
            SUBS.keep_statement(ACCOUNT, b"x", "application/zip")


class OnlyOnS2(unittest.TestCase):
    def seen(self, surface):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        seen = []

        async def go():
            async for _ in AG.turn(ACCOUNT, "hello", [], f"s72-{surface}", None, surface):
                pass
        with mock.patch.object(LLM, "client", client([[Block(type="text", text="Hi!")]], seen=seen)):
            run(go())
        return [t["name"] for t in seen[0]["tools"]]

    def test_s1_never_sees_the_radar_and_s2_does(self):
        from app.agent import sasha as AG
        s1 = self.seen("s1")
        self.assertEqual(s1, [t["name"] for t in AG.tools_for_model()])                                     # S1's list, unchanged
        self.assertFalse(set(SUBS.TOOL_NAMES) & set(s1))
        self.assertTrue(set(SUBS.TOOL_NAMES) <= set(self.seen("s2")))

    def test_s1_fingerprint_with_zero_radar_calls(self):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        engine, radar = [], []

        async def call(c, name, args):
            engine.append(name)
            return {"ok": True, "result": {"venues": [{"name": "Casa Marea"}]}}

        async def agapi(*a, **k):
            radar.append(a)
            return {"ok": False}

        def once():
            evs = []

            async def go():
                async for e in AG.turn(ACCOUNT, "dinner near Sol", [], "s72-fp", None, "s1"):
                    evs.append(json.dumps({k: v for k, v in e.items() if k not in ("ms", "steps", "step_ms", "timing", "first_text_ms")},
                                          sort_keys=True, default=str))
            steps = [[Block(type="tool_use", id="t1", name="search_venues", input={"what": "dinner", "where": "Sol"})], [Block(type="text", text="Here.")]]
            with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call), mock.patch.object(SUBS, "CALL", agapi):
                run(go())
            return evs
        a, b = once(), once()
        self.assertEqual(a, b)
        self.assertEqual(engine.count("search_venues"), 2)                                                 # through v0.call, as before
        self.assertFalse(set(SUBS.TOOL_NAMES) & set(engine))
        self.assertEqual(radar, [])

    def test_the_statement_route_is_s2_only(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.agent import sasha as AG
        app = FastAPI()
        app.include_router(AG.router)
        c = TestClient(app)
        body = {"media_type": "text/csv", "content_base64": base64.b64encode(b"date,description,amount\n").decode()}
        with mock.patch("app.services.chat_account.chat_account", mock.AsyncMock(return_value=ACCOUNT)), \
                mock.patch("app.services.chat_account.signed_in", lambda a: True):
            self.assertEqual(c.post("/api/agent/s2/statement", json=body).status_code, 404)                 # /next: refused
            r = c.post("/api/agent/s2/statement", json=body, headers={"x-sasha-surface": "s2"})
            self.assertTrue(r.json()["statement_ref"].startswith("st_"))
            self.assertEqual(c.post("/api/agent/s2/statement", json={"content_base64": "%%%"}, headers={"x-sasha-surface": "s2"}).status_code, 400)
        with mock.patch("app.services.chat_account.chat_account", mock.AsyncMock(return_value=None)), \
                mock.patch("app.services.chat_account.signed_in", lambda a: False):
            self.assertEqual(c.post("/api/agent/s2/statement", json=body, headers={"x-sasha-surface": "s2"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
