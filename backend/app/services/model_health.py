"""Sasha 257 · THE MODEL'S CREDIT, NAMED (Tyler, 13 Oct, after Sasha went silent for everyone at ~10:40 UTC): when the Anthropic
account behind Sasha's key runs out of credit, every model call fails with "Your credit balance is too low to access the Anthropic
API". Before this, people got an empty reply or "something went wrong", the deploy gate failed on 40 unrelated-looking checks, and
nobody was told. Now, in ONE place:

  is_credit(e)      that failure, recognised (by Anthropic's own words — the billing error, not a rate limit or an outage)
  PLAIN             what a person is told instead: plain, true, no blame on them
  alert(where)      ONE email to the founder (his account's own sign-in address), at most once an hour per process — awaited
  preflight()       a 1-token call the deploy gate makes FIRST: a credit failure stops the gate with its own name

Used by sasha.turn_with_quiver (every surface: /s2, /next, WhatsApp, voice) and scripts/gate.py. Never prints the key."""
from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

log = logging.getLogger("model_health")

PLAIN = ("I can't answer right now — the AI service I run on has run out of credit. Kanoe has been told and is fixing it; "
         "nothing was booked or sent.")
ALERT_EVERY_S = 3600
_LAST: dict = {}
SEND = None   # tests replace it: (msg) → {"sent": bool, "why": str}


def is_credit(e: BaseException) -> bool:
    """Anthropic's billing refusal ("credit balance is too low"), as opposed to a rate limit, an overload or a bad request."""
    t = f"{type(e).__name__}: {e}".lower()
    return "credit balance is too low" in t or ("billing" in t and "credit" in t)


def key_print() -> str:
    """The key's fingerprint (never the key): the same sha256 prefix the gate prints."""
    k = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return hashlib.sha256(k.encode()).hexdigest()[:12] if k else "unset"


async def _founder_address() -> Optional[str]:
    from app.services.accounts import founder_account
    f = founder_account()
    if not f:
        return None
    try:
        from booking_signer import guest_receipt as GR
        return await GR.address_of(f)
    except Exception as e:
        log.warning("[model_health] the founder's address not read: %s", type(e).__name__)
        return None


async def alert(where: str) -> dict:
    """ONE email to the founder that the model's credit is exhausted — at most once an hour (per process). Awaited by the caller."""
    now = time.time()
    if now - _LAST.get("at", 0) < ALERT_EVERY_S:
        return {"sent": False, "why": "already told within the hour"}
    _LAST["at"] = now
    to = await _founder_address()
    if not to:
        log.error("[model_health] ANTHROPIC CREDIT EXHAUSTED (%s) — no founder address to tell", where)
        return {"sent": False, "why": "no founder address"}
    at = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    msg = {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": to,
           "subject": "Sasha is down — the Anthropic API credit is exhausted",
           "text": "\n".join([
               f"At {at} Sasha's model calls started failing: the Anthropic account behind her key has run out of credit.",
               f"Where it was seen: {where}. Key fingerprint (sha256): {key_print()} — the key itself is never sent.",
               "", "Everyone on /s2, /next and WhatsApp is being told plainly that she can't answer right now; nothing is booked or sent.",
               "", "To fix: top up the account at console.anthropic.com → Plans & Billing (or set a funded key on Railway).",
               "Deploys will fail at the gate's first check until then.", "", "— Sasha's health check"])}
    try:
        if SEND is not None:
            r = await SEND(msg)
        else:
            from booking_signer import live_events as LE
            r = await LE.send_email(msg)
    except Exception as e:
        r = {"sent": False, "why": type(e).__name__}
    log.error("[model_health] ANTHROPIC CREDIT EXHAUSTED (%s) — founder told: %s", where, r)
    return r


async def preflight() -> Tuple[bool, str]:
    """The gate's first check: one 1-token call with the key the gate uses. → (ok, what happened)."""
    try:
        import anthropic
        c = anthropic.AsyncAnthropic()
        await c.messages.create(model=os.getenv("SASHA_HEALTH_MODEL", "claude-haiku-4-5-20251001"), max_tokens=1,
                                messages=[{"role": "user", "content": "ok"}])
        return True, "the model answers"
    except Exception as e:
        if is_credit(e):
            return False, f"ANTHROPIC CREDIT EXHAUSTED — key sha256 {key_print()}: top up at console.anthropic.com → Plans & Billing"
        return True, f"the preflight call failed ({type(e).__name__}) — not a credit failure; the suites decide"


__all__ = ["PLAIN", "is_credit", "key_print", "alert", "preflight", "ALERT_EVERY_S"]
