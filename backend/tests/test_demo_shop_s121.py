"""Sasha 121 (F) · Kanoe Demo Market and the vault on stage: the login is opened ONLY inside the one yes, used once,
logged, never shown; revoked, it can't be used. Offline (the shop answers in-process).

    cd backend && python -m unittest tests.test_demo_shop_s121 -v
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import demo_shop as DS, guest_whatsapp as GW
from booking_signer.vault import crypto as VC, kms as VK
from booking_signer.vault.store import MemoryVaultStore
from tests import test_guest_whatsapp_s75 as TG

run = TG.run


class Reorder(TG.Base):
    def setUp(self):
        super().setUp()
        fd, self.kek = tempfile.mkstemp(); os.write(fd, base64.b64encode(os.urandom(32))); os.close(fd)
        self.venv = mock.patch.dict(os.environ, {"SASHA_VAULT_LOCAL_KEK_FILE": self.kek, "SASHA_VAULT_KMS_KEY": "", "SASHA_VAULT_GCP_SA_JSON": "",
                                                 "ENV": "", "RAILWAY_ENVIRONMENT_NAME": "", "SASHA_BOOKING_KEY": "k"})
        self.venv.start()
        VK.reset()
        self.saved_v = (VC.STORE, DS.POST)
        VC.STORE = MemoryVaultStore()
        app = FastAPI(); app.include_router(DS.router)
        shop = TestClient(app)
        self.shop_calls = []

        async def post(url, body):
            path = "/demo-shop/" + url.rsplit("/demo-shop/", 1)[1]
            self.shop_calls.append((path, sorted(body)))
            r = shop.post(path, json=body)
            return r.status_code, r.text
        DS.POST = post
        self.link()
        run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": TG.NOW, "link_tries": []}))

    def tearDown(self):
        VC.STORE, DS.POST = self.saved_v
        self.venv.stop()
        super().tearDown()

    def save_login(self, password=None):
        item = str(uuid.uuid4())
        sealed = run(VC.seal(TG.ACCOUNT, item, "password", json.dumps({"username": DS.USERNAME, "password": password or DS.demo_password()}).encode()))
        now = datetime.now(timezone.utc)
        run(VC.STORE.create({"id": item, "account_id": TG.ACCOUNT, "provider": "Kanoe Demo Market", "label": "Kanoe Demo Market login",
                             "kind": "password", **sealed, "special_category": False, "created_at": now, "updated_at": now}))
        return item

    def test_one_yes_one_use_the_order_placed_and_logged(self):
        self.now = datetime.now(timezone.utc)   # the vault's 15-minute window runs on the real clock
        item = self.save_login()
        self.say("Reorder my usual from Kanoe Demo Market")
        said = "\n".join(self.bodies())
        self.assertIn("• I'll sign in to Kanoe Demo Market with your saved Kanoe Demo Market login.", said)
        self.assertIn("2 × Café de Colombia, 250 g", said)
        self.assertIn("nothing is paid", said)
        self.assertEqual(self.shop_calls, [])                                       # nothing opened, nothing sent before the yes
        body, buttons = GW.SENDER.contents[-1]
        self.assertEqual(body, "Reorder your usual from Kanoe Demo Market?")
        self.say("Yes, order it", payload=buttons[0][1])
        said = "\n".join(self.bodies())
        self.assertRegex(said, r"✅ Ordered from Kanoe Demo Market: order KDM-[0-9A-F]{6}\. I used your saved login once")
        self.assertIn("Pedido confirmado", said)
        self.assertNotIn(DS.demo_password(), json.dumps(GW.SENDER.sent))           # never shown back
        uses = run(VC.STORE.uses_of(TG.ACCOUNT))
        self.assertEqual([(u["action_kind"], u["status"]) for u in uses], [("demo_shop_order", "done")])
        self.assertEqual([p for p, _ in self.shop_calls], ["/demo-shop/login", "/demo-shop/order"])
        # the same yes again: refused — one approval, one use
        self.say("Reorder my usual from Kanoe Demo Market")
        _, b2 = GW.SENDER.contents[-1]
        run(VC.STORE.revoke(TG.ACCOUNT, item, datetime.now(timezone.utc)))           # one-tap revoke
        self.say("yes", payload=b2[0][1])
        self.assertIn("❌ Not ordered", self.bodies()[-1])
        self.assertEqual(len([p for p, _ in self.shop_calls if p.endswith("/order")]), 1)

    def test_no_saved_login_no_action(self):
        self.say("Reorder my usual from Kanoe Demo Market")
        self.assertIn("I don't have a saved login for Kanoe Demo Market", self.bodies()[-1])

    def test_a_wrong_password_is_the_shops_refusal_and_nothing_is_ordered(self):
        self.now = datetime.now(timezone.utc)
        self.save_login(password="wrong")
        self.say("Reorder my usual from Kanoe Demo Market")
        self.say("yes")
        self.assertIn("❌ Not ordered", self.bodies()[-1])
        self.assertNotIn("wrong", self.bodies()[-1])


if __name__ == "__main__":
    import unittest
    unittest.main()
