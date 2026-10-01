"""S-62 step 1 · the account is VERIFIED: a Supabase token's signature, issuer, audience and expiry, or the founder's
session. A forged, expired, foreign or absent token refuses. Offline: the keys are made here.

    cd backend && python -m unittest tests.test_identity -v
"""
from __future__ import annotations

import base64
import os
import time
import unittest
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from booking_signer import identity as I, routes
from booking_signer.account import DEMO_ACCOUNT_ID

GUEST = "22222222-2222-4222-8222-222222222222"
PROJECT = "https://testref.supabase.co"
FOUNDER = "33333333-3333-4333-8333-333333333333"


def _b64(n: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()


def keypair(kid):
    k = ec.generate_private_key(ec.SECP256R1())
    pub = k.public_key().public_numbers()
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return pem, {"kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig", "kid": kid, "x": _b64(pub.x), "y": _b64(pub.y)}


SIGN, JWK = keypair("kid-real")
FORGER, _ = keypair("kid-real")          # same kid, different key: a forgery


def token(pem=SIGN, kid="kid-real", **over):
    claims = {"sub": GUEST, "role": "authenticated", "aud": I.AUDIENCE, "iss": f"{PROJECT}/auth/v1", "exp": int(time.time()) + 600, **over}
    return jwt.encode(claims, pem, algorithm="ES256", headers={"kid": kid})


class Identity(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": "k-test", "SASHA_CALL_SWEEP": "0", "FOUNDER_ACCOUNT_ID": "",
                                               "SASHA_SUPABASE_URL": PROJECT})
        self.env.start()
        self.fetches = 0

        async def fetch():
            self.fetches += 1
            return {"keys": [JWK]}
        self.saved, I.FETCH = I.FETCH, fetch
        I.reset_cache()
        app = FastAPI()
        app.include_router(routes.router)
        self.c = TestClient(app, headers={"x-sasha-booking-key": "k-test"})

    def tearDown(self):
        I.FETCH = self.saved
        I.reset_cache()
        self.env.stop()

    def who(self, **headers):
        """GET /reservations needs an account; without storage it answers 503 — past the account check."""
        r = self.c.get("/api/booking/reservations", headers=headers)
        return r.status_code, (r.json().get("detail") or {}).get("rule") if r.status_code == 401 else None

    def test_a_verified_token_is_the_account(self):
        import asyncio
        self.assertEqual(asyncio.run(I.verify_token(token())), GUEST)
        self.assertNotEqual(self.who(authorization=f"Bearer {token()}")[0], 401)

    def test_forged_expired_foreign_or_malformed_tokens_refuse(self):
        cases = {"forged": (token(pem=FORGER), "account_token_invalid"),
                 "unknown key": (token(kid="kid-other"), "account_token_invalid"),
                 "expired": (token(exp=int(time.time()) - 5), "account_token_expired"),
                 "another project": (token(iss="https://evil.supabase.co/auth/v1"), "account_token_invalid"),
                 "not for users": (token(aud="service_role"), "account_token_invalid"),
                 "anon role": (token(role="anon"), "account_token_invalid"),
                 "garbage": ("not-a-token", "account_token_invalid")}
        for name, (t, rule) in cases.items():
            self.assertEqual(self.who(authorization=f"Bearer {t}"), (401, rule), name)
        self.assertEqual(self.who(authorization="Basic abc"), (401, "account_token_invalid"))

    def test_no_account_refuses_and_sessions_map_as_said(self):
        self.assertEqual(self.who(), (401, "account_required"))                       # the key alone names nobody
        self.assertEqual(self.who(**{"x-sasha-session": "anyone"}), (401, "account_session_unknown"))
        import asyncio
        from starlette.requests import Request
        req = lambda h: Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in h.items()]})
        self.assertEqual(asyncio.run(I.resolve(req({"x-sasha-session": "demo"}))), DEMO_ACCOUNT_ID)
        self.assertEqual(asyncio.run(I.resolve(req({"x-sasha-session": "founder"}))), DEMO_ACCOUNT_ID)   # until he has his own
        with mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": FOUNDER}):
            self.assertEqual(asyncio.run(I.resolve(req({"x-sasha-session": "founder"}))), FOUNDER)

    def test_no_project_configured_refuses_said(self):
        """S-69 · no project ref in code: without SASHA_SUPABASE_URL, a token is refused (503), never checked elsewhere."""
        with mock.patch.dict(os.environ, {"SASHA_SUPABASE_URL": ""}):
            r = self.c.get("/api/booking/reservations", headers={"authorization": f"Bearer {token()}"})
        self.assertEqual((r.status_code, r.json()["detail"]["rule"]), (503, "sign_in_not_configured"))
        self.assertEqual(self.fetches, 0)
        with mock.patch.dict(os.environ, {"SASHA_SUPABASE_URL": "https://evil.example.com"}):
            self.assertIsNone(I.project_url())

    def test_keys_unreachable_fail_closed(self):
        async def down():
            raise OSError("no route")
        I.FETCH, I._cache["keys"] = down, None
        r = self.c.get("/api/booking/reservations", headers={"authorization": f"Bearer {token()}"})
        self.assertEqual((r.status_code, r.json()["detail"]["rule"]), (503, "account_keys_unavailable"))

    def test_keys_are_held_then_refetched_for_a_new_kid(self):
        import asyncio
        asyncio.run(I.verify_token(token()))
        asyncio.run(I.verify_token(token()))
        self.assertEqual(self.fetches, 1)
        with self.assertRaises(Exception):
            asyncio.run(I.verify_token(token(kid="kid-rotated")))
        self.assertEqual(self.fetches, 2)                                               # an unknown kid refetches once


if __name__ == "__main__":
    unittest.main()
