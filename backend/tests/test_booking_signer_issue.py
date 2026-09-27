"""The signer's issue path and its verification, held to the reference signer case by case.

    cd backend && python -m unittest tests.test_booking_signer_issue -v

tests/booking_signer_issue_cases.json was produced by the reference signer the booking helper was built
against: for each input it records either the rule that refused it, or the exact canonical payload,
digest and signature it signed. Python must give the same answer in every case — including the cases
that break TWO rules at once, which pin the order. Keys are the public RFC 8032 test keys, never real.
"""
import base64
import copy
import json
import pathlib
import unittest
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from booking_signer.canonical import canonical_bytes, canonical_json
from booking_signer.issue import IssueRefused, issue_booking_task
from booking_signer.keys import ENV_VAR, load_signing_key
from booking_signer.verify import PairedDevice, VerifyRefused, device_id_of, pairing_statement, verify_device_report, verify_pairing

HERE = pathlib.Path(__file__).parent
FIX = json.loads((HERE / "booking_signer_issue_cases.json").read_text(encoding="utf-8"))
VEC = json.loads((HERE / "booking_signer_vectors.json").read_text(encoding="utf-8"))
SIGNER_SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
DEVICE_SEED = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
KEY = load_signing_key({ENV_VAR: base64.b64encode(SIGNER_SEED).decode()})
DEVICE = Ed25519PrivateKey.from_private_bytes(DEVICE_SEED)
DEVICE_SPKI = VEC["device_public_spki"]
PAIRED = PairedDevice(device_id=VEC["device_id"], device_public_spki=DEVICE_SPKI)
b64 = lambda b: base64.b64encode(b).decode("ascii")


def run(i, **extra):
    return issue_booking_task(
        task=i["task"], read_back=i["read_back"], approval=i["approval"], mode=i["mode"], device_id=i["device_id"],
        standing=i["standing"], confirmation_email_field=i["confirmation_email_field"],
        now=datetime.fromisoformat(i["now"].replace("Z", "+00:00")), key=KEY, **extra,
    )


def outcome(i, **extra):
    try:
        return ("signed", run(i, **extra))
    except IssueRefused as e:
        return ("refused", e.rule)


class ParityWithTheReferenceSigner(unittest.TestCase):
    def test_every_case_gives_the_reference_answer(self):
        self.assertEqual(len(FIX["cases"]), 32)
        for c in FIX["cases"]:
            with self.subTest(case=c["name"]):
                kind, got = outcome(copy.deepcopy(c["input"]))
                if c["expect"]["signed"]:
                    self.assertEqual(kind, "signed", got)
                    self.assertEqual(canonical_json(got["payload"]), c["expect"]["canonical"])
                    self.assertEqual(got["digest"], c["expect"]["digest"])
                    self.assertEqual(got["signature"], c["expect"]["signature"])
                else:
                    self.assertEqual((kind, got), ("refused", c["expect"]["rule"]))

    def test_the_fixture_covers_every_signer_rule(self):
        rules = {c["expect"].get("rule") for c in FIX["cases"] if not c["expect"]["signed"]}
        self.assertEqual(rules, {
            "live_without_established_refusal", "live_on_a_placeholder_refusal", "live_refusal_basis_not_accepted",
            "live_refusal_without_source", "live_refusal_pattern_invalid", "live_refusal_selector_unsupported",
            "no_paired_device", "email_cannot_receive_confirmation", "no_confirmation_email",
            "originates_on_our_server", "not_https", "url_outside_origin", "url_unparseable", "unknown_step",
            "no_submit_on_the_device", "no_reading_on_the_device", "approval_void", "approval_void_payload",
            "required_field_empty", "task_expired", "task_lifetime_too_long",
        })
        self.assertEqual(sum(1 for c in FIX["cases"] if c["name"].startswith("ORDER")), 4)


class WhatOnlyThisSignerChecks(unittest.TestCase):
    def base(self, name="valid live (Psi's established standing)"):
        return copy.deepcopy(next(c["input"] for c in FIX["cases"] if c["name"] == name))

    def test_a_device_this_account_did_not_pair_is_refused(self):
        self.assertEqual(outcome(self.base(), paired_device_ids=["e" * 64]), ("refused", "no_paired_device"))
        self.assertEqual(outcome(self.base(), paired_device_ids=[VEC["device_id"]])[0], "signed")

    def test_a_voice_yes_with_no_words_is_refused(self):
        i = self.base()
        i["approval"]["how"], i["approval"]["said"] = "voice", "  "
        self.assertEqual(outcome(i), ("refused", "approval_voice_without_words"))

    def test_an_approval_that_is_neither_button_nor_voice_is_refused(self):
        i = self.base()
        i["approval"]["how"] = "nod"
        self.assertEqual(outcome(i), ("refused", "approval_void"))

    def test_an_unknown_mode_is_refused(self):
        i = self.base()
        i["mode"] = "maybe"
        self.assertEqual(outcome(i), ("refused", "task_malformed"))

    def test_a_signed_live_task_verifies_and_its_digest_is_what_a_report_must_quote(self):
        got = run(self.base())
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(KEY.public_spki_base64)[-32:])
        pub.verify(base64.b64decode(got["signature"]), canonical_bytes(got["payload"]))  # raises if wrong
        self.assertEqual(got["payload"]["mode"], "live")
        body = {"report": {"sent": True, "tab_opened": True, "phase": "submitted_and_read"}, "task_digest": got["digest"], "device_id": VEC["device_id"]}
        signed = dict(body, device_signature=b64(DEVICE.sign(canonical_bytes(body))))
        self.assertTrue(verify_device_report(signed, PAIRED, got["digest"]).task_verified)


class Pairing(unittest.TestCase):
    CH = "c" * 40
    ORIGIN = "https://project.kanoe.ai"

    def good(self, **over):
        v = dict(challenge=self.CH, expected_origin=self.ORIGIN, device_public_spki=DEVICE_SPKI, device_id=VEC["device_id"],
                 origin=self.ORIGIN, signature=VEC["pairing_signature"])
        v.update(over)
        return v

    def rule(self, **over):
        try:
            verify_pairing(**self.good(**over))
            return "ok"
        except VerifyRefused as e:
            return e.rule

    def test_the_contract_vector_pairs(self):
        self.assertEqual(verify_pairing(**self.good()).device_id, VEC["device_id"])
        self.assertEqual(device_id_of(DEVICE_SPKI), VEC["device_id"])
        self.assertEqual(canonical_json(pairing_statement(self.CH, VEC["device_id"], self.ORIGIN)), VEC["pairing_canonical"])

    def test_refusals(self):
        other = Ed25519PrivateKey.generate()
        self.assertEqual(self.rule(challenge="short"), "pairing_invalid")
        self.assertEqual(self.rule(origin="https://evil.example"), "pairing_wrong_origin")
        self.assertEqual(self.rule(device_public_spki=b64(b"\x00" * 44)), "pairing_invalid")
        self.assertEqual(self.rule(device_id="f" * 64), "pairing_invalid")
        forged = b64(other.sign(canonical_bytes(pairing_statement(self.CH, VEC["device_id"], self.ORIGIN))))
        self.assertEqual(self.rule(signature=forged), "pairing_invalid")
        self.assertEqual(self.rule(signature="not base64!"), "pairing_invalid")


class DeviceReports(unittest.TestCase):
    def vector(self):
        body = json.loads(VEC["report_body_canonical"])
        return dict(body, device_signature=VEC["report_signature"])

    def rule(self, signed, digest=None):
        try:
            verify_device_report(signed, PAIRED, digest or VEC["digest"])
            return "ok"
        except VerifyRefused as e:
            return e.rule

    def test_the_contract_vector_verifies(self):
        v = verify_device_report(self.vector(), PAIRED, VEC["digest"])
        self.assertEqual((v.report["phase"], v.task_verified), ("captured_not_sent", True))

    def test_a_report_the_page_edited_is_refused(self):
        s = self.vector()
        s["report"] = dict(s["report"], sent=True, phase="submitted_and_read", rule="read_accepted")
        self.assertEqual(self.rule(s), "report_signature_invalid")

    def test_another_device_or_another_task_is_refused(self):
        self.assertEqual(self.rule(dict(self.vector(), device_id="e" * 64)), "report_from_another_device")
        self.assertEqual(self.rule(self.vector(), digest="0" * 64), "report_of_another_task")

    def _null_digest(self, report):
        body = {"report": report, "task_digest": None, "device_id": VEC["device_id"]}
        return dict(body, device_signature=b64(DEVICE.sign(canonical_bytes(body))))

    def test_null_digest_refusal_before_verification_is_accepted_as_nothing_ran(self):
        # every report you will see while no key is pinned (contract §5.4)
        r = {"rule": "no_signing_key_pinned", "phase": "refused", "sent": False, "tab_opened": False}
        v = verify_device_report(self._null_digest(r), PAIRED, VEC["digest"])
        self.assertEqual((v.report["rule"], v.task_verified), ("no_signing_key_pinned", False))

    def test_null_digest_that_claims_an_act_is_refused(self):
        r = {"rule": "read_accepted", "phase": "submitted_and_read", "sent": True, "tab_opened": True}
        self.assertEqual(self.rule(self._null_digest(r)), "report_claims_an_act_before_verification")

    def test_null_digest_with_a_bad_signature_is_refused(self):
        s = self._null_digest({"sent": False, "tab_opened": False})
        s["device_signature"] = VEC["report_signature"]
        self.assertEqual(self.rule(s), "report_signature_invalid")


if __name__ == "__main__":
    unittest.main()
