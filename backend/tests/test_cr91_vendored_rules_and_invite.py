"""CR 91 · (1) AgAPI's booking rules, vendored byte-identical (backend/agapi/booking_rules/): the sums hold and every vector passes here
too (EU 250 §A3). (2) /api/booking/ops/invite-from-agapi: only AgAPI's HMAC-signed request; the same invitation as the founder's
/ops/invite; returns the person's account id. Supabase and the email are faked: no test creates a user or sends mail.

    cd backend && python -m unittest tests.test_cr91_vendored_rules_and_invite -v
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
import unittest
from unittest import mock

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agapi", "booking_rules")


class VendoredRules(unittest.TestCase):
    def test_byte_identical_to_agapi(self):
        for line in open(os.path.join(HERE, "SHA256SUMS")):
            want, name = line.split()
            self.assertEqual(hashlib.sha256(open(os.path.join(HERE, name), "rb").read()).hexdigest(), want, f"{name}: re-vendor it from AgAPI")

    def test_every_vector_here_too(self):
        from agapi.booking_rules import test_booking_rules as TBR
        TBR.Vectors.test_every_vector(self)


class InviteFromAgapi(unittest.TestCase):
    def call(self, body: dict, secret="s3cret-for-tests", tamper=False):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from booking_signer import ops as OPS
        app = FastAPI(); app.include_router(OPS.router)
        raw = json.dumps(body); t, n = int(time.time()), secrets.token_urlsafe(16)
        sig = f"t={t},n={n},v1=" + hmac.new(secret.encode(), f"{t}.{n}.{raw}".encode(), hashlib.sha256).hexdigest()
        if tamper:
            raw = raw.replace("@", "+evil@")
        return TestClient(app).post("/ops/invite-from-agapi", content=raw, headers={"content-type": "application/json", "X-Kanoe-Invite-Signature": sig})

    def setUp(self):
        from booking_signer import ops as OPS, emailing as E
        self.sent = []

        async def admin(method, path, body):
            return 200, {"id": "33333333-3333-4333-8333-333333333333", "hashed_token": "th_x"}

        async def send(http, msg):
            self.sent.append(msg["to"])
            return type("R", (), {"sent": True, "why": None})()
        for p in (mock.patch.object(OPS, "ADMIN", admin), mock.patch.object(E, "send", send),
                  mock.patch.dict(os.environ, {"SASHA_AGAPI_INVITE_SECRET": "s3cret-for-tests", "SASHA_EMAIL_FROM": "sasha@example.com"})):
            p.start()
            self.addCleanup(p.stop)

    def test_signed_invite_returns_the_account(self):
        r = self.call({"email": "newperson@example.com"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["account_id"], "33333333-3333-4333-8333-333333333333")
        self.assertEqual(self.sent, ["newperson@example.com"])

    def test_unsigned_or_tampered_is_refused_and_nothing_is_sent(self):
        self.assertEqual(self.call({"email": "x@example.com"}, secret="wrong").status_code, 401)
        self.assertEqual(self.call({"email": "x@example.com"}, tamper=True).status_code, 401)
        self.assertEqual(self.sent, [])
