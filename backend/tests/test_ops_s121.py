"""Sasha 121 · "invite a guest" — founder only; Supabase's own link, emailed from Sasha; never the token logged. Offline.

    cd backend && python -m unittest tests.test_ops_s121 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import emailing as E, ops as OPS


class Invite(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": "", "SASHA_WEB_URL": "https://project.kanoe.ai",
                                                "SASHA_EMAIL_FROM": "Sasha <sasha@booking.kanoe.ai>"})
        self.env.start()
        self.admin_calls, self.mails = [], []

        async def admin(method, path, body):
            self.admin_calls.append(body)
            if body["type"] == "invite" and body["email"] == "known@example.com":
                return 422, {"msg": "A user with this email address has already been registered"}
            return 200, {"properties": {"hashed_token": "abc123"}}
        self.saved = (OPS.ADMIN, E.send)
        OPS.ADMIN = admin

        async def send(http, email):
            self.mails.append(email)
            return E.Sent(True, "re_1", 200, None, None)
        E.send = send
        app = FastAPI()

        @app.middleware("http")
        async def who(request, call_next):
            request.state.account = request.headers.get("x-test-account")
            return await call_next(request)
        app.include_router(OPS.router)
        self.c = TestClient(app)

    def tearDown(self):
        OPS.ADMIN, E.send = self.saved
        self.env.stop()

    def post(self, account, email):
        return self.c.post("/ops/invite", json={"email": email}, headers={"x-test-account": account})

    def test_founder_only(self):
        r = self.post("22222222-2222-4222-8222-222222222222", "eva@example.com")
        self.assertEqual((r.status_code, r.json()["rule"]), (403, "founder_only"))
        self.assertEqual(self.mails, [])

    def test_a_new_address_gets_an_invite_and_a_known_one_a_sign_in_link(self):
        r = self.post("11111111-1111-4111-8111-111111111111", "eva@example.com")
        self.assertEqual(r.status_code, 200, r.text)
        m = self.mails[-1]
        self.assertEqual((m["to"], m["subject"]), ("eva@example.com", "You're invited to Sasha by Kanoe"))
        self.assertIn("https://project.kanoe.ai/auth/confirm?token_hash=abc123&type=invite&next=/you", m["text"])
        self.assertIn("always tells them she is an AI", m["text"])
        self.assertNotIn("abc123", r.text)                                    # the token never comes back to the browser
        r = self.post("11111111-1111-4111-8111-111111111111", "known@example.com")
        self.assertEqual(r.json()["kind"], "magiclink")
        self.assertIn("type=magiclink", self.mails[-1]["text"])

    def test_not_an_email(self):
        self.assertEqual(self.post("11111111-1111-4111-8111-111111111111", "nope").json()["rule"], "email_invalid")


if __name__ == "__main__":
    unittest.main()
