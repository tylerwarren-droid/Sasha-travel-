"""Sasha 153 · NO SIGN-IN WALL: every new visitor gets an AUTOMATIC PRIVATE GUEST ACCOUNT — on the web (one per browser,
kept in its Supabase session cookie) and on WhatsApp (one per number). It is a real account (auth.users), so everything
already scoped to an account — searches, cards, bookings, the itinerary, receipts — is theirs alone, never another's.

  · created server side with the Auth admin API (sign-ups stay closed to the public), with an address on our own domain
    that receives nothing; its random password is used ONCE to open the first session and never kept;
  · "Keep this across devices: add your email" is offered AFTER a booking (the web), never before;
  · what a guest may do is the founder's rule (Sasha 153): search, cards, bookings at OUR test venues, TEST payments, their
    own itinerary; a REAL venue is contacted (form, email, call) only for the founder's account — `real_contact_refusal`;
  · abuse: a cap per address per hour and per day overall (SASHA_GUESTS_PER_IP_HOUR, SASHA_GUESTS_PER_DAY).
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
import uuid
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("booking_signer.guest_accounts")
router = APIRouter(tags=["booking-guests"])

GUEST_DOMAIN = "guests.kanoe.ai"   # ours; no mailbox: nothing is ever sent to it
_BY_IP: Dict[str, Deque[float]] = {}
_DAY: Deque[float] = deque()


def on() -> bool:
    return os.getenv("SASHA_AUTO_GUESTS", "1") == "1"


def _cap(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, "").strip() or default))
    except ValueError:
        return default


def allowed(ip: Optional[str], now: Optional[float] = None) -> Optional[str]:
    """None when a new guest may be made now; else why not."""
    now = now or time.time()
    while _DAY and now - _DAY[0] > 86400:
        _DAY.popleft()
    if len(_DAY) >= _cap("SASHA_GUESTS_PER_DAY", 500):
        return "the daily number of new guests is reached"
    if ip:
        q = _BY_IP.setdefault(hashlib.sha256(ip.encode()).hexdigest()[:16], deque())
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= _cap("SASHA_GUESTS_PER_IP_HOUR", 5):
            return "too many new guests from this address this hour"
    return None


def _count(ip: Optional[str], now: Optional[float] = None) -> None:
    now = now or time.time()
    _DAY.append(now)
    if ip:
        _BY_IP.setdefault(hashlib.sha256(ip.encode()).hexdigest()[:16], deque()).append(now)


async def create_guest(origin: str, ip: Optional[str] = None) -> Tuple[Optional[dict], Optional[str]]:
    """→ ({account_id, email, password}, None) or (None, why). The password is returned only to open the first session."""
    from . import ops
    why = allowed(ip)
    if why:
        return None, why
    email = f"guest-{uuid.uuid4().hex[:20]}@{GUEST_DOMAIN}"
    password = secrets.token_urlsafe(32)
    s, u = await ops.ADMIN("POST", "/admin/users", {"email": email, "password": password, "email_confirm": True,
                                                     "app_metadata": {"kanoe_guest": True, "origin": origin}})
    if s not in (200, 201) or not (u or {}).get("id"):
        log.error("[guests] a guest account could not be created: HTTP %s %s", s, str(u)[:200])
        return None, "a guest account could not be created right now"
    _count(ip)
    log.info("[guests] a new guest account (%s)", origin)
    return {"account_id": u["id"], "email": email, "password": password}, None


async def first_session(email: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    """The guest's first session (access + refresh token), opened with the one-time password."""
    from .http_pool import request
    url = os.getenv("SASHA_SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        return None, "Supabase is not configured on this server"
    r = await request("POST", f"{url}/auth/v1/token?grant_type=password", timeout=20.0,
                      headers={"apikey": key, "content-type": "application/json"}, json={"email": email, "password": password})
    try:
        j = r.json()
    except ValueError:
        j = {}
    if r.status_code != 200 or not j.get("access_token"):
        log.error("[guests] the first session could not be opened: HTTP %s", r.status_code)
        return None, "the guest session could not be opened"
    return {k: j.get(k) for k in ("access_token", "refresh_token", "expires_in", "expires_at", "token_type")}, None


@router.post("/guest/start")
async def guest_start(request: Request):
    """KEYED (the site's own server route calls it, with the booking key): a new private guest account and its first
    session, for a browser with none. Body: {"ip": the visitor's address, for the cap}."""
    if not on():
        return JSONResponse({"ok": False, "rule": "guests_off", "message": "automatic guest accounts are off"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    acct, why = await create_guest("web", str((body or {}).get("ip") or "")[:64] or None)
    if acct is None:
        return JSONResponse({"ok": False, "rule": "guest_not_created", "message": why}, status_code=429 if why and "many" in why else 503)
    sess, why = await first_session(acct["email"], acct["password"])
    if sess is None:
        return JSONResponse({"ok": False, "rule": "guest_session_failed", "message": why}, status_code=503)
    return {"ok": True, "account_id": acct["account_id"], **sess}


# ── what a guest may do: a REAL venue is contacted only for the founder (Sasha 153) ───────────────────────────────

def founder(account: Optional[str]) -> bool:
    from .identity import founder_account
    return bool(account) and account == founder_account()


def extra_accounts() -> set:
    return {a.strip().lower() for a in os.getenv("SASHA_REAL_CONTACT_ACCOUNTS", "").split(",") if a.strip()}


def real_contact_refusal(account: Optional[str], to_test_venue: bool) -> Optional[JSONResponse]:
    """None when this account may contact this venue; else the refusal, said plainly. Our test venues: anyone. A real
    venue: the founder's account (and any listed in SASHA_REAL_CONTACT_ACCOUNTS) — until the founder says otherwise."""
    if to_test_venue or founder(account) or (account or "").lower() in extra_accounts():
        return None
    return JSONResponse({"ok": False, "rule": "real_venue_not_open",
                         "message": "Sasha books real venues for invited accounts only for now. Nothing was sent. Searching and "
                                    "test bookings work for everyone."}, status_code=403)


INBOUND_CONSENT = ("You wrote to Sasha first on WhatsApp; she answers you here, in this chat. Reply STOP at any time. "
                   "No reminders or other first messages are sent to this number.")
INBOUND_VERSION = "v0"   # the column takes ^v[0-9]+$; v0 = no consent to first messages: no proactive message ever goes to them

__all__ = ["router", "create_guest", "first_session", "real_contact_refusal", "allowed", "on", "INBOUND_CONSENT", "INBOUND_VERSION"]
