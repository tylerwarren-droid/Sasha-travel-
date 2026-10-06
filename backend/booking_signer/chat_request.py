"""S-64 step 11 · THE CHAT PRODUCES THE OBJECT — what the guest said, as the parts of `reservation/1` it states.

docs/sasha/S-64-agnostic-reservation.md §7 step 11. Deterministic, like handoff.py: no model reads the message, so
nothing is invented. `draft(message)` returns the parts the message STATES — what, when, how many, the flow — and the
ONE question for the first thing missing, in this order: the activity, the kind of time, the count and its unit.
Nothing is filled from a default except where the words themselves say it ("a tattoo" is one piece).

`complete(draft, who=…, where=…)` adds the guest and the venue (from their profile and the venue read, never the
message) and returns the validated object — the same `reservation/1` every channel renders from.

Activities are a short, explicit list, each with its words in the call languages. One not on the list is asked
about, never guessed; a native read of the non-English words is still owed (as for every template).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Mapping, Optional

from . import handoff as HO
from . import reservation as RS

#: keyword → (activity in English, category, natural unit, default flow, {lang: activity in that language})
ACTIVITIES = [
    (r"\b(table|lunch|dinner|restaurant)\b", "a table", "restaurant", "people", "book",
     {"es": "una mesa", "pt": "uma mesa", "fr": "une table", "de": "einen Tisch", "it": "un tavolo", "en": "a table"}),
    (r"\bmassage\b", "a massage", "beauty", "people", "book",
     {"es": "un masaje", "pt": "uma massagem", "fr": "un massage", "de": "eine Massage", "it": "un massaggio", "en": "a massage"}),
    # Sasha 173 · "an appointment for a spa": a spa treatment (it asked "What should I book there?")
    (r"\b(spa|wellness|facial|treatment)s?\b", "a spa treatment", "beauty", "people", "book",
     {"es": "un tratamiento de spa", "pt": "um tratamento de spa", "fr": "un soin au spa", "de": "eine Spa-Behandlung", "it": "un trattamento spa",
      "en": "a spa treatment", "vi": "một liệu trình spa"}),
    (r"\b(haircut|hair ?cut)\b", "a haircut", "beauty", "people", "book",
     {"es": "un corte de pelo", "pt": "um corte de cabelo", "fr": "une coupe de cheveux", "de": "einen Haarschnitt", "it": "un taglio di capelli", "en": "a haircut"}),
    (r"\btattoo\b", "a tattoo", "beauty", "pieces", "quote_first",
     {"es": "un tatuaje", "pt": "uma tatuagem", "fr": "un tatouage", "de": "ein Tattoo", "it": "un tatuaggio", "en": "a tattoo"}),
    # Sasha 169 · an event to book on a trip: a class, a show, a lesson
    (r"\bcooking (?:class|lesson|school)\b", "a cooking class", "experience", "people", "book",
     {"es": "una clase de cocina", "pt": "uma aula de culinária", "fr": "un cours de cuisine", "de": "einen Kochkurs", "it": "un corso di cucina",
      "en": "a cooking class", "vi": "một lớp học nấu ăn"}),
    (r"\b(?:show|performance|concert|theatre|theater|puppet)\b", "seats for the show", "experience", "people", "book",
     {"es": "entradas para el espectáculo", "pt": "lugares para o espetáculo", "fr": "des places pour le spectacle", "de": "Plätze für die Vorstellung",
      "it": "posti per lo spettacolo", "en": "seats for the show"}),
    (r"\b(?:class|lesson|workshop)\b", "a class", "experience", "people", "book",
     {"es": "una clase", "pt": "uma aula", "fr": "un cours", "de": "einen Kurs", "it": "una lezione", "en": "a class"}),
    (r"\b(kayak|boat|walking|food|wine|city)\s+tour\b|\btour\b", "a tour", "experience", "people", "book",
     {"es": "una visita guiada", "pt": "uma visita guiada", "fr": "une visite guidée", "de": "eine Führung", "it": "una visita guidata", "en": "a tour"}),
]
_ASK_SPACE = re.compile(r"\b(when (?:(?:do|would|could) )?(?:they|you)(?:'d| would)? have (?:space|room|availability|a slot)|any ?time|whenever|when can they)\b", re.I)
_QUOTE = re.compile(r"\b(how much|what (?:would|does) it cost|price|quote)\b", re.I)
_UNITS = {"sessions": r"sessions?", "pieces": r"pieces?|tattoos?", "places": r"places|spots|seats"}
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_N = r"(\d{1,2}|" + "|".join(_NUM) + r")"

QUESTIONS = {
    "activity": "What would you like me to book?",
    "when": "Which day and time — or shall I ask them when they have space?",
    "count": "How many {unit} is it for?",
    "unit": "Is that for a number of people, or of sessions?",
}


#: Sasha 148 · the day is known; only the time is asked — same ending as QUESTIONS["when"], so a reply joins the thread
SPACE_TAIL = " — or shall I ask them when they have space?"


def ask_time(day: str) -> str:
    from . import sentences as SN
    return f"What time on {SN.day_words(day)}{SPACE_TAIL}"


def _n(t: str) -> int:
    return int(t) if t.isdigit() else _NUM[t]


def _time(t: str) -> Optional[str]:
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    if m:
        return f"{int(m[1]) % 12 + (12 if m[3] == 'pm' else 0):02d}:{int(m[2] or 0):02d}"
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
    return f"{int(m[1]):02d}:{m[2]}" if m else None


def _window(t: str, day: Optional[str]) -> Optional[dict]:
    m = re.search(r"\bbetween\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+and\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", t)
    if not m or not day:
        return None
    a, b = _time(m[1]), _time(m[2])
    if not (a and b) or a >= b:
        return None   # "between 10 and 1" is not stated plainly enough: asked, not guessed
    return {"earliest": f"{day}T{a}", "latest": f"{day}T{b}"}


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_UNDER = re.compile(r"\b(?:under(?: the name(?: of)?)?|in the name of|name(?:d)?:?)\s+([A-ZÀ-Þ][\w'’.-]{1,40}(?:\s+[A-ZÀ-Þ][\w'’.-]{1,40}){0,2})")


def plain_day(message: str, now: Optional[datetime] = None) -> Optional[str]:
    """Sasha 86 · the day the message states: a plain date (handoff.plain_date), else today/tonight, else a weekday —
    the next one, today included, exactly as the cards' "open then" reads it (handoff.plain_open_at). "Saturday" said
    on Thursday 1 Oct 2026 is Saturday 3 Oct. Nothing else is guessed."""
    day = HO.plain_date(message, now)
    if day:
        return day
    t = (message or "").lower()
    today = HO._today(now)
    if re.search(r"\b(today|tonight|this evening)\b", t):
        return today.isoformat()
    m = re.search(r"\b(" + "|".join(_WEEKDAYS) + r")\b", t)
    if m:
        from datetime import timedelta
        return (today + timedelta(days=(_WEEKDAYS.index(m[1]) - today.weekday()) % 7)).isoformat()
    return None


def plain_name(message: str) -> Optional[str]:
    """Sasha 86 · the name a booking is under, when the message says so plainly ("under Warren"); else None."""
    m = _UNDER.search(message or "")
    return m[1].strip() if m else None


def in_venue_language(what: Mapping[str, Any], lang: str) -> Dict[str, Any]:
    """Sasha 86 · the activity as it is SAID AT THE VENUE: a word from the list in another language ("a table" for a
    Spanish venue) becomes the venue's ("una mesa"). A wording the guest typed that is not on the list is kept as typed."""
    out = dict(what)
    code = (lang or "en").split("-")[0].lower()
    said = str(out.get("activity_venue_lang") or "").strip()
    for _rx, en, _cat, _unit, _flow, words in ACTIVITIES:
        if out.get("activity") == en or said in words.values():
            if code in words and (not said or said in words.values()):
                out["activity_venue_lang"] = words[code]
            break
    return out


def draft(message: str, now: Optional[datetime] = None, lang: str = "en") -> Dict[str, Any]:
    """{parts: what the message states, missing: [...], question: the ONE thing to ask next, or None}."""
    message = HO.spoken(message)   # Sasha 88 · "nine p.m." said aloud is 9pm
    t = (message or "").lower()
    parts: Dict[str, Any] = {}
    act = next((a for a in ACTIVITIES if re.search(a[0], t)), None)
    if act:
        _, en, category, unit, flow, words = act
        parts["what"] = {"activity": en, "activity_venue_lang": words.get(lang.split("-")[0], words["en"]), "category": category}
        parts["flow"] = "quote_first" if (flow == "quote_first" or _QUOTE.search(t)) else "book"
    day = plain_day(message, now)
    hhmm = _time(t) or HO.context_time(message)   # Sasha 101 · "dinner … at nine" is 21:00
    win = _window(t, day)
    if _ASK_SPACE.search(t) or (parts.get("flow") == "quote_first" and not (day and hhmm)):
        parts["when"] = {"mode": "venue_proposes"}
        if parts.get("flow") == "book":
            parts["flow"] = "availability"
    elif win:
        parts["when"] = {"mode": "window", "window": win}
    elif day and hhmm:
        parts["when"] = {"mode": "at", "at": f"{day}T{hhmm}"}
    elif day:   # Sasha 148 · a day said without a time is KEPT (CR 20: "on arrival" = 1 March), and only the time is asked
        parts["day"] = day
    # how many — in the activity's own unit
    unit = act[3] if act else None
    for u, rx in _UNITS.items():
        m = re.search(rf"\b{_N}\s+(?:{rx})\b", t)
        if m:
            parts["how_many"] = {"count": _n(m[1]), "unit": u}
    if "how_many" not in parts:
        p = HO.plain_party(message) or (1 if re.search(r"\b(just me|only me|on my own|1 person|one person)\b", t) else None)
        if p:
            parts["how_many"] = {"count": p, "unit": "people"}
        elif unit and unit != "people":
            m_act = re.search(act[0], t)
            if m_act and re.search(r"\b(a|an|one)\s+(?:[\w-]+\s+){0,3}$", t[:m_act.start()]):
                parts["how_many"] = {"count": 1, "unit": unit}           # "a fine-line tattoo" says one
    name = plain_name(message)
    if name:
        parts["who"] = {"name": name}
    missing = [k for k, ok in (("activity", "what" in parts), ("when", "when" in parts), ("count", "how_many" in parts)) if not ok]
    question = None
    if missing:
        k = missing[0]
        if k == "count":
            question = QUESTIONS["count"].format(unit=unit) if unit else QUESTIONS["unit"]
        elif k == "when" and parts.get("day"):
            question = ask_time(parts["day"])
        else:
            question = QUESTIONS[k]
    return {"parts": parts, "missing": missing, "question": question}


def complete(d: Mapping[str, Any], *, who: Mapping[str, Any], where: Mapping[str, Any], notes: Optional[str] = None) -> Dict[str, Any]:
    """The draft + the guest (their profile) + the venue (its read) → a validated reservation/1. Refuses if anything
    is still missing — it never fills a gap."""
    if d["missing"]:
        raise RS.ReservationRefused("draft_incomplete", f"still to ask: {', '.join(d['missing'])}")
    p = d["parts"]
    obj = {"schema": RS.SCHEMA, "flow": p["flow"], "who": dict(who), "where": dict(where), "what": p["what"],
           "when": p["when"], "how_many": p["how_many"], **({"extras": {"notes": notes}} if notes else {})}
    return RS.validate(obj)


# ── the chat turn (conductor hook, Stage B) ──────────────────────────────────────────────────────────────────────────

_BOOK = re.compile(r"\b(book|booking|reserve|reservation|appointment)\b", re.I)


def _thread(message: str, history: List[Mapping[str, Any]]) -> Optional[str]:
    """The booking request this message belongs to: if Sasha's last line was one of the draft's questions, the guest's
    lines since the request that started it, joined; else this message alone, if it is a booking request at all."""
    asked = set(QUESTIONS.values()) | {QUESTIONS["count"].format(unit=u) for u in ("people", "sessions", "pieces", "places")}
    last = next((h for h in reversed(history) if h.get("role") == "assistant"), None)
    said = str((last or {}).get("content") or "").rstrip()
    if last and (any(said.endswith(q) for q in asked) or (said.endswith(SPACE_TAIL.strip()) and "What time on " in said)):
        users: List[str] = []
        for h in reversed(history):
            if h.get("role") == "user":
                users.insert(0, str(h.get("content") or ""))
                if _BOOK.search(users[0]):
                    return " ".join(users + [message])
        return None
    return message if _BOOK.search(message or "") and any(re.search(a[0], (message or "").lower()) for a in ACTIVITIES) else None


def booking_turn(message: str, history: Optional[List[Mapping[str, Any]]] = None, now: Optional[datetime] = None) -> Optional[dict]:
    """A full conductor turn for a booking request — ONE question for what is missing, or the complete draft — or None,
    and the conductor carries on exactly as before. Psi has its own hand-off (handoff.py), which runs first."""
    history = list(history or [])
    text = _thread(message, history)
    if text is None:
        return None
    d = draft(text, now)
    if d["missing"]:
        response = d["question"]
    else:
        p = d["parts"]
        when = p["when"]
        said = (p["when"]["at"].replace("T", " at ") if when["mode"] == "at"
                else f"between {when['window']['earliest'][11:]} and {when['window']['latest'][11:]} on {when['window']['earliest'][:10]}" if when["mode"] == "window"
                else "whenever they have space")
        ask = {"quote_first": "ask what it would cost and when they could do it", "availability": "ask when they have space"}.get(p["flow"], "book it")
        n, unit = p["how_many"]["count"], p["how_many"]["unit"]
        one = {"people": "person", "sessions": "session", "pieces": "piece", "places": "place"}[unit]
        response = (f"So: {p['what']['activity']}, {n} {one if n == 1 else unit}, {said}. "
                    f"Which place? I'll look them up, {ask}, and read it all back to you before anything happens.")
    return {
        "response": response, "intents": ["booking"], "photos": [], "tools_used": [], "links": [],
        "hotels": [], "bookings": [], "itinerary": None, "action": None, "booking_ref": None,
        "itinerary_id": None, "payment_item": None, "saved_card": None,
        "messages": history + [{"role": "user", "content": message}, {"role": "assistant", "content": response}],
        "reservation_draft": d,   # S-64 step 11 · the parts of reservation/1 the conversation states, and what is missing
    }
