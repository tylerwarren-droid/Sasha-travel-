"""The booking signer's foundation, proven against the booking helper's own test vectors.

    cd backend && python -m unittest tests.test_booking_signer -v

The vectors (tests/booking_signer_vectors.json) were produced AND verified by the booking helper's own
JavaScript code: its verifier accepted the task, its report check accepted the report, its pairing check
accepted the pairing. So byte-for-byte agreement here is agreement with the thing that will check us.
The keys are the public RFC 8032 test keys — never real.
"""
import base64
import json
import pathlib
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from booking_signer.canonical import CanonicalError, canonical_bytes, canonical_json, digest
from booking_signer.keys import ENV_VAR, InvalidSigningKey, SigningKeyNotConfigured, load_signing_key

V = json.loads((pathlib.Path(__file__).parent / "booking_signer_vectors.json").read_text(encoding="utf-8"))
RFC_TEST_1 = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
RFC_TEST_2 = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
b64 = lambda b: base64.b64encode(b).decode("ascii")


class CanonicalJsonTests(unittest.TestCase):
    def test_small_worked_example_matches_the_helper(self):
        value = {"b": [3, 1, {"d": None, "c": True}], "a": 'é "q" \n\u0001/', "Z": 0}
        self.assertEqual(canonical_json(value), V["small_canonical"])

    def test_full_task_payload_is_byte_for_byte_the_helpers(self):
        got = canonical_bytes(V["payload"])
        self.assertEqual(got, V["canonical"].encode("utf-8"))
        self.assertEqual(len(got), V["canonical_bytes"])
        self.assertEqual(digest(V["payload"]), V["digest"])

    def test_report_and_pairing_bodies_round_trip_unchanged(self):
        for key in ("report_body_canonical", "pairing_canonical"):
            self.assertEqual(canonical_json(json.loads(V[key])), V[key], key)

    def test_payload_hash_and_read_back_hash(self):
        import hashlib
        fields = V["payload"]["task"]["fields"]
        lines = "\n".join(sorted(f"{f['selector']}={f['value']}" for f in fields))
        self.assertEqual(lines, V["filled_values_lines"])
        self.assertEqual(hashlib.sha256(lines.encode("utf-8")).hexdigest(), V["filled_values_sha256"])
        rb = "\n".join(V["payload"]["read_back"]["lines"])
        self.assertEqual(hashlib.sha256(rb.encode("utf-8")).hexdigest(), V["read_back_sha256"])

    def test_string_escapes_match_javascript(self):
        # expected values are JavaScript's own output for the same inputs
        self.assertEqual(canonical_json("a\u0000b\u0008c\u000bd\u001fe\u007ff"), '"a\\u0000b\\bc\\u000bd\\u001fe\u007ff"')
        self.assertEqual(canonical_json("x\ud800y"), '"x\\ud800y"')
        self.assertEqual(canonical_json("x\udc00y"), '"x\\udc00y"')
        self.assertEqual(canonical_json("x\U0001F600y"), '"x\U0001F600y"')
        self.assertEqual(canonical_json("  "), '"  "')
        self.assertEqual(canonical_json('/\\"'), '"/\\\\\\""')

    def test_keys_sort_in_utf16_order_not_code_point_order(self):
        value = {"￿": 1, "\U0001F600": 2, "a": 3, "Z": 4, "é": 5}
        self.assertEqual(canonical_json(value), '{"Z":4,"a":3,"é":5,"\U0001F600":2,"￿":1}')

    def test_integers_and_whole_floats(self):
        self.assertEqual(canonical_json([0, -1, 9007199254740991, 2.0]), "[0,-1,9007199254740991,2]")

    def test_refuses_what_it_cannot_reproduce(self):
        for bad in (1.5, float("nan"), float("inf"), 2**53, {1: "x"}, {"a": {1, 2}}, b"bytes", object()):
            with self.assertRaises(CanonicalError, msg=repr(bad)):
                canonical_json(bad)


class SigningKeyTests(unittest.TestCase):
    def test_rfc_test_1_seed_gives_the_vector_public_key(self):
        k = load_signing_key({ENV_VAR: b64(RFC_TEST_1)})
        self.assertEqual(k.public_spki_base64, V["signer_public_spki"])
        self.assertEqual(len(k.fingerprint), 16)

    def test_rfc_test_2_seed_gives_the_vector_device_key(self):
        self.assertEqual(load_signing_key({ENV_VAR: b64(RFC_TEST_2)}).public_spki_base64, V["device_public_spki"])

    def test_ed25519_over_the_canonical_bytes_reproduces_the_vector_signatures(self):
        # ⚠ uses the library directly: the foundation deliberately has no signing function yet
        sig = Ed25519PrivateKey.from_private_bytes(RFC_TEST_1).sign(canonical_bytes(V["payload"]))
        self.assertEqual(b64(sig), V["signature"])
        dev = Ed25519PrivateKey.from_private_bytes(RFC_TEST_2)
        self.assertEqual(b64(dev.sign(V["report_body_canonical"].encode("utf-8"))), V["report_signature"])
        self.assertEqual(b64(dev.sign(V["pairing_canonical"].encode("utf-8"))), V["pairing_signature"])
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(V["signer_public_spki"])[-32:])
        pub.verify(base64.b64decode(V["signature"]), V["canonical"].encode("utf-8"))  # raises if wrong

    def test_absent_or_empty_is_not_configured(self):
        for env in ({}, {ENV_VAR: ""}, {ENV_VAR: "   "}):
            with self.assertRaises(SigningKeyNotConfigured):
                load_signing_key(env)

    def test_refuses_anything_but_base64_of_exactly_32_bytes(self):
        bad = {
            "31 bytes": b64(RFC_TEST_1[:31]),
            "33 bytes": b64(RFC_TEST_1 + b"\x00"),
            "hex, not base64": RFC_TEST_1.hex(),
            "url-safe alphabet": b64(bytes([0xFB] * 32)).replace("+", "-").replace("/", "_"),
            "a PEM": "-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEIJ1hsZ3v/Vpguoq=\n-----END PRIVATE KEY-----",
            "whitespace inside": b64(RFC_TEST_1)[:10] + " " + b64(RFC_TEST_1)[10:],
            "leading space": " " + b64(RFC_TEST_1),
            "missing padding": b64(RFC_TEST_1).rstrip("="),
        }
        for label, value in bad.items():
            with self.assertRaises(InvalidSigningKey, msg=label) as ctx:
                load_signing_key({ENV_VAR: value})
            self.assertNotIn(value.strip(), str(ctx.exception), f"{label}: the error must never echo the value")

    def test_the_loaded_key_never_shows_its_private_half(self):
        k = load_signing_key({ENV_VAR: b64(RFC_TEST_1)})
        self.assertNotIn(b64(RFC_TEST_1), repr(k))
        self.assertNotIn(RFC_TEST_1.hex(), repr(k))


if __name__ == "__main__":
    unittest.main()
