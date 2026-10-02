"""S-78 steps 2–8 · the vault: sealed per item under a key outside the database, opened only inside an action under that
booking's yes, every use logged, revoke shreds, card numbers refused, health items gated, GDPR delete and export.
Offline (a local test KEK); the Postgres half runs with BOOKING_TEST_DATABASE_URL.

    cd backend && python -m unittest tests.test_vault_s78 -v
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import pathlib
import re
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from booking_signer import contacts as CT, gate, guest_whatsapp as GW, routes
from booking_signer.vault import api as VA, crypto as VC, gdpr as VG, kms as VK
from booking_signer.vault.store import MemoryVaultStore
from tests import test_booking_ladder as TBL   # a module: its own tests are not collected twice

ACCOUNT = "33333333-3333-4333-8333-333333333333"
OTHER = "44444444-4444-4444-8444-444444444444"
ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def token(amr_age_s: int) -> str:
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b({'alg': 'none'})}.{b({'sub': ACCOUNT, 'amr': [{'method': 'otp', 'timestamp': int(time.time()) - amr_age_s}]})}.sig"


class Base(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        fd, self.kek_file = tempfile.mkstemp(); os.write(fd, base64.b64encode(os.urandom(32))); os.close(fd)
        self.env = mock.patch.dict(os.environ, {"SASHA_VAULT_LOCAL_KEK_FILE": self.kek_file, "SASHA_VAULT_KMS_KEY": "",
                                                "SASHA_VAULT_GCP_SA_JSON": "", "ENV": "", "RAILWAY_ENVIRONMENT_NAME": "",
                                                "SASHA_VAULT_HEALTH_DPIA_REF": ""})
        self.env.start()
        VK.reset()
        from booking_signer import proactive as PR
        self.saved = (VC.STORE, GW.STORE, CT.STORE, VG.LOG_DELETION, PR.STORE)
        VC.STORE, GW.STORE, CT.STORE, PR.STORE = MemoryVaultStore(), GW.MemoryGuestStore(), CT.MemoryContactStore(), PR.MemoryProactiveStore()
        self.erasures = []

        async def log_deletion(account, counts, now):
            self.erasures.append(counts)
        VG.LOG_DELETION = log_deletion
        app = FastAPI()
        app.include_router(routes.router)

        async def as_account(request: Request) -> None:
            request.state.account = request.headers.get("x-test-account", ACCOUNT)
        app.dependency_overrides[gate.require_booking_key] = as_account
        self.c = TestClient(app)

    def tearDown(self):
        from booking_signer import proactive as PR
        VC.STORE, GW.STORE, CT.STORE, VG.LOG_DELETION, PR.STORE = self.saved
        self.env.stop()
        VK.reset()
        os.unlink(self.kek_file)

    def save(self, **over):
        body = {"provider": "mercadona.es", "label": "Mercadona login", "kind": "password",
                "fields": {"username": "tyler@example.com", "password": "hunter2!"}, **over}
        return self.c.post("/api/booking/vault", json=body)


class Envelope(Base):
    def test_round_trip_and_every_tamper_fails(self):
        s = run(VC.seal(ACCOUNT, "item-1", "password", b"hunter2"))
        row = {"id": "item-1", "kind": "password", **s}
        self.assertEqual(run(VC._open(ACCOUNT, row)), b"hunter2")
        with self.assertRaises(Exception):
            run(VC._open(OTHER, row))                                          # copied to another account: the AAD fails
        with self.assertRaises(Exception):
            run(VC._open(ACCOUNT, {**row, "id": "item-2"}))                    # or to another item
        with self.assertRaises(Exception):
            run(VC._open(ACCOUNT, {**row, "kind": "identifier"}))              # or relabelled as another kind
        with self.assertRaises(Exception):
            run(VC._open(ACCOUNT, {**row, "ciphertext": bytes([s["ciphertext"][0] ^ 1]) + s["ciphertext"][1:]}))
        s2 = run(VC.seal(ACCOUNT, "item-1", "password", b"hunter2"))
        self.assertNotEqual((s["nonce"], s["wrapped_dek"]), (s2["nonce"], s2["wrapped_dek"]))   # a fresh DEK and nonce per write

    def test_the_local_key_is_refused_in_production_and_nothing_means_closed(self):
        with mock.patch.dict(os.environ, {"RAILWAY_ENVIRONMENT_NAME": "production"}):
            with self.assertRaises(VK.VaultClosed) as e:
                VK.kek()
            self.assertEqual(e.exception.rule, "vault_local_kek_in_production")
        with mock.patch.dict(os.environ, {"SASHA_VAULT_LOCAL_KEK_FILE": ""}):
            self.assertEqual(VK.status(), {"open": False, "why": "the vault's key (Google Cloud KMS) is not set up on this server yet"})
            self.assertEqual(self.save().json()["rule"], "vault_not_configured")     # nothing stored
            self.assertEqual(VC.STORE.items, {})

    def test_google_kms_signs_its_own_token_and_wraps_through_the_api(self):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        g = VK.GoogleKms("projects/p/locations/europe-west1/keyRings/sasha/cryptoKeys/vault",
                         json.dumps({"client_email": "vault@p.iam.gserviceaccount.com", "private_key": pem}))
        head, body, sig = g._assertion().split(".")
        pad = lambda s: s + "=" * (-len(s) % 4)
        key.public_key().verify(base64.urlsafe_b64decode(pad(sig)), f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
        claims = json.loads(base64.urlsafe_b64decode(pad(body)))
        self.assertEqual((claims["scope"], claims["aud"]), (VK.GoogleKms.SCOPE, "https://oauth2.googleapis.com/token"))
        seen = {}

        async def call(verb, b):
            seen[verb] = b
            return ({"ciphertext": base64.b64encode(b"W" + base64.b64decode(b["plaintext"])).decode(), "name": g.key + "/cryptoKeyVersions/3"}
                    if verb == "encrypt" else {"plaintext": base64.b64encode(base64.b64decode(b["ciphertext"])[1:]).decode()})
        g._call = call
        wrapped, version = run(g.wrap(b"k" * 32, b"aad"))
        self.assertEqual(version, g.key + "/cryptoKeyVersions/3")
        self.assertEqual(run(g.unwrap(wrapped, b"aad", version)), b"k" * 32)
        self.assertEqual(base64.b64decode(seen["decrypt"]["additionalAuthenticatedData"]), b"aad")


class Api(Base):
    def test_saved_and_listed_without_ever_returning_the_secret(self):
        r = self.save()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("app password", r.json()["say"])                                       # R7 · the last-resort words
        listing = self.c.get("/api/booking/vault").json()
        self.assertEqual([i["label"] for i in listing["items"]], ["Mercadona login"])
        for text in (r.text, json.dumps(listing)):
            self.assertNotIn("hunter2", text)
            self.assertNotIn("tyler@example.com", text)                                      # nor the username
            self.assertNotIn("ciphertext", text)
        self.assertEqual([k["kind"] for k in listing["kinds"]], ["oauth", "app_password", "passkey", "password", "identifier"])
        self.assertNotIn(b"hunter2", json.dumps({k: str(v) for k, v in next(iter(VC.STORE.items.values())).items()}).encode())

    def test_only_your_own(self):
        item = self.save().json()["item"]["id"]
        self.assertEqual(self.c.get("/api/booking/vault", headers={"x-test-account": OTHER}).json()["items"], [])
        self.assertEqual(self.c.delete(f"/api/booking/vault/{item}", headers={"x-test-account": OTHER}).status_code, 404)

    def test_card_numbers_are_refused_in_every_field(self):
        for over in ({"fields": {"username": "t", "password": "4111 1111 1111 1111"}}, {"label": "card 4111111111111111"},
                     {"kind": "identifier", "fields": {"value": "5555-5555-5555-4444"}}):
            r = self.save(**over)
            self.assertEqual((r.status_code, r.json()["rule"]), (422, "vault_card_refused"), over)
        self.assertEqual(VC.STORE.items, {})

    def test_oauth_is_not_offered_and_a_passkey_stores_nothing_secret(self):
        self.assertEqual(self.save(kind="oauth").json()["rule"], "vault_oauth_unavailable")
        r = self.save(kind="passkey", fields={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(next(iter(VC.STORE.items.values())).get("ciphertext"))

    def test_revoke_shreds_and_says_what_it_cannot_do(self):
        item = self.save().json()["item"]["id"]
        r = self.c.delete(f"/api/booking/vault/{item}")
        self.assertIn("change the password at mercadona.es", r.json()["say"])
        row = VC.STORE.items[item]
        self.assertEqual((row["ciphertext"], row["wrapped_dek"], row["nonce"]), (None, None, None))
        self.assertIsNotNone(row["revoked_at"])
        self.save(label="Two"); self.save(label="Three")
        self.assertEqual(self.c.post("/api/booking/vault/revoke-all").json()["revoked"], 2)

    def test_v4_health_items_wait_for_a_dpia_then_need_art9_consent(self):
        r = self.save(kind="identifier", label="Tarjeta sanitaria", fields={"value": "BBBB123456789012"}, special_category=True)
        self.assertEqual(r.json()["rule"], "vault_health_needs_dpia")
        with mock.patch.dict(os.environ, {"SASHA_VAULT_HEALTH_DPIA_REF": "DPIA-2026-01"}):
            self.assertEqual(self.save(kind="identifier", label="TSI", fields={"value": "BBBB1"}, special_category=True).json()["rule"],
                             "vault_health_consent")
            hc = VA.health_consent()
            r = self.save(kind="identifier", label="TSI", fields={"value": "BBBB1"}, special_category=True,
                          consent_version=hc["version"], consent_sha256=hc["sha256"])
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["item"]["consent_wording_version"], "v1")


class Use(Base):
    def setUp(self):
        super().setUp()
        self.item = self.save().json()["item"]["id"]
        self.lines = ["Book Mercadona delivery for Saturday.", VC.access_line("mercadona.es", "Mercadona login")]
        self.approval = {"read_back_sha256": hashlib.sha256("\n".join(self.lines).encode()).hexdigest(),
                         "at": datetime.now(timezone.utc).isoformat(), "how": "button"}

    def use(self, approval=None, lines=None):
        async def go():
            async with VC.use(ACCOUNT, self.item, approval=approval if approval is not None else self.approval,
                              approved_lines=lines if lines is not None else self.lines, action_kind="form", action_ref="f-1") as s:
                return s.get("password"), s.scrub("typed hunter2! into their page, user tyler@example.com")
        return run(go())

    def test_opened_only_inside_the_action_and_scrubbed_on_the_way_out(self):
        pw, scrubbed = self.use()
        self.assertEqual(pw, "hunter2!")
        self.assertEqual(scrubbed, "typed [vault:Mercadona login] into their page, user [vault:Mercadona login]")
        u = next(iter(VC.STORE.uses.values()))
        self.assertEqual((u["status"], u["approval_sha256"]), ("done", self.approval["read_back_sha256"]))
        self.assertIsNotNone(VC.STORE.items[self.item]["last_used_at"])

    def test_refused_without_that_bookings_yes(self):
        cases = [({}, None, "vault_no_approval"),
                 ({**self.approval, "at": (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()}, None, "vault_approval_stale"),
                 (None, self.lines[:1] + ["I'll sign in to mercadona.es with your saved Other."], "vault_read_back_mismatch")]
        for approval, lines, rule in cases:
            with self.assertRaises(VC.UseRefused) as e:
                self.use(approval, lines)
            self.assertEqual(e.exception.rule, rule)
        plain = self.lines[:1]   # an approval for a plain booking can't unlock a login
        with self.assertRaises(VC.UseRefused) as e:
            self.use({**self.approval, "read_back_sha256": hashlib.sha256(plain[0].encode()).hexdigest()}, plain)
        self.assertEqual(e.exception.rule, "vault_access_not_approved")
        self.assertEqual(VC.STORE.uses, {})

    def test_one_approval_one_use(self):
        self.use()
        with self.assertRaises(VC.UseRefused) as e:
            self.use()
        self.assertEqual(e.exception.rule, "vault_approval_used")

    def test_a_failing_action_is_logged_scrubbed(self):
        async def go():
            async with VC.use(ACCOUNT, self.item, approval=self.approval, approved_lines=self.lines, action_kind="form", action_ref="f-2") as s:
                raise RuntimeError(f"their page rejected {s.get('password')}")
        with self.assertRaises(RuntimeError):
            run(go())
        u = next(iter(VC.STORE.uses.values()))
        self.assertEqual((u["status"], u["outcome_words"]), ("failed", "RuntimeError: their page rejected [vault:Mercadona login]"))

    def test_a_revoked_item_cannot_be_used(self):
        self.c.delete(f"/api/booking/vault/{self.item}")
        with self.assertRaises(VC.UseRefused) as e:
            self.use()
        self.assertEqual(e.exception.rule, "vault_item_unavailable")


class OnlyHere(unittest.TestCase):
    def test_open_is_imported_nowhere_else_and_ciphertext_is_selected_only_in_crypto(self):
        for p in (ROOT / "booking_signer").rglob("*.py"):
            if p.name == "crypto.py" and p.parent.name == "vault":
                continue
            src = p.read_text(encoding="utf-8")
            self.assertNotRegex(src, r"\b_open\b", f"{p} touches vault crypto's private _open")
            for stmt in re.findall(r"select[^;\"']*", src, re.I):
                self.assertNotIn("ciphertext", stmt.lower(), f"{p} selects a ciphertext")
        for p in (ROOT / "app").rglob("*.py"):
            self.assertNotIn("vault_items", p.read_text(encoding="utf-8"), f"{p} reads the vault's table")


class Gdpr(Base):
    def test_erasure_needs_a_typed_confirmation_and_a_fresh_sign_in(self):
        self.save()
        self.assertEqual(self.c.request("DELETE", "/api/booking/account/data", json={}).json()["rule"], "erasure_unconfirmed")
        r = self.c.request("DELETE", "/api/booking/account/data", json={"confirm": "delete everything"})
        self.assertEqual(r.json()["rule"], "erasure_needs_fresh_sign_in")                      # the founder's session isn't a sign-in
        r = self.c.request("DELETE", "/api/booking/account/data", json={"confirm": "delete everything"},
                           headers={"authorization": f"Bearer {token(3600)}"})
        self.assertEqual(r.json()["rule"], "erasure_needs_fresh_sign_in")                      # an hour old: not fresh
        self.assertEqual(len(VC.STORE.items), 1)

    def test_erasure_deletes_the_vault_whatsapp_and_details_and_logs_it(self):
        self.save()
        run(GW.STORE.link({"account_id": ACCOUNT, "wa_id_sha256": "a" * 64, "number_e164": "+447700900123", "linked_at": None,
                           "consent_at": None, "consent_wording_version": "v2", "consent_text_sha256": "b" * 64}))
        run(CT.STORE.put({"account_id": ACCOUNT, "name": "T W", "mobile_e164": "+447700900123"}))
        r = self.c.request("DELETE", "/api/booking/account/data", json={"confirm": "delete everything"},
                           headers={"authorization": f"Bearer {token(60)}"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((VC.STORE.items, GW.STORE.channels, CT.STORE.rows), ({}, {}, {}))
        self.assertEqual(self.erasures, [{"vault_items": 1, "vault_uses": 0, "vault_events": 1, "guest_channels": 1,
                                          "guest_wa_state": 1, "guest_link_codes": 0, "guest_contacts": 1,
                                          "proactive_sent": 0, "proactive_prefs": 0, "guest_places": 0}])

    def test_export_is_metadata_only(self):
        self.save()
        with mock.patch.object(routes, "STORE", None):
            r = self.c.get("/api/booking/account/export")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["vault"]["items"][0]["label"], "Mercadona login")
        self.assertNotIn("hunter2", r.text)
        self.assertNotIn("tyler@example.com", r.text)


@unittest.skipUnless(TBL.PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgresVault(unittest.TestCase):
    """sql/021 as written: sealed or revoked, one use per approval, shred on revoke, erasure."""

    @classmethod
    def setUpClass(cls):
        TBL.OnPostgres.setUpClass.__func__(cls)
        import asyncpg

        async def apply():
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                sql = (ROOT / "booking_signer" / "sql" / "021_vault.sql").read_text()
                await c.execute("drop table if exists vault_uses, vault_events, vault_items")
                await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
            finally:
                await c.close()
        asyncio.run(apply())

    def test_the_store(self):
        import asyncpg
        from booking_signer.store import PostgresStore
        from booking_signer.vault.store import PostgresVaultStore
        asyncio.set_event_loop(asyncio.new_event_loop())
        base = PostgresStore(TBL.PG_URL)
        st = PostgresVaultStore(base)
        acct, now = TBL.DEMO_ACCOUNT_ID, datetime.now(timezone.utc)
        iid = str(uuid.uuid4())

        async def go():
            try:
                with self.assertRaises(asyncpg.CheckViolationError):    # a password row must be sealed
                    await base._run(lambda c: c.execute("insert into vault_items (account_id, provider, label, kind) values ($1,'x.es','x','password')",
                                                        uuid.UUID(acct)))
                await st.create({"id": iid, "account_id": acct, "provider": "mercadona.es", "label": "M", "kind": "password",
                                 "ciphertext": b"c", "nonce": b"n" * 12, "wrapped_dek": b"w", "kek_version": "local:x", "created_at": now})
                self.assertEqual([m["label"] for m in await st.list(acct)], ["M"])
                self.assertNotIn("ciphertext", (await st.list(acct))[0])
                self.assertEqual(bytes((await st.fetch_sealed(VC.SEALED_SQL, iid, acct))["ciphertext"]), b"c")
                u1 = await st.claim_use(acct, iid, "form", "f-1", "a" * 64, now)
                self.assertIsNotNone(u1)
                self.assertIsNone(await st.claim_use(acct, iid, "form", "f-1", "a" * 64, now))   # one approval, one use
                await st.end_use(u1, "done", None, now)
                await st.event(acct, iid, "created", {"kind": "password"}, now)
                self.assertEqual((await st.revoke(acct, iid, now))["id"], iid)
                sealed = await st.fetch_sealed(VC.SEALED_SQL, iid, acct)
                self.assertEqual((sealed["ciphertext"], sealed["wrapped_dek"]), (None, None))      # shredded
                self.assertEqual(await st.delete_account(acct), {"vault_items": 1, "vault_uses": 1, "vault_events": 1})
            finally:
                await base.close()
        asyncio.get_event_loop().run_until_complete(go())


if __name__ == "__main__":
    unittest.main()
