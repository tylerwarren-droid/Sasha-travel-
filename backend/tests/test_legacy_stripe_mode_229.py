"""Sasha 229 · S1's legacy Stripe Checkout path (/api/payments/create-checkout) runs on Stripe TEST for the beta:
SASHA_LEGACY_STRIPE_MODE = test (default) | live. Fake keys only.

    cd backend && python -m unittest tests.test_legacy_stripe_mode_229 -v
"""
from __future__ import annotations

import unittest
from unittest import mock

from app.api import payments as P

ENV = {"STRIPE_SECRET_KEY": "sk_live_FAKE229", "STRIPE_TEST_SECRET_KEY": "sk_test_FAKE229", "STRIPE_WEBHOOK_SECRET": "whsec_FAKE_A"}


class Mode(unittest.TestCase):
    def keys(self, env):
        with mock.patch.dict("os.environ", env, clear=True):
            return P._legacy_keys("live" if env.get("SASHA_LEGACY_STRIPE_MODE", "").strip().lower() == "live" else "test")

    def test_unset_is_test_with_s2s_test_key(self):
        self.assertEqual(self.keys(ENV), ("sk_test_FAKE229", "whsec_FAKE_A"))

    def test_test_prefers_its_own_webhook_secret(self):
        self.assertEqual(self.keys({**ENV, "STRIPE_TEST_WEBHOOK_SECRET": "whsec_FAKE_T"})[1], "whsec_FAKE_T")

    def test_live_is_exactly_as_before(self):
        self.assertEqual(self.keys({**ENV, "SASHA_LEGACY_STRIPE_MODE": "live"}), ("sk_live_FAKE229", "whsec_FAKE_A"))

    def test_test_never_uses_a_live_key_even_misfiled(self):
        self.assertEqual(self.keys({**ENV, "STRIPE_TEST_SECRET_KEY": "sk_live_MISFILED"})[0], "")   # → 501, never a live charge

    def test_anything_else_is_test(self):
        self.assertEqual(self.keys({**ENV, "SASHA_LEGACY_STRIPE_MODE": "LIVE-ish"})[0], "sk_test_FAKE229")


if __name__ == "__main__":
    unittest.main()
