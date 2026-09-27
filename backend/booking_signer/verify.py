"""Verifying what comes back from the booking helper: pairings and device reports (contract §4, §5.4).

STILL UNMOUNTED. These are the server's checks; the page only relays, and a script on the page can alter
anything it relays — so nothing the page says is believed until it passes here.

Rule names match the reference verifier: pairing_invalid · pairing_wrong_origin · report_from_another_device ·
report_of_another_task · report_signature_invalid — plus, for the contract's null-digest case (§5.4),
report_claims_an_act_before_verification.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .canonical import canonical_bytes

#: SPKI DER prefix of every Ed25519 public key; the whole key is always 44 bytes.
_SPKI_ED25519_PREFIX = bytes.fromhex("302a300506032b6570032100")


class VerifyRefused(Exception):
    """A pairing or report did not verify. `rule` is the contract's name for why."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


def _b64(s: Any) -> Optional[bytes]:
    if not isinstance(s, str) or not s:
        return None
    try:
        return base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        return None


def device_id_of(device_public_spki: str) -> str:
    """sha256 hex of the SPKI DER bytes — the id the helper computes the same way."""
    der = _b64(device_public_spki) or b""
    return hashlib.sha256(der).hexdigest()


def _device_key(device_public_spki: str, rule: str) -> Ed25519PublicKey:
    der = _b64(device_public_spki)
    if der is None or len(der) != 44 or not der.startswith(_SPKI_ED25519_PREFIX):
        raise VerifyRefused(rule, "the device key is not an Ed25519 public key (SPKI DER, 44 bytes)")
    return Ed25519PublicKey.from_public_bytes(der[len(_SPKI_ED25519_PREFIX):])


def _verifies(key: Ed25519PublicKey, signature: Any, value: Any) -> bool:
    sig = _b64(signature)
    if sig is None or len(sig) != 64:
        return False
    try:
        key.verify(sig, canonical_bytes(value))
        return True
    except InvalidSignature:
        return False


def pairing_statement(challenge: str, device_id: str, origin: str) -> dict:
    """What the helper signs to pair — built identically on its side."""
    return {"kind": "sasha_pairing", "v": 1, "challenge": challenge, "device_id": device_id, "origin": origin}


@dataclass(frozen=True)
class PairedDevice:
    device_id: str
    device_public_spki: str


def verify_pairing(
    *, challenge: str, expected_origin: str, device_public_spki: str, device_id: str, origin: str, signature: str
) -> PairedDevice:
    """Check a PAIR answer against the challenge THIS SERVER issued. On success, store the returned
    device against the signed-in account."""
    if not isinstance(challenge, str) or len(challenge) < 32:
        raise VerifyRefused("pairing_invalid", "a pairing challenge is at least 32 characters, issued by the server")
    if origin != expected_origin:
        raise VerifyRefused("pairing_wrong_origin", f"the helper paired with {origin!r}, not {expected_origin!r}")
    key = _device_key(device_public_spki, "pairing_invalid")
    if device_id_of(device_public_spki) != device_id:
        raise VerifyRefused("pairing_invalid", "the device id is not the hash of the device key")
    if not _verifies(key, signature, pairing_statement(challenge, device_id, origin)):
        raise VerifyRefused("pairing_invalid", "the pairing signature does not verify against the device key it came with")
    return PairedDevice(device_id=device_id, device_public_spki=device_public_spki)


@dataclass(frozen=True)
class VerifiedReport:
    report: Mapping[str, Any]
    #: False when the helper refused before it could verify the task (task_digest was null): nothing ran,
    #: nothing was sent, and no outcome is recorded — show report["user_words"] and stop.
    task_verified: bool


def verify_device_report(signed: Mapping[str, Any], paired: PairedDevice, expected_task_digest: str) -> VerifiedReport:
    """Accept a relayed REPORT only if the PAIRED device signed it, about THIS task.

    ⚠ It proves which installation spoke, not that its reading was honest.
    """
    report, task_digest, device_id = signed.get("report"), signed.get("task_digest"), signed.get("device_id")
    if device_id != paired.device_id:
        raise VerifyRefused("report_from_another_device", "the report was signed by a device this account did not pair")
    body = {"report": report, "task_digest": task_digest, "device_id": device_id}
    key = _device_key(paired.device_public_spki, "report_signature_invalid")
    if task_digest is None:
        # §5.4 · refused before the task was verified — every report while no key is pinned
        if not _verifies(key, signed.get("device_signature"), body):
            raise VerifyRefused("report_signature_invalid", "the report's signature does not verify against the paired device key")
        if not isinstance(report, Mapping) or report.get("sent") is not False or report.get("tab_opened") is not False:
            raise VerifyRefused("report_claims_an_act_before_verification", "a report with no task digest says a tab opened or something was sent — the helper cannot have acted on a task it never verified")
        return VerifiedReport(report=report, task_verified=False)
    if task_digest != expected_task_digest:
        raise VerifyRefused("report_of_another_task", "the report is about a different task from the one issued")
    if not _verifies(key, signed.get("device_signature"), body):
        raise VerifyRefused("report_signature_invalid", "the report's signature does not verify — it was altered, or it did not come from that device")
    return VerifiedReport(report=report, task_verified=True)
