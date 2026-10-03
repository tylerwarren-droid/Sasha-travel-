"""Sasha 135 · HOTEL "RESERVE" AS A TEST BOOKING — the same steps as a flight in Duffel test mode, until a real provider is on.

  cards → pick → read-back → yes → one touch on Stripe's TEST page → a test booking with a TEST- reference → the itinerary
  and the calendar.

Every screen and message says "Test booking: no hotel contacted" — never "confirmed". No hotel is contacted, nothing is
reserved, nothing is charged. The price is a TEST price (SASHA_TEST_HOTEL_EUR per night, default 120), said to be a
placeholder, never the hotel's rate. "Request the room from the hotel" stays a separate, real option.

When Duffel Stays (asked of Duffel, 3 Oct) or RateHawk credentials arrive, `provider()` says so and this same flow books
for real; until then it answers "test".
"""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

LABEL = "Test booking: no hotel contacted"
MARK = "(TEST booking — no hotel contacted)"
router = APIRouter(prefix="/travel", tags=["travel"])
_BOOKED: Dict[str, dict] = {}


def provider() -> str:
    """'test' until a real hotel provider is switched on (then the flow books for real — not built until one is)."""
    return "test"


def rate_eur() -> float:
    try:
        return max(1.0, float(os.getenv("SASHA_TEST_HOTEL_EUR", "") or 120))
    except ValueError:
        return 120.0


def is_test(name_or_ref: str) -> bool:
    s = name_or_ref or ""
    return s.startswith("TEST-") or "(TEST booking" in s


def quote(hotel: str, city: str, checkin: str, nights: int, party: int) -> Dict[str, Any]:
    eur = round(rate_eur() * nights, 2)
    out = date.fromisoformat(checkin) + timedelta(days=nights)
    lines = [f"⚠ {LABEL} — nothing is reserved at {hotel}, and nothing is charged.",
             f"{hotel}, {city}: check-in {checkin}, check-out {out.isoformat()} — {nights} night{'s' if nights != 1 else ''}, "
             f"{party} {'person' if party == 1 else 'people'}.",
             f"Test price €{eur:.2f} ({nights} × €{rate_eur():.0f}) — a placeholder, not the hotel's rate.",
             "Payment: one touch on Stripe's TEST page — Apple Pay or your phone's saved card; nothing is charged. I never see your card.",
             "It goes in your itinerary and calendar marked as a TEST booking, with a TEST- reference."]
    return {"lines": lines, "sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest(), "eur": eur, "checkout": out.isoformat()}


def new_ref() -> str:
    return "TEST-" + secrets.token_hex(3).upper()


async def _record(account: str, hotel: str, city: str, tz: str, checkin: str, nights: int, party: int, ref: str) -> Optional[str]:
    """The stay on the guest's list: type hotel, its TEST reference and its name say TEST; the calendar mirrors it."""
    from . import ladder_routes as LR
    from .store import BOOKINGS_TRIP_TITLE
    if not hasattr(LR.LADDER_STORE, "_run"):
        return None
    dt = datetime.fromisoformat(f"{checkin}T15:00").replace(tzinfo=ZoneInfo(tz or "Europe/Madrid"))

    async def go(conn):
        async with conn.transaction():
            a = uuid.UUID(account)
            trip = await conn.fetchval("select id from trips where owner_id = $1 and title = $2 limit 1", a, BOOKINGS_TRIP_TITLE)
            if trip is None:
                trip = await conn.fetchval("insert into trips (owner_id, title) values ($1,$2) returning id", a, BOOKINGS_TRIP_TITLE)
            tid = await conn.fetchval("insert into trip_items (trip_id, type, status, provider_name, date_time, duration_minutes, local_timezone, "
                                      "location_name, party_size) values ($1,'hotel','requested',$2,$3,$4,$5,$6,$7) returning id",
                                      trip, f"{hotel} {MARK}", dt, nights * 1440 - 240, tz or "Europe/Madrid", city, party)
            # 'confirmed' only so the calendar mirrors it; every surface reads the TEST- reference and the name, never "confirmed"
            await conn.execute("update trip_items set status = 'confirmed', booking_reference = $2, updated_at = now() where id = $1", tid, ref)
            return str(tid)
    return await LR.LADDER_STORE._run(go)


RECORD = _record   # tests replace it


def tz_of(country: Optional[str]) -> str:
    from . import venue_read as V
    return (V.COUNTRIES.get(country or "") or (None, None, None, "Europe/Madrid"))[3]


# ── the web's "Reserve (TEST)" on a hotel card ─────────────────────────────────────────────────────────────────────────

def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def _req(body: Any) -> Optional[dict]:
    try:
        hotel = str(body.get("hotel") or "").strip()[:120]
        city = str(body.get("city") or "").strip()[:80]
        checkin = date.fromisoformat(str(body.get("checkin"))).isoformat()
        nights, party = int(body.get("nights") or 1), int(body.get("party") or 2)
    except (ValueError, TypeError, AttributeError):
        return None
    if not hotel or not 1 <= nights <= 30 or not 1 <= party <= 10:
        return None
    return {"hotel": hotel, "city": city, "checkin": checkin, "nights": nights, "party": party, "country": body.get("country")}


@router.post("/hotel/prepare")
async def prepare(request: Request):
    r = _req(await request.json())
    if r is None:
        return _refuse(422, "hotel_malformed", "send {hotel, city, checkin (YYYY-MM-DD), nights 1–30, party 1–10}")
    q = quote(r["hotel"], r["city"], r["checkin"], r["nights"], r["party"])
    return {"ok": True, "label": LABEL, "read_back": {"lines": q["lines"], "sha256": q["sha256"]}, "eur": q["eur"]}


@router.post("/hotel/pay")
async def pay(request: Request):
    from . import test_deposit as TD, yes as YS
    body = await request.json()
    r = _req(body)
    if r is None:
        return _refuse(422, "hotel_malformed", "send the same hotel, city, checkin, nights and party")
    if not YS.approval_ok(body.get("approval")):
        return _refuse(422, "approval_void", YS.APPROVAL_VOID)
    q = quote(r["hotel"], r["city"], r["checkin"], r["nights"], r["party"])
    if body.get("read_back_sha256") != q["sha256"]:
        return _refuse(422, "approval_void", "the yes was to different words — prepare it again")
    got = await TD.checkout(f"{q['eur']:.2f}", "EUR", f"{LABEL} — {r['hotel']} {r['checkin']} ({r['nights']} nights)", q["sha256"][:16])
    if "why" in got:
        return _refuse(422, "test_payment_unavailable", got["why"])
    return {"ok": True, "url": got["url"], "session_id": got["id"]}


@router.post("/hotel/status")
async def status(request: Request):
    from . import test_deposit as TD
    from .account import account_for
    body = await request.json()
    sid = str(body.get("session_id") or "")
    if sid in _BOOKED:
        return {"ok": True, "status": "booked", **_BOOKED[sid]}
    r = _req(body)
    if r is None:
        return _refuse(422, "hotel_malformed", "send the same hotel details and the session_id")
    if not await TD.session_paid(sid):
        return {"ok": True, "status": "awaiting_payment"}
    ref = new_ref()
    await RECORD(account_for(request), r["hotel"], r["city"], tz_of(r.get("country")), r["checkin"], r["nights"], r["party"], ref)
    _BOOKED[sid] = {"reference": ref, "say": f"{LABEL}: {r['hotel']}, {r['checkin']}, {r['nights']} night{'s' if r['nights'] != 1 else ''}. "
                                             f"Reference {ref} — in your itinerary and calendar as a TEST booking. Nothing was reserved or charged."}
    TD.note(sid, True, _BOOKED[sid]["say"])
    return {"ok": True, "status": "booked", **_BOOKED[sid]}


__all__ = ["quote", "LABEL", "MARK", "is_test", "new_ref", "RECORD", "router", "provider", "tz_of"]
