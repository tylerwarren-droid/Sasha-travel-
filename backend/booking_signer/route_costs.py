"""Sasha 131 · WHAT EACH ROUTE COST, AND WHAT IT GOT — per booking, and the cost per CONFIRMED booking (the founder's ops view).

Every number says where it came from:
  · a call    → Bland's OWN price for that call (bland_details.price, USD), never estimated;
  · an email, a one-tap WhatsApp page, a form → the rate SETTING for that route (SASHA_COST_EMAIL_EUR,
    SASHA_COST_WHATSAPP_EUR, SASHA_COST_FORM_EUR), labelled "setting"; when a setting isn't set, the cost is
    unknown and said so — never a guessed zero.
The outcome is the booking's own status. Read from records that already exist (booking_forms / _emails / _links / _calls,
trip_items); nothing new is written.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from fastapi import APIRouter, Request

router = APIRouter(prefix="/ops", tags=["booking-ops"])
CONFIRMED = ("confirmed", "guest_booked")
RATE_ENV = {"email": "SASHA_COST_EMAIL_EUR", "one_tap": "SASHA_COST_WHATSAPP_EUR", "form": "SASHA_COST_FORM_EUR"}


def rate(route: str) -> Optional[float]:
    v = os.getenv(RATE_ENV.get(route, ""), "").strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


def usd_eur() -> Optional[float]:
    v = os.getenv("SASHA_USD_EUR", "").strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


def booking_cost(b: dict) -> dict:
    """b = {id, venue, status, forms, emails, links, calls: [price_usd|None, …]} → its routes, each with its cost and source."""
    routes: List[dict] = []
    for route, n in (("form", b.get("forms") or 0), ("email", b.get("emails") or 0), ("one_tap", b.get("links") or 0)):
        if n:
            r = rate(route)
            routes.append({"route": route, "count": n, "eur": round(r * n, 4) if r is not None else None,
                           "source": f"setting {RATE_ENV[route]}" if r is not None else f"unknown — {RATE_ENV[route]} not set"})
    calls = b.get("calls") or []
    if calls:
        known = [p for p in calls if p is not None]
        usd = round(sum(known), 4)
        fx = usd_eur()
        routes.append({"route": "call", "count": len(calls), "usd": usd, "eur": round(usd * fx, 4) if fx is not None else None,
                       "source": "Bland's own price per call" + ("" if len(known) == len(calls) else f" ({len(calls) - len(known)} without one yet)")})
    eur_known = all(r.get("eur") is not None for r in routes)
    return {"id": b["id"], "venue": b.get("venue"), "status": b.get("status"), "confirmed": b.get("status") in CONFIRMED,
            "routes": routes, "eur": round(sum(r["eur"] for r in routes), 4) if routes and eur_known else (0.0 if not routes else None)}


def summary(rows: List[dict]) -> dict:
    """Cost per confirmed booking: all spend (confirmed or not) ÷ confirmed bookings — the honest denominator."""
    per = [booking_cost(b) for b in rows]
    confirmed = sum(1 for p in per if p["confirmed"])
    unknown = sum(1 for p in per if p["eur"] is None)
    total = round(sum(p["eur"] for p in per if p["eur"] is not None), 4)
    by_route: Dict[str, dict] = {}
    for p in per:
        for r in p["routes"]:
            x = by_route.setdefault(r["route"], {"count": 0, "eur": 0.0, "confirmed_bookings": 0, "usd": 0.0})
            x["count"] += r["count"]
            x["eur"] = None if (x["eur"] is None or r["eur"] is None) else round(x["eur"] + r["eur"], 4)   # unknown stays unknown
            x["usd"] = round(x["usd"] + (r.get("usd") or 0), 4)
            x["confirmed_bookings"] += 1 if p["confirmed"] else 0
    # an unknown cost is never counted as zero: with any unknown, the totals are not stated (the parts that are known are)
    return {"bookings": len(per), "confirmed": confirmed, "eur_total": total if not unknown else None, "eur_known_part": total,
            "eur_per_confirmed": round(total / confirmed, 4) if confirmed and not unknown else None,
            "incomplete": unknown, "note": (f"{unknown} booking(s) have a route whose cost isn't known (a rate setting not set, or no "
                                            f"EUR rate for Bland's USD) — the totals leave them out" if unknown else None),
            "by_route": by_route, "rows": per}


async def _rows(limit: int = 500) -> List[dict]:
    from . import ladder_routes as LR
    q = ("select t.id, t.provider_name as venue, t.status, "
         "(select count(*) from booking_forms f where f.trip_item_id = t.id and f.sent_at is not null) forms, "
         "(select count(*) from booking_emails e where e.trip_item_id = t.id and e.sent_at is not null) emails, "
         "(select count(*) from booking_links l where l.trip_item_id = t.id) links, "
         "(select coalesce(array_agg((c.bland_details->>'price')::numeric), '{}') from booking_calls c "
         " where c.trip_item_id = t.id and c.bland_call_id is not null) calls "
         "from trip_items t where exists (select 1 from booking_forms f where f.trip_item_id = t.id and f.sent_at is not null) "
         "or exists (select 1 from booking_emails e where e.trip_item_id = t.id and e.sent_at is not null) "
         "or exists (select 1 from booking_links l where l.trip_item_id = t.id) "
         "or exists (select 1 from booking_calls c where c.trip_item_id = t.id and c.bland_call_id is not null) "
         "order by t.created_at desc limit $1")
    recs = await LR.LADDER_STORE._run(lambda c: c.fetch(q, limit))
    return [{"id": str(r["id"]), "venue": r["venue"], "status": r["status"], "forms": r["forms"], "emails": r["emails"], "links": r["links"],
             "calls": [float(p) if p is not None else None for p in (r["calls"] or [])]} for r in recs]


@router.get("/route-costs")
async def route_costs(request: Request):
    from .ops import founder_only
    from .store import StorageUnavailable
    no = founder_only(request)
    if no:
        return no
    try:
        rows = await _rows()
    except StorageUnavailable as e:
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": False, "rule": e.rule, "message": e.detail}, status_code=503)
    out = summary(rows)
    out["rows"] = out["rows"][:100]
    return {"ok": True, **out}


__all__ = ["router", "booking_cost", "summary", "rate"]
