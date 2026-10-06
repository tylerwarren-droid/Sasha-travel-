"""Sasha 177 · ONE TRIPS SPACE, ONE TAB PER JOURNEY.

A journey is a plan on the account (Vietnam, the campus tour, the move to Madrid). Every booking is FILED into the journey whose
dates AND place fit — or stays at home ("Madrid (home)") when none does, or when two would (never a guess). Live, the campus tour
(15–17 Nov) absorbed the Vietnam hotels and the Hoi An dinner by date alone.

  file(account)      — moves bookings out of the account's general list into their journey (never between journeys);
  journeys(account)  — the tabs: each journey, home, requests (waiting on a reply), receipts (booked), everything by date.
The place of a booking: its location, the city its venue was searched in (a stand-in keeps the real city that way), its name,
and only then its time zone's country.
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
import uuid
from datetime import date, timedelta
from typing import Dict, List, Optional

log = logging.getLogger("booking_signer.journeys")

OPEN = ("pending", "requested", "attempting", "link_sent", "quoted", "proposed", "unclear", "waitlisted")
BOOKED = ("confirmed", "guest_booked")
_TZ_COUNTRY = {"Asia/Ho_Chi_Minh": "VN", "Asia/Bangkok": "VN", "Asia/Saigon": "VN", "Europe/Madrid": "ES", "Europe/London": "GB",
               "Europe/Lisbon": "PT", "Europe/Paris": "FR", "Europe/Rome": "IT"}
_US_CITIES = {"new haven", "providence", "philadelphia", "boston", "cambridge", "new york", "princeton", "ithaca", "hanover", "washington"}
_MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fold(s: Optional[str]) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", (s or "").replace("đ", "d")) if unicodedata.category(ch) != "Mn").lower()


def country_of_plan(title: str, cities: List[str]) -> Optional[str]:
    from .handoff import VN_CITIES
    cs = {_fold(c) for c in cities or []}
    if cs & VN_CITIES or "vietnam" in _fold(title):
        return "VN"
    if cs & _US_CITIES or "campus" in _fold(title):
        return "US"
    if cs & {"madrid", "barcelona", "sevilla", "valencia"}:
        return "ES"
    return None


def label(p: dict) -> str:
    """"Vietnam, Nov" · "Campus tour, week of 15 Nov" · "Move to Madrid"."""
    t = (p.get("title") or "Trip").strip()
    if re.match(r"(?i)campus tour", t):
        return t.replace(" — ", ", ")
    m = re.search(r"(?i)days? in ([A-Za-zÀ-ÿ ]+?)(?::|$)", t)
    start = p.get("start")
    mon = _MONTH[int(str(start)[5:7]) - 1] if start else ""
    if m:
        return f"{m[1].strip()}{', ' + mon if mon else ''}"
    return t


def fits(item: dict, plan: dict) -> bool:
    """Its dates (a flight the day before / after counts) AND its place."""
    d = item.get("date")
    if not d or not plan.get("start") or not plan.get("end"):
        return False
    try:
        dd, a, b = date.fromisoformat(d[:10]), date.fromisoformat(str(plan["start"])[:10]), date.fromisoformat(str(plan["end"])[:10])
    except ValueError:
        return False
    if not (a - timedelta(days=1) <= dd <= b + timedelta(days=1)):
        return False
    cities = [_fold(c) for c in plan.get("cities") or [] if c]
    blob = " ".join(_fold(x) for x in (item.get("location"), item.get("read_city"), item.get("venue")) if x)
    if blob and any(c and re.search(rf"\b{re.escape(c)}\b", blob) for c in cities):
        return True
    if item.get("read_city") or item.get("location"):   # a place IS known and it isn't this journey's
        return False
    return bool(_TZ_COUNTRY.get(item.get("timezone") or "")) and _TZ_COUNTRY.get(item.get("timezone") or "") == plan.get("country")


def _run():
    from . import plan_store as PS
    return PS._run()


async def _plans(conn, account) -> List[dict]:
    rows = await conn.fetch("select id, title, destinations, depart_date, return_date from trips where owner_id = $1 and destinations ? 'plan' "
                            "and status in ('draft','active') order by updated_at desc", uuid.UUID(account))
    out = []
    for r in rows:
        d = r["destinations"]
        d = json.loads(d) if isinstance(d, str) else d
        cities = (d or {}).get("cities") or []
        out.append({"trip_id": str(r["id"]), "title": r["title"], "start": r["depart_date"], "end": r["return_date"], "cities": cities,
                    "country": country_of_plan(r["title"] or "", cities)})
    return out


async def file(account: Optional[str]) -> int:
    """Bookings in the account's general list → the ONE journey they fit. Returns how many moved. Never raises."""
    run = _run()
    if not account or run is None:
        return 0

    async def go(conn):
        plans = await _plans(conn, account)
        if not plans:
            return 0
        rows = await conn.fetch(
            "select ti.id, ti.provider_name, ti.location_name, ti.local_timezone, "
            "to_char(ti.date_time at time zone coalesce(ti.local_timezone, 'UTC'), 'YYYY-MM-DD') as day, "
            "coalesce(vf.query->>'city', ve.query->>'city', vl.query->>'city') as read_city "
            "from trip_items ti join trips t on t.id = ti.trip_id "
            "left join booking_forms bf on bf.trip_item_id = ti.id left join venue_reads vf on vf.read_id = bf.read_id "
            "left join booking_emails be on be.trip_item_id = ti.id left join venue_reads ve on ve.read_id = be.read_id "
            "left join booking_links bl on bl.trip_item_id = ti.id left join venue_reads vl on vl.read_id = bl.read_id "
            "where t.owner_id = $1 and not (t.destinations ? 'plan') and ti.date_time is not null", uuid.UUID(account))
        moved = 0
        for r in rows:
            item = {"date": r["day"], "venue": r["provider_name"], "location": r["location_name"], "timezone": r["local_timezone"],
                    "read_city": r["read_city"]}
            hits = [p for p in plans if fits(item, p)]
            if len(hits) == 1:
                await conn.execute("update trip_items set trip_id = $2, updated_at = now() where id = $1", r["id"], uuid.UUID(hits[0]["trip_id"]))
                moved += 1
        return moved
    try:
        n = await run(go)
        if n:
            log.info("[journeys] %d booking(s) filed into their journey", n)
        return n or 0
    except Exception as e:
        log.warning("[journeys] filing failed: %s: %s", type(e).__name__, e)
        return 0


def home_label() -> str:
    city = (os.getenv("SASHA_HOME_CITY", "Madrid, ES").split(",")[0] or "Madrid").strip()
    return f"{city} (home)"


async def journeys(account: Optional[str], rows: List[dict]) -> dict:
    """The tabs, from the account's reservations (each carries its trip_id)."""
    run = _run()
    plans = []
    if account and run is not None:
        try:
            plans = await run(lambda c: _plans(c, account))
        except Exception as e:
            log.info("[journeys] no plans: %s", type(e).__name__)
    ids = {p["trip_id"] for p in plans}
    tabs = [{"key": p["trip_id"], "label": label({**p, "start": str(p["start"]) if p["start"] else None}), "title": p["title"],
             "start": str(p["start"]) if p["start"] else None, "end": str(p["end"]) if p["end"] else None,
             "count": sum(1 for r in rows if str(r.get("trip_id")) == p["trip_id"] and r.get("status") not in ("cancelled", "failed"))}
            for p in plans]
    live = [r for r in rows if r.get("status") not in ("cancelled", "failed")]
    home = [r for r in live if str(r.get("trip_id")) not in ids]
    return {"journeys": tabs, "home": {"label": home_label(), "items": home},
            "requests": [r for r in live if r.get("status") in OPEN],
            "receipts": [r for r in rows if r.get("status") in BOOKED],
            "everything": sorted(rows, key=lambda r: f"{r.get('date') or '9'}{r.get('time') or ''}")}


def for_journey(rows: List[dict], trip_id: Optional[str]) -> List[dict]:
    """A journey's own bookings only: never another journey's, never home's (the bug was date-only)."""
    return [r for r in rows if trip_id and str(r.get("trip_id")) == str(trip_id)]


__all__ = ["file", "journeys", "for_journey", "fits", "label", "country_of_plan", "OPEN", "BOOKED", "home_label"]
