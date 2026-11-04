"""Sasha 338 · WHO MAY SIGN IN — the ONE place (Tyler, 4 Nov 11:45: "remove the invite wall — anyone may sign in by email link").

Supabase's own public sign-up stays OFF on sasha-prod, so nobody reaches an account except through this rule. The sign-in page asks
here first (POST /api/booking/sign-up {email}); a well-formed address gets its Supabase user (created if missing, email NOT marked
confirmed — their own link confirms it), then Supabase emails the link as before. The founder's invitation (ops.invite) still exists
to EMAIL someone an invitation; it decides nothing about who may sign in.

WHAT a person may do for real is NOT decided here: AgAPI's person_access record does (agapi/person_access.py). A brand-new person has
no row → CLOSED: test mode (the sandbox, payments TEST), real_venue_sends off, platform_submit off — until Tyler marks them live on
/admin/access. Their daily AI budget is sasha.DAILY_BUDGET["new_turns"] until then.

Abuse: per IP SIGNUPS_PER_IP_HOUR an hour and SIGNUPS_PER_DAY a day in all (per worker; Supabase's own email limits apply after).
The answer never says whether an address already had an account (no enumeration). The address is never logged."""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Request

log = logging.getLogger("booking_signer.sign_up")
router = APIRouter(prefix="/sign-up", tags=["sign-up"])
EMAIL = re.compile(r"[^@\s]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}")
SIGNUPS_PER_IP_HOUR = int(os.getenv("SASHA_SIGNUPS_PER_IP_HOUR", "10"))
SIGNUPS_PER_DAY = int(os.getenv("SASHA_SIGNUPS_PER_DAY", "500"))
_BY_IP: Dict[str, List[float]] = {}
_DAY: List[float] = []


def may_sign_in(email: str) -> bool:
    """THE RULE: anyone with an email address (Tyler, 4 Nov). The invite wall was here; to close it again, this is the one line."""
    return bool(EMAIL.fullmatch((email or "").strip()))


def _allowed(ip: str, now: float) -> Tuple[bool, str]:
    hits = [t for t in _BY_IP.get(ip, []) if now - t < 3600]
    day = [t for t in _DAY if now - t < 86400]
    _DAY[:] = day
    if len(hits) >= SIGNUPS_PER_IP_HOUR:
        _BY_IP[ip] = hits
        return False, "too many sign-ups from here in the last hour — try again later"
    if len(day) >= SIGNUPS_PER_DAY:
        return False, "Sasha has taken all the new sign-ups she can today — try again tomorrow"
    _BY_IP[ip] = hits + [now]
    _DAY.append(now)
    return True, ""


async def open_account(email: str, ip: str = "?", now: float = 0.0) -> Dict[str, Any]:
    """→ {ok: True} once the address may receive its link (its user exists), else {ok: False, why}. Never says if it existed."""
    from . import ops
    email = (email or "").strip().lower()
    if not may_sign_in(email):
        return {"ok": False, "why": "that is not an email address"}
    ok, why = _allowed(ip, now or time.time())
    if not ok:
        return {"ok": False, "why": why}
    s, j = await ops.ADMIN("POST", "/admin/users", {"email": email, "email_confirm": False})
    if s in (200, 201) or (s == 422 and re.search(r"already|registered|exists", str(j), re.I)):
        log.info("[sign-up] an address may sign in (%s)", "new" if s in (200, 201) else "existing")   # never the address
        return {"ok": True}
    log.error("[sign-up] the account wasn't opened: HTTP %s", s)
    return {"ok": False, "why": "Sasha couldn't open your account just now — try again in a minute"}


@router.post("")
async def sign_up(request: Request):
    body = await request.json()
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    return await open_account(str(body.get("email") or ""), ip)


__all__ = ["may_sign_in", "open_account", "router", "SIGNUPS_PER_IP_HOUR", "SIGNUPS_PER_DAY"]
