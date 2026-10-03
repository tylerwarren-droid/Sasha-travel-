"""Sasha 131 (3) · loyalty numbers from the Keep (the vault): added to a MATCHING booking, named in the read-back so the
yes covers it, opened only at the send, once, logged; written into the form — never shown back, never on a call.

    cd backend && python -m unittest tests.test_loyalty_s131 -v
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from unittest import mock

from booking_signer import loyalty as LY
from booking_signer.vault import crypto as VC, kms as VK
from booking_signer.vault.store import MemoryVaultStore
from tests.test_form_rung import FormRung, reservation

ACCOUNT = "11111111-1111-4111-8111-111111111111"
NUMBER = "KTC-0004821"   # fictional


class Matching(unittest.TestCase):
    def test_a_programme_matches_only_what_it_belongs_to(self):
        self.assertTrue(LY.matches("club.kanoe.ai", "Sasha Test Venue", "restaurant"))   # as the vault saves it: the site's address
        self.assertTrue(LY.matches("Kanoe Test Club", "Sasha Test Venue", "restaurant"))
        self.assertTrue(LY.matches("Kanoe Test Club", "Kanoe Demo Spa", "beauty"))
        self.assertTrue(LY.matches("Marriott Bonvoy", "The Westin Palace Madrid", "hotel"))
        self.assertFalse(LY.matches("Marriott Bonvoy", "Westin Bar", "restaurant"))     # a hotel number never on a restaurant
        self.assertFalse(LY.matches("Iberia Plus", "Botavara", "restaurant"))
        self.assertFalse(LY.matches("Some Club", "Sasha Test Venue", "restaurant"))      # unknown programmes match nothing


class OnTheForm(FormRung):
    def setUp(self):
        super().setUp()
        fd, self.kek = tempfile.mkstemp(); os.write(fd, base64.b64encode(os.urandom(32))); os.close(fd)
        self.venv = mock.patch.dict(os.environ, {"SASHA_VAULT_LOCAL_KEK_FILE": self.kek, "SASHA_VAULT_KMS_KEY": "", "SASHA_VAULT_GCP_SA_JSON": "",
                                                 "ENV": "", "RAILWAY_ENVIRONMENT_NAME": ""})
        self.venv.start()
        VK.reset()
        self.saved_v = VC.STORE
        VC.STORE = MemoryVaultStore()
        self.item = str(uuid.uuid4())
        sealed = asyncio.run(VC.seal(ACCOUNT, self.item, "identifier", json.dumps({"value": NUMBER}).encode()))
        now = datetime.now(timezone.utc)
        asyncio.run(VC.STORE.create({"id": self.item, "account_id": ACCOUNT, "provider": "club.kanoe.ai", "label": "Kanoe Test Club number",
                                     "kind": "identifier", **sealed, "special_category": False, "created_at": now, "updated_at": now}))

    def tearDown(self):
        VC.STORE = self.saved_v
        self.venv.stop()
        VK.reset()
        super().tearDown()

    def test_named_before_the_yes_opened_at_the_send_once_logged_never_shown_back(self):
        found = asyncio.run(LY.find_for(ACCOUNT, "Sasha Test Venue", "restaurant"))
        self.assertEqual(found["id"], self.item)
        v = self.read()
        prep = self.c.post("/api/booking/forms", json={"read_id": v["read_id"], "reservation": reservation(), "loyalty_item_id": self.item}).json()
        text = "\n".join(prep["read_back"]["lines"])
        self.assertIn("I'll use your saved Kanoe Test Club number from your vault.", text)
        self.assertIn(f"· Comentarios: Kanoe Test Club: {LY.TOKEN}", text)
        self.assertNotIn(NUMBER, text)
        self.assertEqual(asyncio.run(VC.STORE.uses_of(ACCOUNT)), [])                     # nothing opened before the yes
        sent = self.c.post(f"/api/booking/forms/{prep['form_id']}/send",
                           json={"read_back_sha256": prep["read_back"]["sha256"], "approval": {"how": "button"}}).json()
        self.assertEqual(sent["status"], "sent")
        self.assertEqual(self.posts[0][1]["comentarios"], f"Kanoe Test Club: {NUMBER}")   # written in
        self.assertNotIn(NUMBER, json.dumps(sent))                                       # never shown back
        uses = asyncio.run(VC.STORE.uses_of(ACCOUNT))
        self.assertEqual([(u["action_kind"], u["status"]) for u in uses], [("loyalty_number", "done")])

    def test_a_revoked_number_is_not_added(self):
        asyncio.run(VC.STORE.revoke(ACCOUNT, self.item, datetime.now(timezone.utc)))
        v = self.read()
        prep = self.c.post("/api/booking/forms", json={"read_id": v["read_id"], "reservation": reservation(), "loyalty_item_id": self.item}).json()
        self.assertNotIn("Kanoe Test Club", "\n".join(prep["read_back"]["lines"]))
