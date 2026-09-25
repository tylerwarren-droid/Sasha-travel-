"""The signing key: SASHA_BOOKING_TASK_SIGNING_KEY, base64 of a raw 32-byte Ed25519 seed.

The founder sets it on Railway himself. Nothing here prints, logs or returns the seed; errors say what is
wrong with the value, never what the value is.

Two failures are kept apart on purpose:
  * SigningKeyNotConfigured — the variable is absent or empty. The signer cannot work, and says so.
  * InvalidSigningKey       — a value is present and is not base64 of exactly 32 bytes. That is a
                              misconfiguration, and signing with it would mint tasks nothing verifies,
                              so it must stop the signer from starting.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ENV_VAR = "SASHA_BOOKING_TASK_SIGNING_KEY"
SEED_BYTES = 32


class SigningKeyNotConfigured(RuntimeError):
    """The key variable is absent or empty."""


class InvalidSigningKey(RuntimeError):
    """A key value is present and is not base64 of exactly 32 bytes."""


@dataclass(frozen=True)
class LoadedSigningKey:
    """The loaded key. The private half stays in here; only the public half is meant to leave."""

    public_spki_base64: str
    """SPKI DER, standard base64 — the value the helper pins (SIGNING_PUBLIC_KEY_SPKI_BASE64)."""
    fingerprint: str
    """First 16 hex of sha256(SPKI DER). A label for logs and humans, never a check."""
    _private: Ed25519PrivateKey = field(repr=False, compare=False)

    def __repr__(self) -> str:  # never let a repr carry the key object's internals into a log
        return f"LoadedSigningKey(fingerprint={self.fingerprint!r})"


def _decode_seed(raw: str) -> bytes:
    """Strict base64 → exactly 32 bytes. ⚠ Python's default b64decode silently discards characters it
    does not recognise, so a corrupted value would decode to *something*; validate=True plus a
    re-encode round trip makes a wrong value fail here, at startup, rather than sign unverifiable tasks."""
    try:
        seed = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidSigningKey(
            f"{ENV_VAR} is not standard base64 (A–Z a–z 0–9 + / with = padding). "
            "It must be base64 of the raw 32-byte Ed25519 seed — not hex, not a PEM, not URL-safe base64."
        ) from None
    if len(seed) != SEED_BYTES:
        raise InvalidSigningKey(
            f"{ENV_VAR} decodes to {len(seed)} bytes; it must be exactly {SEED_BYTES} "
            "(the raw Ed25519 seed). A PKCS#8 or PEM key is the wrong format."
        )
    if base64.b64encode(seed).decode("ascii") != raw:
        raise InvalidSigningKey(f"{ENV_VAR} is not the canonical base64 of its 32 bytes (padding or trailing bits differ).")
    return seed


def load_signing_key(env: Optional[Mapping[str, str]] = None) -> LoadedSigningKey:
    """Load and check the key. Raises SigningKeyNotConfigured or InvalidSigningKey; never returns None."""
    source = os.environ if env is None else env
    raw = source.get(ENV_VAR)
    if raw is None or raw.strip() == "":
        raise SigningKeyNotConfigured(
            f"{ENV_VAR} is not set. No booking task can be issued without it — "
            "an unsigned task is not a weaker task, it is no authorisation at all."
        )
    if raw != raw.strip():
        raise InvalidSigningKey(f"{ENV_VAR} has leading or trailing whitespace; set the bare base64 value.")
    seed = _decode_seed(raw)
    private = Ed25519PrivateKey.from_private_bytes(seed)
    spki = private.public_key().public_bytes(
        encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return LoadedSigningKey(
        public_spki_base64=base64.b64encode(spki).decode("ascii"),
        fingerprint=hashlib.sha256(spki).hexdigest()[:16],
        _private=private,
    )
