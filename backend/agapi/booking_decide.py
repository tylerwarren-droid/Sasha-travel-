"""Sasha 254 · Sasha 378 (CR 188's Sasha half) · WORDS AND CONSTANTS ONLY. The booking decision is AgAPI's — venue.profile's
`decision` (handoff.decide), then venue.prepare_booking for this person — and Sasha follows it (agapi.venues.one_decision). Nothing here
chooses a channel, reads a person's switch (preference, real_venue_sends, platform_submit) or calls booking_rules.decide.

  say(decision) / out_of(decision)   AgAPI's say_text + the take-over line (R11), as it goes into a tool result
  booking_words(...)                 the read-back's day and time in the venue's own clock
  tell_stopped(...) / stops_of(...)  R12 · an automatic stop → the person is told (WhatsApp if linked; get_status says it)
  is_test_venue(...)                 Kanoe's own TEST venue (its marks)
  SERVER_CALLS_PER_DAY  the server's call net

Deleted by Sasha 378: decide_for / redecide / ctx_for / channels_of / page_of / access_of / access_cached / state_of / PREFERENCE /
CHOICES / CALL_CHOICES / legacy_decision / legacy_ladder / as_v1 — Sasha's own decider over its own channel read.
"""
from __future__ import annotations

import logging
import time as _time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agapi.booking_rules import booking_rules as BR

log = logging.getLogger("agapi.booking_decide")

#: the server-wide net under the rules' per-person cap (BR: "the server cap stays as a net") — the ONE place it is written.
#: It was SASHA_CALLS_PER_DAY (default 3); no env var is read for it any more.
SERVER_CALLS_PER_DAY = 3

TEST_VENUE_MARKS = ("(TEST stand-in)", "Sasha Test Venue")



# ── the venue ────────────────────────────────────────────────────────────────────────────────────────────────────────────────

_TYPES = (("hotel", ("hotel", "hostel", "stay", "lodging", "room", "apartment", "guesthouse", "b&b", "resort")),
          ("spa", ("spa", "massage", "hammam", "wellness", "beauty", "nail", "facial", "sauna")),
          ("restaurant", ("restaurant", "table", "dinner", "lunch", "brunch", "bar", "cafe", "café", "bistro", "tapas")),
          ("activity", ("activity", "tour", "class", "lesson", "experience", "museum", "ticket", "excursion")),
          ("service", ("service", "tattoo", "hair", "barber", "salon", "clinic", "repair", "consultation")))


def venue_type(category: Optional[str], nights: Optional[int] = None) -> str:
    """The rules' venue.type: a stay (nights) is a hotel; else the reservation's category in plain words."""
    if nights:
        return "hotel"
    c = str(category or "").lower()
    return next((t for t, words in _TYPES if any(w in c for w in words)), "other")


def is_test_venue(rd: Optional[dict], card: Optional[dict] = None) -> bool:
    name = str((rd or {}).get("venue") or "") + " " + str((card or {}).get("name") or "")
    return any(m in name for m in TEST_VENUE_MARKS) or bool((card or {}).get("test"))


# ── when ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def utc_of(local_at: Optional[str], country: Optional[str]) -> Optional[str]:
    """The venue's LOCAL booking time ('2026-10-20T21:00', no zone) → UTC ISO, in the venue's own zone (venue_read.COUNTRIES)."""
    if not local_at:
        return None
    try:
        from zoneinfo import ZoneInfo
        from booking_signer import venue_read as V
        tz = (V.COUNTRIES.get(str(country or "").upper()) or (None, None, None, "Europe/Madrid"))[3]
        d = datetime.fromisoformat(str(local_at)[:16])
        if d.tzinfo is None:
            d = d.replace(tzinfo=ZoneInfo(tz))
        return d.astimezone(timezone.utc).isoformat()
    except Exception as e:
        log.info("[booking_decide] no booking time: %s", type(e).__name__)
        return None


def _iso(d: Optional[datetime]) -> Optional[str]:
    if d is None:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def booking_words(venue: Optional[str], party: Any, local_at: Optional[str], country: Optional[str],
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """booking-rules/2's ctx.booking: the venue, the party, the day in plain local words ("today", "tomorrow", "Thu 15 Oct") and the
    time ("21:00") — the venue's own clock, never UTC."""
    day = time_ = None
    try:
        from zoneinfo import ZoneInfo
        from booking_signer import venue_read as V
        tz = ZoneInfo((V.COUNTRIES.get(str(country or "").upper()) or (None, None, None, "Europe/Madrid"))[3])
        at = datetime.fromisoformat(str(local_at)[:16])
        today = (now or datetime.now(timezone.utc)).astimezone(tz).date()
        gap = (at.date() - today).days
        day = "today" if gap == 0 else "tomorrow" if gap == 1 else at.strftime("%a %d %b")
        time_ = at.strftime("%H:%M")
    except Exception:
        pass
    try:
        party = int(party) if party is not None else None
    except (TypeError, ValueError):
        party = None
    return {"venue": venue, "party": party, "day": day, "time": time_}


def say(d: Dict[str, Any]) -> str:
    """What she says: decide()'s say_text, and the take-over (R11) — once (a phrase that already offers it isn't repeated)."""
    text = str(d.get("say_text") or "")
    tk = (d.get("takeover") or {}).get("say") or BR.PHRASES["takeover"]
    return text if "take it over" in text.lower() else f"{text} {tk}".strip()


def out_of(d: Dict[str, Any]) -> Dict[str, Any]:
    """The rules' answer, as it goes into a tool result (the model and the screen read it): action, say, the take-over, follow-ups."""
    return {"action": d["action"], "say_key": d["say"], "say": say(d), "takeover": d["takeover"], "rung": d.get("rung"),
            "follow_ups": d.get("follow_ups") or [], "refusals": d.get("refusals") or [], "rules_version": d.get("rules_version")}


# ── R12 · an automatic stop always reaches the person ────────────────────────────────────────────────────────────────────────

_STOPPED: Dict[str, List[dict]] = {}   # account → the stops told (the last day's): get_status lists them
STOP_KEEP_S = 24 * 3600


#: the call route's refusals that are an automatic stop (R10 / access), and how the person is told why
CALL_STOPS = {"daily_call_limit": "today's calls are made", "account_daily_call_limit": "today's calls for you are made",
              "too_soon": "I called them less than 30 minutes ago", "calls_off_for_account": "calls are off for your account",
              "calls_disabled": "calls are off just now"}


async def tell_stopped(account: Optional[str], what: str, why: str, link: Optional[str] = None, push: bool = True) -> Dict[str, Any]:
    """booking_rules.stopped() → the person is TOLD: on their WhatsApp when it is linked (push; in a live turn the turn's own answer
    says it — push=False), and in get_status (s2_status) either way."""
    d = BR.stopped(what, why, link)
    if not account:
        return d
    now = _time.time()
    keep = [s for s in _STOPPED.get(account, []) if now - s["at"] < STOP_KEEP_S]
    keep.append({"at": now, "say": say(d), "what": what, "why": why, **({"link": link} if link else {})})
    _STOPPED[account] = keep[-10:]
    if not push:
        return {**d, "told": "in the turn"}
    told = "not linked"
    try:
        from booking_signer import guest_whatsapp as GW
        ch = await GW.STORE.channel_of_account(account) if GW.STORE is not None else None
        if ch:
            told = await GW._tell(ch, say(d) + (f"\n{link}" if link else ""))
    except Exception as e:
        told = f"not told: {type(e).__name__}"
        log.warning("[booking_decide] a stop was not sent to WhatsApp (%s); get_status still says it", type(e).__name__)
    log.info("[booking_decide] stopped %s (%s) — WhatsApp: %s", what, why, told)
    return {**d, "told": told}


def stops_of(account: Optional[str]) -> List[str]:
    now = _time.time()
    return [s["say"] for s in _STOPPED.get(account or "", []) if now - s["at"] < STOP_KEEP_S]


__all__ = ["say", "out_of", "tell_stopped", "stops_of", "venue_type", "is_test_venue", "utc_of", "SERVER_CALLS_PER_DAY", "CALL_STOPS",
           "booking_words"]
