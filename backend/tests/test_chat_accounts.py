"""S-62 step 7 · chat history per account: a verified guest's chats, itineraries, offers and trips are theirs alone;
the public demo keeps working with no token; a bad token is refused, never turned into the demo.

    cd backend && python -m unittest tests.test_chat_accounts -v
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from unittest import mock

from booking_signer import identity as I
from tests.test_identity import GUEST, JWK, PROJECT, token


class ChatAccounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        asyncio.set_event_loop(asyncio.new_event_loop())   # app.services.ideas_agent makes an asyncio.Lock at import
        from app.services import chat_store
        cls.CS = chat_store

    def setUp(self):
        from fastapi.testclient import TestClient
        from app.main import app
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (self.CS.DB_PATH, self.CS._inited, I.FETCH)
        self.CS.DB_PATH, self.CS._inited = os.path.join(self.tmp.name, "chats.db"), False
        self.env = mock.patch.dict(os.environ, {"SASHA_SUPABASE_URL": PROJECT, "CONDUCTOR_API_SECRET": ""})
        self.env.start()

        async def fetch():
            return {"keys": [JWK]}
        I.FETCH = fetch
        I.reset_cache()
        self.c = TestClient(app)
        self.guest = {"Authorization": f"Bearer {token()}"}
        run = lambda co: asyncio.get_event_loop().run_until_complete(co)
        run(self.CS.save_turn("demo-sess", self.CS.DEMO_USER_ID, "hi", "hello", title="demo chat"))
        run(self.CS.save_turn("guest-sess", GUEST, "my secret plans", "noted", title="guest chat"))
        run(self.CS.save_itinerary("guest-itin", "guest-sess", GUEST, "Guest trip", 100, {"days": []}))

    def tearDown(self):
        self.CS.DB_PATH, self.CS._inited, I.FETCH = self.saved
        I.reset_cache()
        self.env.stop()
        self.tmp.cleanup()

    def test_each_sees_only_their_own_chats(self):
        mine = self.c.get("/api/chats", headers=self.guest).json()
        self.assertEqual(([s["id"] for s in mine["sessions"]], mine["user"]["id"]), (["guest-sess"], GUEST))
        # Sasha 142 · an anonymous visitor is the PUBLIC demo: none of the founder's chats; his proxied session sees them
        public = self.c.get("/api/chats").json()
        self.assertEqual([s["id"] for s in public["sessions"]], [])
        with mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": "k-s142", "FOUNDER_ACCOUNT_ID": ""}):
            founder = self.c.get("/api/chats", headers={"x-sasha-session": "founder", "x-sasha-booking-key": "k-s142"}).json()
            forged = self.c.get("/api/chats", headers={"x-sasha-session": "founder"}).json()
        self.assertEqual([s["id"] for s in founder["sessions"]], ["demo-sess"])
        self.assertEqual([s["id"] for s in forged["sessions"]], [])

    def test_someone_elses_chat_answers_as_one_that_does_not_exist(self):
        self.assertEqual(self.c.get("/api/chats/guest-sess", headers=self.guest).status_code, 200)
        for headers in ({}, {"Authorization": f"Bearer {token(sub='33333333-3333-4333-8333-333333333333')}"}):
            r, ghost = self.c.get("/api/chats/guest-sess", headers=headers), self.c.get("/api/chats/no-such", headers=headers)
            self.assertEqual((r.status_code, r.json()), (ghost.status_code, ghost.json()))
            self.assertEqual(r.status_code, 404)
        self.assertEqual(self.c.get("/api/chats/demo-sess", headers=self.guest).status_code, 404)

    def test_a_bad_token_is_refused_never_the_demo(self):
        r = self.c.get("/api/chats", headers={"Authorization": "Bearer not-a-token"})
        self.assertEqual((r.status_code, r.json()["detail"]["rule"]), (401, "account_token_invalid"))

    def test_the_conductor_files_a_turn_under_its_account_and_never_into_someone_elses_session(self):
        seen = {}

        async def fake_conduct(**kw):
            seen.update(kw)
            return {"response": "ok", "intents": [], "photos": [], "tools_used": [], "messages": []}
        with mock.patch("app.api.conductor.conduct", fake_conduct):
            r = self.c.post("/api/agents/conductor", json={"message": "hello", "session_id": "demo-sess"}, headers=self.guest)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(seen["user_id"], GUEST)
        self.assertNotEqual(r.json()["session_id"], "demo-sess")                       # a new session, not the demo's
        msgs = asyncio.get_event_loop().run_until_complete(self.CS.get_messages("demo-sess"))
        self.assertEqual([m["content"] for m in msgs], ["hi", "hello"])                 # nothing appended to someone else's
        with mock.patch("app.api.conductor.conduct", fake_conduct):
            r = self.c.post("/api/agents/conductor", json={"message": "again", "session_id": "guest-sess"}, headers=self.guest)
        self.assertEqual(r.json()["session_id"], "guest-sess")                          # their own continues

    def test_classify_never_looks_into_someone_elses_itinerary(self):
        with mock.patch("app.api.conductor.classify_intents", new=mock.AsyncMock(return_value={"intents": [], "primary": None})) as ci:
            self.c.post("/api/agents/classify", json={"message": "yes please", "session_id": "guest-sess"})
        self.assertIs(ci.call_args.args[2], False)                                      # the demo caller: no itinerary seen
        with mock.patch("app.api.conductor.classify_intents", new=mock.AsyncMock(return_value={"intents": [], "primary": None})) as ci:
            self.c.post("/api/agents/classify", json={"message": "yes please", "session_id": "guest-sess"}, headers=self.guest)
        self.assertIs(ci.call_args.args[2], True)

    def test_only_your_own_itinerary_can_be_paid_for(self):
        demo = self.c.post("/api/payments/reserve", json={"itinerary_id": "guest-itin"})
        self.assertEqual(demo.status_code, 404)
        mine = self.c.post("/api/payments/reserve", json={"itinerary_id": "guest-itin"}, headers=self.guest)
        self.assertNotEqual(mine.status_code, 404, mine.text)


if __name__ == "__main__":
    unittest.main()
