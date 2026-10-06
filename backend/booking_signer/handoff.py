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


#: Sasha 104 · a Spanish request, read by the same parsers: only booking phrasing is rewritten, and only when the message
#: reads as Spanish. Place names and qualifiers ("algo romántico") are left as written.
_ES_MARK = re.compile(r"\b(cena|cenar|comida|almuerzo|desayuno|mesa|reserv\w*|res[eé]rvame|para\s+(?:\d|dos|tres|cuatro|seis)|"
                      r"s[aá]bado|domingo|lunes|martes|mi[eé]rcoles|jueves|viernes|a las|personas|quiero|quisiera|busco|b[uú]scame)\b", re.I)
_ES_NUM = {"una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
           "diez": 10, "once": 11, "doce": 12}
_ES_DAYS = {"lunes": "monday", "martes": "tuesday", "miércoles": "wednesday", "miercoles": "wednesday", "jueves": "thursday",
            "viernes": "friday", "sábado": "saturday", "sabado": "saturday", "domingo": "sunday"}
_ES_WORDS = [(r"\b(?:quiero|quisiera|queremos|necesito|necesitamos)\s+(?:reservar|una reserva(?:\s+de)?)\b", "book"),
             (r"\b(?:res[eé]rvame|res[eé]rvanos|reserva|reservar|reservad)\b", "book"),
             (r"\b(?:b[uú]scame|b[uú]scanos|busca|buscar|busco|buscamos)\b", "find"),
             (r"\b(?:quiero|quisiera|queremos)\b", "i want"),
             (r"\bcenar\b|\bcena\b", "dinner"), (r"\b(?:comida|almuerzo|almorzar|comer)\b", "lunch"),
             (r"\bdesayuno\b", "breakfast"), (r"\bmesa\b", "table"), (r"\bun restaurante\b", "a restaurant"),
             (r"\b(?:una|un)\s+(?=table|dinner|lunch|breakfast|restaurant)", "a "),
             (r"\b(\d{1,2})\s+de\s+la\s+(?:noche|tarde)\b", r"\1pm"),
             (r"\b(?:esta\s+noche)\b", "tonight"), (r"\bhoy\b", "today"),
             (r"(?<!la )(?<!de )\bma[nñ]ana\b(?!\s+por\s+la)", "tomorrow"),
             (r"\bpara\s+(?:el|este|esta)\s+", "on "), (r"\b(?:el|este|esta)\s+(?=(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b)", "on "),
             (r"\ba\s+las\b", "at"), (r"\bcerca\s+de(?:l)?\b", "near"), (r"\ben\b", "in")]


def _es(t: str) -> str:
    if not _ES_MARK.search(t):
        return t
    for rx, rep in _ES_WORDS:
        t = re.sub(rx, rep, t, flags=re.I)
    t = re.sub(r"\bpara\s+(\d{1,2}|" + "|".join(_ES_NUM) + r")\b(?:\s+personas)?",
               lambda m: f"for {m[1] if m[1].isdigit() else _ES_NUM[m[1].lower()]}", t, flags=re.I)
    t = re.sub(r"\b(\d{1,2}|" + "|".join(_ES_NUM) + r")\s+personas\b",
               lambda m: f"{m[1] if m[1].isdigit() else _ES_NUM[m[1].lower()]} people", t, flags=re.I)
    return re.sub(r"\b(" + "|".join(_ES_DAYS) + r")\b", lambda m: _ES_DAYS[m[1].lower()], t, flags=re.I)


def spoken(message: str) -> str:
    """Sasha 88 · a request SPOKEN to Sasha reads like a typed one: speech-to-text writes "9 p.m.", "nine p.m.",
    "9 P.M." — the parsers read "9pm". Sasha 104 · "2100", "21h" and a Spanish request read the same way."""
    t = _es(message or "")
    t = re.sub(r"\b([ap])\.\s?m\.?(?=\W|$)", lambda m: m[1].lower() + "m", t, flags=re.I)
    t = re.sub(r"\b(\d{1,2})\s+([ap]m)\b", r"\1\2", t, flags=re.I)
    # Sasha 104 · "at 2100", "a las 2130", "2100h" — a 24-hour clock written without its colon is that time
    t = re.sub(r"\b(at|a las|by|from)\s+([01]\d|2[0-3])([0-5]\d)h?\b", r"\1 \2:\3", t, flags=re.I)
    t = re.sub(r"\b([01]?\d|2[0-3])h(?:([0-5]\d))?\b", lambda m: f"{int(m[1])}:{m[2] or '00'}", t, flags=re.I)   # "21h", "21h30"
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


#: Sasha 104 · the day, time or party said BEFORE the area: "dinner for 2 on Saturday at 21:00 in Chamberí"
#: "at a luxury restaurant" names the PLACE, never a time: the when-part never takes "at a / an / the …"
_WHEN = (r"(?:\s+(?:for|on|at(?!\s+(?:an?|the)\b)|this|next|tomorrow|tonight|today|el|a las|para)\b"
         r"(?:(?!\bat\s+(?:an?|the)\b)[^?.!;]){0,48}?)?")
#: S-66 (EU) step 5 · "find / book / reserve … {X} in {Y}" for ANY kind of place
_FIND = re.compile(r"\b(?:find|book|reserve|look for|search for|get|add|make)\s+(?:me\s+|us\s+)?(?:an?\s+|some\s+|the\s+)?"
                   r"(?P<what>[a-z][\w'’ -]{1,58}?)" + _WHEN + r"\s+(?:in|near|around)\s+(?P<where>[^?.!;]{2,80})", re.I)
#: Sasha 101 · how a request is SPOKEN without "book": "I'd like a luxury dinner in …", "can you get us a table in …".
#: Taken only when what is asked for is a bookable thing (a table, a meal, a place to book) — "I want to see the museum
#: in Madrid" is not a booking.
_SOFT = re.compile(r"\b(?:i(?:'d| would) like|we(?:'d| would) like|i want|we want|i need|we need|looking for|"
                   r"can (?:i|we|you) (?:get|have|find)|could (?:i|we|you) (?:get|have|find)|"
                   r"(?:let'?s|let us) (?:book|get|have))\s+(?:to (?:book|reserve|have|get)\s+)?(?:me\s+|us\s+)?"
                   r"(?:an?\s+|some\s+|the\s+)?(?P<what>[a-z][\w'’ -]{1,58}?)" + _WHEN + r"\s+(?:in|near|around)\s+(?P<where>[^?.!;]{2,80})", re.I)
#: a request that STARTS with the thing itself: "lunch for 4 in Malasaña tomorrow at two", "a table for two in Chamberí…"
_BARE = re.compile(r"^\s*(?:(?:an?|some)\s+)?(?P<what>(?:[a-záéíóúñ'’-]+\s+){0,3}?(?:table|dinner|lunch|breakfast|brunch|supper)"
                   r"(?:\s+for\s+\w+(?:\s+(?:people|of us))?)?)" + _WHEN + r"\s+(?:in|near|around)\s+(?P<where>[^?.!;]{2,80})", re.I)
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
                        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
                        # Sasha 167 · "in Hoi An, October 27 at 09:00": the date ends the place (it was searched as "October 27 restaurant")
                        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
                        r"nov(?:ember)?|dec(?:ember)?|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)\b.*$", re.I)


#: Sasha 126 · a country said by name after the place (only the countries venue_read knows)
COUNTRY_NAMES = {"spain": "ES", "españa": "ES", "portugal": "PT", "france": "FR", "italy": "IT", "italia": "IT", "germany": "DE",
                 "austria": "AT", "uk": "GB", "united kingdom": "GB", "england": "GB", "ireland": "IE", "vietnam": "VN",
                 "viet nam": "VN", "kenya": "KE"}

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


#: Sasha 101 · the places a guest SAYS that speech-to-text mangles: "Chamberí" came back "Chambhuri" and the search found
#: India. A near-miss of one of these (and no country said) is that neighbourhood, in its city and country.
KNOWN_PLACES = {
    "Chamberí": ("Madrid", "ES"), "Malasaña": ("Madrid", "ES"), "Chueca": ("Madrid", "ES"), "Lavapiés": ("Madrid", "ES"),
    "La Latina": ("Madrid", "ES"), "Salamanca": ("Madrid", "ES"), "Retiro": ("Madrid", "ES"), "Sol": ("Madrid", "ES"),
    "Huertas": ("Madrid", "ES"), "Chamartín": ("Madrid", "ES"), "Tetuán": ("Madrid", "ES"), "Arganzuela": ("Madrid", "ES"),
    "Moncloa": ("Madrid", "ES"), "Argüelles": ("Madrid", "ES"), "Conde Duque": ("Madrid", "ES"), "Las Letras": ("Madrid", "ES"),
    "Madrid": (None, "ES"),
}


def known_place(where: str) -> Optional[tuple]:
    """(neighbourhood, its city, its country) when `where` is one of KNOWN_PLACES or a near-miss of it, else None."""
    import difflib
    import unicodedata
    fold = lambda x: unicodedata.normalize("NFD", x).encode("ascii", "ignore").decode().lower().strip()
    names = {fold(k): k for k in KNOWN_PLACES}
    w = fold(where)
    # Sasha 158 · a near-miss must be close AND of a similar length: "Seoul" is not "Sol" (it searched Madrid)
    near = [m for m in difflib.get_close_matches(w, list(names), n=3, cutoff=0.8) if abs(len(m) - len(w)) <= 2]
    hit = names.get(w) or (names[near[0]] if near else None)
    return (hit, *KNOWN_PLACES[hit]) if hit else None


#: Sasha 104 · the qualities a guest asks for — kept in what is searched for, wherever in the request they were said
_QUALITY = re.compile(r"\b(luxury|luxurious|upscale|fancy|fine[- ]dining|romantic|cheap|casual|quiet|cosy|cozy|vegetarian|vegan|"
                      r"lujo|lujoso|rom[aá]ntico|rom[aá]ntica|barato|tranquilo)\b", re.I)
LUXURY = ("luxury", "luxurious", "upscale", "fancy", "fine dining", "fine-dining", "lujo", "lujoso")


def qualities(text: str) -> List[str]:
    return list(dict.fromkeys(q.lower() for q in _QUALITY.findall(text or "")))


#: Sasha 152 · a priority SAID inside the request ("a tattoo parlor, top rated ones in Madrid") is the priority (plain_priority
#: reads it), never part of what is searched for — the founder heard "Let me look for tattoo parlor Top rated ones"
_PRIORITY_WORDS = re.compile(r"(?:^|\s|,)\s*(?:the\s+)?(?:best[- ]rated|top[- ]rated|highly[- ]rated|best[- ]reviewed|well[- ]reviewed|"
                             r"good reviews|the best|best)(?:\s+ones?)?\b", re.I)


def _without_priority(what: str) -> str:
    out = " ".join(_PRIORITY_WORDS.sub(" ", what).split()).strip(" ,")
    return out if len(out) >= 2 else what


def find_request(message: str, now: Optional[datetime] = None) -> Optional[dict]:
    """{what, where, country?, near?} when the message asks for a kind of place in a place — else None. Nothing guessed:
    a country is taken only when written as a two-letter code ("Nairobi, KE")."""
    said = message
    # Sasha 152 · ", top rated ones in Madrid": a comma before a stated priority doesn't end the request
    message = re.sub(r",\s*(?=(?:the\s+)?(?:best|top|highly|well)[- ]?(?:rated|reviewed)?\b)", " ", message or "", flags=re.I)
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
    # Sasha 173 · "make an appointment FOR A SPA in Hanoi on the 13th…": the what was "appointment" (the "for a spa" went with
    # the time) and Google answered with a church and the sea. A booking word alone is not a kind of place: the kind said is.
    if re.fullmatch(r"(?:an?\s+)?(?:appointment|booking|reservation|slot|session|treatment|cita|reserva)s?", what, re.I):
        km = re.search(r"\b(?:for|at|with)\s+(?:an?|the|some)\s+(?P<k>[a-záéíóúñ' -]{2,30}?)\s+(?:in|near|around)\s", message or "", re.I)
        if km:
            what = km["k"].strip()
    what = re.sub(r"^(?:an?\s+)?(?:appointment|booking|reservation|table)\s+(?:at|for|with)\s+(?:an?|the)\s+", "", what, flags=re.I) or what
    # Sasha 170 · "a massage at a spa" is a massage spa (it was searched, and said, as "massage at a spas")
    what = re.sub(r"\b([a-z]+)\s+at\s+an?\s+(spa|salon|studio|parlou?r|bar|restaurant)\b", r"\1 \2", what, flags=re.I)
    # Sasha 167 · "make me a dinner reservation", "add a dinner booking": the meal is searched for, not the word "reservation"
    what = re.sub(r"\s+(?:reservation|booking|reserva)s?$", "", what, flags=re.I).strip() or what
    # Sasha 104 · a short sentence of qualifiers after the request ("Something luxurious and romantic.") is part of what
    # is searched for — every qualifier the guest said, kept
    after = re.split(r"[.!;]\s*", (message or "")[m.end():], maxsplit=1)
    extra = after[1] if len(after) > 1 else ""
    q = re.sub(r"^(?:something|somewhere|a place|ideally|preferably|it should be|we want|i want|i'd like)\s+", "", extra.strip(" .!?"), flags=re.I)
    if re.fullmatch(r"(?:thanks?(?: you)?(?: so much| very much)?|thank you,? sasha|cheers|gracias|please|por favor|ok|okay)", q, re.I):
        q = ""   # Sasha 167 · "… Thank you." is courtesy, not a quality searched for ("Thank you dinner")
    if q and len(q.split()) <= 6 and not re.search(r"\d|\b(?:for|on|at|in|near|tomorrow|today|tonight)\b", q, re.I):
        what = f"{q} {what}"
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
    cn = re.fullmatch(r"(.+?),\s*([^,]+)", where)
    if cm:
        where, country = cm[1].strip(), cm[2].upper()
    elif cn and cn[2].strip().lower() in COUNTRY_NAMES:   # Sasha 126 · "in Hoi An, Vietnam": the country, not a qualifier
        where, country = cn[1].strip(), COUNTRY_NAMES[cn[2].strip().lower()]
    elif "," in where:
        # Sasha 104 · "in Chamberí, somewhere romantic": the place, then a qualifier — kept with what is searched for
        head, tail = where.split(",", 1)
        tail = re.sub(r"^\s*(?:somewhere|something|algo|alg[uú]n sitio|a place)\s+", "", tail).strip(" .")
        if re.fullmatch(r"[A-ZÁÉÍÓÚÑ][\w'’.-]*(?:\s+[A-ZÁÉÍÓÚÑ][\w'’.-]*){0,2}", tail.strip()):
            where = f"{head.strip()}, {tail.strip()}"   # Sasha 158 · "Kreuzberg, Berlin": a place, then its city
        elif known_place(head.strip()) or len(tail.split()) <= 4:
            where = head.strip()
            if tail and not known_place(tail):
                what = f"{tail} {what}"
    if len(what) < 2 or len(where) < 2:
        return None
    if country is None:
        kp = known_place(where)
        if kp:   # "Chambhuri" → Chamberí, Madrid · ES (the search is then in the right country)
            where, country = (f"{kp[0]}, {kp[1]}" if kp[1] else kp[0]), kp[2]
    # Sasha 104 · a quality said anywhere (a request joined from several lines kept only "Dinner") is kept
    missing_q = [q for q in qualities(message) if q not in what.lower()]
    if missing_q:
        what = " ".join(missing_q + [what])
    at = plain_open_at(message, now)
    what = _without_priority(what)   # Sasha 152 · the priority is kept as the priority, not searched for
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


#: Sasha 140 · a bare "<kind of place> in <place>" is a search (never the model's): the kinds Sasha finds and books
_BARE_KIND = re.compile(r"^\s*(?:an?\s+|some\s+|the\s+)?(?:(?:best|good|great|top)\s+)?(?:[a-záéíóúñ]+\s+){0,2}(?:spas?|massages?|tattoo(?:\s+(?:studios?|parlou?rs?|shops?))?|"
                        r"(?:hair|nail|beauty)\s+salons?|hairdressers?|barber(?:shop)?s?|gyms?|yoga(?:\s+studios?)?|pilates|restaurants?|dinner|lunch|"
                        r"brunch|bars?|caf[eé]s?|wine\s+bars?|sushi|tapas|places\s+to\s+eat)\s+(?:in|near|around)\s+[A-ZÁÉÍÓÚa-z]", re.I)
# Sasha 156 · plurals too: "restaurants in Madrid tonight" fell through to the model's curated (Vietnam) dining list


#: Sasha 158 · ANY "<kind of place> in/near <place>" is a search ("a dentist in Buenos Aires", "pottery class in Kyoto") —
#: short, and not a trip, a stay, a flight or a question about a place
_ANY_KIND = re.compile(r"^\s*(?:(?:please\s+)?(?:i need|i'?m looking for|looking for|any|show me|find me|get me)\s+)?(?:an?\s+|some\s+|the\s+)?"
                       r"(?:(?:best|good|great|top|nice|cheap|local)\s+)?(?P<what>[a-záéíóúñü'’ -]{2,40}?)\s+(?:in|near|around)\s+\S", re.I)
_NOT_A_SEARCH = re.compile(r"\b(trip|itinerary|days?|nights?|weekend|week|plan|visit|travel|things to do|weather|flights?|fly|"
                           r"hotels?|hostels?|stay|apartments?|live|living|move|moving|relocat\w*|history|news|time|people|"
                           r"what|where|when|why|how|who|is|are|was|do|does|can|should|tell|about|ones?|rated|reviewed|options|choices|"
                           r"i|i'm|we|you|my|our|like|love|loved|enjoy|enjoyed|went|had|have|miss|hate|want)\b", re.I)


def any_kind(message: str) -> Optional[str]:
    m = _ANY_KIND.match(message or "")
    # Sasha 169 · the length is the request's, not its day, time and party: "a cooking class in Hoi An on the 17th at 10 in the
    # morning for two" (15 words) is a search
    head = re.split(r"\s+(?:on|at|for|this|next|tomorrow|tonight|today)\s+", message or "", maxsplit=1, flags=re.I)[0]
    if not m or len(head.split()) > 12 or len(m["what"].split()) > 4 or _NOT_A_SEARCH.search(m["what"]):
        return None
    return m["what"]


#: Sasha 158 · NAME IT: "book Casa Lucio tomorrow at 9 for 2" — that venue, by name (any city it is in, or the one said)
_NAMED = re.compile(r"^\s*(?:(?:please|can you|could you)\s+)?(?:book|reserve)\s+(?:me\s+|us\s+)?(?:a\s+table\s+at\s+|at\s+)?"
                    r"(?P<name>(?!(?:an?|the|some|me|us|my|dinner|lunch|breakfast|brunch|a table|table)\b)[^,?.!;]{2,60}?)"
                    r"(?:\s*,?\s+in\s+(?P<where>[A-ZÁÉÍÓÚÑ][^,?.!;]{1,40}?))?"
                    r"(?P<rest>\s+(?:tomorrow|today|tonight|at|for|on|this|next|el|a las|para)\b.*)?\s*[.!?]?\s*$", re.I)
_KINDS_NOT_NAMES = re.compile(r"\b(table|dinner|lunch|brunch|breakfast|restaurant|spa|massage|haircut|appointment|class|tour|session|"
                              r"tattoo|barber|salon|hotel|room|flight|car|taxi|something|somewhere)s?\b", re.I)


def restaurant_time(bare: dict) -> str:
    """Sasha 158 · a bare hour at a RESTAURANT is the afternoon or evening ("at 9" → 21:00, "at 2" → 14:00); 12 is noon."""
    h = bare["hour"] if bare["hour"] == 12 else bare["hour"] + 12
    return f"{bare['day']}T{h:02d}:{bare['minute']:02d}"


def named_request(message: str) -> Optional[dict]:
    m = _NAMED.match(message or "")
    if not m or not (m["rest"] or m["where"]):
        return None
    name = " ".join(m["name"].split()).strip(" ,")
    if name == name.lower():   # spoken: "casa lucio" → "Casa Lucio" (Google finds either; the guest reads the name)
        name = name.title()
    if _KINDS_NOT_NAMES.search(name) or len(name.split()) > 6:
        return None
    return {"what": name, "where": (m["where"] or "").strip() or None, "named": True}


def booking_handoff(message: str, history: Optional[List[dict]] = None, now: Optional[datetime] = None) -> Optional[dict]:
    """S-66 (EU) step 5 · a full conductor turn that starts a booking IN THE CHAT — `booking_find` for the chat to run
    Find venues with (S-65) — or None, and the conductor carries on. ⛔ It no longer opens /booking-helper: the Psi-only
    link is retired; any kind of place, anywhere, is found the same way, and nothing is contacted by finding it."""
    said = message
    message = spoken(message)
    c = cancel_request(said) or cancel_request(message)   # Sasha 104 · the guest's own words first ("cancela la reserva en X")
    if c is not None:
        response = f"Let me find your booking at {c['venue']} — I'll ask you once before I cancel anything."
        history = list(history or [])
        return {"response": response, "intents": ["booking"], "photos": [], "tools_used": [], "links": [], "hotels": [], "bookings": [],
                "itinerary": None, "action": None, "booking_ref": None, "itinerary_id": None, "payment_item": None, "saved_card": None,
                "messages": history + [{"role": "user", "content": message}, {"role": "assistant", "content": response}],
                "booking_cancel": c}
    # the stay is what's being booked ("a hotel in Madrid"), not a place said ("… near my hotel")
    if re.search(r"\b(?:hotels?|hostels?|apartments?|alojamiento|a room|habitaci[oó]n)\s+(?:in|at|en|near|cerca)\b", message or "", re.I) and \
            not re.search(r"\b(dinner|lunch|table|restaurant|cena|mesa)\b", message or "", re.I):
        return None   # Sasha 137 · a stay is the hotel flow's (cards with Reserve (TEST), or a real request) — never a table search
    named = named_request(message)
    f = None if named else find_request(message, now)
    if f is None and not named and (_BARE_KIND.match(message or "") or any_kind(message)):   # Sasha 140/158 · "<kind> in <place>": a search
        f = find_request("find " + re.sub(r"^\s*(?:please\s+)?(?:i need|i'?m looking for|looking for|any|show me|find me|get me)\s+", "",
                                          message.strip(), flags=re.I), now)
    if named:
        f = {k: v for k, v in named.items() if v is not None}
        at = plain_open_at(message, now)
        if at:
            f["open_at"] = at
        else:   # "tomorrow at 9": the hour is kept, am/pm decided once the venue's kind is known (a restaurant: the evening)
            hm = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?(?!\s*(?:am|pm|h\b|:))\b", message or "", re.I)
            day = plain_date(message or "", now)
            if hm and day and 1 <= int(hm[1]) <= 12:
                f["bare_time"] = {"day": day, "hour": int(hm[1]), "minute": int(hm[2] or 0)}
    if f is None and not named:
        # Sasha 167 · said loosely, as a voice note does: "romantic booking for two at a restaurant in Hoi An, October 27 at 09:00"
        lm = _LOOSE.search(message or "")
        if lm and _LOOSE_ASK.search(message or ""):
            f = find_request(f"find {lm['kind']} in {lm['where']}", now)
            if f is not None:
                at = plain_open_at(message, now)
                f = {**f, **({"open_at": at} if at else {}), **({"priority": p} if (p := plain_priority(message, None)) else {})}
                missing_q = [q for q in qualities(message) if q not in f["what"].lower()]
                if missing_q:
                    f["what"] = " ".join(missing_q + [f["what"]])
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
    # Sasha 158 · one sentence before; the machinery (sources, ranking, routes) is never explained to the guest
    response = (f"Looking up {f['what']}{' in ' + f['where'] if f.get('where') else ''}." if f.get("named")
                else f"Here are the best-rated {_plural_kind(f['what'])} in {f['where']}.")
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


#: Sasha 167 · a kind of place in a place, anywhere in a sentence that asks to book — "… at a restaurant in Hoi An, …"
_LOOSE = re.compile(r"\b(?:at|to)\s+(?:an?\s+|the\s+|some\s+)?(?P<kind>(?:[a-záéíóúñ]+\s+){0,2}?(?:restaurant|bistro|bar|caf[eé]|spa|"
                    r"steakhouse|brasserie|tavern|trattoria|pizzeria|salon|studio))\s+(?:in|near|around)\s+(?P<where>[A-ZÁÉÍÓÚ][^?.!;]{1,80})", re.I)
_LOOSE_ASK = re.compile(r"\b(book|booking|reserve|reservation|table|res[eé]rva\w*)\b", re.I)


def _plural_kind(what: str) -> str:
    w = (what or "places").strip()
    if re.search(r"\b(dinner|lunch|brunch|breakfast|supper|food|drinks?|coffee|cocktails|sushi|tapas)$", w, re.I):
        return f"places for {w}"
    if re.search(r"(ss|sh|ch|x)$", w, re.I):
        return w + "es"
    if re.search(r"[^aeiou]y$", w, re.I):
        return w[:-1] + "ies"
    return w if re.search(r"(s|pilates)$", w, re.I) else w + "s"


def _draft(message: str, now: Optional[datetime]) -> dict:
    from .chat_request import draft
    return draft(message, now)


__all__ = ["booking_handoff", "find_request", "is_psi_booking", "plain_date", "plain_time", "plain_party", "PSI_SLOTS"]
