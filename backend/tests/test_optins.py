"""S-54 · the refusal check (booking_signer/optins.py) — the rule itself, without routes. Offline.

    cd backend && python -m unittest tests.test_optins -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from booking_signer import optins as O

T = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
NUM = "+34600111222"


def row(i, status, channel="whatsapp", scope=NUM, days_ago=0):
    at = T - timedelta(days=days_ago)
    return {"id": i, "venue_id": "v", "channel": channel, "scope": scope, "status": status, "recorded_at": at,
            "withdrawn_at": at if status == "withdrawn" else None, "withdrawn_how": "STOP" if status == "withdrawn" else None}


class RefusalCheck(unittest.TestCase):
    def test_phone_and_email_need_no_opt_in(self):
        self.assertIsNone(O.check_send([], "phone"))
        self.assertIsNone(O.check_send([], "email"))

    def test_whatsapp_and_form_submission_need_an_active_opt_in_for_that_exact_scope(self):
        self.assertEqual(O.check_send([], "whatsapp", NUM).rule, "no_active_optin")
        self.assertEqual(O.check_send([], "web_submit", "https://x.test/book").rule, "no_active_optin")
        self.assertIsNone(O.check_send([row(1, "active")], "whatsapp", NUM))
        # a number that changed does not inherit the consent
        self.assertEqual(O.check_send([row(1, "active")], "whatsapp", "+34600999999").rule, "no_active_optin")
        # consent to WhatsApp is not consent to the form
        self.assertEqual(O.check_send([row(1, "active")], "web_submit", NUM).rule, "no_active_optin")

    def test_any_stop_on_any_channel_ends_every_channel(self):
        rows = [row(1, "active", days_ago=9), row(2, "withdrawn", days_ago=1)]
        for ch in ("phone", "email", "whatsapp"):
            r = O.check_send(rows, ch, NUM)
            self.assertEqual(r.rule, "venue_opted_out", ch)
        self.assertIn("(whatsapp, 2026-09-29, \"STOP\")", r.message)

    def test_a_new_opt_in_after_the_withdrawal_lifts_it_and_order_is_by_time_not_by_list(self):
        rows = [row(2, "active", days_ago=1), row(1, "withdrawn", days_ago=5)]
        self.assertIsNone(O.check_send(rows, "phone"))
        self.assertIsNone(O.check_send(rows, "whatsapp", NUM))

    def test_a_channel_sasha_does_not_send_on_is_refused(self):
        self.assertEqual(O.check_send([], "sms").rule, "channel_unknown")

    def test_the_venue_is_its_place_id_then_its_own_site_then_its_name(self):
        site = {"source_kind": "site", "source_url": "https://www.lacontra.es/contacto"}
        self.assertEqual(O.venue_id_of({"listing": {"place_id": "ChIJ1"}, "facts": [site]}), "places:ChIJ1")
        self.assertEqual(O.venue_id_of({"listing": None, "facts": [site]}), "host:lacontra.es")
        self.assertEqual(O.venue_id_of({"name": "La  Contra", "country": "es", "facts": []}), "name:la contra|ES")


class Store(unittest.IsolatedAsyncioTestCase):
    async def test_no_venue_id_or_no_store_is_not_checked(self):
        saved = O.OPTIN_STORE
        try:
            O.OPTIN_STORE = O.MemoryOptinStore()
            await O.OPTIN_STORE.add(row(0, "withdrawn") | {"venue_id": "v"})
            self.assertIsNone(await O.refusal_for(None, "phone"))       # the test line, or a call prepared before S-54
            self.assertEqual((await O.refusal_for("v", "phone")).rule, "venue_opted_out")
        finally:
            O.OPTIN_STORE = saved


if __name__ == "__main__":
    unittest.main()
