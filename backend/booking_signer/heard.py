"""S-59 · WHAT THE VENUE ACTUALLY SAID — the time, day, party and name in its own words, checked against the request.

30 Sept 2026, the first real booking: Sasha asked La Contra for 13:00 under Warren. The venue said "Vale, a las tres de
hora" after "¿A qué hora?", and "¿Me puede repetir apellido? Apellido Tyler", then "Pues ya tiene la reserva". The
model read "accepted as asked". It was not: the venue may hold 15:00, under "Tyler".

So a yes is only a yes when nothing the VENUE said contradicts the request. This is deterministic — no model — and
conservative: any time, day, party or name the venue states that is not the one asked for makes the call `unclear`,
with the venue's lines quoted. A question that only repeats the request ("¿El viernes dos?") agrees with it.

Covers Spanish, English and Portuguese, the languages Sasha calls in today. Anything it cannot parse it leaves alone —
it only ever turns a yes into unclear, never the reverse.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, time
from typing import List, Mapping, Optional


def _f(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()


_NUM = {
    # es
    "una": 1, "uno": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
    "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintiuna": 21, "veintidos": 22,
    "veintitres": 23,
    # pt
    "duas": 2, "quatro": 4, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12,
    # en
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}
_N = r"(\d{1,2}|" + "|".join(sorted((k.strip() for k in _NUM), key=len, reverse=True)) + r")"


def _n(tok: str) -> Optional[int]:
    tok = tok.strip()
    return int(tok) if tok.isdigit() else _NUM.get(tok)


# "a las tres", "a la una", "las 21", "às nove", "at nine", "at 9", "9 pm", "21:00", "a las nueve y media"
_TIME = [
    re.compile(r"\b(?:a|para|sobre|hacia)?\s*las?\s+" + _N + r"(?:\s*[:h.]\s*(\d{2}))?(?:\s+y\s+(media|cuarto))?\b"),
    re.compile(r"\b(?:as|a)\s+" + _N + r"(?:\s*[:h]\s*(\d{2}))?\s*(?:horas?)?\b"),
    re.compile(r"\bat\s+" + _N + r"(?:\s*[:.]\s*(\d{2}))?(?:\s*(am|pm|o'?clock))?\b"),
    re.compile(r"\b(\d{1,2})\s*[:h]\s*(\d{2})\b"),
    re.compile(r"\b(\d{1,2})\s*(am|pm)\b"),
]
_PM_WORDS = ("de la tarde", "de la noche", "da tarde", "da noite", "pm", "in the evening", "in the afternoon", "tonight")
_AM_WORDS = ("de la manana", "da manha", "am", "in the morning")


def _hours_said(line: str) -> List[int]:
    f = _f(line)
    out = []
    for rx in _TIME:
        for m in rx.finditer(f):
            h = _n(m.group(1))
            if h is None or not (0 <= h <= 24):
                continue
            out.append(h)
    return out


def _same_hour(said: int, asked: time) -> bool:
    """3 matches 15:00 and 03:00; 13 only 13:00 — a spoken hour is ambiguous across am/pm, never across hours."""
    return said % 12 == asked.hour % 12


_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
             "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4,
             "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
_PARTY = re.compile(r"\b(?:para|somos|mesa de|for|table for|party of)\s+" + _N + r"\s*(?:personas?|pessoas?|people|persons|pax|comensales)?\b")
_NAME = re.compile(r"\b(?:apellido|a nombre de|al nombre de|en nombre de|nombre|sobrenome|em nome de|surname|under the name|name)\s*(?:es\s+|is\s+|de\s+)?([a-z][a-z'-]{1,30})")
_NOT_NAMES = {"de", "del", "la", "el", "que", "quien", "cual", "por", "favor", "es", "is", "the", "please", "sr", "senor",
              "senora", "mr", "mrs", "ms", "who", "what", "su", "your", "seu", "sua", "la", "reserva", "booking"}


def mismatches(turns: List[str], asked: Mapping[str, object]) -> List[dict]:
    """Every line where the VENUE states a time, day, party or name that is not the one asked for."""
    try:
        on = date.fromisoformat(str(asked.get("date")))
        at = time.fromisoformat(str(asked.get("time")))
        party = int(asked.get("party"))
    except (TypeError, ValueError):
        return []
    name_tokens = {_f(t) for t in re.findall(r"[^\W\d_]+", str(asked.get("name") or ""), re.UNICODE)}
    surname = _f(str(asked.get("name") or "").split()[-1]) if str(asked.get("name") or "").split() else ""
    out: List[dict] = []
    for line in turns:
        f = _f(line)
        for h in _hours_said(line):
            if not _same_hour(h, at):
                out.append({"what": "time", "said": h, "asked": at.strftime("%H:%M"), "quote": line})
        for m in _PARTY.finditer(f):
            n = _n(m.group(1))
            if n is not None and n != party:
                out.append({"what": "party", "said": n, "asked": party, "quote": line})
        for w, wd in _WEEKDAYS.items():
            if re.search(rf"\b{w}\b", f) and wd != on.weekday():
                out.append({"what": "day", "said": w, "asked": on.isoformat(), "quote": line})
        for m in re.finditer(r"\b(?:el|dia|on the|the)\s+(\d{1,2}|" + "|".join(k for k in _NUM if " " not in k) + r")\b", f):
            d = _n(m.group(1))
            if d is not None and 1 <= d <= 31 and d != on.day and not re.search(r"(persona|people|pessoa)", f):
                out.append({"what": "day", "said": d, "asked": on.isoformat(), "quote": line})
        for m in _NAME.finditer(f):
            said = m.group(1)
            if said in _NOT_NAMES:
                continue
            is_surname_word = re.search(r"\b(apellido|sobrenome|surname)\b", m.group(0))
            if (is_surname_word and said != surname) or (not is_surname_word and said not in name_tokens):
                out.append({"what": "name", "said": said, "asked": str(asked.get("name")), "quote": line})
    # one entry per (what, quote)
    seen, uniq = set(), []
    for x in out:
        k = (x["what"], x["quote"])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq
