"""Sasha 211 Part B · REAL VENUE BOOKINGS ON THE AGENT — the EXISTING ladder (booking_signer: /venues/read, /forms, /links,
/emails, /calls, cancel), called in-process (guest_whatsapp.api) exactly as the WhatsApp guest flow calls it. No new booking
machinery: these tools only sequence it for the agent, with the same two steps as the trip's checkout.

  read_booking_route   the venue read (its routes), remembered for this account
  hold_venue           the route — the ladder's own question when it has one (> 48 h: "email them, or book it with you now?";
                       within 48 h: their page now, or a call) — then the read-back the yes binds to. Nothing is sent.
  book_venue           only after the person's explicit yes in a LATER turn (as book): by route
                         form      → filled by Sasha (the founder's override: the cloud browser) — any human step (a CAPTCHA,
                                     terms, the final button) goes to the phone as "Tap to finish"
                         page      → the platform's real page to the phone (TheFork, CoverManager, OpenTable…); the person books
                         email     → sent (Requested until the venue replies)
                         call      → placed (the call's reading decides)
                         whatsapp  → the drafted message, for the person to send
  cancel_venue         the same two steps, back the same route (cancel_routes)
Pacioli: every booking is a trip_items row the routes write; it is in the itinerary on its day; Requested → Confirmed only
from proof (the form's confirmation page, the platform's email via Gmail, the venue's reply) — get_status reads them.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

log = logging.getLogger("agapi.venues")

_READS: Dict[str, Dict[str, dict]] = {}   # account → venue key → the read (read_id, rungs, facts…)
_HELD: Dict[str, dict] = {}               # account → the prepared booking (route, id, sha, when it was said)
_CANCEL: Dict[str, dict] = {}             # account → the prepared cancellation
ROUTE_TO_PREFER = {"form": "form", "email": "email", "page": "one_tap", "call": "call"}


def _API():
    from booking_signer import guest_whatsapp as GW
    return GW


def _err(code: str, message: str):
    from agapi.v0 import ToolError
    return ToolError(code, message)


def _key(a: dict) -> str:
    return (a.get("place_id") or f"{a.get('name', '')}|{a.get('city', '')}").strip().lower()


def _what(a: dict) -> str:
    return (a.get("what") or "a table").strip()[:120]


async def _read(ctx, a: dict) -> dict:
    """The venue read through the booking API (it keeps a read_id the routes need), remembered per account."""
    GW = _API()
    s2 = getattr(ctx, "surface", "s1") == "s2"
    k = _key(a) + ("|s2" if s2 else "")
    got = _READS.get(ctx.account, {}).get(k)
    if got:
        return got
    asked = " ".join(x for x in (_what(a), a.get("type") or "") if x)[:200]
    body = {"name": a.get("name"), "city": a.get("city"), "country": a.get("country"), "place_id": a.get("place_id"),
            "website": a.get("website"), "asked_for": asked}
    if s2:   # Sasha 221 · /s2 only: the server applies the S2 demo setting when this account has it (never on /next)
        body["s2_demo"] = True
        if not body.get("place_id"):   # a card named but not passed by id: the card on screen is the pick
            body["place_id"] = (card_of(ctx.account, None, a.get("name")) or {}).get("place_id")
    status, rd = await GW.api(ctx.account, "POST", "/api/booking/venues/read", {k2: v for k2, v in body.items() if v})
    if status != 200:
        raise _err((rd or {}).get("rule") or "read_failed", GW.refusal_words(rd or {}, status))
    venue = (rd.get("listing") or {}).get("name") or a.get("name") or rd.get("venue")
    if "(TEST stand-in)" in str(rd.get("venue") or ""):
        venue = rd["venue"]
    rungs = {r["rung"]: r for r in rd.get("rungs") or [] if r.get("available")}
    out = {"read_id": rd["read_id"], "country": rd.get("country"), "venue": venue, "facts": rd.get("facts") or [], "place_id": a.get("place_id"),
           "rungs": {k2: {"fact_index": r.get("fact_index"), "value": r.get("value")} for k2, r in rungs.items()},
           **GW._hours_of(rd, datetime.now(timezone.utc)), "say": rd.get("say")}
    _READS.setdefault(ctx.account, {})[k] = out
    return out


# ── Sasha 213 · ONE TURN, ONE STATE: the cards on screen are the cards she was given ─────────────────────────────────────
_SHOWN: Dict[str, Dict[str, dict]] = {}   # account → place_id → the card as shown (the pick and the booking show THAT card)


def shown_cards(r: dict, luxe: bool = False) -> List[dict]:
    """The cards the person sees: the server's ranking's default order, its `show` count — what ChatBooking shows.
    Sasha 253 · G14 — luxe ("luxury" asked): €€€ and up first within that order (GW.luxe_first, the old flow's rule)."""
    all_ = [c for c in (r.get("candidates") or []) if c.get("place_id")]
    rk = r.get("ranking") or {}
    order = (rk.get("orders") or {}).get(rk.get("default") or "rated")
    by = {c["place_id"]: c for c in all_}
    if luxe:
        order = _API().luxe_first(list(order or by), by)
    cards = [by[i] for i in order if i in by] if order else all_
    return cards[: int(r.get("show") or 5)]


def area_of(c: dict) -> str:
    parts = [p.strip() for p in str(c.get("address") or "").split(",") if p.strip()]
    return re.sub(r"^\d{4,5}\s*", "", parts[-2]) if len(parts) >= 3 else (parts[0] if parts else "")


def card_for_model(c: dict) -> dict:
    return {"name": c.get("name"), "place_id": c.get("place_id"), "area": area_of(c), "type": c.get("type"),
            # Sasha 248 · where "type" came from — said that way (found live: "Google lists it as Spanish" for the site's own words)
            **({"type_from": {"site": "the venue's own website (quoted)", "map": "the map listing only — not confirmed by the venue"}
                .get(c.get("type_source") or "", "the map listing only — not confirmed by the venue")} if c.get("type") else {}),
            "rating": c.get("rating"), "reviews": c.get("rating_count"),
            # Sasha 217 · OPENING HOURS only — never "a table is free": availability is known only when the venue answers
            **({"opening_hours_then": c["open_at"], "table_availability": "unknown until the venue answers"} if c.get("open_at") else {})}


def remember_cards(account: str, cards: List[dict]) -> None:
    m = _SHOWN.setdefault(account, {})
    for c in cards:
        m[c["place_id"]] = c
    while len(m) > 60:
        m.pop(next(iter(m)))


def _base(name: str) -> str:
    n = re.sub(r"\s*\([^)]*\)\s*", " ", (name or "").lower())
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", re.sub(r"^\s*(?:the|el|la|los|las)\s+", "", n)).strip()


def named_on_screen(account: str, words: Optional[str]) -> Optional[dict]:
    """Sasha 217 · a card on their screen that these words NAME ("The Sasha Test Venue" → the card "Sasha Test Venue (ours …)")."""
    w = _base(words or "")
    if len(w) < 4:
        return None
    for c in reversed(list((_SHOWN.get(account) or {}).values())):
        b = _base(c.get("name") or "")
        if len(b) >= 4 and (b == w or (len(w) >= 6 and (b in w or w in b))):
            return c
    return None


def card_of(account: str, place_id: Optional[str], name: Optional[str] = None) -> Optional[dict]:
    m = _SHOWN.get(account) or {}
    if place_id and place_id in m:
        return m[place_id]
    n = (name or "").strip().lower()
    return next((c for c in reversed(list(m.values())) if n and (c.get("name") or "").strip().lower() == n), None)


def ribbon_line(a: dict, shown: List[dict], r: dict) -> str:
    """The one line over the cards — from the SAME result as the cards and her words."""
    what, where = (a.get("what") or "places").strip(), (a.get("where") or "").strip()
    when = ""
    if a.get("open_at"):
        try:
            from booking_signer import sentences as SN
            when = f" · {SN.day_words(a['open_at'][:10])} {a['open_at'][11:16]}"
        except Exception:
            when = ""
    if not shown:
        return f"No {what} found in {where}{when}" if not r.get("no_match") else f"No {r['no_match']} places found in {where}{when}"
    return f"{len(shown)} for “{what}” in {where}{when}"   # Sasha 248 · the search, quoted — never a claim about every card


async def photos_for(cards: List[dict], budget: float = 1.2) -> None:
    """The top results' photos, fetched now (each venue's own picture, else Google's), cached by the photo layer; a card
    whose photo misses the budget shows without it and gets it lazily."""
    GW = _API()
    try:
        got, _late = await GW._photos_within(cards, budget)
    except Exception as e:
        log.info("[venues] photos: %s", type(e).__name__)
        got = {}
    for c in cards:
        if got.get(c["place_id"]):
            c["photo"] = got[c["place_id"]]


def _routes_of(rd: dict) -> List[str]:
    r = rd.get("rungs") or {}
    # Sasha 246 · rung 2: their OWN booking page is a "page" too — offered before email, a call or a message
    out = [x for x, k in (("form", "form"), ("page", "link"), ("page", "own_page"), ("email", "email"), ("call", "phone"),
                          ("whatsapp", "whatsapp"), ("instagram", "instagram")) if k in r]
    return list(dict.fromkeys(out))


async def read_booking_route(ctx, a: dict) -> dict:
    rd = await _read(ctx, a)
    card = card_of(ctx.account, a.get("place_id"), a.get("name"))   # Sasha 213 · the picked card is what's on screen
    if one_path(ctx):   # Sasha 251 · how it books = the ONE channel hold_venue will use (never a second reading of the same place)
        eng = await engine_channel(card) or read_channel(rd, card)
        return {**({"card": card} if card else {}), "venue": rd["venue"], "routes": _routes_of_channel(eng),
                "how": _how_words(eng), "open_now": rd.get("open_now"), "opens_at": rd.get("opens_at")}
    return {**({"card": card} if card else {}), "venue": rd["venue"], "routes": _routes_of(rd), "how": rd.get("say"),
            "open_now": rd.get("open_now"), "opens_at": rd.get("opens_at")}


def one_path(ctx) -> bool:
    """Sasha 251 · ONE BOOKING PATH on /s2, WhatsApp's brain and /next under S1 parity: every venue booking goes through
    _engine_route. Old S1 (SASHA_S1_PARITY=off) keeps Sasha's own ladder exactly as it was."""
    if getattr(ctx, "surface", "s1") == "s2":
        return True
    from app.agent.sasha import s1_parity
    return s1_parity()


# Sasha's own read (booking_signer/venue_read) → the engine's channel kinds, for a place the venue engine couldn't read (no site,
# robots, a page built in the browser, another branch): the SAME channel shape, so the same question and the same executors decide
READ_KIND = {"form": "form", "own_page": "own_engine", "link": "widget", "whatsapp": "whatsapp", "email": "email", "phone": "phone",
             "instagram": "instagram"}   # their WhatsApp before email (Sasha 232: direct first)
# …and each to its executor: Sasha's form fill sends, so it keeps its read-back and yes; a page with an address is prefilled
READ_ROUTE = {"form": "form", "email": "email", "whatsapp": "whatsapp", "phone": "call", "instagram": "instagram"}


def read_channel(rd: dict, card: Optional[dict] = None) -> Optional[dict]:
    """Sasha 251 · the venue's ONE channel when the engine has none — from what Sasha's read found, in the engine's shape."""
    from agapi import venue_truth as VT
    rungs = rd.get("rungs") or {}
    kinds = []
    for rung, kind in READ_KIND.items():
        if rung in rungs:
            v = str((rungs[rung] or {}).get("value") or "")
            kinds.append({"kind": kind, "value": v, "from": "read", **({"url": v} if v.startswith("http") else {}),
                          **({"name": v} if rung == "link" and not v.startswith("http") else {})})
    ch = VT.channel({"channels": kinds})
    if not ch:
        ch = next(({**k} for k in kinds if k["kind"] in ("instagram", "phone")), None)
    if ch:
        ch["from"] = "read"
        if not ch.get("url") and ch["kind"] in VT.FILLABLE:
            ch["url"] = (card or {}).get("website")
    return ch


def _routes_of_channel(eng: Optional[dict]) -> List[str]:
    if not eng:
        return []
    out = [ENGINE_ROUTE.get(eng["kind"], eng["kind"])] + ([ENGINE_ROUTE.get(eng["alternative"]["kind"], "email")] if eng.get("alternative") else [])
    return list(dict.fromkeys(out))


def _how_words(eng: Optional[dict]) -> str:
    if not eng:
        return "I can't see a way to book them from their site or listing."
    return {"own_engine": "Their own booking page — I can prefill it for them to confirm.", "form": "Their own booking form — I can prefill it.",
            "widget": "Their booking page — I can prefill it for them to confirm.", "email": "By request (they answer it).",
            "whatsapp": "By a message they answer.", "phone": "By phone.", "instagram": "By a message on their profile."}.get(eng["kind"], "")


UNDER = {"type": "string", "description": "the name the booking goes under, ONLY when they name someone ('book it under Alex Gate'); "
                                          "leave it out to use their own name"}


# Sasha 253 · G7 — a request with NO slot (the old flow's "venue_proposes"): custom work they quote for (a tattoo, a commission —
# an email asking for a date and a quote), or "whenever they have space". G8 — a REAL request to a hotel for N nights (its own
# booking engine with the stay in the link, an email asking for a room, a call that says the stay). /s2, WhatsApp's brain and
# /next under parity only; old S1 (parity off) keeps its schema and its day + time, byte-identical.
OPEN_SLOT = {"enum": ["quote", "whenever"], "description": "ONLY when they want no set time (leave time out): 'quote' — custom work "
                                                          "with no slot to book (a tattoo, a commission): their email asks for a date "
                                                          "and a quote; 'whenever' — 'whenever they have space': the venue proposes "
                                                          "the time. A day they named may stay in `day`."}
NIGHTS = {"type": "integer", "minimum": 1, "maximum": 30,
          "description": "a REAL request to a hotel for this many nights from `day` (check-in; time may be left out): their own "
                         "booking engine with the stay filled in, an email asking for a room, or a call that says the stay. Only "
                         "when they want to book with the hotel itself — a TEST stay is search_stays / hold_booking"}


def with_under(tool: dict) -> dict:
    """Sasha 251 · hold_venue's schema with `under` (the person the booking is for) — /s2 and /next under parity only.
    Sasha 253 · and `open_slot` (G7) and `nights` (G8); day and time no longer required there (API.call: required_of)."""
    sch = dict(tool["input_schema"])
    sch["properties"] = {**sch["properties"], "under": UNDER, "open_slot": OPEN_SLOT, "nights": NIGHTS}
    sch["required"] = [k for k in sch["required"] if k not in ("day", "time")]
    return {**tool, "input_schema": sch}


def required_of(ctx, name: str, required: List[str]) -> List[str]:
    """Sasha 253 · what API.call checks is there: hold_venue on the one path takes no time (G7 / G8) — its own rules say what's
    missing (when_invalid). Old S1 (parity off): exactly as it was."""
    if name == "hold_venue" and one_path(ctx):
        return [k for k in required if k not in ("day", "time")]
    return required


def _nights(ctx, a: dict) -> Optional[int]:
    """Sasha 253 · G8 — the hotel stay's nights (the one path only), else None."""
    try:
        n = int(a.get("nights") or 0)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 30 and one_path(ctx) else None


def _open_slot(ctx, a: dict) -> Optional[str]:
    return a.get("open_slot") if a.get("open_slot") in ("quote", "whenever") and not a.get("time") and one_path(ctx) else None


def _slot_key(ctx, a: dict) -> str:
    """The held booking's `when`, as this hold would make it (the same booking held again is recognised)."""
    if _open_slot(ctx, a):
        return ""
    if _nights(ctx, a) and not a.get("time"):
        return f"{a.get('day')}T15:00"
    return f"{a.get('day')}T{a.get('time')}"[:16]


async def _reservation(ctx, a: dict, rd: dict) -> dict:
    GW = _API()
    nights, open_slot = _nights(ctx, a), _open_slot(ctx, a)
    day = hhmm = None
    try:
        day = date.fromisoformat(str(a["day"]))
        hhmm = time.fromisoformat(str(a["time"])[:5]).strftime("%H:%M")
    except (KeyError, ValueError):
        if nights and day:
            hhmm = "15:00"   # Sasha 253 · G8 — check-in, as the old flow's hotel request (a room is never "at" a time)
        elif open_slot:
            day = day if a.get("day") else None
        elif one_path(ctx):
            raise _err("when_invalid", "day is YYYY-MM-DD and time HH:MM — ask for them; or, when they want no set time, pass "
                                       "open_slot ('quote' for custom work they quote for, 'whenever' for 'whenever they have "
                                       "space'); a hotel stay is day + nights") from None
        else:
            raise _err("when_invalid", "day is YYYY-MM-DD and time HH:MM") from None
    party = max(1, min(20, int(a.get("party") or 2)))
    if nights:   # Sasha 253 · G8 — the stay, as a call or a form says it (in Spanish in Spain): the old flow's own words
        what = GW.stay_what(nights, day.isoformat(), rd.get("country") or a.get("country"))
    else:
        _s, d = await GW.api(ctx.account, "POST", "/api/booking/draft", {"text": _what(a), "country": rd.get("country")})
        what = (d.get("parts") or {}).get("what")
        if not what:
            _s, d = await GW.api(ctx.account, "POST", "/api/booking/draft", {"text": f"{_what(a)} restaurant", "country": rd.get("country")})
            what = (d.get("parts") or {}).get("what") or {"category": "restaurant", "activity": "table"}
    status, cj = await GW.api(ctx.account, "GET", "/api/booking/contact")
    contact = (cj or {}).get("contact") if status == 200 else None
    if not contact:
        if one_path(ctx):   # Sasha 253 · /s2, WhatsApp and /next under parity: she asks once, with the consent, and saves it
            raise _err("contact_missing", await _contact_ask(ctx, a, rd, (cj or {}).get("consent") or {}))
        raise _err("contact_missing", "the venue needs the person's name and mobile — ask them, once")
    # Sasha 251 · "under Alex Gate": the name they gave, else the account's own — the contact (mobile) stays theirs
    under = re.sub(r"\s+", " ", str(a.get("under") or "")).strip()[:80]
    if hhmm is None:   # Sasha 253 · G7 — no slot: the venue proposes (the old flow's reservation for it, word for word)
        return {"schema": "reservation/1", "flow": "availability", "who": {"name": under or contact["name"],
                "contact": {"mobile_e164": contact["mobile_e164"]}}, "what": what, "where": {}, "when": {"mode": "venue_proposes"},
                "how_many": {"count": party, "unit": "people"}}
    return {"schema": "reservation/1", "flow": "book", "who": {"name": under or contact["name"], "contact": {"mobile_e164": contact["mobile_e164"]}},
            "what": what, "where": {}, "when": {"mode": "at", "at": f"{day.isoformat()}T{hhmm}"},
            "how_many": {"count": party, "unit": "people"}}


# ── Sasha 253 · THE BOOKING CONTACT (G5): asked once, saved on the one person record, used from then on ──────────────────────
# A venue needs a name and a mobile. When the account has none, hold_venue's contact_missing tells her what to ask — in ONE
# question, with the consent sentence word for word — and save_contact saves what the person said through the booking API's own
# PUT /api/booking/contact (the same record /you edits; no second store). It never invents a name or a number: both must be in
# the person's own words (this turn, or the turn she asked in); on WhatsApp "this number" is their linked WhatsApp number.

_ASKED: Dict[str, dict] = {}   # account → when she asked, in which session, the words of that turn, the venue's country
ASK_WINDOW_S = 2 * 3600
# a mobile typed without its country code, made E.164 only when the venue's country makes it unambiguous
NATIONAL = {"ES": ("34", r"[67]\d{8}"), "PT": ("351", r"9\d{8}"), "IT": ("39", r"3\d{8,9}"), "FR": ("33", r"0?[67]\d{8}"),
            "GB": ("44", r"0?7\d{9}"), "IE": ("353", r"0?8\d{8}"), "NL": ("31", r"0?6\d{8}"), "DE": ("49", r"0?1[5-7]\d{8,9}"),
            "US": ("1", r"[2-9]\d{9}")}
_THIS_NUMBER = re.compile(r"\b(?:this|my|same|the same)\s+(?:number|one|whatsapp|mobile|phone)\b|\b(?:este|mismo)\s+n[úu]mero\b", re.I)


def _wa(ctx) -> bool:
    return str(getattr(ctx, "session", "") or "").startswith("wa:")


async def _wa_number(account: str) -> Optional[str]:
    from booking_signer import contacts as CT
    GW = _API()
    try:
        ch = await GW.STORE.channel_of_account(account) if GW.STORE is not None else None
    except Exception as e:
        log.warning("[contact] no WhatsApp channel read: %s", type(e).__name__)
        return None
    return CT.e164((ch or {}).get("number_e164"))


async def _known_name(account: str) -> Optional[str]:
    """The name they already told her (remember_name) — so only the mobile is asked."""
    try:
        from agapi import s2_memory as MEM
        return await MEM.first_name(account)
    except Exception as e:
        log.info("[contact] no remembered name: %s", type(e).__name__)
        return None


async def _contact_ask(ctx, a: dict, rd: dict, consent: dict) -> str:
    from booking_signer import contacts as CT
    sentence = consent.get("text") or CT.consent()["text"]
    prev = _ASKED.get(ctx.account)
    if prev and prev["session"] == ctx.session and (datetime.now(timezone.utc) - prev["at"]).total_seconds() < ASK_WINDOW_S:
        return ("You've already asked for their booking name and mobile in this conversation — never ask again. If their message "
                "gives them, call save_contact with exactly what they said, then hold_venue again (same booking). If not, say plainly "
                "the venue can't be booked without a name and mobile, and that they can add them on /you.")
    wa_num = await _wa_number(ctx.account) if _wa(ctx) else None
    named = await _known_name(ctx.account)
    _ASKED[ctx.account] = {"at": datetime.now(timezone.utc), "session": ctx.session, "said": str(ctx.user_said or ""),
                           "country": rd.get("country") or a.get("country"), "name": named}
    if wa_num:
        what = ("their full name — the mobile will be this WhatsApp number (they can give another)" if not named else
                f"whether to book as {named} with this WhatsApp number (or another name or mobile)")
    elif named:
        what = f"a mobile with its country code (their name is {named}; if they've told you their full name, use that)"
    else:
        what = ("their name and a mobile with its country code — if they've already told you their full name in this conversation, "
                "ask only for the mobile")
    under = " The booking itself still goes under the name they gave (under); this is THEIR contact, kept for every booking." \
        if a.get("under") else ""
    return (f"No booking name and mobile on their account yet — the venue needs them. Ask ONCE, in one question, for {what}, and "
            f"say this sentence with it, word for word: \"{sentence}\" When they answer, call save_contact with what they said "
            f"(never a name or number they didn't give), then hold_venue again for the same booking.{under}")


def _in_words(needle: str, texts: List[str]) -> bool:
    words = [w for w in re.findall(r"[^\W\d_]+", needle.casefold()) if w]
    hay = " ".join(texts).casefold()
    return bool(words) and all(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", hay) for w in words)


def _digits_in(raw: str, texts: List[str]) -> bool:
    d = re.sub(r"\D", "", raw)
    return len(d) >= 7 and any(d[-9:] in re.sub(r"\D", "", t) for t in texts)


def _mobile(raw: str, country: Optional[str]) -> Optional[str]:
    from booking_signer import contacts as CT
    got = CT.e164(raw)
    if got:
        return got
    d = re.sub(r"[\s().-]", "", str(raw or ""))
    cc = NATIONAL.get(str(country or "").upper())
    if cc and re.fullmatch(cc[1], d):
        return CT.e164("+" + cc[0] + d.lstrip("0"))
    return None


async def save_contact(ctx, a: dict) -> dict:
    """Sasha 253 · their booking name and mobile, from their own words, saved with the consent they were told."""
    GW = _API()
    said = str(ctx.user_said or "")
    asked = _ASKED.get(ctx.account) or {}
    fresh = asked.get("session") == ctx.session and asked.get("at") and \
        (datetime.now(timezone.utc) - asked["at"]).total_seconds() < ASK_WINDOW_S
    texts = [said] + ([asked.get("said") or ""] if fresh else [])
    name = re.sub(r"\s+", " ", str(a.get("name") or "")).strip()[:80]
    if name and not _in_words(name, texts + ([asked.get("name") or ""] if fresh else [])):
        raise _err("not_their_words", f"they didn't say the name \"{name}\" — ask them for it; never write one for them")
    name = name or (asked.get("name") if fresh else None) or await _known_name(ctx.account) or ""
    if not name:
        raise _err("name_missing", "ask for their name (one short question) — nothing was saved")
    raw = str(a.get("mobile") or "").strip()
    wa_default = _wa(ctx) and (not raw or _THIS_NUMBER.search(raw) or a.get("this_number"))
    if wa_default:
        mobile = await _wa_number(ctx.account)
        if not mobile:
            raise _err("mobile_missing", "this WhatsApp number isn't linked — ask for a mobile with its country code")
    else:
        if not raw or a.get("this_number"):
            raise _err("mobile_missing", "ask for a mobile with its country code, e.g. +34 600 000 000 — nothing was saved")
        if not _digits_in(raw, texts):
            raise _err("not_their_words", "they didn't give that number — ask them for it; never write one for them")
        mobile = _mobile(raw, a.get("country") or asked.get("country"))
        if not mobile:
            raise _err("mobile_unclear", "ask for the mobile with its country code (e.g. +34 600 000 000) — nothing was saved")
    # their own words, THIS turn: the name, the number, or (WhatsApp) "this number" / a yes to the one she offered
    if not ((a.get("name") and _in_words(name, [said])) or (not wa_default and _digits_in(raw, [said]))
            or (wa_default and (_THIS_NUMBER.search(said) or re.match(r"\s*(?:yes|yeah|yep|sure|ok|okay|s[ií]|vale)\b", said, re.I)))):
        raise _err("not_their_words", "save only what they've just told you — ask them for their name and mobile, once")
    s, cj = await GW.api(ctx.account, "GET", "/api/booking/contact")
    c = (cj or {}).get("consent") or {}
    if s != 200 or not c.get("version"):
        raise _err("store_unreachable", "their details couldn't be saved just now — nothing was saved")
    s, j = await GW.api(ctx.account, "PUT", "/api/booking/contact",
                        {"name": name, "mobile": mobile, "consent_version": c["version"], "consent_sha256": c["sha256"]})
    if s != 200:
        raise _err("not_saved", f"I couldn't save that — {GW.refusal_words(j, s)}. Nothing was saved or booked.")
    _ASKED.pop(ctx.account, None)
    saved = (j or {}).get("contact") or {"name": name, "mobile_e164": mobile}
    return {"saved": True, "name": saved.get("name") or name, "mobile_e164": saved.get("mobile_e164") or mobile,
            "how": f"Say in a few words that bookings go under {saved.get('name') or name}, then call hold_venue again for the same "
                   "booking (same details) — never ask for these again."}


SAVE_CONTACT_DESC = ("When a booking needs their name and mobile (hold_venue said contact_missing) and they've just told you: save "
                     "them on their account (with the consent sentence you said), then call hold_venue again. Pass only what they "
                     "said — never make up a name or a number. On WhatsApp leave mobile out (or this_number) for this WhatsApp number.")


async def hold_venue(ctx, a: dict) -> dict:
    """Prepare the booking by its route → the read-back (or the ladder's question first). Nothing is sent."""
    from booking_signer import guest_accounts as GA, guest_receipt as GR
    from agapi.v0 import stale
    GW = _API()
    held = _HELD.get(ctx.account)
    # Sasha 217 · THE SAME BOOKING held again (she re-holds on the yes turn): the read-back they already heard, as it is. A new hold
    # made a new form with a new sha256, so the yes was "read back first" again — and the booking looped, never sent.
    if held and held.get("out") and held["at"] < ctx.started and not stale(held["at"]) \
            and (not a.get("route") or a.get("route") == held.get("rung")) \
            and str(held.get("when") or "")[:16] == _slot_key(ctx, a) and int(held.get("party") or 0) == int(a.get("party") or 0) \
            and ((a.get("place_id") and a.get("place_id") == held.get("place_id")) or _base(a.get("name") or "") == _base(held.get("venue") or "")):
        card = card_of(ctx.account, a.get("place_id") or held.get("place_id"), a.get("name"))
        return _with_card(card, {**held["out"], "same_read_back": "they've heard this — on their yes, call book_venue (never hold again)"})
    # Sasha 226 · a NEW hold supersedes the old one at once: if this one ends in a question (choose_route…) or an error, a yes must
    # never fall through to the earlier venue's read-back (found live: "D-Sunset" read back, the yes booked the held "El Mirador")
    _PREV[ctx.account] = _HELD.pop(ctx.account, None)   # Sasha 236 · kept aside ONLY to tell "the same words again" (_hold)
    rd = await _read(ctx, a)
    res = await _reservation(ctx, a, rd)
    at = res["when"].get("at") or ""   # Sasha 253 · G7 — none when the venue proposes
    now = datetime.now(timezone.utc)
    route = a.get("route")
    card = card_of(ctx.account, a.get("place_id"), a.get("name"))   # Sasha 213 · this venue's card, highlighted on screen
    eng = await engine_channel(card)                                 # Sasha 248 · the venue's ONE channel, from the venue engine
    if not eng and one_path(ctx):
        # Sasha 251 · ONE PATH (found live, D4: the hammam's branch went down Sasha's older page path — "Shall I send it to your
        # phone?"): what Sasha's own read found becomes the engine path's channel, so the same question and executors decide
        eng = read_channel(rd, card)
        if not eng:
            raise _err("no_route", f"I can't see a way to book {GW.plain_venue(rd['venue'])} from their site or listing")
    if eng:
        got = await _engine_route(ctx, a, rd, res, at, now, route, eng, card)
        if got is not None:
            return _with_card(card, got)
    return _with_card(card, await _hold_inner(ctx, a, rd, res, at, now, route))


async def engine_channel(card: Optional[dict], budget_s: float = 30.0) -> Optional[dict]:
    """Sasha 248 · ONE BOOKING PATH: how this venue books, from the venue engine's read of its own site (agapi/venue_truth) —
    the same read its card and detail sheet show. None: no site / not readable (then Sasha's own read decides, as before)."""
    import asyncio
    from agapi import venue_truth as VT
    if not card or not card.get("website"):
        return None
    try:
        p = await asyncio.wait_for(VT.profile(card), timeout=budget_s)
    except Exception:
        p = VT.shape(card, VT.cached(card))
    return p.get("channel")


# "page" — the tool's own route word (its schema unchanged: S1 parity) — means "fill it now" when the engine's channel is a form
ENGINE_ROUTE = {"own_engine": "page", "form": "page", "widget": "page", "email": "email", "whatsapp": "page", "phone": "call",
                "instagram": "instagram"}   # Sasha 251 · a place that books only by a message on its profile: the drafted message


async def _engine_route(ctx, a: dict, rd: dict, res: dict, at: str, now, route: Optional[str], eng: dict, card: Optional[dict]) -> Optional[dict]:
    """The engine's channel → the ONE question (a form AND another way: Tyler's words, verbatim) or that channel's read-back.
    None: hand on to the request executors (email / WhatsApp / call) with the route set."""
    from agapi import venue_truth as VT
    from app.agent import voice as V
    if (res.get("when") or {}).get("mode") == "venue_proposes":   # Sasha 253 · G7 — no slot: the request (email, else a call), its read-back, the yes
        return await _open_request(ctx, a, rd, res, route)
    if _nights(ctx, a):
        # Sasha 253 · G8 — HOTELS STAY ON THE LADDER: their own booking engine with the stay in its link (the links API builds it —
        # a prefilled page can't carry the dates), an email asking for a room, a call that says the stay. No "email or book now?"
        # question (the old flow never asked it for a room); the person's chosen route first.
        return await _hold_inner(ctx, a, rd, res, at, now, route)
    if not route and eng.get("ask"):
        alt = ENGINE_ROUTE.get((eng.get("alternative") or {}).get("kind") or "", "email")
        return {"status": "choose_route", "venue": rd["venue"], "ask": V.ASK_BOOK,
                "options": [{**o, "route": o["route"] or alt} for o in V.CHOICES],
                "how": "Ask `ask` word for word, then hold_venue again with the route they chose."}
    route = route or ENGINE_ROUTE.get(eng.get("kind") or "")
    if eng.get("from") == "read" and (eng.get("kind") in READ_ROUTE or not eng.get("url")) and not (route == "page" and eng.get("url")):
        # Sasha 251 · a channel Sasha's own read found: its own executor (the form fill, the drafted message, the email, the call,
        # their page to the phone) — the same one question decided it, above
        if route == "page" and eng.get("kind") == "form":
            route = "form"
        elif route in (None, "page") or route == ENGINE_ROUTE.get(eng.get("kind") or ""):
            route = READ_ROUTE.get(eng.get("kind") or "", route or "page")
        return await _hold_inner(ctx, a, rd, res, at, now, route)
    if route in ("page", "form", "whatsapp") and eng.get("kind") in VT.PREPARED:   # venue.prepare_booking prepares it (row 775)
        held = await _prepared(ctx, a, rd, res, at, now, eng, card)
        # Sasha 249 · ONE QUESTION: the prefilled form IS their go-ahead — nothing reaches the venue until they confirm it themselves,
        # so no second yes. It goes on their screen now, recorded like any attempt.
        return await _finish(ctx, _HELD[ctx.account]) if held.get("status") == "awaiting_yes" and ctx.account in _HELD else held
    return None if route in (None, "no") else await _hold_inner(ctx, a, rd, res, at, now, route)


async def _prepared(ctx, a: dict, rd: dict, res: dict, at: str, now, eng: dict, card: Optional[dict]) -> dict:
    """"Fill it now", until AgAPI's venue.prepare_booking is live: their OWN booking page (the engine's evidence) on their phone,
    with every detail shown and one-tap copy — they confirm there (a CAPTCHA, if any, is theirs). Read back first; on the yes,
    book_venue sends it. The attempt goes in the outcomes ledger as human_tap."""
    import hashlib as _h
    from booking_signer import guest_receipt as GR
    GW = _API()
    url = eng.get("url") or (card or {}).get("website")
    if not url:
        return {"status": "no_route", "venue": rd["venue"], "say": "Their booking page isn't on their site — ask how they'd like to book."}
    email = await GR.address_of(ctx.account)
    fields = [{"label": "Day", "value": GW.summary(res).split(" at ")[0]}, {"label": "Time", "value": at[11:16]},
              {"label": "People", "value": str(res["how_many"]["count"])}, {"label": "Name", "value": res["who"]["name"]},
              *([{"label": "Email", "value": email}] if email else []),
              {"label": "Mobile", "value": res["who"]["contact"].get("mobile_e164") or ""}]
    venue = GW.plain_venue(rd["venue"])
    if eng.get("kind") == "whatsapp":   # a prepared WhatsApp they send — a request: the venue answers yes or no
        lines = [f"I'll put a message to {venue} on your phone, ready to send: {GW.summary(res)}, under {res['who']['name']}.",
                 "You press send — I never send it for you.", "It's a request: nothing is booked until they reply."]
    else:
        lines = [f"I'll put {venue}'s own booking page on your phone, with your booking ready to confirm: {GW.summary(res)}, under {res['who']['name']}.",
                 "You press confirm there (and tick any “I'm not a robot” box) — I can't press it for you.",
                 "Nothing is booked until " + ("their page confirms it." if eng.get("confirm") == "instant" else "they confirm it.")]
    ly = await _loyalty(ctx, rd, res)
    if ly:   # Sasha 253 · G14 — a matching loyalty number from the Keep: named in the read-back (the Keep's rule), masked in every
        # field she or the screen sees; its value is opened once, logged, only into the copy on THEIR phone (_book_inner)
        from booking_signer import loyalty as LY
        from booking_signer.vault import crypto as VC
        lines = lines[:1] + [VC.access_line(ly.get("provider") or "", ly.get("label") or "", "identifier")] + lines[1:]
        key = str(ly.get("provider") or "").strip().lower()
        fields.append({"label": LY.NAMES.get(LY.ALIASES.get(key, key), ly.get("label") or "Loyalty number"), "value": LY.TOKEN,
                       "loyalty_item": str(ly["id"])})
    sha = _h.sha256("\n".join(lines + [url]).encode()).hexdigest()
    prev = _HELD.get(ctx.account)
    _HELD[ctx.account] = {"rung": "prepared", "id": "prep-" + sha[:12], "sha": sha, "at": prev["at"] if prev and prev.get("sha") == sha else now,
                          "venue": rd["venue"], "summary": GW.summary(res), "when": at, "party": res["how_many"]["count"],
                          "place_id": rd.get("place_id"), "url": url, "fields": fields, "channel_name": eng.get("name"), "website": (card or {}).get("website"),
                          **({"lines": lines + [url]} if ly else {}),
                          "sector": (res.get("what") or {}).get("category")}
    return {"status": "awaiting_yes", "venue": venue, "route": "page", "when": GW.summary(res), "read_back": lines,
            "what_happens": "on their yes, book_venue puts their own page on their phone with every detail to copy; they confirm there"}


def _with_card(card: Optional[dict], out: dict) -> dict:
    if card and isinstance(out, dict):
        out["card"] = card
    return out


async def _loyalty(ctx, rd: dict, res: dict) -> Optional[dict]:
    """Sasha 253 · G14 — the one saved loyalty number that matches this booking (booking_signer.loyalty.find_for: a fixed list,
    never a guess), on the one path only. Its value is never here: the booking API names it in the read-back and opens it once,
    at the send, under the yes (form_rung); she says only the read-back's line."""
    if not one_path(ctx):
        return None
    from booking_signer import loyalty as LY
    return await LY.find_for(ctx.account, rd["venue"], (res.get("what") or {}).get("category"))


async def _open_request(ctx, a: dict, rd: dict, res: dict, route: Optional[str]) -> dict:
    """Sasha 253 · G7 — a request with NO slot (custom work they quote for; "whenever they have space"): the old flow's own email
    asking for a date and a quote (GW.quote_email — the body of POST /api/booking/emails), else a call that asks when they have
    space (the reservation's availability flow). Read back; on the yes, book_venue sends it. Nothing is booked until they reply."""
    from booking_signer import guest_receipt as GR
    GW = _API()
    if route == "no":
        return {"status": "not_booking", "venue": rd["venue"]}
    rungs, why = rd["rungs"], None
    venue = GW.plain_venue(rd["venue"])
    day = str(a.get("day") or "")[:10]
    try:
        day = date.fromisoformat(day).isoformat()
    except ValueError:
        day = ""
    for r in (["call", "email"] if route == "call" else ["email", "call"]):
        if r == "email" and "email" in rungs:
            mine = await GR.address_of(ctx.account)
            status, j = await GW.api(ctx.account, "POST", "/api/booking/emails",
                                     GW.quote_email(rd["read_id"], res["who"]["name"], mine, _what(a), day or None))
            if status == 200:
                return _hold(ctx, "email", j["email_id"], j["read_back"], rd, res,
                             extra={"trip_item_id": j.get("trip_item_id"), "open_slot": a.get("open_slot"),
                                    "say": GW.quote_sentence(venue, day or None)})
            why = GW.refusal_words(j, status)
        elif r == "call" and "phone" in rungs:
            fi = rungs["phone"].get("fact_index")
            status, j = await GW.api(ctx.account, "POST", "/api/booking/calls",
                                     {"reservation": res, "read_id": rd["read_id"], **({"fact_index": fi} if fi is not None else {})})
            if status == 200:
                return _hold(ctx, "call", j["call_id"], j["read_back"], rd, res,
                             extra={"trip_item_id": j.get("trip_item_id"), "open_slot": a.get("open_slot")})
            why = GW.refusal_words(j, status)
    raise _err("no_route", f"{venue} can't be asked without a time from here" + (f" — {why}" if why else
                           " (no email or phone to ask on) — ask the person for a day and time"))


async def _hold_inner(ctx, a: dict, rd: dict, res: dict, at: str, now, route: Optional[str]) -> dict:
    from booking_signer import guest_accounts as GA, guest_receipt as GR
    GW = _API()
    nights = _nights(ctx, a)   # Sasha 253 · G8 — a hotel stay (the one path only)
    msg_routes = [x for x in _routes_of(rd) if x in ("whatsapp", "instagram")]
    # Sasha 232 · /s2, DIRECT FIRST for every kind of place: their own form or booking page (their booking software IS their form) →
    # their own WhatsApp (drafted; THEY send it from their WhatsApp — S-48 Mode A) → email → phone. S1 unchanged.
    # Sasha 248 · reached ONLY when the venue engine had no channel for this place (no site / not readable): Sasha's own read decides
    wa_first = (not route and getattr(ctx, "surface", "s1") == "s2" and "whatsapp" in msg_routes
                and not {"form", "page"} & set(_routes_of(rd)) and not nights)
    if wa_first:
        msg_routes = ["whatsapp"]
    if route in ("whatsapp", "instagram") or wa_first or (not route and msg_routes and set(_routes_of(rd)) <= {"whatsapp", "instagram"}):
        # Sasha 212 · a place that books only by a message (a tattoo studio on Instagram, a bar on WhatsApp): Sasha DRAFTS it
        # for their phone — they send it; nothing is booked until the place answers them
        ch = route if route in ("whatsapp", "instagram") else msg_routes[0]
        val = str((rd["rungs"].get(ch) or {}).get("value") or "")
        n = res['how_many']['count']
        when_words = f"{n} {'person' if n == 1 else 'people'}"
        asked = _what(a)   # Sasha 232 · the service they asked for ("a 60-minute massage") — found live: the draft left it out
        svc = f" ({asked})" if asked and asked.lower() not in ("a table", "table", "dinner", "lunch") else ""
        msg = (f"Hola, quería pedir cita{svc} para {n} {'persona' if n == 1 else 'personas'} el {at[:10]} a las {at[11:16]}, a nombre de {res['who']['name']}. "
               f"¿Tienen disponibilidad? Gracias." if rd.get("country") == "ES" else
               f"Hello, I'd like to book{svc} for {when_words} on {at[:10]} at {at[11:16]}, under {res['who']['name']}. "
               f"Do you have availability? Thank you.")
        link = (f"https://wa.me/{re.sub(r'[^0-9]', '', val)}?text={quote(msg)}" if ch == "whatsapp" and re.sub(r"\D", "", val)
                else f"https://ig.me/m/{val}" if ch == "instagram" and val else None)
        prev = _HELD.get(ctx.account)
        sha = hashlib.sha256(f"draft|{ch}|{rd['venue']}|{msg}".encode()).hexdigest()
        _HELD[ctx.account] = {"rung": "draft", "id": ch, "sha": sha, "at": prev["at"] if prev and prev.get("sha") == sha else now,
                              "venue": rd["venue"], "summary": GW.summary(res), "when": at, "party": res["how_many"]["count"],
                              "message": msg, "link": link, "channel": ch}
        return {"status": "draft_message", "venue": GW.plain_venue(rd["venue"]), "route": ch, "message": msg,
                **({"open_in_" + ch: link} if link else {}),
                "what_happens": f"they book only by a {('WhatsApp' if ch == 'whatsapp' else 'Instagram')} message: on their yes, "
                                "Sasha sends the drafted message to their phone and they send it; it is NOT booked until the place replies"}
    if not route and not nights:   # Sasha 253 · G8 — a room: no ladder question (the old flow's rule), the decision's order
        lad = GW.ladder_of(rd, res, now)
        acts = [r for _t, r in (lad or {}).get("options") or [] if r != "no"]
        if lad and len(acts) == 1 and getattr(ctx, "surface", "s1") == "s2":
            # Sasha 230 · /s2: ONE way to book it ("I can book X directly — shall I?") is not a choice — straight to that route's
            # read-back, which asks the one yes. Found live (10 Oct): the pick got "shall I?", the yes got the read-back's "shall
            # I send it?" — the same question twice, and on the phone it looked like she'd repeated the step. A real choice
            # (email or book now, the page or a call) still asks first. S1 unchanged.
            route = acts[0]
        elif lad and lad.get("options"):
            return {"status": "choose_route", "venue": rd["venue"], "ask": lad["line"],
                    "options": [{"title": t, "route": r} for t, r in lad["options"]]}
    if route == "no":
        return {"status": "not_booking", "venue": rd["venue"]}
    dv = GW.decision_of(rd, ROUTE_TO_PREFER.get(route or ""), at, now, ctx.account)
    order = [r for r in [dv.route] + list(dv.alternatives) if r]
    if route in ROUTE_TO_PREFER:   # the person's choice first
        order = [ROUTE_TO_PREFER[route]] + [r for r in order if r != ROUTE_TO_PREFER[route]]
    rungs, why = rd["rungs"], None
    contact_name = res["who"]["name"]
    for r in order:
        if r == "form" and "form" in rungs:
            email = await GR.address_of(ctx.account)
            rf = {**res, "who": {**res["who"], "contact": {**res["who"]["contact"], **({"email": email} if email else {})}}}
            ly = await _loyalty(ctx, rd, res)   # Sasha 253 · G14 — a matching loyalty number from the Keep, under this yes
            status, j = await GW.api(ctx.account, "POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": rf,
                                                                                 **({"loyalty_item_id": str(ly["id"])} if ly else {})})
            rung = "form"
            if status != 200 and GA.founder(ctx.account):   # the founder's override: the cloud browser fills it; a human step → the phone
                status, j = await GW.api(ctx.account, "POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": rf, "handover": True})
                rung = "handover"
            if status == 200:
                return _hold(ctx, rung, j["form_id"], j["read_back"], rd, res, extra={"trip_item_id": j.get("trip_item_id")})
            why = GW.refusal_words(j, status)
        elif r == "one_tap" and ("link" in rungs or "form" in rungs or "own_page" in rungs):   # Sasha 246 · their own page
            status, j = await GW.api(ctx.account, "POST", "/api/booking/links", {
                "read_id": rd["read_id"], "date": at[:10], "time": at[11:16], "party": res["how_many"]["count"], "name": contact_name,
                "venue": GW.plain_venue(rd["venue"])[:120],
                # Sasha 233 · /s2: the service asked for, so a Fresha/Treatwell/Booksy page's matching service + price is read back
                **({"asked_for": _what(a)} if getattr(ctx, "surface", "s1") == "s2" and not nights else {}),
                **({"nights": nights} if nights else {})})   # Sasha 253 · G8 — the stay in their engine's link (slot_link.build_hotel)
            if status == 200:
                return _hold(ctx, "page", j["link_id"], j["read_back"], rd, res,
                             extra={"url": j["url"], "platform": j.get("platform"), "slot_filled": bool(j.get("slot_filled")),
                                    "trip_item_id": j.get("trip_item_id"),
                                    **({"nights": nights, "hotel_text": GW.hotel_link_text(GW.plain_venue(rd["venue"]), j)} if nights else {})})
            why = GW.refusal_words(j, status)
        elif r in ("call", "call_email") and "phone" in rungs:
            fi = rungs["phone"].get("fact_index")
            status, j = await GW.api(ctx.account, "POST", "/api/booking/calls",
                                     {"reservation": res, "read_id": rd["read_id"], **({"fact_index": fi} if fi is not None else {})})
            if status == 200:
                return _hold(ctx, "call", j["call_id"], j["read_back"], rd, res, extra={"trip_item_id": j.get("trip_item_id")})
            why = GW.refusal_words(j, status)
        elif r == "email" and "email" in rungs:
            mine = await GR.address_of(ctx.account)
            status, j = await GW.api(ctx.account, "POST", "/api/booking/emails", {
                "read_id": rd["read_id"], "date": at[:10], "time": at[11:16], "party": res["how_many"]["count"], "name": contact_name,
                "email": mine or "", **({"nights": nights} if nights else {})})   # Sasha 253 · G8 — the room email (N nights)
            if status == 200:
                return _hold(ctx, "email", j["email_id"], j["read_back"], rd, res, extra={"trip_item_id": j.get("trip_item_id"),
                             **({"nights": nights, "say": GW.room_email_sentence(GW.plain_venue(rd["venue"]), res["how_many"]["count"],
                                                                                 at[:10], nights)} if nights else {})})
            why = GW.refusal_words(j, status)
    raise _err("no_route", f"{GW.plain_venue(rd['venue'])} can't be booked from here right now" + (f" — {why}" if why else ""))


_PREV: Dict[str, Optional[dict]] = {}   # Sasha 236 · account → the hold a new hold_venue superseded (for _hold's same-words check only)


def _same_words(lines: List[str]) -> str:
    """Sasha 236 · a read-back's words without its one-time forwarding address: what the person HEARD, for "is this the same one?"."""
    import hashlib as _h
    return _h.sha256("\n".join(re.sub(r"act-[0-9a-f-]+@", "act-@", str(l)) for l in lines).encode()).hexdigest()


def _hold(ctx, rung: str, rid: str, read_back: dict, rd: dict, res: dict, extra: Optional[dict] = None) -> dict:
    GW = _API()
    prev = _HELD.get(ctx.account) or _PREV.pop(ctx.account, None)
    # Sasha 236 · the same booking held again is the same read-back, whatever its ONE-TIME forwarding address (act-<uuid>@…) —
    # found live on /s2: a page route's read-back changed on every hold, so the yes never answered one they'd heard
    same = _same_words(read_back.get("lines") or [])
    at = prev["at"] if prev and (prev.get("sha") == read_back["sha256"] or (prev.get("same") == same and prev.get("rung") == rung)) \
        else datetime.now(timezone.utc)
    _HELD[ctx.account] = {"rung": rung, "id": rid, "sha": read_back["sha256"], "at": at, "venue": rd["venue"], "summary": GW.summary(res),
                          "place_id": rd.get("place_id"),
                          "when": res["when"].get("at") or "", "party": res["how_many"]["count"], "same": same,
                          "sector": (res.get("what") or {}).get("category"), **(extra or {})}   # CR 87 · the sector, for the outcomes ledger
    lines = GW.guest_lines(rung, read_back.get("lines") or [])
    out = {"status": "awaiting_yes", "venue": GW.plain_venue(rd["venue"]), "route": rung, "when": GW.summary(res),
            "read_back": lines, "what_happens": {
                "form": "Sasha sends their own booking form",
                "handover": "Sasha fills their booking page; if it needs a human step (a CAPTCHA, terms, the final button) "
                            "it goes to their phone as Tap to finish",
                # Sasha 246 · their OWN booking page (rung 2) is named as itself, never "their their own booking page page"
                "page": (f"{extra['platform']} goes to their phone, with the day, time and number to enter; they finish it there"
                         if str(extra.get("platform") or "").startswith("their ") else
                         f"their {extra.get('platform') or 'booking'} page goes to their phone; they press book there") if extra else "",
                "email": ("Sasha emails them asking for a date and a quote; nothing is booked until they reply" if (extra or {}).get("open_slot")
                          else f"Sasha emails the hotel asking for a room for {extra['nights']} nights; it's a request until they reply"
                          if (extra or {}).get("nights") else "Sasha emails them; it's a request until they reply"),
                "call": "Sasha calls them; it's booked only if they say yes on the call"}.get(rung, "")}
    if (extra or {}).get("say"):   # Sasha 253 · G7 / G8 — the old flow's own sentence for a request with no slot / a room
        out["say"] = extra["say"]
    _HELD[ctx.account]["out"] = out   # Sasha 217 · the same booking held again gets these words, unchanged
    # Sasha 236 · held again in the turn they said yes to it (found live on /s2: she re-held and asked again, turn after turn):
    # the read-back is the one they heard in an EARLIER turn, and this turn's words are an explicit yes → book it now
    from agapi.v0 import yes_to_book
    if at < ctx.started and yes_to_book(ctx.user_said or ""):
        return {**out, "status": "yes_heard", "how": "They already heard this read-back and said yes this turn: call book_venue now. "
                                                     "Don't ask again."}
    return out


async def book_venue(ctx, a: dict) -> dict:
    """After the person's explicit yes in a LATER turn: the prepared booking, by its route."""
    from agapi.v0 import claim, stale, yes_to_book
    GW = _API()
    said = ((a.get("approval") or {}).get("said")) or ""
    if not yes_to_book(said):
        raise _err("no_explicit_yes", "booking needs the person's explicit yes in this turn — ask them, then call book_venue")
    held = _HELD.get(ctx.account)
    if not held:
        raise _err("nothing_held", "call hold_venue first — the yes is bound to its read-back")
    if held["at"] >= ctx.started:
        raise _err("read_back_first", "say what you'll do and ask them to go ahead; book once they say yes")
    if stale(held["at"]):   # Sasha 215 · a read-back over 15 minutes old is never acted on: prepared again, said again
        _HELD.pop(ctx.account, None)
        raise _err("read_back_stale", "that was prepared over 15 minutes ago — call hold_venue again and read it back before booking")
    return await _finish(ctx, held, {"how": "voice", "said": said})


async def _finish(ctx, held: dict, how: Optional[dict] = None) -> dict:
    """Book what's held, once: claimed, recorded in the outcomes ledger (CR 87), its card with it. book_venue after a yes; a
    prefilled form straight away (Sasha 249 — the form is their go-ahead)."""
    from agapi.v0 import claim
    GW = _API()
    if how:   # an act on their yes: claimed first (a prefilled form sends nothing to the venue — nothing to claim)
        await claim(ctx)   # Sasha 215 · durable: sent once, across restarts and workers
    how = how or {"how": "chose_form", "said": "prefilled form"}
    venue, rung = GW.plain_venue(held["venue"]), held["rung"]
    _HELD.pop(ctx.account, None)
    card = card_of(ctx.account, held.get("place_id"), venue)
    from agapi import s2_outcomes as OC   # CR 87 · every real booking attempt goes in the outcomes ledger (never the person's details)
    try:
        out = await _book_inner(ctx, held, how, venue, rung)
    except Exception as e:
        await OC.booked(ctx.account, held, venue, area_of(card) if card else None, error=str(getattr(e, "message", "") or type(e).__name__))
        raise
    await OC.booked(ctx.account, held, venue, area_of(card) if card else None, result=out)
    return _with_card(card, out)


async def _book_inner(ctx, held: dict, how: dict, venue: str, rung: str) -> dict:
    from booking_signer import slot_link as SL, wa_brain as WB
    GW = _API()
    where = await WB.trip_day_words(ctx.account, held["when"][:10], venue)
    if rung == "form":
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/forms/{held['id']}/send", {"read_back_sha256": held["sha"], "approval": how}, timeout=120)
        if status != 200:
            raise _err("not_sent", GW.refusal_words(j, status))
        result = (j.get("reading") or {}).get("result") if j.get("status") == "sent" else None
        ref = j.get("booking_reference") if result == "confirmed" else None
        return {"status": "confirmed" if result == "confirmed" else ("requested" if j.get("status") == "sent" else "not_sent"),
                "venue": venue, "when": held["summary"], "itinerary": where, **({"reference": ref} if ref else {}),
                "line": (f"✅ Booked: {venue}, {held['summary']}." + (f" Their reference: {ref}." if ref else "")) if result == "confirmed"
                else __import__("app.agent.voice", fromlist=["x"]).SENT}   # Sasha 249 · her short confirmation
    if rung == "draft":   # Sasha 212 · the drafted message goes to THEIR phone; they send it — never "booked"
        sent = False
        try:
            ch = await GW.STORE.channel_of_account(ctx.account) if GW.STORE else None
            if ch:
                # Sasha 249 · her voice never names the channel: the link opens the right one
                out = await GW._tell(ch, f"✍️ For {venue} — send them this{': ' + held['link'] if held.get('link') else ''}\n\n{held['message']}")
                sent = "sent" in out and "not" not in out
        except Exception as e:
            log.warning("[venues] the draft was not sent to the phone: %s", type(e).__name__)
        return {"status": "draft_on_phone" if sent else "draft_message", "venue": venue, "when": held["summary"], "booked": False,
                "message": held["message"], **({"open": held["link"]} if held.get("link") and not sent else {}),
                "line": "It's not booked until they reply to you."}
    if rung == "prepared":   # Sasha 248 · "fill it now": their own page + every detail, on their phone; they confirm there
        from agapi import venue_truth as VT
        f = {x["label"]: x["value"] for x in held["fields"]}
        prep = await VT.prepare({"name": venue, "website": held.get("website"), "place_id": held.get("place_id")},
                                {"name": f.get("Name"), "phone": f.get("Mobile"), "email": f.get("Email")},
                                held["when"][:10], held["when"][11:16], int(held["party"]))   # CR 89 · ready to confirm; nothing submitted
        if prep:
            held = {**held, "url": prep["link"], "human_step": prep.get("human_step"), "prep_say": prep.get("say")}
        phone_fields = await _with_loyalty(ctx, held)   # Sasha 253 · G14 — the value only here, on their phone
        text = (f"📝 {venue} — your booking, ready to copy into their page:\n" + "\n".join(f"{x['label']}: {x['value']}" for x in phone_fields)
                + f"\n\nTheir page: {held['url']}\n" + (prep.get("human_step") if prep and prep.get("human_step") else
                                                           "Press confirm there — it's booked only when their page says so."))
        sent = False
        try:
            ch = await GW.STORE.channel_of_account(ctx.account) if GW.STORE else None
            if ch:
                o = await GW._tell(ch, text)
                sent = "sent" in o and "not" not in o
        except Exception as e:
            log.warning("[venues] the prepared page was not sent to the phone: %s", type(e).__name__)
        return {"status": "page_on_phone" if sent else "page_link", "venue": venue, "when": held["summary"], "itinerary": where, "booked": False,
                "prepared": {"venue": venue, "url": held["url"], "fields": held["fields"], "on_phone": sent,
                             **({"human_step": held["human_step"], "prepared_by": "venue.prepare_booking"} if held.get("human_step") else {})},
                # Sasha 249 · her words for it are her voice's, never the engine's (which may name the booking platform)
                "say": __import__("app.agent.voice", fromlist=["x"]).done_form(getattr(ctx, "surface", "s2")) + " Say exactly that — never that it's booked."}
    if rung == "handover":
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/forms/{held['id']}/handover", {}, timeout=120)
        if status != 200:
            raise _err("not_opened", (j or {}).get("say") or GW.refusal_words(j, status))
        sent = bool((j.get("phone") or {}).get("sent"))
        return {"status": "tap_to_finish", "venue": venue, "when": held["summary"], "itinerary": where, "on_phone": sent,
                **({} if sent else {"open": j.get("view_url")}), **({"view_url": j["view_url"]} if j.get("view_url") else {})}
    if rung == "page":
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/links/{held['id']}/opened", {"read_back_sha256": held["sha"]})
        if status != 200:
            raise _err("not_sent", GW.refusal_words(j, status))
        dt = datetime.fromisoformat(held["when"])
        url = j.get("url") or held.get("url")
        text = held.get("hotel_text") or SL.platform_message(venue, held.get("platform") or "their booking page", dt.date(), dt.time(),
                                                             held["party"], bool(held.get("slot_filled")), url)   # Sasha 253 · G8 — the stay
        out = await GW.tap_platform(ctx.account, text, url, held["id"], venue, held["when"])
        sent = "sent" in out and "not" not in out
        return {"status": "page_on_phone" if sent else "page_link", "venue": venue, "when": held["summary"], "itinerary": where,
                "platform": held.get("platform"), **({} if sent else {"open": url}), **({"page_url": url} if url else {}),
                # Sasha 236 · found live on /s2: "their page is on your phone" when it wasn't sent there
                **({} if sent else {"say": "Their page is on this screen — Tap to finish opens it. Never say it's on their phone."})}
    if rung == "email":
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/emails/{held['id']}/send", {"read_back_sha256": held["sha"], "approval": how}, timeout=60)
        if status != 200 or j.get("status") != "sent":
            raise _err("not_sent", (j or {}).get("say") or GW.refusal_words(j, status))
        return {"status": "requested", "venue": venue, "when": held["summary"], "itinerary": where,
                "line": __import__("app.agent.voice", fromlist=["x"]).SENT}   # Sasha 249 · her short confirmation
    status, j = await GW.api(ctx.account, "POST", f"/api/booking/calls/{held['id']}/place", {"read_back_sha256": held["sha"], "approval": how}, timeout=120)
    if status != 200:
        raise _err("not_called", GW.refusal_words(j, status))
    if j.get("status") in ("placed", "uncertain"):   # Sasha 253 · G2 — its result pushed to their WhatsApp when the call ends
        await _push_later(ctx.account, call_id=held["id"], venue=venue, purpose="book", what=held.get("summary") or "")
    return {"status": j.get("status"), "venue": venue, "when": held["summary"], "itinerary": where,
            **({"scheduled_for": str(j.get("scheduled_for") or "")[11:16]} if j.get("status") == "scheduled" else {})}


async def _with_loyalty(ctx, held: dict) -> List[dict]:
    """Sasha 253 · G14 — the prepared page's fields for THEIR phone: a loyalty number's value opened once from the Keep (vault.use:
    bound to the read-back that named it, logged as a loyalty_number use). Anything refused: the number is left out, said so."""
    lf = next((x for x in held.get("fields") or [] if x.get("loyalty_item")), None)
    if not lf:
        return list(held.get("fields") or [])
    from booking_signer.vault import crypto as VC
    lines = list(held.get("lines") or [])
    number = None
    try:
        async with VC.use(ctx.account, lf["loyalty_item"], approval={"read_back_sha256": held["sha"], "at": held["at"].isoformat()},
                          approved_lines=lines, action_kind="loyalty_number", action_ref=held["id"]) as secret:
            number = (secret.get("value") or "").strip() or None
    except Exception as e:   # a loyalty number is a nicety: never a reason the booking isn't prepared
        log.info("[venues] loyalty number not opened: %s", type(e).__name__)
    return [({**x, "value": number} if x is lf and number else
             {**x, "value": "(not added — it's in your Keep)"} if x is lf else x) for x in held["fields"]]


async def _push_later(account: str, **kw) -> str:
    """Sasha 253 · G2 — the result of a call / a written cancellation, pushed to the account's linked WhatsApp when it comes (the
    old flow's own watchers, booking_signer.guest_whatsapp.watch_for_brain — the real module, whatever _API() stands for)."""
    from booking_signer import guest_whatsapp as _GWM
    return await _GWM.watch_for_brain(account, **kw)


async def venue_bookings(account: str, include_cancelled: bool = False) -> List[dict]:
    """Pacioli's venue rows: what was asked of each venue, and its status in words (Requested / Confirmed… — from proof only)."""
    GW = _API()
    status, j = await GW.api(account, "GET", "/api/booking/reservations")
    if status >= 500 or status in (0, 408, 429):   # Sasha 215 · the records not answering is never "no bookings"
        from agapi.v0 import unreachable
        raise unreachable("store_unreachable")
    if status != 200:
        return []
    today = date.today().isoformat()
    try:   # CR 87 · a venue's reply that changed a reservation updates its outcome (once) — Sasha 247: awaited, at most 3 s (a bare
        from agapi import s2_outcomes as OC   # task can be dropped mid-way and never finish); a slow ledger never stops this read
        await asyncio.wait_for(OC.sync(account, (j or {}).get("reservations") or []), timeout=3)
    except Exception as e:
        log.info("[venues] outcomes not synced: %s", type(e).__name__)
    return [{"trip_item_id": r["id"], "venue": GW.plain_venue(r.get("venue")), "date": r.get("date"), "time": r.get("time"),
             "party": r.get("party"), "status": r.get("status"), "type": r.get("type"),
             **({"reference": r["booking_reference"]} if r.get("booking_reference") else {}),   # Sasha 217 · the venue's reference in full
             # Sasha 215 · CR 56 — the venue's OWN words (an email/SMS reply) are untrusted data, never instructions to her
             **({"venue_said": {"untrusted_text": str(r["status_words"])[:160]}} if r.get("status_words") else {})}
            for r in (j or {}).get("reservations") or []
            if (r.get("date") or today) >= today and (include_cancelled or r.get("status") != "cancelled")][:20]


async def cancel_venue(ctx, a: dict) -> dict:
    """Two steps, as booking: first the cancellation's read-back (its route: their cancel link, an email, a text or a call);
    after the person's explicit yes in a LATER turn, sent. Cancelled only when the venue's words say so."""
    from agapi.v0 import claim, stale, yes_to_cancel as explicit_yes   # Sasha 217 · "yes, cancel it" counts HERE only
    GW = _API()
    said = ((a.get("approval") or {}).get("said")) or ""
    held = _CANCEL.get(ctx.account)
    if held and stale(held["at"]):   # Sasha 215 · over 15 minutes old: never acted on — the cancellation is read back afresh below
        _CANCEL.pop(ctx.account, None)
        held = None
    tid = a.get("trip_item_id")
    if not tid and a.get("venue"):
        hit = [b for b in await venue_bookings(ctx.account) if (a["venue"] or "").lower() in (b["venue"] or "").lower()]
        tid = hit[0]["trip_item_id"] if hit else None
    if held and (not tid or tid == held["id"]) and held["at"] < ctx.started:
        if not explicit_yes(said):
            raise _err("no_explicit_yes", "cancelling needs their explicit yes — ask them")
        await claim(ctx)
        _CANCEL.pop(ctx.account, None)
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/reservations/{held['id']}/cancel",
                                 {"read_back_sha256": held["sha"], "approval": {"how": "voice", "said": said}}, timeout=120)
        if status != 200:
            raise _err("not_cancelled", GW.refusal_words(j, status))
        if j.get("status") in ("requested", "not_confirmed"):   # Sasha 253 · G2 — "cancelled" pushed to WhatsApp on their words
            await _push_later(ctx.account, trip_item_id=held["id"], venue=GW.plain_venue(held["venue"]))
        return {"status": j.get("status"), "say": j.get("say"), "venue": held["venue"]}
    if not tid:
        raise _err("booking_unknown", "which booking? get_status lists them")
    status, j = await GW.api(ctx.account, "GET", f"/api/booking/reservations/{tid}/cancel")
    if status != 200:
        raise _err((j or {}).get("rule") or "booking_unknown", GW.refusal_words(j, status))
    _CANCEL[ctx.account] = {"id": tid, "sha": j["read_back"]["sha256"], "at": datetime.now(timezone.utc), "venue": j.get("venue")}
    return {"status": "awaiting_yes", "venue": GW.plain_venue(j.get("venue")), "route": j.get("route"), "read_back": j["read_back"]["lines"]}


__all__ = ["read_booking_route", "hold_venue", "book_venue", "cancel_venue", "venue_bookings"]
