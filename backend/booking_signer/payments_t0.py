"""S-81 tier 0 · "PAY THE €20 DEPOSIT TO X?" — the guest pays the venue DIRECTLY; no money touches Kanoe.

When a venue asks for a deposit on the call, Sasha agreed to nothing (calls.DEPOSIT_RULE) and the reading is unclear
(_MONEY). Here: a payment request is created from the venue's own words, the guest is asked ONE sentence — the amount,
the payee, what it's for, that they pay the venue themselves — and one yes (hash-bound, like every other). On the yes,
Sasha asks the venue, in writing, to send the guest their OWN payment link (a text to the venue's published mobile, else
an email). `payer = guest_direct`. A card number is never asked for, held, spoken or stored (S-78 §8, rule 2).
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .store import StorageUnavailable

log = logging.getLogger("booking_signer.payments")
NOW = lambda: datetime.now(timezone.utc)
_AMOUNT = re.compile(r"(?:€|eur(?:os?)?\s*)\s*(\d{1,4})(?:[.,](\d{2}))?|(\d{1,4})(?:[.,](\d{2}))?\s*(?:€|euros?\b|eur\b)", re.I)
_DEPOSIT = re.compile(r"dep[óo]sito|se[ñn]al|deposit|pre-?pay|prepayment|anticipo|tarjeta|card|garant[ií]a|sinal|acompte|arrhes|caparra|anzahlung", re.I)


def amount_of(words: str) -> Optional[int]:
    """Minor units (cents) of the first euro amount the venue said — or None (then the read-back says so)."""
    m = _AMOUNT.search(words or "")
    if not m:
        return None
    whole, cents = (m[1], m[2]) if m[1] else (m[3], m[4])
    return int(whole) * 100 + int(cents or 0)


def deposit_asked(reading) -> Optional[str]:
    """The venue's own words asking for a deposit or card on this call — or None."""
    for r in getattr(reading, "raised", None) or []:
        if r.get("what") in ("deposit", "card") or _DEPOSIT.search(r.get("quote") or ""):
            return r.get("quote")
    m = _DEPOSIT.search(getattr(reading, "venue_words", "") or "")
    if m:
        words = reading.venue_words
        return " / ".join(t for t in words.split(" / ") if _DEPOSIT.search(t)) or words[:300]
    return None


def euros(minor: Optional[int]) -> str:
    if minor is None:
        return "a deposit"
    return f"€{minor // 100}" + (f".{minor % 100:02d}" if minor % 100 else "")


def read_back(venue: str, minor: Optional[int], quote: str, when: str) -> List[str]:
    """One amount, one yes: the amount, the payee, what it's for, how it's paid — and that Sasha never sees a card."""
    amt = euros(minor) + (" deposit" if minor is not None else "")
    return [f"{venue} needs {amt} for {when}. Their words: \"{quote}\"",
            f"I'll ask {venue} to send you their own payment link, by text or email. You pay them directly — I never see "
            f"your card, and nothing is charged by Sasha or Kanoe.",
            f"Ask {venue} for the payment link?"]


def sha(lines: List[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


# ── the store: Memory for tests, Postgres (sql/024) for real ────────────────────────────────────────────────────────

class MemoryPaymentStore:
    def __init__(self) -> None:
        self.rows: Dict[str, dict] = {}

    async def create(self, row):
        if any(r["trip_item_id"] == row["trip_item_id"] and r["purpose"] == row["purpose"] and r["status"] not in ("cancelled", "failed")
               for r in self.rows.values()):
            return None
        self.rows[row["id"]] = dict(row)
        return row["id"]

    async def get(self, account, pid):
        r = self.rows.get(pid)
        return dict(r) if r and r["account_id"] == account else None

    async def approve(self, account, pid, approval, now):
        r = self.rows.get(pid)
        if not r or r["account_id"] != account or r["status"] != "awaiting_approval":
            return False
        r.update(approval=approval, status="approved", updated_at=now)
        return True

    async def set(self, pid, **kw):
        self.rows[pid].update(kw)


class PostgresPaymentStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("024_payments.sql") from None

    async def create(self, row):
        r = await self._run(lambda c: c.fetchval(
            "insert into payment_requests (id, account_id, trip_item_id, payee, purpose, amount_minor, currency, venue_terms_quote, "
            "read_back_lines, read_back_sha256, tier) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'guest_direct') on conflict do nothing returning id",
            uuid.UUID(row["id"]), uuid.UUID(row["account_id"]), uuid.UUID(row["trip_item_id"]), row["payee"], row["purpose"],
            row.get("amount_minor"), row.get("currency", "EUR"), row.get("venue_terms_quote"), row["read_back_lines"], row["read_back_sha256"]))
        return str(r) if r else None

    async def get(self, account, pid):
        r = await self._run(lambda c: c.fetchrow("select * from payment_requests where id = $1 and account_id = $2",
                                                 uuid.UUID(pid), uuid.UUID(account)))
        return {**dict(r), "id": str(r["id"]), "account_id": str(r["account_id"]), "trip_item_id": str(r["trip_item_id"])} if r else None

    async def approve(self, account, pid, approval, now):
        r = await self._run(lambda c: c.execute(
            "update payment_requests set approval = $3, status = 'approved', updated_at = $4 "
            "where id = $1 and account_id = $2 and status = 'awaiting_approval'", uuid.UUID(pid), uuid.UUID(account), approval, now))
        return r.endswith(" 1")

    async def set(self, pid, **kw):
        cols = [k for k in kw if k in ("status", "link_asked_by")]
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(cols))
        await self._run(lambda c: c.execute(f"update payment_requests set {sets}, updated_at = now() where id = $1", uuid.UUID(pid),
                                            *[kw[k] for k in cols]))


STORE: Any = None


# ── after a call: a deposit asked → one request, one question to the guest ─────────────────────────────────────────

async def after_call(call: dict, reading, venue: str) -> Optional[dict]:
    """A booking call whose venue asked for a deposit or card → the payment request (once per booking)."""
    if STORE is None or (call.get("brief") or {}).get("purpose") != "book" or reading.state != "answered":
        return None
    quote = deposit_asked(reading)
    if not quote:
        return None
    brief = call.get("brief") or {}
    minor = amount_of(quote) or amount_of(reading.venue_words or "")
    from . import sentences as SN   # Sasha 117 · "Saturday 3 October at 21:00", never "2026-10-03" in the guest's sentence
    when = f"{SN.day_words(brief.get('date'))} at {brief.get('time')}, {brief.get('party')} people" if brief.get("date") else "your booking"
    lines = read_back(venue, minor, quote[:300], when)
    row = {"id": str(uuid.uuid4()), "account_id": str(call["account_id"]), "trip_item_id": str(call["trip_item_id"]), "payee": venue,
           "purpose": "deposit", "amount_minor": minor, "currency": "EUR", "venue_terms_quote": quote[:500],
           "read_back_lines": lines, "read_back_sha256": sha(lines), "tier": "guest_direct", "status": "awaiting_approval"}
    pid = await STORE.create(row)
    return {**row, "id": pid} if pid else None


router = APIRouter(prefix="/payments", tags=["booking-payments"])


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


@router.post("/{pid}/approve")
async def approve(pid: str, request: Request):
    """Sasha 319 · retired: on the guest's yes it asked the VENUE (Sasha's own text / email) for its payment link — Sasha's own send to a
    venue, gone. Nothing is sent. (S-81 tier 0's question was already retired, Sasha 254 R8: nothing creates these any more.)"""
    from .retired import refusal
    return refusal("a payment-link request to the venue")


__all__ = ["after_call", "amount_of", "deposit_asked", "read_back", "router", "MemoryPaymentStore", "PostgresPaymentStore"]
