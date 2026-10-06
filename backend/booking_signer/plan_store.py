"""Sasha 165 · THE BRIDGE: the itinerary builder's plan and the bookings become ONE itinerary, on the ACCOUNT.

Before: a plan lived only in the chat's SQLite (sasha_chats.db, keyed by the browser's session, no Railway volume — wiped by
every redeploy); bookings lived in Postgres (trips / trip_items, keyed by account). Now:

  · save()   — a freshly built plan is ALSO a trip on the account (Postgres `trips`): its title, its dates (from the guest's own
               words, "Vietnam 12–20 Nov"), its cities, and the plan itself (in `destinations`, as {"cities", "plan"} — additive;
               no migration). The builder is untouched: this runs after it, and its failure never touches the chat.
  · merged() — the latest plan with every booking whose date falls in it slotted into its day (by date, and its time of day),
               with its status in words; a matching placeholder activity ("Dinner…", "Spa…") is marked as replaced by it.
  · text()   — the same thing, compact, for WhatsApp and the voice.
Bookings outside any plan stay exactly as they were.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("booking_signer.plan_store")

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_RANGE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:[-–—]|to|until|till)\s*(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]{3})[a-z]*\b", re.I)
_FROM = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]{3})[a-z]*\b", re.I)


def _jsonable(x: Any) -> Any:
    """The plan as plain JSON values — handed to the driver as an OBJECT (its jsonb codec encodes it; a pre-encoded string
    would be stored as a JSON string, which `destinations ? 'plan'` never matches)."""
    return json.loads(json.dumps(x, default=str))


def dates_of(message: str, days: int, today: date) -> tuple:
    """(start, end) from "12–20 Nov" / "from 12 to 20 November" / "12 Nov" (+ the plan's length); (None, None) when unsaid."""
    m = _RANGE.search(message or "")
    if m and m[3].lower()[:3] in _MONTHS:
        mon = _MONTHS[m[3].lower()[:3]]
        y = today.year + (1 if mon < today.month else 0)
        try:
            return date(y, mon, int(m[1])), date(y, mon, int(m[2]))
        except ValueError:
            return None, None
    m = _FROM.search(message or "")
    if m and m[2].lower()[:3] in _MONTHS:
        mon = _MONTHS[m[2].lower()[:3]]
        y = today.year + (1 if mon < today.month else 0)
        try:
            a = date(y, mon, int(m[1]))
            return a, a + timedelta(days=max(0, days - 1))
        except ValueError:
            return None, None
    return None, None


STORE_RUN = None   # tests replace it; otherwise the ladder store's Postgres runner


def _run():
    if STORE_RUN is not None:
        return STORE_RUN
    from . import ladder_routes as LR
    return getattr(LR.LADDER_STORE, "_run", None)


async def save(account: Optional[str], itinerary: dict, message: str, now: datetime) -> Optional[str]:
    """The plan as a trip on the account → the trip's id, or None (no account, no store). Never raises."""
    run = _run()
    if not account or run is None or not (itinerary or {}).get("days"):
        return None
    try:
        days = itinerary["days"]
        start, end = dates_of(message, len(days), now.date())
        cities = list(dict.fromkeys(d.get("city") for d in days if d.get("city")))
        dest = {"cities": cities, "plan": itinerary, "kanoe": "plan/1"}
        title = (itinerary.get("title") or "Your trip")[:200]

        async def fn(conn):
            # a revision of the same plan (made within 6 h, sharing its title or a city) updates it: one trip, not one per edit
            prev = await conn.fetchrow("select id, title, destinations from trips where owner_id = $1 and destinations ? 'plan' "
                                       "and status in ('draft','active') and created_at > now() - interval '6 hours' "
                                       "order by created_at desc limit 1", uuid.UUID(account))
            if prev:
                pd = prev["destinations"]
                pd = json.loads(pd) if isinstance(pd, str) else pd
                if prev["title"] == title or set(pd.get("cities") or []) & set(cities):
                    await conn.execute("update trips set title = $2, destinations = $3::jsonb, depart_date = coalesce($4, depart_date), "
                                       "return_date = coalesce($5, return_date), updated_at = now() where id = $1",
                                       prev["id"], title, _jsonable(dest), start, end)
                    return prev["id"]
            return await conn.fetchval(
                "insert into trips (owner_id, title, status, destinations, depart_date, return_date) values ($1,$2,'draft',$3::jsonb,$4,$5) returning id",
                uuid.UUID(account), title, _jsonable(dest), start, end)
        tid = await run(fn)
        log.info("[plan_store] plan saved as trip %s (%s → %s)", tid, start, end)
        return str(tid)
    except Exception as e:
        log.warning("[plan_store] the plan was not saved on the account: %s: %s", type(e).__name__, e)
        return None


async def latest(account: Optional[str]) -> Optional[dict]:
    run = _run()
    if not account or run is None:
        return None

    async def fn(conn):
        return await conn.fetchrow("select id, title, destinations, depart_date, return_date, created_at from trips where owner_id = $1 "
                                   "and destinations ? 'plan' and status in ('draft','active') order by created_at desc limit 1",
                                   uuid.UUID(account))
    try:
        r = await run(fn)
    except Exception as e:
        log.info("[plan_store] no plan read: %s", type(e).__name__)
        return None
    if not r:
        return None
    d = r["destinations"]
    d = json.loads(d) if isinstance(d, str) else d
    return {"trip_id": str(r["id"]), "title": r["title"], "start": r["depart_date"], "end": r["return_date"], "plan": d.get("plan") or {},
            "cities": d.get("cities") or []}


async def _edit(account: str, trip_id: Optional[str], change) -> Any:
    """Read the plan's trip, change its plan in Python, write it back — one transaction, the owner checked in the SQL."""
    run = _run()
    if not account or run is None:
        return None

    async def fn(conn):
        async with conn.transaction():
            q = ("select id, destinations from trips where owner_id = $1 and destinations ? 'plan' and status in ('draft','active') "
                 + ("and id = $2 " if trip_id else "") + "order by created_at desc limit 1 for update")
            r = await conn.fetchrow(q, *([uuid.UUID(account), uuid.UUID(trip_id)] if trip_id else [uuid.UUID(account)]))
            if not r:
                return None
            d = r["destinations"]
            d = json.loads(d) if isinstance(d, str) else d
            res = change(d.get("plan") or {})
            await conn.execute("update trips set destinations = $2::jsonb, updated_at = now() where id = $1", r["id"], _jsonable(d))
            return res
    try:
        return await run(fn)
    except Exception as e:
        log.warning("[plan_store] the plan was not changed: %s: %s", type(e).__name__, e)
        return None


async def add_place(account: str, trip_id: str, day: Optional[int], activity: dict) -> bool:
    """Sasha 167 · a place picked on WhatsApp, on its day of the plan (a plan item — nothing booked)."""
    def change(plan):
        days = plan.get("days") or []
        d = next((x for x in days if x.get("day") == day), days[0] if days else None)
        if d is None:
            return False
        acts = d.setdefault("activities", [])
        if not any(a.get("place_id") and a.get("place_id") == activity.get("place_id") for a in acts):
            acts.insert(0, activity)
        return True
    return bool(await _edit(account, trip_id, change))


async def clear_added(account: str, dry: bool = False) -> int:
    """Sasha 167 · "reset the demo": the places added on WhatsApp leave the latest plan (count only when dry)."""
    if dry:
        p = await latest(account)
        return sum(1 for d in ((p or {}).get("plan") or {}).get("days") or [] for a in d.get("activities") or [] if a.get("added"))

    def change(plan):
        n = 0
        for d in plan.get("days") or []:
            keep = [a for a in d.get("activities") or [] if not a.get("added")]
            n += len(d.get("activities") or []) - len(keep)
            d["activities"] = keep
        return n
    return int(await _edit(account, None, change) or 0)


_PART = (("Morning", 0, 12), ("Afternoon", 12, 18), ("Evening", 18, 24))
_MATCH = {"restaurant": r"dinner|lunch|restaurant|eat|food|meal|street.?food|tasting",
          "beauty": r"spa|massage|wellness|tattoo|salon|nail|hair",
          "experience": r"tour|class|cooking|cruise|visit|excursion", "other": r"tattoo|class|tour|visit"}


def _part(hhmm: Optional[str]) -> str:
    try:
        h = int((hhmm or "")[:2])
    except ValueError:
        return "Evening"
    return next((p for p, a, b in _PART if a <= h < b), "Evening")


def merge(p: dict, bookings: List[dict]) -> dict:
    """The plan's days with the bookings that fall on them (by date), each with its status in words; a placeholder activity
    of the same kind and time of day is marked `replaced_by`. Pure: no I/O."""
    plan = json.loads(json.dumps(p.get("plan") or {}, default=str))
    start = p.get("start")
    if isinstance(start, str):
        start = date.fromisoformat(start)
    days = plan.get("days") or []
    for i, d in enumerate(days):
        # CR 35 · a day may carry its OWN date (RelocateMe's sparse deadlines); else the start + its place in the plan
        d["date"] = str(d.get("date") or "")[:10] or ((start + timedelta(days=i)).isoformat() if start else None)
        d.setdefault("bookings", [])
    by_date = {d["date"]: d for d in days if d.get("date")}
    for b in bookings:
        day = by_date.get(b.get("date") or "")
        if day is None or b.get("status") in ("cancelled",):
            continue
        part = _part(b.get("time"))
        from .wa_brain import is_test
        entry = {"id": b.get("id"), "venue": b.get("venue"), "time": b.get("time"), "part": part, "status": b.get("status"),
                 "status_words": b.get("status_words"), "what": b.get("what"), "type": b.get("type"),
                 "test": is_test(b)}   # Sasha 167 · kept for the demo, labelled TEST; "reset the demo" clears them
        rx = _MATCH.get(b.get("category") or b.get("type") or "", r"$^")
        for a in day.get("activities") or []:
            if not a.get("replaced_by") and (a.get("time") or "") == part and re.search(rx, f"{a.get('name','')} {a.get('blurb','')}", re.I):
                a["replaced_by"] = b.get("venue")
                entry["replaces"] = a.get("name")
                break
        day["bookings"].append(entry)
    plan["trip_id"], plan["title"] = p.get("trip_id"), p.get("title") or plan.get("title")
    plan["start"], plan["end"] = (str(p.get("start")) if p.get("start") else None), (str(p.get("end")) if p.get("end") else None)
    return plan


_SHORT = {"requested": "Requested", "attempting": "Requested", "pending": "Not sent yet", "confirmed": "Confirmed ✅", "guest_booked": "Booked by you ✅",
          "declined": "Declined", "quoted": "Quoted — read their reply", "proposed": "They offered another time", "unclear": "Read their reply",
          "link_sent": "Link sent — not booked yet", "waitlisted": "Waiting list"}


def short_status(b: dict) -> str:
    """The status in a few words for the compact view (the full words, with their quote, are on the web and the receipt)."""
    words = _SHORT.get(b.get("status") or "", b.get("status_words") or b.get("status") or "")
    ref = re.search(r"their ref ([A-Z0-9-]+)", b.get("status_words") or "")
    return words + (f" · ref {ref[1]}" if ref and b.get("status") == "confirmed" else "")


def text(plan: dict) -> List[str]:
    """Compact, for WhatsApp and the voice: one block per day — the place, the bookings with their status, what's planned."""
    from .sentences import day_words
    out = [f"🗺 {plan.get('title') or 'Your trip'}" + (f" — {day_words(plan['start'])} to {day_words(plan['end'])}" if plan.get("start") and plan.get("end") else "")]
    for d in plan.get("days") or []:
        head = f"Day {d.get('day')}{' · ' + day_words(d['date']) if d.get('date') else ''} — {d.get('city') or ''}"
        lines = [head]
        for b in sorted(d.get("bookings") or [], key=lambda x: x.get("time") or ""):
            lines.append(f"  • {b.get('time') or ''} {'TEST · ' if b.get('test') else ''}{b.get('venue')}: {short_status(b)}".replace("  •  ", "  • "))
        acts = [a for a in d.get("activities") or [] if not a.get("replaced_by")]
        for a in [a for a in acts if a.get("added")]:   # Sasha 167 · a place picked on WhatsApp: on its day, not booked
            lines.append(f"  📍 {a.get('time')}: {a.get('name')} (not booked yet)")
        for a in [a for a in acts if not a.get("added")][:2]:
            lines.append(f"  · {a.get('time')}: {a.get('name')}")
        out.append("\n".join(lines))
    return out


__all__ = ["save", "latest", "merge", "text", "dates_of", "add_place", "clear_added"]
