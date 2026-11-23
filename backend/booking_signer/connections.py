"""Sasha 400 · A BROKEN CONNECTION IS NOTICED AND SAID — the ONE health truth for every outside connection Sasha depends on.

Measured (Tyler's Gmail): Google refused the link's token on 8 Nov 20:03 (vault_uses: "UseRefused: Google refused the connection's
token"). mailbox.link_dead marked mailbox_links.needs_reconnect_at and tried to tell him ONCE — WhatsApp (outside its 24-hour window)
and a one-slot /s2 "news" line the next news overwrites — and the 6-hourly loop then left the link out (all_links: needs_reconnect_at
is null). Nothing said it again: not the morning brief, not get_status. He reconnected on 20 Nov without knowing why nothing came. Each
connection decided its own health: Gmail by its columns, Google Calendar by its OWN copy of them (and its own rule: only invalid_grant),
Gmail's receipts by re-reading Gmail's, and Outlook by nothing — a refused Outlook token was silently None.

THE ONE TRUTH (this module):
  CONNECTIONS   every outside connection — its name, what a break costs the person, where they reconnect, and HOW its health is known.
  broke()       a connection refused (any refusal but a transient one: Google/Microsoft 5xx or 429, a network error) → kept on the
                person's own record (s2_memory kind KIND, {kind: {since, why}}), and SAID ONCE on the one outcome channel
                (channel.tell: WhatsApp when it can take it, else S2, kept for their return).
  working()     it answered again (a use that worked, or a reconnect) → cleared; the person is not told twice.
  broken()      what is broken now — the ONLY reader: the connection's own code before it uses it, get_status (s2_status), the morning
                brief (proactive), the You page (mailbox.status / calendar_sync.status).
  check()       the 6-hourly look (mailbox's loop): every linked person-held connection's token is asked for once — so a break is
                noticed within hours, not when some booking next happens to need it.

PERSON-HELD connections are kept here. PLATFORM connections (AgAPI, the WhatsApp sender, the payment provider, Duffel) are Sasha's own,
not the person's: their health is said in the turn that needs them (CONNECTIONS[...]["noticed"] names where), never kept per person.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("booking_signer.connections")

KIND = "connections"   # the person's own record (s2_memory): {kind: {"since": iso, "why": rule}} — nothing else

#: every outside connection. "held": "person" (kept here, said to them) | "platform" (Sasha's own; said in the turn that needs it).
CONNECTIONS: Dict[str, Dict[str, Any]] = {
    "gmail": {"held": "person", "name": "Gmail", "provider": "google.com", "label": "Gmail (read-only)", "purposes": ("gmail_read",),
              "cost": "I can't read your booking confirmation emails until you reconnect it", "where": "/you#gmail"},
    "google_calendar": {"held": "person", "name": "Google Calendar", "provider": "google.com", "label": "Google Calendar",
                        "purposes": ("calendar_sync", "calendar_freebusy", "calendar_setup"),
                        "cost": "I can't put your bookings in your calendar or check when you're free until you reconnect it",
                        "where": "/you#calendar"},
    "outlook": {"held": "person", "name": "Outlook", "provider": "microsoft.com", "label": "Outlook (read-only)", "purposes": ("outlook_read",),
                "cost": "I can't read your booking confirmation emails in Outlook until you reconnect it", "where": "/you#outlook"},
    "agapi": {"held": "platform", "noticed": "agapi/v0.py ToolError — said in the turn; /health watched by ops"},
    "whatsapp_sender": {"held": "platform", "noticed": "booking_signer/channel.tell — WhatsApp refused → said on S2, kept"},
    "payments": {"held": "platform", "noticed": "the checkout's own answer — said at payment"},
    "duffel": {"held": "platform", "noticed": "scripts/live_suite — the 6-hourly live suite alerts"},
}
PERSON = tuple(k for k, c in CONNECTIONS.items() if c["held"] == "person")
_MEM: Dict[str, Dict[str, dict]] = {}   # no database (tests): this process's copy


def transient(rule: str) -> bool:
    """The ONE rule for "not broken, just busy": the provider answering 5xx / 429, or the network. Anything else is broken."""
    return bool(re.fullmatch(r"connection_http_(5\d\d|429)", rule or "")) or rule in ("network", "unreachable")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get(account: str) -> Dict[str, dict]:
    from agapi import s2_memory as M
    try:
        kept = await M.kind(account, KIND)
    except Exception:
        kept = None
    if isinstance(kept, dict):
        return {k: dict(v) for k, v in kept.items() if k in CONNECTIONS and isinstance(v, dict)}
    return dict(_MEM.get(account) or {})


async def _put(account: str, rows: Dict[str, dict]) -> None:
    _MEM[account] = rows
    from agapi import s2_memory as M
    try:
        if not await M.put_kind(account, KIND, rows or None):
            log.info("[connections] kept in this process only (no memory table)")
    except Exception as e:
        log.warning("[connections] not kept: %s", type(e).__name__)


def line(kind: str) -> str:
    """What a break costs them, plainly, and their one step."""
    c = CONNECTIONS[kind]
    return f"Your {c['name']} connection stopped working, so {c['cost']}. Reconnect it in You."


async def broken(account: Optional[str]) -> Dict[str, dict]:
    """{kind: {since, why}} — what is broken for this person now. The ONE reader."""
    return await _get(account) if account else {}


async def is_broken(account: Optional[str], kind: str) -> bool:
    return kind in await broken(account)


async def broke(account: str, kind: str, rule: str, now: Optional[datetime] = None) -> bool:
    """A refusal. Transient → nothing (tried again later). Else kept and, the FIRST time, said once. → True when it is broken."""
    if kind not in PERSON:
        raise KeyError(kind)
    if transient(rule):
        log.info("[connections] %s busy for now (%s) — tried again later", kind, rule)
        return False
    rows = await _get(account)
    if kind in rows:
        return True   # already known and already said: never twice
    rows[kind] = {"since": (now or _now()).isoformat(), "why": str(rule or "refused")[:80]}
    await _put(account, rows)
    log.warning("[connections] %s broken: %s — said once; get_status and the brief say it while it lasts", kind, rule)
    try:
        from . import channel as CH
        c = CONNECTIONS[kind]
        await CH.tell(account, line(kind), news_key=f"connection:{kind}:{rows[kind]['since'][:10]}", news_url=c["where"],
                      event={"render": {"kind": "reconnect", "label": f"Reconnect {c['name']}", "url": c["where"]}})
    except Exception as e:   # the record still holds it: get_status and the brief say it
        log.warning("[connections] the %s line wasn't told now: %s", kind, type(e).__name__)
    return True


async def working(account: str, kind: str) -> None:
    """It answered (a use that worked, or a reconnect): cleared — the notice ends by itself."""
    rows = await _get(account)
    if rows.pop(kind, None) is not None:
        await _put(account, rows)
        log.info("[connections] %s working again — the notice is cleared", kind)


async def gone(account: str, kind: str) -> None:
    """Disconnected by them: no connection, so nothing broken to say — cleared like a mend."""
    await working(account, kind)


async def said(account: Optional[str]) -> Optional[str]:
    """The line get_status and the morning brief say while something is broken (None when all is well)."""
    rows = await broken(account)
    return " ".join(line(k) for k in CONNECTIONS if k in rows) or None


async def check(account: str, kind: str, item_id: str) -> bool:
    """The 6-hourly look: one token asked for, nothing read. → True when it works."""
    from .vault import crypto as VC
    try:
        await VC.use_connection(account, item_id, purpose=CONNECTIONS[kind]["purposes"][0])
    except VC.UseRefused as e:
        await broke(account, kind, e.rule)
        return False
    except Exception as e:   # the network: not a break
        log.info("[connections] %s not checked now: %s", kind, type(e).__name__)
        return False
    await working(account, kind)
    return True


def kind_of(item: dict) -> Optional[str]:
    """The connection a vault item IS (its provider and label) — None for one no connection here claims (the ratchet fails on it)."""
    return next((k for k in PERSON if CONNECTIONS[k]["provider"] == item.get("provider") and CONNECTIONS[k]["label"] == item.get("label")), None)


EVERY_S = 6 * 3600


async def check_all() -> List[str]:
    """Every live connection of every person, looked at once: a break noticed within hours (said once), a mend cleared. Gmail's own
    6-hourly sync starts with the same look, so it is skipped here."""
    from .vault import crypto as VC
    out: List[str] = []
    for it in await VC.STORE.live_connections():
        kind = kind_of(it)
        if kind is None:
            log.error("[connections] a live connection no health truth claims: %s / %s", it.get("provider"), it.get("label"))
            continue
        if kind == "gmail":
            continue
        ok = await check(str(it["account_id"]), kind, str(it["id"]))
        out.append(f"{kind}: {'ok' if ok else 'broken'}")
    return out


_task = None


async def _forever() -> None:
    import asyncio
    while True:
        try:
            done = await check_all()
            if done:
                log.info("[connections] looked at %d connection(s)", len(done))
        except Exception as e:
            log.error("[connections] the look failed: %s", type(e).__name__)
        await asyncio.sleep(EVERY_S)


def start() -> None:
    import asyncio
    import os
    global _task
    if _task is None and os.getenv("SASHA_CONNECTIONS_LOOP", "1") == "1" and os.getenv("DATABASE_URL", "").strip():
        _task = asyncio.create_task(_forever())


__all__ = ["gone", "kind_of", "check_all", "start", "CONNECTIONS", "PERSON", "KIND", "transient", "line", "broken", "is_broken", "broke", "working", "said", "check"]
