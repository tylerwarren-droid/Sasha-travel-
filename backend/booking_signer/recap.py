"""S-60 · THE CLOSING RECAP — the founder's non-negotiable rule for every booking call.

Every booking call ends with Sasha reading the whole booking back in the venue's language:
    "Para confirmar: viernes 2 de octubre, a la una de la tarde, dos personas, a nombre de Warren. ¿Correcto?"
and it is CONFIRMED only on an explicit yes to that recap. A conflict (a different time, day, party or name) is
resolved on the call — Sasha states the right detail and reads the recap again — or the outcome is NOT confirmed, with
the venue's lines quoted. (30 Sept 2026: La Contra said "a las tres" and "Apellido Tyler", then "ya tiene la reserva".)

The recap is built here, put in the brief (so it is hashed into the guest's approval), spoken by the agent, and checked
in the transcript by `recap_answer`: Sasha's recap turn must be there, whole, and the venue's next words must be a yes
with no "no" and nothing contradicting the request (heard.py). Everything else is `unclear` — shown as "not confirmed".

Email and WhatsApp: nothing marks a booking confirmed from a reply today — a reply is shown to the guest word for word
and never moves the status itself (ladder_routes.inbound). When a reader for replies is built it must use `restates`.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, time
from typing import List, Mapping, Optional

from . import heard


def _hour12(h: int) -> int:
    return h % 12 or 12


_ES_H = ("", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce")
_PT_H = ("", "uma", "duas", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze")
_EN_H = ("", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")
_ES_N = ("", "una persona", "dos personas", "tres personas", "cuatro personas", "cinco personas", "seis personas",
         "siete personas", "ocho personas", "nueve personas", "diez personas", "once personas", "doce personas")
_PT_N = ("", "uma pessoa", "duas pessoas", "três pessoas", "quatro pessoas", "cinco pessoas", "seis pessoas",
         "sete pessoas", "oito pessoas", "nove pessoas", "dez pessoas", "onze pessoas", "doze pessoas")
_EN_N = ("", "one person", "two people", "three people", "four people", "five people", "six people", "seven people",
         "eight people", "nine people", "ten people", "eleven people", "twelve people")


def _n(table, n: int, word: str) -> str:
    return table[n] if 0 < n < len(table) else f"{n} {word}"


def _es_at(t: time) -> str:
    h = _hour12(t.hour)
    mins = {0: "", 15: " y cuarto", 30: " y media"}.get(t.minute, f" y {t.minute}")
    part = "de la mañana" if t.hour < 12 else "del mediodía" if t.hour == 12 else "de la tarde" if t.hour < 21 else "de la noche"
    return f"{'a la' if h == 1 else 'a las'} {_ES_H[h]}{mins} {part}"


def _pt_at(t: time) -> str:
    h = _hour12(t.hour)
    mins = {0: "", 30: " e meia"}.get(t.minute, f" e {t.minute}")
    part = "da manhã" if t.hour < 12 else "da tarde" if t.hour < 19 else "da noite"
    return f"{'à' if h == 1 else 'às'} {_PT_H[h]}{mins} {part}"


def _en_at(t: time) -> str:
    mins = {0: "", 15: " fifteen", 30: " thirty", 45: " forty-five"}.get(t.minute, f" {t.minute:02d}")
    part = "in the morning" if t.hour < 12 else "in the afternoon" if t.hour < 17 else "in the evening"
    return f"at {_EN_H[_hour12(t.hour)]}{mins} {part}"


def _hm24(t: time, h_word: str, sep: str) -> str:
    return f"{t.hour} {h_word}" + (f" {sep}{t.minute:02d}" if t.minute else "")


#: lang code → (prefix, the recap, the question). Weekday and month words come from calls.LANGUAGES.
def sentence(lang_code: str, weekdays, months, on: date, at: time, party: int, surname: str) -> str:
    wd, mo = weekdays[on.weekday()], months[on.month - 1]
    if lang_code.startswith("es"):
        return f"Para confirmar: {wd} {on.day} de {mo}, {_es_at(at)}, {_n(_ES_N, party, 'personas')}, a nombre de {surname}. ¿Correcto?"
    if lang_code.startswith("pt"):
        return f"Para confirmar: {wd}, {on.day} de {mo}, {_pt_at(at)}, {_n(_PT_N, party, 'pessoas')}, em nome de {surname}. Está correto?"
    if lang_code.startswith("fr"):
        return f"Pour confirmer : {wd} {on.day} {mo}, à {_hm24(at, 'heures', '')}, {party} personne{'s' if party > 1 else ''}, au nom de {surname}. C'est bien ça ?"
    if lang_code.startswith("de"):
        return f"Zur Bestätigung: {wd}, {on.day}. {mo}, um {_hm24(at, 'Uhr', '')}, {party} Person{'en' if party > 1 else ''}, auf den Namen {surname}. Ist das richtig?"
    if lang_code.startswith("it"):
        return f"Per confermare: {wd} {on.day} {mo}, alle {at.hour}" + (f" e {at.minute}" if at.minute else "") + \
            f", {party} person{'e' if party > 1 else 'a'}, a nome {surname}. È corretto?"
    return f"To confirm: {wd} {on.day} {mo}, {_en_at(at)}, {_n(_EN_N, party, 'people')}, under the name {surname}. Is that right?"


PREFIXES = ("para confirmar", "pour confirmer", "zur bestatigung", "per confermare", "to confirm")


def _f(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", s).split())


_YES = re.compile(r"\b(si|sí|correcto|exacto|eso es|asi es|vale|perfecto|de acuerdo|yes|yeah|yep|correct|right|that s right|"
                  r"exactly|sim|certo|exato|isso|oui|exact|c est ca|c est bien ca|ja|richtig|genau|stimmt|esatto|giusto|certo)\b")
_NO = re.compile(r"\b(no|nao|non|nein|not|incorrect|incorrecto|errado|falsch|sbagliato|wrong)\b")


def recap_answer(transcripts: List[Mapping], recap: str, asked: Mapping) -> dict:
    """{confirmed: bool, why: str, quotes: [str]} — confirmed ONLY when Sasha's whole recap was spoken and the venue's
    next words are an explicit yes, with no "no" and nothing after it contradicting the request."""
    target = _f(recap)
    idx = None
    for i, t in enumerate(transcripts):
        if t.get("user") == "assistant" and target and target in _f(str(t.get("text") or "")):
            idx = i
    if idx is None:
        return {"confirmed": False, "quotes": [], "why": "Sasha's closing recap was never read in full, so nothing was confirmed against it"}
    after = [str(t.get("text") or "").strip() for t in transcripts[idx + 1:] if t.get("user") == "user" and str(t.get("text") or "").strip()]
    if not after:
        return {"confirmed": False, "quotes": [], "why": "the venue said nothing after Sasha's recap"}
    first = after[0]
    f = _f(first)
    if _NO.search(f) or not _YES.search(f):
        return {"confirmed": False, "quotes": [first], "why": f"the venue's answer to the recap was not an explicit yes: \"{first}\""}
    off = heard.mismatches(after, asked)
    if off:
        return {"confirmed": False, "quotes": [m["quote"] for m in off],
                "why": "after saying yes to the recap the venue said something different: "
                       + "; ".join(f"{m['what']} (they said {m['said']}, asked {m['asked']}): \"{m['quote']}\"" for m in off)}
    return {"confirmed": True, "quotes": [first], "why": f"they said yes to the recap: \"{first}\""}


def restates(text: str, asked: Mapping) -> bool:
    """For a written reply (email, WhatsApp): True only if it names the same time AND party AND day as the request,
    and names nothing different. Not wired: no path confirms a booking from a reply today."""
    try:
        on, at, party = date.fromisoformat(str(asked["date"])), time.fromisoformat(str(asked["time"])), int(asked["party"])
    except (KeyError, TypeError, ValueError):
        return False
    if heard.mismatches([text], asked):
        return False
    f = _f(text)
    hours = heard._hours_said(text)
    has_time = any(heard._same_hour(h, at) for h in hours)
    has_party = bool(re.search(rf"\b({party}|{'|'.join(w for w, n in heard._NUM.items() if n == party)})\b", f))
    has_day = bool(re.search(rf"\b{on.day}\b", f)) or any(re.search(rf"\b{w}\b", f) for w, d in heard._WEEKDAYS.items() if d == on.weekday())
    return has_time and has_party and has_day
