"""CR 63 · THE KEEP on Sasha (agapi/s2_keep.py) on the shared logic (agapi/keep.py — the AgAPI sandbox's own module and frozen
vectors): masks only to the model, a value only on the person's own screen or inside the order, the yes that names it, the
envelope under the vault's KMS, deletion that shreds, Activity rows with proof, the chat guard — and the value nowhere else.

    cd backend && python -m unittest tests.test_keep_s63 -v
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import pathlib
import unittest
import uuid
from unittest import mock

from agapi import keep as K, s2_keep as KEEP, s2_records as REC, v0 as API

VEC = json.loads((pathlib.Path(__file__).parent / "fixtures" / "keep_vectors.json").read_text(encoding="utf-8"))
ACCT, OTHER = "00000000-0000-4000-8000-0000000000f0", "00000000-0000-4000-8000-0000000000b2"
PASSPORT = {"number": "PAA123456", "country": "ES", "expires_on": "2031-05-01"}


def run(c):
    return asyncio.run(c)


class SharedVectors(unittest.TestCase):
    def test_the_sandbox_vectors(self):
        for c in VEC["valid"]:
            n = K.normalise(c["type"], c["value"])
            self.assertEqual({"normalised": n, "masked": K.mask(c["type"], n), "tier": K.tier_of(c["type"])}, c["expect"], c["id"])
        for c in VEC["refused"]:
            with self.assertRaises(K.Refused) as e:
                K.normalise(c["type"], c["value"])
            self.assertEqual((e.exception.path, e.exception.rule), (c["expect"]["path"], c["expect"]["rule"]), c["id"])
        for c in VEC["use"]:
            try:
                K.check_use(c["type"], c["purpose"])
                got = None
            except K.Refused as e:
                got = e.rule
            self.assertEqual(got, c["expect"]["refused"], c["id"])
        for c in VEC["envelope"]:   # the same bytes open here as in the sandbox
            kms = K.LocalKms(base64.b64decode(c["kms_key_b64"]))
            dek = run(kms.unwrap(base64.b64decode(c["wrapped_dek_b64"]), K.dek_aad(c["account"], c["person"]), kms.version))
            self.assertEqual(K.open_(dek, K.item_aad(c["account"], c["person"], c["item_id"], c["type"]), base64.b64decode(c["nonce_b64"]),
                                     base64.b64decode(c["ciphertext_b64"])), c["expect"]["values"])


class Base(unittest.TestCase):
    def setUp(self):
        REC.clear_memory()
        self.store = KEEP.MemoryKeepStore()
        self.kms = K.LocalKms(os.urandom(32))
        for p in (mock.patch.object(KEEP, "STORE", self.store), mock.patch("booking_signer.vault.kms.kek", lambda: self.kms),
                  mock.patch.object(REC, "RUN", None), mock.patch("booking_signer.plan_store._run", lambda: None)):
            p.start()
            self.addCleanup(p.stop)
        self.logs = []
        h = logging.Handler()
        h.emit = lambda rec: self.logs.append(rec.getMessage())
        root, level = logging.getLogger(), logging.getLogger().level
        root.addHandler(h)
        root.setLevel(logging.DEBUG)
        self.addCleanup(root.setLevel, level)
        self.addCleanup(root.removeHandler, h)

    def everywhere(self) -> str:
        """Everything the Keep and the Activity view hold, and every log line."""
        dump = lambda o: json.dumps(o, default=lambda x: base64.b64encode(x).decode() if isinstance(x, (bytes, bytearray)) else str(x))
        return dump(self.store.items) + dump(self.store.fills) + dump(self.store.keys) + dump(REC.ACTS) + "\n".join(self.logs)

    def assertNowhere(self, *values):
        blob = self.everywhere()
        for v in values:
            self.assertNotIn(v, blob)
            self.assertNotIn(hashlib.sha256(v.encode()).hexdigest(), blob)

    def call(self, tool, args, account=ACCT):
        if tool == "keep_use":
            args = {**args, "idempotency_key": f"k-{uuid.uuid4().hex}"}   # the loop fills it in production
        return run(API.call(API.Ctx(account=account), tool, args))


class TheKeep(Base):
    def test_the_scan_finds_a_value_when_one_is_there(self):
        REC.ACTS.append({"canary": "CANARY-PAA999"})
        logging.getLogger("agapi").info("CANARY-LOG")
        self.assertIn("CANARY-PAA999", self.everywhere())
        self.assertIn("CANARY-LOG", self.everywhere())

    def test_saved_masked_and_the_model_sees_only_masks(self):
        out = run(KEEP.put(ACCT, "passport", PASSPORT))
        self.assertEqual((out["masked"], out["tier"], out["created"]), ("Passport ES ••••456", "yes", True))
        self.assertFalse(run(KEEP.put(ACCT, "passport", {**PASSPORT, "number": "paa 123-456"}))["created"])   # the same value
        run(KEEP.put(ACCT, "door_code", {"place": "Calle Mayor flat", "code": "4711#"}))
        r = self.call("keep_list", {})
        self.assertEqual([i["masked"] for i in r["result"]["items"]], ["Passport ES ••••456", "Door code · Calle Mayor flat"])
        self.assertEqual(self.call("keep_list", {}, OTHER)["result"]["items"], [])                    # another account: nothing
        self.assertNotIn("PAA123456", json.dumps(r))
        self.assertEqual([a["kind"] for a in REC.ACTS], ["keep_save", "keep_save"])                  # in Activity
        self.assertNowhere("PAA123456", "4711#")
        # the key per account is wrapped by the KMS; a different KMS key can't open it
        k = self.store.keys[ACCT]
        with self.assertRaises(Exception):
            run(K.LocalKms(os.urandom(32)).unwrap(k["wrapped_dek"], K.dek_aad(ACCT, ACCT), k["kek_version"]))

    def test_never_stored_and_never_echoed(self):
        for kind, value, rule in [("card", {"number": "4111111111111111"}, "never_card"), ("otp", {}, "never_2fa"),
                                  ("password", {"password": "hunter2"}, "not_in_v1"),
                                  ("insurance_policy", {"insurer": "X", "number": "4111 1111 1111 1111"}, "never_card")]:
            with self.assertRaises(KEEP.KeepError) as e:
                run(KEEP.put(ACCT, kind, value))
            self.assertEqual(e.exception.rule, rule)
            self.assertNotIn("4111", e.exception.message)
        self.assertEqual(self.store.items, {})
        self.assertNowhere("4111111111111111", "hunter2")

    def test_the_model_asking_for_the_raw_value_is_refused(self):
        item = run(KEEP.put(ACCT, "passport", PASSPORT))["item_id"]
        for purpose in ("raw", "value", "reveal", "plaintext", "export", "read me the number"):
            r = self.call("keep_use", {"item_id": item, "purpose": purpose})
            self.assertEqual(r["error"]["code"], "never_raw", purpose)
            self.assertNotIn("PAA123456", json.dumps(r))
        self.assertEqual(self.call("keep_use", {"item_id": item, "purpose": "show"})["error"]["code"], "fill_only")
        self.assertEqual(self.call("keep_use", {"item_id": str(uuid.uuid4()), "purpose": "fill"})["error"]["code"], "not_found")
        t = {x["name"]: x for x in KEEP.tools()}
        self.assertEqual(set(API.schema_for_model(t["keep_use"])["input_schema"]["properties"]), {"item_id", "purpose"})   # no key, no value

    def test_a_passport_fills_the_order_only_under_the_yes_that_heard_it(self):
        item = run(KEEP.put(ACCT, "passport", PASSPORT))["item_id"]
        r = self.call("keep_use", {"item_id": item, "purpose": "fill"})["result"]
        self.assertEqual((r["state"], r["line"]), ("needs_yes", "I'll use your saved Passport ES ••••456 for this booking."))
        heard = ["I'll book Iberia IB3166 Madrid → London on Thu 12 Nov for Ana.", *run(KEEP.lines(ACCT)), "Total €120."]
        self.assertIn(r["line"], heard)                                                               # hold_booking reads it out
        self.assertEqual(run(KEEP.approve(ACCT, ["a read-back WITHOUT the passport line"], "Yes, book it.", "cs_1")), 0)
        self.assertEqual(run(KEEP.approve(ACCT, heard, "Yes, book it.", "cs_2")), 1)

        async def order(sid):   # a round trip: two orders, both carry the passport, one Activity row
            async with KEEP.fill(ACCT, sid) as kept:
                docs = kept.duffel()
                kept.result("UHQ9B1" if docs else None, bool(docs))
                assert kept.duffel() == docs
                kept.result("ZX81QA" if docs else None, bool(docs))
                return docs
        self.assertEqual(run(order("cs_other")), [])                                                  # another payment: nothing
        self.assertEqual(run(order("cs_2")), [{"type": "passport", "unique_identifier": "PAA123456", "issuing_country_code": "ES",
                                               "expires_on": "2031-05-01"}])
        self.assertEqual(run(order("cs_2")), [])                                                      # used once
        used = [a for a in REC.ACTS if a["kind"] == "keep_use"]
        self.assertEqual(len(used), 1)
        self.assertEqual((used[0]["about"], used[0]["proof"]["reference"], used[0]["proof"]["said"]), ("Passport ES ••••456", "UHQ9B1, ZX81QA", "Yes, book it."))
        self.assertTrue(REC.verified(used[0]))
        self.assertNowhere("PAA123456")

    def test_a_loyalty_number_needs_no_line_and_a_door_code_is_only_shown(self):
        loyal = run(KEEP.put(ACCT, "loyalty", {"program": "Iberia Plus", "number": "IB12345678"}))["item_id"]
        self.assertEqual(self.call("keep_use", {"item_id": loyal, "purpose": "fill"})["result"]["state"], "ready")
        self.assertEqual(run(KEEP.lines(ACCT)), [])
        door = run(KEEP.put(ACCT, "door_code", {"place": "Calle Mayor flat", "code": "4711#"}))["item_id"]
        self.assertEqual(self.call("keep_use", {"item_id": door, "purpose": "fill"})["error"]["code"], "read_back_only")
        r = self.call("keep_use", {"item_id": door, "purpose": "show"})["result"]
        self.assertEqual(r["state"], "on_their_screen")
        self.assertNotIn("4711#", json.dumps(r))
        self.assertEqual(run(KEEP.show(ACCT, door)), {"place": "Calle Mayor flat", "code": "4711#"})   # their own screen only
        with self.assertRaises(KEEP.KeepError):
            run(KEEP.show(OTHER, door))
        self.assertIn("keep_show", [a["kind"] for a in REC.ACTS])

    def test_delete_one_then_everything_shreds_the_key(self):
        a = run(KEEP.put(ACCT, "passport", PASSPORT))["item_id"]
        run(KEEP.put(ACCT, "wifi", {"network": "CasaLucio", "password": "tapas2026"}))
        self.assertEqual(run(KEEP.delete(ACCT, a)), {"deleted": 1, "key_destroyed": False})
        self.assertEqual(run(KEEP.delete(ACCT)), {"deleted": 1, "key_destroyed": True})
        self.assertEqual((self.store.items, self.store.keys), ({}, {}))
        self.assertEqual([x["kind"] for x in REC.ACTS].count("keep_delete"), 2)
        self.assertNowhere("PAA123456", "tapas2026")

    def test_closed_without_its_kms_or_its_tables(self):
        from booking_signer.vault import kms

        def closed():
            raise kms.VaultClosed("vault_not_configured", "not set up")
        with mock.patch("booking_signer.vault.kms.kek", closed):
            with self.assertRaises(KEEP.KeepError) as e:
                run(KEEP.put(ACCT, "passport", PASSPORT))
            self.assertEqual(e.exception.rule, "keep_closed")
        with mock.patch.object(KEEP, "STORE", None):
            self.assertEqual(self.call("keep_list", {})["error"]["code"], "keep_closed")             # no database: closed, said
        self.assertEqual(self.store.items, {})

    def test_the_chat_guard(self):
        for said in ("my passport is PAA123456", "DNI 12345678Z", "it's 12345678Z", "NIE: X1234567L", "my global entry is 98765432",
                     "pasaporte PAA 123456"):
            self.assertTrue(KEEP.guard(said), said)
        for said in ("dinner for 4 at 21:00 on the 12th", "flight IB3166 to London", "I need a passport photo place", "12345678A is wrong",
                     "book the hotel for 2 nights", "my passport expires in 2031"):
            self.assertFalse(KEEP.guard(said), said)


class ChatGuard(unittest.TestCase):
    def test_the_next_turn_never_carries_a_secret_or_a_document_number(self):
        self.assertEqual(KEEP.chat_guard("my passport is PAA123456"), KEEP.GUARD_REPLY)
        self.assertIn("card numbers", KEEP.chat_guard("pay with 4111 1111 1111 1111"))
        self.assertIn("passwords", KEEP.chat_guard("my password is hunter2!"))
        self.assertIsNone(KEEP.chat_guard("dinner for 2 on Saturday at 21:00"))
        h = KEEP.clean_history([{"role": "user", "content": "DNI 12345678Z"}, {"role": "assistant", "content": "ok"},
                                {"role": "user", "content": "book it"}])
        self.assertNotIn("12345678Z", json.dumps(h))
        self.assertEqual([m["content"] for m in h][1:], ["ok", "book it"])

    def test_a_new_binding_voids_a_reused_read_back(self):
        with mock.patch.object(KEEP, "bind", mock.AsyncMock(return_value={"state": "needs_yes", "line": "x", "masked": "m"})):
            API._HELD[ACCT] = {"sha": "s"}
            run(API.call(API.Ctx(account=ACCT), "keep_use", {"item_id": "i", "purpose": "fill", "idempotency_key": "k-bind-1"}))
            self.assertNotIn(ACCT, API._HELD)


class Routes(Base):
    """The /keep screen's API, as the signed-in person (chat_account patched)."""

    def setUp(self):
        super().setUp()
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(KEEP.router, prefix="/api/agent")
        self.c = TestClient(app)
        for p in (mock.patch("app.services.chat_account.chat_account", mock.AsyncMock(return_value=ACCT)),
                  mock.patch("app.services.chat_account.signed_in", lambda a: bool(a))):
            p.start()
            self.addCleanup(p.stop)

    def test_save_list_show_delete(self):
        r = self.c.post("/api/agent/keep", json={"type": "passport", "value": PASSPORT})
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("PAA123456", r.text)
        self.assertEqual(self.c.post("/api/agent/keep", json={"type": "card", "value": {"number": "4111111111111111"}}).json()["rule"], "never_card")
        door = self.c.post("/api/agent/keep", json={"type": "door_code", "value": {"place": "Flat", "code": "4711#"}}).json()["item_id"]
        listed = self.c.get("/api/agent/keep").json()
        self.assertEqual([i["masked"] for i in listed["items"]], ["Passport ES ••••456", "Door code · Flat"])
        self.assertNotIn("PAA123456", json.dumps(listed))
        self.assertEqual(self.c.post(f"/api/agent/keep/{door}/show").json()["values"]["code"], "4711#")
        pp = listed["items"][0]["item_id"]
        self.assertEqual(self.c.post(f"/api/agent/keep/{pp}/show").json()["rule"], "fill_only")       # a passport is never shown
        self.assertEqual(self.c.delete("/api/agent/keep").status_code, 400)                          # everything: only with DELETE typed
        self.assertEqual(self.c.delete("/api/agent/keep?confirm=DELETE").json()["key_destroyed"], True)
        self.assertEqual(self.c.get("/api/agent/keep").json()["items"], [])
        self.assertNowhere("PAA123456", "4711#")

    def test_signed_out_is_refused(self):
        with mock.patch("app.services.chat_account.signed_in", lambda a: False):
            self.assertEqual(self.c.get("/api/agent/keep").status_code, 403)
            self.assertEqual(self.c.post("/api/agent/keep", json={"type": "passport", "value": PASSPORT}).status_code, 403)


PG_URL = os.getenv("BOOKING_TEST_DATABASE_URL", "")


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(unittest.TestCase):
    """036 + 037 applied to a scratch Postgres: the same flow on the real store; the tables hold ciphertext, never the value."""

    @classmethod
    def setUpClass(cls):
        import asyncpg
        cls.loop = asyncio.new_event_loop()
        cls.conn = cls.loop.run_until_complete(asyncpg.connect(PG_URL))
        root = pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql"

        async def setup(c):
            for role in ("anon", "authenticated"):
                await c.execute(f"do $$ begin create role {role}; exception when duplicate_object then null; end $$")
            await c.execute("drop table if exists public.keep_fills, public.keep_items, public.keep_keys, public.s2_acts, "
                            "public.s2_wa_contacts, public.s2_wa_replies")
            for f in ("036_s2_activity_whatsapp.sql", "037_keep.sql", "037_keep.sql"):   # 037 twice: idempotent
                sql = (root / f).read_text()
                await c.execute(sql[sql.index("begin;"):sql.index("-- check")])
        cls.loop.run_until_complete(setup(cls.conn))

    @classmethod
    def tearDownClass(cls):
        async def down(c):
            await c.execute("drop table if exists public.keep_fills, public.keep_items, public.keep_keys, public.s2_acts, "
                            "public.s2_wa_contacts, public.s2_wa_replies")
            await c.close()
        cls.loop.run_until_complete(down(cls.conn))
        cls.loop.close()

    def test_the_whole_flow_on_postgres(self):
        c = self.conn

        async def runner(fn):
            return await fn(c)
        kms = K.LocalKms(os.urandom(32))
        with mock.patch.object(KEEP, "STORE", KEEP.PostgresKeepStore(runner)), mock.patch.object(REC, "RUN", runner), \
                mock.patch("booking_signer.vault.kms.kek", lambda: kms):
            go = self.loop.run_until_complete
            item = go(KEEP.put(ACCT, "passport", PASSPORT))
            self.assertFalse(go(KEEP.put(ACCT, "passport", PASSPORT))["created"])
            r = go(KEEP.bind(ACCT, item["item_id"], "fill"))
            heard = ["I'll book it.", r["line"], "Total €120."]
            self.assertEqual(go(KEEP.lines(ACCT)), [r["line"]])
            self.assertEqual(go(KEEP.approve(ACCT, heard, "Yes, book it.", "cs_pg")), 1)

            async def order():
                async with KEEP.fill(ACCT, "cs_pg") as kept:
                    docs = kept.duffel()
                    kept.result("PGREF1", True)
                    return docs
            self.assertEqual(go(order())[0]["unique_identifier"], "PAA123456")
            rows = go(c.fetch("select row_to_json(t)::text as j from (select * from keep_items) t union all "
                              "select row_to_json(t)::text from (select * from keep_fills) t union all "
                              "select row_to_json(t)::text from (select * from keep_keys) t union all "
                              "select row_to_json(t)::text from (select * from s2_acts) t"))
            blob = "\n".join(r["j"] for r in rows)
            self.assertIn("Passport ES ••••456", blob)                                                # the mask is there…
            self.assertNotIn("PAA123456", blob)                                                       # …the value is not,
            self.assertNotIn(hashlib.sha256(b"PAA123456").hexdigest(), blob)                          # nor its plain hash
            self.assertIn('"state":"used"', blob)
            self.assertEqual(go(KEEP.delete(ACCT)), {"deleted": 1, "key_destroyed": True})
            self.assertEqual(go(c.fetchval("select count(*) from keep_keys")) + go(c.fetchval("select count(*) from keep_items")), 0)


_ADDED: list = []   # Sasha 224 · once wired, v0 registers them itself: only what THIS module added is taken away again


def setUpModule():
    for t in KEEP.tools():
        if t["name"] not in API.BY_NAME:
            API.TOOLS.append(t)
            API.BY_NAME[t["name"]] = t
            _ADDED.append(t["name"])


def tearDownModule():
    for name in _ADDED:
        t = API.BY_NAME.pop(name, None)
        if t in API.TOOLS:
            API.TOOLS.remove(t)


if __name__ == "__main__":
    unittest.main()
