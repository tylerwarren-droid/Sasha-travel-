"""S-62 step 5 · a guest's NAME and MOBILE, stored once, with the consent they were given under (sql/015).

  GET    /api/booking/contact   → {contact: {name, mobile_e164, consent_version, consent_at} | null, consent: {version, text, sha256}}
  PUT    /api/booking/contact   {name, mobile, consent_version, consent_sha256} → saved (create or change)
  DELETE /api/booking/contact   → deleted; the next booking asks again

  · Sasha 328 · the BOOKING EMAIL (where venues and platforms send the confirmation and its cancel link) is on THIS record too — only
    when the person names one ("use tylerwarren@gmail.com for my bookings": set_booking_email, from their own words). With none,
    booking_email() gives their linked Gmail's address (mailbox.address_of — where Sasha reads), else their sign-in address. It is
    never asked for. sql/047 adds the nullable column;
  · the consent sentence is versioned and hashed; a save must name the CURRENT version and its hash, proving the page
    showed these exact words — a stale or altered sentence is refused, nothing saved;
  · a booking already made keeps the details its read-back recorded: that record is what the guest approved;
  · every row is the caller's own account (account_for); nobody reads another's.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .account import account_for
from .store import StorageUnavailable

log = logging.getLogger("booking_signer.contacts")

CONSENT = {"v1": ("Sasha will give your name and mobile to the places you ask her to book — and to nobody else. "
                  "You can change or delete them any time.")}
CURRENT = "v1"


def consent(version: str = CURRENT) -> dict:
    text = CONSENT[version]
    return {"version": version, "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest(), "privacy": "/sasha-privacy"}


def name_case(name: str) -> str:
    """Sasha 118 · a name is kept AS TYPED ("Warren", "McDonald", "de la Vega") — never upper-cased, never title-cased.
    The one exception: a name typed ENTIRELY in capitals (caps lock, an autofill: "TYLER WARREN", saved 2 Oct) is put in
    name case, since a venue would otherwise read "a nombre de WARREN"."""
    if any(ch.isalpha() for ch in name) and name == name.upper():
        return re.sub(r"[^\W\d_]+", lambda m: m[0][:1] + m[0][1:].lower(), name)   # each word: its first letter, then lower
    return name


def e164(raw: Any) -> Optional[str]:
    s = re.sub(r"[\s().-]", "", str(raw or ""))
    if s.startswith("00"):
        s = "+" + s[2:]
    return s if re.fullmatch(r"\+[1-9]\d{7,14}", s) else None


class MemoryContactStore:
    def __init__(self) -> None:
        self.rows: Dict[str, dict] = {}

    async def get(self, account_id: str) -> Optional[dict]:
        return dict(self.rows[account_id]) if account_id in self.rows else None

    async def put(self, row: dict) -> None:
        old = self.rows.get(row["account_id"]) or {}
        # the booking email stays when the name / mobile change (Postgres's upsert leaves that column as it is too)
        self.rows[row["account_id"]] = {**dict(row), **({"booking_email": old["booking_email"]} if old.get("booking_email") else {})}

    async def set_email(self, account_id: str, email: Optional[str]) -> bool:
        if account_id not in self.rows:
            return False
        self.rows[account_id]["booking_email"] = email
        return True

    async def delete(self, account_id: str) -> bool:
        return self.rows.pop(account_id, None) is not None


class PostgresContactStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("015_guest_contacts.sql") from None

    async def get(self, account_id):
        r = await self._run(lambda c: c.fetchrow("select * from guest_contacts where account_id = $1", uuid.UUID(account_id)))
        return {k: (str(v) if k == "account_id" else v) for k, v in dict(r).items()} if r else None

    async def put(self, row):
        await self._run(lambda c: c.execute(
            "insert into guest_contacts (account_id, name, mobile_e164, consent_at, consent_wording_version, consent_text_sha256, updated_at) "
            "values ($1,$2,$3,$4,$5,$6,$4) on conflict (account_id) do update set name = excluded.name, mobile_e164 = excluded.mobile_e164, "
            "consent_at = excluded.consent_at, consent_wording_version = excluded.consent_wording_version, "
            "consent_text_sha256 = excluded.consent_text_sha256, updated_at = excluded.updated_at",
            uuid.UUID(row["account_id"]), row["name"], row["mobile_e164"], row["consent_at"], row["consent_wording_version"],
            row["consent_text_sha256"]))

    async def set_email(self, account_id, email):
        """Sasha 328 · the booking email on the ONE contact row (sql/047). No row yet → False: it is kept with their name and mobile."""
        n = await self._run(lambda c: c.execute("update guest_contacts set booking_email = $2, updated_at = now() where account_id = $1",
                                                uuid.UUID(account_id), email))
        return n.endswith(" 1")

    async def delete(self, account_id):
        n = await self._run(lambda c: c.execute("delete from guest_contacts where account_id = $1", uuid.UUID(account_id)))
        return n.endswith(" 1")


STORE: Any = None          # routes.py sets the Postgres store; tests set a memory one
NOW = None                 # tests set a clock; None = utcnow
router = APIRouter(tags=["booking-contact"])


def _now() -> datetime:
    from datetime import timezone
    return NOW() if NOW else datetime.now(timezone.utc)


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def _view(row: Optional[dict]) -> Optional[dict]:
    return None if not row else {"name": row["name"], "mobile_e164": row["mobile_e164"],
                                 "consent_version": row["consent_wording_version"], "consent_at": row["consent_at"].isoformat(),
                                 **({"booking_email": row["booking_email"]} if row.get("booking_email") else {})}   # Sasha 328


# ── Sasha 328 · THE BOOKING EMAIL: one address for bookings, on this one record ─────────────────────────────────────────────────
EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}")


def email_of(raw: Any) -> Optional[str]:
    s = str(raw or "").strip().strip("<>.,;:").lower()
    return s if len(s) <= 254 and EMAIL.fullmatch(s) else None


async def set_booking_email(account: str, raw: Any) -> Dict[str, Any]:
    """The address the person named for their bookings → their contact row. → {ok, booking_email} | {ok: False, rule, message}."""
    email = email_of(raw)
    if not email:
        return {"ok": False, "rule": "email_invalid", "message": "that isn't an email address — nothing was saved"}
    if STORE is None:
        return {"ok": False, "rule": "store_unreachable", "message": "their details couldn't be saved just now — nothing was saved"}
    try:
        done = await STORE.set_email(account, email)
    except StorageUnavailable as e:
        return {"ok": False, "rule": e.rule, "message": e.detail}
    except Exception as e:   # sql/047 not applied yet (no column): said — never a silent "saved"
        log.warning("[contacts] booking email not saved: %s", type(e).__name__)
        return {"ok": False, "rule": "store_unreachable", "message": "the booking email couldn't be saved just now — nothing was saved"}
    if not done:
        return {"ok": False, "rule": "contact_first", "message": "no booking name and mobile on their account yet — the email is kept with them"}
    return {"ok": True, "booking_email": email}


async def booking_email(account: str) -> Optional[str]:
    """THE address a booking gives the venue (venue.prepare_booking's person.email): the one they named for bookings (this record), else
    their linked Gmail's (where Sasha reads the confirmation and its cancel link — mailbox.address_of), else their sign-in address."""
    try:
        row = await STORE.get(account) if STORE is not None else None
    except Exception as e:
        log.info("[contacts] booking email not read: %s", type(e).__name__)
        row = None
    if (row or {}).get("booking_email"):
        return row["booking_email"]
    from . import mailbox as MB
    addr = await MB.address_of(account)
    if addr:
        return addr
    from . import guest_receipt as GR
    return await GR.address_of(account)


@router.get("/contact")
async def get_contact(request: Request):
    account = account_for(request)
    try:
        return {"contact": _view(await STORE.get(account)), "consent": consent()}
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)


@router.put("/contact")
async def put_contact(request: Request):
    account = account_for(request)
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return _refuse(400, "contact_malformed", "send {name, mobile, consent_version, consent_sha256} as a JSON object")
    name = name_case(" ".join(str(body.get("name") or "").split()))
    if not 1 <= len(name) <= 80:
        return _refuse(422, "name_invalid", "a name is 1–80 characters")
    mobile = e164(body.get("mobile"))
    if mobile is None:
        return _refuse(422, "mobile_invalid", "a mobile is written with its country code, e.g. +44 7700 900123")
    c = consent()
    if body.get("consent_version") != c["version"] or body.get("consent_sha256") != c["sha256"]:
        return _refuse(422, "consent_not_current", "these details are saved only under the consent sentence shown now — reload it; nothing was saved")
    row = {"account_id": account, "name": name, "mobile_e164": mobile, "consent_at": _now(),
           "consent_wording_version": c["version"], "consent_text_sha256": c["sha256"]}
    try:
        await STORE.put(row)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"ok": True, "contact": _view(row)}


@router.delete("/contact")
async def delete_contact(request: Request):
    account = account_for(request)
    try:
        gone = await STORE.delete(account)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"ok": True, "deleted": gone, "say": "Your saved name and mobile are deleted; I'll ask next time you book." if gone
            else "There were no saved details to delete."}


__all__ = ["router", "consent", "e164", "MemoryContactStore", "PostgresContactStore", "CONSENT", "CURRENT", "set_booking_email",
           "booking_email", "email_of"]
