"""Sasha 153 · NO SIGN-IN WALL: an automatic private guest account per browser (web) and per number (WhatsApp). Real
accounts (auth.users), so their data is theirs alone; capped against abuse; a REAL venue is contacted only for the founder.
Offline.

    cd backend && python -m unittest tests.test_auto_guests_s153 -v
"""
from __future__ import annotations
import tests.founder_fixture  # noqa: F401,E402  (Sasha 249 · the fixtures name the founder; no fallback any more)

import asyncio
import os
import unittest
from unittest import mock

from booking_signer import guest_accounts as GA, ops

A = "11111111-1111-4111-8111-111111111111"


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


class Creating(unittest.TestCase):
    def setUp(self):
        GA._BY_IP.clear(); GA._DAY.clear()
        self.made = []

        async def admin(method, path, body):
            self.made.append(body)
            return 200, {"id": f"g-{len(self.made)}", "email": body["email"]}
        self.p = mock.patch.object(ops, "ADMIN", admin)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_a_real_private_account_on_our_own_domain(self):
        acct, why = run(GA.create_guest("web", "1.2.3.4"))
        self.assertIsNone(why)
        b = self.made[0]
        self.assertTrue(b["email"].endswith("@guests.kanoe.ai"))
        self.assertTrue(b["email_confirm"])                       # no email is ever sent to it
        self.assertEqual(b["app_metadata"], {"kanoe_guest": True, "origin": "web"})
        self.assertGreaterEqual(len(b["password"]), 32)            # random, used once, never kept by us

    def test_capped_per_address_and_per_day(self):
        with mock.patch.dict(os.environ, {"SASHA_GUESTS_PER_IP_HOUR": "2", "SASHA_GUESTS_PER_DAY": "3"}):
            out = [run(GA.create_guest("web", "9.9.9.9"))[1] for _ in range(3)]
            self.assertEqual(out[:2], [None, None])
            self.assertIn("this address", out[2])
            run(GA.create_guest("web", "8.8.8.8"))
            self.assertIn("daily", run(GA.create_guest("web", "7.7.7.7"))[1])


class RealVenues(unittest.TestCase):
    def test_only_the_founder_contacts_a_real_venue(self):
        with mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": tests.founder_fixture.FOUNDER, "SASHA_REAL_CONTACT_ACCOUNTS": ""}):
            self.assertIsNone(GA.real_contact_refusal(A, False))                 # the founder
            self.assertIsNone(GA.real_contact_refusal("g-1", True))              # anyone, at our test venue
            r = GA.real_contact_refusal("g-1", False)                            # a guest, a real venue
            self.assertEqual(r.status_code, 403)
            self.assertIn(b"Nothing was sent", r.body)


# Sasha 253 · item 5 — RETIRED by Tyler's decision (mailbox 807): WhatsAppNewNumber (a new number got its own guest account and its
# message was answered). An unlinked number now gets ONE line telling it to link at /you, and no account is made:
# tests/test_s253_one_brain_all.py Unlinked pins that.


if __name__ == "__main__":
    unittest.main()
