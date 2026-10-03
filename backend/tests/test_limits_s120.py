"""Sasha 120 · per-guest limits and the per-guest calls switch, before guest sign-up opens. Offline.

    cd backend && python -m unittest tests.test_limits_s120 -v
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from booking_signer import ladder as L, limits as LM

GUEST, OTHER, FOUNDER = "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333", "11111111-1111-4111-8111-111111111111"


class Limits(unittest.TestCase):
    def setUp(self):
        LM.reset()
        self.env = mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": "", "SASHA_FINDS_PER_HOUR": "3", "SASHA_FORMS_PER_DAY": "2",
                                                "SASHA_CALLS_ACCOUNTS": "", "SASHA_CALLS_ENABLED": "1", "BLAND_API_KEY": "k"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        LM.reset()

    def test_a_guest_is_capped_per_account_and_the_founder_is_not(self):
        for _ in range(3):
            self.assertIsNone(LM.check(GUEST, "find"))
        over = LM.check(GUEST, "find")
        self.assertEqual(over.status_code, 429)
        self.assertIn(b"3 searches this hour", over.body)
        self.assertIsNone(LM.check(OTHER, "find"))                       # another guest has their own window
        for _ in range(10):
            self.assertIsNone(LM.check(FOUNDER, "find"))                 # the founder's account is exempt
        self.assertIsNone(LM.check(GUEST, "form_send"))
        self.assertIsNone(LM.check(GUEST, "form_send"))
        self.assertEqual(LM.check(GUEST, "form_send").status_code, 429)

    def test_calls_are_off_for_a_guest_until_the_founder_lists_them(self):
        self.assertTrue(LM.calls_on(FOUNDER))
        self.assertFalse(LM.calls_on(GUEST))
        self.assertEqual(L.calls_ready(GUEST), LM.CALLS_OFF_FOR_ACCOUNT)
        self.assertIsNone(L.calls_ready(FOUNDER))
        with mock.patch.dict(os.environ, {"SASHA_CALLS_ACCOUNTS": f"{OTHER}, {GUEST}"}):
            self.assertTrue(LM.calls_on(GUEST))
            self.assertIsNone(L.calls_ready(GUEST))

    def test_a_guests_phone_rung_says_why_it_is_off(self):
        read = {"country": "ES", "facts": [{"kind": "phone", "value": "+34910000000", "source_label": "their website", "source_kind": "site"}]}
        phone = next(r for r in L.choose(read, account=GUEST)["rungs"] if r["rung"] == "phone")
        self.assertEqual((phone["available"], phone["why_not"]), (False, LM.CALLS_OFF_FOR_ACCOUNT))
        self.assertTrue(next(r for r in L.choose(read, account=FOUNDER)["rungs"] if r["rung"] == "phone")["available"])


if __name__ == "__main__":
    unittest.main()
