"""Sasha 370 · no Sasha route acts on a booking, trip or person without the ONE account resolver + an owner check, applied at
the ROUTER. NO PATCHES.

Found (CR finding #20): /bookings/create, /bookings/{id} and /bookings/cancel had no account dependency (only the shared browser
key of the rate limiter); tenant.py said "individual routes decide".

ONE source: chat_account.require_account declared on the router (booking_signer.gate.require_booking_key for /api/booking/*, the
same resolver behind the proxy key); handlers read it (chat_account.acting / account.account_for) and check the owner. The server
refuses to start while any mounted route lacks it or a named public reason (app/account_gate.refuse_unguarded).

    cd backend && python -m unittest tests.test_s370_one_resolver_at_the_router -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient

from app import account_gate as AG
from app.services import chat_account as CA

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _app():
    from app.main import app
    return app


class EveryRouteDeclaresIt(unittest.TestCase):
    def test_every_mounted_route_has_the_door_or_a_named_public_reason(self):
        app = _app()
        self.assertEqual(AG.unguarded(app), [])
        mounted = {(m, p) for m, p, _ in AG.routes(app)}
        self.assertEqual(sorted(set(AG.PUBLIC) - mounted), [])                          # no stale allow-list entry
        for k, why in AG.PUBLIC.items():
            self.assertTrue(len(why) > 10 and "no " in why, (k, why))                     # each with its reason
        for m, p, _ in AG.routes(app):                                                   # nothing that names a person is public
            if (m, p) in AG.PUBLIC:
                self.assertNotRegex(p, r"booking|trip|chat|payment|keep|agent|avatar|voice|memory|me\b")

    def test_the_data_routers_carry_it_on_the_router_itself(self):
        for f in ("app/api/chats.py", "app/api/trips.py", "app/api/payments.py", "app/api/conductor.py", "app/api/ideas.py",
                  "app/api/voice_conductor.py", "app/agent/sasha.py", "app/avatar_gate.py",
                  "agapi/activity.py", "agapi/keep_scan.py", "agapi/keep_handoff.py", "agapi/s2_home.py", "agapi/s2_keep.py"):
            self.assertRegex((BACKEND / f).read_text(), r"router = APIRouter\([^)]*dependencies=\[Depends\(require_account\)\]", f)

    def test_the_server_refuses_to_start_with_a_route_without_it(self):
        app = FastAPI()
        bare = APIRouter(prefix="/api/somewhere")

        @bare.get("/person/{pid}")
        async def leak(pid: str):
            return {}
        app.include_router(bare)
        with self.assertRaises(RuntimeError) as e:
            AG.refuse_unguarded(app)
        self.assertIn("GET /api/somewhere/person/{pid}", str(e.exception))
        self.assertIn("refuse_unguarded(app)", (BACKEND / "app" / "main.py").read_text().rstrip().splitlines()[-1])   # last, after every mount


class NoHandlerResolvesByItself(unittest.TestCase):
    def test_only_the_door_calls_the_resolver(self):
        hits = []
        for d in ("app", "agapi", "booking_signer", "products"):
            for f in sorted((BACKEND / d).rglob("*.py")):
                if f.name in ("chat_account.py", "identity.py"):
                    continue
                if re.search(r"\bchat_account\(", f.read_text(encoding="utf-8", errors="ignore")):
                    hits.append(str(f.relative_to(BACKEND)))
        self.assertEqual(hits, [])

    def test_a_handler_without_the_door_fails_loudly(self):
        app = FastAPI()
        r = APIRouter()

        @r.get("/x")
        async def x(request: Request):
            return {"a": await CA.acting(request)}
        app.include_router(r)
        with self.assertRaises(RuntimeError):
            TestClient(app).get("/x")


class TheUnusedDoorsAreGone(unittest.TestCase):
    def test_bookings_search_conversation_voice_heygen_and_card_submissions_are_deleted(self):
        paths = {p for _, p, _ in AG.routes(_app())}
        for gone in ("/bookings/create", "/bookings/{booking_id}", "/bookings/cancel", "/search/hotels", "/conversation/chat",
                     "/voice/transcribe", "/api/heygen/chat/completions", "/api/cards/submit", "/api/cards/pending/list"):
            self.assertNotIn(gone, paths)
        for f in ("bookings.py", "search.py", "conversation.py", "voice.py", "heygen_chat.py"):
            self.assertFalse((BACKEND / "app" / "api" / f).exists(), f)


class OwnerAndStranger(unittest.TestCase):
    """Through the real app and its real door: the owner reads their chat; a stranger (another verified account, or nobody) gets 404."""

    def _client(self, who):
        async def verify(token):
            return {"tok-owner": "acct-owner", "tok-stranger": "acct-stranger"}[token]
        from agapi import person_access as PA
        from app.services import chat_store
        p = [mock.patch("booking_signer.identity.verify_token", verify), mock.patch.object(PA, "warm", mock.AsyncMock()),
             mock.patch.object(chat_store, "session_owner", mock.AsyncMock(return_value="acct-owner")),
             mock.patch.object(chat_store, "get_messages", mock.AsyncMock(return_value=[{"role": "user", "content": "hi"}]))]
        for x in p:
            x.start()
            self.addCleanup(x.stop)
        h = {"Authorization": f"Bearer {who}"} if who else {}
        return TestClient(_app()), h

    def test_owner_reads_stranger_does_not(self):
        c, h = self._client("tok-owner")
        self.assertNotEqual(c.get("/api/chats/s-1", headers=h).status_code, 404)
        c, h = self._client("tok-stranger")
        self.assertEqual(c.get("/api/chats/s-1", headers=h).status_code, 404)
        c, h = self._client(None)
        self.assertEqual(c.get("/api/chats/s-1", headers=h).status_code, 404)

    def test_a_bad_token_is_refused_at_the_router(self):
        c, _ = self._client(None)
        self.assertEqual(c.get("/api/trips", headers={"Authorization": "Basic x"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
