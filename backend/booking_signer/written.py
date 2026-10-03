"""Sasha 118 · CONFIRMED IN WRITING, whichever way the writing comes — the confirmation rate's third leg.

A written confirmation is filed on the ONE booking it belongs to, for any booking Sasha made (a phone call, a form, an
email), whether:
  · the VENUE wrote to Sasha's own address (sasha@…) or texted her number from a number she did not call (4), or
  · the GUEST forwarded the venue's confirmation to her — by email from their account's own address, or on WhatsApp (3).
Before this, only a venue's email after a PHONE booking could be matched (inbound_phone.match_written), and even that
was never stored: booking_inbound did not accept the channel 'email' (sql/027).

The match is never a guess — the first rule that names exactly ONE booking decides; two that fit is no match:
  1. Sasha's own reference (K-XXXX, said to the venue on the call);
  2. the venue's own reference for it (localizador);
  3. the venue's name, and the booking's day;
  4. the guest's surname, and the booking's day.
What it says is read with the same field checks as every reply (followup.reply_reading): "confirmed" only on an explicit
yes that restates the day, the time and the number. A forwarded message is read for the VENUE's words in it — never the
guest's covering note, never a header.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

log = logging.getLogger("booking_signer.written")
WINDOW = timedelta(days=21)          # bookings made up to three weeks ago, still ahead (or today)
_GENERIC = {"restaurante", "restaurant", "bar", "taberna", "cafe", "casa", "madrid", "lisboa", "barcelona", "the", "and",
            "del", "las", "los", "spa", "hotel", "studio", "estudio", "centro", "dinner", "lunch", "cena", "comida", "table", "mesa"}
_FWD = re.compile(r"^\s*(?:-{2,}\s*)?(?:forwarded message|mensaje reenviado|message transf[ée]r[ée]|mensagem encaminhada|"
                  r"weitergeleitete nachricht|messaggio inoltrato)\b.*$", re.I | re.M)
_HEADER = re.compile(r"^\s*(?:from|de|von|da|date|fecha|data|datum|sent|enviado|subject|asunto|assunto|objet|betreff|oggetto|"
                     r"to|para|an|a|cc)\s*:.*$", re.I)


def _fold(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s or "") if unicodedata.category(ch) != "Mn").lower()


def _compact(s: str) -> str:
    return re.sub(r"[\s\-·.]", "", _fold(s))


def venue_words(text: Optional[str], forwarded: bool) -> str:
    """The venue's words: for a forward, what follows the forward marker, without headers or "> " quoting."""
    t = str(text or "")
    if forwarded:
        m = _FWD.search(t)
        if m:
            t = t[m.end():]
        t = "\n".join(re.sub(r"^\s*>+\s?", "", ln) for ln in t.splitlines())
        t = "\n".join(ln for ln in t.splitlines() if not _HEADER.match(ln))
    return t.strip()


def _local_day(c: Mapping[str, Any]) -> Optional[str]:
    dt = c.get("date_time")
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    try:
        return dt.astimezone(ZoneInfo(c.get("local_timezone") or "Europe/Madrid")).date().isoformat()
    except Exception:
        return dt.date().isoformat()


def _surname(c: Mapping[str, Any]) -> str:
    name = ((c.get("request") or {}).get("who") or {}).get("name") or c.get("guest_name") or ""
    parts = name.split()
    return parts[-1] if parts else ""


def pick(cands: List[Mapping[str, Any]], subject: Optional[str], text: Optional[str], now: datetime) -> Tuple[Optional[dict], str]:
    """(the one booking, the rule that named it) — or (None, why not)."""
    from .mailbox import _when
    hay = f"{subject or ''}\n{text or ''}"
    fh, ch = _fold(hay), _compact(hay)
    said_day = (_when(hay, now) or "")[:10] or None

    def one(rule: str, hits: List[Mapping[str, Any]]):
        ids = {str(h["trip_item_id"]) for h in hits}
        if len(ids) == 1:
            return dict(hits[0]), rule
        return None, (f"two or more bookings fit by {rule} — not guessed" if ids else "")

    tiers = [
        ("Sasha's reference", [c for c in cands if c.get("own_reference") and len(_compact(c["own_reference"])) >= 4
                               and _compact(c["own_reference"]) in ch]),
        ("the venue's reference", [c for c in cands if c.get("booking_reference") and len(_compact(c["booking_reference"])) >= 4
                                   and _compact(c["booking_reference"]) in ch]),
        ("the venue's name and the day", [c for c in cands if said_day and _local_day(c) == said_day
                                          and (lambda ws: bool(ws) and all(re.search(rf"\b{re.escape(w)}\b", fh) for w in ws))(
                                              [w for w in re.findall(r"[a-z0-9]+", _fold(c.get("venue") or "")) if len(w) >= 4 and w not in _GENERIC])]),
        ("the guest's surname and the day", [c for c in cands if said_day and _local_day(c) == said_day and len(_surname(c)) >= 3
                                             and re.search(rf"\b{re.escape(_fold(_surname(c)))}\b", fh)]),
    ]
    for rule, hits in tiers:
        got, why = one(rule, hits)
        if got is not None or why:
            return got, why or rule
    return None, "nothing in it names one of the bookings (no reference; no venue name or surname with the day)"


async def file(provider_id: str, channel: str, sender: Optional[str], subject: Optional[str], text: Optional[str], now: datetime,
               account: Optional[str] = None, forwarded: bool = False) -> Optional[dict]:
    """Match and file. Returns {trip_item_id, venue, result, why, basis} — or None (not one booking: nothing filed here)."""
    from . import followup as FU, inbound_phone as IP
    if IP.STORE is None:
        return None
    words = venue_words(text, forwarded)
    cands = await IP.STORE.written_candidates(now - WINDOW, account)
    got, basis = pick(cands, subject, words, now)
    if got is None:
        log.info("[written] %s %s not matched: %s", channel, provider_id, basis)
        return None
    o = got.get("request") or {}
    try:
        reading = FU.reply_reading(words, o) if isinstance(o, dict) and o else None
    except (KeyError, TypeError, ValueError):   # an older booking's request without every field: shown, never read as a yes
        reading = None
    reading = reading or {"result": "none", "why": "the booking's request can't be checked against their words — shown as written",
                          "quote": words[:300]}
    reading = {**reading, "basis": basis, **({"forwarded_by": "guest"} if forwarded else {})}
    key = ("sha256:" + hashlib.sha256(sender.strip().lower().encode()).hexdigest()) if sender else "unknown"
    row = {"provider_id": provider_id, "channel": channel, "from_key": key, "to_number": None, "body_text": words[:8000],
           "call_id": str(got["call_id"]) if got.get("call_id") else None, "trip_item_id": str(got["trip_item_id"]), "received_at": now}
    fresh = await IP.STORE.put(row)
    if not fresh:
        return {"trip_item_id": str(got["trip_item_id"]), "venue": got.get("venue"), "result": "already filed", "why": "", "basis": basis}
    await IP.STORE.set_reading(provider_id, reading)
    status = {"confirmed": "confirmed", "proposed": "proposed"}.get(reading["result"])
    if status and got.get("status") != status:   # a "no" never cancels by itself; a confirmation lifts unclear/requested
        await IP.STORE.outcome(str(got["trip_item_id"]), status, "confirmed" if status == "confirmed" else "unclear",
                               words, now, "email" if channel == "email" else channel)
    log.info("[written] %s %s → %s (%s): %s", channel, provider_id, got["trip_item_id"], basis, reading["result"])
    return {"trip_item_id": str(got["trip_item_id"]), "venue": got.get("venue"), "result": reading["result"], "why": reading["why"],
            "basis": basis, "day": _local_day(got)}


async def account_of_email(addr: Optional[str]) -> Optional[str]:
    """The account whose OWN address this is (its sign-in email; the founder's for the demo account) — a guest forwarding."""
    import os
    from . import ladder_routes as LR
    from .account import DEMO_ACCOUNT_ID
    a = (addr or "").strip().lower()
    if not a:
        return None
    if a == os.getenv("SASHA_FOUNDER_EMAIL", "").strip().lower():
        from .identity import founder_account
        return founder_account() or DEMO_ACCOUNT_ID
    return await LR.LADDER_STORE.account_by_email(a) if LR.LADDER_STORE is not None else None


__all__ = ["pick", "file", "venue_words", "account_of_email", "WINDOW"]
