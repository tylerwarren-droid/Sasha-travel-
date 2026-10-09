"""CR 63 · THE KEEP v1 — S2's vault for a person's numbers and codes, BUILT ONCE. The AgAPI sandbox (agapi_service: keep.put,
keep.list, keep.use, keep.delete) and Sasha (agapi/s2_keep.py) both call this module: the same tiers, the same validation, the same
masks, the same refusals, the same envelope.

  TIERS   free       use freely: preferences, loyalty / frequent-flyer numbers, home address
          yes        used only under a yes on the person's phone that NAMES it: passport, DNI/NIE, Global Entry/PreCheck,
                     visa/residence, insurance policy, health card
          read_back  shown to the person only, never filled anywhere: booking references, door / Wi-Fi codes, eSIM details
  NEVER   card numbers (Apple Pay only) · one-time / 2FA codes · passwords (not in v1)

  THE RULE  the AI never sees a value — only its mask ("Passport ES ••••1234"). Code opens a value at the moment of use (a fill
            into a booking, after the yes for tier `yes`; a show on the person's own screen for `read_back`) and drops it.

  ENVELOPE  per person: one data key (DEK, AES-256) wrapped by a KMS key (Sasha: Google Cloud KMS, booking_signer/vault/kms.py;
            the sandbox: a local stand-in). Each value: AES-256-GCM under the person's DEK, a fresh nonce per write, bound by its
            AAD to the account, the person, the item and its type. Deleting the person's wrapped DEK shreds every value at once.
            A keyed fingerprint (HMAC under a key derived from the DEK) finds a re-save of the same value — never a plain hash,
            which a 9-character passport number would not survive.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import unicodedata
from datetime import date
from typing import Dict, List, Optional, Tuple

FREE, YES, READ_BACK = "free", "yes", "read_back"
MASK = "••••"


class Refused(ValueError):
    """A refusal that NEVER contains the value it refused (it may be logged or returned)."""

    def __init__(self, path: str, rule: str, message: str):
        super().__init__(message)
        self.path, self.rule, self.message = path, rule, message


# field: (min, max, kind) — kind: text | id (A–Z 0–9, spaces/dashes dropped) | iso2 | date | enum:<a|b>
TYPES: Dict[str, dict] = {
    "preference":        {"tier": FREE, "name": "Preference", "fields": {"topic": (1, 40, "text"), "text": (1, 200, "text")}},
    "loyalty":           {"tier": FREE, "name": "Loyalty number", "fields": {"program": (1, 60, "text"), "number": (3, 30, "id")}},
    "home_address":      {"tier": FREE, "name": "Home address", "fields": {"line1": (1, 120, "text"), "line2": (0, 120, "text"),
                                                                          "city": (1, 80, "text"), "postcode": (1, 16, "text"),
                                                                          "country": (2, 2, "iso2")}},
    "passport":          {"tier": YES, "name": "Passport", "fields": {"number": (5, 20, "id"), "country": (2, 2, "iso2"),
                                                                   "expires_on": (10, 10, "date")}},
    "national_id":       {"tier": YES, "name": "National ID", "fields": {"kind": (2, 5, "enum:dni|nie|other"), "number": (5, 20, "id"),
                                                                       "country": (2, 2, "iso2")}},
    "trusted_traveller": {"tier": YES, "name": "Trusted traveller", "fields": {
                              "program": (4, 20, "enum:global_entry|tsa_precheck|nexus|sentri"), "number": (8, 10, "id")}},
    "visa_residence":    {"tier": YES, "name": "Visa / residence", "fields": {"country": (2, 2, "iso2"), "number": (4, 30, "id"),
                                                                            "expires_on": (0, 10, "date")}},
    "insurance_policy":  {"tier": YES, "name": "Insurance policy", "fields": {"insurer": (1, 80, "text"), "number": (3, 40, "id")}},
    "health_card":       {"tier": YES, "name": "Health card", "fields": {"issuer": (1, 80, "text"), "number": (5, 30, "id")}},
    "booking_reference": {"tier": READ_BACK, "name": "Booking reference", "fields": {"provider": (1, 80, "text"), "reference": (3, 30, "id")}},
    "door_code":         {"tier": READ_BACK, "name": "Door code", "fields": {"place": (1, 80, "text"), "code": (2, 20, "text")}},
    "wifi":              {"tier": READ_BACK, "name": "Wi-Fi", "fields": {"network": (1, 64, "text"), "password": (0, 63, "text")}},
    "esim":              {"tier": READ_BACK, "name": "eSIM", "fields": {"provider": (1, 60, "text"), "activation_code": (10, 300, "text"),
                                                                     "iccid": (0, 22, "id")}},
}
# what the mask may show (never the value): a type's public words, and the LAST characters of its secret field
PUBLIC = {"preference": ("topic",), "loyalty": ("program",), "home_address": ("country",), "passport": ("country",),
          "national_id": ("kind", "country"), "trusted_traveller": ("program",), "visa_residence": ("country",),
          "insurance_policy": ("insurer",), "health_card": ("issuer",), "booking_reference": ("provider",), "door_code": ("place",),
          "wifi": ("network",), "esim": ("provider",)}
SECRET = {"loyalty": "number", "passport": "number", "national_id": "number", "trusted_traveller": "number", "visa_residence": "number",
          "insurance_policy": "number", "health_card": "number", "booking_reference": "reference"}
PROGRAM_WORDS = {"global_entry": "Global Entry", "tsa_precheck": "TSA PreCheck", "nexus": "NEXUS", "sentri": "SENTRI",
                 "dni": "DNI", "nie": "NIE", "other": "ID"}

NEVER = {"card": ("never_card", "Card numbers are never kept — Sasha pays with Apple Pay."),
         "payment_card": ("never_card", "Card numbers are never kept — Sasha pays with Apple Pay."),
         "credit_card": ("never_card", "Card numbers are never kept — Sasha pays with Apple Pay."),
         "debit_card": ("never_card", "Card numbers are never kept — Sasha pays with Apple Pay."),
         "otp": ("never_2fa", "One-time and two-factor codes are never kept — they're yours alone, in the moment."),
         "2fa": ("never_2fa", "One-time and two-factor codes are never kept — they're yours alone, in the moment."),
         "verification_code": ("never_2fa", "One-time and two-factor codes are never kept — they're yours alone, in the moment."),
         "password": ("not_in_v1", "Passwords aren't kept in the Keep yet."),
         "login": ("not_in_v1", "Passwords aren't kept in the Keep yet.")}
NO_PAN_CHECK = {("esim", "iccid"), ("esim", "activation_code")}   # an ICCID is Luhn-valid by design; it isn't a card
RAW_ASKS = ("raw", "value", "reveal", "plain", "plaintext", "decrypt", "export", "unmask", "full", "text")
PURPOSES = ("fill", "show")


def tier_of(kind: str) -> str:
    return TYPES[kind]["tier"]


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


_PAN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def looks_like_card(s: str) -> bool:
    """13–19 digits (spaces/dashes allowed), Luhn-valid, on a card network's first digit (2–6)."""
    for m in _PAN.finditer(s or ""):
        d = re.sub(r"\D", "", m.group(0))
        if 13 <= len(d) <= 19 and d[0] in "23456" and _luhn(d):
            return True
    return False


_OTP = re.compile(r"(?i)\b(otp|2fa|two[- ]factor|one[- ]time (?:code|password)|verification code|c[oó]digo de verificaci[oó]n)\b")


def _dni_ok(kind: str, n: str) -> bool:
    letters = "TRWAGMYFPDXBNJZSQVHLCKE"
    if kind == "dni":
        return bool(re.fullmatch(r"\d{8}[A-Z]", n)) and letters[int(n[:8]) % 23] == n[8]
    if kind == "nie":
        return bool(re.fullmatch(r"[XYZ]\d{7}[A-Z]", n)) and letters[int("XYZ".index(n[0]).__str__() + n[1:8]) % 23] == n[8]
    return True


def normalise(kind: str, value: dict) -> Dict[str, str]:
    """The value, validated and normalised → {field: str}. Every refusal names the field, never its content."""
    k = (kind or "").strip().lower()
    if k in NEVER:
        rule, words = NEVER[k]
        raise Refused("/type", rule, words)
    if k not in TYPES:
        raise Refused("/type", "unknown_type", "That isn't something the Keep holds.")
    if not isinstance(value, dict):
        raise Refused("/value", "object", "The value is a set of named fields.")
    spec = TYPES[k]["fields"]
    extra = sorted(set(value) - set(spec))
    if extra:
        raise Refused(f"/value/{extra[0]}", "unknown_field", f"A {TYPES[k]['name'].lower()} has no field '{extra[0]}'.")
    out: Dict[str, str] = {}
    for f, (lo, hi, fk) in spec.items():
        v = value.get(f)
        if v is None or v == "":
            if lo == 0:
                continue
            raise Refused(f"/value/{f}", "required", f"The {f.replace('_', ' ')} is needed.")
        if not isinstance(v, str):
            raise Refused(f"/value/{f}", "string", f"The {f.replace('_', ' ')} is text.")
        v = unicodedata.normalize("NFC", re.sub(r"[\u0000-\u001f\u007f-\u009f​-‍‪-‮⁦-⁩﻿]", "", v)).strip()
        if (k, f) not in NO_PAN_CHECK and looks_like_card(v):
            raise Refused(f"/value/{f}", "never_card", NEVER["card"][1])
        if _OTP.search(v):
            raise Refused(f"/value/{f}", "never_2fa", NEVER["otp"][1])
        if fk == "id":
            v = re.sub(r"[\s-]", "", v).upper()
            if not re.fullmatch(r"[A-Z0-9]+", v):
                raise Refused(f"/value/{f}", "id", f"The {f.replace('_', ' ')} is letters and digits only.")
        elif fk == "iso2":
            v = v.upper()
            if not re.fullmatch(r"[A-Z]{2}", v):
                raise Refused(f"/value/{f}", "iso2", "The country is its two-letter code (ES, GB, US…).")
        elif fk == "date":
            try:
                date.fromisoformat(v)
            except ValueError:
                raise Refused(f"/value/{f}", "date", "A date is YYYY-MM-DD.") from None
        elif fk.startswith("enum:"):
            v = v.lower()
            if v not in fk[5:].split("|"):
                raise Refused(f"/value/{f}", "enum", f"The {f.replace('_', ' ')} is one of: {', '.join(fk[5:].split('|'))}.")
        if not lo <= len(v) <= hi:
            raise Refused(f"/value/{f}", "length", f"The {f.replace('_', ' ')} is {lo}–{hi} characters.")
        out[f] = v
    if k == "national_id" and out.get("country") == "ES" and not _dni_ok(out["kind"], out["number"]):
        raise Refused("/value/number", "checksum", f"That isn't a valid {out['kind'].upper()} (its letter doesn't match).")
    if k == "passport" and out["expires_on"] < date.today().isoformat():
        raise Refused("/value/expires_on", "expired", "That passport has expired — it can't be used to travel.")
    return out


def _tail(s: str) -> str:
    """At most a third of the value, and never more than 4 characters."""
    n = min(4, len(s) // 3)
    return MASK + (s[-n:] if n else "")


def mask(kind: str, v: Dict[str, str]) -> str:
    """What the AI and every log may see. Never the value."""
    name = TYPES[kind]["name"]
    pub = [PROGRAM_WORDS.get(v[f], v[f]) for f in PUBLIC.get(kind, ()) if v.get(f)]
    if kind == "trusted_traveller":
        return f"{pub[0]} {_tail(v['number'])}"
    if kind == "national_id":
        return f"{pub[0]} ({v['country']}) {_tail(v['number'])}"
    if kind == "preference":
        return f"Preference: {v['topic']}"
    if kind in ("door_code", "wifi", "esim", "home_address"):
        return f"{name} · {pub[0]}" if pub else name
    sec = SECRET.get(kind)
    word = {"insurance_policy": "policy", "health_card": "health card", "booking_reference": "booking"}.get(kind)
    if kind == "loyalty" or word:          # "Iberia Plus ••••678", "Sanitas policy ••••911"
        return " ".join([*pub, word or "", _tail(v[sec])]).replace("  ", " ")
    return " ".join([name, *pub, _tail(v[sec]) if sec else ""]).strip()


def use_line(masked: str, purpose: str = "fill") -> str:
    """The line a yes must contain for a tier-`yes` fill — so the approval's hash covers exactly this item."""
    return f"I'll use your saved {masked} for this booking." if purpose == "fill" else f"I'll show your saved {masked} on your phone."


def check_use(kind: str, purpose: str) -> None:
    """keep.use's gate, before anything is opened. "The model asks for the raw value" → refused, whatever it calls it."""
    p = (purpose or "").strip().lower()
    if p in RAW_ASKS or p not in PURPOSES:
        raise Refused("/purpose", "never_raw", "Sasha never sees a saved value. It's filled in by code at the moment of use, "
                      "or shown on your own phone — never handed over.")
    t = tier_of(kind)
    if t == READ_BACK and p == "fill":
        raise Refused("/purpose", "read_back_only", "That one is only ever shown to you — it's never filled in anywhere.")
    if t != READ_BACK and p == "show":
        raise Refused("/purpose", "fill_only", "That one is used for you, not shown — it's filled in where it's needed.")


# ── the envelope ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def new_dek() -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM.generate_key(bit_length=256)


def dek_aad(account: str, person: str) -> bytes:
    return f"keep-dek/v1\x1f{account}\x1f{person}".encode()


def item_aad(account: str, person: str, item_id: str, kind: str) -> bytes:
    return f"keep-item/v1\x1f{account}\x1f{person}\x1f{item_id}\x1f{kind}".encode()


def seal(dek: bytes, aad: bytes, values: Dict[str, str]) -> Tuple[bytes, bytes]:
    """→ (nonce, ciphertext). A fresh nonce on every write."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return nonce, AESGCM(dek).encrypt(nonce, json.dumps(values, sort_keys=True, separators=(",", ":")).encode(), aad)


def open_(dek: bytes, aad: bytes, nonce: bytes, ct: bytes) -> Dict[str, str]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return json.loads(AESGCM(dek).decrypt(nonce, ct, aad))


def fingerprint(dek: bytes, kind: str, values: Dict[str, str]) -> str:
    """Keyed: finds a re-save of the same value without a hash anyone could brute-force (the key never leaves the envelope)."""
    k = hmac.new(dek, b"keep-fingerprint/v1", hashlib.sha256).digest()
    return "hmac:" + hmac.new(k, (kind + "\x1f" + json.dumps(values, sort_keys=True, separators=(",", ":"))).encode(), hashlib.sha256).hexdigest()


def scrub(text: str, values: Dict[str, str], masked: str) -> str:
    """Anything leaving a use (an error, a provider's words) with each opened value replaced by its mask."""
    for v in sorted((v for v in values.values() if isinstance(v, str) and len(v) >= 3), key=len, reverse=True):
        text = text.replace(v, f"[{masked}]")
    return text


class LocalKms:
    """The sandbox's KMS stand-in (and tests'): AES-256-GCM key wrap with a 32-byte key held outside the database. Same interface
    as Sasha's booking_signer.vault.kms backends: async wrap(dek, aad) → (wrapped, version); async unwrap(wrapped, aad, version)."""

    def __init__(self, key: bytes) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        if len(key) != 32:
            raise ValueError("the KMS stand-in needs a 32-byte key")
        self._aead = AESGCM(key)
        self.version = "local-kms:" + hashlib.sha256(key).hexdigest()[:12]

    async def wrap(self, dek: bytes, aad: bytes) -> Tuple[bytes, str]:
        n = os.urandom(12)
        return n + self._aead.encrypt(n, dek, aad), self.version

    async def unwrap(self, wrapped: bytes, aad: bytes, version: str) -> bytes:
        if version != self.version:
            raise ValueError("wrapped by a different key")
        return self._aead.decrypt(wrapped[:12], wrapped[12:], aad)


__all__ = ["TYPES", "FREE", "YES", "READ_BACK", "Refused", "normalise", "mask", "use_line", "check_use", "tier_of", "looks_like_card",
           "new_dek", "dek_aad", "item_aad", "seal", "open_", "fingerprint", "scrub", "LocalKms"]
