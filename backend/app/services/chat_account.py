"""S-62 step 7 · WHOSE chat is this — a VERIFIED account, or the public demo.

  · `Authorization: Bearer <a Supabase access token>` → the signed-in guest, verified exactly as bookings are
    (booking_signer.identity: ES256 against the project's JWKS, issuer, audience, role, expiry). A bad token is refused
    (401), never quietly turned into the demo;
  · no token → the public demo account, as before: the demo pages keep working for anyone, and see only demo chats.
A guest's chats, itineraries, offers, trips and payments are theirs alone: every read by id checks the owner, and a
session or itinerary someone else owns answers exactly as one that does not exist.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request

from app.services import chat_store


async def chat_account(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth:
        return chat_store.DEMO_USER_ID
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
