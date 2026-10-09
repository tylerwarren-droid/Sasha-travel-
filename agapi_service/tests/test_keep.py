"""CR 63 · THE KEEP in the sandbox: keep.put / keep.list (masked) / keep.use (a fill token, never the value) / keep.delete, the
envelope (a key per person, wrapped by the KMS stand-in), the fill at the moment of use under the booking's yes, the show-once
page, Activity rows with proof — and the value NOWHERE else: not in a response, the database, evidence, a message or the logs.

    python -m unittest agapi_service.tests.test_keep -v      (from the repo root)
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unittest
from unittest import mock

from agapi_service import config, providers as PV, rules as R   # (config first: it puts backend/ on the path)
from agapi import keep as K  # noqa: E402
from agapi_service.tests.test_service import Base

PASSPORT = {"number": "PAA123456", "country": "es", "expires_on": "2031-05-01"}
SECRETS = ("PAA123456", "4711#", "tapas2026")


class Keep(Base):
    def setUp(self):
        super().setUp()
        self.got = []

        async def capture(service, kind, values, up):        # what a provider would receive at the moment of use
            self.got.append((service, kind, dict(values)))
            return {"reference": "DOC0001", "service": service + "_documents", "words": "Travel details received (sandbox)."}
        p = mock.patch.object(PV, "send_documents", capture)
        p.start()
        self.addCleanup(p.stop)
        self.logs = []
        h = logging.Handler()
        h.emit = lambda rec: self.logs.append(rec.getMessage())
        root, level = logging.getLogger(), logging.getLogger().level
        root.addHandler(h)
        root.setLevel(logging.DEBUG)                                                             # every line, INFO and DEBUG too
        self.addCleanup(root.setLevel, level)
        self.addCleanup(root.removeHandler, h)

    def put(self, uid, kind="passport", value=None, expect=None):
        r, b = self.call("keep.put", {"end_user": uid, "type": kind, "value": value or PASSPORT}, expect=expect)
        return b["result"] if b["ok"] else b

    def everywhere(self) -> str:
        """Every byte the sandbox wrote: the whole database file, plus the logs."""
        raw = self.store.raw_dump()      # CR 69 · SQLite: the file + WAL (as before); Postgres: every row of every table
        return raw.decode("latin-1") + "\n".join(self.logs)

    def assertNowhere(self, *values):
        blob = self.everywhere()
        for v in values:
            self.assertNotIn(v, blob, "a value reached the database or the logs")
            self.assertNotIn(hashlib.sha256(v.encode()).hexdigest(), blob, "a PLAIN hash of a value was stored")

    def test_the_scan_finds_a_value_when_one_is_there(self):
        """The guard below, seen catching: a canary written to the database and to a log is found (plain and hashed)."""
        self.store.x("insert into accounts (id, name, created_at) values ('canary', 'CANARY-PAA999', 'x')")
        logging.getLogger("agapi").info("CANARY-LOG-777")
        blob = self.everywhere()
        self.assertIn("CANARY-PAA999", blob)
        self.assertIn("CANARY-LOG-777", blob)
        self.store.x("update accounts set name = ? where id = 'canary'", hashlib.sha256(b"PLAINHASHED").hexdigest())
        with self.assertRaises(AssertionError):
            self.assertNowhere("PLAINHASHED")

    # ── put / list ──────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_saved_masked_and_the_value_is_nowhere(self):
        uid = self.user()
        out = self.put(uid)
        self.assertEqual((out["masked"], out["tier"], out["created"]), ("Passport ES ••••456", "yes", True))
        self.assertNotIn("PAA123456", json.dumps(out))
        again = self.put(uid, value={**PASSPORT, "number": "paa 123 456"})                  # the same value → the same item
        self.assertEqual((again["item_id"], again["created"]), (out["item_id"], False))
        self.put(uid, "door_code", {"place": "Calle Mayor flat", "code": "4711#"})
        self.put(uid, "wifi", {"network": "CasaLucio", "password": "tapas2026"})
        listed = self.ok("keep.list", {"end_user": uid})
        self.assertEqual([i["masked"] for i in listed["items"]], ["Passport ES ••••456", "Door code · Calle Mayor flat", "Wi-Fi · CasaLucio"])
        self.assertFalse(listed["values_shown"])
        ev = self.ok("evidence.get", {"evidence_id": out["evidence_id"]})
        self.assertTrue(self.ok("evidence.verify", {"evidence": ev})["valid"])
        self.assertNowhere(*SECRETS)
        self.assertEqual(self.ok("keep.list", {"end_user": self.user("u2", "+15005550007")})["items"], [])   # another person: nothing

    def test_never_stored(self):
        uid = self.user()
        for kind, value, rule in [("card", {"number": "4111111111111111"}, "never_card"),
                                  ("payment_card", {}, "never_card"),
                                  ("otp", {"code": "123456"}, "never_2fa"),
                                  ("password", {"site": "x", "password": "hunter2"}, "not_in_v1"),
                                  ("insurance_policy", {"insurer": "X", "number": "4111 1111 1111 1111"}, "never_card"),
                                  ("preference", {"topic": "note", "text": "my 2FA code is 998877"}, "never_2fa"),
                                  ("passport", {**PASSPORT, "number": "AB12"}, "length"),
                                  ("national_id", {"kind": "dni", "number": "12345678A", "country": "ES"}, "checksum"),
                                  ("passport", {**PASSPORT, "expires_on": "2020-01-01"}, "expired"),
                                  ("spaceship", {}, "unknown_type")]:
            b = self.put(uid, kind, value, expect="invalid_input")
            self.assertEqual(b["error"]["details"]["rule"], rule, kind)
            for v in ("4111111111111111", "4111 1111 1111 1111", "123456", "hunter2", "998877", "12345678A"):
                self.assertNotIn(v, json.dumps(b), "a refusal echoed the value")
        self.assertEqual(self.ok("keep.list", {"end_user": uid})["items"], [])
        self.assertNowhere("4111111111111111", "hunter2", "998877")

    # ── use ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_the_model_asking_for_the_raw_value_is_refused(self):
        uid = self.user()
        item = self.put(uid)["item_id"]
        for purpose in ("raw", "value", "reveal", "plaintext", "export", "unmask", "give me the number"):
            r, b = self.call("keep.use", {"end_user": uid, "item_id": item, "purpose": purpose}, expect="invalid_input")
            self.assertEqual(b["error"]["details"]["rule"], "never_raw", purpose)
            self.assertNotIn("PAA123456", json.dumps(b))
        self.call("keep.use", {"end_user": uid, "item_id": item, "purpose": "fill", "return_value": True}, expect="invalid_input")
        self.call("keep.use", {"end_user": uid, "item_id": item, "purpose": "show"}, expect="invalid_input")   # a passport is used, not shown

    def test_a_passport_is_filled_at_the_moment_of_booking_under_the_yes_that_names_it(self):
        uid = self.user()
        item = self.put(uid)["item_id"]
        h = self.flight_hold(uid)
        early = self.ok("sandbox.simulate_approval", {"read_back_id": h["read_back"]["read_back_id"], "said": "Yes, book it."})["approval_id"]
        use = self.ok("keep.use", {"end_user": uid, "item_id": item, "purpose": "fill", "hold_id": h["hold_id"]})
        self.assertEqual(use["state"], "needs_yes")
        self.assertRegex(use["fill_token"], r"^kf_")
        self.assertEqual(use["line"], "I'll use your saved Passport ES ••••456 for this booking.")
        self.assertIn(use["line"], use["read_back"]["lines"])                                 # the booking's read-back NAMES it
        self.assertNotIn("PAA123456", json.dumps(use))
        r, b = self.call("trip.complete", {"hold_id": h["hold_id"]}, approval=early)          # a yes from BEFORE the passport: void
        self.assertIn(b["error"]["code"], ("approval_void", "approval_same_turn"))         # refused, whichever rule says it first
        self.assertEqual(self.got, [])
        apv = self.ok("sandbox.simulate_approval", {"read_back_id": use["read_back"]["read_back_id"], "said": "Yes, book it."})["approval_id"]
        act = self.ok("trip.complete", {"hold_id": h["hold_id"]}, approval=apv)
        self.assertEqual(self.got, [])                                                         # not yet: a paid flight books on payment
        self.client.post("/" + act["outcome"]["payment_url"].split("://", 1)[1].split("/", 1)[1])
        self.assertEqual(self.got, [("duffel", "passport", {"number": "PAA123456", "country": "ES", "expires_on": "2031-05-01"})])
        items = self.ok("keep.activity", {"end_user": uid})["items"]
        used = [i for i in items if i["kind"] == "keep_use"]
        self.assertEqual(len(used), 1)
        self.assertEqual((used[0]["line"], used[0]["about"]["text"], used[0]["check"]), ("Used from your Keep for a booking",
                                                                                         "Passport ES ••••456", "green"))
        ev = self.ok("evidence.get", {"evidence_id": used[0]["proof"]})
        self.assertEqual((ev["approval"]["approval_id"], ev["outcome"]["reference"]), (apv, "DOC0001"))   # what was approved, the provider's ref
        self.assertTrue(self.ok("evidence.verify", {"evidence": ev})["valid"])
        self.assertTrue(used[0]["verified"])
        self.assertNowhere(*SECRETS)
        # the token was single-use: the next booking needs its own keep.use (and its own yes)
        h2 = self.flight_hold(uid)
        apv2 = self.ok("sandbox.simulate_approval", {"read_back_id": h2["read_back"]["read_back_id"], "said": "Yes, book it."})["approval_id"]
        act2 = self.ok("trip.complete", {"hold_id": h2["hold_id"]}, approval=apv2)
        self.client.post("/" + act2["outcome"]["payment_url"].split("://", 1)[1].split("/", 1)[1])
        self.assertEqual(len(self.got), 1)

    def test_a_loyalty_number_fills_freely_and_a_deleted_item_stops_the_booking(self):
        uid = self.user()
        loyal = self.put(uid, "loyalty", {"program": "Iberia Plus", "number": "IB12345678"})["item_id"]
        h = self.venue_hold(uid)
        use = self.ok("keep.use", {"end_user": uid, "item_id": loyal, "purpose": "fill", "hold_id": h["hold_id"]})
        self.assertEqual(use["state"], "ready")                                               # tier free: no line, no extra yes
        apv = self.ok("sandbox.simulate_approval", {"read_back_id": h["read_back"]["read_back_id"], "said": "Yes, book it."})["approval_id"]
        self.ok("trip.complete", {"hold_id": h["hold_id"]}, approval=apv)
        self.assertEqual(self.got[0][1:], ("loyalty", {"program": "Iberia Plus", "number": "IB12345678"}))
        # a passport bound to a hold, then deleted: the booking does NOT go ahead with a missing document
        pp = self.put(uid)["item_id"]
        h = self.venue_hold(uid)
        use = self.ok("keep.use", {"end_user": uid, "item_id": pp, "purpose": "fill", "hold_id": h["hold_id"]})
        self.ok("keep.delete", {"end_user": uid, "item_id": pp})
        apv = self.ok("sandbox.simulate_approval", {"read_back_id": use["read_back"]["read_back_id"], "said": "Yes, book it."})["approval_id"]
        r, b = self.call("trip.complete", {"hold_id": h["hold_id"]}, approval=apv)
        self.assertFalse(b["ok"])                                                              # the yes named it; it's gone → re-derived, void

    def test_a_door_code_is_only_ever_shown_once_on_their_own_phone(self):
        uid = self.user()
        item = self.put(uid, "door_code", {"place": "Calle Mayor flat", "code": "4711#"})["item_id"]
        h = self.venue_hold(uid)
        r, b = self.call("keep.use", {"end_user": uid, "item_id": item, "purpose": "fill", "hold_id": h["hold_id"]}, expect="invalid_input")
        self.assertEqual(b["error"]["details"]["rule"], "read_back_only")
        out = self.ok("keep.use", {"end_user": uid, "item_id": item, "purpose": "show"})
        self.assertEqual((out["state"], out["channel"]), ("sent_to_phone", "sms"))
        self.assertNotIn("4711#", json.dumps(out))
        msg = [m for m in self.ok("sandbox.messages", {"end_user_id": uid})["messages"] if "/k/" in m["body"]][-1]["body"]
        self.assertNotIn("4711#", msg)
        path = "/" + re.search(r"(http\S+/k/\S+)", msg).group(1).split("://", 1)[1].split("/", 1)[1]
        self.assertNotIn("4711#", self.client.get(path).text)                                 # GET never opens it
        self.assertIn("4711#", self.client.post(path).text)                                   # their own tap: shown once
        self.assertEqual(self.client.post(path).status_code, 404)                             # never twice
        kinds = [i["kind"] for i in self.ok("keep.activity", {"end_user": uid})["items"]]
        self.assertIn("keep_show", kinds)
        self.assertNowhere("4711#")

    # ── delete ──────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_delete_one_then_everything_shreds_the_key(self):
        uid = self.user()
        a, b = self.put(uid)["item_id"], self.put(uid, "wifi", {"network": "CasaLucio", "password": "tapas2026"})["item_id"]
        self.assertEqual(self.ok("keep.delete", {"end_user": uid, "item_id": a})["deleted"], 1)
        self.call("keep.use", {"end_user": uid, "item_id": a, "purpose": "fill", "hold_id": self.venue_hold(uid)["hold_id"]}, expect="not_found")
        out = self.ok("keep.delete", {"end_user": uid})
        self.assertEqual((out["deleted"], out["key_destroyed"]), (1, True))
        self.assertIsNone(self.store.one("select 1 from keep_keys where end_user = ?", uid))
        self.assertIsNone(self.store.one("select 1 from keep_items where end_user = ?", uid))
        self.assertEqual(self.ok("keep.list", {"end_user": uid})["items"], [])
        lines = [i["line"] for i in self.ok("keep.activity", {"end_user": uid})["items"]]
        self.assertEqual(lines.count("Deleted from your Keep"), 2)
        self.assertNowhere(*SECRETS)

    def test_the_envelope(self):
        """A key per person, wrapped by the KMS; the wrong person's key, a moved ciphertext or another KMS can't open it."""
        import asyncio
        from agapi_service import keep_ops as KO
        uid, other = self.user(), self.user("u2", "+15005550007")
        self.put(uid)
        self.put(other)
        rows = self.store.q("select * from keep_items")
        keys = {k["end_user"]: k for k in self.store.q("select * from keep_keys")}
        self.assertEqual(len(keys), 2)
        self.assertNotEqual(bytes(keys[uid]["wrapped_dek"]), bytes(keys[other]["wrapped_dek"]))
        kms = KO.kms()
        dek = asyncio.run(kms.unwrap(bytes(keys[uid]["wrapped_dek"]), K.dek_aad(self.account, uid), keys[uid]["kek_version"]))
        mine = next(r for r in rows if r["end_user"] == uid)
        theirs = next(r for r in rows if r["end_user"] == other)
        self.assertEqual(K.open_(dek, K.item_aad(self.account, uid, mine["id"], "passport"), bytes(mine["nonce"]), bytes(mine["ciphertext"]))["number"],
                         "PAA123456")
        with self.assertRaises(Exception):     # someone else's item under my key
            K.open_(dek, K.item_aad(self.account, other, theirs["id"], "passport"), bytes(theirs["nonce"]), bytes(theirs["ciphertext"]))
        with self.assertRaises(Exception):     # my ciphertext, bound to another item id
            K.open_(dek, K.item_aad(self.account, uid, "kpi_X", "passport"), bytes(mine["nonce"]), bytes(mine["ciphertext"]))
        with self.assertRaises(Exception):     # another KMS key
            asyncio.run(K.LocalKms(b"x" * 32).unwrap(bytes(keys[uid]["wrapped_dek"]), K.dek_aad(self.account, uid), keys[uid]["kek_version"]))
        with mock.patch.dict("os.environ", {"RAILWAY_ENVIRONMENT_NAME": "production", "AGAPI_KEEP_KEK": ""}), \
                mock.patch.object(config, "KEY_PEPPER", "agapi-sandbox-local-pepper"):
            b = self.put(uid, "wifi", {"network": "N", "password": "p4ssword"}, expect="upstream_unreachable")
            self.assertEqual(b["error"]["details"]["service"], "kms")                          # deployed without a KMS key: closed


class Vectors(unittest.TestCase):
    """The frozen Keep vectors (spec/ext/vectors/keep.json) — the same file Sasha's branch tests against."""
    VEC = json.loads((R.SPEC.parent / "ext" / "vectors" / "keep.json").read_text(encoding="utf-8"))

    def test_valid_masks_and_tiers(self):
        for c in self.VEC["valid"]:
            n = K.normalise(c["type"], c["value"])
            self.assertEqual({"normalised": n, "masked": K.mask(c["type"], n), "tier": K.tier_of(c["type"])}, c["expect"], c["id"])
            for f, v in n.items():
                if f in K.SECRET.values() and len(v) >= 6:
                    self.assertNotIn(v, c["expect"]["masked"], c["id"])                          # the mask never holds the number

    def test_refused_never_echo(self):
        for c in self.VEC["refused"]:
            with self.assertRaises(K.Refused) as e:
                K.normalise(c["type"], c["value"])
            self.assertEqual((e.exception.path, e.exception.rule), (c["expect"]["path"], c["expect"]["rule"]), c["id"])
            for v in c["value"].values():
                if len(v) >= 4:
                    self.assertNotIn(v, e.exception.message, c["id"])

    def test_use_including_the_model_asking_for_the_raw_value(self):
        for c in self.VEC["use"]:
            try:
                K.check_use(c["type"], c["purpose"])
                got = None
            except K.Refused as e:
                got = e.rule
            self.assertEqual(got, c["expect"]["refused"], c["id"])
        self.assertTrue(any(c["expect"]["refused"] == "never_raw" for c in self.VEC["use"]))
        for c in self.VEC["use_line"]:
            self.assertEqual(K.use_line(c["masked"], c["purpose"]), c["line"])

    def test_envelope_known_answer(self):
        import asyncio, base64
        for c in self.VEC["envelope"]:
            kms = K.LocalKms(base64.b64decode(c["kms_key_b64"]))
            self.assertEqual(c["dek_aad"].encode(), K.dek_aad(c["account"], c["person"]))
            dek = asyncio.run(kms.unwrap(base64.b64decode(c["wrapped_dek_b64"]), K.dek_aad(c["account"], c["person"]), kms.version))
            aad = K.item_aad(c["account"], c["person"], c["item_id"], c["type"])
            self.assertEqual(K.open_(dek, aad, base64.b64decode(c["nonce_b64"]), base64.b64decode(c["ciphertext_b64"])), c["expect"]["values"])
            self.assertEqual(K.fingerprint(dek, c["type"], c["expect"]["values"]), c["expect"]["fingerprint"])

    def test_counts(self):
        self.assertEqual([len(self.VEC[k]) for k in ("valid", "refused", "use", "use_line", "envelope")], [15, 14, 12, 2, 1])


if __name__ == "__main__":
    unittest.main()
