"""S-62 step 7 · WHOSE chat is this — a VERIFIED account, or the public demo.

  · `Authorization: Bearer <a Supabase access token>` → the signed-in guest, verified exactly as bookings are
    (booking_signer.identity: ES256 against the project's JWKS, issuer, audience, role, expiry). A bad token is refused
    (401), never quietly turned into the demo;
  · `x-sasha-session: founder` WITH the booking key (only the site's own proxy holds it, after checking the founder's
    session cookie) → the founder's account (Sasha 142);
  · neither → the PUBLIC demo account: its own, empty, shared by anonymous visitors. ⛔ Never the founder's — until
    Sasha 142 it was, and a phone that wasn't signed in was shown his itinerary (CR's finding, 4 Oct 2026).
A guest's chats, itineraries, offers, trips and payments are theirs alone: every read by id checks the owner, and a
session or itinerary someone else owns answers exactly as one that does not exist.
"""
from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request

from app.services import chat_store

#: Sasha 142 · the anonymous visitor's account: nobody's, and empty. Never chat_store.DEMO_USER_ID (the founder's own).
PUBLIC_DEMO_ID = "00000000-0000-4000-8000-0000000d3e00"


def founder_session(request: Request) -> bool:
    """The founder's session, as the site's proxy vouches for it: the session header AND the booking key, compared in
    constant time. The header alone names nothing; with no key configured, nobody is the founder."""
    if request.headers.get("x-sasha-session", "").strip().lower() != "founder":
        return False
    want = os.getenv("SASHA_BOOKING_KEY", "").strip()
    got = request.headers.get("x-sasha-booking-key", "").strip()
    ok = bool(want) and bool(got) and hmac.compare_digest(got.encode(), want.encode())
    if ok:   # Sasha 159 · the founder's address: guests beside him (the demo devices) are never capped
        from booking_signer.guest_accounts import note_founder_ip
        note_founder_ip(request.headers.get("x-sasha-client-ip", "").strip()[:64] or None)
    return ok


def signed_in(account: Optional[str]) -> bool:
    """A real account (a verified guest, or the founder): the products and anything personal may act on it."""
    return bool(account) and account != PUBLIC_DEMO_ID


async def chat_account(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth:
        if founder_session(request):
            from booking_signer.identity import founder_account
            return founder_account()
        return PUBLIC_DEMO_ID
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, {"ok": False, "rule": "account_token_invalid", "message": "the Authorization header is not a bearer token"})
    from booking_signer.identity import verify_token
    return await verify_token(token.strip())


async def own_session(session_id: Optional[str], account: str) -> Optional[str]:
    """The session id if it is new or this account's own; None if it belongs to someone else."""
    if not session_id:
        return None
    owner = await chat_store.session_owner(session_id)
    return session_id if owner in (None, account) else None


async def own_itinerary(itinerary_id: Optional[str], account: str) -> Optional[dict]:
    it = await chat_store.get_itinerary(itinerary_id) if itinerary_id else None
    return it if it and (it.get("user_id") or chat_store.DEMO_USER_ID) == account else None   # no owner recorded = the demo's


async def own_offer(offer_id: Optional[str], account: str) -> Optional[dict]:
    off = await chat_store.get_offer(offer_id) if offer_id else None
    return off if off and (off.get("user_id") or chat_store.DEMO_USER_ID) == account else None
