"""CR 1 · a registered visit in the family's bookings and calendar.

`record` adds a trip item (type 'experience', status 'pending') to the account's bookings — the same row every Sasha
booking is, so "You → My bookings", the S-83 reminders and the S-79 calendar outbox see it with no new code. It stays
`pending` ("registered on your word") until the school's own confirmation is pasted; `confirm` then sets 'confirmed',
which the calendar trigger (sql/022) picks up. Without a database it returns None and the chat says so plainly.
"""
from __future__ import annotations

import logging
import urllib.parse
import uuid
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from .. import store as ST

log = logging.getLogger("products.campus.visits")
TRIP_TITLE = "Sasha bookings"   # = call_store.BOOKINGS_TRIP_TITLE: one trip holds every booking


def _minutes(x: dict) -> int:
    if x.get("end"):
        h1, m1 = map(int, x["start"].split(":"))
        h2, m2 = map(int, x["end"].split(":"))
        return max(30, (h2 * 60 + m2) - (h1 * 60 + m1))
    return 90


def name_of(s: dict, x: dict) -> str:
    return f"{s['name']} campus visit — {x['title'].split(' · ')[0]}"


async def record(account: str, s: dict, x: dict, party: int) -> Optional[str]:
    if ST.BASE is None:
        return None
    try:
        from booking_signer.call_store import BOOKINGS_TRIP_TITLE as title
    except Exception:
        title = TRIP_TITLE
    acct = uuid.UUID(account)

    async def fn(conn):
        async with conn.transaction():
            tid = await conn.fetchval("select id from trips where owner_id = $1 and title = $2 and status in ('draft','active') "
                                      "order by created_at limit 1", acct, title)
            if tid is None:
                tid = await conn.fetchval("insert into trips (owner_id, title) values ($1, $2) returning id", acct, title)
            return await conn.fetchval(
                "insert into trip_items (trip_id, type, status, provider_name, date_time, local_timezone, party_size, "
                "duration_minutes, location_name) values ($1, 'experience', 'pending', $2, ($3::date + $4::time) at time zone $5, "
                "$5, $6, $7, $8) returning id",
                tid, name_of(s, x), date.fromisoformat(x["day"]), datetime.strptime(x["start"], "%H:%M").time(), s["tz"],
                party, _minutes(x), x.get("location") or s["full_name"])
    try:
        return str(await ST.BASE._run(fn))
    except Exception as e:
        log.error("[campus] the visit wasn't added to bookings: %s: %s", type(e).__name__, e)
        return None


async def confirm(item_id: Optional[str]) -> None:
    if not item_id or ST.BASE is None:
        return
    try:
        await ST.BASE._run(lambda c: c.execute("update trip_items set status = 'confirmed', updated_at = now() where id = $1",
                                               uuid.UUID(item_id)))
    except Exception as e:
        log.error("[campus] the visit wasn't marked confirmed: %s: %s", type(e).__name__, e)


def _span_utc(s: dict, x: dict):
    tz = ZoneInfo(s["tz"])
    start = datetime.combine(date.fromisoformat(x["day"]), datetime.strptime(x["start"], "%H:%M").time(), tzinfo=tz)
    end = start + timedelta(minutes=_minutes(x))
    utc = ZoneInfo("UTC")
    return start.astimezone(utc), end.astimezone(utc)


def google_link(s: dict, x: dict) -> str:
    """Google Calendar's own "add event" page, pre-filled — the person presses Save."""
    a, b = _span_utc(s, x)
    q = {"action": "TEMPLATE", "text": name_of(s, x), "dates": f"{a:%Y%m%dT%H%M%SZ}/{b:%Y%m%dT%H%M%SZ}",
         "location": f"{x.get('location') or ''}, {s['full_name']}, {s['city']}".lstrip(", "),
         "details": f"Registration page: {x['form_url']}"}
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(q)


def ics(s: dict, x: dict, uid: str, confirmed: bool) -> str:
    a, b = _span_utc(s, x)

    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Kanoe//CampusMe//EN", "METHOD:PUBLISH", "BEGIN:VEVENT",
        f"UID:{uid}@campusme.kanoe.ai", f"DTSTAMP:{datetime.now(ZoneInfo('UTC')):%Y%m%dT%H%M%SZ}",
        f"DTSTART:{a:%Y%m%dT%H%M%SZ}", f"DTEND:{b:%Y%m%dT%H%M%SZ}", f"SUMMARY:{esc(name_of(s, x))}",
        f"LOCATION:{esc((x.get('location') or '') + ', ' + s['full_name'] + ', ' + s['city'])}",
        f"DESCRIPTION:{esc(('Confirmed by the school in writing.' if confirmed else 'Registered on your word; the school confirms by email.') + ' Registration page: ' + x['form_url'])}",
        f"STATUS:{'CONFIRMED' if confirmed else 'TENTATIVE'}", "END:VEVENT", "END:VCALENDAR", ""])
