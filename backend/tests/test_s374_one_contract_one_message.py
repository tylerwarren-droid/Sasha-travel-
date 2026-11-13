"""Sasha 374 · Sasha's half of CR 186 — ONE provider message id, ONE inbound call, and every AgAPI shape from the ONE generated contract.
NO PATCHES. Spec: agapi cr/186 docs/agapi/cr186-sasha-half.md (mailbox row 1896).

  · kanoe_contract vendored byte-identical (1.80.1; 1.84.0 since Sasha 378 · CR 190) (VENDORED.json: AgAPI's commit + each file's sha256); OP.X / ERR.X, never the strings;
    the ratchet (kanoe_contract.ratchet) at 0 over backend/ (tests excluded).
  · (a) ONE reader of the provider id — inbound_phone.provider_id: MessageSid, else SmsSid — read in the webhook, carried as _message_id.
  · (b) messages.whatsapp_inbound ALWAYS carries message_id.
  · (c) ONE call per message (Sasha 379b · CR 192: carrying what AD may need — never a `space`).
  · a test double may never answer a field AgAPI doesn't publish (agapi/contract_shape: assert_shape, guard on every CALL / _call hook).

    cd backend && python -m unittest tests.test_s374_one_contract_one_message -v
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

import kanoe_contract as KC
from agapi import contract_shape as CS, venue_submit as VS
from booking_signer import guest_whatsapp as GW, inbound_phone as IP
from tests import test_inbound_phone as TIP

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]
GUEST = "+34611374374"


class TheOneContract(unittest.TestCase):
    def test_vendored_byte_identical_at_the_pinned_release(self):
        v = json.loads((BACKEND / "kanoe_contract" / "VENDORED.json").read_text())
        for name, sha in v["files"].items():
            self.assertEqual(hashlib.sha256((BACKEND / "kanoe_contract" / name).read_bytes()).hexdigest(), sha, name)
        agapi = json.loads((BACKEND / "kanoe_contract" / "AGAPI_MANIFEST.json").read_text())
        self.assertEqual((KC.CONTRACT_VERSION, agapi["version"], v["version"]), ("1.93.0", "1.93.0", "1.93.0"))   # Sasha 383 · CR 202 (381: 1.90.0 · CR 192: 1.86.0)

    def test_the_ratchet_finds_no_hand_written_copy(self):
        r = subprocess.run([sys.executable, "-m", "kanoe_contract.ratchet", ".", "--exclude", "tests"], cwd=BACKEND, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        self.assertIn("0 hand-written copies", r.stdout)

    def test_a_double_may_not_answer_an_unpublished_field(self):
        with self.assertRaises(AssertionError):
            CS.assert_shape(KC.OP.USERS_REGISTER, {"ok": True, "result": {"end_user_id": "u", "invented": 1}})
        with self.assertRaises(AssertionError):
            CS.assert_shape(KC.OP.USERS_REGISTER, {"ok": False, "error": {"code": "not_an_agapi_code"}})
        CS.assert_shape(KC.OP.USERS_REGISTER, {"ok": True, "result": {"end_user_id": "u"}})

        async def double(op, body, approval=None, account=None):
            return {"ok": True, "result": {"matched": False, "invented": True}}
        with mock.patch.object(VS, "CALL", double):                                      # ANY double on the hook is shaped
            with self.assertRaises(AssertionError):
                run(VS.whatsapp_inbound(GUEST, "hola", message_id="SM1"))
        self.assertIs(VS.CALL, VS.__dict__["_CONTRACT_REAL"]["CALL"])                    # the real client is never wrapped


class OneInboundMessage(TIP.InboundPhone):
    """Through the REAL webhook (signed, as Twilio sends it): AgAPI's ONE inbound op, as a double that keeps its published shape."""

    def setUp(self):
        super().setUp()
        self.seen = []

        async def agapi(op, body, approval=None, account=None):
            self.seen.append((op, dict(body)))
            if op == KC.OP.MESSAGES_WHATSAPP_INBOUND:
                return {"ok": True, "result": {"matched": True, "kept": True, "ad": "replied" if body.get("space") else None}}
            if op == KC.OP.USERS_REGISTER:
                return {"ok": True, "result": {"end_user_id": "usr_374"}}
            return {"ok": True, "result": {}}
        p = mock.patch.object(VS, "CALL", agapi)
        p.start()
        self.addCleanup(p.stop)
        GW._SEEN_STEPS.clear()

    def deliver(self, form):
        return self.post("sms", {"From": f"whatsapp:{GUEST}", "To": "whatsapp:+447700900000", "Body": "hola", **form})

    def inbound(self):
        return [b for op, b in self.seen if op == KC.OP.MESSAGES_WHATSAPP_INBOUND]

    def test_the_same_delivery_twice_is_one_message_with_one_id(self):
        r1, r2 = self.deliver({"MessageSid": "SM374a"}), self.deliver({"MessageSid": "SM374a"})
        self.assertEqual((r1.status_code, r2.status_code), (200, 200))
        self.assertEqual([b["message_id"] for b in self.inbound()], ["SM374a"])          # AgAPI asked once, with THE id — one answer

    def test_an_smssid_only_delivery_carries_its_id(self):
        self.deliver({"SmsSid": "SM374sms"})
        self.assertEqual([b["message_id"] for b in self.inbound()], ["SM374sms"])

    def test_no_id_is_never_made_up(self):
        self.assertEqual(self.deliver({}).status_code, 400)
        self.assertEqual(self.inbound(), [])

    def test_a_linked_guest_is_one_call_with_what_ad_may_need_and_no_space(self):
        """Sasha 379b · CR 192: ONE call per message, carrying what AD may need (their own Kanoe email, CR 165) — never a `space`."""
        from datetime import datetime, timezone
        from products import diligence as DG
        now = datetime.now(timezone.utc)
        run(GW.STORE.link({"account_id": "00000000-0000-4000-8000-000000000374", "wa_id_sha256": GW.wa_key(GUEST), "number_e164": GUEST,
                           "linked_at": now, "consent_at": now, "consent_wording_version": "v2", "consent_text_sha256": GW.consent()["sha256"]}))
        with mock.patch.object(DG, "_account_email", mock.AsyncMock(return_value="tyler@example.test")):
            r = self.deliver({"MessageSid": "SM374dd", "Body": "any news on Lehman?"})
        self.assertEqual(r.status_code, 200)
        calls = self.inbound()
        self.assertEqual(len(calls), 1)                                                   # ONE call …
        self.assertEqual((calls[0]["message_id"], calls[0]["account_email"]), ("SM374dd", "tyler@example.test"))
        self.assertNotIn("space", calls[0])

    def test_the_one_reader(self):
        self.assertEqual(IP.provider_id({"MessageSid": "SM1", "SmsSid": "SM2"}), "SM1")
        self.assertEqual(IP.provider_id({"SmsSid": "SM2"}), "SM2")
        self.assertEqual(IP.provider_id({}), "")
        for f in ("products/whatsapp.py", "booking_signer/guest_whatsapp.py", "booking_signer/wa_agent.py"):
            self.assertNotIn('p.get("MessageSid")', (BACKEND / f).read_text(), f)        # nobody reads Twilio's field but the ONE reader


for _n in [n for n in vars(TIP.InboundPhone) if n.startswith("test_")]:   # the webhook's harness only — its own tests run in their file
    setattr(OneInboundMessage, _n, None)


if __name__ == "__main__":
    unittest.main()
