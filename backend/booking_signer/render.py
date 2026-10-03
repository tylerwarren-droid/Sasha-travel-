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

import re
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


def call_read_back(lang: C.Lang, o: Mapping[str, Any], venue_name: str, number: str, source: Optional[str], today: date,
                   own_ref: str = "") -> List[str]:
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
        n, unit = o["how_many"]["count"], o["how_many"]["unit"]
        one = {"people": "person", "sessions": "session", "pieces": "piece", "places": "place"}[unit]
        lines.append(f"That is: {o['what']['activity']} ({o['what']['activity_venue_lang']}) · {n} {one if n == 1 else unit}"
                     f" · {when_iso}" + (f" · {w['duration_min']} minutes" if w.get("duration_min") else "") + ".")
    lines += [
        "I won't agree to a deposit, a fee, a card or a different time. I'll tell them I need to check with you.",
        (f"If they ask for a contact number, I'll give yours, {phone}." if phone
         else "I'll give them no contact number; if they need one, I'll say you'll confirm directly."),
        f"I'll ask for their booking reference and give them ours, {own_ref}; both go on your receipt.",
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


def instructions(lang: C.Lang, o: Mapping[str, Any], first: str, check: str, own_ref: str = "") -> str:
    """Bland's `task`, from the object — calls.task_text, so a table is calls.instructions' string exactly."""
    on, at = _at(o)
    name = o["who"]["name"]
    phone = (o["who"].get("contact") or {}).get("mobile_e164")
    if is_table(o):
        place, what = "a restaurant", "a table"
        booking = f"{o['how_many']['count']} people, {on.isoformat()} at {at.strftime('%H:%M')} local time, under the name {name}. "
        never = "Never accept another date, time or party size. "
    else:
        place, what = "a venue", o["what"]["activity"]
        # the opener above and the recap below already state all of it, word for word: repeated here it only costs
        # Bland's 2,000 characters
        booking = f"{on.isoformat()} at {at.strftime('%H:%M')} venue time, under the name {name}. "
        never = "Never accept another date, time, number, service or length. "
    return C.task_text(lang, place=place, what=what, booking=booking, never=never, opening=first, check=check,
                       recap=recap(lang, o), name=name, phone=phone, own_ref=own_ref)


def call_brief(o: Mapping[str, Any], venue: C.CallVenue, today: date, number: str) -> dict:
    """The brief for a BOOKING call, from the object. ⛔ Same keys and, for a table, the same values as calls.build_call."""
    o = RS.validate(o)
    if o["flow"] != "book" or o["when"]["mode"] != "at":
        raise RS.ReservationRefused("flow_not_built", "a booking can be phoned only at a set time; for a window, ask them "
                                                      "when they have space (an availability call) and book the time they give")
    lang = C.LANGUAGES[venue.language]
    on, at = _at(o)
    first, check = opening(lang, o, today), _check(lang, o)
    own_ref = C.own_ref_of(venue.key, on, at, o["how_many"]["count"], o["who"]["name"], today)
    task = instructions(lang, o, first, check, own_ref)
    if len(task) > 2000:
        raise RS.ReservationRefused("brief_too_long", "the call's instructions exceed Bland's 2,000 characters")
    return {
        "purpose": "book", "timezone": venue.timezone, "reference": None, "own_reference": own_ref,
        "venue_key": venue.key, "number": number, "language": lang.code,
        "recap": recap(lang, o),
        "first_sentence": first, "task": task, "check_sentence": check,
        "party": o["how_many"]["count"], "date": on.isoformat(), "time": at.strftime("%H:%M"), "name": o["who"]["name"],
        "phone": (o["who"].get("contact") or {}).get("mobile_e164"),
        "from": C.caller_id(), "number_source": venue.source, "venue_name": venue.name,
        "venue_ids": list(venue.venue_ids) if venue.venue_ids else None,
        # S-64 · not a table: what the venue's words are checked against (heard.py), and what a cancellation cancels
        **({} if is_table(o) else {"activity": o["what"]["activity"], "activity_venue_lang": o["what"]["activity_venue_lang"],
                                    "category": o["what"]["category"], "unit": o["how_many"]["unit"], "mode": "at",
                                    **({"duration_min": o["when"]["duration_min"]} if o["when"].get("duration_min") else {})}),
    }


# ── S-64 step 6 · the email and WhatsApp Mode A, from the object ───────────────────────────────────────────────────
#
# ⛔ For a table, `email` returns EXACTLY emailing.compose's email (so its read-back and email_sha256 are today's), and
# `whatsapp` returns EXACTLY the page's whatsappText (frontend/lib/whatsapp-template.ts — goldens generated by running
# that function). Anything else: the same templates with the table phrase replaced by the activity and its count.

_EMAIL_TABLE = {"en": ("Table request", "a table for {n}"), "es": ("Solicitud de mesa", "una mesa para {n}"),
                "pt": ("Pedido de mesa", "uma mesa para {n}"), "fr": ("Demande de table", "une table pour {n}"),
                "it": ("Richiesta tavolo", "un tavolo per {n}"), "de": ("Tischanfrage", "einen Tisch für {n}")}
_EMAIL_GENERIC = {"en": "Booking request", "es": "Solicitud de reserva", "pt": "Pedido de reserva", "fr": "Demande de réservation",
                  "it": "Richiesta di prenotazione", "de": "Reservierungsanfrage"}


def _count_noun(code: str, o: Mapping[str, Any]) -> str:
    """"4 personas", "2 sesiones" — the count as the email's {n} slot says it (no preposition: the template has one)."""
    from . import emailing as E
    n, unit = o["how_many"]["count"], o["how_many"]["unit"]
    if unit == "people":
        return (E._PERSON if n == 1 else E._PEOPLE)[code].format(n=n)
    one, many = _UNITS[code][unit]
    return (one if n == 1 else many.format(n=n)).split(" ", 1)[1]


def email(o: Mapping[str, Any], lang_code: str, venue_email: str, email_id: str) -> dict:
    """The email for a booking request, from the object (the BCC is the guest's own address, as today)."""
    from . import emailing as E
    o = RS.validate(o)
    if o["when"]["mode"] != "at" or o["flow"] != "book":
        raise RS.ReservationRefused("flow_not_built", "only a booking at a set time can be emailed from the object yet")
    guest = (o["who"].get("contact") or {}).get("email")
    if not guest:
        raise RS.ReservationRefused("contact_invalid", "an email request BCCs the guest, so it needs their address")
    from .i18n import emails as I18N   # CR 7 i18n
    if lang_code in I18N.LANGS and I18N.usable(lang_code, venue_email) and not is_table(o):
        return I18N.object_email(lang_code, o, venue_email, email_id)
    code = lang_code if lang_code in E._T else "en"
    on, at = _at(o)
    p = E.EmailParticulars(on=on, at=at, party=o["how_many"]["count"], name=o["who"]["name"], guest_email=guest.lower())
    if is_table(o):
        return E.compose(lang_code if lang_code in I18N.LANGS else code, o["where"]["venue_name"], venue_email, p, email_id)   # CR 7 i18n
    subj_word, table_phrase = _EMAIL_TABLE[code]
    subj_t, body_t = E._T[code]
    n = _count_noun(code, o)
    act = activity_phrase(C.LANGUAGES.get(code) or C.LANGUAGES["en"], o)
    # the table phrase is replaced by "<activity>, <count>" — nothing else in the template moves
    body_t = body_t.replace(table_phrase, f"{act}, {{n}}", 1)
    subj_t = subj_t.replace(subj_word, f"{_EMAIL_GENERIC[code]}: {act}", 1)
    people = o["how_many"]["unit"] == "people" and o["how_many"]["count"] > 1
    who = E._WHO[code].format(s=p.name.split()[-1]) if people else p.name
    d, t = on.isoformat(), at.strftime("%H:%M")
    return {"from": E._env("SASHA_EMAIL_FROM"), "to": venue_email, "bcc": p.guest_email, "reply_to": E.act_address(email_id),
            "subject": subj_t.format(n=n, d=d, t=t),
            "text": body_t.format(disclosure=E.DISCLOSURE.get(code, E.DISCLOSURE["en"]), who=who, n=n, d=d, t=t, guest_short=p.name)}


_WA_LANG = {"ES": "es", "PT": "pt", "TR": "tr"}
_TR_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
_TR_DAYS = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")
_WA_TABLE = {"en": "a table for {n} people", "es": "una mesa para {n} personas", "pt": "uma mesa para {n} pessoas", "tr": "{n} kişilik bir masa"}


def _wa_date(code: str, on: date) -> str:
    """The date as the page writes it (toLocaleDateString, weekday long, day numeric, month long, year numeric)."""
    if code == "tr":
        return f"{on.day} {_TR_MONTHS[on.month - 1]} {on.year} {_TR_DAYS[on.weekday()]}"
    L = C.LANGUAGES[code]
    wd, mo = L.weekdays[on.weekday()], L.months[on.month - 1]
    return f"{wd}, {on.day} {mo} {on.year}" if code == "en" else f"{wd}, {on.day} de {mo} de {on.year}"


def whatsapp(o: Mapping[str, Any], country: Optional[str]) -> str:
    """WhatsApp Mode A's message (the GUEST sends it), from the object. A table: the page's text exactly."""
    from .wordings import WHATSAPP_ONE, WHATSAPP_TEMPLATE_V2
    o = RS.validate(o)
    if o["when"]["mode"] != "at":
        raise RS.ReservationRefused("flow_not_built", "only a booking at a set time can be written for WhatsApp from the object yet")
    code = _WA_LANG.get((country or "").upper(), "en")
    on, at = _at(o)
    name = o["who"]["name"].strip()
    people = o["how_many"]["unit"] == "people"
    fam = {"en": "the {s} family", "es": "la familia {s}", "pt": "a família {s}", "tr": "{s} ailesi"}[code]
    who = fam.format(s=name.split()[-1]) if people and o["how_many"]["count"] > 1 else name
    t = WHATSAPP_TEMPLATE_V2[code]
    if not is_table(o):
        what = o["what"]["activity_venue_lang"]
        # the count in the venue's own words ("2 sesiones"); Turkish has no unit table yet, so the bare number
        count = _count_noun(code, o) if code in _UNITS else str(o["how_many"]["count"])
        t = t.replace(_WA_TABLE[code], f"{what} ({count})", 1)
    elif o["how_many"]["count"] == 1 and code in WHATSAPP_ONE:
        t = t.replace(*WHATSAPP_ONE[code])
    return _contract(code, t.replace("{who}", who).replace("{n}", str(o["how_many"]["count"])).replace("{date}", _wa_date(code, on)).replace("{time}", at.strftime("%H:%M")))


def _contract(code: str, s: str) -> str:
    """Portuguese contracts "de a" → "da": "em nome da família Warren", never "em nome de a família". Same on the page."""
    return s.replace("em nome de a ", "em nome da ") if code == "pt" else s


# ── S-64 step 9 · the ASKING flows: quote-first and "when do you have space" ───────────────────────────────────────
#
# Neither books anything. The opener discloses first (S-52) and asks; the agent writes down every price and time as
# said and repeats each once; there is NO closing recap (no booking is made — the recap belongs to a booking). Whatever
# the venue offers is read as `quoted` / `proposed` (step 8) and comes back to the guest: taking it is a NEW `book`
# request, with a new read-back and a new yes. Photos are not sent by phone; on email they wait for an asset store.

_ASK = {
    "en": ("Hello, this is {d}, calling {party} to ask {ask} {act}, {count}{when}. Could you tell me?",
           "what it would cost and when you could do", "when you would have space for"),
    "es": ("Hola, soy {d}, y llamo {party} para preguntar {ask} {act}, {count}{when}. ¿Me lo podrían decir?",
           "cuánto costaría y cuándo podrían hacer", "cuándo tendrían hueco para"),
    "pt": ("Olá, fala a {d}, a ligar {party} para perguntar {ask} {act}, {count}{when}. Pode dizer-me?",
           "quanto custaria e quando poderiam fazer", "quando teriam disponibilidade para"),
    "fr": ("Bonjour, ici {d}. J'appelle {party} pour savoir {ask} {act}, {count}{when}. Pourriez-vous me le dire ?",
           "combien coûterait et quand vous pourriez faire", "quand vous auriez de la place pour"),
    "de": ("Hallo, hier ist {d}. Ich rufe {party} an und möchte wissen, {ask} {act}, {count}{when}. Können Sie mir das sagen?",
           "was es kosten würde und wann Sie Zeit hätten für", "wann Sie Platz hätten für"),
    "it": ("Buongiorno, sono {d}. Chiamo {party} per sapere {ask} {act}, {count}{when}. Me lo potrebbe dire?",
           "quanto costerebbe e quando potreste fare", "quando avreste posto per"),
}


#: Sasha 110 · ON THE PHONE the disclosure is the shorter form the founder approved ("…de Kanoe Technologies SL"); the
#: written wordings (WhatsApp, email, the consents — versioned and hashed) keep theirs
_PHONE_SHORT = (("operated by", "from"), ("operada por", "de"), ("operada pela", "da"), ("exploitée par", "de"), ("gestita da", "di"))


def phone_disclosure(text: str) -> str:
    for a, b in _PHONE_SHORT:
        text = text.replace(f" {a} Kanoe Technologies SL", f" {b} Kanoe Technologies SL")
    return text


def ask_opening(lang: C.Lang, o: Mapping[str, Any], today: date) -> str:
    from .wordings import DISCLOSURE
    code = _code(lang)
    frame, quote_ask, space_ask = _ASK[code]
    ask = quote_ask if o["flow"] == "quote_first" else space_ask
    when = ""
    if o["when"]["mode"] != "venue_proposes":
        w, at = spoken_when(lang, o, today)
        when = f" {w} {at}".rstrip()
    party = party_of(lang, o)
    s = frame.format(d=phone_disclosure(DISCLOSURE.get(code, DISCLOSURE["en"])), party=party, ask=ask, act=activity_phrase(lang, o),
                     count=spoken_count(lang, o), when=when)
    return " ".join(s.split())


def ask_instructions(lang: C.Lang, o: Mapping[str, Any], first: str, check: str) -> str:
    phone = (o["who"].get("contact") or {}).get("mobile_e164")
    contact = (f"If — and only if — they ask for a contact number, give {' '.join(phone)} (the guest's own number). "
               if phone else "You have no contact number to give. If they ask for one, say the guest will confirm directly. ")
    quote = o["flow"] == "quote_first"
    spec = o["what"].get("spec")
    return (
        f"You are Sasha, an AI concierge operated by Kanoe Technologies SL, phoning a venue to ASK — not to book — "
        f"{'what it would cost and ' if quote else ''}when they could do {o['what']['activity']} ({o['what']['activity_venue_lang']}), "
        f"{o['how_many']['count']} {o['how_many']['unit']}, for {o['who']['name']}. Speak {lang.label} only. "
        f"{C.already_said(lang.code, first)}"
        + (f"If they ask what exactly: {spec}. " if spec else "")
        + "If they ask whether you are a person or a machine: you are an AI concierge. Never claim to be the guest or a human. "
        "RULES YOU MUST NEVER BREAK: "
        "Do NOT book anything and do not hold a slot, even if they offer to. "
        "Never agree to a deposit, a fee or a card. You have no card and no payment details. "
        f"If they want to book now or ask for any payment, say exactly: \"{check}\" "
        f"{contact}"
        "Do not give any email address or any other personal detail. "
        f"Write down every {'price and every ' if quote else ''}time or day they offer, exactly as they say it, and repeat each back once. "
        "Then thank them and end the call — the guest decides, and a booking is a separate call. "
        "If they say no or that they cannot help, thank them and end the call. "
        f"If they ask not to be contacted again, say exactly \"{C._ack(lang)}\" and end the call. "
        "Keep it short and polite. Do not leave a voicemail."
    )


def ask_read_back(lang: C.Lang, o: Mapping[str, Any], venue_name: str, number: str, source: Optional[str], today: date) -> List[str]:
    en = C.LANGUAGES["en"]
    quote = o["flow"] == "quote_first"
    phone = (o["who"].get("contact") or {}).get("mobile_e164")
    first = ask_opening(lang, o, today)
    oe = {**o, "what": {**o["what"], "activity_venue_lang": o["what"]["activity"]}}
    lines = [
        f"I'll phone {venue_name}, {number}" + (f" — the number on {source}." if source else "."),
        f"I'll say: \"{first}\"" + ("" if lang.code == "en" else f" (in {lang.label}: {ask_opening(en, oe, today)})"),
        f"I'll ask {'what it would cost and ' if quote else ''}when they could do it. I won't book anything, hold a slot, or agree to a deposit, a fee or a card.",
    ]
    if o["what"].get("photos"):
        lines.append("Your photos are not sent on a call — only the description.")
    lines += [
        (f"If they ask for a contact number, I'll give yours, {phone}." if phone
         else "I'll give them no contact number; if they need one, I'll say you'll confirm directly."),
        f"Whatever they offer comes back to you word for word; booking it is a new request and a new yes. Shall I call them now?",
    ]
    return lines


def call_for(o: Mapping[str, Any], venue: C.CallVenue, now: datetime, number: str) -> dict:
    """S-64 step 9 · the call — brief, read-back and both hashes — for ANY object a call can carry out.
    A booking at a set time: call_brief + call_read_back (a table: today's, byte for byte). Asking: the flows above."""
    from zoneinfo import ZoneInfo
    o = RS.validate(o)
    lang = C.LANGUAGES[venue.language]
    today = now.astimezone(ZoneInfo(venue.timezone)).date()
    if o["flow"] == "book":
        brief = call_brief(o, venue, today, number)
        lines = call_read_back(lang, o, venue.name, number, venue.source, today, brief["own_reference"])
    elif o["flow"] in RS.ASKING:
        first, check = ask_opening(lang, o, today), C.check_sentence(lang, C.CallParticulars(
            on=today, at=time(12, 0), party=1, name=o["who"]["name"], phone=None))
        task = ask_instructions(lang, o, first, check)
        if len(task) > 2000:
            raise RS.ReservationRefused("brief_too_long", "the call's instructions exceed Bland's 2,000 characters")
        w = o["when"]
        on_at = w.get("at", "T").split("T")
        brief = {
            "purpose": o["flow"], "timezone": venue.timezone, "reference": None,
            "venue_key": venue.key, "number": number, "language": lang.code,
            "recap": None,   # ⛔ no booking is made on an asking call, so there is no closing recap
            "first_sentence": first, "task": task, "check_sentence": check,
            "party": o["how_many"]["count"], "date": on_at[0] or None, "time": on_at[1] or None, "name": o["who"]["name"],
            "phone": (o["who"].get("contact") or {}).get("mobile_e164"),
            "from": C.caller_id(), "number_source": venue.source, "venue_name": venue.name,
            "venue_ids": list(venue.venue_ids) if venue.venue_ids else None,
            "mode": w["mode"],
        }
        lines = ask_read_back(lang, o, venue.name, number, venue.source, today)
    else:
        raise RS.ReservationRefused("flow_not_built", "a cancellation is prepared from the booking call itself (S-47)")
    return {"brief": brief, "brief_sha256": C._sha256hex(C._canonical(brief)),
            "read_back_lines": lines, "read_back_sha256": C._sha256hex("\n".join(lines)), "local_timezone": venue.timezone}


# ── S-64 · cancelling a booking made from the object (S-47's pattern, the activity instead of "a table") ────────────

_CANCEL_SWAP = {  # the table phrase in each language's cancel opening → the activity
    "en": ("{cancel_when} under", "{cancel_when} ({activity}) under"),     # Sasha 119 · the founder's opening, naming the activity
    "es": ("{cancel_when} a nombre", "{cancel_when}, {activity}, a nombre"),
    "pt": ("de uma mesa", "de {activity}"),
    "fr": ("d'une table", "{de} {activity}"),
    "de": ("eines Tisches", "für {activity}"),
    "it": ("di un tavolo", "di {activity}"),
}


def cancel_opening(lang: C.Lang, o: Mapping[str, Any], today: date) -> str:
    code = _code(lang)
    old, new = _CANCEL_SWAP[code]
    if (o.get("what") or {}).get("activity") in ("a table", "table"):   # a table needs no naming: the founder's sentence as it is
        old = new = ""
    act = activity_phrase(lang, o)
    de = "d'" if code == "fr" and act[:1].lower() in "aeiouhéè" else "de"
    template = lang.cancel_opening.replace(old, new.replace("{activity}", "\x00").replace("{de}", de), 1)
    when, at = spoken_when(lang, o, today)
    s = template.replace("\x00", act.replace("{", "{{").replace("}", "}}")).replace("d' ", "d'")
    on, t = date.fromisoformat(o["when"]["at"][:10]), time.fromisoformat(o["when"]["at"][11:16])
    s = s.format(party=party_of(lang, o), what=spoken_count(lang, o), when=when, at=at,
                 cancel_when=C.cancel_when(lang, on, t, today), surname=C.surname_of((o.get("who") or {}).get("name") or ""))
    return " ".join(s.split())


def cancel_for(booking_brief: Mapping[str, Any], venue: C.CallVenue, now: datetime, reference: Optional[str]) -> dict:
    """The cancellation of a booking a call made from the object: brief, read-back and both hashes — everything read
    from the booking call's own brief, nothing from the request."""
    from zoneinfo import ZoneInfo
    b = booking_brief
    o = RS.validate({"schema": RS.SCHEMA, "flow": "cancel",
                     "who": {"name": b["name"], "account_id": "cancel", **({"contact": {"mobile_e164": b["phone"]}} if b.get("phone") else {})},
                     "what": {"activity": b["activity"], "activity_venue_lang": b["activity_venue_lang"], "category": b.get("category") or "other"},
                     "where": {"venue_name": venue.name, "timezone": venue.timezone, "venue_ids": list(venue.venue_ids or ())},
                     "when": {"mode": "at", "at": f"{b['date']}T{b['time']}", **({"duration_min": b["duration_min"]} if b.get("duration_min") else {})},
                     "how_many": {"count": b["party"], "unit": b.get("unit") or "people"}})
    lang = C.LANGUAGES[venue.language]
    today = now.astimezone(ZoneInfo(venue.timezone)).date()
    first = cancel_opening(lang, o, today)
    check = C.check_sentence(lang, C.CallParticulars(on=today, at=time(12), party=1, name=b["name"], phone=None))
    held = f'It is held under "{reference}". ' if reference else ""
    recap = C.cancel_recap(lang, C.CallParticulars(on=date.fromisoformat(b["date"]), at=time.fromisoformat(b["time"]),
                                                   party=int(b["party"]), name=b["name"], phone=None))
    task = (
        f"You are Sasha, an AI concierge operated by Kanoe Technologies SL, phoning a venue to CANCEL an existing booking on behalf of a guest. Speak {lang.label} only. "
        f"{C.already_said(lang.code, first)}"
        f"The booking to cancel: {b['activity']} ({b['activity_venue_lang']}), {b['party']} {b.get('unit') or 'people'}, {b['date']} at {b['time']} (venue's local time), under the name {b['name']}. {held}"
        "If they ask whether you are a person or a machine: you are an AI concierge. Never claim to be the guest or a human. "
        "RULES YOU MUST NEVER BREAK: "
        "Never agree to a cancellation fee, a charge, or to give a card. You have no card and no payment details. "
        f"If they ask for ANY payment, say exactly: \"{check}\" — then thank them and end the call. "
        "Do not move the booking to another day or time; only cancel it. Do not give any email address or personal detail. "
        # Sasha 119 · cancelled only on their explicit yes to this recap
        f"When they say they'll cancel it, say at once: \"{recap}\" and wait silently for the answer. "
        f"Only a clear yes confirms; to just \"ok\", ask once: \"{recap.split('. ')[-1]}\" Then thank them and end the call. "
        "If they cannot find the booking, or say to call back, thank them and end the call. "
        f"If they ask not to be contacted again, say exactly \"{C._ack(lang)}\" and end the call. "
        "Keep it short and polite. Do not leave a voicemail."
    )
    number = b["number"]
    brief = {"purpose": "cancel", "timezone": venue.timezone, "reference": reference, "venue_key": venue.key, "number": number,
             "language": lang.code, "recap": recap, "first_sentence": first, "task": task, "check_sentence": check,
             "party": b["party"], "date": b["date"], "time": b["time"], "name": b["name"], "phone": b.get("phone"),
             "from": C.caller_id(), "number_source": venue.source, "venue_name": venue.name,
             "venue_ids": list(venue.venue_ids) if venue.venue_ids else None,
             "activity": b["activity"], "activity_venue_lang": b["activity_venue_lang"], "unit": b.get("unit") or "people"}
    en = C.LANGUAGES["en"]
    oe = {**o, "what": {**o["what"], "activity_venue_lang": o["what"]["activity"]}}
    lines = [
        f"I'll phone {venue.name}, {number}" + (f" — the number on {venue.source}." if venue.source else "."),
        f"I'll say: \"{first}\"" + ("" if lang.code == "en" else f" (in {lang.label}: {cancel_opening(en, oe, today)})"),
        f"This cancels your {re.sub(r'^(?:a|an|the) ', '', b['activity'])} for {b['party']} on {b['date']} at {b['time']}, under {b['name']}" + (f', held under "{reference}".' if reference else "."),
        "I won't agree to a cancellation fee or give a card. I'll tell them I need to check with you.",
        "I'll tell you exactly what they said. Shall I call them now?",
    ]
    return {"brief": brief, "brief_sha256": C._sha256hex(C._canonical(brief)),
            "read_back_lines": lines, "read_back_sha256": C._sha256hex("\n".join(lines)), "local_timezone": venue.timezone}
