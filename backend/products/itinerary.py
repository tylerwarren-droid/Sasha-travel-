"""CR 10 · one account, one itinerary: what a person booked THEMSELVES through a product — the consulate or TIE
appointment, a SERMAS appointment, a campus visit — becomes a trip item in their "Sasha bookings" trip, like any booking.

The Sasha tab's rules (CR 10 answer): status 'guest_booked' ("Booked by you — forward the confirmation to add the
reference"), never 'confirmed' — that only on the provider's own words; types 'visa' (consulate, TIE), 'doctor'
(SERMAS or another doctor's appointment), 'appointment' (anything else dated with a place). S-83 treats guest_booked as
booked: the day-before reminder fires, and the products say so. Dated REMINDERS (apply-from, the volante's expiry) are
NOT trip items — they're listed in their own block (GET /api/booking/products/reminders).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, time
from typing import Optional, Tuple

from . import store as ST

log = logging.getLogger("products.itinerary")

#: the provider names CR products write — the rehearsal and the reset find their own rows by these, and nothing else
CONSULATE = "Consulado General de España en Londres — visa appointment"
TIE = "TIE appointment — Oficina de Extranjería / Policía"
SERMAS = "Centro de salud (SERMAS) — doctor's appointment"
OURS = (CONSULATE, TIE, SERMAS)

_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"), 1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})


def parse_day_time(text: str, today: date) -> Optional[Tuple[date, str]]:
    """"12 November 10:00", "12/11/2026 at 9:30", "November 12 2026 10.15" → (the next such day, "HH:MM"), or None."""
    s = (text or "").lower()
    tm = re.search(r"\b([01]?\d|2[0-3])[:.h]([0-5]\d)\b", s)
    if not tm:
        return None
    hhmm = f"{int(tm.group(1)):02d}:{tm.group(2)}"
    s2 = s[:tm.start()] + " " + s[tm.end():]
    d = None
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", s2)
    if m:
        y = int(m.group(3)) if m.group(3) else today.year
        y = y + 2000 if y < 100 else y
        try:
            d = date(y, int(m.group(2)), int(m.group(1)))
        except ValueError:
            d = None
    if d is None:   # every "12 November" / "November 12" candidate, until one names a real month
        cands = [(m.group(1), m.group(2), m.group(3)) for m in re.finditer(r"\b(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?\b", s2)]
        cands += [(m.group(2), m.group(1), m.group(3)) for m in re.finditer(r"\b([a-z]+)\s+(\d{1,2})(?:,?\s+(\d{4}))?\b", s2)]
        for day, mon, yr in cands:
            if mon[:3] in _MONTHS:
                try:
                    d = date(int(yr) if yr else today.year, _MONTHS[mon[:3]], int(day))
                    break
                except ValueError:
                    continue
    if d is None:
        return None
    if d < today and not re.search(r"\b\d{4}\b", s2):
        d = date(d.year + 1, d.month, d.day)
    return (d, hhmm) if d >= today else None


async def guest_booked(account: str, *, type_: str, provider_name: str, on: date, at: str, tz: str,
                       location: Optional[str] = None, party: int = 1) -> Optional[str]:
    """One trip item in the account's "Sasha bookings" trip, status guest_booked. None (and logged) without a database."""
    if ST.BASE is None:
        return None
    from booking_signer.call_store import BOOKINGS_TRIP_TITLE as title
    acct = uuid.UUID(account)

    async def fn(conn):
        async with conn.transaction():
            tid = await conn.fetchval("select id from trips where owner_id = $1 and title = $2 and status in ('draft','active') "
                                      "order by created_at limit 1", acct, title)
            if tid is None:
                tid = await conn.fetchval("insert into trips (owner_id, title) values ($1, $2) returning id", acct, title)
            return await conn.fetchval(
                "insert into trip_items (trip_id, type, status, provider_name, date_time, local_timezone, party_size, location_name) "
                "values ($1, $2, 'guest_booked', $3, ($4::date + $5::time) at time zone $6, $6, $7, $8) returning id",
                tid, type_, provider_name, on, datetime.strptime(at, "%H:%M").time(), tz, party, location)
    try:
        return str(await ST.BASE._run(fn))
    except Exception as e:
        log.error("[itinerary] not added: %s: %s", type(e).__name__, e)
        return None
