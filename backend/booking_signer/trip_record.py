"""Sasha 397 · 395 (2) · THE ONE TRIP RECORD — a trip is one Sasha `trips` row T, whatever its parts and whatever door shows it; this is the
ONE reader over T (root test: mailbox row 2087; Tyler's go on EU 288 §1).

  T             a personal trip: the trips row (plan_store), its basket rows by trip_id; a GROUP trip: its movement's set of T's — one per
                traveller (groups.trip_of, linked as group_members.trip_id). No second trip table.
  trips()       the account's trips as T's: its own plans, and every movement it organises (the set of its travellers' T's).
  find(words)   the trip THEIR words name (a plan's title or city, a movement's destination): exactly one → it; none → None (the caller
                reads the latest, as before); more than one → {"several": [...]} — never a guess.
  booked parts  read from their OWN record, never the basket's copy: a group traveller's from AgAPI (group.bookings, via the movement's
                card — groups.card → reconcile); a venue from AgAPI (venue.bookings, external_ref = trip:T); a personal flight from its
                Duffel order (basket.live) until AgAPI holds it (FOR CR 1, row 2088).

Replaces v0._named_movement (394), a reader that merged two records by name.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

log = logging.getLogger("booking_signer.trip_record")


def _norm(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " " + " ".join(re.sub(r"[^a-z0-9]+", " ", s).split()) + " "


def ref(trip_id: str) -> str:
    """T as the external_ref every AgAPI booking carries (CR 132's shape)."""
    return f"trip:{trip_id}"


async def trips(account: Optional[str]) -> List[Dict[str, Any]]:
    """The account's trips, as T's: {kind: personal|group, id, names, …}. A store that doesn't answer gives fewer — never an invented one."""
    if not account:
        return []
    out: List[Dict[str, Any]] = []
    from . import plan_store as PS
    try:
        mine = await PS.plans(account) or []
    except Exception as e:   # the plans didn't read: none listed (the caller reads the latest, as before) — never an invented one
        log.info("[trip_record] plans not read: %s", type(e).__name__)
        mine = []
    for p in mine:
        tid = p.get("trip_id") or p.get("id")
        if not tid:
            continue
        names = [p.get("title")] + [c.get("name") if isinstance(c, dict) else c for c in (p.get("cities") or [])]
        out.append({"kind": "personal", "id": str(tid), "trip_id": str(tid), "title": p.get("title"),
                    "names": [n for n in names if n], "start": p.get("start"), "end": p.get("end")})
    try:
        from . import groups as G
        for m in await G.store().trips(account):
            out.append({"kind": "group", "id": m["id"], "movement_id": m["id"], "title": m.get("destination"),
                        "names": [n for n in (m.get("destination"), m.get("company")) if n], "start": m.get("starts_on"), "end": m.get("ends_on")})
    except Exception as e:   # no group record for this account (or it didn't answer): its personal trips only
        log.info("[trip_record] group trips not read: %s", type(e).__name__)
    return out


def named(all_trips: List[Dict[str, Any]], words: str) -> List[Dict[str, Any]]:
    """The trips whose own name (a title, a city, a destination — 3+ letters) is in their words."""
    said = _norm(words)
    hit = []
    for t in all_trips:
        if any(len(_norm(n).strip()) >= 3 and _norm(n) in said for n in t.get("names") or []):
            hit.append(t)
    return hit


async def find(account: Optional[str], words: Optional[str]) -> Optional[Dict[str, Any]]:
    """The trip THEIR words name — one; {"several": [...]} when more than one is named (never a guess); None when none is."""
    if not account or not str(words or "").strip():
        return None
    hit = named(await trips(account), str(words))
    if len(hit) == 1:
        return hit[0]
    if len(hit) > 1:
        return {"several": [{"kind": t["kind"], "title": t.get("title"), "start": t.get("start"), "end": t.get("end")} for t in hit]}
    return None


async def trip_on(account: Optional[str], day: Optional[str]) -> Optional[str]:
    """Sasha 397 · the ONE personal T a booking on `day` belongs to — the plan whose dates hold it (exactly one; else none, never a guess).
    The same rule the itinerary used at view time, now decided ONCE, when the booking is made, and carried on AgAPI's record."""
    if not account or not day:
        return None
    from . import plan_store as PS
    d = str(day)[:10]
    try:
        mine = await PS.plans(account) or []
    except Exception as e:
        log.info("[trip_record] plans not read for the booking's trip: %s", type(e).__name__)
        return None
    on = [p for p in mine if p.get("start") and p.get("end") and str(p["start"]) <= d <= str(p["end"])]
    return str(on[0].get("trip_id") or on[0].get("id")) if len(on) == 1 else None


#: Sasha 398 · the kind, in the ONE conversation record, that POINTS at the trip this conversation is about: {kind, id} — never its content
NOW = "trip_now"
_NOW: Dict[str, Dict[str, str]] = {}   # Sasha 403 · this process's copy when the record has no database (tests, local) — the same pointer


async def _pointer(account: str) -> Optional[Dict[str, str]]:
    from agapi import s2_memory as MEM
    try:
        k = await MEM.kind(account, NOW)
    except Exception:
        k = None
    return k if isinstance(k, dict) and k.get("id") else _NOW.get(account)


async def remember(account: Optional[str], t: Optional[Dict[str, Any]]) -> None:
    """Sasha 398 · the trip the reader just resolved IS the trip this conversation is about (a pointer; cleared by "New chat")."""
    if not account or not t or t.get("several") or not t.get("id"):
        return
    from agapi import s2_memory as MEM
    p = {"kind": t["kind"], "id": str(t["id"])}
    _NOW[account] = p
    try:
        await MEM.put_kind(account, NOW, p)
    except Exception as e:
        log.info("[trip_record] the trip now wasn't kept: %s", type(e).__name__)


async def current(account: Optional[str]) -> Optional[Dict[str, Any]]:
    """Sasha 398 · THE ONE ANSWER to "which trip is this conversation about?" — every screen, message and tool asks it here: the trip the
    reader last resolved in THIS conversation (still on the record), else the person's latest personal T. None: no trip."""
    if not account:
        return None
    k = await _pointer(account)
    if isinstance(k, dict) and k.get("id"):
        t = next((x for x in await trips(account) if x["kind"] == k.get("kind") and str(x["id"]) == str(k["id"])), None)
        if t:
            return t
    p = await plan_now(account)
    return {"kind": "personal", "id": p["trip_id"], "trip_id": p["trip_id"], "title": p.get("title")} if p else None


async def plan_now(account: Optional[str], strict: bool = False) -> Optional[dict]:
    """Sasha 398 · the PERSONAL plan this conversation is about (plan_store's shape): the one pointed at, else the latest. A group trip in
    talk leaves the person's own latest plan for the personal tools. strict: an outage raises (never read as "no trip")."""
    if not account:
        return None
    from . import plan_store as PS
    k = await _pointer(account)
    if isinstance(k, dict) and k.get("kind") == "personal" and k.get("id"):
        p = await PS.by_id(account, str(k["id"]))
        if p:
            return p
    return await PS.latest(account, strict=strict)


async def plans(account: Optional[str]) -> List[dict]:
    """Sasha 403 · the account's personal trips as plans ({trip_id, title, start, end, cities}, newest touched first, archived never) —
    the ONE read every screen lists them by (journeys had its own SQL, and showed archived trips the rest hid)."""
    from . import plan_store as PS
    return await PS.plans(account) if account else []


async def group_now(account: Optional[str], store: Any = None) -> Optional[str]:
    """Sasha 403 · EU 292 claim 1 · WHICH GROUP TRIP is meant — the ONE answer (groups' own "open trip" pointer, opened_at, is gone): the
    conversation's pointer when it is a group trip still on the record; else the organiser's ONLY open trip; else None — several, and
    none pointed at, is asked, never the newest."""
    if not account:
        return None
    try:
        from . import groups as G
        mine = await (store or G.store()).trips(account)   # the store being asked (its own movements), else the app's
    except Exception as e:
        log.info("[trip_record] group trips not read: %s", type(e).__name__)
        return None
    ids = [str(m["id"]) for m in mine]
    k = await _pointer(account)
    if isinstance(k, dict) and k.get("kind") == "group" and str(k.get("id")) in ids:
        return str(k["id"])
    return ids[0] if len(ids) == 1 else None


async def bucket(conn, owner, title: str):
    """Sasha 403 · THE account's general-bookings trip (a booking made before it is on a journey), found or made — the ONE copy of this
    (it was in call_store, form_rung, ladder_store ×2, store, products/campus/visits and products/itinerary). Inside the caller's
    transaction: `conn` is theirs."""
    tid = await conn.fetchval("select id from trips where owner_id = $1 and title = $2 and status in ('draft','active') "
                              "order by created_at limit 1", owner, title)
    if tid is None:
        tid = await conn.fetchval("insert into trips (owner_id, title) values ($1, $2) returning id", owner, title)
    return tid


async def booked_parts(account: str, rows: List[dict]) -> List[dict]:
    """A personal T's basket rows with every BOOKED part read from its own record (the Duffel order, basket.live — Sasha 305), never the
    basket's copy. Plan state (suggested / chosen / pending_payment) is the basket's own."""
    from . import basket as BK
    return await BK.live(rows)


__all__ = ["trips", "find", "named", "trip_on", "booked_parts", "ref", "remember", "current", "plan_now", "NOW", "group_now", "bucket", "plans"]
