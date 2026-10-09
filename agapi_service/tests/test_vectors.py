"""CR 58 · EU 201's conformance vectors (spec/v1/vectors, vendored from the AD repo), every case, against this runtime.
The idempotency vectors drive the HTTP service (they need its key store); the rest drive agapi_service.rules directly.

    python -m unittest agapi_service.tests.test_vectors -v        (from the repo root)
"""
from __future__ import annotations

import json
import unittest

from agapi_service import rules as R

V = R.SPEC / "vectors"


def load(name):
    return json.loads((V / f"{name}.json").read_text(encoding="utf-8"))


class Canonical(unittest.TestCase):
    """Part 1 §4.1 — 10 accepted (bytes + sha256) and 5 refused, plus the §4.1 refusals the AD runtime still lacks."""

    def test_every_case(self):
        n = 0
        for c in load("canonical")["cases"]:
            with self.subTest(c["id"]):
                if c.get("expect") == "refused":
                    with self.assertRaises(R.Refused):
                        R.canonical(json.loads(c["input_json"]))
                else:
                    value = json.loads(c["input_json"]) if "input_json" in c else c["input"]
                    self.assertEqual(R.canonical(value), c["canonical"])
                    self.assertEqual(R.sha256(value), c["sha256"])
                n += 1
        self.assertEqual(n, 15)

    def test_more_section_4_1_refusals(self):
        for bad in ({"n": float("nan")}, {"n": float("inf")}, {"d": b"x"}, {"s": {1, 2}}, {"k-dash": 1}, {"n": 0.1}):
            with self.subTest(repr(bad)), self.assertRaises(R.Refused):
                R.canonical(bad)


class ExplicitYes(unittest.TestCase):
    def test_every_case(self):
        cases = load("explicit-yes")["cases"]
        for c in cases:
            with self.subTest(f"{c['lang']}: {c['said']}"):
                self.assertEqual(R.explicit_yes(c["said"], c["lang"]), c["explicit_yes"])
        self.assertEqual(len(cases), 38)                                  # v1.0: +12 question/request cases

    def test_apostrophe_errata(self):
        """EU's frozen reference passes "Yes, don't book it" as a yes (the apostrophe becomes a space). Never here."""
        for said in ("Yes, don't book it", "Yes, don’t book it", "yes, I don't want that"):
            self.assertFalse(R.explicit_yes(said, "en"), said)
        for said in ("OK, let's do it", "Perfect, let’s do it"):
            self.assertTrue(R.explicit_yes(said, "en"), said)

    def test_the_lists_come_from_the_frozen_file(self):
        L = json.loads((V / "approval-language.json").read_text(encoding="utf-8"))
        self.assertEqual(L["version"], "1.0")
        self.assertIn("questions_and_requests", L["languages"]["en"])
        self.assertTrue(R.explicit_yes("Vale", "es"))                    # Tyler: "vale" alone is a yes
        self.assertFalse(R.explicit_yes("Yes — what are my cancellation terms?", "en"))


class Approval(unittest.TestCase):
    def test_every_case_in_the_normative_order(self):
        cases = load("approval")["cases"]
        for c in cases:
            with self.subTest(c["id"] + " " + c["description"]):
                self.assertEqual(R.decide(c), (c["expect"]["decision"], c["expect"]["void_reason"]))
        self.assertEqual(len(cases), 17)

    def test_sandbox_simulated_only_in_test_mode(self):
        c = json.loads(json.dumps(load("approval")["cases"][0]))
        c["approval"]["device"] = {"channel": "sandbox_simulated"}
        self.assertEqual(R.decide(c, test_mode=False)[0], "approval_untrusted_origin")
        self.assertEqual(R.decide(c, test_mode=True)[0], "valid")


class Outage(unittest.TestCase):
    def test_every_case(self):
        cases = load("outage")["cases"]
        for c in cases:
            with self.subTest(c["id"]):
                got, e = R.classify(c["sources"]), c["expect"]
                if e["ok"]:
                    self.assertEqual((got[0], got[1], got[2]), ("ok", e["coverage"], e["item_count"]))
                else:
                    self.assertEqual(got, ("error", e["code"]))
        self.assertEqual(len(cases), 7)


class Untrusted(unittest.TestCase):
    def test_every_case(self):
        cases = load("untrusted")["cases"]
        for c in cases:
            with self.subTest(c["id"]):
                e = c["expect"]
                got = R.wrap(c["text"], c.get("source", e["source"]), c.get("retrieved_at", e["retrieved_at"]))
                self.assertEqual(got, e)
        self.assertEqual(len(cases), 8)


class Evidence(unittest.TestCase):
    def test_every_case(self):
        for c in load("evidence")["cases"]:
            with self.subTest(c["id"]):
                got = R.evidence_body_sha256(c["evidence"])
                self.assertEqual(got, c["expect"]["recomputed_body_sha256"])
                self.assertEqual(got == c["evidence"]["body_sha256"], c["expect"]["valid"])


class WebhookSignature(unittest.TestCase):
    def test_every_case(self):
        for c in load("webhook-signature")["cases"]:
            with self.subTest(c["id"]):
                e = c["expect"]
                if "header" in e:
                    self.assertEqual(R.webhook_signature(c["secret"], c["t"], c["raw_body"]), e["header"])
                header = c.get("header") or R.webhook_signature(c["secret"], c["t"], c["raw_body"])
                ok, why = R.webhook_verify(c["secret"], header, c.get("raw_body_received", c["raw_body"]),
                                           received_at=c.get("received_at_unix", c["t"]))
                self.assertEqual(ok, e["valid"], why)
                if "reason" in e:
                    self.assertEqual(why, e["reason"])


class Ids(unittest.TestCase):
    def test_ulid_ids_match_the_common_schema(self):
        import re
        a, b = R.new_id("apv"), R.new_id("apv")
        self.assertRegex(a, r"^apv_[0-9A-HJKMNP-TV-Z]{26}$")
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
