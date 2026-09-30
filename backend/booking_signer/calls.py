"""S-33 · THE PHONE RUNG — Sasha calls a venue, as a concierge, on behalf of a named party.

What it does, and nothing else:
  · builds the call from particulars the user approved: the opening sentence in the venue's language, the
    instructions the voice agent follows, and the read-back lines the approval is bound to;
  · places the call through Bland and CHECKS BLAND'S ANSWER — a call is "placed" only when Bland says
    `status: success` and returns a call id. ⛔ The deleted restaurant_agent returned `called: True` without
    looking; that is the one thing this module must never do again;
  · reads the finished call back from Bland and gives it ONE of three outcomes — yes, no, unclear — always
    carrying the venue's own words. A call that never reached a person is not an outcome at all: `not_reached`.

⚠⚠ THE NUMBER NEVER COMES FROM THE REQUEST. There is no authentication in front of these routes (account.py),
so a number taken from the request would let anyone make Sasha dial anyone. The number comes from CALL_VENUES,
server-side, and today that holds one entry: the test line, whose number the founder sets in the environment.

⚠ THE READING IS AN AI READING, LABELLED AS ONE. A model reads the transcript and proposes yes / no / unclear.
It can only say yes or no by QUOTING THE VENUE, and the quote must appear verbatim in what the venue said —
not in what Sasha said. Anything it cannot quote, anything it is unsure of, and any "yes" that came with a
deposit, a fee, a card or a different time, is `unclear`. Never a guess.

No recording (founder, S-33): `record: false`. Bland still produces the text transcript the outcome is read from.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Awaitable, Callable, List, Mapping, Optional
from zoneinfo import ZoneInfo

from . import heard

BLAND_CALLS_URL = "https://api.bland.ai/v1/calls"
#: The model that reads a finished call. Its reading is labelled as an AI reading wherever it is shown.
READER_MODEL = "claude-sonnet-5"
READ_BY = f"an AI reading of the call transcript ({READER_MODEL})"
#: A voice call longer than this is cut off by Bland. A table booking is a two-minute call.
MAX_CALL_MINUTES = 4


class CallRefused(Exception):
    """The call cannot be prepared or placed. `rule` names why; nothing was dialled."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


# ── the venues a call may be placed to — server-side, never from the request ──────────────────────

@dataclass(frozen=True)
class CallVenue:
    key: str
    name: str             #: as the read-back says it
    number_env: str       #: the environment variable holding its E.164 number — set by the founder, never in git
    language: str         #: one of LANGUAGES
    timezone: str         #: IANA; "Thursday" is worked out in the venue's own day
    number: Optional[str] = None   #: S-36 · a number MAGELLAN READ (venue_read.py) — used instead of number_env
    source: Optional[str] = None   #: where that number was read: "their website, lacontra.es" / "their Google listing"
    venue_ids: Optional[tuple] = None  #: S-54/55 · every id its opt-in records may use (optins.venue_ids_of); None = the test line


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def test_line() -> CallVenue:
    """The founder's own phone, standing in for a restaurant. Read at call time so a change needs no redeploy."""
    return CallVenue(
        key="test-line", name="the Sasha test line", number_env="SASHA_TEST_CALL_NUMBER",
        language=_env("SASHA_TEST_CALL_LANGUAGE", "en") or "en",
        timezone=_env("SASHA_TEST_CALL_TIMEZONE", "Europe/Lisbon") or "Europe/Lisbon",
    )


def call_venues() -> dict:
    """⚠ A real venue is added here by a person, with where its number came from — never from a web search."""
    v = test_line()
    return {v.key: v}


_E164 = re.compile(r"\+[1-9]\d{7,14}")


def number_of(venue: CallVenue) -> str:
    if venue.number:
        if not _E164.fullmatch(venue.number):
            raise CallRefused("venue_number_invalid", "the number read for this venue is not E.164")
        return venue.number
    n = re.sub(r"[\s().-]", "", _env(venue.number_env))
    if not n:
        raise CallRefused("venue_number_not_set", f"{venue.number_env} is not set, so {venue.name} has no number to call")
    if not _E164.fullmatch(n):
        raise CallRefused("venue_number_invalid", f"{venue.number_env} is not an E.164 number (+ and 8–15 digits)")
    return n


def calls_enabled() -> bool:
    """⛔ Off unless the founder turns it on. A call is an act on a real phone line."""
    return _env("SASHA_CALLS_ENABLED") == "1"


def bland_key() -> str:
    return _env("BLAND_API_KEY")


def sasha_number() -> Optional[str]:
    """S-35/36 · Sasha's own number (SASHA_PHONE_NUMBER), once bought. Until it exists this is None and calls go out
    on Bland's own caller ID. ⚠ It is used as CALLER ID only: nothing answers it yet (no inbound agent, no SMS
    webhook), so it is never GIVEN as a contact number — a number nobody answers is never handed out (S-32)."""
    n = re.sub(r"[\s().-]", "", _env("SASHA_PHONE_NUMBER"))
    return n if _E164.fullmatch(n) else None


# ── the particulars ─────────────────────────────────────────────────────────────────────────────

_NAME = re.compile(r"[^\W\d_]+(?:[ '’.-][^\W\d_]+)*", re.UNICODE)


@dataclass(frozen=True)
class CallParticulars:
    on: date
    at: time
    party: int
    name: str                   #: the guest's full name; the surname names the party ("the Peters family")
    phone: Optional[str]        #: given to the venue ONLY if they ask, and only because the read-back says so


def parse_call_particulars(body: Mapping[str, Any]) -> CallParticulars:
    raw_date, raw_time = body.get("date"), body.get("time")
    try:
        on = date.fromisoformat(raw_date) if isinstance(raw_date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date) else None
    except ValueError:
        on = None
    if on is None:
        raise CallRefused("date_invalid", "date is a calendar date, YYYY-MM-DD")
    m = re.fullmatch(r"(\d{2}):(\d{2})", raw_time) if isinstance(raw_time, str) else None
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise CallRefused("time_invalid", "time is a 24-hour clock time, HH:MM")
    party = body.get("party")
    if not isinstance(party, int) or isinstance(party, bool) or not 1 <= party <= 20:
        raise CallRefused("party_invalid", "party is a whole number from 1 to 20")
    name = body.get("name")
    # ⚠ The name is SPOKEN to a stranger, and nobody is signed in: letters, spaces, apostrophes, dots and
    # hyphens only, 2–60 characters. Anything else is refused rather than read aloud.
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 60 or not _NAME.fullmatch(name.strip()):
        raise CallRefused("name_invalid", "name is 2–60 letters (spaces, apostrophes, dots and hyphens allowed)")
    phone = body.get("phone")
    if phone is not None and phone != "":
        phone = re.sub(r"[\s().-]", "", str(phone))
        if not _E164.fullmatch(phone):
            raise CallRefused("phone_invalid", "phone, if given, is an E.164 number: + and 8–15 digits")
    else:
        phone = None
    if "number" in body or "phone_number" in body or "venue_phone" in body:
        raise CallRefused("number_from_request", "the number to call is never taken from the request — it comes from the venue")
    return CallParticulars(on=on, at=time(int(m.group(1)), int(m.group(2))), party=party, name=" ".join(name.split()), phone=phone)


# ── the words, per language ─────────────────────────────────────────────────────────────────────
#
# ⚠ Deterministic templates, not a model's translation: the opening sentence is what the approval covers, so it
# is built the same way every time. Every one keeps the AI clause (EU AI Act Art. 50: disclosed at first
# interaction). ⚠ The non-English templates are mine and need a native speaker's read before a real venue hears
# them; Bland's `pt-BR` voice is Brazilian, which a Lisbon restaurant will notice but understand.

@dataclass(frozen=True)
class Lang:
    code: str             #: Bland's `language`
    label: str            #: as the read-back names it
    weekdays: tuple
    months: tuple
    today: str
    family: Callable[[str], str]           #: surname → "on behalf of the Peters family", as the opening needs it
    person: Callable[[str], str]           #: full name → "on behalf of Jon Peters"
    who: Callable[[str], str]              #: surname → "the Petersons", as the check sentence needs it
    for_n: Callable[[int], str]
    on_day: Callable[[str], str]           #: weekday → "on Thursday"
    on_date: Callable[[str, int, str], str]  #: (weekday, day, month) → "on Thursday, 8 October"
    at: Callable[[time], str]
    opening: str                           #: {party} {what} {when} {at}
    check: str                             #: {who}
    cancel_opening: str = ""               #: S-47 · the same slots, for cancelling a booking already made


_EN_NUM = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")


def _en_at(t: time) -> str:
    """"at eight in the evening", "at eight thirty in the evening" — never a bare "at eight" a listener could hear
    as morning."""
    mins = {0: "", 15: " fifteen", 30: " thirty", 45: " forty-five"}.get(t.minute, f" {t.minute:02d}")
    part = "in the morning" if t.hour < 12 else "in the afternoon" if t.hour < 17 else "in the evening"
    return f"at {_EN_NUM[t.hour % 12 or 12]}{mins} {part}"


def _en_plural(surname: str) -> str:
    return surname + ("es" if re.search(r"(s|x|z|ch|sh)$", surname) else "s")


def _hm(t: time, sep: str = ":") -> str:
    return f"{t.hour}{sep}{t.minute:02d}"


LANGUAGES = {
    "en": Lang(
        code="en", label="English",
        weekdays=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
        months=("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
        today="today",
        family=lambda s: f"on behalf of the {s} family", person=lambda n: f"on behalf of {n}", who=lambda s: f"the {_en_plural(s)}",
        for_n=lambda n: f"for {_EN_NUM[n] if n < len(_EN_NUM) else n}",
        on_day=lambda wd: f"on {wd}", on_date=lambda wd, d, mo: f"on {wd}, {d} {mo},",
        at=_en_at,
        opening="Hello, this is Sasha, an AI concierge operated by Kanoe Technologies SL, calling {party} to book a table {what} {when} {at}. Is that possible?",
        check="I'll need to check that with {who}.",
        cancel_opening="Hello, this is Sasha, an AI concierge operated by Kanoe Technologies SL, calling {party} to cancel their table {what} {when} {at}. Could you cancel it, please?",
    ),
    "pt": Lang(
        code="pt-BR", label="Portuguese",
        weekdays=("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"),
        months=("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"),
        today="hoje",
        family=lambda s: f"em nome da família {s}", person=lambda n: f"em nome de {n}", who=lambda s: f"a família {s}",
        for_n=lambda n: "para uma pessoa" if n == 1 else f"para {n} pessoas",
        on_day=lambda wd: f"na {wd}" if wd.endswith("feira") else f"no {wd}",
        on_date=lambda wd, d, mo: (f"na {wd}" if wd.endswith("feira") else f"no {wd}") + f", {d} de {mo},",
        at=lambda t: f"às {t.hour}h" + (f"{t.minute:02d}" if t.minute else ""),
        opening="Olá, fala a Sasha, uma concierge de inteligência artificial operada pela Kanoe Technologies SL, a ligar {party} para reservar uma mesa {what} {when} {at}. É possível?",
        check="Vou ter de confirmar isso com {who}.",
        cancel_opening="Olá, fala a Sasha, uma concierge de inteligência artificial operada pela Kanoe Technologies SL, a ligar {party} para cancelar a reserva de uma mesa {what} {when} {at}. Podem cancelá-la, por favor?",
    ),
    "es": Lang(
        code="es", label="Spanish",
        weekdays=("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
        months=("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"),
        today="hoy",
        family=lambda s: f"de parte de la familia {s}", person=lambda n: f"de parte de {n}", who=lambda s: f"la familia {s}",
        for_n=lambda n: "para una persona" if n == 1 else f"para {n} personas",
        on_day=lambda wd: f"el {wd}", on_date=lambda wd, d, mo: f"el {wd} {d} de {mo},",
        at=lambda t: ("a la " if t.hour in (1, 13) else "a las ") + _hm(t),
        opening="Hola, soy Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL, y llamo {party} para reservar una mesa {what} {when} {at}. ¿Sería posible?",
        check="Tendré que consultarlo con {who}.",
        cancel_opening="Hola, soy Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL, y llamo {party} para cancelar la reserva de una mesa {what} {when} {at}. ¿Podrían cancelarla, por favor?",
    ),
    "fr": Lang(
        code="fr", label="French",
        weekdays=("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
        months=("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"),
        today="aujourd'hui",
        family=lambda s: f"de la part de la famille {s}", person=lambda n: f"de la part de {n}", who=lambda s: f"la famille {s}",
        for_n=lambda n: "pour une personne" if n == 1 else f"pour {n} personnes",
        on_day=lambda wd: wd, on_date=lambda wd, d, mo: f"le {wd} {d} {mo}",
        at=lambda t: f"à {t.hour} heures" + (f" {t.minute:02d}" if t.minute else ""),
        opening="Bonjour, ici Sasha, une concierge d'intelligence artificielle exploitée par Kanoe Technologies SL. J'appelle {party} pour réserver une table {what} {when} {at}. Est-ce possible ?",
        check="Je dois d'abord vérifier avec {who}.",
        cancel_opening="Bonjour, ici Sasha, une concierge d'intelligence artificielle exploitée par Kanoe Technologies SL. J'appelle {party} pour annuler la réservation d'une table {what} {when} {at}. Pourriez-vous l'annuler, s'il vous plaît ?",
    ),
    "de": Lang(
        code="de", label="German",
        weekdays=("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
        months=("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"),
        today="heute",
        family=lambda s: f"im Auftrag der Familie {s}", person=lambda n: f"im Auftrag von {n}", who=lambda s: f"Familie {s}",
        for_n=lambda n: "für eine Person" if n == 1 else f"für {n} Personen",
        on_day=lambda wd: f"am {wd}", on_date=lambda wd, d, mo: f"am {wd}, den {d}. {mo},",
        at=lambda t: f"um {t.hour} Uhr" + (f" {t.minute:02d}" if t.minute else ""),
        opening="Hallo, hier ist Sasha, eine KI-Concierge von Kanoe Technologies SL. Ich rufe {party} an und möchte einen Tisch {what} {when} {at} reservieren. Ist das möglich?",
        check="Das muss ich erst mit {who} abklären.",
        cancel_opening="Hallo, hier ist Sasha, eine KI-Concierge von Kanoe Technologies SL. Ich rufe {party} an, um die Reservierung eines Tisches {what} {when} {at} zu stornieren. Können Sie sie bitte stornieren?",
    ),
    "it": Lang(
        code="it", label="Italian",
        weekdays=("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"),
        months=("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"),
        today="oggi",
        family=lambda s: f"per conto della famiglia {s}", person=lambda n: f"per conto di {n}", who=lambda s: f"la famiglia {s}",
        for_n=lambda n: "per una persona" if n == 1 else f"per {n} persone",
        on_day=lambda wd: wd, on_date=lambda wd, d, mo: f"{wd} {d} {mo}",
        at=lambda t: ("all'" if t.hour in (1, 8, 11) else "alle ") + _hm(t),
        opening="Buongiorno, sono Sasha, una concierge di intelligenza artificiale gestita da Kanoe Technologies SL. Chiamo {party} per prenotare un tavolo {what} {when} {at}. Sarebbe possibile?",
        check="Devo prima verificarlo con {who}.",
        cancel_opening="Buongiorno, sono Sasha, una concierge di intelligenza artificiale gestita da Kanoe Technologies SL. Chiamo {party} per cancellare la prenotazione di un tavolo {what} {when} {at}. Potreste cancellarla, per favore?",
    ),
}


def surname_of(name: str) -> str:
    return name.split()[-1]


def party_phrase(lang: Lang, p: CallParticulars) -> str:
    """'the Peters family' for a party of two or more; the guest's own name for one."""
    return lang.family(surname_of(p.name)) if p.party > 1 else lang.person(p.name)


def when_phrase(lang: Lang, on: date, today: date) -> str:
    """The weekday alone when the date is within the coming six days — "on Thursday" is unambiguous then — else
    the weekday AND the date. ⚠ Worked out in the VENUE's today, not the server's."""
    days = (on - today).days
    if days < 0:
        raise CallRefused("date_in_the_past", "that date has already passed where the venue is")
    if days == 0:
        return lang.today
    wd = lang.weekdays[on.weekday()]
    return lang.on_day(wd) if days <= 6 else lang.on_date(wd, on.day, lang.months[on.month - 1])


def opening_sentence(lang: Lang, p: CallParticulars, today: date, purpose: str = "book") -> str:
    s = (lang.cancel_opening if purpose == "cancel" else lang.opening).format(party=party_phrase(lang, p), what=lang.for_n(p.party), when=when_phrase(lang, p.on, today), at=lang.at(p.at))
    return re.sub(r"\s+", " ", s).strip()


def check_sentence(lang: Lang, p: CallParticulars) -> str:
    """"I'll need to check that with the Johnsons." — the one sentence she answers any deposit, fee, card or
    different time with."""
    return lang.check.format(who=lang.who(surname_of(p.name)) if p.party > 1 else p.name)


# ── the brief: what the voice agent is told, and what the approval covers ────────────────────────

def _ack(lang: Lang) -> str:
    """S-56 · the one acknowledgement of a stop, spoken before hanging up (the transcript is then read by stop.py)."""
    from .stop import ack_spoken
    return ack_spoken(lang.code)


def instructions(lang: Lang, p: CallParticulars, venue: CallVenue, opening: str, check: str) -> str:
    """Bland's `task`. ⚠ Every rule the founder set is here, and the brief is hashed into the approval."""
    contact = (f"If — and only if — they ask for a contact number, give {' '.join(p.phone)} (the guest's own number). "
               if p.phone else "You have no contact number to give. If they ask for one, say the guest will confirm directly. ")
    return (
        f"You are Sasha, an AI concierge operated by Kanoe Technologies SL, phoning a restaurant to book a table on behalf of a guest. Speak {lang.label} only. "
        f"You already said: \"{opening}\" "
        f"The booking: {p.party} people, {p.on.isoformat()} at {p.at.strftime('%H:%M')} (venue's local time), under the name {p.name}. "
        "If they ask whether you are a person or a machine: you are an AI concierge. Never claim to be the guest or a human. "
        "RULES YOU MUST NEVER BREAK: "
        "Never agree to a different date, a different time or a different number of people. "
        "Never agree to a deposit, a fee, a minimum spend, a cancellation charge, or to give a card. You have no card and no payment details. "
        f"If they offer or ask for ANY of those, say exactly: \"{check}\" — then ask them to repeat the offer so it is noted, thank them, and end the call. "
        f"{contact}"
        "Do not give any email address or any other personal detail. "
        "If they say yes to the booking as asked, ask what name or reference the booking is held under, then repeat it back once "
        "to confirm (people, day, time, name or reference), thank them, and end the call. "
        "If they say no, thank them and end the call. If they say to call back later or they are unsure, thank them and end the call. "
        f"If they ask not to be called or contacted again, say exactly: \"{_ack(lang)}\" — then end the call. "
        "Keep it short and polite. Do not leave a voicemail."
    )


def cancel_instructions(lang: Lang, p: CallParticulars, opening: str, check: str, reference: Optional[str]) -> str:
    """S-47 · Bland's `task` for CANCELLING a booking Sasha made. Same rules: no fee, no card, their words brought back."""
    held = f'It is held under "{reference}". ' if reference else ""
    return (
        f"You are Sasha, an AI concierge operated by Kanoe Technologies SL, phoning a restaurant to CANCEL an existing table booking on behalf of a guest. Speak {lang.label} only. "
        f"You already said: \"{opening}\" "
        f"The booking to cancel: {p.party} people, {p.on.isoformat()} at {p.at.strftime('%H:%M')} (venue's local time), under the name {p.name}. {held}"
        "If they ask whether you are a person or a machine: you are an AI concierge. Never claim to be the guest or a human. "
        "RULES YOU MUST NEVER BREAK: "
        "Never agree to a cancellation fee, a charge, or to give a card. You have no card and no payment details. "
        f"If they ask for ANY payment, say exactly: \"{check}\" — then thank them and end the call. "
        "Do not move the booking to another day or time; only cancel it. Do not give any email address or personal detail. "
        "If they confirm it is cancelled, repeat it back once (the day, the time, the name), thank them, and end the call. "
        "If they cannot find the booking, or say to call back, thank them and end the call. "
        f"If they ask not to be called or contacted again, say exactly: \"{_ack(lang)}\" — then end the call. "
        "Keep it short and polite. Do not leave a voicemail."
    )


def _sha256hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_call(venue: CallVenue, p: CallParticulars, now: datetime, purpose: str = "book", reference: Optional[str] = None) -> dict:
    """The brief (what Bland will be sent), the read-back lines, and both hashes. The approval binds to both.

    S-47 · `purpose="cancel"` builds the call that cancels a booking Sasha made — the same venue, number and particulars,
    read from the booking call itself (call_routes), never re-typed."""
    if purpose not in ("book", "cancel"):
        raise CallRefused("purpose_invalid", "a call books or cancels")
    lang = LANGUAGES.get(venue.language)
    if lang is None:
        raise CallRefused("language_not_supported", f"no call script exists in {venue.language!r}; supported: {', '.join(sorted(LANGUAGES))}")
    number = number_of(venue)
    try:
        today = now.astimezone(ZoneInfo(venue.timezone)).date()
    except Exception:  # no tz database on the host: "Thursday" cannot be worked out safely, so no call is built
        raise CallRefused("venue_timezone_unavailable", f"the server cannot resolve {venue.timezone}, so it cannot say which day is which there") from None
    opening = opening_sentence(lang, p, today, purpose)
    check = check_sentence(lang, p)
    task = instructions(lang, p, venue, opening, check) if purpose == "book" else cancel_instructions(lang, p, opening, check, reference)
    brief = {
        "purpose": purpose, "timezone": venue.timezone, "reference": reference,
        "venue_key": venue.key, "number": number, "language": lang.code,
        "first_sentence": opening, "task": task, "check_sentence": check,
        "party": p.party, "date": p.on.isoformat(), "time": p.at.strftime("%H:%M"), "name": p.name, "phone": p.phone,
        "from": sasha_number(), "number_source": venue.source, "venue_name": venue.name,
        "venue_ids": list(venue.venue_ids) if venue.venue_ids else None,
    }
    en = LANGUAGES["en"]
    if purpose == "cancel":
        lines = [
            f"I'll phone {venue.name}, {number}" + (f" — the number on {venue.source}." if venue.source else "."),
            f"I'll say: \"{opening}\"" + ("" if lang.code == "en" else f" (in {lang.label}: {opening_sentence(en, p, today, 'cancel')})"),
            f"This cancels your table for {p.party} on {p.on.isoformat()} at {p.at.strftime('%H:%M')}, under {p.name}"
            + (f', held under "{reference}".' if reference else "."),
            "I won't agree to a cancellation fee or give a card. I'll tell them I need to check with you.",
            "I'll tell you exactly what they said. Shall I call them now?",
        ]
        return {"brief": brief, "brief_sha256": _sha256hex(_canonical(brief)),
                "read_back_lines": lines, "read_back_sha256": _sha256hex("\n".join(lines)), "local_timezone": venue.timezone}
    lines = [
        f"I'll phone {venue.name}, {number}" + (f" — the number on {venue.source}." if venue.source else "."),
        f"I'll say: \"{opening}\"" + ("" if lang.code == "en" else f" (in {lang.label}: {opening_sentence(en, p, today)})"),
        "I won't agree to a deposit, a fee, a card or a different time. I'll tell them I need to check with you.",
        (f"If they ask for a contact number, I'll give yours, {p.phone}." if p.phone
         else "I'll give them no contact number; if they need one, I'll say you'll confirm directly."),
        "I'll tell you exactly what they said. Shall I call them now?",
    ]
    return {
        "brief": brief, "brief_sha256": _sha256hex(_canonical(brief)),
        "read_back_lines": lines, "read_back_sha256": _sha256hex("\n".join(lines)),
        "local_timezone": venue.timezone,
    }


def bland_payload(brief: Mapping[str, Any], call_id: str) -> dict:
    """Exactly what is POSTed to Bland. ⚠ record: false (founder, S-33); voicemail: hang up — a message left on a
    machine is itself a request that may have landed, and nobody approved one."""
    return {
        "phone_number": brief["number"],
        "task": brief["task"],
        "first_sentence": brief["first_sentence"],
        "language": brief["language"],
        "wait_for_greeting": True,
        "record": False,
        "max_duration": MAX_CALL_MINUTES,
        "voicemail": {"action": "hangup"},
        "metadata": {"sasha_call_id": call_id, "venue_key": brief["venue_key"]},
        # S-36 · Sasha's own number as caller ID once it exists (it must be imported into Bland first, or Bland
        # refuses — and that refusal is shown in Bland's own words, like any other)
        **({"from": brief["from"]} if brief.get("from") else {}),
    }


# ── placing: Bland's answer is READ, never assumed ──────────────────────────────────────────────

@dataclass(frozen=True)
class Placed:
    placed: bool
    bland_call_id: Optional[str]
    http_status: Optional[int]
    answer: Any                   #: Bland's own response body, kept as it came
    why: Optional[str]            #: when not placed: Bland's own message, or what went wrong reaching it
    #: S-57 · the request was SENT but no answer came back (a read timeout, a dropped connection, a gateway 5xx): Bland
    #: may have dialled. Never recorded as not placed — the sweeper looks the call up in Bland's own log first.
    uncertain: bool = False


Http = Callable[..., Awaitable[Any]]   # (method, url, headers=, json=) -> object with .status_code and .json()


#: transport errors raised before the request was sent — only these prove nothing reached Bland
_NEVER_SENT = {"ConnectError", "ConnectTimeout", "PoolTimeout", "UnsupportedProtocol", "InvalidURL",
               "ConnectionError", "ConnectionRefusedError", "gaierror"}


async def calls_in_log(http: Http, key: str, number: str, since: datetime) -> List[dict]:
    """S-57 · Bland's OWN log: its calls to `number` created at or after `since` (a minute's slack for clocks)."""
    r = await http("GET", f"{BLAND_CALLS_URL}?limit=100", headers={"authorization": key})
    if r.status_code != 200:
        raise CallRefused("bland_log_unavailable", f"Bland answered HTTP {r.status_code} for its call log")
    body = r.json()
    out = []
    for c in (body.get("calls") if isinstance(body, dict) else body) or []:
        try:
            at = datetime.fromisoformat(str(c.get("created_at")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if c.get("to") == number and at >= since - timedelta(minutes=1):
            out.append({**c, "_created": at})
    return sorted(out, key=lambda c: c["_created"])


async def place_call(http: Http, key: str, payload: Mapping[str, Any]) -> Placed:
    """⛔ `placed` is True ONLY when Bland answered HTTP 200 with `status: "success"` and a call id. Anything else —
    an error status, a 200 without success, a body that is not JSON, no call id, a network error — is NOT placed,
    with Bland's own words kept. There is no path that reports a call Bland did not accept."""
    try:
        r = await http("POST", BLAND_CALLS_URL, headers={"authorization": key, "content-type": "application/json"}, json=dict(payload))
    except Exception as e:
        if type(e).__name__ in _NEVER_SENT:   # the connection was never made: nothing reached Bland
            return Placed(False, None, None, None, f"Bland could not be reached: {type(e).__name__}: {e}")
        # ⚠ S-57 · sent, unanswered — 30 Sept 17:30: a ReadTimeout recorded "not placed" while Bland dialled La Contra
        return Placed(False, None, None, None, f"Bland did not answer in time ({type(e).__name__}); it may have placed the call", uncertain=True)
    if r.status_code in (502, 503, 504):
        return Placed(False, None, r.status_code, None, f"Bland's gateway answered HTTP {r.status_code}; it may have placed the call", uncertain=True)
    try:
        body = r.json()
    except Exception:
        return Placed(False, None, r.status_code, None, f"Bland answered HTTP {r.status_code} with a body that is not JSON")
    if not isinstance(body, dict):
        return Placed(False, None, r.status_code, body, f"Bland answered HTTP {r.status_code} with an unexpected body")
    cid = body.get("call_id")
    if r.status_code == 200 and body.get("status") == "success" and isinstance(cid, str) and cid.strip():
        return Placed(True, cid.strip(), 200, body, None)
    words = body.get("message") or "no message"
    errs = body.get("errors")
    if errs:
        words = f"{words} — {errs}"
    return Placed(False, None, r.status_code, body, f"Bland did not place the call (HTTP {r.status_code}): {words}")


async def fetch_call(http: Http, key: str, bland_call_id: str) -> Any:
    r = await http("GET", f"{BLAND_CALLS_URL}/{bland_call_id}", headers={"authorization": key})
    if r.status_code != 200:
        raise CallRefused("bland_details_unavailable", f"Bland answered HTTP {r.status_code} for call {bland_call_id}")
    return r.json()


# ── reading the finished call ───────────────────────────────────────────────────────────────────

#: Bland statuses that end a call that never became a conversation.
_NOT_REACHED = {"failed", "busy", "no-answer", "canceled"}

#: Money and guarantees, in the languages above. A "yes" that mentions any of these is NOT a yes: Sasha said she
#: would check with the guests, so the outcome is unclear, with their words.
_MONEY = re.compile(
    r"deposit|pre-?pay|prepayment|credit card|\bcard\b|\bfee\b|charge|minimum spend|€|\$|£|\beuros?\b|"
    r"dep[óo]sito|cart[ãa]o|pagamento|sinal|tarjeta|se[ñn]al|garant[ií]a|pago\b|"
    r"caution|acompte|carte (bancaire|de cr[ée]dit)|arrhes|frais|"
    r"anzahlung|kaution|kreditkarte|geb[üu]hr|"
    r"caparra|carta di credito|acconto|penale",
    re.IGNORECASE,
)


@dataclass
class CallReading:
    state: str                          #: in_progress | not_reached | answered
    outcome: Optional[str] = None       #: yes | no | unclear — only when answered
    venue_words: str = ""               #: everything the venue said, verbatim, in order
    quote: Optional[str] = None         #: the venue's own words the outcome rests on (yes/no only)
    raised: List[dict] = field(default_factory=list)   #: deposit / fee / card / different time …, with their words
    reference: Optional[str] = None     #: S-41 G4 · the name or reference the venue said it is held under — verbatim, or None
    why: str = ""                       #: plain words on how the outcome was reached
    read_by: Optional[str] = None       #: set whenever a model read the transcript
    bland_status: Optional[str] = None
    answered_by: Optional[str] = None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


def venue_turns(details: Mapping[str, Any]) -> List[str]:
    """What the VENUE said — Bland labels the called party `user`; Sasha is `assistant`."""
    out = []
    for t in details.get("transcripts") or []:
        if isinstance(t, dict) and t.get("user") == "user" and isinstance(t.get("text"), str) and t["text"].strip():
            out.append(t["text"].strip())
    return out


def transcript_for_reader(details: Mapping[str, Any], purpose: str = "book") -> str:
    lines = [f"PURPOSE: {'CANCEL an existing booking' if purpose == 'cancel' else 'BOOK a table'}"]
    for t in details.get("transcripts") or []:
        if not isinstance(t, dict) or not isinstance(t.get("text"), str):
            continue
        who = {"user": "VENUE", "assistant": "SASHA"}.get(t.get("user"))
        if who:
            lines.append(f"{who}: {t['text'].strip()}")
    return "\n".join(lines)


READER_SYSTEM = """You read the transcript of a phone call in which Sasha, an AI concierge, asked a restaurant (VENUE) for a table.
Decide what the VENUE answered to the booking AS ASKED. Answer with JSON only:
{"reading": "yes" | "no" | "unclear", "quote": "<the VENUE's exact words the reading rests on, copied verbatim from a VENUE line>", "reference": "<ONLY the name or reference number the VENUE said the booking is held under, copied verbatim from a VENUE line; empty if they gave none>", "raised": [{"what": "deposit|fee|card|different_time|different_date|different_party|call_back|other", "quote": "<VENUE's exact words>"}]}
Rules:
- The first line says the PURPOSE. When it is CANCEL: "yes" ONLY if the VENUE clearly confirmed the booking is cancelled; "no" ONLY if they clearly refused to cancel or said there is no such booking; anything else is "unclear". The reference field is empty for a cancellation.
- "yes" ONLY if the VENUE clearly accepted the booking exactly as asked (same day, time, number of people), with nothing attached.
- "no" ONLY if the VENUE clearly refused and offered nothing instead.
- Everything else is "unclear": call back later, maybe, checking, an alternative offered, a deposit/fee/card asked for, a misunderstanding, silence.
- The quote must be copied character for character from one VENUE line. Never quote SASHA. Never paraphrase. If you cannot quote, the reading is "unclear".
- List in "raised" every deposit, fee, card, alternative time/date/party or request to call back the VENUE mentioned, each with the VENUE's exact words."""


Reader = Callable[[str], Awaitable[str]]   # transcript -> the model's raw text


async def anthropic_reader(transcript: str) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic()
    msg = await client.messages.create(
        model=READER_MODEL, max_tokens=600, system=READER_SYSTEM,
        messages=[{"role": "user", "content": transcript}],
    )
    return "".join(getattr(b, "text", "") for b in msg.content)


def _parse_reader(raw: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _quoted_by_venue(quote: Any, turns: List[str]) -> bool:
    if not isinstance(quote, str) or not _norm(quote):
        return False
    q = _norm(quote)
    return any(q in _norm(t) for t in turns)


async def read_call(details: Mapping[str, Any], reader: Reader, purpose: str = "book",
                    asked: Optional[Mapping[str, Any]] = None) -> CallReading:
    """Bland's call details → a reading. ⚠ Every path that is not a quoted, unconditional yes or no is `unclear`.
    S-59 · `asked` (the brief: date, time, party, name) — a yes is only a yes if nothing the venue SAID contradicts it."""
    status = details.get("status")
    answered_by = details.get("answered_by")
    base = {"bland_status": status, "answered_by": answered_by}
    if not details.get("completed") and status not in _NOT_REACHED and status != "completed":
        return CallReading(state="in_progress", why=f"the call is {details.get('queue_status') or status or 'queued'}", **base)
    if status in _NOT_REACHED or answered_by in ("voicemail", "no-answer"):
        what = {"voicemail": "a voicemail answered; she hung up without leaving a message",
                "no-answer": "nobody answered"}.get(answered_by) or {
            "busy": "the line was busy", "no-answer": "nobody answered", "canceled": "the call was cancelled",
            "failed": f"the call failed: {details.get('error_message') or 'no reason given'}"}.get(status, f"Bland reports {status}")
        return CallReading(state="not_reached", why=f"{what}. Nothing was agreed; nothing reached a person.", **base)

    turns = venue_turns(details)
    words = " / ".join(turns)[:2000]
    if not turns:
        return CallReading(state="answered", outcome="unclear", venue_words="", why="the call connected but the venue said nothing Bland transcribed", **base)

    money = [{"what": "money", "quote": t} for t in turns if _MONEY.search(t)]
    try:
        parsed = _parse_reader(await reader(transcript_for_reader(details, purpose)))
    except Exception as e:
        return CallReading(state="answered", outcome="unclear", venue_words=words, raised=money,
                           why=f"the transcript could not be read ({type(e).__name__}); here are their words", **base)
    if parsed is None:
        return CallReading(state="answered", outcome="unclear", venue_words=words, raised=money, read_by=READ_BY,
                           why="the reading was not in the required form; here are their words", **base)

    raised = [r for r in (parsed.get("raised") or []) if isinstance(r, dict) and _quoted_by_venue(r.get("quote"), turns)] + money
    reading, quote = parsed.get("reading"), parsed.get("quote")
    if reading not in ("yes", "no", "unclear"):
        reading = "unclear"
    if reading in ("yes", "no") and not _quoted_by_venue(quote, turns):
        return CallReading(state="answered", outcome="unclear", venue_words=words, raised=raised, read_by=READ_BY,
                           why=f"the reading said {reading} but could not quote the venue saying it; here are their words", **base)
    if reading == "yes" and raised:
        return CallReading(state="answered", outcome="unclear", venue_words=words, quote=quote, raised=raised, read_by=READ_BY,
                           why="they agreed, but with something attached she may not accept for you: "
                               + "; ".join(f"{r['what']}: \"{r['quote']}\"" for r in raised), **base)
    if reading == "yes" and asked:
        off = heard.mismatches(turns, asked)
        if off:
            said = [{"what": f"{m['what']}: they said {m['said']}, you asked {m['asked']}", "quote": m["quote"]} for m in off]
            return CallReading(state="answered", outcome="unclear", venue_words=words, quote=quote, raised=raised + said, read_by=READ_BY,
                               why="they said yes, but what they said does not match what was asked — "
                                   + "; ".join(f"{m['what']} (they said {m['said']}, asked {m['asked']}): \"{m['quote']}\"" for m in off)
                                   + ". Check with them before relying on it.", **base)
    ref = parsed.get("reference")
    ref = ref.strip() if isinstance(ref, str) and ref.strip() and _quoted_by_venue(ref, turns) else None   # never invented
    return CallReading(state="answered", outcome=reading, venue_words=words, quote=quote if reading != "unclear" else None,
                       raised=raised, read_by=READ_BY, reference=ref if reading == "yes" else None,
                       why={"yes": "they accepted the booking as asked", "no": "they declined",
                            "unclear": "their answer was neither a clear yes nor a clear no"}[reading], **base)


def say_for(venue_name: str, r: CallReading, purpose: str = "book") -> str:
    """What Sasha tells the guest. ⚠ Never 'booked' on anything but a quoted yes; always their words."""
    if r.state == "in_progress":
        return f"I'm on the phone to {venue_name} now."
    if r.state == "not_reached":
        return f"I couldn't reach {venue_name}: {r.why}"
    if purpose == "cancel" and r.outcome == "yes":
        return f"{venue_name} confirmed the cancellation. Their words: \"{r.quote}\""
    if purpose == "cancel" and r.outcome == "no":
        return f"{venue_name} did not cancel it. Their words: \"{r.quote}\""
    if r.outcome == "yes":
        held = f' It is held under "{r.reference}".' if r.reference else " They gave no name or reference."
        return f"{venue_name} said yes. Their words: \"{r.quote}\".{held}"
    if r.outcome == "no":
        return f"{venue_name} said no. Their words: \"{r.quote}\""
    return f"I couldn't tell whether {venue_name} said yes — {r.why}. What they said: \"{r.venue_words}\""
