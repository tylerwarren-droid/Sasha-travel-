"""S-80 · "book dinner with Jon this week" (§5 tests 1–6), path I: the intent, the slots, minimisation, no first
contact, Jon's scope, and the booking staying the inviter's. Offline.

    cd backend && python -m unittest tests.test_invitations_s80 -v
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import guest_whatsapp as GW, invitations as IV
from tests import test_guest_whatsapp_s75 as TG   # a module: its own tests are not collected twice

MAD = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)   # Friday
JON = "+447700900555"


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


class Intent(unittest.TestCase):
    def test_1_the_intent(self):
        r = IV.invite_request("book dinner with Jon this week", NOW)
        self.assertEqual((r["invitee"], r["activity"], r["window"]), ("Jon", "dinner", (date(2026, 10, 2), date(2026, 10, 4))))
        self.assertEqual(IV.invite_request("invite Ana to lunch tomorrow", NOW)["invitee"], "Ana")
        self.assertEqual(IV.invite_request("cena con Lucía el sábado en Chamberí", NOW)["area"], "Chamberí")
        self.assertIsNone(IV.invite_request("dinner for two in Chamberí on Saturday", NOW))
        self.assertIsNone(IV.invite_request("dinner with my wife", NOW))
        self.assertIsNone(IV.invite_request("book dinner with Jon", NOW)["window"])     # asked once

    def test_2_slots(self):
        days = (date(2026, 10, 2), date(2026, 10, 4))
        s = IV.slots(days, [], [], "dinner", NOW)
        self.assertEqual([x["start"][:16] for x in s], ["2026-10-02T21:00", "2026-10-03T21:00", "2026-10-04T21:00"])   # different days
        busy = [(datetime(2026, 10, 3, 20, 0, tzinfo=MAD), datetime(2026, 10, 3, 23, 30, tzinfo=MAD))]
        self.assertNotIn("2026-10-03", [x["start"][:10] for x in IV.slots(days, busy, [], "dinner", NOW)])
        all_busy = [(datetime(2026, 10, 2, 0, 0, tzinfo=MAD), datetime(2026, 10, 5, 0, 0, tzinfo=MAD))]
        self.assertEqual(IV.slots(days, all_busy, [], "dinner", NOW), [])


class PathI(TG.Base):
    def setUp(self):
        super().setUp()
        self.iv_saved = IV.STORE
        IV.STORE = IV.MemoryInviteStore()
        self.link()
        run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": TG.NOW, "link_tries": []}))
        app = FastAPI(); app.include_router(IV.router)
        self.web = TestClient(app)
        IV._HITS.clear()

    def tearDown(self):
        IV.STORE = self.iv_saved
        super().tearDown()

    def invite(self):
        with mock.patch.object(IV, "NOW", lambda: TG.NOW):
            self.say("book dinner with Jon this week")
        return next(iter(IV.STORE.rows.values()))

    def test_the_inviter_gets_a_share_link_and_sasha_writes_to_no_one_new(self):
        inv = self.invite()
        b = self.bodies()
        self.assertTrue(b[0].startswith("I can't see your calendar, so these are suggestions:"))
        self.assertIn(f"https://wa.me/?text=", b[1])                                  # Ana's own WhatsApp, no number
        self.assertIn(inv["code"], b[1])
        self.assertTrue(all(s["to"] == TG.GUEST for s in GW.SENDER.sent))            # 4 · no first contact to Jon
        self.assertEqual((inv["inviter_first_name"], inv["party_size"]), ("Tyler", 2))

    def test_3_minimisation_and_the_choice(self):
        inv = self.invite()
        view = self.web.get(f"/invite/{inv['code']}").json()
        self.assertEqual(set(view), {"inviter", "invitee", "activity", "slots", "chosen", "status", "consent", "consent_sha256", "whatsapp"})
        dumped = json.dumps(view)
        for leak in (TG.GUEST, "Warren", "@", "AB12", "Botavara"):
            self.assertNotIn(leak, dumped)
        self.assertEqual(self.web.post(f"/invite/{inv['code']}/choose", json={"slot": 1, "consent_sha256": "x"}).json()["rule"], "consent_stale")
        with mock.patch.object(IV, "NOW", lambda: TG.NOW):
            r = self.web.post(f"/invite/{inv['code']}/choose", json={"slot": 1, "consent_sha256": view["consent_sha256"], "first_name": "Jon"}).json()
        self.assertEqual(r["status"], "chosen")
        told = self.bodies()[-2:]
        self.assertTrue(told[0].startswith("Jon picked Saturday 3 October, 21:00."))
        self.assertEqual(told[1], 'Where should I look — an area, e.g. "Chamberí"?')
        self.assertNotIn(JON, " ".join(self.bodies()))

    def test_3b_jons_tap_never_waits_for_the_inviters_search(self):
        """Sasha 117 · live: the choose answered after 24 s — it awaited the inviter's whole place search."""
        import inspect
        src = inspect.getsource(IV.invite_choose)
        self.assertNotIn("await _tell_inviter", src)
        self.assertEqual(src.count("background.add_task(_tell_inviter_logged"), 2)

    def test_4_jon_opts_in_only_to_this_invitation_and_a_bad_code_is_refused(self):
        inv = self.invite()
        self.assertIsNone(run(IV.on_invite_message(JON, "hello")))
        self.assertEqual(run(IV.on_invite_message(JON, "INVITE ZZZZZZZZ")), IV.BAD_INVITE)
        self.assertTrue(run(IV.on_invite_message(JON, f"invite {inv['code']}")).startswith("You'll hear from Sasha about this dinner only."))
        self.assertEqual(IV.STORE.rows[inv["code"]]["invitee_wa_sha256"], GW.wa_key(JON))
        self.assertEqual(run(IV.on_invitee_stop(JON, "STOP")), "OK — no more messages about it.")
        self.assertIsNone(IV.STORE.rows[inv["code"]]["invitee_number_e164"])

    def test_5_jon_is_not_a_guest(self):
        """After INVITE, Jon's "write me a poem" is not a chat: he is not linked, so the webhook answers with the one
        onboarding sentence and the model is never called (the test's model mock would raise)."""
        self.invite()
        self.assertIsNone(run(GW.STORE.channel_for(GW.wa_key(JON))))

    def test_6_the_booking_is_the_inviters(self):
        inv = self.invite()
        view = self.web.get(f"/invite/{inv['code']}").json()
        with mock.patch.object(IV, "NOW", lambda: TG.NOW):
            self.web.post(f"/invite/{inv['code']}/choose", json={"slot": 0, "consent_sha256": view["consent_sha256"]})
        self.assertFalse(any(c[2].endswith("/place") or c[2] == "/api/booking/calls" for c in GW.api.calls))   # Jon's choice places nothing
        self.say("Chamberí")                                                          # Ana names the area
        self.assertEqual(GW.SENDER.contents[-1][0], "Which one?")
        _, buttons = GW.SENDER.contents[-1]
        self.say("x", payload=buttons[0][1])
        prep = next(c for c in GW.api.calls if c[2] == "/api/booking/calls")
        self.assertEqual(prep[0], TG.ACCOUNT)                                          # under ANA's account
        self.assertEqual(prep[3]["reservation"]["who"]["name"], "Tyler Warren")
        self.assertEqual(prep[3]["reservation"]["how_many"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
