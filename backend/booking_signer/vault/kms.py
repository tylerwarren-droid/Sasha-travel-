"""S-78 §2 · THE KEY THAT WRAPS EVERY ITEM'S KEY — outside the database (V-1: Google Cloud KMS).

One interface, two backends:
  · GoogleKms — production. The KEK never leaves Cloud KMS; this server holds only a service account that may
    Encrypt/Decrypt with that one key (SASHA_VAULT_KMS_KEY, the key's resource name; SASHA_VAULT_GCP_SA_JSON, the
    service account's JSON key). Spoken to over its REST API with a token this module signs itself (RS256, the
    `cryptography` package already pinned) — no new dependency.
  · LocalKek — tests and local development only: a 32-byte key in a file (SASHA_VAULT_LOCAL_KEK_FILE). ⛔ REFUSED in
    production: a KEK on the same host as the database credentials would make "outside the database" true in letter
    only — one host compromise would yield both.

Neither is configured → the vault is closed (VaultClosed), said plainly, and nothing is stored.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class VaultClosed(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def production() -> bool:
    return os.getenv("ENV", "").strip().lower() == "production" or os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip().lower() == "production"


class LocalKek:
    """⛔ Never in production (kek() refuses it). AES-256-GCM with a key read from a file."""

    def __init__(self, path: str) -> None:
        with open(path, "rb") as f:
            raw = f.read().strip()
        key = base64.b64decode(raw) if len(raw) != 32 else raw
        if len(key) != 32:
            raise VaultClosed("vault_local_kek_invalid", "the local KEK file must hold 32 bytes (or their base64)")
        self._aead = AESGCM(key)
        self.version = "local:" + hashlib.sha256(key).hexdigest()[:12]

    async def wrap(self, dek: bytes, aad: bytes) -> Tuple[bytes, str]:
        n = os.urandom(12)
        return n + self._aead.encrypt(n, dek, aad), self.version

    async def unwrap(self, wrapped: bytes, aad: bytes, version: str) -> bytes:
        if version != self.version:
            raise VaultClosed("vault_kek_version_unknown", "this item was wrapped by a different local key")
        return self._aead.decrypt(wrapped[:12], wrapped[12:], aad)


class GoogleKms:
    SCOPE = "https://www.googleapis.com/auth/cloudkms"

    def __init__(self, key_name: str, sa_json: str) -> None:
        try:
            self._sa = json.loads(sa_json)
            assert self._sa["client_email"] and self._sa["private_key"]
        except Exception:
            raise VaultClosed("vault_kms_credentials_invalid", "the KMS service account JSON could not be read") from None
        self.key = key_name.strip()
        self._token: Optional[Tuple[str, float]] = None

    def _assertion(self) -> str:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
        now = int(time.time())
        head = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        uri = self._sa.get("token_uri") or "https://oauth2.googleapis.com/token"
        body = b64(json.dumps({"iss": self._sa["client_email"], "scope": self.SCOPE, "aud": uri, "iat": now, "exp": now + 3600}).encode())
        key = serialization.load_pem_private_key(self._sa["private_key"].encode(), password=None)
        sig = key.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{head}.{body}.{b64(sig)}"

    async def _bearer(self) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        import httpx
        uri = self._sa.get("token_uri") or "https://oauth2.googleapis.com/token"
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as c:
            r = await c.post(uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": self._assertion()})
        if r.status_code != 200:
            raise VaultClosed("vault_kms_unreachable", f"Google refused the KMS sign-in (HTTP {r.status_code})")
        j = r.json()
        self._token = (j["access_token"], time.time() + int(j.get("expires_in", 3600)))
        return self._token[0]

    async def _call(self, verb: str, body: dict) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as c:
            r = await c.post(f"https://cloudkms.googleapis.com/v1/{self.key}:{verb}", json=body,
                             headers={"authorization": f"Bearer {await self._bearer()}"})
        if r.status_code != 200:
            raise VaultClosed("vault_kms_refused", f"Cloud KMS refused to {verb} (HTTP {r.status_code})")
        return r.json()

    async def wrap(self, dek: bytes, aad: bytes) -> Tuple[bytes, str]:
        j = await self._call("encrypt", {"plaintext": base64.b64encode(dek).decode(),
                                         "additionalAuthenticatedData": base64.b64encode(aad).decode()})
        return base64.b64decode(j["ciphertext"]), str(j.get("name") or self.key)

    async def unwrap(self, wrapped: bytes, aad: bytes, version: str) -> bytes:
        j = await self._call("decrypt", {"ciphertext": base64.b64encode(wrapped).decode(),
                                         "additionalAuthenticatedData": base64.b64encode(aad).decode()})
        return base64.b64decode(j["plaintext"])


_KEK = None


def kek():
    """The configured backend. Cloud KMS when its two settings are present; the local file only outside production."""
    global _KEK
    name, sa = os.getenv("SASHA_VAULT_KMS_KEY", "").strip(), os.getenv("SASHA_VAULT_GCP_SA_JSON", "").strip()
    if name and sa:
        if not (isinstance(_KEK, GoogleKms) and _KEK.key == name):
            _KEK = GoogleKms(name, sa)
        return _KEK
    local = os.getenv("SASHA_VAULT_LOCAL_KEK_FILE", "").strip()
    if local:
        if production():
            raise VaultClosed("vault_local_kek_in_production", "a local key file is never used in production; Cloud KMS is required")
        return LocalKek(local)
    raise VaultClosed("vault_not_configured", "the vault's key (Google Cloud KMS) is not set up on this server yet")


def reset() -> None:
    global _KEK
    _KEK = None


def status() -> dict:
    try:
        k = kek()
        return {"open": True, "backend": "google_kms" if isinstance(k, GoogleKms) else "local_dev"}
    except VaultClosed as e:
        return {"open": False, "why": str(e)}


__all__ = ["VaultClosed", "LocalKek", "GoogleKms", "kek", "production", "status", "reset"]
