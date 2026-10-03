"""Sasha 126 · Kanoe Demo Spa (ours) and two bookings from ONE sentence. The membership login is opened only inside the
one yes, used once, logged; revoked, it can't be used. The restaurant and the spa: two card sets, one combined
read-back, one yes, two bookings. Offline (the spa answers in-process).

    cd backend && python -m unittest tests.test_demo_spa_s126 -v
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import demo_spa as DSP, guest_receipt as GR, guest_whatsapp as GW
from booking_signer.vault import crypto as VC, kms as VK
from booking_signer.vault.store import MemoryVaultStore
from tests import test_guest_whatsapp_s75 as TG

run = TG.run


class Spa(TG.Base):
    def setUp(self):
        super().setUp()
        fd, self.kek = tempfile.mkstemp(); os.write(fd, base64.b64encode(os.urandom(32))); os.close(fd)
        self.venv = mock.patch.dict(os.environ, {"SASHA_VAULT_LOCAL_KEK_FILE": self.kek, "SASHA_VAULT_KMS_KEY": "", "SASHA_VAULT_GCP_SA_JSON": "",
                                                 "ENV": "", "RAILWAY_ENVIRONMENT_NAME": "", "SASHA_BOOKING_KEY": "k"})
        self.venv.start()
        VK.reset()
        self.saved_v = (VC.STORE, DSP.POST, DSP.RECORD, GR.send_for_route)
        VC.STORE = MemoryVaultStore()
        app = FastAPI(); app.include_router(DSP.router)
        spa = TestClient(app)
        self.spa_calls, self.recorded, self.receipts = [], [], []

        async def post(url, body):
            path = "/demo-spa/" + url.rsplit("/demo-spa/", 1)[1]
            self.spa_calls.append(path)
            r = spa.post(path, json=body)
            return r.status_code, r.text

        async def record(account, at, ref):
            self.recorded.append((at, ref))
            return "ti-1"

        async def receipt(account, venue, route, status, details):
            self.receipts.append((venue, details.get("venue_reference")))
            return "sent"
        DSP.POST, DSP.RECORD, GR.send_for_route = post, record, receipt
        self.link()
        run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": TG.NOW, "link_tries": []}))
        self.now = datetime.now(timezone.utc)   # the vault's 15-minute window runs on the real clock

    def tearDown(self):
        VC.STORE, DSP.POST, DSP.RECORD, GR.send_for_route = self.saved_v
        self.venv.stop()
        super().tearDown()

    def save_login(self, password=None):
        item = str(uuid.uuid4())
        sealed = run(VC.seal(TG.ACCOUNT, item, "password", json.dumps({"username": DSP.USERNAME, "password": password or DSP.demo_password()}).encode()))
        now = datetime.now(timezone.utc)
        run(VC.STORE.create({"id": item, "account_id": TG.ACCOUNT, "provider": "Kanoe Demo Spa", "label": "Kanoe Demo Spa membership",
                             "kind": "password", **sealed, "special_category": False, "created_at": now, "updated_at": now}))
        return item

    def test_membership_one_yes_one_use_logged_then_revoked(self):
        item = self.save_login()
        self.say("Use my spa membership to book a massage on Tuesday at 18:00")
        said = "\n".join(self.bodies())
        self.assertIn("• I'll sign in to Kanoe Demo Spa with your saved Kanoe Demo Spa membership.", said)
        self.assertIn("nothing is paid", said)
        self.assertEqual(self.spa_calls, [])                                       # nothing opened before the yes
        body, buttons = GW.SENDER.contents[-1]
        self.assertTrue(body.startswith("Book a 60-minute relaxing massage at Kanoe Demo Spa, Tuesday"), body)
        self.say("Yes, book it", payload=buttons[0][1])
        said = "\n".join(self.bodies())
        self.assertRegex(said, r"✅ Booked: a 60-minute relaxing massage at Kanoe Demo Spa, Tuesday \d+ \w+ at 18:00\. Ref KDS-[0-9A-F]{6}\. "
                               r"I used your saved membership once")
        self.assertIn("Reserva confirmada", said)
        self.assertNotIn(DSP.demo_password(), json.dumps(GW.SENDER.sent))
        self.assertEqual([(u["action_kind"], u["status"]) for u in run(VC.STORE.uses_of(TG.ACCOUNT))], [("demo_spa_booking", "done")])
        self.assertEqual(self.spa_calls, ["/demo-spa/login", "/demo-spa/book"])
        self.assertEqual(len(self.recorded), 1)                                    # on the guest's list → their calendar
        self.assertEqual(self.receipts[0][0], "Kanoe Demo Spa")
        # revoked in one tap: the next yes can't open it
        self.say("Use my spa membership to book a massage on Tuesday at 18:00")
        _, b2 = GW.SENDER.contents[-1]
        run(VC.STORE.revoke(TG.ACCOUNT, item, datetime.now(timezone.utc)))
        self.say("yes", payload=b2[0][1])
        self.assertIn("❌ Not booked", self.bodies()[-1])
        self.assertEqual(self.spa_calls.count("/demo-spa/book"), 1)

    def test_asks_day_and_time_then_no_books_nothing(self):
        self.save_login()
        self.say("book a massage with my spa membership")
        self.assertEqual(self.bodies()[-1], "Which day and time for the massage?")
        self.say("Tuesday at 18:00")
        self.say("No")
        self.assertIn("nothing was booked", self.bodies()[-1])
        self.assertEqual(self.spa_calls, [])

    def test_no_saved_login(self):
        self.say("Use my spa membership on Tuesday at 18:00")
        self.assertIn("I don't have a saved Kanoe Demo Spa login", self.bodies()[-1])

    def test_portal_refuses_a_wrong_password(self):
        self.save_login(password="wrong")
        self.say("Use my spa membership to book a massage on Tuesday at 18:00")
        self.say("yes")
        self.assertIn("❌ Not booked", self.bodies()[-1])
        self.assertNotIn("wrong", self.bodies()[-1])
        self.assertEqual(self.recorded, [])

    def test_combo_two_card_sets_one_yes_two_bookings(self):
        from booking_signer import ladder_routes as LR, ladder_store as LS
        self.save_login()
        api, saved = GW.api, LR.LADDER_STORE
        LR.LADDER_STORE = LS.MemoryLadderStore()
        LR.LADDER_STORE.account_emails = {TG.ACCOUNT: "guest@example.com"}
        sends = []

        async def fake(account, method, path, body=None, timeout=90.0):
            if path == "/api/booking/venues/read":
                return 200, {"read_id": "r-1", "venue": "Sasha Test Venue", "country": "ES", "listing": None, "say": "x",
                             "rungs": [{"rung": "form", "available": True, "fact_index": 1, "value": "https://x/form"}]}
            if path == "/api/booking/forms":
                return 200, {"form_id": "form-1234", "read_back": {"lines": ["I'll send the booking form:", "· Name: Tyler Warren"],
                                                                     "sha256": "f" * 64}}
            if path == "/api/booking/forms/form-1234/send":
                sends.append(body)
                return 200, {"status": "sent", "reading": {"result": "confirmed"}, "booking_reference": "TV-FE41E1"}
            return await api(account, method, path, body, timeout)
        GW.api = fake
        try:
            self.say("Book a restaurant and a spa in Madrid when I arrive next week")
            self.assertIn("what time for each", self.bodies()[-1])
            self.say("Tuesday — spa at 18:00, dinner at 21:00")
            _, cards = GW.SENDER.contents[-1]
            self.say("x", payload=cards[1][1])                              # the restaurant
            self.assertIn("Then the spa", "\n".join(self.bodies()))
            _, spa_cards = GW.SENDER.contents[-1]
            self.assertEqual(spa_cards[-1][0], "Kanoe Demo Spa")
            self.assertEqual(sends, [])
            self.say("x", payload=spa_cards[0][1])                          # a real spa: not together, says so
            self.assertIn("I can book only Kanoe Demo Spa today", self.bodies()[-1])
            self.say("x", payload=spa_cards[-1][1])
            said = "\n".join(self.bodies())
            self.assertIn("both, on one yes:", said)
            body, yes = GW.SENDER.contents[-1]
            self.assertTrue(body.startswith("Book both?"), body)
            self.assertEqual((sends, self.spa_calls), ([], []))           # nothing sent, nothing opened before the ONE yes
            self.say("Yes, book both", payload=yes[0][1])
            said = "\n".join(self.bodies())
            self.assertIn("✅ 1) Booked: Botavara Chamberí, Tuesday 6 October at 21:00, 2 people.", said)
            self.assertIn("Their reference: TV-FE41E1", said)
            self.assertRegex(said, r"✅ 2\) Booked: a 60-minute relaxing massage at Kanoe Demo Spa, Tuesday \d+ \w+ at 18:00\. Ref KDS-")
            self.assertEqual(len(sends), 1)
            self.assertEqual(sends[0]["read_back_sha256"], "f" * 64)
            self.assertEqual(self.spa_calls, ["/demo-spa/login", "/demo-spa/book"])
            self.assertEqual(self.recorded[0][0][11:16], "18:00")
            self.assertIsNone(run(GW.STORE.get_state(GW.wa_key(TG.GUEST))).get("combo"))
        finally:
            GW.api, LR.LADDER_STORE = api, saved

    def test_combo_times_each_next_to_its_own_kind(self):
        self.assertEqual(GW.combo_times("Tuesday — spa at 18:00, dinner at 21:00"), {"spa": "18:00", "dinner": "21:00"})
        self.assertEqual(GW.combo_times("dinner at 9pm and a massage at 6pm"), {"spa": "18:00", "dinner": "21:00"})
        self.assertTrue(GW.COMBO.search("book a restaurant and a spa in Madrid when I arrive next week"))
        self.assertFalse(GW.COMBO.search("dinner for 2 in Chamberí on Saturday at 9"))
