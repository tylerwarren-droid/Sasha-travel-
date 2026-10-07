"""Sasha 182 · PICK A FLIGHT BY WORDS on the web chat and the avatar. Live 7 Oct: with Duffel's cards on screen, "the first
China Eastern", "can I book the first Air China flight", "let's book it" and even "forget about the flights" each re-ran the
search and got the SAME list back — the pick was never read, so checkout was never reached.

pick(message, options) → the option's index (0-based), "none" (the guest dropped the flights), or None (not a pick).
By: an ordinal ("the first", "second one", "number 2", "option 3", "the last"), the airline (+ an ordinal within it:
"the first China Eastern"), the flight number ("ZZ 3829"), a time ("07:44", "7:44"), a price ("1,027", "€1027"), or a bare
"book it" / "this one" / "that one" (the first on screen — the read-back says which, and nothing happens before a yes).
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Union

_ORD = {"first": 0, "1st": 0, "one": 0, "second": 1, "2nd": 1, "two": 1, "third": 2, "3rd": 2, "three": 2,
        "fourth": 3, "4th": 3, "four": 3, "fifth": 4, "5th": 4, "five": 4}
NONE = re.compile(r"\b(?:forget (?:about )?(?:the )?flights?|no flights?|skip (?:the )?flights?|never ?mind(?: the flights?)?|"
                  r"not (?:the|any) flights?|no,? thanks)\b", re.I)
_BOOKISH = re.compile(r"\b(?:book|reserve|take|choose|pick|want|i'?ll (?:have|take)|go (?:with|for)|that one|this one|"
                      r"let'?s do|that flight|this flight|the (?:first|second|third|last|cheapest))\b", re.I)


_AIRLINES = ("air china", "china eastern", "china southern", "british airways", "iberia", "vietnam airlines", "qatar", "emirates",
             "turkish", "lufthansa", "air france", "klm", "duffel airways", "cathay", "singapore airlines", "thai airways", "etihad",
             "finnair", "vietjet", "bamboo", "air europa", "swiss", "korean air", "asiana", "japan airlines", "ana")


def named_missing(message: str, options: List[dict]) -> Optional[str]:
    """An airline the guest named that isn't on the list on screen (never silently another one in its place)."""
    t = _fold(message)
    have = " | ".join(_fold(o.get("name") or "") for o in options)
    for a in _AIRLINES:
        if re.search(rf"\b{re.escape(a)}\b", t) and a not in have:
            if a == "air china" and "china eastern" in t:
                continue
            return a.title()
    return None


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower()) if not unicodedata.combining(c))


def _digits(s: str) -> str:
    return re.sub(r"[^\d]", "", s or "")


def pick(message: str, options: List[dict]) -> Union[int, str, None]:
    # Sasha 193 · what the mic hears: "the Iberia fight", "the first fly", "flight's" — said as "flight"
    t = re.sub(r"\b(?:fight|flite|fly|flighs|flights)\b", "flight", _fold(message))
    if NONE.search(t):
        return "none"
    if not options:
        return None
    n = len(options)
    names = [_fold(o.get("name") or "") for o in options]
    blob = [_fold(f"{o.get('name') or ''} {o.get('detail') or ''}") for o in options]
    # a flight number: "ZZ 3829", "mu0262"
    for m in re.finditer(r"\b([a-z0-9]{2})\s?(\d{2,4})\b", t):
        code = f"{m[1]} {m[2]}"
        hits = [i for i, b in enumerate(blob) if code in b or code.replace(" ", "") in b.replace(" ", "")]
        if len(hits) == 1:
            return hits[0]
    # an ordinal, possibly within one airline: "the first China Eastern"
    k = None
    m = re.search(r"\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|last|cheapest)\b", t) or \
        re.search(r"\b(?:number|option|flight|no\.?)\s*(one|two|three|four|five|\d)\b", t)
    if m:
        w = m[1]
        k = -1 if w == "last" else ("cheap" if w == "cheapest" else (int(w) - 1 if w.isdigit() else _ORD.get(w)))
    def _score(nm: str) -> int:   # the whole name said, else how many of its own words ("air", "airlines" don't count)
        if not nm:
            return 0
        if nm in t:
            return 100
        own = [x for x in nm.split() if len(x) > 2 and x not in ("airlines", "airline", "airways", "air", "lines")]
        return len(own) if own and all(re.search(rf"\b{re.escape(x)}\b", t) for x in own) else 0
    sc = [_score(nm) for nm in names]
    best = max(sc) if sc else 0
    airline = [i for i, v in enumerate(sc) if best and v == best]
    pool = airline or list(range(n))
    if k == "cheap":
        def _p(i):
            try:
                return float(re.sub(r"[^\d.]", "", str(options[i].get("provider_amount") or options[i].get("price") or "")) or 9e9)
            except ValueError:
                return 9e9
        return min(pool, key=_p)
    if isinstance(k, int):
        if k == -1:
            return pool[-1]
        if 0 <= k < len(pool):
            return pool[k]
    if airline and len(airline) >= 1 and (_BOOKISH.search(t) or len(t.split()) <= 6
                                          or re.search(r"\b(?:give me|get me|i'?d like|i like|can i|could i|let me have|go for|please)\b", t)):
        return airline[0]
    # a time: "07:44", "7:44"
    for hh, mm in re.findall(r"\b(\d{1,2})[:.h](\d{2})\b", t):
        tm = f"{int(hh):02d}:{mm}"
        hits = [i for i, b in enumerate(blob) if tm in b]
        if len(hits) == 1:
            return hits[0]
    # a price: "1,027", "€1027", "1027 euros"
    for p in re.findall(r"\d[\d,.]{2,}", t):
        d = _digits(p.split(".")[0] if "," in p or len(p.split(".")[-1]) == 2 else p)
        if len(d) >= 3:
            hits = [i for i, o in enumerate(options) if _digits(str(o.get("price") or "")).startswith(d)]
            if len(hits) >= 1:
                return hits[0]
    if re.search(r"\b(?:book (?:it|that|this|one)|let'?s book|this one|that one|that flight|this flight|go ahead and book)\b", t):
        return 0
    return None


def is_flight_list(text: str) -> bool:
    """Sasha's last reply was a Duffel flight list (the cards are on screen)."""
    return bool(re.search(r"found a few flights to|Book it \(TEST\)\" makes a TEST booking|Here's exactly what I'll book \(TEST|"
                          r"isn't on this flight list|Here are some flights for you to consider|Say “yes” to book it", text or ""))


__all__ = ["pick", "is_flight_list", "named_missing", "NONE"]
