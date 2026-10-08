"""Sasha 212 · PAYMENT → SASHA KNOWS. When a payment completes and Pacioli has recorded the booking (paid_watch.settle, whoever
sees the payment first), the account's open /next page hears it AT ONCE — the person does nothing — and Sasha says it,
once: "That's gone through — you're booked. Your confirmation is on its way to <email>, and your full itinerary is here."
with a card linking the itinerary. The confirmation email (TEST-tagged, like the cards) goes to the account's address on
record with the same link. "Booked" only when Pacioli booked it; a failure is said plainly with the next step.

One worker (R3), so the channel is in memory: each open page subscribes (GET /api/agent/events, server-sent events); the
last few events per account are kept for 15 minutes, so a page that reconnects (or opens just after) still hears it once —
the page sends the last id it heard.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import os
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("booking_signer.live_events")

_SUBS: Dict[str, List[asyncio.Queue]] = {}
_RECENT: Dict[str, List[dict]] = {}
_IDS = itertools.count(int(time.time() * 1000))
KEEP_S = 900


def subscribe(account: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _SUBS.setdefault(account, []).append(q)
    return q


def unsubscribe(account: str, q: asyncio.Queue) -> None:
    subs = _SUBS.get(account) or []
    if q in subs:
        subs.remove(q)


def recent(account: str, since: int = 0) -> List[dict]:
    now = time.time()
    keep = [e for e in _RECENT.get(account, []) if now - e["_at"] < KEEP_S]
    _RECENT[account] = keep
    return [e for e in keep if e["id"] > since]


def publish(account: str, event: dict) -> dict:
    ev = {**event, "id": next(_IDS), "_at": time.time()}
    _RECENT.setdefault(account, []).append(ev)
    del _RECENT[account][:-5]
    for q in list(_SUBS.get(account) or []):
        q.put_nowait(ev)
    log.info("[live_events] %s → %d open page(s)", event.get("type"), len(_SUBS.get(account) or []))
    return ev


def itinerary_url() -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/") + "/next?tab=trip"


def words_for(r: dict, email: Optional[str]) -> Dict[str, str]:
    """What she says (display and spoken — no figures in either) for a settled payment."""
    status = (r or {}).get("status")
    if status == "booked":
        if email:
            said = email.replace("@", " at ").replace(".", " dot ")
            return {"text": f"That's gone through — you're booked. Your confirmation is on its way to {email}, and your full itinerary is here.",
                    "spoken": f"That's gone through, you're booked. Your confirmation is on its way to {said}, and your full itinerary is here."}
        text = "That's gone through — you're booked. Your full itinerary is here."
        return {"text": text, "spoken": text.replace(" — ", ", ")}
    failed = [x for x in (r or {}).get("failed") or [] if x]
    done = [x for x in (r or {}).get("booked") or [] if x]
    if done and failed:
        text = ("Your payment went through and most of it is booked — but not everything: " + failed[0].rstrip(".") +
                ". Shall I find the closest alternative for that part?")
    else:
        why = (failed[0] if failed else str((r or {}).get("say") or "the booking didn't go through")).rstrip(".")
        text = f"Your payment went through, but the booking didn't: {why}. Shall I find the closest alternative and try again?"
    return {"text": text, "spoken": text}


def compose_email(r: dict, to: str, title: Optional[str]) -> dict:
    """The confirmation, TEST-tagged like the cards: what Pacioli booked, word for word, and the itinerary link."""
    lines = ["Your trip is booked (TEST).", ""] + [f"• {x}" for x in (r.get("booked") or [r.get("say")]) if x] + [
        "", f"Your full itinerary: {itinerary_url()}", "",
        "TEST: a demo booking — no airline or hotel charge.", "", "— Sasha (AI concierge, Kanoe Technologies SL)"]
    return {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": to,
            "subject": f"Booked (TEST): {title or 'your trip'}", "text": "\n".join(lines)}


SEND = None   # tests replace it: (email dict) → {"sent": bool, "why": str}


async def send_email(msg: dict) -> dict:
    if SEND is not None:
        return await SEND(msg)
    from . import emailing as E, ladder_routes as LR
    from .ladder import emails_ready
    why = emails_ready()
    if why:
        return {"sent": False, "why": why}
    got = await E.send(LR.HTTP, msg)
    return {"sent": bool(got.sent), "why": getattr(got, "why", None)}


async def on_settled(account: str, r: dict, title: Optional[str] = None) -> dict:
    """Called once per payment, after Pacioli recorded it: the confirmation email (booked only), then the event."""
    from . import guest_receipt as GR
    email, mailed = None, None
    if (r or {}).get("status") == "booked":
        try:
            email = await GR.address_of(account)
            if email:
                mailed = await send_email(compose_email(r, email, title))
                if not mailed.get("sent"):
                    log.error("[live_events] confirmation not emailed: %s", mailed.get("why"))
                    email = None   # never say it's on its way when it isn't
        except Exception as e:
            log.error("[live_events] confirmation not emailed: %s: %s", type(e).__name__, e)
            email = None
    w = words_for(r, email)
    ev = publish(account, {"type": "booked" if (r or {}).get("status") == "booked" else "booking_failed", **w,
                           "card": {"kind": "itinerary_link", "url": itinerary_url(), "title": title or "Your trip"},
                           "emailed": bool(email)})
    return {"event": ev, "email": mailed}


__all__ = ["subscribe", "unsubscribe", "recent", "publish", "on_settled", "words_for", "compose_email", "itinerary_url"]
