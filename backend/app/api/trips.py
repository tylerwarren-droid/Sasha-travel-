"""
Trips API — the guest's real, paid bookings.

This backs the workspace's "Where you've been" list. It reads the `bookings` table, so a trip
only appears here once Stripe actually confirmed the payment. That matters: the list used to
be a hardcoded array in the frontend, which meant it said the same two trips forever and a
booking the guest genuinely made never showed up.
"""

from fastapi import APIRouter

from app.services import chat_store

router = APIRouter(prefix="/api/trips", tags=["trips"])


def _first_city(payload: dict) -> str:
    days = (payload or {}).get("days") or []
    return (days[0] or {}).get("city", "") if days else ""


@router.get("")
async def list_trips():
    """Paid trips for the current guest, newest first."""
    rows = await chat_store.list_booked_trips(chat_store.DEMO_USER_ID)
    trips = []
    for r in rows:
        payload = r.get("payload") or {}
        days = payload.get("days") or []
        trips.append({
            "booking_ref": r.get("booking_ref"),
            "title": r.get("title") or payload.get("title") or "Vietnam trip",
            "paid_at": r.get("paid_at"),
            "amount_usd": r.get("amount_usd"),
            "days": len(days),
            "first_city": _first_city(payload),
        })
    return {"trips": trips}
