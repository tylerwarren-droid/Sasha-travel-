"""Sasha 261 · AN AGAPI OUTAGE, NAMED (rows 897/900: from 16:59 UTC on 13 Oct the sandbox key's monthly budget was spent — every
paid AgAPI call answered 402 budget_exhausted — and she said "didn't work", or offered a bank statement in its place). AgAPI is
Kanoe's own service, and when IT is out the person is told so in one plain line, and the founder is told by email — the way
model_health names the model's credit. In ONE place, used by the one transport (agapi_route.post) every family's client calls:

  kind_of(envelope)   "limit" (402 budget_exhausted, 429 rate_limited) | "slow" (a timeout, AgAPI unreachable) | None
  note(kind, …)       recorded on the tool call in progress (watching) + ONE email to the founder, at most once an hour per process
  watching()          sasha.turn's window around one tool: the outages its AgAPI calls met (the turn says voice.outage_line)

A venue's own upstream being down (upstream_unreachable) is NOT an AgAPI outage — that's the venue, said by its tool as before."""
from __future__ import annotations

import contextvars
import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Optional

log = logging.getLogger("agapi_health")

LIMIT, SLOW = "limit", "slow"
_KINDS = {"budget_exhausted": LIMIT, "rate_limited": LIMIT, "timeout": SLOW, "unreachable": SLOW}
ALERT_EVERY_S = 3600
_LAST: dict = {}
SEND = None   # tests replace it: (msg) → {"sent": bool, "why": str}
_SEEN: contextvars.ContextVar = contextvars.ContextVar("agapi_outages", default=None)


def kind_of(env: dict) -> Optional[str]:
    """An AgAPI answer (or the transport's own envelope) → the outage it is, else None."""
    if not isinstance(env, dict) or env.get("ok"):
        return None
    return _KINDS.get(str((env.get("error") or {}).get("code") or ""))


class watching:
    """with watching() as seen: r = await run(...) — `seen` is the outages the tool's AgAPI calls met (kinds, in order)."""

    def __enter__(self) -> List[str]:
        self.seen: List[str] = []
        self.tok = _SEEN.set(self.seen)
        return self.seen

    def __exit__(self, *exc):
        _SEEN.reset(self.tok)
        return False


def key_print(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:12] if key else "unset"


async def note(kind: str, op: str, url: str, key: str) -> dict:
    """An outage met: on the tool call in progress, and the founder told — at most once an hour (per process). Awaited."""
    seen = _SEEN.get()
    if seen is not None:
        seen.append(kind)
    now = time.time()
    if now - _LAST.get("at", 0) < ALERT_EVERY_S:
        return {"sent": False, "why": "already told within the hour"}
    _LAST["at"] = now
    from app.services import model_health as MH
    to = await MH._founder_address()
    where = f"{op} on {url.split('//')[-1].split('/')[0]}"
    what = "its key's budget is spent or rate-limited (402/429)" if kind == LIMIT else "it didn't answer in time / was unreachable"
    if not to:
        log.error("[agapi_health] AGAPI OUTAGE (%s: %s) — no founder address to tell", where, kind)
        return {"sent": False, "why": "no founder address"}
    at = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    msg = {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": to,
           "subject": "Sasha can't reach AgAPI — " + ("the key's budget is spent" if kind == LIMIT else "it isn't answering"),
           "text": "\n".join([
               f"At {at} one of Sasha's AgAPI calls failed: {what}.",
               f"Where it was seen: {where}. Key fingerprint (sha256): {key_print(key)} — the key itself is never sent.",
               "", "People are being told plainly that it can't be done right now; nothing is sent or booked on their behalf.",
               "", "To fix: raise the key's budget (AgAPI's signed admin action), or check the AgAPI service on Railway.",
               "You'll hear at most once an hour.", "", "— Sasha's health check"])}
    try:
        if SEND is not None:
            r = await SEND(msg)
        else:
            from booking_signer import live_events as LE
            r = await LE.send_email(msg)
    except Exception as e:
        r = {"sent": False, "why": type(e).__name__}
    log.error("[agapi_health] AGAPI OUTAGE (%s: %s) — founder told: %s", where, kind, r)
    return r


__all__ = ["LIMIT", "SLOW", "kind_of", "watching", "note", "key_print", "ALERT_EVERY_S"]
