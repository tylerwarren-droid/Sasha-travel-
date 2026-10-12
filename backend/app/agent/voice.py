"""Sasha 249 · HER VOICE, IN ONE PLACE (EU 246's demo path §2) — the persona rules every surface's prompt carries, the sentences the
tools hand her word for word, and the transcript check the deploy gate runs. Nothing else in the code words these.

  RULES        → appended to /s2's system text (WhatsApp shares it) and /next's under S1 parity (parity off: /next unchanged)
  ASK_BOOK     → the one booking question, when a venue has a form AND another way (agapi.venue_truth.ASK_FILL is this)
  CHOICES      → its two answers, as buttons / a list
  done_form()  → the confirmation once a prefilled form is on their screen
  SENT         → the confirmation once a request has gone to the venue
  faults()     → a transcript's breaches: a channel named, or a second question for the same detail
  SHOWS / SAYS → Sasha 251 · which tools put something on screen; FAILED / failed_line() → what she says when one failed and
                 nothing was drawn; claims_shown() / honest_faults() → a claim of what isn't there (sasha.turn acts on it)
"""
from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

ASK_BOOK = "I'll book it. Want a prefilled form you just confirm, or shall I handle it and let you know?"
CHOICES = ({"title": "Prefilled form", "route": "page"}, {"title": "Handle it", "route": None})
DONE_FORM = "Done — it's on your screen, tap to confirm."
DONE_FORM_WA = "Done — it's below, tap to confirm."   # WhatsApp: the card arrives as the next message, not "on your screen"
SENT = "Sent. I'll tell you when they reply."

# the channels she never names (EU 246 §2 rule 1), and the booking platforms the code knows by name
CHANNEL_NAMES = ("WhatsApp", "Instagram", "Booksy", "SevenRooms", "CoverManager", "FareHarbor", "Restaurantic", "TheFork", "OpenTable",
                 "Resy", "Fresha", "Treatwell", "Rover", "Bookeo", "Checkfront", "Mindbody", "Tock")
_CHANNEL = re.compile(r"\b(" + "|".join(CHANNEL_NAMES) + r")\b|\bweb form\b|\bAPI\b|\brungs?\b|\bthe ladder\b", re.I)
_API_CASE = re.compile(r"\bAPI\b")   # "api" only as the acronym (never "rapid", never a lowercase URL path)

# the details a booking asks for: one question each, ever
DETAILS = {
    "name": re.compile(r"\b(what name|which name|whose name|under what name|name (should|shall) (it|i|we) (be|put)|your (full )?name)\b", re.I),
    "time": re.compile(r"\b(what|which) time\b", re.I),
    "day": re.compile(r"\b(what|which) (day|date)\b", re.I),
    "party": re.compile(r"\bhow many (people|of you|guests|travell?ers)\b", re.I),
    "email": re.compile(r"\b(email address|your email|which email)\b", re.I),
    "phone": re.compile(r"\b(phone|mobile) number\b", re.I),
    "nationality": re.compile(r"\b(nationality|which passport|what passport)\b", re.I),
}

RULES = f"""

## Her voice (every surface)

- Never name how a booking travels: no WhatsApp, Instagram, booking-platform names, "web form", "API", "rung" or "ladder". Say
  what you'll do for them ("I'll send them the request"), never the pipe it goes down.
- When a place can take a prefilled form AND you could handle it for them, ask exactly this, word for word: "{ASK_BOOK}"
- Ask for every missing detail once, together, up front ("For two on Thursday at 9 — what name should it be under?"). Never ask
  again for something you have — from their Keep, what you remember, or earlier in this chat. If they move on without answering,
  don't ask it again: answer what they said, and leave the question where it is until they come back to it.
- Confirm short: one or two sentences, then the card. "{DONE_FORM}" / "{SENT}"
- When a tool fails (its result says ok: false), say plainly that it didn't work and what you'll do next. Never describe results,
  cards, a form, a booking, a message sent or a total that the tool didn't return — nothing is on their screen unless a tool put it
  there this turn.
"""

# Sasha 251 · HONEST RESULTS (found live on /s2: search_venues failed and she said "Have a look whenever you like and tap one if it
# tempts you" — no card was ever drawn). Every tool she has is in exactly one of these two tables (tests/test_s251_honest_results.py
# holds it): SHOWS — when it works, something appears on their screen (cards, a form, a read-back, a total, the trip); the value is
# what she calls it when it fails. SAYS — its answer is only ever in her words, so a failure has nothing on screen to lie about.
SHOWS = {
    "search_venues": "That search", "read_booking_route": "Looking up how they take bookings", "search_flights": "The flight search",
    "search_stays": "The search for places to stay", "propose_trip": "Putting the trip together", "swap_stay": "Changing the hotel",
    "choose_offer": "Changing the flight", "hold_booking": "Getting the booking ready", "book": "Setting up the payment",
    "get_total": "Adding it up", "get_trip": "Looking up your trip", "get_status": "Looking up your trip",
    "hold_venue": "Getting the booking ready", "book_venue": "The booking", "cancel_venue": "The cancellation",
    "my_plans": "Looking up your plans", "running_late": "Getting that message ready", "change_booking": "Getting the change ready",
    "cancel_booking": "Getting the cancellation ready", "send_email": "Sending that", "send_whatsapp": "Sending that",
    "hotel_request": "Sending that", "add_to_calendar": "The calendar links", "what_i_can_do": "Pulling that up",
    "keep_add": "Opening the photo picker",
    # fine print (CR 74/75/81) — each answers with a card on /s2
    "my_cards": "Looking up your cards", "add_card": "Adding the card", "card_cover": "Checking the cover", "which_card": "Checking your cards",
    "rental_cover": "Checking the cover", "accident": "Opening the accident case", "accident_notify": "Getting that message ready",
    "file_claim": "The claim", "claim_status": "Looking up the claim", "flight_money_back": "Checking what you're owed",
    "file_flight_claim": "The claim", "suggest_activities": "That search", "bag_money_back": "Checking what you're owed",
    "file_bag_claim": "The claim", "money_claim_status": "Looking up the claim", "entry_documents": "Checking the entry rules",
    "prepare_entry": "Getting the entry papers ready",
    # subscriptions (CR 72/84)
    "find_subscriptions": "Looking for your subscriptions", "plan_cancel_subscription": "The cancellation",
    "cancel_subscription": "The cancellation",
}
SAYS = ("prepare_trip", "check_offer", "save_travellers", "get_activity", "keep_list", "keep_use", "note_not_yet", "note_rental",
        "remember_name", "file_confirmation", "time_between", "add_to_trip", "save_for_later")   # Sasha 253 · said, no card

FAILED = "{what} didn't work{why}. Say the word and I'll try again."

# what claims something is on their screen, came back, or went out — false after a showing tool failed and nothing was drawn
_SHOWN_CLAIM = re.compile(
    r"\b(?:have|take) a (?:quick )?look\b|\bbelow\b|\bon (?:your|the) (?:screen|cards?|panel)\b|\btap (?:one|it|any|the|to|on)\b|"
    r"\btempts? you\b|\bpick (?:one|any)\b|\bhere (?:are|is|they are|it is)\b|\bhere's\b|\bi(?:'ve| have)? (?:found|pulled|put|got) "
    r"(?:you |some |a few |three |two |four |five |the )|\bthe (?:options|cards|results|places|flights|hotels|links) (?:are|is) "
    r"(?:up|here|below|ready|on)\b|\bit'?s (?:all )?(?:ready|there|on your)\b|^\W*(?:sent|done)\b|\b(?:i(?:'ve| have)|it'?s) "
    r"(?:sent|gone)\b|\bcheck (?:them|it) out\b", re.I)
# a sentence that says it didn't work is never a claim, whatever else it mentions
_SAYS_FAILED = re.compile(r"\b(?:didn'?t|did not|couldn'?t|could not|can'?t|cannot|wasn'?t able|not able|unable|won'?t|isn'?t "
                          r"working|went wrong|no luck|nothing came back|failed)\b", re.I)


def claims_shown(text: str) -> List[str]:
    """Sasha 251 · the sentences in what she says that claim something is on their screen (or came back, or went out) — and
    don't say it failed."""
    return [s for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip() and _SHOWN_CLAIM.search(s) and not _SAYS_FAILED.search(s)]


def plain_why(message: str) -> str:
    """A failed tool's own words, only when they read as plain words to a person (no codes, paths, tool names or instructions to
    the model) — else nothing."""
    m = (message or "").strip().rstrip(".")
    if not m or len(m) > 100 or re.search(r"[_(){}\[\]/<>|:]|\b(?:tool|call|answer with|get_status|retry|internal)\b", m, re.I):
        return ""
    return m


def failed_line(tool: str, message: str = "") -> str:
    """Sasha 251 · what she says when a showing tool failed and nothing reached their screen: that it didn't work, and what next."""
    why = plain_why(message)
    return FAILED.format(what=SHOWS.get(tool, "That"), why=f" — {why[0].lower() + why[1:]}" if why else "")


def unshown(calls: Iterable[dict], rendered: bool) -> List[dict]:
    """Sasha 251 · this turn's failed showing tools, when nothing reached their screen ([] when something did — a retry that worked,
    a second tool's card). `calls`: {"tool", "ok", "message"?}."""
    if rendered:
        return []
    return [c for c in calls if c.get("tool") in SHOWS and not c.get("ok")]


def honest_faults(turns: Iterable[dict]) -> List[str]:
    """Sasha 251 · the gate's sibling of faults(): each turn {"said", "calls": [{"tool","ok"}], "rendered": bool} → a breach when a
    showing tool failed, nothing was drawn, and what she said claims it was (or never says it didn't work)."""
    out: List[str] = []
    for i, t in enumerate(turns):
        failed = unshown(t.get("calls") or [], bool(t.get("rendered")))
        if not failed:
            continue
        for s in claims_shown(t.get("said") or ""):
            out.append(f"turn {i}: {failed[0]['tool']} failed and she says {s.strip()!r}")
        if not _SAYS_FAILED.search(t.get("said") or ""):
            out.append(f"turn {i}: {failed[0]['tool']} failed and she never says so")
    return out


def done_form(surface: str = "s2") -> str:
    return DONE_FORM_WA if surface == "wa" else DONE_FORM


def channel_words(text: str) -> List[str]:
    """The channel words in one thing she says (case-insensitive, except "API", which is only the acronym)."""
    found = []
    for m in _CHANNEL.finditer(text or ""):
        w = m.group(0)
        if w.lower() == "api" and not _API_CASE.fullmatch(w):
            continue
        found.append(w)
    return found


def _questions(text: str) -> List[str]:
    return [q.strip() for q in re.findall(r"[^.?!\n]*\?", text or "")]


def faults(transcript: Iterable[Tuple[str, str]]) -> List[str]:
    """A transcript of (role, text) turns → what breaks her voice: a channel named in anything she says, or a second question (in a
    later turn of hers) for a detail she has already asked for."""
    out: List[str] = []
    asked: dict = {}
    for i, (role, text) in enumerate(transcript):
        if role != "assistant":
            continue
        for w in channel_words(text):
            out.append(f"turn {i}: names the channel {w!r}")
        for q in _questions(text):
            for d, rx in DETAILS.items():
                if rx.search(q):
                    if d in asked and asked[d] != i:
                        out.append(f"turn {i}: asks for the {d} again (first asked in turn {asked[d]})")
                    asked.setdefault(d, i)
    return out


def check(lines: Sequence[str]) -> List[str]:
    """faults() for a single run of her lines (each one a turn of hers)."""
    return faults(("assistant", x) for x in lines)


__all__ = ["ASK_BOOK", "CHOICES", "DONE_FORM", "DONE_FORM_WA", "SENT", "CHANNEL_NAMES", "DETAILS", "RULES", "done_form", "channel_words",
           "faults", "check", "SHOWS", "SAYS", "FAILED", "claims_shown", "plain_why", "failed_line", "unshown", "honest_faults"]
