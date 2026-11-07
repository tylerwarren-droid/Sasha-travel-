"""Sasha 354 · WHAT IS PENDING FOR THIS PERSON NOW — ONE record, read before any model step, so a reply means what it answers.

Found (Sasha 352's proof, mailbox 1774): (1) a new pick on a flight whose earlier choice was waiting for payment failed in the store
(AlreadyRecorded) — "still waiting for payment", and no card; (2) "Yes" with nothing waiting for a yes (a payment already under way) made
the model search flights again.

The record is the conversation's (s2_memory `pending`, Sasha 349's one record), written by the turn that made it (s2_memory.fold):
  yes      a read-back waiting for their yes — scope trip (hold_booking) or venue (kind "hold", hold_venue)
  pick     a new pick that waits for "keep or switch?" — an earlier choice of that flight is waiting for payment
  question her latest question (a "yes" answers IT, never an older read-back)
… each checked against what's live (a read-back still in its 15 minutes, the pick's payment still open). And, read from the basket itself,
a payment under way (never copied into the record).

  now(account) → {"now": the pending item or None, "payment": the payment under way or None}
  resolve_yes(...) the ONE reading of a bare yes — what it answers, or that nothing waits for one.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

log = logging.getLogger("agapi.pending")

PICK_KIND = "pending_pick"   # s2_memory kinds: the pick waiting (its offer, the payment it would replace) — set by choose_offer
PICK_FOR_S = 15 * 60
NOTHING = "Nothing is waiting for a yes right now — what would you like to do?"


def _fresh(at: Any, secs: int) -> bool:
    try:
        t = at if isinstance(at, datetime) else datetime.fromisoformat(str(at))
        return (datetime.now(timezone.utc) - t).total_seconds() <= secs
    except Exception:
        return False


async def payment(account: str) -> Optional[Dict[str, Any]]:
    """The payment under way for the trip (the basket's own rows: pending_payment, one Stripe session) — its amount and what it holds."""
    try:
        from booking_signer import basket_book as BB
        p = await BB.in_progress(account)
    except Exception as e:
        log.info("[pending] the basket didn't answer: %s", type(e).__name__)
        return None
    if not p:
        return None
    rows = p.get("rows") or []
    amount = round(sum(float(r.get("price_amount") or 0) for r in rows), 2) or None
    what = "; ".join(f"{(r.get('snapshot') or {}).get('owner') or ''} {(r.get('snapshot') or {}).get('from') or ''} → "
                     f"{(r.get('snapshot') or {}).get('to') or ''}".strip() for r in rows if r.get("kind") == "flight") or "your trip"
    return {"sid": p["sid"], "trip_id": p["trip_id"], "amount_eur": amount, "what": what, "rows": rows}


async def now(account: str) -> Dict[str, Any]:
    from agapi import s2_memory as MEM
    try:
        m = await MEM._load(account) or {}
    except Exception as e:
        log.info("[pending] the record didn't answer: %s", type(e).__name__)
        m = {}
    p = dict(m.get("pending") or {})
    cur: Optional[Dict[str, Any]] = None
    if p.get("kind") == "yes" and p.get("scope") == "trip":
        from agapi import v0 as API
        h = API._HELD.get(account)
        if h and not API.stale(h.get("at")):
            cur = {**p, "id": h.get("sha")}
    elif p.get("kind") == "hold":   # a venue's read-back (s2_memory's own kind)
        from agapi import venues as VN
        h = VN._HELD.get(account) or {}
        if h and MEM._hold_live(account, p):
            cur = {"kind": "yes", "scope": "venue", "what": p.get("what"), "venue": h.get("venue"), "at": p.get("at")}
    elif p.get("kind") == "pick":
        pk = ((m.get("kinds") or {}).get(PICK_KIND)) or {}
        if pk and _fresh(pk.get("at"), PICK_FOR_S):
            cur = {**p, **pk}
    elif p.get("kind") == "question":
        cur = p
    return {"now": cur, "payment": await payment(account)}


async def hold_pick(account: str, pick: Dict[str, Any]) -> None:
    from agapi import s2_memory as MEM
    await MEM.put_kinds(account, {PICK_KIND: {**pick, "at": datetime.now(timezone.utc).isoformat()}})


async def drop_pick(account: str) -> None:
    from agapi import s2_memory as MEM
    await MEM.put_kinds(account, {PICK_KIND: None})


def payment_line(pay: Dict[str, Any]) -> str:
    amt = f"€{pay['amount_eur']:,.2f} " if pay.get("amount_eur") else ""
    return f"Nothing is waiting for a yes — your payment {amt}for {pay.get('what') or 'your trip'} is still open. Tap Pay to finish it."


def pick_line(pick: Dict[str, Any]) -> str:
    """Both choices WITH their own figures (found live: without them, her words added the waiting payment's total to the new pick)."""
    eur = lambda v: f" (€{float(v):,.2f})" if isinstance(v, (int, float)) and v else ""
    return (f"Your earlier pick, {pick.get('old') or 'that flight'}{eur(pick.get('old_eur'))}, is waiting for payment. Keep it, or switch to "
            f"{pick.get('new') or 'the new one'}{eur(pick.get('new_eur'))}?")


def resolve_yes(state: Dict[str, Any]) -> Dict[str, Any]:
    """A bare yes, against what is pending now → {"do": "book" | "book_venue" | "model" | "say", ...}."""
    cur, pay = state.get("now"), state.get("payment")
    if cur and cur.get("kind") == "yes" and cur.get("scope") == "trip":
        return {"do": "book"}
    if cur and cur.get("kind") == "yes" and cur.get("scope") == "venue":
        return {"do": "book_venue", "venue": cur.get("venue")}
    if cur and cur.get("kind") == "question":
        return {"do": "model"}   # her question — the conversation answers it, as ever
    if cur and cur.get("kind") == "pick":
        return {"do": "say", "line": pick_line(cur), "card": True}
    if pay:
        return {"do": "say", "line": payment_line(pay), "card": True}
    return {"do": "say", "line": NOTHING, "card": False}


__all__ = ["now", "payment", "hold_pick", "drop_pick", "resolve_yes", "payment_line", "pick_line", "NOTHING", "PICK_KIND"]
