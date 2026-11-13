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
    for m in re.finditer(r"(?<![\d-])\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b(?![:.]\d)", w):
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


def time_(words: str, hhmm: str) -> bool:
    w = (words or "").casefold()
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    for hh, mm in re.findall(r"\b(\d{1,2})[:.h](\d{2})\b", w):
        if int(hh) == h and int(mm) == m:
            return True
    if m:
        return False   # 21:30 is said only with its minutes
    h12 = h - 12 if h > 12 else h
    pm = h >= 12
    for hh, ap in re.findall(r"\b(\d{1,2})\s*(am|pm|h)\b", w):
        if (ap == "h" and int(hh) == h) or (ap == "pm" and pm and int(hh) == h12) or (ap == "am" and not pm and int(hh) == h):
            return True
    for hh in re.findall(rf"\b(?:at|a las|sobre las)\s+{_NUM}\b(?![:.]\d)(?!\s*(?:people|persons?|personas?|of us|guests|pax))", w):
        if _n(hh) in (h, h12):   # Sasha 381 · "at 9" and "at nine" / "a las nueve" alike
            return True
    return False


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


__all__ = ["which", "said_all", "venue", "day", "days_in", "time_", "people", "MONTH_NAMES"]
