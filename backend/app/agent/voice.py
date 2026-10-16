"""Sasha 249 · HER VOICE, IN ONE PLACE (EU 246's demo path §2) — the persona rules every surface's prompt carries, the sentences the
tools hand her word for word, and the transcript check the deploy gate runs. Nothing else in the code words these.

  RULES        → appended to /s2's system text (WhatsApp shares it) and /next's under S1 parity (parity off: /next unchanged)
  ASK_BOOK     → the one booking question, when a venue has a form AND another way (agapi.venue_truth.ASK_FILL is this)
  CHOICES      → its two answers, as buttons / a list
  done_form()  → the confirmation once a prefilled form is on their screen
  SENT         → the confirmation once a request has gone to the venue
  READ_BACK_ASK / read_back_line() → Sasha 262 · the one line over a read-back card, said by code (sasha.turn)
  faults()     → a transcript's breaches: a channel named, or a second question for the same detail
  SHOWS / SAYS → Sasha 251 · which tools put something on screen; FAILED / failed_line() → what she says when one failed and
                 nothing was drawn; claims_shown() / honest_faults() → a claim of what isn't there (sasha.turn acts on it)
  TOLD / told_line() / told_prefix() → Sasha 254 · the booking rules' refusals and stops, said in the rules' words (sasha.turn)
  OUTAGE / outage_line() → Sasha 261 · an AgAPI outage (its budget spent, rate-limited, not answering), one plain line (sasha.turn)
  PROGRESS_S / progress_line() / Steps → Sasha 264 · no silence: a line from the step running, every PROGRESS_S (stream + WhatsApp)
  BRIEF_MAX / brief()  → Sasha 264 · short, never twice: her own sentences capped, never last reply's or a card's (sasha.turn)
  NOT_FILLED / PAGE_HERE / phone_line() / platform_line() / page_line() → Sasha 264 · a form or a platform's page, said as it is
"""
from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Iterable, List, Optional, Sequence, Tuple

TRY_FIRST = "Let me see what I can do."   # Sasha 268 · item 7: her first answer to any request for a service (first_line, RULES)
ASK_BOOK = "I'll book it. Want a prefilled form you just confirm, or shall I handle it and let you know?"
CHOICES = ({"title": "Prefilled form", "route": "page"}, {"title": "Handle it", "route": None})
DONE_FORM = "Done — it's on your screen, tap to confirm."
DONE_FORM_WA = "Done — it's below, tap to confirm."   # WhatsApp: the card arrives as the next message, not "on your screen"
SENT = "Sent. I'll tell you when they reply."
#: Sasha 256 · the one line over a venue read-back card (its details are on the card, never recited). Sasha 262 (S2 item 10, row 911):
#: said BY CODE and the turn ends there (sasha.turn) — the model once added "I haven't booked it yet. I need a clear yes first."
READ_BACK_ASK = "Shall I send this to {venue}? Every detail is on the card."


#: Sasha 262 · S2 item 3 (row 911): ONE TOTAL — a turn that priced the trip says the trip's one figure (basket.trip_figures, the Trip
#: tab's ALL IN). EU 257's run: her reply carried no € total at all, the Trip tab said €482. When she leaves it out, it's said by code.
TOTAL_LINE = "All in, that's about €{eur}."
TOTAL_TOOLS = ("propose_trip", "swap_stay", "choose_offer")
_EUROS = re.compile(r"€\s?(\d[\d.,]*)|(\d[\d.,]*)\s?(?:€|euros?\b|EUR\b)", re.I)


def total_line(figures: dict, text: str) -> str:
    """The one total's line when her reply doesn't already say that figure (within €1), else ""."""
    t = (figures or {}).get("total_eur")
    if not isinstance(t, (int, float)) or t <= 0:
        return ""
    for m in _EUROS.finditer(text or ""):
        try:
            if abs(float((m.group(1) or m.group(2)).replace(",", "").rstrip(".")) - t) <= 1:
                return ""
        except ValueError:
            continue
    return TOTAL_LINE.format(eur=f"{round(t):,}")


def read_back_line(tool: str, r: dict) -> str:
    """The read-back line a booking tool's result carries on a screen (hold_venue / book_venue: awaiting_yes + its card), else ""."""
    res = (r or {}).get("result") if (r or {}).get("ok") else None
    if tool not in ("hold_venue", "book_venue") or not isinstance(res, dict) or res.get("status") != "awaiting_yes":
        return ""
    if res.get("choices") and res.get("ask") and res.get("read_back"):   # Sasha 265 · item 4: the ONE question that IS the call's card
        return res["ask"]
    return res["ask"] if res.get("read_back") and res.get("ask") and res["ask"] == READ_BACK_ASK.format(venue=res.get("venue")) else ""


# Sasha 263 · S2 item 10 (row 914): the in-app yes sends ONLY the card on their screen. No card waiting: this line, and nothing is sent.
# Sent and confirmed: one sentence with its reference and the one question — two sentences, said by code; the turn ends on it.
NOTHING_WAITING = "There's nothing waiting to send."
CALENDAR_ASK = "Shall I put it in your calendar?"


def booked_line(venue: str, when: str, ref: Optional[str]) -> str:
    return f"✅ Booked: {venue}, {when}" + (f" — reference {ref}." if ref else ".")


def yes_line(tool: str, r: dict) -> str:
    """The line an in-app yes ends on (book_venue): nothing waiting, or booked + the calendar question. Else "" (WhatsApp: as it was)."""
    res = (r or {}).get("result") if (r or {}).get("ok") else None
    if tool != "book_venue" or not isinstance(res, dict) or not res.get("in_app"):
        return ""
    if res.get("status") == "nothing_waiting":
        return NOTHING_WAITING
    if res.get("status") == "confirmed" and res.get("line"):
        return f"{res['line']} {CALENDAR_ASK}"
    if res.get("status") == "calling" and res.get("line"):   # Sasha 265 · item 4: the call act's own "On it — …", and only that
        return res["line"]
    return ""

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

# Sasha 269 · Tyler (15 Oct): never "no online booking form" — when the venue engine (venue.profile) finds no form of their own, this
NO_LINK = "I can't see their booking link from here — if you can, send it to me and I'll fill it in."
RESERVABLE = "They take reservations."   # Sasha 270 · CR 101's reservable.say, word for word (their listing, via the Places API)


def no_link_line(reservable=None) -> str:
    """No own booking form found: said this way, never "they have no online booking form" (it may well exist — we just can't see it).
    Sasha 270 · + their listing's reservable, said as fact in the engine's own words (venue.profile reservable.say) when it said."""
    said = reservable.strip() if isinstance(reservable, str) and reservable.strip() else (RESERVABLE if reservable is True else "")
    return f"{NO_LINK} {said}" if said else NO_LINK


# Sasha 270 · CR 101 · A LINK THE PERSON HANDED OVER, classified by the venue engine (venue.profile link) — said short.
LINK_ON_IT = "OK, I'm on it."   # theirs to fill by Sasha (owner kanoe): before the read-back's one question
#: the person's to finish (owner "the person"), by what the link IS — the engine's say without the host it names (her voice never names
#: how a booking travels), and never "no booking form" about a place
LINK_THEIRS = {"captcha": "Their form asks you to prove you're human, so that last step is yours — here it is.",
               "needs_sign_in": "Their form needs you to sign in, so it's yours to fill — here it is.",
               "platform": "Here's their page — you finish it there.",
               "not_a_booking_form": "That page isn't a booking form I can fill in — here it is to look at.",
               "cant_read": "I couldn't read that page from here — here it is to open yourself."}


def link_line(channel: Optional[dict]) -> str:
    """The one line for a handed-over link that is the person's to finish (or couldn't be read): by its kind; else the engine's `say`
    with any "(host)" taken out."""
    ch = channel or {}
    if ch.get("kind") in LINK_THEIRS:
        return LINK_THEIRS[ch["kind"]]
    say = re.sub(r"\s*\([^)]*\)", "", str(ch.get("say") or "")).strip()
    return say or LINK_THEIRS["cant_read"]


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
- Try first. Asked for any service or business (a dog walker, a tattoo, a dentist, a plumber, a florist — anything with a web
  presence), her first answer is "{TRY_FIRST}" and then she does it: search for it, show the cards, find how they take bookings, ask
  the one question. "I can't" is never her first answer; she says it only after a tool actually tried and failed — and then with what
  she found and what she CAN do.
- Never say a place has "no online booking form" or "no booking form": when read_booking_route's `how` gives it, say it word for word —
  "{NO_LINK}"
- Short: two or three sentences at most — the card or the list carries the detail. Never repeat what's already on their screen,
  what you said earlier in this reply, or what you said in your last reply.
- A booking page is always on their screen as a card they tap; sending it to their phone is an extra. Never say it can only go to
  their phone.
- When they send a link to a place's booking page (typed, spoken or on WhatsApp), call hold_venue with that booking and `link` set to
  it, exactly as they sent it. Never judge the link yourself (a form, a platform, a sign-in) — hold_venue's result says.
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
        "remember_name", "save_contact", "file_confirmation", "time_between", "add_to_trip", "save_for_later",   # Sasha 253 · said, no card
        "call_again")   # Sasha 269 · the act's own `say`

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


# Sasha 273 · rule 15 (row 1035 · 6, Tyler's demo 16 Oct): never name OR LIMIT how a place books. She said "Periplo takes bookings by
# phone only" and "the only route I can use is a phone call" — the model's paraphrase of read_booking_route's "By phone." and its routes.
# How a place books is said as BOOK_IT (read_booking_route's `how` on the one path), then the one question (the card); a sentence of hers
# that limits the channel is dropped before it is said (sasha.turn, /s2 and S1 parity) and flagged by faults() (the deploy gate).
BOOK_IT = "I'll make the booking."
#: the booking rules' R3 wait ("Their only way to book is by phone, and it's still a while away — …"), said on the one path without the limit
WAIT_TO_CALL = "It's still a while away — I'll call them closer to the day."
_MEANS = r"(?:the )?(?:phone|telephone|calls?|(?:a )?message|messages|text|texts|e-?mail|emails|their form|forms?|online)"
_LIMIT = re.compile(
    r"\b(?:takes?|accepts?|does|do|handles?)\s+(?:bookings|reservations|booking|reservation)s?\s+(?:only\s+)?(?:by|via|over|through)\s+" + _MEANS +
    r"|\b(?:by|via|over|through)\s+" + _MEANS + r"\s+only\b|\bonly\s+(?:by|via|over|through)\s+" + _MEANS +
    r"|\b(?:the|their|its) only (?:route|way|option|channel|method)s?\b[^.?!]{0,40}\b(?:book\w*|reserv\w*|phone|call\w*|message\w*|e-?mail|use)\b"
    r"|\b(?:phone|a call|calls?|messages?|e-?mail)\s+(?:is|are)\s+(?:the|their)\s+only\b", re.I)


def limits_channel(text: str) -> bool:
    """Sasha 273 · one thing she says names a single way a place books as its only one ("by phone only", "the only route…")."""
    return bool(_LIMIT.search(text or ""))


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
        if limits_channel(text):   # Sasha 273 · rule 15: nor limits it
            out.append(f"turn {i}: limits the channel {_LIMIT.search(text).group(0)!r}")
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


# Sasha 254 · THE RULES' WORDS ARE HEARD (found live on /s2, Hammam Al Ándalus: hold_venue's rules said "This account is in test
# mode, so I won't contact a real venue." and she paraphrased it away). The booking rules' refusals and automatic stops are TOLD to
# the person: when a booking tool's result carries one of these say_keys (or any refusal), the reply must contain the rules'
# sentence — sasha.turn puts it in front, once, whatever the model wrote. agapi/booking_rules/booking_rules.py PHRASES is the list.
TOLD = frozenset({"not_live", "no_real_sends", "no_channel", "calls_cap", "too_soon", "stopped", "platform", "prepared_link_captcha"})
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _plain(t: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", " ", (t or "").lower().replace("’", "'").replace("'", "")).split())


def told_line(result) -> str:
    """The rules' sentence a booking tool's result must have said to the person ("" when it carries none to tell)."""
    rules = result.get("rules") if isinstance(result, dict) else None
    if not isinstance(rules, dict) or not rules.get("say"):
        return ""
    if rules.get("say_key") not in TOLD and not rules.get("refusals"):
        return ""
    line = " ".join(str(rules["say"]).split())
    return "" if channel_words(line) else line   # never a channel name, even in the rules' own words


def is_told(sentence: str, lines: Iterable[str]) -> bool:
    """One sentence she wrote IS one of the rules' told sentences (said as the rules say it — never dropped as "internal")."""
    p = _plain(sentence)
    return bool(p) and any(p == _plain(s) for line in lines for s in _SENT_SPLIT.split(line or ""))


def told_prefix(text: str, lines: Iterable[str]) -> str:
    """What goes in front of her reply: for each told line whose FIRST sentence she didn't say, its sentences she didn't say —
    once (a sentence already in the reply, or already put in front, is never said twice). "" when nothing is missing."""
    have = _plain(text)
    out: List[str] = []
    for line in dict.fromkeys(x for x in lines if x):
        sents = [s.strip() for s in _SENT_SPLIT.split(line) if s.strip()]
        if not sents or _plain(sents[0]) in have:
            continue
        for s in sents:
            if _plain(s) and _plain(s) not in have:
                out.append(s)
                have += " " + _plain(s)
    return " ".join(out)


# ── Sasha 257 · THE HOLDING LINE (Tyler, row 863: "a WhatsApp question took 10–15 s before any reply") ─────────────────────────────
#: when her reply isn't ready within HOLD_AFTER_S: ONE short line, rotating — never a claim (nothing found, booked or sent), never for a
#: fast reply. The same words on every surface (WhatsApp, /s2, /next with parity); spoken when her voice is on.
HOLDING = ("On it — one moment.", "Getting that for you now.", "Looking now, one sec.")
HOLD_AFTER_S = 3.0
_HELD_N: dict = {}


def holding_line(account: str = "") -> str:
    """The next holding line for this person (rotating, so it never sounds canned)."""
    n = _HELD_N.get(account or "", 0)
    _HELD_N[account or ""] = n + 1
    return HOLDING[n % len(HOLDING)]


# ── Sasha 264 · item 1 — NO SILENCE (Tyler's beta, 14 Oct: one line at 3 s, then 20–44 s of nothing while tools ran) ───────────
#: after the holding line, while the turn still works: a line every PROGRESS_S, from the step ACTUALLY running (the tool that started
#: and hasn't returned), varied, never a claim (nothing found, booked, sent, done). The same lines on every surface: the stream's
#: "hold" event (/s2, /next with parity — shown and spoken) and a message on WhatsApp.
PROGRESS_S = 5.0   # Sasha 265 · item 5 (row 935, Tyler: "about every 5 s"; was 6.0)
_STEP = {
    "stays": ("Looking at hotels now.", "Still going through the hotels.", "Comparing a few places to stay."),
    "flights": ("Checking flights.", "Still checking the flights.", "Looking at the flight times."),
    "trip": ("Putting the trip together.", "Still building the trip.", "Working out the days and the flights."),
    "places": ("Looking at places now.", "Still looking through the places.", "Checking a few more places."),
    "route": ("Checking how they take bookings.", "Still checking how they take bookings.", "Looking at their booking page."),
    "booking": ("Setting up the booking.", "Still setting up the booking.", "Working on the booking."),
    "up": ("Bringing that up.", "Still pulling that up.", "Getting that up for you."),
    None: ("Still on it.", "Bear with me — still working.", "Still working on it.", "Nearly there…"),   # 265: Tyler's "Nearly there…" ("Almost done…" is a claim)
}
_STEP_OF = {"search_stays": "stays", "swap_stay": "stays", "search_flights": "flights", "choose_offer": "flights", "check_offer": "flights",
            "propose_trip": "trip", "prepare_trip": "trip", "search_venues": "places", "suggest_activities": "places",
            "read_booking_route": "route", "hold_venue": "booking", "book_venue": "booking", "hold_booking": "booking", "book": "booking",
            "cancel_venue": "booking", "change_booking": "booking", "cancel_booking": "booking", "get_trip": "up", "get_status": "up",
            "get_total": "up", "my_plans": "up", "get_activity": "up", "what_i_can_do": "up", "keep_list": "up"}
_STEP_N: dict = {}


# ── Sasha 265 · item 5 — THE FIRST LINE, AT ONCE (row 935, Tyler 14 Oct 16:54: a destination on /next, "she just sits and looks at me
# for about 20 seconds") ─ a request for WORK (a trip, a place, dates, a booking, a search) gets this line the instant it arrives — before
# anything else of the turn, under 1 s on the page, spoken when her voice is on — then a progress line about every PROGRESS_S. A turn
# that isn't work (a yes, a thanks, a question of fact) keeps the holding line at HOLD_AFTER_S, only if it's slow. Every surface reads it:
# the stream's first event (/s2, /next — her face's caption and voice too) and WhatsApp's first message.
FIRST_LINE = "Great — let me pull something together, it might take a few seconds."
# Sasha 271 · B (row 1008, Tyler's words) · HER ARRIVAL: half-body, "Hey there" (a return: "Hey <name>"), then at once CAMERA_OFF —
# and she moves to the corner circle. Replaces Sasha 268's "full size until his first request". Said by code, never the model's; spoken
# by her live face when it is up, else her voice. CAMERA_OFF is also what she says when a tap brought her back and his next request
# sends her to the corner again.
HELLO = "Hey there"
HELLO_BACK = "Hey {name}"
CAMERA_OFF = "I'm turning off my camera, but just speak to me naturally. You can always tap to get me back."


def arrival_line(name: Optional[str] = None, back: bool = False) -> str:
    """Her arrival, in one breath: "Hey there." / (a return) "Hey <first name>." — then CAMERA_OFF."""
    first = str(name or "").strip().split(" ")[0][:40]
    return f"{HELLO_BACK.format(name=first) if back and first else HELLO}. {CAMERA_OFF}"
FIRST_GAP_EARLY_S = 1.0   # after the first line, the first progress line comes this much sooner (the page said it ~1 s earlier)
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
# Sasha 268 · item 7 (rows 954/955, Tyler 21:00: "Can you find a dog walker and schedule one?" → "I can't do that yet, but I've noted
# it" — then, pushed, she found one and offered to call: "this is perfect"). Kanoe's promise: if a business has any web presence, she can
# try to reach it. Her first answer to ANY request for a service is TRY_FIRST, then she does it (search → cards → how they take
# bookings → the one question). "I can't" is never a first answer — only after a tool actually tried and failed (RULES, below).
_TRIP = re.compile(r"\b(?:trip|travel\w*|holiday|vacation|getaway|honeymoon|itinerary|plan|planning|going|go\s+to|fly|flying|flights?|"
                   r"hotels?|restaurants?|table|tour|visit\w*)\b"
                   r"|\b" + _MONTH + r"\s+\d{1,2}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH + r"\b", re.I)
_ASK = re.compile(r"\b(?:book|booking|reserve|reservation|find|search|look\s+for|get\s+me|schedule|appointment|arrange|hire|order|"
                  r"send|fix|repair|deliver\w*|someone\s+to|i\s+need|i\s+want\s+(?:a|an|to|some)|i'?d\s+like\s+(?:a|an|to|some))\b", re.I)
_WORK = re.compile(_TRIP.pattern + "|" + _ASK.pattern, re.I)   # any request for work: the page's rule (GET /api/agent/first-line)


def first_line(message: str) -> Optional[str]:
    """FIRST_LINE for a trip, a table or dates; TRY_FIRST for any other request for a service (268); else None (not work)."""
    m = message or ""
    return FIRST_LINE if _TRIP.search(m) else TRY_FIRST if _ASK.search(m) else None


def progress_line(tool: Optional[str], account: str = "") -> str:
    """The next progress line for the step running now (`tool`: the tool running, None while she's still thinking) — rotating per
    person, so the same step never sounds the same twice in a row."""
    lines = _STEP[_STEP_OF.get(tool or "")] if tool else _STEP[None]
    n = _STEP_N.get(account or "", 0)
    _STEP_N[account or ""] = n + 1
    return lines[n % len(lines)]


class Steps:
    """Sasha 264 · the tools running now, in the order they started: a turn's {"type": "tool_start", "name"} puts one in, its
    {"type": "tool", "name"} takes it out. `now` is the step a progress line speaks for."""

    def __init__(self):
        self.running: List[str] = []

    def see(self, ev) -> None:
        if not isinstance(ev, dict):
            return
        if ev.get("type") == "tool_start" and ev.get("name"):
            self.running.append(ev["name"])
        elif ev.get("type") == "tool" and ev.get("name") in self.running:
            self.running.remove(ev["name"])

    @property
    def now(self) -> Optional[str]:
        return self.running[0] if self.running else None


#: WhatsApp's turn runs in its own task: the Steps it reports into (set by guest_whatsapp._brain_turn, read by wa_agent.agent_turn)
STEPS: "ContextVar[Optional[Steps]]" = ContextVar("sasha_steps", default=None)


# ── Sasha 264 · item 5 — SHORT, NEVER TWICE (Tyler's beta: she repeats herself and says too much) ──────────────────────────────
#: her own words in a turn: at most BRIEF_MAX sentences (the card or the list carries the detail); a sentence she has said this turn,
#: or in her last reply, or that a card on screen already says, is never said again. Held in code (sasha.turn: brief()), and told.
BRIEF_MAX = 3   # told in RULES too ("Short: two or three sentences at most …")


def _sent_key(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower().replace("’", "'").replace("'", "")).split())


def brief(sentences: Sequence[str], said: Iterable[str], seen: Iterable[str], count: int, asked: bool) -> Tuple[List[str], int, bool]:
    """Sasha 264 · item 5, in code: which of these sentences of hers may be said. `said`: what she has said this turn and in her last
    reply; `seen`: what is on their screen (a card's lines); `count`: her sentences so far this turn; `asked`: a question said already.
    Over BRIEF_MAX, only her first question still goes (she never loses the question she's asking). → (kept, count, asked)."""
    have = {_sent_key(x) for line in said for x in _SENT_SPLIT.split(line or "") if _sent_key(x)}
    have |= {_sent_key(x) for x in seen if _sent_key(x)}
    out: List[str] = []
    for s in sentences:
        k = _sent_key(s)
        if not k or k in have:
            continue
        q = s.rstrip().endswith("?")
        if count >= BRIEF_MAX and not (q and not asked):
            continue
        out.append(s)
        have.add(k)
        count += 1
        asked = asked or q
    return out, count, asked


# ── Sasha 264 · items 2 and 3 — WHAT REACHED THEM, SAID AS IT IS ────────────────────────────────────────────────────────────────
#: item 2: AgAPI's venue.prepare_booking gave no filled page (Tyler's spa: the venue's own page opened, every field empty, and she said
#: "Done — it's on your screen, tap to confirm"). Never an empty page called prefilled: their page + the details to copy, said so.
NOT_FILLED = "I couldn't fill in their form, so their page is on your screen with your details to copy in. It's not booked until you confirm there."
CAPTCHA_TOO = " Their page asks you to prove you're human, which only you can do."


def not_filled_line(captcha: bool = False) -> str:
    return NOT_FILLED + (CAPTCHA_TOO if captcha else "")


#: item 3: a booking page is ALWAYS on their screen (a card they tap); their phone is an extra — and when that send fails, she says so.
PAGE_HERE = "Their page is on your screen — tap it to book there."
PHONE_FAILED = "I couldn't send it to your phone{why}."
_PHONE_WHY = {"outside the 24-hour window": " — you haven't messaged me there in the last day, so I'm not allowed to write first",
              "no whatsapp linked": " — there's no phone linked to your account", "opted out": " — you've asked me not to message you there",
              "whatsapp for guests is off": " — messages to phones are switched off right now"}


def phone_line(sent: bool, out: str) -> str:
    """What she says about their phone after a page went (or didn't) — "" when it arrived. `out`: the send's own result."""
    if sent:
        return ""
    o = (out or "").lower()
    if "already sent" in o:
        return ""
    why = next((v for k, v in _PHONE_WHY.items() if k in o), "")
    return PHONE_FAILED.format(why=why)


def page_line(tool: str, r: dict) -> str:
    """Sasha 264 · the line an in-app booking page ends on (book_venue → a platform's page, or a prepared form): the page is on their
    screen, the phone's outcome said, an unfilled form said as unfilled. Else "" (WhatsApp, and old S1: as they were)."""
    res = (r or {}).get("result") if (r or {}).get("ok") else None
    if tool not in ("book_venue", "hold_venue") or not isinstance(res, dict) or not res.get("in_app"):
        return ""
    if res.get("status") not in ("page_on_phone", "page_link"):
        return ""
    prep = res.get("prepared")
    if isinstance(prep, dict):   # their form: filled → "Done — it's on your screen" stays as it was; NOT filled → said so
        return NOT_FILLED if prep.get("filled") is False else ""
    if not res.get("page_url"):
        return ""
    return f"{res.get('page_says') or PAGE_HERE} {res.get('phone_line') or ''}".strip()   # a platform's page: its line, the phone's outcome


def platform_line(venue: str, party: int, when: str, filled: bool, gmail: bool) -> str:
    """Sasha 264 · item 8 (row 929): a platform's page in the app — ONE line over ONE button ("Open their booking page"). Never "shall
    I send" (she never sends on a platform), never an internal address, never the platform's name (her voice's first rule), and "filled
    in" only when the link really carries the slot."""
    who = f"{party} {'person' if party == 1 else 'people'}"
    slot = f"it's filled in for {who}, {when}" if filled else f"pick {when} for {who} there"
    then = "I'll pick up their confirmation from your email." if gmail else "forward me the confirmation when it arrives."
    return f"{venue} books on their own booking page — {slot}. Tap to book there; {then}"


# ── Sasha 258 · THE IN-APP YES (CR 97): her words when AgAPI refuses a tap — one plain line each, never a dead end ─────────────────
TAP_SAYS = {
    "approval_void": "Something in it changed, so here's the card again. Shall I send it?",      # + the new read-back card
    "approval_expired": "That card timed out, so here it is again. Shall I send it?",            # + a fresh read-back card
    "approval_untrusted_origin": "I couldn't confirm it's you on this device — please sign in again, then say yes.",
    "approval_consumed": "That's already been sent.",                                             # + the booking's status
}


def tap_line(code: str) -> str:
    return TAP_SAYS.get(code, "That didn't go through — nothing was sent. Shall I try again?")


# ── Sasha 261 · AN AGAPI OUTAGE, SAID (rows 897/900: the sandbox key's budget spent → "didn't work", or a statement offered) ──────
#: a tool failed and its AgAPI calls met an outage (agapi_health: "limit" = 402/429, "slow" = a timeout / unreachable) → ONE line,
#: said by code (sasha.turn), never a retry or an improvised alternative. The founder is emailed by agapi_health (once an hour).
OUTAGE = {"limit": "I can't {what} right now — the {service} has hit its limit. Kanoe has been told; nothing was sent.",
          "slow": "I can't {what} right now — the {service} didn't answer in time. Kanoe has been told; nothing was sent."}
OUTAGE_BOOKING = ("book_venue", "hold_venue", "read_booking_route", "cancel_venue", "book", "cancel_booking", "change_booking",
                  "running_late")


def outage_line(kind: str, tool: str) -> str:
    what, service = ("book", "booking service") if tool in OUTAGE_BOOKING else ("do that", "service I use for it")
    return OUTAGE.get(kind, OUTAGE["slow"]).format(what=what, service=service)


# ── Sasha 269 · "CALL THEM AGAIN" IS THE ENGINE'S (CR 100, booking-rules/2.1) ──────────────────────────────────────────────────────
# After a no-answer she reads AgAPI's own words (venue.call_attempt / venue.booking_status): `say` ("They didn't pick up."), then `ask`
# — the ONE question — as a card with its `choices`. The second no-answer: `say` + their page, no question. Her words below only join
# them; nothing here decides a call (venue.call_again does, under the booking's one approval).
NO_CALL_OPEN = "There's no call of theirs I can try again — nothing was dialled."
WA_TRY_AGAIN = "Reply \"try once more\" and I'll call them again."       # on WhatsApp the card's first choice is a reply
FORM_HERE = "Their form: {page}"


def act_line(say: Optional[str]) -> str:
    """Sasha 271 · CR 102 · a booking act's own words when its call opens with it (R6: "On it — I've emailed Hotel Sandbox, and I'll call
    them now too and let you know.") — said as the act says them, never re-worded; SENT when it gave none."""
    return str(say or "").strip() or SENT


def takeover_line(say: Optional[str], link: Optional[str]) -> str:
    """Sasha 272 · CR 103 · a call the booking can't make because their listing shows no number at that moment (takeover {kind
    "their_listing", link}): the act's own words when it gave them, else the existing no-channel line — always with their listing's link."""
    from agapi.booking_rules import booking_rules as BR
    said = str(say or "").strip() or BR.PHRASES["no_channel"]
    return f"{said} {link}" if link and link not in said else said


def no_answer_words(res: dict, channel: str = "page") -> str:
    """AgAPI's no-answer, said: its `say`, then (the first time) its `ask`, and their page — never a line of her own about a call.
    Sasha 272 · CR 103 · the take-over on their listing (next_step {kind their_listing, phone?, link?}): its number when the listing shows one
    now, and their listing's link — each only once (the act's say may already carry it)."""
    said = str(res.get("say") or "").strip()
    ask = str(res.get("ask") or "").strip()
    step = res.get("next_step") or {}
    page = str(step.get("page") or step.get("phone") or "").strip()
    link = str(step.get("link") or "").strip() if step.get("kind") == "their_listing" else ""
    page, link = ("" if page and page in said else page), ("" if link and link in said else link)
    parts = [said]
    if ask and channel == "whatsapp":   # no card on WhatsApp: the question, how to answer it, and the form's link
        parts += [ask, WA_TRY_AGAIN] + ([FORM_HERE.format(page=page)] if page else [])
    elif ask:
        parts.append(ask)               # on the page the choices are the card's buttons
    else:
        parts += [page, link]           # the second: the line + the link, no question
    return " ".join(p for p in parts if p)


__all__ = ["PROGRESS_S", "progress_line", "Steps", "STEPS", "BRIEF_MAX", "brief", "NOT_FILLED", "PAGE_HERE", "PHONE_FAILED", "phone_line",
           "NO_CALL_OPEN", "WA_TRY_AGAIN", "FORM_HERE", "no_answer_words", "act_line", "takeover_line", "HELLO", "HELLO_BACK", "CAMERA_OFF", "arrival_line", "BOOK_IT", "WAIT_TO_CALL", "limits_channel", "NO_LINK", "RESERVABLE", "no_link_line", "LINK_ON_IT", "LINK_THEIRS", "link_line",
           "page_line", "platform_line", "not_filled_line", "TOTAL_LINE", "TOTAL_TOOLS", "total_line", "READ_BACK_ASK", "read_back_line", "OUTAGE", "OUTAGE_BOOKING", "outage_line", "TAP_SAYS", "tap_line", "HOLDING", "HOLD_AFTER_S", "holding_line", "ASK_BOOK", "CHOICES", "DONE_FORM", "DONE_FORM_WA", "SENT", "CHANNEL_NAMES", "DETAILS", "RULES", "done_form", "channel_words",
           "faults", "check", "SHOWS", "SAYS", "FAILED", "claims_shown", "plain_why", "failed_line", "unshown", "honest_faults",
           "TOLD", "told_line", "told_prefix", "is_told"]
