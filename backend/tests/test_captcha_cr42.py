"""CR 42 · the test venue's CAPTCHA takes a REAL key: reCAPTCHA v2 (checkbox) or Cloudflare Turnstile by SASHA_TEST_CAPTCHA; the
site key in the page, the secret checked server-side on submit — a failed or missing token is NOT booked. Until both halves of a
pair are set, the provider's documented always-pass TEST pair. Offline: the provider's siteverify is replaced."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import form_rung as FR

FORM = {"fecha": "2026-10-20", "hora": "21:00", "personas": "2", "nombre": "Ana Prueba", "email": "ana@example.com",
        "telefono": "600000000", "token": "t"}
CLEAN = {k: "" for k in ("SASHA_TEST_CAPTCHA", "RECAPTCHA_SITE_KEY", "RECAPTCHA_SECRET_KEY", "TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY")}


class Captcha(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(FR.router, prefix="/api/booking")
        self.c = TestClient(app)
        self.calls = []
        self.answer = True

        async def verify(kind, token, secret):
            self.calls.append((kind, token, secret))
            return (bool(token) and self.answer), "stub"
        p = mock.patch.object(FR, "CAPTCHA_VERIFY", verify)
        p.start()
        self.addCleanup(p.stop)

    def env(self, **kv):
        p = mock.patch.dict(os.environ, {**CLEAN, **kv})
        p.start()
        self.addCleanup(p.stop)

    def page(self):
        return self.c.get("/api/booking/test-venue/captcha").text

    def book(self, **extra):
        before = len(FR.TEST_SUBMISSIONS)
        r = self.c.post("/api/booking/test-venue/captcha", data={**FORM, **extra})
        return r, len(FR.TEST_SUBMISSIONS) - before

    def test_default_is_googles_test_key(self):
        self.env()
        html = self.page()
        self.assertIn('class="g-recaptcha" data-sitekey="6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"', html)
        self.assertIn("www.google.com/recaptcha/api.js", html)
        self.assertFalse(FR.captcha_status()["real_key"])

    def test_a_real_recaptcha_key(self):
        self.env(RECAPTCHA_SITE_KEY="6Lreal-site", RECAPTCHA_SECRET_KEY="real-secret")
        self.assertIn('data-sitekey="6Lreal-site"', self.page())
        r, n = self.book(**{"g-recaptcha-response": "tok"})
        self.assertEqual((r.status_code, n), (200, 1))
        self.assertIn("Reserva confirmada", r.text)
        self.assertEqual(self.calls[-1], ("recaptcha", "tok", "real-secret"))

    def test_turnstile_by_env(self):
        self.env(SASHA_TEST_CAPTCHA="turnstile", TURNSTILE_SITE_KEY="0xSITE", TURNSTILE_SECRET_KEY="0xSECRET")
        html = self.page()
        self.assertIn('class="cf-turnstile" data-sitekey="0xSITE"', html)
        self.assertIn("challenges.cloudflare.com/turnstile/v0/api.js", html)
        self.assertNotIn("g-recaptcha", html)
        r, n = self.book(**{"cf-turnstile-response": "tok"})
        self.assertEqual((r.status_code, n), (200, 1))
        self.assertEqual(self.calls[-1], ("turnstile", "tok", "0xSECRET"))

    def test_turnstile_test_key_until_both_are_set(self):
        self.env(SASHA_TEST_CAPTCHA="turnstile", TURNSTILE_SITE_KEY="0xSITE")      # the secret not yet set
        self.assertIn('data-sitekey="1x00000000000000000000AA"', self.page())
        s = FR.captcha_status()
        self.assertEqual((s["real_key"], s["site_key_set"], s["secret_set"]), (False, True, False))

    def test_a_missing_or_failed_token_is_not_booked(self):
        self.env(RECAPTCHA_SITE_KEY="6Lreal-site", RECAPTCHA_SECRET_KEY="real-secret")
        r, n = self.book()
        self.assertEqual((r.status_code, n), (403, 0))
        self.assertIn("Reserva no realizada", r.text)
        self.answer = False
        r, n = self.book(**{"g-recaptcha-response": "bad"})
        self.assertEqual((r.status_code, n), (403, 0))

    def test_the_failure_page_reads_as_a_no(self):
        from booking_signer import followup as FU
        self.env()
        r, _ = self.book()
        o = {"when": {"mode": "at", "at": "2026-10-20T21:00"}, "who": {"name": "Ana Prueba"}, "how_many": {"count": 2, "unit": "people"},
             "what": {"activity": "dinner", "activity_venue_lang": "cena"}}
        text = " ".join(r.text.replace("<", " <").split())
        import re
        self.assertEqual(FU.reply_reading(re.sub(r"<[^>]+>", " ", text), o)["result"], "declined")

    def test_status_never_shows_a_key(self):
        self.env(RECAPTCHA_SITE_KEY="6Lreal-site", RECAPTCHA_SECRET_KEY="real-secret")
        body = self.c.get("/api/booking/test-venue-captcha/status").text
        self.assertNotIn("real-secret", body)
        self.assertNotIn("6Lreal-site", body)
        self.assertIn('"real_key":true', body)

    def test_no_token_never_reaches_the_network(self):
        import asyncio
        ok, why = asyncio.run(FR._captcha_verify("recaptcha", "", "s"))
        self.assertFalse(ok)
        self.assertIn("no token", why)

    def test_turnstiles_hidden_token_field_is_a_challenge(self):
        live = {"fields": [{"name": "cf-turnstile-response", "type": "hidden", "hidden_by_style": False, "autocomplete_off_trap": False,
                            "required": False, "label": ""}]}
        self.assertEqual([x["role"] for x in FR.roles_for(live, {"fields": {}})], ["challenge"])


if __name__ == "__main__":
    unittest.main()
