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


async def status_now(account: str) -> Optional[dict]:
    """Sasha 249 · ONE STATUS: the account's status as get_status decides it (agapi.s2_status) — the /s2 "Booked" card and the
    WhatsApp line show its line. None when the records don't answer (the card is then not drawn; never a guessed "Booked")."""
    try:
        from agapi import s2_status as ST
        return ST.public(await ST.status_of(account, sweep=False))
    except Exception as e:
        log.warning("[live_events] status not read: %s", type(e).__name__)
        return None


def compose_itinerary(lines: List[str], to: str, title: Optional[str], test: bool = False) -> dict:
    """Sasha 279 · C · the itinerary email after a completed booking that wasn't a payment (a venue): what is booked, from the ONE
    status's own lines, and the itinerary link. TEST-tagged only when the booking was a test one."""
    body = [f"Booked{' (TEST)' if test else ''}:", ""] + [f"• {x}" for x in lines if x] + [
        "", f"Your full itinerary: {itinerary_url()}", "",
        *(["TEST: a demo booking.", ""] if test else []),
        "If you want to change anything, reply to Sasha any time — 24 hours a day, 7 days a week.", "",
        "— Sasha (AI concierge, Kanoe Technologies SL)"]
    return {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": to,
            "subject": f"Booked{' (TEST)' if test else ''}: {title or 'your itinerary'}", "text": "\n".join(body)}


# ── Sasha 279 · B + C · A FINISHED BOOKING — the ONE trigger ─────────────────────────────────────────────────────────────────────
# Every way a booking becomes confirmed calls completed(): a payment settled (on_settled — flights, hotels, a whole trip), a venue
# confirmed in the turn (agapi.venues._finish), a venue confirmed later by its call (agapi.venue_calls.after_call) or by a platform's
# email (mailbox._told_auto). Once per booking `key`: the itinerary email (its send result READ — "I've sent it" only when it went),
# her words (voice.paid_line + voice.closing_line), and — push=True — BOTH doors told now: the open page (the `booked` event, which
# /s2 speaks) and WhatsApp; kept as news (s2_memory "news") so a return later — from WhatsApp, the payment page, after the 15-minute
# replay or a restart — hears it first, once. push=False: the caller's own turn or message says the words (they are returned).
CLOSED_KEEP = 60
_CLOSED: Dict[str, List[str]] = {}
WA_SEND = None   # tests replace it: (account, text) → str


async def _closed(account: str) -> List[str]:
    if account not in _CLOSED:
        try:
            from agapi import s2_memory as M
            _CLOSED[account] = [str(x) for x in (await M.kind(account, "closed") or [])]
        except Exception as e:
            log.warning("[live_events] closed keys not read: %s", type(e).__name__)
            _CLOSED[account] = []
    return _CLOSED[account]


async def _close(account: str, key: str) -> None:
    keys = await _closed(account)
    keys.append(key)
    del keys[:-CLOSED_KEEP]
    try:
        from agapi import s2_memory as M
        await M.put_kind(account, "closed", list(keys))
    except Exception as e:
        log.warning("[live_events] closed key not kept: %s", type(e).__name__)


async def keep_news(account: str, key: str, text: str) -> None:
    try:
        from agapi import s2_memory as M
        await M.put_kind(account, "news", {"key": key, "text": text, "at": time.time()})
    except Exception as e:
        log.warning("[live_events] news not kept: %s", type(e).__name__)


async def take_news(account: str) -> Optional[dict]:
    """The news kept for this account's return (and forgotten: it is said once). None when there is none, or it is over a day old."""
    try:
        from agapi import s2_memory as M
        n = await M.kind(account, "news")
        if n:
            await M.put_kind(account, "news", None)
        return n if isinstance(n, dict) and n.get("text") and time.time() - float(n.get("at") or 0) < 86400 else None
    except Exception as e:
        log.warning("[live_events] news not read: %s", type(e).__name__)
        return None


async def _tell_whatsapp(account: str, text: str) -> str:
    if WA_SEND is not None:
        return await WA_SEND(account, text)
    try:
        from . import guest_whatsapp as GW
        ch = await GW.STORE.channel_of_account(account) if GW.STORE else None
        if not ch:
            return "not linked"
        st = await GW.STORE.get_state(ch["wa_id_sha256"])
        res = await GW.deliver(ch, GW.sender_for(st), GW.Out().text(text), st.get("last_inbound_at"))
        return str(res)
    except Exception as e:
        log.warning("[live_events] not told on WhatsApp: %s: %s", type(e).__name__, e)
        return f"not told: {type(e).__name__}"


async def completed(account: str, key: str, *, item: Optional[str] = None, paid: bool = False, lead: Optional[str] = None,
                    lines: Optional[List[str]] = None, title: Optional[str] = None, test: bool = False, email: Optional[dict] = None,
                    push: bool = True, wa_extra: Optional[List[str]] = None) -> Dict[str, Any]:
    """A booking is complete (confirmed): said once. `lead` (else paid_line(item) when paid) goes first; then the closing line.
    `email`: the message to send (else the itinerary from `lines`). → {text, emailed, said, …}; said False when already said."""
    from app.agent import voice as V
    from . import guest_receipt as GR
    if not account or not key:
        return {"text": "", "emailed": False, "said": False}
    if key in await _closed(account):
        return {"text": "", "emailed": False, "said": False, "already": True}
    await _close(account, key)
    emailed, mailed = False, None
    try:
        to = await GR.address_of(account)
        if to:
            msg = {**email, "to": to} if email else compose_itinerary(list(lines or []), to, title, test)
            mailed = await send_email(msg)
            emailed = bool(mailed.get("sent"))
            if not emailed:
                log.error("[live_events] itinerary not emailed: %s", mailed.get("why"))
        else:
            log.warning("[live_events] itinerary not emailed: no address on record")
    except Exception as e:
        log.error("[live_events] itinerary not emailed: %s: %s", type(e).__name__, e)
    first = lead if lead is not None else (V.paid_line(item) if paid else "")
    text = " ".join(x for x in (first, V.closing_line(emailed)) if x)
    out: Dict[str, Any] = {"text": text, "emailed": emailed, "email": mailed, "said": True}
    if push:
        st = await status_now(account)
        out["event"] = publish(account, {"type": "booked", "text": text, "say": text, "spoken": text.replace(" — ", ", "), "key": key,
                                         "card": {"kind": "itinerary_link", "url": itinerary_url(), "title": title or "Your itinerary"},
                                         "emailed": emailed, **({"status": st} if st else {})})
        await keep_news(account, key, text)
        out["whatsapp"] = await _tell_whatsapp(account, "\n".join([text] + [x for x in (wa_extra or []) if x] + [itinerary_url()]))
        log.info("[live_events] completed %s: emailed %s, WhatsApp %s", key[-12:], emailed, out["whatsapp"])
    return out


def item_of(r: dict, title: Optional[str]) -> str:
    """What was paid for, in words: the trip's title, else the flight, else "your trip"."""
    if title:
        return str(title)
    c = (r or {}).get("card") or {}
    if c.get("flights"):
        return f"the {' '.join(str(x) for x in (c.get('owner'), c.get('flights')) if x)} flight"
    return "your trip"


async def on_settled(account: str, r: dict, title: Optional[str] = None, key: Optional[str] = None,
                     wa_extra: Optional[List[str]] = None) -> dict:
    """Called once per payment, after Pacioli recorded it. Booked → completed() (the email, her words — Sasha 279 · B: "Your payment
    for <item> went through — you're booked." then the closing line — and both doors). Failed or partly booked → said as before."""
    status = (r or {}).get("status")
    failed = [x for x in (r or {}).get("failed") or [] if x]
    if status == "booked" and key:
        lead = None if not failed else words_for({**r, "status": "partly_booked"}, None)["text"]   # partly booked: never "you're booked"
        email = compose_email(r, "", title)
        out = await completed(account, f"pay:{key}", item=item_of(r, title), paid=True, lead=lead, title=title, email=email,
                              wa_extra=wa_extra)
        if out.get("said"):
            return {"event": out.get("event"), "email": out.get("email"), "whatsapp": out.get("whatsapp"), "text": out["text"]}
        return {"event": None, "email": None, "already": True}
    email, mailed = None, None
    if status == "booked":   # no key (an old caller): the confirmation email and the event, as before
        from . import guest_receipt as GR
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
    st = await status_now(account)
    ev = publish(account, {"type": "booked" if status == "booked" else "booking_failed", **w,
                           "card": {"kind": "itinerary_link", "url": itinerary_url(), "title": title or "Your trip"},
                           "emailed": bool(email), **({"status": st} if st else {})})
    return {"event": ev, "email": mailed}


__all__ = ["subscribe", "unsubscribe", "recent", "publish", "on_settled", "words_for", "compose_email", "itinerary_url", "completed",
           "compose_itinerary", "take_news", "keep_news", "item_of"]
