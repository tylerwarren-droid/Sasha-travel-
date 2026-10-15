"""CR 91 · THE BOOKING RULES — every rule in ONE place (EU 250 §A, docs/platform/booking-rules-and-access-spec.md). One pure function, no I/O:
decide(ctx) → Decision. Sasha (S1, S2, WhatsApp), DIVE, outside agents (EU 249) and the invite page read THESE rules; the file is vendored
byte-identical (like yes_one) and gated by vectors.json — one vector (or more) per rule.

Tyler's answers (12 Oct; mailbox rows 791, 798):
  · 48 h is the threshold (not 24) · own channels in this order: form → WhatsApp → email → phone
  · calls: at most 3 per PERSON per day (the server cap stays as a net) and at least 30 minutes between two calls to the SAME venue
  · deposits are REFUSED, never asked about · "the person can always take it over" is on EVERY answer · nothing is cancelled silently
  · never book on a platform — Booksy, Fresha, Treatwell, CoverManager and Zenchef included

ctx (all optional except venue and when):
  venue:  {type: restaurant|spa|hotel|activity|service|other, test: bool,
           channels: [{kind: form|own_engine|widget|whatsapp|email|phone|platform, value, host, captcha, required_consent}], open_now}
  when:   {booking_at: ISO, now: ISO}
  person: {access: {mode: test|live, calls: on|off, real_venue_sends: on|off}, preference: none|link|myself|handle|call|email|whatsapp}
  state:  {calls_today_person, server_calls_today, server_cap, last_call_to_venue_at, request_sent_at, venue_replied, prepared_link}
  booking: {venue, party, day, time} — the read-back's own words for the ONE question (booking-rules/2); missing parts come from venue.name and
           when.booking_at. venue.opens_at "HH:MM" (+ venue.open_now) says when a call can be made.

booking-rules/2 (CR 99, Tyler 14 Oct, row 928): the ONE question IS the read-back and its answer IS the approval, for every route — calls too.
  · a page of their own AND a phone, within the threshold, calls allowed → "<party> at <venue>, <day> <time> — fill in their page now, or
    shall I call them?" (answered: preference "link" → their page; "call" → the call)
  · no page, within the threshold, a phone → "I'll call them when they open at <time> — OK?" (open now: "… — shall I call them now?")
  · after the answer: "On it — <next step>." · the last unanswered call: "No one picked up again — I'd fill in their page instead."

booking-rules/2.1 (CR 100, Tyler 14 Oct: "if the user says call, try again, say it wasn't picked up, recommend the form"): EVERY call is an act
(venue.call_attempt), first or follow-up (R3/R5/R6), under the booking's ONE approval — nobody keeps a retry loop of their own.
  · the first unanswered call: "They didn't pick up." then the ONE question: "Try once more, or fill in their form so you just tap confirm?"
  · the second: "They didn't pick up again — the form is the fastest way." (+ the page) — no third call unless the person asks (the cap holds)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

VERSION = "booking-rules/2.1 · 2026-10-14"

# ── the constants, as data (never env vars) ──────────────────────────────────────────────────────────────────────────────
URGENT_HOURS = 48                           # R3/R4 · more than this → request and wait; within it → call or their own page
HOTEL_ARRIVAL_CALL_HOURS = 24               # R6 · a hotel arriving within this → call + email
HOTEL_NO_REPLY_HOURS = 24                   # R5 · a hotel that hasn't answered a request within this → call
CALLS_PER_PERSON_PER_DAY = 3                # R10 · per PERSON (the server-wide cap stays as a net: state.server_cap)
MIN_MINUTES_BETWEEN_CALLS_SAME_VENUE = 30   # R10 · never back to back: no instant redial after no answer
MAX_CALL_MINUTES = 4                        # R7–R9 · the call's own limit
CHANNEL_ORDER = ("form", "whatsapp", "email", "phone")   # R1 · own channels, for every venue type

# R14 · booking platforms: read and hand over their link, never press Book (Sasha venue_read.PLATFORMS ∪ AgAPI magellan.BOOKING_PLATFORMS)
PLATFORM_HOSTS = (
    "thefork", "eltenedor", "lafourchette", "opentable", "covermanager", "sevenrooms", "resy.com", "quandoo", "tablein", "bookatable",
    "resdiary", "zenchef", "guestonline", "restoo", "booksy", "fresha", "restaurantic", "treatwell",
    "direct-book.com", "book-directonline.com", "thebookingbutton", "littlehotelier.com", "cloudbeds.com", "mews.com", "mews.li", "synxis.com",
    "secure-hotel-booking.com", "d-edge.com", "availpro.com", "roiback.com", "neobookings.com", "bookassist", "guestcentric", "omnibees.com",
    "simplebooking.it", "webhotelier.net", "ihotelier.com", "hotetec.com",
    "booking.com", "expedia.com", "hotels.com", "airbnb.com", "vrbo.com", "agoda.com", "trip.com", "tripadvisor.com", "getyourguide.com",
    "viator.com", "klook.com", "tiqets.com", "checkyeti.com", "getmyboat.com", "exploretock.com", "fareharbor.com", "bokun.io", "rezdy.com",
    "checkfront.com", "peek.com", "xola.com", "regiondo.com", "trekksoft.com", "bookeo.com", "simplybook.me", "eventbrite.com",
    "ticketmaster.com", "skyscanner.net", "kayak.com", "hostelworld.com", "musement.com", "civitatis.com")

# ── the ONE phrasebook (say keys; never free text) ─────────────────────────────────────────────────────────────────────
PHRASES = {
    "ask_book": "I'll book it. Want a prefilled form you just confirm, or shall I handle it and let you know?",   # R2 · Sasha voice.ASK_BOOK
    "done_form": "Done — it's on your screen, tap to confirm.",
    "sent": "Sent. I'll tell you when they reply.",
    "request_wait": "I've asked them. It's a request until they reply — I'll tell you when they do.",
    "calling": "I'll call them now and tell you what they say.",
    "call_and_email": "It's soon, so I'll call them and email them too, and tell you what they say.",
    "platform": "They book on {platform}: their page is ready for you — you press Book there. I never book on a platform for you.",
    "prepared_link": "Here's their booking page, filled in for you — you confirm it there.",
    "prepared_link_captcha": "Here's their booking page, filled in for you — you confirm it there (it asks you to prove you're human, which only you can do).",
    "wait_to_call": "Their only way to book is by phone, and it's still a while away — I'll call them closer to the day.",
    "calls_cap": "I've made today's calls for you, so I won't call again today. Here's their page to finish it yourself.",
    "too_soon": "I called them less than 30 minutes ago — I won't call straight back. I'll try again later, or you can take it over now.",
    "not_live": "This account is in test mode, so I won't contact a real venue. Here's their page to book it yourself.",
    "no_real_sends": "I can't contact venues for you yet on this account. Here's their page to book it yourself.",
    "no_channel": "I couldn't find a way to book them online or by message. You can take it over — here's what I found.",
    "takeover": "You can take it over at any point.",                                                   # R11 · on EVERY answer
    "stopped": "I stopped {what} ({why}). Nothing else was cancelled — you can take it over at any point.",   # R12
    # booking-rules/2 · the ONE question is the read-back (R2/R4); its answer is the approval
    "ask_page_or_call": "{head} — fill in their page now, or shall I call them?",
    "ask_call_when_open": "I'll call them when they open at {opens_at} — OK?",
    "ask_call_now": "{head} — shall I call them now?",
    "on_it": "On it — {next}.",
    "no_answer": "They didn't pick up again — the form is the fastest way.",                                   # booking-rules/2.1 · the 2nd
    "no_answer_no_page": "They didn't pick up again — here's their {how} so you can reach them yourself.",
    "no_answer_first": "They didn't pick up.",                                                                   # booking-rules/2.1 · the 1st
    "ask_try_again": "Try once more, or fill in their form so you just tap confirm?",                            # … then the ONE question
    "ask_try_again_no_page": "Shall I try them once more?",
    "call_not_asked": "No call is open for this booking — I only call again when you ask.",                    # a call nobody asked for
}

# ── calls (R7–R9): the fixed preamble and rules, as data ──────────────────────────────────────────────────────────────
CALL_DISCLOSURE = "Hello, this is Sasha, an AI concierge from Kanoe Technologies SL"   # R7 · every opening starts with this, exactly
CALL_RULES = ("Say you are an AI from Kanoe Technologies at the start; if asked, you are an AI — never the guest, never a human.",
              "Agree to no deposit, no fee and no different time, and give no card. If they ask for a deposit, a fee or another time, "
              "thank them and end the call — never ask the amount.",                                                         # R8 (Tyler)
              "No voicemail: if a machine answers, hang up and leave nothing.")                                             # R9
CALL_PAYLOAD = {"voicemail": {"action": "hangup"}, "record": False, "max_minutes": MAX_CALL_MINUTES}                    # R9
_MONEY_OR_TIME = ("deposit", "depósito", "fianza", "señal", "prepay", "pago por adelantado", "card", "tarjeta", "fee", "cargo", "suplemento",
                  "another time", "different time", "otra hora", "a las", "only at", "solo a las", "would", "could you do")
_RUNG = {"fill_form_zero_touch": "zero_touch", "prepared_link": "human_tap", "ask_one_question": "human_tap", "ask_call": "phone", "hand_over_platform_link": "human_tap",
         "request_whatsapp": "request_reply", "request_email": "request_reply", "wait": "request_reply", "call": "phone", "call_and_email": "phone",
         "refuse": None}


def _ts(v: Optional[str]) -> Optional[datetime]:
    """ISO → naive UTC (a time without a zone is taken as UTC)."""
    if not v:
        return None
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def is_platform(host_or_url: Optional[str]) -> Optional[str]:
    h = (host_or_url or "").lower()
    return next((p for p in PLATFORM_HOSTS if p in h), None)


def call_opening(rest: str) -> str:
    """R7 · every call script starts with the AI disclosure sentence, exactly."""
    return f"{CALL_DISCLOSURE}, {rest}"


def call_answer(said: str) -> Dict[str, Any]:
    """R8 · the venue asks a deposit, a fee or another time → the call ends; the outcome is unclear; no amount is ever agreed."""
    s = (said or "").lower()
    if any(w in s for w in _MONEY_OR_TIME):
        return {"end_call": True, "outcome": "unclear", "amount_agreed": None, "reason": "a deposit, a fee or another time was asked — refused, never discussed"}
    return {"end_call": False, "outcome": None, "amount_agreed": None}


def head(ctx: Dict[str, Any]) -> str:
    """The read-back's first words: "<party> at <venue>, <day> <time>" (booking-rules/2) — the caller's words first, else derived."""
    b, venue, when = ctx.get("booking") or {}, ctx.get("venue") or {}, ctx.get("when") or {}
    at = _ts(when.get("booking_at"))
    party = b.get("party")
    if isinstance(party, int) or (isinstance(party, str) and party.isdigit()):
        party = f"{int(party)} {'person' if int(party) == 1 else 'people'}"
    day = b.get("day") or (at.strftime("%a %d %b") if at else "")
    time_ = b.get("time") or (at.strftime("%H:%M") if at else "")
    who = " at ".join(x for x in (party, b.get("venue") or venue.get("name")) if x) or "This booking"
    when_ = " ".join(x for x in (day, time_) if x)
    return f"{who}, {when_}" if when_ else who


def call_when(ctx: Dict[str, Any]) -> str:
    """When the call can be made: "when they open at 13:00", or "now"."""
    v = ctx.get("venue") or {}
    return f"when they open at {v['opens_at']}" if v.get("opens_at") and not v.get("open_now") else "now"


def on_it(next_step: str) -> str:
    """booking-rules/2 · after the person's answer: ONE short line, then it's done ("On it — I'll call them at 13:00 and let you know.")."""
    return PHRASES["on_it"].format(next=next_step.rstrip("."))


def call_allowed(access: dict, state: dict, now_iso: Optional[str]) -> Dict[str, Any]:
    """R10 · may a call be made now? (the act enforces it: venue.call_attempt) → {allowed, reason}."""
    ok, why = _call_allowed(access, state, _ts(now_iso))
    return {"allowed": ok, "reason": why}


def no_answer(page_link: Optional[str], phone: Optional[str] = None, email: Optional[str] = None, n: int = 2) -> Dict[str, Any]:
    """booking-rules/2.1 · a call went unanswered (n = the unanswered calls for this booking so far): said, never silent.
    n == 1 → "They didn't pick up." + the ONE question (try once more, or their form); n >= 2 → the form is the fastest way (their page
    prefilled, else their number or email) and no third call unless the person asks."""
    if int(n or 0) <= 1:
        return _decision("ask_one_question", "no_answer_first", None, page_link, ask="ask_try_again" if page_link else "ask_try_again_no_page",
                         ask_once=["try_again_or_page" if page_link else "try_again"], follow_ups=[{"action": "tell_person", "reason": "no one picked up"}])
    if page_link:
        return _decision("prepared_link", "no_answer", None, page_link, follow_ups=[{"action": "tell_person", "reason": "no one picked up"}])
    how = "number" if phone else "email" if email else "details"
    return _decision("prepared_link", "no_answer_no_page", {"kind": "phone", "value": phone} if phone else {"kind": "email", "value": email} if email else None,
                     None, fmt={"how": how}, follow_ups=[{"action": "tell_person", "reason": "no one picked up"}])


def stopped(what: str, why: str, prepared_link: Optional[str] = None) -> Dict[str, Any]:
    """R12 · an automatic stop or cancel ALWAYS becomes a message to the person (never only a log line)."""
    return _decision("refuse", "stopped", None, prepared_link, fmt={"what": what, "why": why},
                     follow_ups=[{"action": "tell_person", "reason": f"{what} stopped: {why}"}], refusals=[{"rule": "R12", "reason": why}])


def _decision(action: str, say: str, channel: Optional[dict], link: Optional[str], *, fmt: Optional[dict] = None, ask_once: Optional[list] = None,
              follow_ups: Optional[list] = None, refusals: Optional[list] = None, ask: Optional[str] = None) -> Dict[str, Any]:
    text = PHRASES[say].format(**(fmt or {}))
    return {"action": action, "say": say, "say_text": text, **({"ask": ask, "ask_text": PHRASES[ask]} if ask else {}),
            "ask_once": ask_once or [], "channel_used": (channel or {}).get("kind"),
            "channel": channel, "rung": _RUNG.get(action), "billable_on_confirm": action not in ("refuse", "wait"),
            "price_class": _RUNG.get(action),
            "takeover": {"link": link, "say": PHRASES["takeover"]},          # R11 · ALWAYS present
            "follow_ups": follow_ups or [], "refusals": refusals or [], "rules_version": VERSION}


def decide(ctx: Dict[str, Any]) -> Dict[str, Any]:
    venue, when, person, state = ctx.get("venue") or {}, ctx.get("when") or {}, ctx.get("person") or {}, ctx.get("state") or {}
    hd = head(ctx)
    access = person.get("access") or {"mode": "test", "calls": "off", "real_venue_sends": "off"}   # no record → fail closed
    pref = (person.get("preference") or "none").lower()
    link = state.get("prepared_link")
    hotel = (venue.get("type") or "") == "hotel"
    now, at = _ts(when.get("now")), _ts(when.get("booking_at"))
    hours = (at - now).total_seconds() / 3600 if (now and at) else None
    chans = list(venue.get("channels") or [])

    # R14 · a platform: read and hand over its link, never press Book
    for c in chans:
        p = c.get("kind") == "platform" and (is_platform(c.get("host") or c.get("value")) or c.get("host") or "a booking platform") or \
            (c.get("kind") in ("form", "own_engine", "widget") and is_platform(c.get("host") or c.get("value")))
        own_first = any(x.get("kind") in ("form", "whatsapp", "email") and not is_platform(x.get("host") or x.get("value")) for x in chans)
        if p and not own_first:   # R1 · their own form / WhatsApp / email come first; a platform is never submitted to
            return _decision("hand_over_platform_link", "platform", c, link or c.get("value"), fmt={"platform": p},
                             refusals=[{"rule": "R14", "reason": f"{p} is a booking platform — never booked for anyone"}])

    own = {k: next((c for c in chans if c.get("kind") == k and not is_platform(c.get("host") or c.get("value"))), None) for k in CHANNEL_ORDER}
    real = not venue.get("test")
    # access gates (§B): a real venue is contacted only for a LIVE person with real-venue sends ON
    if real and access.get("mode") != "live":
        return _decision("prepared_link", "not_live", own["form"] or next((c for c in chans), None), link, refusals=[{"rule": "access", "reason": "test mode"}])
    sends_ok = (not real) or access.get("real_venue_sends") == "on"

    form = own["form"]
    if form:
        # R13 · CAPTCHA or a required consent box is the person's: never zero-touch
        if form.get("captcha") or form.get("required_consent"):
            return _decision("prepared_link", "prepared_link_captcha" if form.get("captcha") else "prepared_link", form, link,
                             refusals=[{"rule": "R13", "reason": "a CAPTCHA or a required consent box — only the person can"}])
        if pref in ("link", "myself"):
            return _decision("prepared_link", "prepared_link", form, link)
        if not sends_ok:
            return _decision("prepared_link", "no_real_sends", form, link, refusals=[{"rule": "access", "reason": "real-venue sends are off"}])
        phone_ = own["phone"]
        urgent = hours is not None and hours <= (HOTEL_ARRIVAL_CALL_HOURS if hotel else URGENT_HOURS)
        call_ok_, _ = _call_allowed(access, state, now) if phone_ else (False, None)
        if pref == "call" and phone_ and call_ok_:   # booking-rules/2 · they answered "call": the call, said in one line
            return _decision("call", "on_it", phone_, link, fmt={"next": f"I'll call them {call_when(ctx)} and let you know"})
        if pref == "handle":
            return _decision("fill_form_zero_touch", "sent", form, link)
        if phone_ and call_ok_ and urgent:   # booking-rules/2 · soon, a page and a phone: the ONE question is the read-back
            return _decision("ask_one_question", "ask_page_or_call", form, link, fmt={"head": hd}, ask_once=["their_page_or_call"])
        return _decision("ask_one_question", "ask_book", form, link, ask_once=["prefilled_form_or_handle_it"])   # R2 · the ONE question

    msg = own["whatsapp"] or own["email"]
    phone = own["phone"]
    if not (msg or phone):
        return _decision("prepared_link", "no_channel", None, link)
    if not sends_ok:
        return _decision("prepared_link", "no_real_sends", msg or phone, link, refusals=[{"rule": "access", "reason": "real-venue sends are off"}])

    call_ok, why_not = _call_allowed(access, state, now)
    threshold = HOTEL_ARRIVAL_CALL_HOURS if hotel else URGENT_HOURS
    # R5 · a hotel that hasn't answered our request in 24 h → a call (when calls are allowed)
    sent_at = _ts(state.get("request_sent_at"))
    if hotel and sent_at and now and not state.get("venue_replied") and (now - sent_at).total_seconds() >= HOTEL_NO_REPLY_HOURS * 3600 and phone:
        if call_ok:
            return _decision("call", "calling", phone, link)
        return _decision("prepared_link", why_not or "calls_cap", phone, link, refusals=[{"rule": "R10", "reason": why_not or "calls off"}])

    far = hours is None or hours > threshold
    if far:   # R3 · no form and more than 48 h away (a hotel: 24 h) → a request, and wait — never a call
        if msg:
            hotel_follow = [{"after_hours": HOTEL_NO_REPLY_HOURS, "action": "call", "reason": "no reply in 24 h (hotel)", "only_when": "venue open or 10:00–20:00"}] if hotel else []
            return _decision("request_whatsapp" if msg is own["whatsapp"] else "request_email", "request_wait", msg, link,
                             follow_ups=hotel_follow + [{"action": "tell_person", "reason": "when they reply"}])
        return _decision("wait", "wait_to_call", phone, link, follow_ups=[{"before_hours": threshold, "action": "call", "reason": "within the threshold"}])
    # R4 / R6 · within the threshold → a call (a hotel within 24 h: call and email), or their own page
    if phone and call_ok:
        if hotel and own["email"]:
            return _decision("call_and_email", "call_and_email", phone, link)
        if pref == "call":   # booking-rules/2 · they said OK: the call, said in one line
            return _decision("call", "on_it", phone, link, fmt={"next": f"I'll call them {call_when(ctx)} and let you know"})
        cw = call_when(ctx)   # booking-rules/2 · the call is asked as the ONE question (the read-back); their OK is the approval
        return _decision("ask_call", "ask_call_now" if cw == "now" else "ask_call_when_open", phone, link,
                         fmt={"head": hd, "opens_at": venue.get("opens_at") or ""}, ask_once=["call_ok"])
    if phone and not call_ok:
        return _decision("prepared_link", why_not, phone, link, refusals=[{"rule": "R10", "reason": why_not}])
    return _decision("request_whatsapp" if msg is own["whatsapp"] else "request_email", "request_wait", msg, link,
                     follow_ups=[{"action": "tell_person", "reason": "when they reply"}])


def _call_allowed(access: dict, state: dict, now: Optional[datetime]) -> tuple:
    """R10 · calls: this person's switch, at most 3 a day per person, the server net, and 30 minutes between calls to the same venue."""
    if access.get("calls") != "on":
        return False, "no_real_sends"
    if int(state.get("calls_today_person") or 0) >= CALLS_PER_PERSON_PER_DAY:
        return False, "calls_cap"
    if state.get("server_cap") is not None and int(state.get("server_calls_today") or 0) >= int(state["server_cap"]):
        return False, "calls_cap"
    last = _ts(state.get("last_call_to_venue_at"))
    if last and now and now - last < timedelta(minutes=MIN_MINUTES_BETWEEN_CALLS_SAME_VENUE):
        return False, "too_soon"
    return True, None


__all__ = ["decide", "stopped", "call_opening", "call_answer", "is_platform", "head", "call_when", "on_it", "call_allowed", "no_answer", "PHRASES", "PLATFORM_HOSTS", "CALL_PAYLOAD", "CALL_RULES",
           "CALL_DISCLOSURE", "VERSION", "URGENT_HOURS", "HOTEL_ARRIVAL_CALL_HOURS", "HOTEL_NO_REPLY_HOURS", "CALLS_PER_PERSON_PER_DAY",
           "MIN_MINUTES_BETWEEN_CALLS_SAME_VENUE", "MAX_CALL_MINUTES", "CHANNEL_ORDER"]
