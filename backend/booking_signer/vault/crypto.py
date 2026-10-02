"""S-78 §2, §5 · SEAL AND USE — the only module that ever touches a secret's ciphertext.

    secret ─AES-256-GCM(DEK, nonce, aad = account‖item‖kind)─► ciphertext            (DB)
    DEK (random, per item, per write) ─KMS wrap(KEK, same aad)─► wrapped_dek          (DB)
    KEK never leaves Cloud KMS                                                         (kms.py)

  · `use()` is the ONLY decrypt path, and it opens a secret only inside the executing action, under THAT booking's yes:
    an approval no older than 15 minutes, whose read-back hash matches the lines approved, and whose lines NAME this
    access ("I'll sign in to {provider} with your saved {label}."). One approval, one use (vault_uses, claimed first).
  · `_open` is private: tests/test_vault_s78.py fails if any other module imports it, and if a ciphertext is SELECTed
    anywhere but here.
  · Everything an action returns passes through the use's scrub(), which replaces each value it opened with
    [vault:label] — exact, because the action knows what it opened.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import kms

APPROVAL_WINDOW = timedelta(minutes=15)   # = call_routes.APPROVAL_WINDOW
NOW = lambda: datetime.now(timezone.utc)
STORE: Any = None                          # vault.store — routes.py sets the Postgres one; tests a memory one

#: the one read of a sealed item — here and nowhere else (a test holds that)
SEALED_SQL = ("select id, account_id, provider, label, kind, ciphertext, nonce, wrapped_dek, kek_version, revoked_at "
              "from vault_items where id = $1 and account_id = $2")


class UseRefused(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def _aad(account: str, item_id: str, kind: str) -> bytes:
    return f"{account}\x1f{item_id}\x1f{kind}".encode()


async def seal(account: str, item_id: str, kind: str, plaintext: bytes) -> Dict[str, Any]:
    """A fresh DEK and nonce on EVERY write (a re-save never reuses either)."""
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    aad = _aad(account, item_id, kind)
    ct = AESGCM(dek).encrypt(nonce, plaintext, aad)
    wrapped, version = await kms.kek().wrap(dek, aad)
    return {"ciphertext": ct, "nonce": nonce, "wrapped_dek": wrapped, "kek_version": version}


async def _open(account: str, row: dict) -> bytes:
    aad = _aad(account, str(row["id"]), row["kind"])
    dek = await kms.kek().unwrap(bytes(row["wrapped_dek"]), aad, row["kek_version"])
    return AESGCM(dek).decrypt(bytes(row["nonce"]), bytes(row["ciphertext"]), aad)


def access_line(provider: str, label: str) -> str:
    """The read-back line that names the access — the approval must contain it, so its hash covers it."""
    return f"I'll sign in to {provider} with your saved {label}."


class Secret:
    """What an action holds for the length of one use. Its values are dropped on exit."""

    def __init__(self, label: str, values: Dict[str, str]) -> None:
        self.label = label
        self._values = dict(values)

    def get(self, key: str) -> Optional[str]:
        return self._values.get(key)

    def scrub(self, text: Any) -> Any:
        """§4.3 · every value this use opened, replaced by [vault:label] — before anything is logged, stored or shown."""
        if not isinstance(text, str):
            return text
        for v in sorted((v for v in self._values.values() if isinstance(v, str) and len(v) >= 3), key=len, reverse=True):
            text = text.replace(v, f"[vault:{self.label}]")
        return text

    def _drop(self) -> None:
        for k in list(self._values):
            self._values[k] = None
        self._values.clear()


@asynccontextmanager
async def use(account: str, item_id: str, *, approval: Optional[dict], approved_lines: List[str], action_kind: str,
              action_ref: str):
    """async with use(account, item, approval=row["approval"], approved_lines=row["read_back_lines"], …) as secret:"""
    now = NOW()
    row = await STORE.fetch_sealed(SEALED_SQL, item_id, account)
    if not row or row.get("revoked_at") or row.get("ciphertext") is None:
        raise UseRefused("vault_item_unavailable", "that saved access is not in your vault (or was revoked)")
    if row["kind"] == "passkey":
        raise UseRefused("vault_passkey", "a passkey stays on your device — you sign in yourself")
    if not isinstance(approval, dict) or not approval.get("read_back_sha256") or not approval.get("at"):
        raise UseRefused("vault_no_approval", "a saved access is used only under that booking's yes")
    try:
        at = datetime.fromisoformat(str(approval["at"]))
    except ValueError:
        raise UseRefused("vault_no_approval", "the approval has no time") from None
    if now - at > APPROVAL_WINDOW:
        raise UseRefused("vault_approval_stale", "that yes is more than 15 minutes old")
    if hashlib.sha256("\n".join(approved_lines).encode()).hexdigest() != approval["read_back_sha256"]:
        raise UseRefused("vault_read_back_mismatch", "the yes was to different words")
    if access_line(row["provider"], row["label"]) not in approved_lines:
        raise UseRefused("vault_access_not_approved", "the read-back you said yes to did not name this saved access")
    use_id = await STORE.claim_use(account, item_id, action_kind, action_ref, approval["read_back_sha256"], now)
    if use_id is None:
        raise UseRefused("vault_approval_used", "that yes has already been used once")
    raw = bytearray(await _open(account, row))
    secret = Secret(row["label"], json.loads(bytes(raw)))
    for i in range(len(raw)):
        raw[i] = 0
    status, words = "failed", None
    try:
        yield secret
        status = "done"
    except Exception as e:
        words = secret.scrub(f"{type(e).__name__}: {e}")
        raise
    finally:
        secret._drop()
        await STORE.end_use(use_id, status, words, NOW())


__all__ = ["seal", "use", "access_line", "Secret", "UseRefused", "SEALED_SQL", "APPROVAL_WINDOW"]
