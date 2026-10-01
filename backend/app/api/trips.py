"""
Trips API — the guest's real, paid bookings.

This backs the workspace's "Where you've been" list. It reads the `bookings` table, so a trip
only appears here once Stripe actually confirmed the payment. That matters: the list used to
be a hardcoded array in the frontend, which meant it said the same two trips forever and a
booking the guest genuinely made never showed up.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services import chat_store
from app.services.chat_account import chat_account

router = APIRouter(prefix="/api/trips", tags=["trips"])


def _first_city(payload: dict) -> str:
    days = (payload or {}).get("days") or []
    return (days[0] or {}).get("city", "") if days else ""


@router.get("")
async def list_trips(request: Request):
    """Paid trips for the caller — a signed-in guest's own, or the public demo's — newest first (S-62 step 7)."""
    account = await chat_account(request)
    try:
        rows = await chat_store.list_booked_trips(account)
    except chat_store.TripsUnavailable as e:
        # S-45 · a failed read says it failed — the panel shows "couldn't be loaded", never "No trips yet"
        return JSONResponse({"trips": None, "error": "trips_unavailable", "message": str(e)}, status_code=503)
    trips = []
    for r in rows:
        payload = r.get("payload") or {}
        days = payload.get("days") or []
        trips.append({
            "booking_ref": r.get("booking_ref"),
            "title": r.get("title") or payload.get("title") or "Vietnam trip",
            "paid_at": r.get("paid_at"),
            "amount_usd": r.get("amount_usd"),
            # Set when the guest paid with the saved card in-conversation; None = reservation.
            "card_last4": r.get("card_last4"),
            "days": len(days),
            "first_city": _first_city(payload),
        })
    return {"trips": trips}
