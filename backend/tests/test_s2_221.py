"""Sasha 221 · S2's front door (/s2) — S2 mode is chosen ONLY by /s2's proxy; S1 (/next) is byte-for-byte as before.
Offline: a scripted model, stand-in APIs, 0 live calls.

    cd backend && python -m unittest tests.test_s2_221 -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from agapi import v0 as API
from app.agent.fakes import Block, client

ACCOUNT = "00000000-0000-4000-8000-000000000221"


def run(c):
    return asyncio.run(c)


def seen_by_model(surface):
    import app.services.llm as LLM
    from app.agent import sasha as AG
    seen = []

    async def go():
        async for _ in AG.turn(ACCOUNT, "hello", [], f"s221-{surface}", None, surface):
            pass
    with mock.patch.object(LLM, "client", client([[Block(type="text", text="Hey there — what can I do for you?")]], seen=seen)):
        run(go())
    return seen[0]


class Isolation(unittest.TestCase):
    def test_s1_is_exactly_as_before(self):
        from app.agent import sasha as AG
        from app.services import persona as P
        s = seen_by_model("s1")
        self.assertEqual(s["system"][0]["text"], P.AGENT_SYSTEM)
        self.assertEqual([t["name"] for t in s["tools"]], [t["name"] for t in AG.tools_for_model()])

    def test_s2_has_her_own_opening_and_its_tool_set(self):
        from app.agent import s2 as S2
        s = seen_by_model("s2")
        self.assertTrue(s["system"][0]["text"].startswith(S2.S2_WHO))
        self.assertIn("## How she talks", s["system"][0]["text"])   # the shared rules, unchanged
        self.assertEqual(sorted(t["name"] for t in s["tools"]), sorted(S2.S2_TOOLS))

    def test_only_the_s2_header_chooses_s2(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.agent import sasha as AG
        got = []

        async def fake(account, message, history, session, surface="s1"):
            got.append(surface)
            yield {"type": "done", "text": "ok", "guard": [], "tools": []}
        app = FastAPI()
        app.include_router(AG.router)
        c = TestClient(app)
        with mock.patch("app.services.chat_account.chat_account", mock.AsyncMock(return_value=ACCOUNT)), \
                mock.patch("app.services.chat_account.signed_in", lambda a: True), mock.patch.object(AG, "turn_with_quiver", fake), \
                mock.patch.object(AG, "over_budget", mock.AsyncMock(return_value=None)):
            c.post("/api/agent/turn", json={"message": "hi"})
            c.post("/api/agent/turn", json={"message": "hi", "surface": "s2"}, headers={"x-sasha-surface": "nope"})
            c.post("/api/agent/turn", json={"message": "hi"}, headers={"x-sasha-surface": "s2"})
        self.assertEqual(got, ["s1", "s1", "s2"])


class DemoSetting(unittest.TestCase):
    def test_venue_reads_flag_s2_only_on_s2(self):
        from agapi import venues as VN
        calls = []

        async def api(account, method, path, body=None, timeout=None):
            calls.append(body)
            return 200, {"read_id": "r1", "venue": "Casa Lucio", "rungs": [], "facts": []}
        GW = VN._API()
        with mock.patch.object(GW, "api", api), mock.patch.object(GW, "_hours_of", lambda rd, now: {}):
            run(VN._read(API.Ctx(account=ACCOUNT), {"name": "Casa Lucio", "city": "Madrid", "place_id": "ChIJx"}))
            run(VN._read(API.Ctx(account=ACCOUNT, surface="s2"), {"name": "Casa Lucio", "city": "Madrid", "place_id": "ChIJx"}))
        VN._READS.pop(ACCOUNT, None)
        self.assertNotIn("s2_demo", calls[0])
        self.assertTrue(calls[1]["s2_demo"])

    def test_who_has_the_demo_setting(self):
        from booking_signer import ladder_routes as LR, guest_accounts as GA
        with mock.patch.object(GA, "founder", lambda a: a == "f"), mock.patch.dict("os.environ", {"SASHA_S2_DEMO_ACCOUNTS": "fixture-1"}):
            self.assertTrue(LR._s2_demo_account("f"))
            self.assertTrue(LR._s2_demo_account("fixture-1"))
            self.assertFalse(LR._s2_demo_account("guest-9"))
            self.assertFalse(LR._s2_demo_account(None))

    def test_the_read_route_stands_in_only_with_the_flag_and_the_setting(self):
        import inspect
        from booking_signer import ladder_routes as LR
        src = inspect.getsource(LR.read_venue)
        self.assertIn('body.pop("s2_demo", False)', src)
        self.assertIn("_s2_demo_account(account_for(request))", src)


if __name__ == "__main__":
    unittest.main()
