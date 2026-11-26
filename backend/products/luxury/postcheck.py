"""Sasha 419 · THE POST-CHECK (DESIGN §5, ratchet R8): Julia's reply is SPOKEN only if every %, amount and date in it is in that turn's
tool output, on an item carrying its observation ids. Otherwise the whole reply is replaced by "I don't have a measurement for that."

What is checked, in English and Spanish (she follows the person):
  · an AMOUNT of money: never said, supported or not (KANOE 12:45: TAAP prices are never published);
  · every NUMBER (digits or words): one the turn's observed items hold (a gap %, a hotel count, nights, a party, an age in days, a
    date's day or year);
  · a % : a gap_percent of an observed item; one held ONLY by destination medians, said beside a hotel's name, is a hotel % borrowed
    from a median (§5);
  · a MONTH or WEEKDAY: one of an observed item's dates or window labels (no unmeasured or interpolated date);
  · every % is said WITH its measured date (§5): a month of its measured_at, or its age in days;
  · §5's refusals that words can show: "guaranteed" / "best price" / "lowest price", a supplier's name, commission or package rates,
    predictions, availability (Phase 1 has no live read).
Past decay never reaches here as a figure: it arrives as kind=not_recent, with no ids, so nothing it carries supports a number.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from . import reader as R

_EN_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
             "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_ES_UNITS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce", "trece",
             "catorce", "quince", "dieciseis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidos", "veintitres",
             "veinticuatro", "veinticinco", "veintiseis", "veintisiete", "veintiocho", "veintinueve"]
_ES_TENS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90}
UNITS: Dict[str, int] = {**{w: n for n, w in enumerate(_EN_UNITS)}, **{w: n for n, w in enumerate(_ES_UNITS)}, "veintiun": 21}
TENS: Dict[str, int] = {**_EN_TENS, **_ES_TENS}
HUNDRED = {"hundred": 100, "cien": 100, "ciento": 100}
#: "one" / "un" / "uno" / "una" alone are pronouns and articles, not figures ("this one", "una habitación")
_NOT_A_FIGURE = {"one", "un", "uno", "una"}

MONTHS = {**{m: n for n, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September",
                                          "October", "November", "December"], 1)},
          **{m: n for n, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)},
          "Sept": 9,
          **{m: n for n, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                                          "noviembre", "diciembre"], 1)}, "setiembre": 9}
#: English months are capitalized (so "may" the verb is not May); Spanish months are written in lower case
_MONTH_RX = re.compile(r"\b(" + "|".join(sorted((m for m in MONTHS if m[0].isupper()), key=len, reverse=True)) + r")\b"
                       r"|\b(" + "|".join(sorted((m for m in MONTHS if m[0].islower()), key=len, reverse=True)) + r")\b", re.U)
WEEKDAYS = {**{d: n for n, d in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])},
            **{d: n for n, d in enumerate(["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"])}}

MONEY = re.compile(r"[€$£¥]|\b(?:eur|usd|gbp|euros?|dollars?|pounds?|libras?|d[oó]lar(?:es)?|quid|bucks)\b", re.I)
PERCENT_WORD = r"(?:%|\s?percent\b|\s?per\s?cent\b|\s?por\s?ciento\b)"
REFUSED = {
    "superlative": re.compile(r"\bguarantee[ds]?\b|\bbest\s+(?:price|deal|rate)s?\b|\blowest\s+(?:price|rate)s?\b|\bcheapest\b"
                              r"|garantiz|\bmejor(?:es)?\s+precios?\b|\bprecios?\s+m[aá]s\s+bajos?\b|\bm[aá]s\s+barat[oa]\s+posible", re.I),
    "supplier": re.compile(r"\bexpedia\b|\btaap\b|\bhotels\.com\b|\bvrbo\b|\bbooking\.com\b|\bagent\s+rates?\b", re.I),
    "commission": re.compile(r"\bcommissions?\b|\bcomisi[oó]n(?:es)?\b|\bpackage\s+(?:rate|price)s?\b|\bprecios?\s+de\s+paquete\b", re.I),
    "prediction": re.compile(r"\bpredict|\bforecast|\bwill\s+(?:probably\s+|likely\s+)?(?:be\s+|get\s+)?(?:cheaper|lower|higher|drop|fall|rise|go\s+(?:down|up))\b"
                             r"|\b(?:expected|likely)\s+to\b|\bprobably\b|\bpron[oó]stic|\bprevisi[oó]n|\bprobablemente\b|\bbajar[aá]n?\b|\bsubir[aá]n?\b"
                             r"|\bser[aá]n?\s+m[aá]s\s+barat", re.I),
    "availability": re.compile(r"\b(?:is|are)\s+(?:still\s+)?available\b|\bavailable\s+(?:now|today|for\s+your)\b|\brooms?\s+left\b"
                               r"|\bhay\s+disponibilidad\b|\bquedan\s+habitaciones\b|\best[aá]n?\s+disponibles?\b", re.I),
}


def _fold(s: str) -> str:
    return (s.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ü", "u"))


def word_numbers(text: str) -> List[Tuple[int, int]]:
    """Numbers written as words, English or Spanish, with where each ends: [(value, end_offset)]."""
    toks = [(m.group(0).lower(), m.end()) for m in re.finditer(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", text)]
    toks = [(_fold(t), e) for t, e in toks]
    out: List[Tuple[int, int]] = []
    i = 0
    while i < len(toks):
        t, e = toks[i]
        if t in TENS or t in UNITS:
            v, j = (TENS[t], i + 1) if t in TENS else (UNITS[t], i + 1)
            if t in TENS and j < len(toks):
                nxt = toks[j][0]
                if nxt in UNITS and 0 < UNITS[nxt] < 10:                     # "fifty eight" (en; "fifty-eight" splits the same way)
                    v, j = v + UNITS[nxt], j + 1
                elif nxt == "y" and j + 1 < len(toks) and toks[j + 1][0] in UNITS and 0 < UNITS[toks[j + 1][0]] < 10:   # "cincuenta y ocho"
                    v, j = v + UNITS[toks[j + 1][0]], j + 2
            if j < len(toks) and toks[j][0] in HUNDRED:                      # "one hundred"
                v, j = v * 100, j + 1
            if not (t in _NOT_A_FIGURE and j == i + 1):
                out.append((v, toks[j - 1][1]))
            i = j
            continue
        if t in HUNDRED and not (i > 0 and toks[i - 1][0] == "por"):   # "por ciento" is the % sign, not a hundred
            out.append((100, e))
        i += 1
    return out


def digit_numbers(text: str) -> List[Tuple[Optional[int], int]]:
    """Numbers written in digits: [(value or None for a fraction / grouped amount, end_offset)]."""
    out: List[Tuple[Optional[int], int]] = []
    for m in re.finditer(r"\d+(?:[.,]\d+)*", text):
        s = m.group(0)
        out.append((int(s) if s.isdigit() else None, m.end()))
    return out


def _date(v: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _dates_of(i: Mapping[str, Any]) -> List[date]:
    out: List[Any] = []
    at = i.get("measured_at") or {}
    out += [at.get("high"), at.get("low")]
    w = i.get("windows") or {}
    for side in ("high", "low"):
        out += [(w.get(side) or {}).get("from"), (w.get(side) or {}).get("to")]
    st = i.get("stay") or {}
    out += [st.get("high_check_in"), st.get("low_check_in")]
    out += list((i.get("closure") or {}).get("dates_checked") or [])
    return [d for d in (_date(x) for x in out) if d]


def support(outputs: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """What this turn's tool output can support — ONLY from items carrying their observation ids."""
    outs = list(outputs)
    nums: Set[int] = set()
    months: Set[int] = set()
    weekdays: Set[int] = set()
    pct: Dict[int, List[Dict[str, Any]]] = {}
    for i in R.items(outs):
        if not R.has_observation(i):
            continue
        ds = _dates_of(i)
        for d in ds:
            nums |= {d.day, d.year}
            months.add(d.month)
            weekdays.add(d.weekday())
        for side in ("high", "low"):
            label = str(((i.get("windows") or {}).get(side) or {}).get("label") or "")
            months |= {MONTHS[w] for w in re.findall(r"[A-Za-z]+", label) if w in MONTHS}
        st = i.get("stay") or {}
        for k in ("nights", "adults", "children", "rooms"):
            if isinstance(st.get(k), int):
                nums.add(st[k])
        if str(st.get("check_in_weekday") or "") in WEEKDAYS:
            weekdays.add(WEEKDAYS[str(st["check_in_weekday"])])
        for k in ("hotels_counted", "hotels_closed"):
            if isinstance(i.get(k), int):
                nums.add(i[k])
        c = i.get("closure") or {}
        if c.get("dates_checked"):
            nums.add(len(c["dates_checked"]))
        fr = i.get("freshness") or {}
        age = fr.get("age_days") if isinstance(fr.get("age_days"), int) else None
        if age is not None:
            nums.add(age)
        if isinstance(i.get("gap_percent"), int):
            at = i.get("measured_at") or {}
            pct.setdefault(i["gap_percent"], []).append({
                "basis": i.get("gap_basis"), "age": age,
                "measured_months": {d.month for d in (_date(at.get("high")), _date(at.get("low"))) if d}})
            nums.add(i["gap_percent"])
    hotels = {str(i.get("hotel_name")) for i in R.items(outs) if i.get("hotel_name")}
    #: every NAME the reader gave this turn (hotels, destinations, rooms, window labels): words, not figures ("Four Seasons")
    names = hotels | {str(i.get("destination_name")) for i in R.items(outs) if i.get("destination_name")} | \
        {str((i.get("stay") or {}).get("room_name")) for i in R.items(outs) if (i.get("stay") or {}).get("room_name")} | \
        {str(((i.get("windows") or {}).get(sd) or {}).get("label")) for i in R.items(outs) for sd in ("high", "low")
         if ((i.get("windows") or {}).get(sd) or {}).get("label")}
    return {"nums": nums, "months": months, "weekdays": weekdays, "pct": pct, "hotels": hotels, "names": names}


#: the product's own words — "five-star" is what the hotels ARE (the reader's five-star set, §8), not a figure
_PRODUCT_WORDS = re.compile(r"\b(?:five|5)[- ]stars?\b|\bcinco\s+estrellas\b", re.I)


def _figures_only(text: str, names: Iterable[str]) -> str:
    """The reply with the reader's names and the product's own words taken out: what is left is what Julia asserts."""
    t = _PRODUCT_WORDS.sub(" ", text)
    for n in sorted(names, key=len, reverse=True):
        if n:
            t = t.replace(n, " ")
    return t


def check(reply: str, outputs: Iterable[Mapping[str, Any]]) -> Tuple[bool, str]:
    """(True, "ok") when the reply may be spoken; else (False, the rule it broke). The reply's words are never logged."""
    text = reply or ""
    for rule, rx in REFUSED.items():
        if rx.search(text):
            return False, rule
    if MONEY.search(text):
        return False, "amount"
    s = support(outputs)
    said = text
    text = _figures_only(said, s["names"])
    found: List[Tuple[Optional[int], int]] = digit_numbers(text) + [(v, e) for v, e in word_numbers(text)]
    for v, _ in found:
        if v is None or v not in s["nums"]:
            return False, "number"
    said_months = {MONTHS.get(a or b) for a, b in _MONTH_RX.findall(text)}
    if not said_months <= s["months"]:
        return False, "date"
    folded = _fold(text)
    said_days = {n for d, n in WEEKDAYS.items() if re.search(rf"\b{d}\b", folded)}
    if not said_days <= s["weekdays"]:
        return False, "date"
    percents = [v for v, e in found if v is not None and re.match(PERCENT_WORD, text[e:e + 12], re.I)]
    for v in percents:
        held = s["pct"].get(v)
        if not held:
            return False, "percent"
        if all(h["basis"] == "median_of_hotels" for h in held) and any(n and n in said for n in s["hotels"]):
            return False, "median_for_hotel"
        dated = any(h["measured_months"] & said_months for h in held) or \
            any(h["age"] is not None and any(n == h["age"] for n, _ in found) for h in held)
        if not dated:
            return False, "no_measured_date"
    return True, "ok"


__all__ = ["check", "support", "word_numbers", "digit_numbers", "REFUSED", "MONEY"]
