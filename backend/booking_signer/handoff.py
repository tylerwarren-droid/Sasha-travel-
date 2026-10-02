"""S-26 → S-66 (EU) step 5 · Sasha recognises "find / book / reserve {X} in {Y}" and starts the booking IN THE CHAT.

Called at the top of the conductor (app/services/conductor.py, `conduct()`), by a block Stage B re-applies after
every CTO drop. It returns a full conductor turn carrying `booking_find: {what, where, country?}` — the chat runs Find
venues with it (S-65: up to five Google listings, nothing contacted) — or None, and the conductor carries on.

⛔ The Psi-only link to /booking-helper is RETIRED (S-66 §3.4): any kind of place, anywhere, is found the same way.
⚠ NO GUESSING. The date, time and count are taken from the message only when stated plainly (`plain_*`, and the
reservation/1 draft beside it); anything unclear is asked. A wrong date, read back and approved, is a real harm.
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


_WORD_HOURS = {w: n for n, w in enumerate(["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                                           "ten", "eleven", "twelve"])}


def spoken(message: str) -> str:
    """Sasha 88 · a request SPOKEN to Sasha reads like a typed one: speech-to-text writes "9 p.m.", "nine p.m.",
    "9 P.M." — the parsers read "9pm". Nothing else is changed."""
    t = re.sub(r"\b([ap])\.\s?m\.?(?=\W|$)", lambda m: m[1].lower() + "m", message or "", flags=re.I)
    t = re.sub(r"\b(\d{1,2})\s+([ap]m)\b", r"\1\2", t, flags=re.I)
    return re.sub(r"\b(" + "|".join(_WORD_HOURS) + r")\s*([ap]m)\b", lambda m: f"{_WORD_HOURS[m[1].lower()]}{m[2].lower()}", t, flags=re.I)


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


#: S-66 (EU) step 5 · "find / book / reserve … {X} in {Y}" for ANY kind of place
_FIND = re.compile(r"\b(?:find|book|reserve|look for|search for|get)\s+(?:me\s+|us\s+)?(?:an?\s+|some\s+|the\s+)?"
                   r"(?P<what>[a-z][\w'’ -]{1,58}?)\s+(?:in|near|around)\s+(?P<where>[^?.!;]{2,80})", re.I)
#: Sasha 101 · how a request is SPOKEN without "book": "I'd like a luxury dinner in …", "can you get us a table in …".
#: Taken only when what is asked for is a bookable thing (a table, a meal, a place to book) — "I want to see the museum
#: in Madrid" is not a booking.
_SOFT = re.compile(r"\b(?:i(?:'d| would) like|we(?:'d| would) like|i want|we want|i need|we need|looking for|"
                   r"can (?:i|we|you) (?:get|have|find)|could (?:i|we|you) (?:get|have|find)|"
                   r"(?:let'?s|let us) (?:book|get|have))\s+(?:to (?:book|reserve|have|get)\s+)?(?:me\s+|us\s+)?"
                   r"(?:an?\s+|some\s+|the\s+)?(?P<what>[a-z][\w'’ -]{1,58}?)\s+(?:in|near|around)\s+(?P<where>[^?.!;]{2,80})", re.I)
#: a request that STARTS with the thing itself: "lunch for 4 in Malasaña tomorrow at two", "a table for two in Chamberí…"
_BARE = re.compile(r"^\s*(?:(?:an?|some)\s+)?(?P<what>(?:[a-záéíóúñ'’-]+\s+){0,3}?(?:table|dinner|lunch|breakfast|brunch|supper)"
                   r"(?:\s+for\s+\w+(?:\s+(?:people|of us))?)?)\s+(?:in|near|around)\s+(?P<where>[^?.!;]{2,80})", re.I)
_BOOKABLE = re.compile(r"\b(table|dinner|lunch|breakfast|brunch|supper|restaurant|bistro|tapas|bar|caf[eé]|spa|massage|tour|"
                       r"hotel|room|studio|salon|class|session|appointment|reservation)s?\b", re.I)
_DINNER = re.compile(r"\b(dinner|supper|cena|cenar|tonight|evening|noche|night|table|restaurant|mesa)\b", re.I)
_LUNCH = re.compile(r"\b(lunch|comida|almuerzo|almorzar)\b", re.I)
_MORNING = re.compile(r"\b(morning|mañana|breakfast|desayuno|a\.?m\.?)\b", re.I)


def context_time(message: str) -> Optional[str]:
    """Sasha 101 · a bare hour as people SAY it — "dinner … at nine" is 21:00, "lunch at two" is 14:00 — unless they
    say morning or am. Only for a meal said in the same request; otherwise a bare "at 9" stays unknown and is asked."""
    t = (message or "").lower()
    m = re.search(r"\bat\s+(\d{1,2}|" + "|".join(_NUMBERS) + r")(?::([0-5]\d))?(?:\s*o'?clock)?\b(?!\s*(?:am|pm|a\.m|p\.m|:))", t)
    if not m:
        return None
    h = int(m[1]) if m[1].isdigit() else _NUMBERS[m[1]]
    mi = int(m[2] or 0)
    if not 1 <= h <= 12:
        return None
    if _MORNING.search(t):   # breakfast, morning, am: the hour as said
        return f"{h:02d}:{mi:02d}" if 5 <= h <= 11 else None
    if _DINNER.search(t) and h <= 11:
        h += 12
    elif _LUNCH.search(t) and h <= 5:
        h += 12
    elif not (_DINNER.search(t) or _LUNCH.search(t)):
        return None
    return f"{h:02d}:{mi:02d}"


_WHERE_END = re.compile(r"(?:\s+|\s*,\s*)(?:for|on|at|tomorrow|today|tonight|this|next|by|please|from|open|opened|"
                        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*$", re.I)


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def plain_open_at(message: str, now: Optional[datetime] = None) -> Optional[str]:
    """S-68 step 4 · the local time a venue must be open at, "YYYY-MM-DDTHH:MM", or None. Taken only when a TIME is
    stated plainly (17:00 · 5pm · 5:30 pm); the day is a weekday (the next one, today included), "today"/"tomorrow"
    or a plain date, else today. Nothing is guessed: "Tuesday" alone, "the evening", "at 5" are None."""
    t = (message or "").lower()
    m = re.search(r"\b(\d{1,2})(?::([0-5]\d))?\s*(am|pm)\b", t)
    if m and 1 <= int(m[1]) <= 12:
        h, mi = int(m[1]) % 12 + (12 if m[3] == "pm" else 0), int(m[2] or 0)
    else:
        m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
        ct = None if m else context_time(message)   # Sasha 101 · "dinner … at nine" said aloud
        if not (m or ct):
            return None
        h, mi = (int(m[1]), int(m[2])) if m else (int(ct[:2]), int(ct[3:]))
    today = _today(now)
    day = plain_date(message, now)
    if day is None:
        wd = re.search(r"\b(" + "|".join(_WEEKDAYS) + r")\b", t)
        if wd:
            day = (today + timedelta(days=(_WEEKDAYS.index(wd[1]) - today.weekday()) % 7)).isoformat()
        else:
            day = today.isoformat()   # "today" too
    return f"{day}T{h:02d}:{mi:02d}"


#: S-68 step 7 · a priority the guest STATED, in their words — never inferred from anything else
_PRIORITY = [("price", re.compile(r"\b(cheap(?:est)?|budget|affordable|inexpensive|not too expensive|good value|low[- ]cost)\b", re.I)),
             ("rated", re.compile(r"\b(best[- ]rated|top[- ]rated|highly[- ]rated|best reviewed|well reviewed|the best|good reviews)\b", re.I)),
             ("closest", re.compile(r"\b(closest|nearest|walking distance)\b", re.I))]
PRIORITY_QUESTION = "What matters most: best rated, closest, price, or open at a time you want?"


def plain_priority(message: str, near: Optional[str]) -> Optional[str]:
    """rated · closest · price — when the message says so; "near X" with no other priority means closest."""
    for key, rx in _PRIORITY:
        if rx.search(message or ""):
            return key
    return "closest" if near else None


def find_request(message: str, now: Optional[datetime] = None) -> Optional[dict]:
    """{what, where, country?, near?} when the message asks for a kind of place in a place — else None. Nothing guessed:
    a country is taken only when written as a two-letter code ("Nairobi, KE")."""
    m = _FIND.search(message or "")
    if not m:
        m = _SOFT.search(message or "")
        if m and not _BOOKABLE.search(m["what"]):
            m = None
    if not m:
        m = _BARE.search(message or "")
    if not m:
        return None
    # Sasha 86 · "dinner for 2" is dinner, for two: the count belongs to the booking, not to what is searched for (or to
    # the name a picked place falls back to)
    what = re.sub(rf"\s+(?:for|party of)\s+(?:\d{{1,2}}|{'|'.join(_NUMBERS)})(?:\s+(?:people|persons|guests|of us))?\b", "",
                  " ".join(m["what"].split()), flags=re.I)
    # Sasha 101 · "a table at a luxury restaurant" searches for the luxury restaurant — every qualifier kept
    what = re.sub(r"^(?:a\s+)?table\s+(?:at|in)\s+(?:an?\s+|the\s+)?", "", what, flags=re.I).strip() or what
    raw = m["where"]
    # S-68 step 3 · "… in Madrid near Hotel Urban" / "near my hotel": what the distance is measured from, as said
    nm = re.search(r"[\s,]+(?:near|close to)\s+(?P<near>[^?.!;]{2,120})$", raw, re.I)
    near = None
    if nm:
        raw = raw[:nm.start()]
        near = re.sub(r"\s+(?:for|on|at|tomorrow|today|tonight|this|next|please|from)\b.*$", "", nm["near"], flags=re.I).strip(" ,") or None
    where = _WHERE_END.sub("", raw).strip(" ,")
    country = None
    cm = re.fullmatch(r"(.+?),\s*([A-Za-z]{2})", where)
    if cm:
        where, country = cm[1].strip(), cm[2].upper()
    if len(what) < 2 or len(where) < 2:
        return None
    at = plain_open_at(message, now)
    return {"what": what, "where": where, **({"country": country} if country else {}), **({"near": near} if near else {}),
            **({"open_at": at} if at else {}),
            **({"priority": p} if (p := plain_priority(message, near)) else {})}   # absent: Sasha asks (S-68 step 7)


#: Sasha 96 · "cancel my booking at Botavara" · "cancel Botavara" · "cancela la reserva en Botavara"
_CANCEL = re.compile(r"^\s*(?:please\s+)?(?:cancel|cancela(?:r)?|anula(?:r)?)\s+(?:my\s+|mi\s+|the\s+|la\s+)?"
                     r"(?:(?:booking|reservation|table|reserva|mesa)\s+)?(?:(?:at|in|for|en|de|con)\s+)?(?P<venue>[^?.!]{2,80}?)\s*[?.!]*\s*$", re.I)


def cancel_request(message: str) -> Optional[dict]:
    """{venue} when the message asks to cancel a booking at a named place — else None. The chat finds which reservation
    it is (by the venue's real name, from its receipt) and asks one yes; nothing is cancelled by asking."""
    m = _CANCEL.match(message or "")
    if not m:
        return None
    venue = re.sub(r"\s+(?:please|por favor|for (?:me|us)|tonight|today|tomorrow|on \w+day)$", "", m["venue"].strip(), flags=re.I).strip(" ,")
    return {"venue": venue} if len(venue) >= 2 else None


def booking_handoff(message: str, history: Optional[List[dict]] = None, now: Optional[datetime] = None) -> Optional[dict]:
    """S-66 (EU) step 5 · a full conductor turn that starts a booking IN THE CHAT — `booking_find` for the chat to run
    Find venues with (S-65) — or None, and the conductor carries on. ⛔ It no longer opens /booking-helper: the Psi-only
    link is retired; any kind of place, anywhere, is found the same way, and nothing is contacted by finding it."""
    message = spoken(message)
    c = cancel_request(message)
    if c is not None:
        response = f"Let me find your booking at {c['venue']} — I'll ask you once before I cancel anything."
        history = list(history or [])
        return {"response": response, "intents": ["booking"], "photos": [], "tools_used": [], "links": [], "hotels": [], "bookings": [],
                "itinerary": None, "action": None, "booking_ref": None, "itinerary_id": None, "payment_item": None, "saved_card": None,
                "messages": history + [{"role": "user", "content": message}, {"role": "assistant", "content": response}],
                "booking_cancel": c}
    f = find_request(message, now)
    if f is None:
        # Sasha 101 · a spoken request often arrives in pieces (a pause ends the turn): "Book a luxury dinner for two" /
        # "in Chamberí on Saturday at nine". The guest's last lines and this one, read together, as one request.
        users = [str(h.get("content") or "") for h in (history or []) if h.get("role") == "user"][-2:]
        for k in (1, 2):
            if len(users) >= k:
                joined = " ".join(re.sub(r"[.!?]+\s*$", "", u.strip()) for u in users[-k:] + [message])
                f = find_request(joined, now)
                if f is not None:
                    message = joined
                    break
    if f is None:
        return None
    where = f"{f['where']}{', ' + f['country'] if f.get('country') else ''}"
    response = f"Let me look for {f['what']} in {where} — from Google Maps; nobody is contacted by looking."
    if f.get("priority") is None:   # S-68 step 7 · asked ONCE, only when none was stated; best rated meanwhile
        response += f" {PRIORITY_QUESTION} I'll show them best rated until you say."
    history = list(history or [])
    return {
        "response": response, "intents": ["booking"], "photos": [], "tools_used": [], "links": [],
        "hotels": [], "bookings": [], "itinerary": None, "action": None, "booking_ref": None,
        "itinerary_id": None, "payment_item": None, "saved_card": None,
        "messages": history + [{"role": "user", "content": message}, {"role": "assistant", "content": response}],
        "booking_find": f,
        # S-64 step 11 · whatever else the message says (when, how many) as the parts of reservation/1 — for later
        "reservation_draft": _draft(message, now),
    }


def _draft(message: str, now: Optional[datetime]) -> dict:
    from .chat_request import draft
    return draft(message, now)


__all__ = ["booking_handoff", "find_request", "is_psi_booking", "plain_date", "plain_time", "plain_party", "PSI_SLOTS"]
