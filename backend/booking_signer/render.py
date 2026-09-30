"""S-64 step 4 · THE RENDERERS — every sentence a channel says, built from one `reservation/1` object.

docs/sasha/S-64-agnostic-reservation.md §2. `spoken_when`, `spoken_count`, the activity phrase, the opening sentence
and the call read-back. ⛔ THE GOLDEN RULE: a restaurant request (a table, at a time, for people) renders today's
opening and read-back BYTE FOR BYTE (tests/test_render.py), so every existing hash and approval means what it meant.

How: each language's opening in calls.LANGUAGES says "… para reservar una mesa {what} {when} {at} …". The generic
opening is that same template with the table phrase replaced by the activity — so a table IS the generic case, not a
special one, and the golden test proves the substitution changes nothing.

The activity is in the venue's language ONCE, at prepare (`what.activity_venue_lang`); nothing here translates.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, List, Mapping, Optional

from . import calls as C
from . import reservation as RS

_BETWEEN = {"en": "between {a} and {b}", "es": "entre las {a} y las {b}", "pt": "entre as {a} e as {b}",
            "fr": "entre {a} et {b}", "de": "zwischen {a} und {b}", "it": "tra le {a} e le {b}"}
_PROPOSES = {"en": "whenever you have space", "es": "cuando tengan hueco", "pt": "quando tiverem disponibilidade",
             "fr": "quand vous aurez de la place", "de": "wann immer Sie Platz haben", "it": "quando avete posto"}
_UNITS = {  # unit → (one, many with {n}); people come from calls.LANGUAGES[…].for_n, as today
    "en": {"sessions": ("for one session", "for {n} sessions"), "pieces": ("for one piece", "for {n} pieces"), "places": ("for one place", "for {n} places")},
    "es": {"sessions": ("para una sesión", "para {n} sesiones"), "pieces": ("para una pieza", "para {n} piezas"), "places": ("para una plaza", "para {n} plazas")},
    "pt": {"sessions": ("para uma sessão", "para {n} sessões"), "pieces": ("para uma peça", "para {n} peças"), "places": ("para um lugar", "para {n} lugares")},
    "fr": {"sessions": ("pour une séance", "pour {n} séances"), "pieces": ("pour une pièce", "pour {n} pièces"), "places": ("pour une place", "pour {n} places")},
    "de": {"sessions": ("für eine Sitzung", "für {n} Sitzungen"), "pieces": ("für ein Stück", "für {n} Stücke"), "places": ("für einen Platz", "für {n} Plätze")},
    "it": {"sessions": ("per una seduta", "per {n} sedute"), "pieces": ("per un pezzo", "per {n} pezzi"), "places": ("per un posto", "per {n} posti")},
}
_DURATION = {"en": "of {m} minutes", "es": "de {m} minutos", "pt": "de {m} minutos", "fr": "de {m} minutes",
             "de": "von {m} Minuten", "it": "di {m} minuti"}


def _code(lang: C.Lang) -> str:
    return lang.code.split("-")[0]


def _particulars(o: Mapping[str, Any], on: date, at: time) -> C.CallParticulars:
    return C.CallParticulars(on=on, at=at, party=o["how_many"]["count"], name=o["who"]["name"],
                             phone=(o["who"].get("contact") or {}).get("mobile_e164"))


def _at(o: Mapping[str, Any]):
    d, hm = o["when"]["at"].split("T")
    return date.fromisoformat(d), time.fromisoformat(hm)


def is_table(o: Mapping[str, Any]) -> bool:
    """Today's case, and the only one today's rungs can express."""
    return (o["what"]["category"] == "restaurant" and o["when"]["mode"] == "at" and o["how_many"]["unit"] == "people"
            and o["what"]["activity_venue_lang"] in RS.TABLE.values() and "duration_min" not in o["when"])


def activity_phrase(lang: C.Lang, o: Mapping[str, Any]) -> str:
    """The activity in the venue's language, with its duration when it matters to the venue."""
    a = o["what"]["activity_venue_lang"]
    m = o["when"].get("duration_min")
    if not m or str(m) in a:   # "a 60-minute massage" already says it
        return a
    return f"{a} {_DURATION[_code(lang)].format(m=m)}"


def spoken_count(lang: C.Lang, o: Mapping[str, Any]) -> str:
    n, unit = o["how_many"]["count"], o["how_many"]["unit"]
    if unit == "people":
        return lang.for_n(n)
    one, many = _UNITS[_code(lang)][unit]
    return one if n == 1 else many.format(n=n)


def spoken_when(lang: C.Lang, o: Mapping[str, Any], today: date) -> tuple:
    """(when, at) — the two slots every opening template has. `at`: today's words exactly."""
    mode = o["when"]["mode"]
    if mode == "at":
        on, at = _at(o)
        return C.when_phrase(lang, on, today), lang.at(at)
    if mode == "window":
        a = datetime.fromisoformat(o["when"]["window"]["earliest"])
        b = datetime.fromisoformat(o["when"]["window"]["latest"])
        return C.when_phrase(lang, a.date(), today), _BETWEEN[_code(lang)].format(a=a.strftime("%H:%M"), b=b.strftime("%H:%M"))
    return "", _PROPOSES[_code(lang)]


def party_of(lang: C.Lang, o: Mapping[str, Any]) -> str:
    """"de parte de la familia Warren" for a party of people; the guest's own name for one person or any other unit."""
    name = o["who"]["name"]
    if o["how_many"]["unit"] == "people" and o["how_many"]["count"] > 1:
        return lang.family(C.surname_of(name))
    return lang.person(name)


def opening(lang: C.Lang, o: Mapping[str, Any], today: date) -> str:
    """The first sentence: disclosure first (S-52), then the request. For a table: today's sentence, byte for byte."""
    table = RS.TABLE[_code(lang)]
    template = lang.opening.replace(f" {table} ", " {activity} ", 1)
    when, at = spoken_when(lang, o, today)
    s = template.format(party=party_of(lang, o), activity=activity_phrase(lang, o), what=spoken_count(lang, o), when=when, at=at)
    return " ".join(s.split())


def call_read_back(lang: C.Lang, o: Mapping[str, Any], venue_name: str, number: str, source: Optional[str], today: date) -> List[str]:
    """What the guest approves for a booking call. A table: today's five lines exactly. Anything else: the same lines,
    with one more saying what, when, how many and how long — in plain English, so the guest reads what they asked for."""
    en = C.LANGUAGES["en"]
    phone = (o["who"].get("contact") or {}).get("mobile_e164")
    first = opening(lang, o, today)
    lines = [
        f"I'll phone {venue_name}, {number}" + (f" — the number on {source}." if source else "."),
        f"I'll say: \"{first}\"" + ("" if lang.code == "en" else f" (in {lang.label}: {opening_en(o, today)})"),
    ]
    if not is_table(o):
        w = o["when"]
        when_iso = w.get("at") or (f"{w['window']['earliest']} to {w['window']['latest']}" if w.get("window") else "a time they propose")
        lines.append(f"That is: {o['what']['activity']} ({o['what']['activity_venue_lang']}) · {o['how_many']['count']} {o['how_many']['unit']}"
                     f" · {when_iso}" + (f" · {w['duration_min']} minutes" if w.get("duration_min") else "") + ".")
    lines += [
        "I won't agree to a deposit, a fee, a card or a different time. I'll tell them I need to check with you.",
        (f"If they ask for a contact number, I'll give yours, {phone}." if phone
         else "I'll give them no contact number; if they need one, I'll say you'll confirm directly."),
        "I'll tell you exactly what they said. Shall I call them now?",
    ]
    return lines


def opening_en(o: Mapping[str, Any], today: date) -> str:
    """The English of the opening, for the read-back: the activity in the guest's own words."""
    en = C.LANGUAGES["en"]
    oe = {**o, "what": {**o["what"], "activity_venue_lang": o["what"]["activity"] if not is_table(o) else RS.TABLE["en"]}}
    return opening(en, oe, today)
