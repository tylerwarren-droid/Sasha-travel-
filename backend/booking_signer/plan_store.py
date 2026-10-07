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
    # Sasha 191 · MONTH FIRST, as said aloud: "between November 15 and November 27", "Nov 15 to 27", "November 15"
    _MF = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:\s*(?:-|–|to|and|until|till|through)\s*(?:([A-Za-z]{3,9})\.?\s+)?(\d{1,2})(?:st|nd|rd|th)?\b)?")
    mm = next((x for x in _MF.finditer(message or "") if x[1].lower()[:3] in _MONTHS), None)
    if mm:
        mon = _MONTHS[mm[1].lower()[:3]]
        y = today.year + (1 if mon < today.month else 0)
        try:
            a = date(y, mon, int(mm[2]))
            if mm[4]:
                mon2 = _MONTHS.get((mm[3] or mm[1]).lower()[:3], mon)
                b = date(y + (1 if mon2 < mon else 0), mon2, int(mm[4]))
                if b >= a:
                    return a, b
            return a, a + timedelta(days=max(0, days - 1))
        except ValueError:
            pass
    # Sasha 169 · the first DATE, not the first "<number> <word>": "8 days in Vietnam from 12 November" read "8 days" and stopped
    m = next((x for x in _FROM.finditer(message or "") if x[2].lower()[:3] in _MONTHS), None)
    if m:
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
        if not itinerary.get("party"):   # Sasha 169 · how many, as the guest said it ("2 of us") — the trip's bookings are for them
            from .handoff import plain_party
            n = plain_party(message or "")
            if n:
                itinerary = {**itinerary, "party": n}
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
        from . import basket as BK
        if BK.on():   # Sasha 198 R3 · the plan's hotels as suggested stays in the basket (Magellan)
            try:
                await BK.sync_stays(account, str(tid), itinerary.get("days") or [], start, itinerary.get("party"))
            except Exception as e:
                log.error("[plan_store] the stays were not put in the basket: %s: %s", type(e).__name__, e)
        return str(tid)
    except Exception as e:
        log.warning("[plan_store] the plan was not saved on the account: %s: %s", type(e).__name__, e)
        return None


def _names(r, d: dict) -> List[str]:
    words = [w for w in re.findall(r"[A-Za-zÀ-ÿ]{4,}", r["title"] or "") if w.lower() not in ("days", "trip", "your", "plan", "move")]
    return [c for c in (d.get("cities") or []) if c] + words


async def latest(account: Optional[str], hint: Optional[str] = None) -> Optional[dict]:
    """The account's plan: the one the guest's words name (a city or a word of its title, e.g. "Hoi An", "Vietnam"), else the
    one touched most recently. Sasha 169: an account can hold several (a move to Madrid and a Vietnam holiday) — the newest
    CREATED one hijacked "show me my itinerary" while the other was being worked on."""
    run = _run()
    if not account or run is None:
        return None

    async def fn(conn):
        return await conn.fetch("select id, title, destinations, depart_date, return_date, created_at from trips where owner_id = $1 "
                                "and destinations ? 'plan' and status in ('draft','active') order by updated_at desc, created_at desc limit 6",
                                uuid.UUID(account))
    try:
        rows = await run(fn)
    except Exception as e:
        log.info("[plan_store] no plan read: %s", type(e).__name__)
        return None
    if not rows:
        return None
    r = rows[0]
    if hint and len(rows) > 1:
        # Sasha 179 · the DATED plan first when several share the word (an undated "Vietnam" stub took "my Vietnam trip")
        for x in sorted(rows, key=lambda y: y["depart_date"] is None):
            dx = x["destinations"]
            dx = json.loads(dx) if isinstance(dx, str) else dx
            if any(re.search(rf"\b{re.escape(n)}\b", hint, re.I) for n in _names(x, dx or {})):
                r = x
                break
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


async def add_day(account: str, trip_id: str, day: str, city: str) -> bool:
    """Sasha 167 (4) · a date outside the trip, added to it: every day gets its own date (CR 35's merge honours it), the new day
    joins in date order, the days are renumbered, and the trip's dates widen."""
    p = await latest(account)
    if not p or p.get("trip_id") != trip_id:
        return False
    start = p.get("start")
    start = date.fromisoformat(str(start)[:10]) if start else None

    def change(plan):
        days = plan.get("days") or []
        for i, d in enumerate(days):
            d["date"] = str(d.get("date") or "")[:10] or ((start + timedelta(days=i)).isoformat() if start else None)
        if any(d.get("date") == day for d in days):
            return True
        days.append({"day": 0, "date": day, "city": city, "title": f"{city} — added", "activities": []})
        days.sort(key=lambda d: d.get("date") or "9999")
        for i, d in enumerate(days, 1):
            d["day"] = i
        plan["days"] = days
        return True
    ok = await _edit(account, trip_id, change)
    if ok:
        async def widen(conn):
            await conn.execute("update trips set depart_date = least(depart_date, $2::date), return_date = greatest(return_date, $2::date) "
                               "where id = $1 and owner_id = $3", uuid.UUID(trip_id), date.fromisoformat(day), uuid.UUID(account))
        try:
            await _run()(widen)
        except Exception as e:
            log.warning("[plan_store] the trip's dates were not widened: %s: %s", type(e).__name__, e)
    return bool(ok)


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


async def plans(account: Optional[str]) -> List[dict]:
    """Sasha 175 · every trip plan on the account, newest touched first: {trip_id, title, start, end, cities}."""
    run = _run()
    if not account or run is None:
        return []

    async def fn(conn):
        return await conn.fetch("select id, title, destinations->'cities' cities, depart_date, return_date from trips where owner_id = $1 "
                                "and destinations ? 'plan' and status in ('draft','active') order by updated_at desc limit 20", uuid.UUID(account))
    try:
        rows = await run(fn)
    except Exception as e:
        log.info("[plan_store] no plans read: %s", type(e).__name__)
        return []
    out = []
    for r in rows:
        c = r["cities"]
        c = json.loads(c) if isinstance(c, str) else c
        out.append({"trip_id": str(r["id"]), "title": r["title"], "start": str(r["depart_date"]) if r["depart_date"] else None,
                    "end": str(r["return_date"]) if r["return_date"] else None, "cities": c or []})
    return out


async def by_id(account: Optional[str], trip_id: str) -> Optional[dict]:
    """One plan of the account's, by its trip id (the latest() shape)."""
    run = _run()
    if not account or run is None:
        return None

    async def fn(conn):
        return await conn.fetchrow("select id, title, destinations, depart_date, return_date from trips where owner_id = $1 and id = $2 "
                                   "and destinations ? 'plan'", uuid.UUID(account), uuid.UUID(trip_id))
    try:
        r = await run(fn)
    except Exception:
        return None
    if not r:
        return None
    d = r["destinations"]
    d = json.loads(d) if isinstance(d, str) else d
    return {"trip_id": str(r["id"]), "title": r["title"], "start": r["depart_date"], "end": r["return_date"], "plan": d.get("plan") or {},
            "cities": d.get("cities") or []}


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
        day, edge = by_date.get(b.get("date") or ""), None
        if day is None and b.get("type") == "flight" and days and b.get("date"):
            # Sasha 169 · the flight there leaves the day before day 1, and the one home the day after the last: shown on those days
            try:
                fd = date.fromisoformat(str(b["date"])[:10])
                if days[0].get("date") and fd == date.fromisoformat(days[0]["date"]) - timedelta(days=1):
                    day, edge = days[0], f"leaves {fd.strftime('%a')} {fd.day} {fd.strftime('%b')}"
                elif days[-1].get("date") and fd == date.fromisoformat(days[-1]["date"]) + timedelta(days=1):
                    day, edge = days[-1], f"leaves {fd.strftime('%a')} {fd.day} {fd.strftime('%b')}"
            except ValueError:
                pass
        if day is None or b.get("status") in ("cancelled",):
            continue
        part = _part(b.get("time"))
        from .wa_brain import is_test
        entry = {"id": b.get("id"), "venue": b.get("venue"), "time": b.get("time"), "part": part, "status": b.get("status"),
                 "status_words": b.get("status_words"), "what": b.get("what"), "type": b.get("type"),
                 "test": is_test(b), **({"edge": edge} if edge else {})}   # Sasha 167 · TEST-labelled; Sasha 169 · the flight's own day
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


#: Sasha 179 (1) · a TEST booking never reads "Confirmed" anywhere — no venue confirmed anything
TEST_BOOKED = "TEST · booked (demo)"


def _is_test(b: dict) -> bool:
    from .wa_brain import is_test
    return bool(b.get("test")) or is_test(b)


def truthful(rows: List[dict]) -> List[dict]:
    """The reservations with every booked TEST item's words replaced by TEST_BOOKED (web tabs, WhatsApp, ask-anything)."""
    return [{**r, "status_words": TEST_BOOKED, "test": True} if r.get("status") in ("confirmed", "guest_booked") and _is_test(r) else r
            for r in rows or []]


def short_status(b: dict) -> str:
    """The status in a few words for the compact view (the full words, with their quote, are on the web and the receipt)."""
    if b.get("status") in ("confirmed", "guest_booked") and _is_test(b):
        return TEST_BOOKED
    words = _SHORT.get(b.get("status") or "", b.get("status_words") or b.get("status") or "")
    ref = re.search(r"their ref ([A-Z0-9-]+)", b.get("status_words") or "")
    return words + (f" · ref {ref[1]}" if ref and b.get("status") == "confirmed" else "")


async def view(account: Optional[str], p: dict, bookings: List[dict]) -> dict:
    """Sasha 198 R3 · THE VIEW every surface shows (web panel, WhatsApp, voice, ask-anything): merge(), and with the basket on
    (SASHA_BASKET=1) each day's stay and the trip's flights from the basket — the same on all three."""
    m = merge(p, bookings)
    from . import basket as BK
    if account and p.get("trip_id") and BK.on():
        m = BK.overlay(m, await BK.items(account, p["trip_id"]))
    return m


def text(plan: dict) -> List[str]:
    """Compact, for WhatsApp and the voice: one block per day — the place, the bookings with their status, what's planned."""
    from .sentences import day_words
    out = [f"🗺 {plan.get('title') or 'Your trip'}" + (f" — {day_words(plan['start'])} to {day_words(plan['end'])}" if plan.get("start") and plan.get("end") else "")]
    for f in (plan.get("basket") or {}).get("flights") or []:
        out.append(f"✈️ {f.get('owner') or ''} {f.get('flights') or ''} {f.get('from') or ''}→{f.get('to') or ''}: {f.get('words')}".replace("  ", " "))
    for d in plan.get("days") or []:
        head = f"Day {d.get('day')}{' · ' + day_words(d['date']) if d.get('date') else ''} — {d.get('city') or ''}"
        lines = [head]
        for b in sorted(d.get("bookings") or [], key=lambda x: x.get("time") or ""):
            name = str(b.get("venue") or "").replace("(TEST stand-in)", "(our test venue stood in)")
            when = f"{b.get('time') or ''} ({b['edge']})" if b.get("edge") else (b.get("time") or "")
            lines.append(f"  • {when} {'TEST · ' if b.get('test') and not short_status(b).startswith('TEST') else ''}{name}: {short_status(b)}".replace("  •  ", "  • "))
        if d.get("stay") and d["stay"].get("first_night"):   # Sasha 198 R3 · the basket's stay, in its state's words
            lines.append(f"  🏨 {d['stay'].get('name')}: {d['stay'].get('words')}")
        acts = [a for a in d.get("activities") or [] if not a.get("replaced_by")]
        for a in [a for a in acts if a.get("added")]:   # Sasha 167 · a place picked on WhatsApp: on its day, not booked
            lines.append(f"  📍 {a.get('time')}: {a.get('name')} (not booked yet)")
        for a in [a for a in acts if not a.get("added")][:2]:
            lines.append(f"  · {a.get('time')}: {a.get('name')}")
        out.append("\n".join(lines))
    return out


__all__ = ["TEST_BOOKED", "truthful", "short_status", "save", "latest", "merge", "view", "text", "dates_of", "add_place", "clear_added", "add_day"]
