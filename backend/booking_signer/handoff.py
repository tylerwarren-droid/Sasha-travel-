"""S-26 · Sasha recognises a booking at Restaurante Psi and hands it to her booking tab.

Called at the top of the conductor (app/services/conductor.py, `conduct()`), by a block Stage B re-applies after
every CTO drop. It returns a full conductor turn — or None, and the conductor carries on as if it were not there.

⚠ NARROW ON PURPOSE: one venue (Psi), dry run, and the yes is given in her tab — where the five read-back lines
are shown and the approval is bound, by the server, to the exact words (booking_signer/routes.py). Nothing here
signs, records or books anything; it only opens the tab.

⚠ NO GUESSING. The date, time and party are taken from the message only when stated plainly; anything unclear
is left empty and the tab asks. A wrong date, read back and approved, is a real harm; an empty field is not.

The tab is opened by the chat's own restaurant card: a `bookings` entry whose option has no `offer_id` renders
as a real link (SashaChat.tsx), and a click is the user gesture a new top-level tab needs — the helper refuses a
framed page, and a tab opened without a click would be blocked as a pop-up.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional
from urllib.parse import urlencode

try:
    from zoneinfo import ZoneInfo
    _LISBON = ZoneInfo("Europe/Lisbon")
except Exception:  # no tz database: fall back to UTC for "today" (Lisbon is UTC or UTC+1)
    _LISBON = timezone.utc

#: Psi's served times (contract §3.6) — a time outside these is left for the tab to ask, never rounded.
PSI_SLOTS = ("12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "19:30", "20:00", "20:30", "21:00", "21:30", "22:00")
BOOKING_TAB = "/booking-helper"

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}
_MONTHS.update({m[:3]: n for m, n in list(_MONTHS.items())})
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "eleven": 11, "twelve": 12}

_PSI = re.compile(r"\bpsi\b", re.I)
_BOOKING = re.compile(r"\b(book|booking|reserve|reservation|table)\b", re.I)


def is_psi_booking(message: str) -> bool:
    return bool(_PSI.search(message or "")) and bool(_BOOKING.search(message or ""))


def _today(now: Optional[datetime]) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(_LISBON).date()


def plain_date(message: str, now: Optional[datetime] = None) -> Optional[str]:
    """ISO date, or None. Accepts 2026-10-05 · 5 October · 5th of October · October 5 · tomorrow."""
    t = message.lower()
    today = _today(now)
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            return None
    if re.search(r"\btomorrow\b", t):
        return (today + timedelta(days=1)).isoformat()
    names = "|".join(sorted(_MONTHS, key=len, reverse=True))
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({names})\b", t) or \
        re.search(rf"\b({names})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", t)
    if not m:
        return None
    day, month = (int(m[1]), _MONTHS[m[2]]) if m[1].isdigit() else (int(m[2]), _MONTHS[m[1]])
    for year in (today.year, today.year + 1):   # the next such date that is not in the past
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= today:
            return d.isoformat()
    return None


def plain_time(message: str) -> Optional[str]:
    """HH:MM on Psi's served slots, or None. Accepts 8pm · 8:30 pm · 20:00. A bare "at 8" is ambiguous: None."""
    t = message.lower()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    if m:
        h, mi = int(m[1]) % 12 + (12 if m[3] == "pm" else 0), int(m[2] or 0)
    else:
        m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
        if not m:
            return None
        h, mi = int(m[1]), int(m[2])
    hhmm = f"{h:02d}:{mi:02d}"
    return hhmm if hhmm in PSI_SLOTS else None


def plain_party(message: str) -> Optional[int]:
    """1–20, or None. Accepts: for 2 · for two · table for 4 · 3 people · party of 6."""
    t = message.lower()
    words = "|".join(_NUMBERS)
    m = re.search(rf"\b(?:for|party of)\s+(\d{{1,2}}|{words})\b(?!\s*(?:am|pm|:))", t) or \
        re.search(rf"\b(\d{{1,2}}|{words})\s+(?:people|persons|guests|of us)\b", t)
    if not m:
        return None
    n = int(m[1]) if m[1].isdigit() else _NUMBERS[m[1]]
    return n if 1 <= n <= 20 else None


def booking_handoff(message: str, history: Optional[List[dict]] = None, now: Optional[datetime] = None) -> Optional[dict]:
    """A full conductor turn that opens Sasha's booking tab for Psi — or None, and the conductor carries on."""
    if not is_psi_booking(message):
        return None
    d, t, p = plain_date(message, now), plain_time(message), plain_party(message)
    # `profile=demo`: the tab fills name, email and phone from a DEMO guest (P807mv) — line 4 of the read-back says the
    # email and telephone aloud, and a room must never hear the founder's own
    query = {"venue": "restaurante-psi", **({"date": d} if d else {}), **({"time": t} if t else {}), **({"party": p} if p else {}),
             "profile": "demo"}
    url = f"{BOOKING_TAB}?{urlencode(query)}"
    known = ", ".join(x for x in [
        (lambda x: f"{x:%A} {x.day} {x:%B}")(date.fromisoformat(d)) if d else None,
        t, f"{p} {'person' if p == 1 else 'people'}" if p else None] if x)
    missing = [x for x, v in (("the date", d), ("the time", t), ("how many people", p)) if not v]
    response = (
        f"I'll open my booking tab for Restaurante Psi{f' — {known}' if known else ''}. "
        + (f"Add {', '.join(missing)} there. " if missing else "")
        + "I'll read it all back before anything happens — and this is a dry run: I fill their form on your computer and stop before sending."
    )
    card = {"type": "restaurant", "title": "Restaurante Psi, Lisbon — booking",
            "options": [{"name": "Open my booking tab", "detail": known or "details to add", "price": "dry run",
                         "book_url": url}]}
    history = list(history or [])
    return {
        "response": response, "intents": ["restaurant"], "photos": [], "tools_used": [], "links": [],
        "hotels": [], "bookings": [card], "itinerary": None, "action": None, "booking_ref": None,
        "itinerary_id": None, "payment_item": None, "saved_card": None,
        "messages": history + [{"role": "user", "content": message}, {"role": "assistant", "content": response}],
        # S-64 step 11 · the same message as the parts of reservation/1 it states, and what is still to ask — carried
        # alongside; the Psi link above is unchanged
        "reservation_draft": _draft(message, now),
    }


def _draft(message: str, now: Optional[datetime]) -> dict:
    from .chat_request import draft
    return draft(message, now, lang="pt")


__all__ = ["booking_handoff", "is_psi_booking", "plain_date", "plain_time", "plain_party", "PSI_SLOTS"]
