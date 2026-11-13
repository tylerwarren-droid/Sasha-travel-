"""Sasha 287 · THE CONSENT RULE (Tyler, 25 Oct): a booking request in the person's OWN words that gives the venue, the day, the time and
the people IS their yes. said_all() says whether this turn's words give all four, each matching the booking exactly; anything S2
filled in itself (a default party, a time it picked, a day it worked out from "next week") is not said — then she asks once.

Conservative by design: when a detail can't be read plainly from their words, it counts as NOT said (one question is the cost; a
detail sent that they never gave is the failure). English and Spanish, as she speaks."""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional

WEEKDAYS = (("monday", "lunes"), ("tuesday", "martes"), ("wednesday", "miércoles", "miercoles"), ("thursday", "jueves"),
            ("friday", "viernes"), ("saturday", "sábado", "sabado"), ("sunday", "domingo"))
MONTHS = (("jan", "ene"), ("feb",), ("mar",), ("apr", "abr"), ("may",), ("jun",), ("jul",), ("aug", "ago"), ("sep", "set"),
          ("oct",), ("nov",), ("dec", "dic"))
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
           "twelve": 12, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
           "diez": 10, "once": 11, "doce": 12}
_NUM = r"(\d{1,2}|" + "|".join(NUMBERS) + r")"
GENERIC = {"the", "and", "bar", "cafe", "café", "restaurant", "restaurante", "spa", "hotel", "club", "house", "casa", "de", "la", "el",
           "los", "las", "del", "london", "madrid", "barcelona", "lisbon", "soho", "shoreditch"}
#: their tap on a place card on their screen — they chose that venue (sasha's own marker on the message, never the model's)
TAPPED = re.compile(r"\[their tap on the card on their screen: (.+?) · place_id")


def _n(x: str) -> Optional[int]:
    return int(x) if x.isdigit() else NUMBERS.get(x)


def venue(words: str, name: str) -> bool:
    t = (TAPPED.search(words or "") or [None, ""])[1]
    if t and _base(t) == _base(name):
        return True
    w = (words or "").casefold()
    keys = [k for k in re.findall(r"[^\W\d_]+", _base(name)) if len(k) >= 4 and k not in GENERIC]
    return bool(keys) and any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", w) for k in keys)


def _base(name: str) -> str:
    return re.sub(r"\s*\(.*?\)\s*", " ", str(name or "")).casefold().strip()


#: Sasha 381f · every month as a person names it, EN + ES (full, short) — the ONE reader's table
MONTH_NAMES = {1: ("january", "jan", "enero", "ene"), 2: ("february", "feb", "febrero"), 3: ("march", "mar", "marzo"),
               4: ("april", "apr", "abril", "abr"), 5: ("may", "mayo"), 6: ("june", "jun", "junio"), 7: ("july", "jul", "julio"),
               8: ("august", "aug", "agosto", "ago"), 9: ("september", "sept", "sep", "septiembre", "setiembre", "set"),
               10: ("october", "oct", "octubre"), 11: ("november", "nov", "noviembre"), 12: ("december", "dec", "diciembre", "dic")}
_MONTH_OF = {name: n for n, names in MONTH_NAMES.items() for name in names}
_MON = "(" + "|".join(sorted(_MONTH_OF, key=len, reverse=True)) + r")\.?"
_ORDS = r"(?:st|nd|rd|th|º|°|o)?"
_NOT_PEOPLE = r"(?!\s*(?:people|persons?|personas?|of us|guests|pax|comensales|adults|h\b|:|\.\d|am\b|pm\b|o'?clock))"


def _next_md(today: date, month: int, day_: int, year: Optional[int] = None) -> Optional[date]:
    """A day and month as a person says them: that year when named, else the next one that isn't past."""
    for y in ((year,) if year else (today.year, today.year + 1)):
        try:
            d = date(y, month, day_)
        except ValueError:
            return None
        if year or d >= today:
            return d
    return None


def _next_d(today: date, day_: int) -> Optional[date]:
    """A day of the month alone ("the 13th", "el 13"): this month's, or next month's when it's already past."""
    y, m = today.year, today.month
    for _ in range(2):
        try:
            d = date(y, m, day_)
            if d >= today:
                return d
        except ValueError:
            pass
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return None


def days_in(words: str, today: date) -> List[date]:
    """Sasha 381f · THE ONE READER of every way a person names a day — EN and ES, resolved against `today` (the venue's local date):
    2026-11-13 · 13/11 · 13 Nov · 13th of November · November 13 · 13 de noviembre · the 13th · on the 13th · el 13 · el día 13 · today ·
    tonight · hoy · esta noche · tomorrow · mañana · the day after tomorrow · pasado mañana · Saturday · el sábado (the next one, today
    counting) · a range's days ("from 20 to 22 October", "del 20 al 22 de octubre"). → every date named, in the order said."""
    w = (words or "").casefold()
    found: List[tuple] = []

    def add(pos: int, d: Optional[date]) -> None:
        if d and all(d != x for _, x in found):
            found.append((pos, d))
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", w):
        try:
            add(m.start(), date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            pass
    for m in re.finditer(r"(?<![\d-])(?<!at )(?<!las )(?<!by )\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b(?![:.]\d)(?!\s*(?:am|pm|a\.m|p\.m|h\b))", w):   # "at 10.05" / "10.05pm" is a time
        y = int(m[3]) + (2000 if m[3] and len(m[3]) == 2 else 0) if m[3] else None
        add(m.start(), _next_md(today, int(m[2]), int(m[1]), y))
    for m in re.finditer(rf"(?<!for )(?<!para )\b(\d{{1,2}}){_ORDS}\s*(?:-|–|to|until|till|al|a)\s*(\d{{1,2}}){_ORDS}\s*(?:of\s+|de\s+)?{_MON}", w):
        add(m.start(), _next_md(today, _MONTH_OF[m[3]], int(m[1])))
        add(m.start(2), _next_md(today, _MONTH_OF[m[3]], int(m[2])))
    for m in re.finditer(rf"(?<!for )(?<!para )\b(\d{{1,2}}){_ORDS}\s+(?:of\s+|de\s+)?{_MON}(?![a-z])", w):   # "for 2" is people
        add(m.start(), _next_md(today, _MONTH_OF[m[2]], int(m[1])))
    for m in re.finditer(rf"\b{_MON}\s+(\d{{1,2}}){_ORDS}\b", w):
        add(m.start(), _next_md(today, _MONTH_OF[m[1]], int(m[2])))
    month_after = rf"(?!{_ORDS}\s*(?:-|–|to|al)?\s*\d*{_ORDS}\s*(?:of\s+|de\s+)?{_MON})"
    for m in re.finditer(rf"\b(?:the|el(?:\s+d[ií]a)?|d[ií]a)\s+(\d{{1,2}}){_ORDS}\b{month_after}{_NOT_PEOPLE}", w):
        add(m.start(), _next_d(today, int(m[1])))
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)\b{month_after}", w):
        add(m.start(), _next_d(today, int(m[1])))
    for m in re.finditer(r"\b(today|tonight|this evening|hoy|esta noche|esta tarde)\b", w):
        add(m.start(), today)
    for m in re.finditer(r"\b(the day after tomorrow|pasado ma[ñn]ana)\b", w):
        add(m.start(), date.fromordinal(today.toordinal() + 2))
    for m in re.finditer(r"\b(tomorrow|ma[ñn]ana)\b", w):
        before = w[max(0, m.start() - 12):m.start()]
        if re.search(r"(?:after|pasado|la|por la|de la)\s+$", before):   # "the day after tomorrow", "por la mañana" (the morning)
            continue
        add(m.start(), date.fromordinal(today.toordinal() + 1))
    for i_, names in enumerate(WEEKDAYS):
        for n in names:
            for m in re.finditer(rf"(?<!next )\b{n}\b", w):   # "next Friday" is this one or the week after's: never guessed (asked)
                add(m.start(), date.fromordinal(today.toordinal() + (i_ - today.weekday()) % 7))
    return [d for _, d in sorted(found, key=lambda x: x[0])]


def day(words: str, d: date, today: date) -> bool:
    """Their words name THIS day (the ONE reader, days_in)."""
    return d in days_in(words, today)


#: Sasha 381h · the side of the day a bare hour is on, as a person says it — RIGHT AFTER the time ("nine at night", "9 de la mañana")
_AFTER_PM = r"(?:pm|p\.\s?m\.?|in the afternoon|in the evening|at night|tonight|this evening|de la tarde|de la noche|por la tarde|por la noche|esta noche)"
_AFTER_AM = r"(?:am|a\.\s?m\.?|in the morning|this morning|de la ma[ñn]ana|por la ma[ñn]ana)"
#: … or anywhere in their words: what the meal or the part of the day says ("dinner … at nine", "tonight at nine", "breakfast at 9")
_CUE_PM = re.compile(r"\b(dinner|supper|cena|cenar|tonight|night|evening|afternoon|noche|tarde|pm|p\.m)\b")
_CUE_AM = re.compile(r"\b(breakfast|desayuno|desayunar|morning|am|a\.m)\b|\b(?:de|por) la ma[ñn]ana\b")
_CUE_LUNCH = re.compile(r"\b(lunch|comida|comer|almuerzo|almorzar)\b")
_MIN_WORDS = {"oclock": 0, "fifteen": 15, "thirty": 30, "forty five": 45, "forty-five": 45, "en punto": 0, "y media": 30,
              "y cuarto": 15}
_HOUR = r"(\d{1,2}|" + "|".join(sorted(NUMBERS, key=len, reverse=True)) + r")"
_NOT_A_TIME = r"(?!\s*(?:people|persons?|personas?|of us|guests|pax|comensales|adults|nights?|days?|noches|d[ií]as)\b)"


def _side(w: str, end: int) -> Optional[str]:
    """"pm" / "am" said right after the time, else None."""
    tail = w[end:end + 22]
    if re.match(rf"\s*{_AFTER_PM}(?![a-z])", tail):
        return "pm"
    if re.match(rf"\s*{_AFTER_AM}(?![a-z])", tail):
        return "am"
    return None


def _clock(h: int, mi: int, side: Optional[str], w: str, plain24: bool, open_between: Optional[tuple] = None, clock: bool = False,
           spoken: bool = True) -> tuple:
    """→ ("HH:MM", None) when the time is certain, or (None, (h, mi)) when it is a bare hour that could be either side of the day.
    A 24-hour time (13–23, 0, a leading zero) is certain as said; 12 is noon; 1–11 needs its side — said after it, or ONE side said
    anywhere in their words (the meal, the part of the day). Both sides said, or none → not read: asked "9am or 9pm?", never guessed —
    Sasha 381i · a clock time is read by what it IS and HOW it reached Sasha (`spoken`, from the door): TYPED "11:37" / "09:00" is the
    24-hour clock as written (a side said still wins: "dinner at 9:30" → 21:30); SPOKEN, ≤ 12:59 with no side said, it is asked —
    speech-to-text writes a spoken "nine" as "09:00" (Sasha 167's live failure: a romantic dinner at 09:00)."""
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None, None
    if side == "pm" and 1 <= h <= 11:
        h += 12
    elif side == "am" and h == 12:
        h = 0
    elif side is None and h == 12 and clock and spoken:   # Sasha 381i · a spoken "12:30" (speech-to-text) could be 00:30: asked
        if not (_CUE_PM.search(w) or _CUE_AM.search(w) or _CUE_LUNCH.search(w)):
            return None, (h, mi)
    elif side is None and 1 <= h <= 11 and not plain24:
        pm, am, lunch = bool(_CUE_PM.search(w)), bool(_CUE_AM.search(w)), bool(_CUE_LUNCH.search(w))
        if lunch and not (pm or am):
            pm, am = h <= 5, h >= 11   # "lunch at 1" is 13:00, "lunch at 11" is 11:00; "lunch at 8" is not read
        if pm == am and clock and not spoken:   # Sasha 381i · a TYPED clock time ("11:37", "9:30", "09:00") is the 24-hour clock as written
            pm, am = False, True
        if pm == am and open_between:   # the venue open on ONE side of that hour only: that side ("10:00" at an office open 7–21)
            lo, hi = open_between
            am, pm = (lo * 60 <= x * 60 + mi <= hi * 60 for x in (h, h + 12))
        if pm == am:
            return None, (h, mi)
        h += 12 if pm else 0
    return f"{h:02d}:{mi:02d}", None


def _heard() -> bool:
    """Sasha 381i · did THIS turn's words come through speech-to-text? — THE ONE door reader (venue_submit.door: its entry point
    recorded it), never guessed. No door recorded → typed (an entry point that transcribes always says so)."""
    from agapi import venue_submit as VS
    d = VS.door()
    return (d.get("words") if d else VS.words_heard()) == "spoken"


def _times(words: str, open_between: Optional[tuple] = None, spoken: Optional[bool] = None) -> tuple:
    spoken = _heard() if spoken is None else spoken
    w = " " + (words or "").casefold().replace("’", "'") + " "
    found: List[tuple] = []   # (pos, "HH:MM" | None, (h, mi) | None)
    taken: List[range] = []

    def add(m, h: int, mi: int, plain24: bool = False, side: Optional[str] = None, clock: bool = False) -> None:
        if any(m.start() < r.stop and r.start < m.end() for r in taken):   # one time, read once
            return
        taken.append(range(m.start(), m.end()))
        got, unsure = _clock(h, mi, side or _side(w, m.end()), w, plain24, open_between, clock, spoken)
        if got or unsure:
            found.append((m.start(), got, unsure))
    # spoken forms first (they hold a number word): half past nine · quarter past/to nine · half nine · las nueve y media / menos cuarto
    for m in re.finditer(rf"\b(half|quarter)\s+(past|to)\s+{_HOUR}\b", w):
        h, mi = _n(m[3]), 30 if m[1] == "half" else 15
        if h is not None:
            add(m, (h - 1) % 12 or 12 if m[2] == "to" else h, 60 - mi if m[2] == "to" else mi)
    for m in re.finditer(rf"\bhalf\s+{_HOUR}\b{_NOT_A_TIME}", w):
        if _n(m[1]) is not None:
            add(m, _n(m[1]), 30)
    for m in re.finditer(rf"\b(?:a\s+)?(?:las|la)\s+{_HOUR}(?![:.h]\d)(?:\s+(y media|y cuarto|menos cuarto|en punto))?\b{_NOT_A_TIME}", w):
        h = _n(m[1])
        if h is None:
            continue
        if m[2] == "menos cuarto":
            add(m, (h - 1) % 12 or 12, 45)
        else:
            add(m, h, _MIN_WORDS.get(m[2] or "", 0))
    # clock forms: 21:30 · 9:30pm · 9.30 p.m. · 21h30 · 21h · 9 pm · nine pm · nine thirty
    for m in re.finditer(r"(?<![\d/.:-])(\d{1,2})([:.h])(\d{2})(?![\d/.:-]?\d)", w):
        if m[2] == "." and not (_side(w, m.end()) or re.search(r"\b(?:at|a las|sobre las|around|by)\s+$", w[:m.start()])):
            continue   # "20.11" is a day; "9.30 pm" / "at 21.30" is a time
        h = int(m[1])
        add(m, h, int(m[3]), plain24=h >= 13 or h == 0, clock=True)
    for m in re.finditer(r"\b(?:at|a las|by|from|sobre las)\s+([01]\d|2[0-3])([0-5]\d)h?\b", w):   # "at 2130", "a las 2100h"
        add(m, int(m[1]), int(m[2]), plain24=True)
    for m in re.finditer(r"(?<![\d/.:-])(\d{1,2})h(?![a-z\d])", w):
        add(m, int(m[1]), 0, plain24=int(m[1]) >= 13 or int(m[1]) == 0, clock=True)
    for m in re.finditer(rf"\b{_HOUR}\s+(o'?clock|thirty|fifteen|forty[- ]five)\b", w):
        if _n(m[1]) is not None:
            add(m, _n(m[1]), _MIN_WORDS[m[2].replace("-", " ").replace("'", "")])
    for m in re.finditer(rf"(?<!for )(?<!para )(?<!of )(?<!x)\b{_HOUR}(?:\s*o'?clock)?\s*(?=(?:{_AFTER_PM}|{_AFTER_AM})(?![a-z]))", w):   # 9pm · 10 in the morning · nueve de la noche
        if _n(m[1]) is not None:
            add(m, _n(m[1]), 0)
    # a bare hour after "at" / "sobre las": "at nine", "at 9" — its side said, or asked
    for m in re.finditer(rf"\b(?:at|around|by)\s+{_HOUR}\b(?![:.h]\d){_NOT_A_TIME}", w):
        if _n(m[1]) is not None:
            add(m, _n(m[1]), 0)
    for m in re.finditer(r"\b(noon|midday|mediod[ií]a)\b", w):
        add(m, 12, 0, plain24=True)
    for m in re.finditer(r"\b(midnight|medianoche)\b", w):
        add(m, 0, 0, plain24=True)
    found.sort(key=lambda x: x[0])
    sure, unsure = [], []
    for _, t, u in found:
        if t and t not in sure:
            sure.append(t)
        if u and u not in unsure:
            unsure.append(u)
    return sure, unsure


def times_in(words: str, open_between: Optional[tuple] = None, spoken: Optional[bool] = None) -> List[str]:
    """Sasha 381h · THE ONE READER of every way a person says a booking's time — EN and ES → every time they said, "HH:MM", in order:
    21:30 · 9:30pm · 9.30 p.m. · 21h30 · 21h · half past nine · half nine · quarter past / to nine · nine thirty · nine o'clock · 9pm ·
    "at nine" with its side (at night, tonight, dinner, in the morning, breakfast, lunch) · a las nueve y media · las nueve y cuarto ·
    las nueve menos cuarto · a las nueve de la noche · noon · midnight. A bare hour whose side of the day they didn't say is NOT read
    (unsure_hours names it: asked "9am or 9pm?") — a time they didn't say never reaches a booking. `open_between` (start, end hours):
    the venue's own hours, when known — a bare hour it is open on ONE side of only is that side; open on both → still asked."""
    return _times(words, open_between, spoken)[0]


def unsure_hours(words: str, open_between: Optional[tuple] = None, spoken: Optional[bool] = None) -> List[tuple]:
    """Sasha 381h · the bare hours they said without saying which side of the day: [(9, 0)] for "at nine" — asked, never guessed."""
    return _times(words, open_between, spoken)[1]


def times_matching(words: str) -> List[str]:
    """Sasha 381h · a time they name to PICK one of the options on their screen ("the 7:44"): every time they said, a bare hour as
    both its sides — matched against what was offered (never a time sent on its own)."""
    sure, unsure = _times(words, spoken=True)   # "the 7:44" names the 07:44 or the 19:44 on their screen (both, matched to the list)
    return sure + [f"{h + d:02d}:{mi:02d}" for h, mi in unsure for d in (0, 12) if h + d < 24]


def time_(words: str, hhmm: str) -> bool:
    """Their words say THIS time (the ONE reader, times_in)."""
    return hhmm in times_in(words)


def people(words: str, n: int) -> bool:
    w = (words or "").casefold()
    pats = (rf"\bfor\s+{_NUM}\b(?!\s*(?:am|pm|h\b|:|\.\d|o'?clock))", rf"\bpara\s+{_NUM}\b(?!\s*(?:am|pm|h\b|:))",
            rf"\b{_NUM}\s+(?:people|persons?|personas?|of us|guests|adults|pax|comensales)\b", rf"\bparty of\s+{_NUM}\b",
            rf"\btable for\s+{_NUM}\b", rf"\bmesa para\s+{_NUM}\b", rf"\bx\s?{_NUM}\b")
    got = {_n(x) for p in pats for x in re.findall(p, w)}
    if n == 1 and re.search(r"\b(just me|only me|for one|solo yo|para mí|para mi)\b", w):
        return True
    if n == 2 and re.search(r"\b(for two|for 2|the two of us|nosotros dos|para dos)\b", w):
        return True
    return n in got


def which(words: str, name: str, at: str, party: int, today: date) -> Dict[str, bool]:
    """→ {venue, day, time, people}: True for each detail THEIR words give, matching this booking."""
    d = date.fromisoformat(at[:10])
    return {"venue": venue(words, name), "day": day(words, d, today), "time": time_(words, at[11:16]), "people": people(words, int(party))}


def said_all(words: str, name: str, at: str, party: int, today: date) -> bool:
    return all(which(words, name, at, party, today).values())


__all__ = ["which", "said_all", "venue", "day", "days_in", "times_in", "unsure_hours", "times_matching", "time_", "people", "MONTH_NAMES"]
