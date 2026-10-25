"""Sasha 287 · THE CONSENT RULE (Tyler, 25 Oct): a booking request in the person's OWN words that gives the venue, the day, the time and
the people IS their yes. said_all() says whether this turn's words give all four, each matching the booking exactly; anything S2
filled in itself (a default party, a time it picked, a day it worked out from "next week") is not said — then she asks once.

Conservative by design: when a detail can't be read plainly from their words, it counts as NOT said (one question is the cost; a
detail sent that they never gave is the failure). English and Spanish, as she speaks."""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, Optional

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


def day(words: str, d: date, today: date) -> bool:
    w = (words or "").casefold()
    gap = (d - today).days
    if gap == 0 and re.search(r"\b(today|tonight|hoy|esta noche)\b", w):
        return True
    if gap == 1 and re.search(r"\b(tomorrow|ma[ñn]ana)\b", w) and not re.search(r"\bpasado ma[ñn]ana\b", w):
        return True
    if 0 <= gap <= 6 and any(re.search(rf"\b{n}\b", w) for n in WEEKDAYS[d.weekday()]):
        return True
    if d.isoformat() in w:
        return True
    mon = "|".join(MONTHS[d.month - 1])
    if re.search(rf"\b0?{d.day}(st|nd|rd|th)?\s*(de\s+)?({mon})\w*\b", w) or re.search(rf"\b({mon})\w*\s+0?{d.day}(st|nd|rd|th)?\b", w):
        return True
    return bool(re.search(rf"\b0?{d.day}[/.-]0?{d.month}\b", w))


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
    for hh in re.findall(r"\b(?:at|a las|sobre las)\s+(\d{1,2})\b(?![:.]\d)(?!\s*(?:people|persons?|personas?|of us|guests|pax))", w):
        if int(hh) in (h, h12):
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


__all__ = ["which", "said_all", "venue", "day", "time_", "people"]
