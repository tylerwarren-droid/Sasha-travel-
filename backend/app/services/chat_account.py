"""S-62 step 7 · WHOSE chat is this — a VERIFIED account, or the public demo.

  · `Authorization: Bearer <a Supabase access token>` → the signed-in guest, verified exactly as bookings are
    (booking_signer.identity: ES256 against the project's JWKS, issuer, audience, role, expiry). A bad token is refused
    (401), never quietly turned into the demo;
  · `x-sasha-session: founder` WITH the booking key (only the site's own proxy holds it, after checking the founder's
    session cookie) → the founder's account (Sasha 142);
  · neither → the PUBLIC demo account: its own, empty, shared by anonymous visitors. ⛔ Never the founder's — until
    Sasha 142 it was, and a phone that wasn't signed in was shown his itinerary (CR's finding, 4 Oct 2026).
Sasha 249 · THE resolver (one-truth-spec §1.1): booking_signer.identity.resolve() is a thin wrapper over chat_account(), so
a chat route and a booking route resolve the same request to the same account. `x-sasha-session: demo` names the demo;
any other session word is refused (401). A founder session with FOUNDER_ACCOUNT_ID unset is refused (503) — never the
demo. The ids and the founder decision live in app/services/accounts.py.
A guest's chats, itineraries, offers, trips and payments are theirs alone: every read by id checks the owner, and a
session or itinerary someone else owns answers exactly as one that does not exist.
"""
from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request

from app.services import chat_store
from app.services.accounts import DEMO_ACCOUNT_ID, founder_account, signed_in  # noqa: F401  (signed_in: re-exported)

SESSION_HEADER = "x-sasha-session"


def founder_session(request: Request) -> bool:
    """The founder's session, as the site's proxy vouches for it: the session header AND the booking key, compared in
    constant time. The header alone names nothing; with no key configured, nobody is the founder."""
    if request.headers.get(SESSION_HEADER, "").strip().lower() != "founder":
        return False
    want = os.getenv("SASHA_BOOKING_KEY", "").strip()
    got = request.headers.get("x-sasha-booking-key", "").strip()
    ok = bool(want) and bool(got) and hmac.compare_digest(got.encode(), want.encode())
    if ok:   # Sasha 159 · the founder's address: guests beside him (the demo devices) are never capped
        from booking_signer.guest_accounts import note_founder_ip
        note_founder_ip(request.headers.get("x-sasha-client-ip", "").strip()[:64] or None)
    return ok


async def chat_account(request: Request, anonymous: Optional[str] = DEMO_ACCOUNT_ID) -> Optional[str]:
    """The acting account (_resolve below), its access record warmed (Sasha 254 item 5: the sync checks — is_founder, calls_on,
    real_contact_refusal … — then read a fresh record; a failed read is closed)."""
    acct = await _resolve(request, anonymous)
    if acct:
        from agapi import person_access as PA
        await PA.warm(acct)
    return acct


async def _resolve(request: Request, anonymous: Optional[str] = DEMO_ACCOUNT_ID) -> Optional[str]:
    """Sasha 249 · WHO IS ACTING — the one resolver, for chat and booking alike:
      1. `Authorization: Bearer` → the verified account (a bad token is refused, never turned into the demo);
      2. `x-sasha-session: founder` WITH the booking key → FOUNDER_ACCOUNT_ID; unset → 503, never the demo;
      3. `x-sasha-session: demo` → the demo; any other session word → 401;
      4. nobody → `anonymous`: the demo for a chat, None for a booking route (identity.resolve → account_required)."""
    auth = request.headers.get("authorization", "")
    if auth:
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(401, {"ok": False, "rule": "account_token_invalid", "message": "the Authorization header is not a bearer token"})
        from booking_signer.identity import verify_token
        return await verify_token(token.strip())
    session = request.headers.get(SESSION_HEADER, "").strip().lower()
    if session == "founder":
        if not founder_session(request):
            return anonymous   # the header alone (no key, a wrong key) names nobody
        acct = founder_account()
        if acct is None:   # ⛔ Sasha 249 · never the demo: until 249 an unset FOUNDER_ACCOUNT_ID made him 11111111
            raise HTTPException(503, {"ok": False, "rule": "founder_account_not_configured",
                                      "message": "FOUNDER_ACCOUNT_ID is not set on this server, so the founder's session names no account; nothing was done"})
        return acct
    if session == "demo":
        return DEMO_ACCOUNT_ID
    if session:
        raise HTTPException(401, {"ok": False, "rule": "account_session_unknown", "message": f"{SESSION_HEADER} is founder or demo"})
    return anonymous


async def own_session(session_id: Optional[str], account: str) -> Optional[str]:
    """The session id if it is new or this account's own; None if it belongs to someone else."""
    if not session_id:
        return None
    owner = await chat_store.session_owner(session_id)
    return session_id if owner in (None, account) else None


async def own_itinerary(itinerary_id: Optional[str], account: str) -> Optional[dict]:
    """Sasha 249 · a row with no owner recorded belongs to NOBODY (until 249 it counted as 11111111's)."""
    it = await chat_store.get_itinerary(itinerary_id) if itinerary_id else None
    return it if it and it.get("user_id") and it.get("user_id") == account else None


async def own_offer(offer_id: Optional[str], account: str) -> Optional[dict]:
    off = await chat_store.get_offer(offer_id) if offer_id else None
    return off if off and off.get("user_id") and off.get("user_id") == account else None
