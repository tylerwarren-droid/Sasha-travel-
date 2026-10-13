"""Sasha 254 · item 2 — ONE DECIDER. Every venue booking chooser (/s2, WhatsApp's brain, /next — and old S1, the old WhatsApp flow,
the web card's words, the no-reply sweep) asks the vendored booking rules (agapi/booking_rules: decide(ctx) → Decision) and nothing
else. This module is only the ADAPTER: Sasha's records → the rules' ctx, and the Decision → what she says. It decides nothing.

  ctx_for(...)          the rules' ctx: venue {type, test, channels}, when {booking_at, now} in UTC, person {access, preference}, state
  channels_of(eng, rd)  THE ONE CHANNEL READER, in the rules' kinds (form / own_engine / widget / whatsapp / email / phone / platform)
  access_of(account)    the person's access {mode, calls, real_venue_sends} — ONE function: the record (agapi.person_access, CR's access.get)
  state_of(...)         calls_today_person / server_calls_today + server_cap / last_call_to_venue_at, from the call store
  decide_for(...)       the above, then booking_rules.decide — the Decision, untouched
  say(decision)         decide()'s say_text + the take-over line (R11: on EVERY answer)
  tell_stopped(...)     R12 · an automatic stop → booking_rules.stopped() → the person is told (WhatsApp if linked; get_status says it)
  legacy_decision / legacy_ladder   the old flow's and the web card's shapes, from the SAME Decision (their words are its phrases)

Retired by this (Sasha 254): booking_signer/decide.py's decide / ladder / line / urgent_hours / reply_hours / tap_window_min /
available / urgent / _then; venues._hold_inner's own route order and the /s2 WhatsApp-first decider; GW.ladder_of / decision_of as
deciders (they call legacy_* here); proactive's own timing (D.reply_hours, D.urgent_hours, D.tap_window_min; tap_offers);
call_routes.cap()'s SASHA_CALLS_PER_DAY and account_cap()'s SASHA_CALLS_PER_ACCOUNT_PER_DAY (the rules' 3/person + the net below).
"""
from __future__ import annotations

import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agapi.booking_rules import booking_rules as BR

log = logging.getLogger("agapi.booking_decide")

#: the server-wide net under the rules' per-person cap (BR: "the server cap stays as a net") — the ONE place it is written.
#: It was SASHA_CALLS_PER_DAY (default 3); no env var is read for it any more.
SERVER_CALLS_PER_DAY = 3

TEST_VENUE_MARKS = ("(TEST stand-in)", "Sasha Test Venue")

# the hold's route word (the tool's enum, unchanged: the S1 fingerprint) → the rules' preference
PREFERENCE = {"page": "link", "link": "link", "myself": "myself", "form": "handle", "handle": "handle",
              "email": "email", "call": "call", "whatsapp": "whatsapp"}

# the ONE question's two answers (R2: PHRASES["ask_book"]) as hold routes: a prefilled form (their page) / she handles it (the form)
CHOICES = ({"title": "Prefilled form", "route": "page"}, {"title": "Handle it", "route": "form"})


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


def _host(v: Optional[str]) -> Optional[str]:
    from agapi import venue_truth as VT
    return VT._host(v) if v and ("." in str(v) or "://" in str(v)) else None


def _one(kind: str, value: Optional[str], url: Optional[str] = None, captcha: bool = False) -> dict:
    """A channel in the rules' shape. A booking platform is passed ANONYMOUSLY (kind platform, no host): the rules never book on it
    (R14) and her voice never names it (voice.CHANNEL_NAMES) — the platform's own page stays in `url`, the take-over link."""
    target = url or value
    if kind in ("form", "own_engine", "widget", "platform") and (kind == "platform" or BR.is_platform(target) or BR.is_platform(_host(target))):
        return {"kind": "platform", "url": target if str(target or "").startswith("http") else None}
    if kind in ("own_engine", "widget"):
        # their OWN booking engine / widget is their own form to the rules (R1: "form" first; decide reads own channels by kind)
        c = {"kind": "form", "engine": kind, "value": value or url}
        if url:
            c["url"] = url
        if captcha:
            c["captcha"] = True
        return c
    c = {"kind": kind, "value": value or url}
    if url:
        c["url"] = url
    if captcha:
        c["captcha"] = True
    return c


def channels_of(eng: Optional[dict], rd: Optional[dict] = None, card: Optional[dict] = None) -> List[dict]:
    """THE ONE CHANNEL READER (the rules' venue.channels). The venue engine's read of their own site when it has one (its channel,
    its request alternative, and every other way it read — engine_channel attaches them as `all`); else Sasha's own read
    (venue_read's rungs). A phone from Sasha's read is added only when the engine found none (R4 needs it within 48 h)."""
    rd = rd or {}
    rungs = rd.get("rungs") or {}
    captcha = any(f.get("kind") == "challenge" for f in rd.get("facts") or [])
    out: List[dict] = []
    if eng and eng.get("from") != "read":
        seen = [eng] + ([eng["alternative"]] if eng.get("alternative") else []) + list(eng.get("all") or [])
        for k in seen:
            kind = k.get("kind")
            if kind in ("form", "own_engine", "widget", "whatsapp", "email", "phone", "platform"):
                out.append(_one(kind, k.get("value") or k.get("name"), k.get("url") or (card or {}).get("website") if kind in ("form", "own_engine", "widget") else k.get("url"),
                                captcha=bool(k.get("captcha") or (kind in ("form", "own_engine", "widget") and captcha))))
        if not any(c["kind"] == "phone" for c in out) and "phone" in rungs:
            out.append({"kind": "phone", "value": str((rungs["phone"] or {}).get("value") or "read")})
    else:
        for rung, kind in (("form", "form"), ("own_page", "own_engine"), ("link", "widget"), ("whatsapp", "whatsapp"),
                           ("email", "email"), ("phone", "phone")):
            if rung not in rungs:
                continue
            v = str((rungs[rung] or {}).get("value") or "")
            if rung == "link" and not v.startswith("http"):
                # the link rung's value is a platform's NAME ("TheFork", "CoverManager"): a booking platform, never submitted to
                out.append({"kind": "platform", "url": None})
                continue
            url = v if v.startswith("http") else ((card or {}).get("website") if kind in ("form", "own_engine") else None)
            out.append(_one(kind, v or None, url, captcha=captcha and kind in ("form", "own_engine", "widget")))
    # one of each kind, in the order read (the rules' R1 order is the rules' own)
    seen_k: set = set()
    uniq = []
    for c in out:
        key = (c["kind"], c.get("url") or c.get("value"))
        if key not in seen_k:
            seen_k.add(key)
            uniq.append(c)
    return uniq


def page_of(channels: List[dict], card: Optional[dict] = None) -> Optional[str]:
    """The prepared / take-over link: their own booking page (or the platform's), else their site."""
    for k in ("form", "platform"):
        c = next((c for c in channels if c["kind"] == k and str(c.get("url") or "").startswith("http")), None)
        if c:
            return c["url"]
    w = (card or {}).get("website")
    return w if str(w or "").startswith("http") else None


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


# ── the person ───────────────────────────────────────────────────────────────────────────────────────────────────────────────

#: no person named (an old-flow read with no account): the family's route, as agapi_route.person_mode(None) says — and no powers
NOBODY = {"mode": "live", "calls": "off", "real_venue_sends": "off"}


def _access(rec: dict) -> Dict[str, str]:
    """The rules' person.access — the record's mode, calls and real-venue sends, nothing added."""
    return {"mode": "live" if rec.get("mode") == "live" else "test", "calls": "on" if rec.get("calls") == "on" else "off",
            "real_venue_sends": "on" if rec.get("real_venue_sends") == "on" else "off"}


async def access_of(account: Optional[str]) -> Dict[str, str]:
    """THE person's access, for the rules (§B) — ONE function. Sasha 254 item 5: AgAPI's person_access record, through access.get
    (agapi.person_access.get; cached ≤ 60 s; a failed read, or no row, is closed: test, everything off)."""
    from agapi import person_access as PA
    return _access(await PA.get(account)) if account else dict(NOBODY)


def access_cached(account: Optional[str]) -> Dict[str, str]:
    """access_of for the SYNC legacy callers (the old flow's and the web card's words): the same record, as last read (≤ 60 s;
    warmed where the account is resolved) — closed when unread."""
    from agapi import person_access as PA
    return _access(PA.cached(account)) if account else dict(NOBODY)


# ── state ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def state_of(account: Optional[str], venue_key: Optional[str] = None, number: Optional[str] = None,
                   now: Optional[datetime] = None) -> Dict[str, Any]:
    """The rules' state from the call store: this person's calls in 24 h, the server's (and its net), the last call to THIS venue."""
    from booking_signer import call_routes as CR
    now = now or datetime.now(timezone.utc)
    st: Dict[str, Any] = {"calls_today_person": 0, "server_calls_today": 0, "server_cap": SERVER_CALLS_PER_DAY, "last_call_to_venue_at": None}
    store = CR.CALL_STORE
    if store is None or not account or not hasattr(store, "call_counts"):
        return st
    try:
        c = await store.call_counts(str(account), venue_key, number, now - timedelta(hours=24))
    except Exception as e:   # unreadable: the server's own claim still refuses a call over the caps
        log.warning("[booking_decide] call counts not read: %s", type(e).__name__)
        return st
    st.update(calls_today_person=int(c.get("person") or 0), server_calls_today=int(c.get("server") or 0),
              last_call_to_venue_at=_iso(c.get("last_to_venue")))
    return st


def ctx_for(*, channels: List[dict], vtype: str, test: bool, booking_at_utc: Optional[str], now: Optional[datetime] = None,
            access: Optional[dict] = None, preference: Optional[str] = None, state: Optional[dict] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    return {"venue": {"type": vtype, "test": bool(test), "channels": channels},
            "when": {"booking_at": booking_at_utc, "now": _iso(now)},
            "person": {"access": access or {"mode": "test", "calls": "off", "real_venue_sends": "off"},
                       "preference": PREFERENCE.get(str(preference or ""), "none")},
            "state": dict(state or {})}


async def decide_for(account: Optional[str], *, channels: List[dict], vtype: str, test: bool, local_at: Optional[str],
                     country: Optional[str], preference: Optional[str] = None, venue_key: Optional[str] = None,
                     number: Optional[str] = None, link: Optional[str] = None, now: Optional[datetime] = None,
                     extra_state: Optional[dict] = None) -> Dict[str, Any]:
    """The Decision for one booking — booking_rules.decide, nothing added. The ctx goes with it (`ctx`), for the record."""
    now = now or datetime.now(timezone.utc)
    st = await state_of(account, venue_key, number, now)
    st.update(prepared_link=link, **(extra_state or {}))
    ctx = ctx_for(channels=channels, vtype=vtype, test=test, booking_at_utc=utc_of(local_at, country), now=now,
                  access=await access_of(account), preference=preference, state=st)
    d = BR.decide(ctx)
    log.info("[booking_decide] %s → %s (%s)", vtype, d["action"], d["say"])
    return {**d, "ctx": ctx}


def redecide(d: Dict[str, Any], preference: str) -> Dict[str, Any]:
    """The same booking asked again with another preference (the hold's route word) — still booking_rules.decide, the same ctx."""
    ctx = {**d["ctx"], "person": {**d["ctx"]["person"], "preference": PREFERENCE.get(preference, "none")}}
    return {**BR.decide(ctx), "ctx": ctx, "channels": d.get("channels")}


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


# ── the legacy shapes (the old WhatsApp flow / voice avatar, and the web card's words), from the SAME Decision ─────────────────

class LegacyDecision:
    """The old flow's dv: .route ∈ form | one_tap | email | call | call_email | None, .reason (said), .then (None: the rules' own
    follow-ups replace the old escalation plans), .alternatives ([]: the rules decide one way)."""

    def __init__(self, route: Optional[str], reason: str, decision: Dict[str, Any]):
        self.route, self.reason, self.then, self.alternatives, self.decision = route, reason, None, [], decision


_ROUTE = {"fill_form_zero_touch": "form", "ask_one_question": "form", "hand_over_platform_link": "one_tap",
          "request_email": "email", "call": "call", "call_and_email": "call_email"}


def _legacy_rd(rd: dict, at: Optional[str], prefer: Optional[str], account: Optional[str], now) -> Dict[str, Any]:
    chans = channels_of(None, rd)
    nights = None
    return BR.decide(ctx_for(channels=chans, vtype=venue_type((rd.get("what") or {}).get("category") if isinstance(rd.get("what"), dict) else rd.get("type"), nights),
                             test=is_test_venue(rd), booking_at_utc=utc_of(at, rd.get("country")), now=now,
                             access=access_cached(account), preference={"one_tap": "page", "call_email": "call"}.get(prefer or "", prefer),
                             state={"server_cap": SERVER_CALLS_PER_DAY, "prepared_link": page_of(chans)}))


def legacy_decision(rd: dict, prefer: Optional[str] = None, at: Optional[str] = None, now=None, account: Optional[str] = None) -> LegacyDecision:
    d = _legacy_rd(rd, at, prefer, account, now or datetime.now(timezone.utc))
    route = _ROUTE.get(d["action"])
    if d["action"] == "prepared_link" and d["say"] in ("prepared_link", "prepared_link_captcha") and \
            {"link", "own_page", "form"} & set((rd.get("rungs") or {})):
        route = "one_tap"   # their page, prefilled where it can be — the person confirms it there
    return LegacyDecision(route, say(d), d)


def legacy_ladder(rd: dict, reservation: dict, now, account: Optional[str] = None) -> Optional[dict]:
    """The old flow's / web card's {line, options}: the rules' one question (R2) with its two answers, else the one way it decided."""
    d = _legacy_rd(rd, (reservation.get("when") or {}).get("at"), None, account, now or datetime.now(timezone.utc))
    if d["action"] == "ask_one_question":
        return {"line": d["say_text"], "options": [(o["title"], o["route"]) for o in CHOICES]}
    return None


__all__ = ["decide_for", "ctx_for", "channels_of", "access_of", "access_cached", "state_of", "say", "out_of", "tell_stopped", "stops_of",
           "venue_type", "is_test_venue", "utc_of", "page_of", "legacy_decision", "legacy_ladder", "SERVER_CALLS_PER_DAY", "CHOICES",
           "PREFERENCE", "CALL_STOPS"]
