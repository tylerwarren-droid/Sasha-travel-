"""Sasha 153 · NO SIGN-IN WALL: an automatic private guest account per browser (web) and per number (WhatsApp). Real
accounts (auth.users), so their data is theirs alone; capped against abuse; a REAL venue is contacted only for the founder.
Offline.

    cd backend && python -m unittest tests.test_auto_guests_s153 -v
"""
from __future__ import annotations

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
        with mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": "", "SASHA_REAL_CONTACT_ACCOUNTS": ""}):
            self.assertIsNone(GA.real_contact_refusal(A, False))                 # the founder
            self.assertIsNone(GA.real_contact_refusal("g-1", True))              # anyone, at our test venue
            r = GA.real_contact_refusal("g-1", False)                            # a guest, a real venue
            self.assertEqual(r.status_code, 403)
            self.assertIn(b"Nothing was sent", r.body)


class WhatsAppNewNumber(unittest.TestCase):
    def test_a_new_number_gets_its_own_account_and_its_message_is_answered(self):
        from booking_signer import guest_whatsapp as GW, invitations as IV
        asyncio.set_event_loop(asyncio.new_event_loop())
        saved = (GW.STORE, GW._spawn, IV.STORE)
        GW.STORE, IV.STORE = GW.MemoryGuestStore(), IV.MemoryInviteStore()
        spawned = []
        GW._spawn = lambda coro: (spawned.append(coro.__name__), coro.close())

        async def make(origin, ip):
            return {"account_id": "g-wa", "email": "x", "password": "y"}, None
        try:
            with mock.patch.object(GA, "create_guest", make), mock.patch.object(GW, "guest_numbers", lambda: {"+14155238886"}):
                async def no_venue(sender):
                    return False
                out = asyncio.get_event_loop().run_until_complete(GW.dispatch(
                    {"From": "whatsapp:+34600111222", "To": "whatsapp:+14155238886", "Body": "spa in Madrid"}, no_venue))
                ch = asyncio.get_event_loop().run_until_complete(GW.STORE.channel_for(GW.wa_key("+34600111222")))
                stop = asyncio.get_event_loop().run_until_complete(GW.dispatch(
                    {"From": "whatsapp:+34600999888", "To": "whatsapp:+14155238886", "Body": "STOP"}, no_venue))
                none = asyncio.get_event_loop().run_until_complete(GW.STORE.channel_for(GW.wa_key("+34600999888")))
        finally:
            GW.STORE, GW._spawn, IV.STORE = saved
        self.assertEqual(out, "")                                   # answered as a turn, not the "link your account" wall
        self.assertEqual((ch["account_id"], ch["consent_wording_version"]), ("g-wa", "v0"))
        self.assertFalse(GW.consent_at_least("v0", 3))              # never a proactive first message
        self.assertEqual(spawned, ["_turn"])
        self.assertIsNone(none)                                     # STOP from a stranger creates nothing


if __name__ == "__main__":
    unittest.main()
