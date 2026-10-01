"""S-59 · WHAT THE VENUE ACTUALLY SAID — the time, day, party and name in its own words, checked against the request.

30 Sept 2026, the first real booking: Sasha asked La Contra for 13:00 under Warren. The venue said "Vale, a las tres de
hora" after "¿A qué hora?", and "¿Me puede repetir apellido? Apellido Tyler", then "Pues ya tiene la reserva". The
model read "accepted as asked". It was not: the venue may hold 15:00, under "Tyler".

So a yes is only a yes when nothing the VENUE said contradicts the request. This is deterministic — no model — and
conservative: any time, day, party or name the venue states that is not the one asked for makes the call `unclear`,
with the venue's lines quoted. A question that only repeats the request ("¿El viernes dos?") agrees with it.

S-64 step 7 · GENERALISED (docs/sasha/S-64-agnostic-reservation.md §5). `asked` may now come from a `reservation/1`
object (`asked_from`), and the checks follow it:
  · when — `at`: any other hour; `window`: a time OUTSIDE the window (a proposal, not a yes); `venue_proposes`: no
    time is a mismatch — every time said is a proposal (`proposals`);
  · day — the asked date, or the window's dates and weekdays;
  · how many — unit-aware: "dos sesiones" against one session; "para seis" against four people;
  · duration — "hora y media", "90 minutos", "half-day", "el de 90" against `duration_min`;
  · what — conservative: a meal that is not the one asked for ("cena" when lunch was asked). A generic word never counts;
  · name — as before.
Languages: Spanish, English and Portuguese, + French, Italian and German. Turkish waits for a native check.
Anything it cannot parse it leaves alone — it only ever turns a yes into unclear, never the reverse.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from typing import Any, Dict, List, Mapping, Optional


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
    # fr (S-64 step 7)
    "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "douze": 12,
    "midi": 12, "treize": 13, "quinze": 15,
    "quatorze": 14, "seize": 16, "dix-sept": 17, "dix-huit": 18, "dix-neuf": 19, "vingt": 20, "vingt et une": 21,
    "vingt-deux": 22, "vingt-trois": 23,
    # it
    "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8, "dieci": 10, "undici": 11,
    "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15, "sedici": 16, "diciassette": 17, "diciotto": 18,
    "diciannove": 19, "venti": 20, "ventuno": 21, "ventidue": 22, "ventitre": 23,
    # de
    "eins": 1, "ein": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4, "funf": 5, "sechs": 6, "sieben": 7, "acht": 8,
    "neun": 9, "zehn": 10, "elf": 11, "zwolf": 12, "dreizehn": 13, "vierzehn": 14, "funfzehn": 15, "sechzehn": 16,
    "siebzehn": 17, "achtzehn": 18, "neunzehn": 19, "zwanzig": 20, "einundzwanzig": 21, "zweiundzwanzig": 22,
    "dreiundzwanzig": 23,
}
_N = r"(\d{1,2}|" + "|".join(sorted((re.escape(k.strip()) for k in _NUM), key=len, reverse=True)) + r")"


def _n(tok: str) -> Optional[int]:
    tok = tok.strip()
    return int(tok) if tok.isdigit() else _NUM.get(tok)


# "a las tres", "a la una", "las 21", "às nove", "at nine", "at 9", "9 pm", "21:00", "à treize heures", "alle tredici",
# "um 13 Uhr"
_TIME = [
    re.compile(r"\b(?:a|para|sobre|hacia)?\s*las?\s+" + _N + r"(?:\s*[:h.]\s*(\d{2}))?(?:\s+y\s+(media|cuarto))?\b"),
    re.compile(r"\b(?:as|a)\s+" + _N + r"(?:\s*[:h]\s*(\d{2}))?\s*(?:horas?|heures?|h)?\b"),
    re.compile(r"\bat\s+" + _N + r"(?:\s*[:.]\s*(\d{2}))?(?:\s*(am|pm|o'?clock))?\b"),
    re.compile(r"\b(\d{1,2})\s*[:h]\s*(\d{2})\b"),
    re.compile(r"\b(\d{1,2})\s*(am|pm)\b"),
    re.compile(r"\balle\s+" + _N + r"\b"),                                   # it
    re.compile(r"\bum\s+" + _N + r"(?:\s*uhr)?\b"),                          # de
]
_ALL_UNA = re.compile(r"\ball'?\s?una\b")                                    # it: "all'una" is one o'clock


def _hours_said(line: str) -> List[int]:
    f = _f(line)
    out = []
    for rx in _TIME:
        for m in rx.finditer(f):
            h = _n(m.group(1))
            if h is None or not (0 <= h <= 24):
                continue
            out.append(h)
    if _ALL_UNA.search(f):
        out.append(1)
    return out


def _same_hour(said: int, asked: time) -> bool:
    """3 matches 15:00 and 03:00; 13 only 13:00 — a spoken hour is ambiguous across am/pm, never across hours."""
    return said % 12 == asked.hour % 12


_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
             "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4,
             "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
             # fr · it · de
             "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6,
             "lunedi": 0, "martedi": 1, "mercoledi": 2, "giovedi": 3, "venerdi": 4, "domenica": 6,
             "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3, "freitag": 4, "samstag": 5, "sonntag": 6}
_PEOPLE = r"(?:personas?|pessoas?|people|persons|pax|comensales|personnes?|persone|personen)"
_PARTY = re.compile(r"\b(?:para|somos|mesa de|for|table for|party of|pour|per|fur)\s+" + _N + r"\s*" + _PEOPLE + r"?\b")
#: how many of a NON-people unit the venue states ("dos sesiones", "two sessions")
_UNIT_WORDS = {
    "sessions": r"(?:sesion(?:es)?|sessao|sessoes|sessions?|seances?|sedut[ae]|sitzung(?:en)?)",
    "pieces": r"(?:piezas?|pecas?|pieces?|pezz[io]|stucke?)",
    "places": r"(?:plazas?|lugar(?:es)?|places?|post[io]|platze?)",
}
_NAME = re.compile(r"\b(?:apellido|a nombre de|al nombre de|en nombre de|nombre|sobrenome|em nome de|surname|under the name|name"
                   r"|au nom de|a nome di|a nome|auf den namen)\s*(?:es\s+|is\s+|de\s+)?([a-z][a-z'-]{1,30})")
_NOT_NAMES = {"de", "del", "la", "el", "que", "quien", "cual", "por", "favor", "es", "is", "the", "please", "sr", "senor",
              "senora", "mr", "mrs", "ms", "who", "what", "su", "your", "seu", "sua", "reserva", "booking", "qui", "chi", "wem",
              "monsieur", "madame", "signor", "signora", "herr", "frau"}

# ── duration ──
_HALF_HOUR = re.compile(r"\b(media hora|meia hora|half an hour|demi-heure|mezz'?ora|halbe stunde)\b")
_HOUR_HALF = re.compile(r"\b(hora y media|hora e meia|an hour and a half|one and a half hours|une heure et demie|un'?ora e mezza|anderthalb stunden|eineinhalb stunden)\b")
_HALF_DAY = re.compile(r"\b(half[- ]day|medio dia|media jornada|meia jornada|demi-journee|mezza giornata|halbtags|halber tag)\b")
_MINUTES = re.compile(r"(?<!las )(?<!a )(?<!um )(?<!alle )\b" + _N + r"\s*(?:minutos?|minutes?|minuti|minuten|mins?)\b")
_HOURS = re.compile(r"(?<!las )(?<!a )(?<!um )(?<!alle )(?<!at )\b" + _N + r"\s*(?:horas|hours|heures|ore|stunden)\b")
_EL_DE = re.compile(r"\b(?:el|la|o|a)\s+de\s+(\d{2,3})\b")                   # "solo tenemos el de 90"

# ── what: the meal, the only activity word read conservatively ──
_LUNCH = re.compile(r"\b(comida|almuerzo|almorzar|comer|lunch|almoco|almocar|dejeuner|pranzo|mittagessen|mittag)\b")
_DINNER = re.compile(r"\b(cena|cenar|dinner|jantar|diner|abendessen)\b")


def asked_from(o: Mapping[str, Any]) -> Dict[str, Any]:
    """S-64 · what `mismatches` checks, from a reservation/1 object."""
    w = o["when"]
    out: Dict[str, Any] = {"mode": w["mode"], "name": o["who"]["name"], "party": o["how_many"]["count"],
                           "unit": o["how_many"]["unit"], "activity": f"{o['what']['activity']} {o['what']['activity_venue_lang']}"}
    if w["mode"] == "at":
        out["date"], out["time"] = w["at"].split("T")
    elif w["mode"] == "window":
        out["window"] = dict(w["window"])
    if w.get("duration_min"):
        out["duration_min"] = w["duration_min"]
    return out


def _durations_said(f: str) -> List[int]:
    out = []
    if _HALF_HOUR.search(f):
        out.append(30)
    if _HOUR_HALF.search(f):
        out.append(90)
    if _HALF_DAY.search(f):
        out.append(240)
    for m in _MINUTES.finditer(f):
        n = _n(m.group(1))
        if n:
            out.append(n)
    for m in re.finditer(r"\b(\d{3})\s*(?:minutos?|minutes?|minuti|minuten|mins?)\b", f):
        out.append(int(m.group(1)))
    for m in _HOURS.finditer(f):
        n = _n(m.group(1))
        if n:
            out.append(60 * n)
    for m in _EL_DE.finditer(f):
        out.append(int(m.group(1)))
    return out


def _within(h: int, earliest: datetime, latest: datetime) -> bool:
    """An hour said — either am or pm when it is 12 or less — inside the window."""
    for hh in ({h % 12, (h % 12) + 12} if h <= 12 else {h}):
        if earliest.time() <= time(hh % 24) <= latest.time():
            return True
    return False


def proposals(turns: List[str]) -> List[dict]:
    """S-64 · for `venue_proposes` (and any out-of-window time): every time the venue offers, with its line."""
    return [{"hour": h, "quote": line} for line in turns for h in _hours_said(line)]


def mismatches(turns: List[str], asked: Mapping[str, object]) -> List[dict]:
    """Every line where the VENUE states a time, day, number, length, meal or name that is not the one asked for."""
    mode = asked.get("mode") or "at"
    on: Optional[date] = None
    at: Optional[time] = None
    win = None
    try:
        party = int(asked.get("party"))
        if mode == "at":
            on = date.fromisoformat(str(asked.get("date")))
            at = time.fromisoformat(str(asked.get("time")))
        elif mode == "window":
            w = asked.get("window") or {}
            win = (datetime.fromisoformat(w["earliest"]), datetime.fromisoformat(w["latest"]), set(w.get("days") or []))
    except (TypeError, ValueError, KeyError):
        return []
    unit = asked.get("unit") or "people"
    duration = asked.get("duration_min")
    activity = _f(str(asked.get("activity") or ""))
    name_tokens = {_f(t) for t in re.findall(r"[^\W\d_]+", str(asked.get("name") or ""), re.UNICODE)}
    surname = _f(str(asked.get("name") or "").split()[-1]) if str(asked.get("name") or "").split() else ""
    days_ok = {on.weekday()} if on else ({d.weekday() for d in (win[0].date(), win[1].date())} | win[2]) if win else None
    dates_ok = {on.day} if on else {win[0].day, win[1].day} if win else None
    asked_day = on.isoformat() if on else "the window"
    out: List[dict] = []
    for line in turns:
        f = _f(line)
        # when
        for h in _hours_said(line):
            if mode == "at" and not _same_hour(h, at):
                out.append({"what": "time", "said": h, "asked": at.strftime("%H:%M"), "quote": line})
            elif mode == "window" and not _within(h, win[0], win[1]):
                out.append({"what": "time", "said": h, "asked": f"{win[0].strftime('%H:%M')}–{win[1].strftime('%H:%M')}", "quote": line})
        # how many — in the unit asked
        if unit == "people":
            for m in _PARTY.finditer(f):
                n = _n(m.group(1))
                if n is not None and n != party:
                    out.append({"what": "party", "said": n, "asked": party, "quote": line})
        else:
            for m in re.finditer(r"\b" + _N + r"\s+" + _UNIT_WORDS[unit] + r"\b", f):
                n = _n(m.group(1))
                if n is not None and n != party:
                    out.append({"what": "count", "said": n, "asked": f"{party} {unit}", "quote": line})
        # day
        if days_ok is not None:
            for w, wd in _WEEKDAYS.items():
                if re.search(rf"\b{w}\b", f) and wd not in days_ok:
                    out.append({"what": "day", "said": w, "asked": asked_day, "quote": line})
            for m in re.finditer(r"\b(?:el|dia|on the|the|le|il|am)\s+(\d{1,2}|" + "|".join(k for k in _NUM if " " not in k) + r")\b", f):
                d = _n(m.group(1))
                if d is not None and 1 <= d <= 31 and d not in dates_ok and not re.search(r"(persona|people|pessoa|personne|person|uhr)", f):
                    out.append({"what": "day", "said": d, "asked": asked_day, "quote": line})
        # duration
        if duration:
            for d in _durations_said(f):
                if d != duration:
                    out.append({"what": "duration", "said": f"{d} min", "asked": f"{duration} min", "quote": line})
        # what: a meal that is not the one asked for
        if activity:
            if _LUNCH.search(activity) and not _DINNER.search(activity) and _DINNER.search(f):
                out.append({"what": "what", "said": _DINNER.search(f).group(1), "asked": asked.get("activity"), "quote": line})
            if _DINNER.search(activity) and not _LUNCH.search(activity) and _LUNCH.search(f):
                out.append({"what": "what", "said": _LUNCH.search(f).group(1), "asked": asked.get("activity"), "quote": line})
        # name
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
