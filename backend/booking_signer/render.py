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
from . import recap as RC
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


# ── S-64 step 5 · the call brief, from the object ──────────────────────────────────────────────────────────────────
#
# ⛔ For a table, `call_brief` returns EXACTLY the brief calls.build_call returns today (tests/test_render.py: dict
# equality, so the same brief_sha256 the guest's approval binds). For any other activity at a time, the same
# instructions with the activity, its count, its duration and the rules widened to service and duration.
# A window or venue_proposes is a different conversation (S-64 §3) and is refused here until its flow is built.

_RECAP_PREFIX = {"es": ("Para confirmar:", "a nombre de", "¿Correcto?"), "pt": ("Para confirmar:", "em nome de", "Está correto?"),
                 "fr": ("Pour confirmer :", "au nom de", "C'est bien ça ?"), "de": ("Zur Bestätigung:", "auf den Namen", "Ist das richtig?"),
                 "it": ("Per confermare:", "a nome", "È corretto?"), "en": ("To confirm:", "under the name", "Is that right?")}


def recap(lang: C.Lang, o: Mapping[str, Any]) -> str:
    """The closing recap (S-60/S-63). A table: S-60's sentence exactly. Otherwise the same frame, with the activity."""
    on, at = _at(o)
    p = _particulars(o, on, at)
    if is_table(o):
        return C.recap_sentence(lang, p)
    pre, under, q = _RECAP_PREFIX[_code(lang)]
    when = RC.when_words(lang.code, lang.weekdays, lang.months, on, at)
    return f"{pre} {activity_phrase(lang, o)}, {spoken_count(lang, o)}, {when}, {under} {C.surname_of(p.name)}. {q}"


def _check(lang: C.Lang, o: Mapping[str, Any]) -> str:
    on, at = _at(o)
    p = _particulars(o, on, at)
    if o["how_many"]["unit"] != "people":   # "the Warrens" only for a party of people
        p = C.CallParticulars(on=on, at=at, party=1, name=p.name, phone=p.phone)
    return C.check_sentence(lang, p)


def instructions(lang: C.Lang, o: Mapping[str, Any], first: str, check: str) -> str:
    """Bland's `task`, from the object. A table: calls.instructions' string exactly."""
    on, at = _at(o)
    name = o["who"]["name"]
    phone = (o["who"].get("contact") or {}).get("mobile_e164")
    contact = (f"If — and only if — they ask for a contact number, give {' '.join(phone)} (the guest's own number). "
               if phone else "You have no contact number to give. If they ask for one, say the guest will confirm directly. ")
    if is_table(o):
        place, what = "a restaurant", "a table"
        booking = f"{o['how_many']['count']} people, {on.isoformat()} at {at.strftime('%H:%M')} (venue's local time), under the name {name}. "
        never = "Never agree to a different date, a different time or a different number of people. "
    else:
        place, what = "a venue", o["what"]["activity"]
        dur = o["when"].get("duration_min")
        booking = (f"{o['what']['activity']} ({o['what']['activity_venue_lang']}), {o['how_many']['count']} {o['how_many']['unit']}, "
                   f"{on.isoformat()} at {at.strftime('%H:%M')} (venue's local time)" + (f", {dur} minutes" if dur else "")
                   + f", under the name {name}. ")
        never = "Never agree to a different date, time, number, service or length. "
    return (
        f"You are Sasha, an AI concierge operated by Kanoe Technologies SL, phoning {place} to book {what} on behalf of a guest. Speak {lang.label} only. "
        f"You already said: \"{first}\" "
        f"The booking: {booking}"
        "If they ask whether you are a person or a machine: you are an AI concierge. Never claim to be the guest or a human. "
        "RULES YOU MUST NEVER BREAK: "
        f"{never}"
        "Never agree to a deposit, a fee, a minimum spend, a cancellation charge, or to give a card. You have no card and no payment details. "
        f"If they offer or ask for ANY of those, say exactly: \"{check}\" — then ask them to repeat the offer so it is noted, thank them, and end the call. "
        f"{contact}"
        "Do not give any email address or any other personal detail. "
        "If they say yes, ask for any reference. Then ALWAYS end with this exact recap and wait for the answer: "
        f"\"{recap(lang, o)}\" Only a clear yes to it confirms. "
        "If they state a different time, day, party or name, repeat the right one once and say the recap again; "
        f"if they still differ, say exactly \"{check}\" and end the call. "
        "If they say no, say to call back later, or are unsure, thank them and end the call. "
        f"If they ask not to be contacted again, say exactly \"{C._ack(lang)}\" and end the call. "
        "Keep it short and polite. Do not leave a voicemail."
    )


def call_brief(o: Mapping[str, Any], venue: C.CallVenue, today: date, number: str) -> dict:
    """The brief for a BOOKING call, from the object. ⛔ Same keys and, for a table, the same values as calls.build_call."""
    o = RS.validate(o)
    if o["flow"] != "book" or o["when"]["mode"] != "at":
        raise RS.ReservationRefused("flow_not_built", "only a booking at a set time can be phoned from the object yet "
                                                      "(a window, venue-proposes and quote-first come with S-64 steps 8–9)")
    lang = C.LANGUAGES[venue.language]
    on, at = _at(o)
    first, check = opening(lang, o, today), _check(lang, o)
    task = instructions(lang, o, first, check)
    if len(task) > 2000:
        raise RS.ReservationRefused("brief_too_long", "the call's instructions exceed Bland's 2,000 characters")
    return {
        "purpose": "book", "timezone": venue.timezone, "reference": None,
        "venue_key": venue.key, "number": number, "language": lang.code,
        "recap": recap(lang, o),
        "first_sentence": first, "task": task, "check_sentence": check,
        "party": o["how_many"]["count"], "date": on.isoformat(), "time": at.strftime("%H:%M"), "name": o["who"]["name"],
        "phone": (o["who"].get("contact") or {}).get("mobile_e164"),
        "from": C.sasha_number(), "number_source": venue.source, "venue_name": venue.name,
        "venue_ids": list(venue.venue_ids) if venue.venue_ids else None,
    }
