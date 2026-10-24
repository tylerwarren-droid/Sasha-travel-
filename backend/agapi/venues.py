"""Sasha 211 Part B · REAL VENUE BOOKINGS ON THE AGENT — the EXISTING ladder (booking_signer: /venues/read, /forms, /links,
/emails, /calls, cancel), called in-process (guest_whatsapp.api) exactly as the WhatsApp guest flow calls it. No new booking
machinery: these tools only sequence it for the agent, with the same two steps as the trip's checkout.

  read_booking_route   the venue read (its routes), remembered for this account
  hold_venue           Sasha 254 · what the BOOKING RULES decided (agapi/booking_rules via agapi.booking_decide — the one decider for
                       every surface): the ONE question for a form, the read-back the yes binds to, their page, or the rules' refusal —
                       in the rules' words, with the take-over. Nothing is sent.
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
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

log = logging.getLogger("agapi.venues")

_READS: Dict[str, Dict[str, dict]] = {}   # account → venue key → the read (read_id, rungs, facts…)
_HELD: Dict[str, dict] = {}               # account → the prepared booking (route, id, sha, when it was said)
_CANCEL: Dict[str, dict] = {}             # account → the prepared cancellation
_PREPARED: Dict[str, List[dict]] = {}     # Sasha 254 · account → the pages prepared for them to book (their tap pending)
PREPARED_KIND = "prepared_pages"          # … kept in s2_memory too (the table is the truth when it answers)


# ── Sasha 254 · ONE TRUTH: a prepared page is on the record get_status reads ────────────────────────────────────────────────────
# Found live on /s2 (Hammam Al Ándalus, 29 Oct): hold_venue drew their prefilled page three times and said "It's in your bookings",
# and get_status answered "no booking or request … nothing was set up". The prepared rung wrote nothing anywhere: _finish popped
# _HELD, no trip_items row exists for it, and the outcomes ledger keeps no open entry without one. Now it is written here, and
# agapi.s2_status reads it: "prepared — waiting for you to book it on their page, not booked".

async def prepared_pages(account: Optional[str]) -> List[dict]:
    """The pages prepared for this account to book themselves (today or later): the table's when it answers, else this process's."""
    if not account:
        return []
    from agapi import s2_memory as M
    kept = await M.kind(account, PREPARED_KIND)
    rows = [dict(r) for r in kept if isinstance(r, dict)] if isinstance(kept, list) else list(_PREPARED.get(account) or [])
    today = date.today().isoformat()
    return [r for r in rows if str(r.get("date") or today) >= today]


async def note_prepared(account: str, venue: str, when: str, party: Any, url: Optional[str], link_id: Optional[str] = None) -> None:
    """A prepared page drawn for them: on the record (the same booking prepared again replaces its line, never a second one).
    Sasha 283 · item 4c: EVERY page hand-over writes this row (the copy card, and a platform's page with its booking_links id) — the
    one place the way back reads."""
    row = {"venue": venue, "date": str(when or "")[:10], "time": str(when or "")[11:16], "party": int(party or 0),
           **({"url": url} if url else {}), **({"link_id": link_id} if link_id else {}), "at": datetime.now(timezone.utc).isoformat()}
    same = lambda r: _base(r.get("venue") or "") == _base(venue) and r.get("date") == row["date"] and r.get("time") == row["time"]
    rows = ([r for r in await prepared_pages(account) if not same(r)] + [row])[-10:]
    _PREPARED[account] = rows
    from agapi import s2_memory as M
    if not await M.put_kind(account, PREPARED_KIND, rows):
        log.info("[venues] prepared page kept in this process only (no memory table)")


# ── Sasha 283 · item 4c · THE WAY BACK: a page handed over is never left hanging ───────────────────────────────────────────────────
# Tyler, 23 Oct (The India – Fleet Street): he finished on their page and had no way back, and nothing asked how it went. On his return
# to the app she asks ONE question — "Did it go through?" — unless what watches for the confirmation already knows (a platform link's
# record confirmed by its email; a confirmation found in their Gmail since): then she just says it. The answer goes on THIS row (and a
# platform link's own record: /links/{id}/booked, its word). Asked once; a hand-over older than WORD_HOURS is never asked about.
WORD_HOURS = 6
WORD_BOOKED = ("booked_by_you", "confirmed")   # the row's outcomes get_status says as booked (by him, or by its confirmation)


def _word_key(r: dict) -> str:
    return "|".join(str(r.get(k) or "") for k in ("venue", "date", "time"))


async def _put_row(account: str, key: str, **fields: Any) -> Optional[dict]:
    rows = await prepared_pages(account)
    hit = next((r for r in rows if _word_key(r) == key), None)
    if hit is None:
        return None
    hit.update(fields)
    _PREPARED[account] = rows
    from agapi import s2_memory as M
    if not await M.put_kind(account, PREPARED_KIND, rows):
        log.info("[venues] the hand-over's answer kept in this process only (no memory table)")
    return hit


async def _known(account: str, r: dict) -> Optional[str]:
    """What watches for the confirmation already knows: "confirmed" (their platform's email, on the link's record) or None."""
    try:
        if r.get("link_id"):
            from booking_signer import ladder_routes as LR
            l = await LR.LADDER_STORE.get_link(account, str(r["link_id"])) if LR.LADDER_STORE is not None else None
            if l and l.get("status") == "confirmed":
                return "confirmed"
            return None
        from booking_signer import mailbox as MB
        if MB.STORE is None:
            return None
        since = str(r.get("at") or "")
        for f in await MB.STORE.list_finds(account):
            fx = f.get("facts") or {}
            if f.get("kind") == "confirmation" and _base(str(fx.get("venue") or "")) == _base(r.get("venue") or "") \
                    and str(f.get("found_at") or "") >= since:
                return "confirmed"
    except Exception as e:   # the watcher unreadable: she asks instead (never a guess)
        log.info("[venues] confirmation not read for the way back: %s", type(e).__name__)
    return None


async def awaiting_word(account: Optional[str]) -> Optional[dict]:
    """The newest page handed over in the last WORD_HOURS with no answer yet → {key, venue, when, ask | said}; marked asked (once)."""
    if not account:
        return None
    from app.agent import voice as V
    now = datetime.now(timezone.utc)
    for r in reversed(await prepared_pages(account)):
        if r.get("asked") or r.get("outcome"):
            continue
        try:
            at = datetime.fromisoformat(str(r.get("at")))
        except ValueError:
            continue
        if now - at > timedelta(hours=WORD_HOURS):
            continue
        key = _word_key(r)
        when = " ".join(x for x in (r.get("date"), r.get("time")) if x)
        if await _known(account, r) == "confirmed":
            await _put_row(account, key, asked=now.isoformat(), outcome="confirmed")
            return {"key": key, "venue": r["venue"], "when": when, "said": V.went_through(r["venue"])}
        await _put_row(account, key, asked=now.isoformat())
        return {"key": key, "venue": r["venue"], "when": when, "ask": V.DID_IT}
    return None


async def answer_word(account: str, key: str, booked: bool, how: str = "button") -> dict:
    """His answer, on the ONE record: this row's outcome — and a platform link's own record (its /booked: on his word, never as the
    platform's confirmation). → {ok, say}."""
    from app.agent import voice as V
    rows = await prepared_pages(account)
    r = next((x for x in rows if _word_key(x) == key), None)
    if r is None:
        return {"ok": False, "say": V.WORD_GONE}
    if booked and r.get("link_id"):
        GW = _API()
        status, _j = await GW.api(account, "POST", f"/api/booking/links/{r['link_id']}/booked", {"how": how if how in ("button", "voice", "chat") else "button"})
        if status != 200:
            log.warning("[venues] the link's own record didn't take his word (%s)", status)
    await _put_row(account, key, outcome="booked_by_you" if booked else "not_yet", said_at=datetime.now(timezone.utc).isoformat(), how=how)
    return {"ok": True, "say": V.BOOKED_BY_YOU if booked else V.NOT_YET}


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
        m[c.get("place_id") or c["ref"]] = c   # Sasha 276 · an independent (venue.discover) by its ref: no listing
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
    from agapi import test_venues as TV
    a = await TV.vet(ctx, a)   # Sasha 256 · the test venue: a test person's card, never a live person's
    rd = await _read(ctx, a)
    card = card_of(ctx.account, a.get("place_id"), a.get("name"))   # Sasha 213 · the picked card is what's on screen
    if one_path(ctx):   # Sasha 251 · how it books = the ONE channel hold_venue will use (never a second reading of the same place)
        eng = await engine_channel(card or listing_card(rd), listing=True) or read_channel(rd, card, one_path=True)
        how = _how_words(eng)
        from agapi import venue_truth as VT
        dec = VT.decision(card or listing_card(rd))
        # Sasha 284 · AgAPI's ONE decision: its words, whatever the route (never NO_LINK over it) — but a call: AgAPI's call lines
        # ("only takes bookings by phone") limit the channel (rule 15, Tyler 16 Oct), so a call is her own offer (voice.CALL_IT) until
        # CR words it. Sasha 284b (live, 8 phone-only venues): the call fell through to NO_LINK — every route AgAPI found returns here.
        if dec and dec["route"] != "none":
            from app.agent import voice as V
            return {**({"card": card} if card else {}), "venue": rd["venue"], "routes": _routes_of_channel(eng) or [dec["route"]],
                    "how": V.CALL_IT if dec.get("how_far") == "call" else dec["say_text"],
                    "decision": {k: dec.get(k) for k in ("route", "say_text", "button")},
                    "open_now": rd.get("open_now"), "opens_at": rd.get("opens_at")}
        if not eng or eng.get("kind") not in OWN_FORM:   # Sasha 269 · no own form found: never "no online booking form" (voice.py)
            from agapi import venue_truth as VT
            from app.agent import voice as V
            # Sasha 270 · CR 101: their listing's reservable, said as fact in the engine's words (venue.profile reservable.say)
            # Sasha 273 · rule 15 (Tyler's demo, Periplo): never "By phone." / "By a message they answer." — the model said it as "Periplo
            # takes bookings by phone only". How they book is hers to do: voice.BOOK_IT, then the one question (the card).
            how = " ".join(x for x in (V.no_link_line(VT.reservable_say(card or listing_card(rd))), V.BOOK_IT if eng else "") if x)
        return {**({"card": card} if card else {}), "venue": rd["venue"], "routes": _routes_of_channel(eng),
                "how": how, "open_now": rd.get("open_now"), "opens_at": rd.get("opens_at")}
    return {**({"card": card} if card else {}), "venue": rd["venue"], "routes": _routes_of(rd), "how": rd.get("say"),
            "open_now": rd.get("open_now"), "opens_at": rd.get("opens_at")}


from app.agent.voice import READ_BACK_ASK   # noqa: E402 · Sasha 262 · the one read-back line lives in her voice (app/agent/voice.py)
# Sasha 263 · row 914: 262's second memory of "which booking the one question was about" (_ASKED_ROUTE) is gone — it kept item 7's
# 20:15 and the yes sent it in place of the 21:15 asked for. The one record is the read-back card (_HELD: AgAPI's read_back_id + sha).
_NOT_BOOKING = ("approval", "idempotency_key", "route")


def chosen_route(said: Optional[str]) -> Optional[str]:
    """Sasha 256 · found live (test venue, /s2): "Prefilled form" was sent as route "form" (the word "form" is in it) and became Sasha
    sending it. Their own words naming exactly ONE of the rules' options (booking_decide.CHOICES) pick its route; anything else → None."""
    import re as _re
    from agapi import booking_decide as BD
    t = " " + _re.sub(r"[^a-z]+", " ", str(said or "").lower()) + " "
    named = {o["route"] for o in BD.CHOICES + BD.CALL_CHOICES if f" {o['title'].lower()} " in t}   # Sasha 265 · + the call card's two
    if " prefilled " in t or " pre filled " in t:
        named.add("page")
    if _re.search(r" handle (it|this|that) ", t):
        named.add("form")
    return next(iter(named)) if len(named) == 1 else None


def one_path(ctx) -> bool:
    """Sasha 251 · the one path's SCHEMA and asks (under / open_slot / nights, the contact asked once, a Keep loyalty number) on /s2,
    WhatsApp's brain and /next under S1 parity; old S1 (SASHA_S1_PARITY=off) keeps its own schema byte-identical. Sasha 254 · the
    booking DECISION is the same for every surface: the booking rules (hold_venue → rules_for → agapi.booking_decide)."""
    if getattr(ctx, "surface", "s1") == "s2":
        return True
    from app.agent.sasha import s1_parity
    return s1_parity()


# Sasha's own read (booking_signer/venue_read) → the engine's channel kinds, for a place the venue engine couldn't read (no site,
# robots, a page built in the browser, another branch): the SAME channel shape, so the same question and the same executors decide
READ_KIND = {"form": "form", "own_page": "own_engine", "link": "widget", "whatsapp": "whatsapp", "email": "email", "phone": "phone",
             "instagram": "instagram"}   # their WhatsApp before email (Sasha 232: direct first)


def read_channel(rd: dict, card: Optional[dict] = None, one_path: bool = False) -> Optional[dict]:
    """Sasha 251 · the venue's ONE channel when the engine has none — from what Sasha's read found, in the engine's shape.
    Sasha 270 · one_path: never a FORM of Sasha's own reading (a form, their own page, a widget link that isn't a known platform) —
    whether a place has a booking form is the venue engine's to say (venue.profile, CR 101), else "send me the link" (voice.NO_LINK)."""
    from agapi import venue_truth as VT
    rungs = rd.get("rungs") or {}
    kinds = []
    for rung, kind in READ_KIND.items():
        if one_path and not _read_rung_kept(rung, rungs.get(rung)):
            continue
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


def _read_rung_kept(rung: str, r: Optional[dict]) -> bool:
    """Sasha 270 · on the one path, what Sasha's own read may still say: a message, a phone, a profile — and a link only when it is a
    known booking platform's (handed over, never booked). Never a form: that is the engine's."""
    if rung in ("form", "own_page"):
        return False
    if rung == "link":
        from agapi.booking_rules import booking_rules as BR
        v = str((r or {}).get("value") or "")
        return not v.startswith("http") or bool(BR.is_platform(v))
    return True


def listing_card(rd: dict) -> Optional[dict]:
    """Sasha 270 · a venue not on screen: its listing (place_id) for the venue engine — its reservable and its website, if Places has one."""
    return {"place_id": rd["place_id"], "name": rd.get("venue")} if rd.get("place_id") else None


def _routes_of_channel(eng: Optional[dict]) -> List[str]:
    if not eng:
        return []
    out = [ENGINE_ROUTE.get(eng["kind"], eng["kind"])] + ([ENGINE_ROUTE.get(eng["alternative"]["kind"], "email")] if eng.get("alternative") else [])
    return list(dict.fromkeys(out))


OWN_FORM = ("own_engine", "form", "widget")   # Sasha 269 · a booking form or page of their own (venue.profile's channel kinds)


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


ROOM = {"type": "string", "maxLength": 80,
        "description": "with `nights` only: the room they asked for, in their words ('a double', 'twin', 'a sea-view room'). Leave it out "
                       "when they didn't say"}


LINK = {"type": "string", "description": "a link to this place's booking page that THEY sent you (typed, spoken or on WhatsApp), "
                                         "exactly as sent — the venue engine says what it is and whether you can fill it in. Never a "
                                         "link you found yourself"}


def with_under(tool: dict) -> dict:
    """Sasha 251 · hold_venue's schema with `under` (the person the booking is for) — /s2 and /next under parity only.
    Sasha 253 · and `open_slot` (G7) and `nights` (G8); day and time no longer required there (API.call: required_of).
    Sasha 270 · and `link` (CR 101): a booking link the person handed over. Sasha 271 · and `room` (CR 102: a stay's room)."""
    sch = dict(tool["input_schema"])
    sch["properties"] = {**sch["properties"], "under": UNDER, "open_slot": OPEN_SLOT, "nights": NIGHTS, "room": ROOM, "link": LINK}
    sch["required"] = [k for k in sch["required"] if k not in ("day", "time")]
    return {**tool, "input_schema": sch}


def with_booking(tool: dict, hold: dict) -> dict:
    """Sasha 263 · book_venue's schema with the booking (hold_venue's fields, none required): on their answer to the one question
    ("Handle it") it reads back THIS booking by the one path; on a yes they're ignored — the yes sends only the card on their
    screen. /s2, /next under parity and WhatsApp's brain; old S1 (parity off): its schema, untouched."""
    sch = dict(tool["input_schema"])
    props = {k: v for k, v in hold["input_schema"]["properties"].items() if k != "route"}
    sch["properties"] = {**props, **sch["properties"]}
    return {**tool, "input_schema": sch, "description": tool["description"] + (
        " On their answer to the one question (\"Handle it\"), pass the booking they just asked for exactly as for hold_venue: it "
        "reads it back. On a yes, pass nothing but the approval: it sends only the card on their screen.")}


def with_act(tool: dict) -> dict:
    """Sasha 256 · cancel_venue's schema with `act_id` (the booking get_status listed, sent through AgAPI) and `reference` (the venue's
    reference they quote) — /s2, /next under parity and WhatsApp's brain. Old S1 (parity off): its schema, untouched."""
    sch = dict(tool["input_schema"])
    sch["properties"] = {**sch["properties"],
                         "act_id": {"type": "string", "description": "the booking's act_id from get_status — exactly the one they mean"},
                         "reference": {"type": "string", "description": "the venue's reference they quoted, e.g. TCO-75C655"}}
    return {**tool, "input_schema": sch}


def _which_act(acts: List[dict], *texts: Optional[str]) -> Optional[dict]:
    """Sasha 256 · the one act a quoted reference names: a reference-shaped token (TCO-75C655) found in exactly one act's venue
    words. None: nothing quoted, or it doesn't single one out."""
    import re as _re
    toks = {t.upper() for x in texts if x for t in _re.findall(r"\b[A-Za-z0-9]{2,}-[A-Za-z0-9]{3,}\b", str(x))}
    hits = [b for b in acts if toks and any(t in str((b.get("venue_said") or {}).get("untrusted_text") or "").upper() for t in toks)]
    return hits[0] if len(hits) == 1 else None


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


def _stay(ctx, a: dict) -> Optional[dict]:
    """Sasha 271 · CR 102 · the stay as venue.prepare_booking takes it — {nights, room?} (date = check-in, party = guests) — else None."""
    n = _nights(ctx, a)
    if not n:
        return None
    room = re.sub(r"\s+", " ", str(a.get("room") or "")).strip()[:80]
    return {"nights": n, **({"room": room} if room else {})}


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
    """Prepare the booking → what the booking rules decided (agapi.booking_decide → booking_rules.decide): the ONE question, the
    read-back the yes binds to, their page, or the rules' refusal — said in the rules' words with the take-over. Nothing is sent."""
    from agapi.v0 import stale
    from agapi import test_venues as TV
    a = await TV.vet(ctx, a)   # Sasha 256 · the test venue: held for a test person only — a live person's hold naming it is refused
    picked = chosen_route(ctx.user_said)
    if picked and one_path(ctx) and a.get("route") != picked:   # Sasha 256 · their words name the option: it decides, not the model
        log.info("[venues] %r names %s — the route is %s (the model sent %s)", (ctx.user_said or "")[:40], picked, picked, a.get("route"))
        a = {**a, "route": picked}
    GW = _API()
    held = _HELD.get(ctx.account)
    # Sasha 217 · THE SAME BOOKING held again (she re-holds on the yes turn): the read-back they already heard, as it is. A new hold
    # made a new form with a new sha256, so the yes was "read back first" again — and the booking looped, never sent.
    if held and held.get("out") and held["at"] < ctx.started and not stale(held["at"]) \
            and (not a.get("route") or a.get("route") == held.get("rung") or held.get("rung") == "agapi") \
            and str(held.get("when") or "")[:16] == _slot_key(ctx, a) and int(held.get("party") or 0) == int(a.get("party") or 0) \
            and ((a.get("place_id") and a.get("place_id") == held.get("place_id")) or _base(a.get("name") or "") == _base(held.get("venue") or "")) \
            and _link_of(ctx, a) in (None, held.get("link_handed")):   # Sasha 270 · a NEW link they hand over is a new booking route
        card = card_of(ctx.account, a.get("place_id") or held.get("place_id"), a.get("name"))
        # Sasha 258 · found by the scoreboard (item 15, Taverna Correo): on "Yes, send it." she re-held instead of booking; an AgAPI
        # hold's rung is "agapi" whatever channel word she passes ("email"), so it never matched — a NEW read-back, asked again.
        # Now it's the same booking; and in the turn of their yes it says so: book it now
        from agapi.v0 import yes_to_book
        if yes_to_book(ctx.user_said or ""):
            return _with_card(card, {**held["out"], "status": "yes_heard",
                                     "how": "They already heard this read-back and said yes this turn: call book_venue now. Don't ask again."})
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
    if route == "no":
        return _with_card(card, {"status": "not_booking", "venue": rd["venue"]})
    link = _link_of(ctx, a)
    if link:   # Sasha 270 · CR 101 · a link THEY handed over: the venue engine's one classifier says whose it is
        return _with_card(card, await _person_link(ctx, a, rd, res, at, now, card, link))
    # Sasha 248/251 · how it books: the venue engine's read of their own site, else Sasha's own read in the engine's shape
    path = one_path(ctx)   # Sasha 270 · the one path: their listing too (reservable); never a form of Sasha's own reading
    eng = await engine_channel(card or (listing_card(rd) if path else None), listing=path) or read_channel(rd, card, one_path=path)
    from agapi import venue_truth as VT
    dec = VT.decision(card or listing_card(rd)) if path else None
    if follows(dec, at):   # Sasha 284 · the person finishes it: handed over as AgAPI decided (its words, its button)
        return _with_card(card, await follow(ctx, a, rd, res, at, now, card, dec))
    d = await rules_for(ctx, a, rd, res, at, eng, card, route, now)
    if dec and dec["route"] != "none" and d.get("say") in REFUSED:   # Sasha 284 · Kanoe may not act here: never "can't" — AgAPI's
        return _with_card(card, await follow(ctx, a, rd, res, at, now, card, dec, refused=True))   # prepared page, theirs to finish
    return _with_card(card, await _execute(ctx, a, rd, res, at, now, d, eng, card))


# Sasha 284 · the booking rules' answers that mean "Kanoe may not act here" (access off, today's calls made, too soon, no channel of
# its own) — with AgAPI's decision naming a route, each becomes that route handed over, never a "can't"
REFUSED = ("no_real_sends", "calls_cap", "too_soon", "no_channel")


def follows(dec: Optional[dict], at: Optional[str]) -> bool:
    """Sasha 284 · AgAPI's decision is one the PERSON finishes — its button sends nothing, it is not a call, a route was found — so S2
    hands it over as decided. A message they send needs its words written by venue.prepare_booking: only with a day and a time."""
    if not dec or dec.get("route") in (None, "none") or dec.get("how_far") == "call" or (dec.get("button") or {}).get("sends"):
        return False
    return bool(at) or dec.get("how_far") != "request"


async def follow(ctx, a: dict, rd: dict, res: dict, at: Optional[str], now, card: Optional[dict], dec: dict, refused: bool = False) -> dict:
    """Sasha 284 · S2 FOLLOWS AGAPI'S DECISION (venue.profile → handoff.decide: route · say_text · button) through the ONE hand-over path
    (283): with a slot, venue.prepare_booking prepares it (nothing is sent) and its page goes to their screen and phone with the way
    back; without one, venue.profile's button as given. Either way the row the way back reads is written. Never re-decided here."""
    GW = _API()
    venue = GW.plain_venue(rd["venue"])
    link = (dec.get("button") or {}).get("link") or (card or {}).get("website")
    if at and not _open_slot(ctx, a) and link:
        held = await _prepared(ctx, a, rd, res, at, now, {"kind": "agapi", "url": link, "name": dec.get("channel")}, card)
        if held.get("status") == "awaiting_yes" and ctx.account in _HELD:
            _HELD[ctx.account]["follow"] = {"decision": dec, "refused": refused}
            out = await _finish(ctx, _HELD[ctx.account])
            out["how"] = "Say `say` exactly — never that it's booked."
            return out
    from app.agent import voice as V
    await note_prepared(ctx.account, venue, at or str(a.get("day") or "")[:10], res["how_many"]["count"], link)
    return {"status": "page_link", "venue": venue, "booked": False, "route": dec["route"], **_link_out(link),
            **({"button": {"label": V.OPEN_THEIR_PAGE if refused else (dec.get("button") or {}).get("label"), "link": link}} if link else {}),
            # Sasha 284b (live, Boys Don't Cry — a quote, no slot): nothing was prepared here, so neither AgAPI's words ("I've written it")
            # nor FINISH_IT ("your booking ready") — the plain hand-over: their way in, and the way back
            "say": (V.REACH_THEM if link else V.NO_WAY_YET) + " Say exactly that — never that it's booked."}


_URL = re.compile(r"https?://[^\s<>\"'`]+", re.I)


def _link_of(ctx, a: dict) -> Optional[str]:
    """Sasha 270 · the booking link THEY handed over — hold_venue's `link`, else one in their own words this turn (a model that forgot
    to pass it never loses it). The one path only; old S1 has no link."""
    if not one_path(ctx):
        return None
    for v in (str(a.get("link") or "").strip(), *(_URL.findall(getattr(ctx, "user_said", None) or "")[:1])):
        m = _URL.match(v)
        if m:
            return m.group(0).rstrip(".,;:!?)]}")[:500]
    return None


async def _person_link(ctx, a: dict, rd: dict, res: dict, at: str, now, card: Optional[dict], link: str) -> dict:
    """Sasha 270 · CR 101 · A LINK THE PERSON HANDED OVER, through the ONE classifier and the ONE ladder (never loaded by Sasha):
    venue.profile link {url} (+ their place_id and website) → channels[].owner —
      kanoe       → the booking rules (preference: handle it) → venue.prepare_booking on THAT link → the read-back → ONE yes →
                    venue.submit_booking → booking_status (get_status), exactly as a form on their own site
      the person  → their link handed to them, with what it is in her words (voice.link_line): a sign-in, a CAPTCHA, a platform"""
    from agapi import venue_truth as VT
    from app.agent import voice as V
    GW = _API()
    venue = GW.plain_venue(rd["venue"])
    place = {"name": (card or {}).get("name") or venue, "place_id": rd.get("place_id") or (card or {}).get("place_id"),
             "website": (card or {}).get("website") or a.get("website")}
    got = await VT.link_profile(place, link)
    ch = (got.get("channel") if got.get("ok") else None) or {"kind": "cant_read", "owner": "the person", "url": link}
    log.info("[venues] %s: their link is %s (owner %s)", venue, ch.get("kind"), ch.get("owner"))
    if ch.get("owner") == "kanoe" and at and not _nights(ctx, a) and not _open_slot(ctx, a):
        d = await rules_for(ctx, a, rd, res, at, {"kind": "form", "url": link, "from": "person"}, card, "form", now)
        if d["action"] == "fill_form_zero_touch":
            out = await _via_agapi(ctx, a, rd, res, at, now, d, card, link=link)
            if out is not None:
                if out.get("ask"):   # short: "OK, I'm on it." then the read-back's one question (the card carries the detail)
                    out["ask"] = f"{V.LINK_ON_IT} {out['ask']}"
                    if _HELD.get(ctx.account):
                        _HELD[ctx.account]["out"] = {**_HELD[ctx.account].get("out", {}), "ask": out["ask"]}
                return out
        # the rules didn't let Sasha send it (test mode for a real venue, sends off, …): their link, with the rules' words
        return _said({"status": "page_link", "venue": venue, "booked": False, "link_kind": ch.get("kind"), **_link_out(link)},
                     {**d, "takeover": {**d["takeover"], "link": link}})
    return {"status": "page_link", "venue": venue, "booked": False, "link_kind": ch.get("kind"), **_link_out(link),
            "say": V.link_line(ch), "how": "Say `say` exactly — their link is on their screen; never that it's booked."}


async def rules_for(ctx, a: dict, rd: dict, res: dict, at: str, eng: Optional[dict], card: Optional[dict], route: Optional[str],
                    now: Optional[datetime] = None) -> dict:
    """Sasha 254 · ONE DECIDER: this booking's Decision from the booking rules (agapi.booking_decide), with the channels it read."""
    from agapi import booking_decide as BD
    chans = BD.channels_of(eng if eng and eng.get("from") != "read" else None, rd, card, one_path=one_path(ctx))
    if _open_slot(ctx, a) or (res.get("when") or {}).get("mode") == "venue_proposes":
        # Sasha 253 · G7 — no slot: a form or a platform books a SLOT, so for this booking only the request channels exist
        chans = [c for c in chans if c["kind"] not in ("form", "platform")]
    phone = str(((rd.get("rungs") or {}).get("phone") or {}).get("value") or "") or None
    test = BD.is_test_venue(rd, card)
    if test and (card or {}).get("phone") and not any(c["kind"] == "phone" for c in chans):
        chans = chans + [{"kind": "phone", "value": card["phone"]}]   # Sasha 265 · a Kanoe test venue's own (sandbox) number
        phone = phone or card["phone"]
    when = at or (f"{str(a.get('day'))[:10]}T12:00" if _open_slot(ctx, a) and a.get("day") else None)
    country = rd.get("country") or a.get("country")
    path = one_path(ctx)
    d = await BD.decide_for(ctx.account, channels=chans, vtype=BD.venue_type((res.get("what") or {}).get("category"), _nights(ctx, a)),
                            test=test, local_at=when, country=country,
                            preference=route, venue_key=f"read:{rd.get('read_id')}", number=phone if phone and phone.startswith("+") else None,
                            link=BD.page_of(chans, card), now=now,
                            # Sasha 265 · item 4 (booking-rules/2): the ONE question's words, local, and when they open
                            booking=BD.booking_words(_API().plain_venue(rd["venue"]), (res.get("how_many") or {}).get("count"), at or None,
                                                     country, now) if path else None,
                            opening=opening_of(rd, card, now, country) if path else None, sandbox_calls=path)
    if not path:   # Sasha 265 · old S1 (parity off): booking-rules/1's answers, byte-identical
        d = BD.as_v1(d)
    return {**d, "channels": chans, **({"phone": phone} if phone else {})}


def opening_of(rd: dict, card: Optional[dict], now: Optional[datetime], country: Optional[str]) -> Optional[dict]:
    """Sasha 265 · item 4 · when the venue can be called: {opens_at "HH:MM" (their next opening, local), open_now} from the hours the read
    holds (their site first, then Google: booking_signer.hours), or a Kanoe test venue's own week. None: no hours known (then "now")."""
    try:
        from booking_signer import hours as H, venue_read as V
        tz = (V.COUNTRIES.get(str(country or "").upper()) or (None, None, None, "Europe/Madrid"))[3]
        read = rd
        if (card or {}).get("week"):
            read = {"facts": [{"kind": "hours", "source_kind": "site", "source_label": "their page", "evidence": {"week": card["week"]}}]}
        st = H.status(read, now or datetime.now(timezone.utc), tz)
        if not st.get("known"):
            return None
        return {"open_now": bool(st.get("open_now")), **({"opens_at": str(st["opens_at"])[11:16]} if st.get("opens_at") else {})}
    except Exception as e:
        log.info("[venues] no opening hours read: %s", type(e).__name__)
        return None


def _rules(d: dict) -> dict:
    from agapi import booking_decide as BD
    return BD.out_of(d)


def _said(out: dict, d: dict, *, when: str = "now", account: Optional[str] = None) -> dict:
    """Every answer carries the rules' words and the take-over (R11). `when`: "now" — she says it with this result; "after_yes" —
    the read-back comes first, and the rules' words follow the send (kept on the hold: book_venue says them)."""
    from agapi import booking_decide as BD
    out["rules"] = _rules(d)
    out["takeover"] = d["takeover"]
    if when == "now":
        out["say"] = BD.say(d) if not out.get("say") else f"{out['say']} {d['takeover']['say']}"
    elif account and account in _HELD and out.get("status") in ("awaiting_yes", "yes_heard"):
        _HELD[account]["rules_say"] = BD.say(d)
        _HELD[account]["out"] = {**_HELD[account].get("out", {}), "rules": out["rules"], "takeover": out["takeover"]}
    return out


async def _execute(ctx, a: dict, rd: dict, res: dict, at: str, now, d: dict, eng: Optional[dict], card: Optional[dict]) -> dict:
    """Sasha 254 · the executors run EXACTLY the action decide() returned — nothing chooses here."""
    from agapi import booking_decide as BD
    GW = _API()
    action, key = d["action"], d["say"]
    rungs = rd.get("rungs") or {}
    nights, open_slot = _nights(ctx, a), _open_slot(ctx, a)
    venue = GW.plain_venue(rd["venue"])
    kinds = {c["kind"] for c in d.get("channels") or []}
    if one_path(ctx) and action == "call_and_email" and "email" in rungs:
        # Sasha 269 · R6 (CR 100): the email is the act. Sasha 271 · CR 102: a hotel stay is an act too — and the call that goes with
        # the email is the ENGINE's (venue.submit_booking returns its call_plan R6 under the same yes); Sasha dials only that plan
        if at and not open_slot:
            got = await _via_agapi(ctx, a, rd, res, at, now, d, card, **({"stay": _stay(ctx, a)} if nights else {}))
            if got is not None:
                return got
        if nights:   # no booking service here: a stay is never Sasha's own email (its call would be nobody's)
            return await _no_engine(ctx, rd, d, venue)
        return _said(await _email(ctx, a, rd, res, at, d), d, when="after_yes", account=ctx.account)
    if one_path(ctx) and (key == "ask_page_or_call" or action in ("ask_call", "call", "call_and_email", "wait")):
        # Sasha 265 · item 4 (CR 99, booking-rules/2): a call is an ACT — the ONE question is its read-back, on a card. Sasha 269: every
        # call (R3's wait and R6's call too) is the act's — Sasha's own call (/api/booking/calls, never placed without an act) is not used
        if action == "wait" and not _wait_until(d):
            return _said({"status": "need_day", "venue": rd["venue"],
                          "how": "There's no day to call closer to: ask them which day (one short question), then hold_venue again."}, d)
        if not at or open_slot:   # the act books a day and a time: no slot, no call of Sasha's own — their page, or said
            return await _no_call(ctx, a, rd, res, at, now, d, card, venue, "a call needs a day and a time to ask them for")
        # Sasha 271 · CR 102: a stay's call is the same act, with the stay (its check-in, nights, room) — never a call of Sasha's own
        return await _call_question(ctx, a, rd, res, at, now, d, card)
    if action == "ask_one_question":   # R2 · the ONE question, word for word (voice.ASK_BOOK is this phrase)
        return _said({"status": "choose_route", "venue": rd["venue"], "ask": d["say_text"],
                      "options": [dict(o) for o in BD.CHOICES],
                      "how": "Say `say` word for word, then hold_venue again with the route they chose (Prefilled form → page; "
                             "Handle it → form)."}, d)
    if action in ("fill_form_zero_touch", "request_email", "request_whatsapp") and one_path(ctx) and at and not open_slot \
            and not (nights and action == "fill_form_zero_touch"):
        # Sasha 254 · item 3 — "I'll handle it", LIVE: AgAPI sends it (venue.prepare_booking → the read-back → on their yes,
        # venue.submit_booking). Sasha's own senders stay only where it doesn't reach: no AgAPI key on this server (below), a
        # request with no slot (G7), a call, and old S1. Sasha 271 · CR 102: a hotel stay's request is the engine's act too (its
        # R5 call, when the rules say, comes from booking_status.follow_up); a hotel's own booking engine stays their page
        got = await _via_agapi(ctx, a, rd, res, at, now, d, card, **({"stay": _stay(ctx, a)} if nights else {}))
        if got is not None:
            return got
        if nights:   # no booking service here: never Sasha's own room email for a stay
            return await _no_engine(ctx, rd, d, venue)
    if action == "fill_form_zero_touch":   # R2 · "handle it": the form, filled and sent on their yes
        if "form" in rungs and not one_path(ctx):   # Sasha 270 · Sasha's own form reading/sender: old S1 only
            return _said(await _form(ctx, a, rd, res), d, when="after_yes", account=ctx.account)
        # the venue engine's form (no form in Sasha's own read): Sasha can't submit it from here yet — their page, prepared, and said so
        return await _prepared_now(ctx, a, rd, res, at, now, eng, card, BD.redecide(d, "page"))
    if action == "prepared_link":
        if key in ("prepared_link", "prepared_link_captcha") and nights and ({"link", "own_page"} & set(rungs)):
            return _said(await _page(ctx, a, rd, res, at), d)   # a hotel's own engine with the stay in its link (G8)
        if key == "prepared_link_captcha" and "form" in rungs and not one_path(ctx) and (await _founder(ctx)):
            got = await _form(ctx, a, rd, res, handover=True)   # R13 · Sasha fills the rest; the CAPTCHA is theirs (Tap to finish)
            if got.get("status") == "awaiting_yes":
                return _said(got, d)
        return await _prepared_now(ctx, a, rd, res, at, now, eng, card, d)
    if action == "hand_over_platform_link":   # R14 · their page, handed over — never booked on a platform
        if {"link", "own_page"} & set(rungs) and not open_slot:
            got = await _page(ctx, a, rd, res, at)
            from agapi import venue_submit as VS
            if one_path(ctx) and VS.TAP.get() is not None and got.get("status") == "awaiting_yes" and ctx.account in _HELD:
                # Sasha 264 · item 8 (row 929, Ichikani Madrid): on a platform SHE never sends — so no "Shall I send this?", no read-back
                # card, no forwarding address: their page at once, ONE line + ONE button (the hand-over card), said by code
                out = _said(await _finish(ctx, _HELD[ctx.account]), d)
                line = out.get("page_says") or ""
                out["rules"] = {**out["rules"], "say": line}   # the rules' words for it ARE this line (never a second, longer one)
                out["say"] = f"{line} Say exactly that."
                return out
            return _said(got, d)
        url = d["takeover"].get("link") or next((c.get("url") for c in d.get("channels") or [] if c["kind"] == "platform" and c.get("url")), None)
        return _said({"status": "page_link", "venue": venue, "booked": False, **_link_out(url)}, d)
    if action == "request_email":
        if "email" not in rungs:
            raise _err("no_route", f"{venue}'s email isn't in what I read of them — " + BD.say(d))
        return _said(await _email(ctx, a, rd, res, at, d), d, when="after_yes", account=ctx.account)
    if action == "request_whatsapp":
        if eng and eng.get("from") != "read" and eng.get("kind") == "whatsapp":
            held = await _prepared(ctx, a, rd, res, at, now, eng, card)   # a prepared WhatsApp THEY send (venue.prepare_booking)
            return _said(held, d, when="after_yes")
        return _said(_draft(ctx, a, rd, res, at, now, "whatsapp"), d, when="after_yes")
    if action == "wait":   # R3 · a phone only, more than 48 h away: no call now — a call closer to the day, on their yes
        due = _wait_until(d)
        if not due:
            return _said({"status": "need_day", "venue": rd["venue"],
                          "how": "There's no day to call closer to: ask them which day (one short question), then hold_venue again."}, d)
        got = await _call(ctx, a, rd, res, extra={"scheduled_for": due})
        got["what_happens"] = "on their yes, Sasha calls them closer to the day (it's scheduled); booked only if they say yes on the call"
        out = _said(got, d)
        if one_path(ctx):   # Sasha 273 · rule 15: the rules' R3 words without "their only way to book is by phone" (voice.WAIT_TO_CALL)
            from agapi.booking_rules import booking_rules as BR
            from app.agent import voice as V
            for o in (out, out.get("rules") or {}):
                if isinstance(o.get("say"), str):
                    o["say"] = o["say"].replace(BR.PHRASES["wait_to_call"], V.WAIT_TO_CALL)
        return out
    if action in ("call", "call_and_email"):
        if action == "call_and_email" and "email" in rungs:   # R6 · the call AND the email at once: one read-back, one yes
            return _said(await _call_and_email(ctx, a, rd, res, at, d), d)
        return _said(await _call(ctx, a, rd, res), d, when="after_yes", account=ctx.account)
    # refuse (and anything the rules add later): said, nothing prepared
    return _said({"status": "refused", "venue": venue}, d)


async def _call_question(ctx, a: dict, rd: dict, res: dict, at: str, now, d: dict, card: Optional[dict]) -> dict:
    """Sasha 265 · item 4 (CR 99 §4b) · THE ONE QUESTION IS THE CARD. venue.prepare_booking with the venue's call {phone, opens_at,
    open_now}, then venue.submit_booking route "call" → the call's read-back (read_back_id + its sha). The card: ask_page_or_call → TWO
    buttons ("Fill in their page": their prepared page, nothing sent, no approval · "Call them": the tap IS the approval); ask_call → ONE
    "OK". Answered already in words ("call them" — on_it) with this card on screen: that answer is the approval (the held read-back)."""
    from agapi import booking_decide as BD, venue_submit as VS
    from booking_signer import guest_receipt as GR
    GW = _API()
    venue = GW.plain_venue(rd["venue"])
    held = _HELD.get(ctx.account) or _PREV.get(ctx.account)   # hold_venue set the card aside (_PREV) before deciding again
    if d["say"] == "on_it" and held and held.get("rung") == "agapi_call" and held["at"] < ctx.started \
            and _base(held.get("venue") or "") == _base(rd["venue"]):   # their words answered the card: the call act, now
        _PREV.pop(ctx.account, None)
        return await _finish(ctx, held, {"how": "words", "said": (ctx.user_said or "")[:200]})
    place = {"name": (card or {}).get("name") or venue, "website": (card or {}).get("website") or a.get("website"),
             "place_id": rd.get("place_id") or (card or {}).get("place_id"), "city": a.get("city"), "category": (res.get("what") or {}).get("category")}
    v = (d.get("ctx") or {}).get("venue") or {}
    call = call_of(rd, card, place.get("place_id"))   # Sasha 272 · CR 103: once, here — a listing as its place_id, never its number
    if not call:
        return await _no_call(ctx, a, rd, res, at, now, d, card, venue, "there's no number for them to call")
    call = {**call, **({"opens_at": v["opens_at"]} if v.get("opens_at") else {}), "open_now": bool(v.get("open_now"))}
    person = {"name": res["who"]["name"], "phone": res["who"]["contact"].get("mobile_e164"), "email": await GR.address_of(ctx.account)}
    p = await VS.prepare(ctx.account, place, person, at[:10], at[11:16], int(res["how_many"]["count"]), call=call,
                         **({"stay": _stay(ctx, a)} if _stay(ctx, a) else {}))   # Sasha 271 · CR 102: a stay's call says the stay
    if not p.get("ok") and p["error"]["code"] == "not_configured":   # no venues key on this server: no act — so no call (never the old path)
        return await _no_call(ctx, a, rd, res, at, now, d, card, venue, "calls go through the booking service, which isn't on here")
    if not p.get("ok"):
        raise _err("not_prepared", f"{venue} couldn't be prepared from here right now — {p['error']['message']}. " + d["takeover"]["say"])
    rb = await VS.read_back(ctx.account, p["prepared_id"], route="call")
    if not rb.get("ok"):
        if rb["error"]["code"] == "not_allowed":
            link = next((x for x in (rb["error"].get("details", {}).get("link"), p.get("link"), d["takeover"].get("link"))
                         if str(x or "").startswith("https://")), None)
            return _said({"status": "not_contacted", "venue": venue, "booked": False, "not_allowed": True, "say": rb["error"]["message"],
                          **_link_out(link)}, d)
        raise _err("not_prepared", f"{venue} couldn't be prepared from here right now — {rb['error']['message']}. " + d["takeover"]["say"])
    choices = [dict(o) for o in (BD.CALL_CHOICES if d["say"] == "ask_page_or_call" else BD.OK_CHOICES)]
    ask = d["say_text"] if d["say"] != "on_it" else BR_ask_call(d)
    link = p.get("link") if str(p.get("link") or "").startswith("https://") else d["takeover"].get("link")
    out = _hold(ctx, "agapi_call", p["prepared_id"], {"lines": rb["lines"], "sha256": rb["sha256"]}, rd, res,
                extra={"prepared_id": p["prepared_id"], "read_back_id": rb["read_back_id"], "end_user": rb["end_user"], "link": link,
                       "call": call, "lines": rb["lines"], "name": res["who"]["name"], "place_id": place.get("place_id"),
                       "booking": {k: v for k, v in a.items() if k not in _NOT_BOOKING}})
    out.update(ask=ask, choices=choices, read_back_id=rb["read_back_id"],
               how="Say `ask` word for word — it IS the card's question; their tap on the card is the approval. Never ask a second "
                   "yes, never read the card out.")
    if _HELD.get(ctx.account):
        _HELD[ctx.account]["out"] = {**_HELD[ctx.account].get("out", {}), "ask": ask, "choices": choices, "read_back_id": rb["read_back_id"]}
    return _said(out, d, when="after_yes", account=ctx.account)


def own_number(rd: dict, card: Optional[dict] = None) -> Optional[str]:
    """Sasha 265 · item 4 · the number the call ACT may carry (AgAPI keeps it, and Bland dials it): the venue's OWN published number, read
    on their own site — or a Kanoe test venue's sandbox number. A Google listing's is never Sasha's to pass (Sasha 272: call_of)."""
    if BD_is_test(rd, card) and str((card or {}).get("phone") or "").startswith("+"):
        return card["phone"]
    v = str((((rd.get("rungs") or {}).get("phone") or {}).get("value")) or "")
    facts = [f for f in rd.get("facts") or [] if f.get("kind") == "phone" and str(f.get("value") or "").startswith("+")]
    site = next((f["value"] for f in facts if f.get("source_kind") == "site"), None)
    if site:
        return site
    return v if v.startswith("+") and not facts else None


def listed(rd: dict) -> bool:
    """Sasha 272 · their Google listing shows a number in this read (what the place card shows) — whether to hand the booking their
    listing. Its digits are never taken from here: AgAPI reads the number fresh from the listing for each call (CR 103, row 942)."""
    return any(f.get("kind") == "phone" and f.get("source_kind") == "places" and str(f.get("value") or "").startswith("+")
               for f in rd.get("facts") or [])


def call_of(rd: dict, card: Optional[dict], place_id: Optional[str]) -> Optional[dict]:
    """Sasha 272 · CR 103 · the ONE call object, given ONCE at venue.prepare_booking (never again at submit_booking or call_again — the
    booking record is the truth): the venue's own number {phone, source "venue"}, or their listing {source "listing", place_id} with NO
    phone. None: no number to call."""
    own = own_number(rd, card)
    if own:
        return {"phone": own, "source": "venue"}
    if place_id and listed(rd):
        return {"source": "listing", "place_id": place_id}
    return None


def BD_is_test(rd: dict, card: Optional[dict]) -> bool:   # noqa: N802
    from agapi import booking_decide as BD
    return BD.is_test_venue(rd, card)


async def _no_call(ctx, a: dict, rd: dict, res: dict, at: str, now, d: dict, card: Optional[dict], venue: str, why: str) -> dict:
    """Sasha 265 · item 4 · a call the act can't make (why): their page when they have one (the card's other answer) — else said plainly,
    with the take-over. Never Sasha's own call (no act, never dialled)."""
    from agapi import booking_decide as BD
    if d["say"] == "ask_page_or_call" or BD.page_of(d.get("channels") or [], card):
        eng = await engine_channel(card or listing_card(rd), listing=True) or read_channel(rd, card, one_path=True)
        return await _prepared_now(ctx, a, rd, res, at, now, eng, card, BD.redecide(d, "page"))
    raise _err("no_route", f"{venue} books by phone, and I can't call them from here — {why}. " + d["takeover"]["say"])


def BR_ask_call(d: dict) -> str:   # noqa: N802 · their words asked for the call with no card yet: the call's own question (the OK card)
    from agapi.booking_rules import booking_rules as BR
    v = (d.get("ctx") or {}).get("venue") or {}
    head = BR.head(d.get("ctx") or {})
    return (BR.PHRASES["ask_call_when_open"].format(opens_at=v["opens_at"]) if v.get("opens_at") and not v.get("open_now")
            else BR.PHRASES["ask_call_now"].format(head=head))


async def answer_card(ctx, read_back_id: str, choice: str) -> dict:
    """Sasha 265 · item 4 · THE TAP: the card's button, straight from the page (no model between). "call" → the tap IS the approval
    (approvals.in_app_tap on THIS read-back) → the act → "On it — …". "page" → their prepared page (nothing sent, no approval)."""
    held = _HELD.get(ctx.account)
    if not held or held.get("rung") != "agapi_call" or held.get("read_back_id") != read_back_id:
        return {"status": "nothing_waiting", "booked": False, "in_app": True}
    if choice == "page":
        return await hold_venue(ctx, {**(held.get("booking") or {}), "route": "page"})
    return await _finish(ctx, held, {"how": "tap", "said": "tap: " + ("Call them" if choice == "call" else "OK")})


# the booking rules' action → what the outcomes ledger records for an AgAPI send (CR 87's rung + channel)
AGAPI_RUNG = {"fill_form_zero_touch": ("zero_touch", "web_form"), "request_email": ("request_reply", "email"),
              "request_whatsapp": ("request_reply", "whatsapp")}


async def _via_agapi(ctx, a: dict, rd: dict, res: dict, at: str, now, d: dict, card: Optional[dict], link: Optional[str] = None,
                     stay: Optional[dict] = None) -> Optional[dict]:
    """The AgAPI send, read back first. None: this server has no venues key (then Sasha's own sender, as before).
    Sasha 270 · link: the booking link the person handed over (CR 101) — prepared on THAT form, by the same ladder.
    Sasha 271 · stay (CR 102): a hotel stay, with the venue's number for the calls the booking rules attach (R6 with the send, R5 when
    booking_status says it's due) — the engine's, under this same yes; Sasha keeps no time of its own for them."""
    from agapi import venue_submit as VS
    from booking_signer import guest_receipt as GR
    GW = _API()
    venue = GW.plain_venue(rd["venue"])
    place = {"name": (card or {}).get("name") or venue, "website": (card or {}).get("website") or a.get("website"), "place_id": rd.get("place_id") or (card or {}).get("place_id"),
             "city": a.get("city"), "category": (res.get("what") or {}).get("category")}
    person = {"name": res["who"]["name"], "phone": res["who"]["contact"].get("mobile_e164"), "email": await GR.address_of(ctx.account)}
    asked = _what(a)
    # Sasha 272 · CR 103 · the stay's number for the engine's R5/R6 calls: given ONCE here (a listing as its place_id), kept by the record
    call = call_of(rd, card, place.get("place_id")) if stay else None
    p = await VS.prepare(ctx.account, place, person, at[:10], at[11:16], int(res["how_many"]["count"]),
                         notes=None if stay else asked if asked.lower() not in ("a table", "table", "dinner", "lunch") else None,
                         **({"link": link} if link else {}), **({"stay": stay} if stay else {}), **({"call": call} if call else {}))
    if not p.get("ok") and p["error"]["code"] == "not_configured":
        log.info("[venues] no venues key here: Sasha's own sender for %s", d["action"])
        return None
    if not p.get("ok"):
        raise _err("not_prepared", f"{venue} couldn't be prepared from here right now — {p['error']['message']}. " + d["takeover"]["say"])
    rb = await VS.read_back(ctx.account, p["prepared_id"])
    if not rb.get("ok") and rb["error"]["code"] == "not_allowed":
        # Sasha 254 · not allowed to contact venues (not granted): said kindly, with their page prepared — never an error
        from agapi.booking_rules import booking_rules as BR
        link = next((x for x in (rb["error"].get("details", {}).get("link"), p.get("link"), d["takeover"].get("link"))
                     if str(x or "").startswith("https://")), None)
        d2 = {**d, "action": "prepared_link", "say": "no_real_sends", "say_text": BR.PHRASES["no_real_sends"],
              "takeover": {**d["takeover"], "link": link}}
        return _said({"status": "not_contacted", "venue": venue, "booked": False, "not_allowed": True, **_link_out(link)}, d2)
    if not rb.get("ok"):
        raise _err("not_prepared", f"{venue} couldn't be prepared from here right now — {rb['error']['message']}. " + d["takeover"]["say"])
    link = p.get("link") if str(p.get("link") or "").startswith("https://") else d["takeover"].get("link")
    out = _hold(ctx, "agapi", p["prepared_id"], {"lines": rb["lines"], "sha256": rb["sha256"]}, rd, res,
                extra={"prepared_id": p["prepared_id"], "read_back_id": rb["read_back_id"], "end_user": rb["end_user"], "link": link,
                       "agapi_action": d["action"], **({"call_source": call["source"], **({"place_id": call["place_id"]} if call.get("place_id") else {})}
                                                       if call else {}),   # its source (and a listing's place_id) only, never a number
                       **({"link_handed": link} if link else {}), **({"stay": stay} if stay else {}),
                       "category": (res.get("what") or {}).get("category")})
    out["what_happens"] = ("on their yes, Sasha sends it to the venue; it's booked only when they confirm"
                           + (" — their own phone gets a tap to approve it first" if await VS.target(ctx.account) == "live" else ""))
    return _said(out, d, when="after_yes", account=ctx.account)


async def _no_engine(ctx, rd: dict, d: dict, venue: str) -> dict:
    """Sasha 271 · a hotel stay with no booking service on this server: said, with the take-over — never Sasha's own room email (the
    call the rules attach to it would be nobody's)."""
    raise _err("no_route", f"I can't ask {venue} for the room from here right now. " + d["takeover"]["say"])


def _wait_until(d: dict) -> Optional[str]:
    """R3's follow-up: the call is due when the booking comes within the rules' threshold (`before_hours`), never before now."""
    at = (d.get("ctx") or {}).get("when", {}).get("booking_at")
    fu = next((f for f in d.get("follow_ups") or [] if f.get("action") == "call" and f.get("before_hours")), None)
    if not at or not fu:
        return None
    due = datetime.fromisoformat(str(at).replace("Z", "+00:00")) - timedelta(hours=float(fu["before_hours"]))
    return due.astimezone(timezone.utc).isoformat()


async def _founder(ctx) -> bool:
    from booking_signer import guest_accounts as GA
    return bool(GA.founder(ctx.account))


async def _prepared_now(ctx, a: dict, rd: dict, res: dict, at: str, now, eng: Optional[dict], card: Optional[dict], d: dict) -> dict:
    """prepared_link (the person's choice, a CAPTCHA, or one of the rules' refusals): their own page, prefilled, on their screen at
    once — nothing reaches the venue (Sasha 249: the prefilled form IS their go-ahead). No page to prepare: the rules' words and the
    take-over link."""
    from agapi import venue_truth as VT
    GW = _API()
    fillable = eng and (eng.get("kind") in VT.FILLABLE) and (eng.get("url") or (card or {}).get("website"))
    if fillable and at and not _open_slot(ctx, a):
        held = await _prepared(ctx, a, rd, res, at, now, eng, card)
        if held.get("status") == "awaiting_yes" and ctx.account in _HELD:
            out = await _finish(ctx, _HELD[ctx.account])
            out.pop("say", None)   # the rules' words for it (prepared_link / its CAPTCHA / the refusal), never a second line
            out = _said(out, d)
            if (out.get("prepared") or {}).get("filled") is False:   # Sasha 264 · item 2: "filled in for you" only when it IS — the
                from app.agent import voice as V                      # rules' words for it too (a CAPTCHA's reason kept)
                line = V.not_filled_line(d.get("say") == "prepared_link_captcha")
                out["rules"] = {**out["rules"], "say": line}
                out["say"] = f"{line} {d['takeover']['say']}"
            out["how"] = "Say `say` exactly — never that it's booked."
            return out
    link = d["takeover"].get("link")
    out = _said({"status": "not_contacted", "venue": GW.plain_venue(rd["venue"]), "booked": False, **_link_out(link)}, d)
    if one_path(ctx) and d.get("say") == "no_channel":   # Sasha 270 · no way found: "send me their link" (+ reservable), never "no form"
        from app.agent import voice as V
        line = V.no_link_line(VT.reservable_say(card or listing_card(rd)))
        out["rules"] = {**out["rules"], "say": line}
        out["say"] = f"{line} {d['takeover']['say']}"
    return out


def _link_out(link: Optional[str]) -> dict:
    """The take-over link, drawn on their screen (the hand-over card) — or, when there is none, said plainly: never a page that
    isn't there (the rules' phrase offers "their page")."""
    if link:
        return {"open": link, "page_url": link}
    return {"no_page": "there is no page of theirs to give — say you can't contact them from here and that they can take it over; "
                       "never say a page is on their screen"}


async def _form(ctx, a: dict, rd: dict, res: dict, handover: bool = False) -> dict:
    """Their own form (Sasha's read): filled, read back; on the yes, sent (the founder's override: the cloud browser, a human step
    to the phone as Tap to finish)."""
    from booking_signer import guest_accounts as GA, guest_receipt as GR
    GW = _API()
    email = await GR.address_of(ctx.account)
    rf = {**res, "who": {**res["who"], "contact": {**res["who"]["contact"], **({"email": email} if email else {})}}}
    ly = await _loyalty(ctx, rd, res)   # Sasha 253 · G14 — a matching loyalty number from the Keep, under this yes
    status, j, rung = 0, {}, "form"
    if not handover:
        status, j = await GW.api(ctx.account, "POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": rf,
                                                                             **({"loyalty_item_id": str(ly["id"])} if ly else {})})
    if handover or (status != 200 and GA.founder(ctx.account)):   # the founder's override: the cloud browser fills it
        status, j = await GW.api(ctx.account, "POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": rf, "handover": True})
        rung = "handover"
    if status == 200:
        return _hold(ctx, rung, j["form_id"], j["read_back"], rd, res, extra={"trip_item_id": j.get("trip_item_id")})
    raise _err("no_route", f"{GW.plain_venue(rd['venue'])} can't be booked from here right now — {GW.refusal_words(j, status)}")


async def _page(ctx, a: dict, rd: dict, res: dict, at: str) -> dict:
    """Their booking page (a platform's, or their own engine with a hotel stay in the link): read back; on the yes, to their phone."""
    GW = _API()
    nights = _nights(ctx, a)
    status, j = await GW.api(ctx.account, "POST", "/api/booking/links", {
        "read_id": rd["read_id"], "date": at[:10], "time": at[11:16], "party": res["how_many"]["count"], "name": res["who"]["name"],
        "venue": GW.plain_venue(rd["venue"])[:120],
        # Sasha 233 · /s2: the service asked for, so a Fresha/Treatwell/Booksy page's matching service + price is read back
        **({"asked_for": _what(a)} if getattr(ctx, "surface", "s1") == "s2" and not nights else {}),
        **({"nights": nights} if nights else {})})   # Sasha 253 · G8 — the stay in their engine's link (slot_link.build_hotel)
    if status != 200:
        raise _err("no_route", f"{GW.plain_venue(rd['venue'])}'s page can't be prepared right now — {GW.refusal_words(j, status)}")
    return _hold(ctx, "page", j["link_id"], j["read_back"], rd, res,
                 extra={"url": j["url"], "platform": j.get("platform"), "slot_filled": bool(j.get("slot_filled")),
                        "trip_item_id": j.get("trip_item_id"),
                        **({"nights": nights, "hotel_text": GW.hotel_link_text(GW.plain_venue(rd["venue"]), j)} if nights else {})})


def _plan(d: dict, rd: dict) -> Optional[str]:
    """R5 · the rules' own follow-up (a hotel that hasn't answered in 24 h → a call), said in the read-back so the ONE yes covers it
    (escalation.plan_line: the server verifies it before the call is placed). Only when they have a phone to call."""
    from booking_signer import escalation as ESC
    fu = next((f for f in d.get("follow_ups") or [] if f.get("action") == "call" and f.get("after_hours")), None)
    if not fu or "phone" not in (rd.get("rungs") or {}):
        return None
    return ESC.plan_line(f"If they haven't replied within {int(fu['after_hours'])} hours, I'll call them", None)


async def _email(ctx, a: dict, rd: dict, res: dict, at: str, d: dict) -> dict:
    """The request by email (a room for N nights; a date and a quote when there's no slot): read back; on the yes, sent."""
    from booking_signer import guest_receipt as GR
    GW = _API()
    nights, open_slot = _nights(ctx, a), _open_slot(ctx, a)
    venue = GW.plain_venue(rd["venue"])
    mine = await GR.address_of(ctx.account)
    plan = _plan(d, rd)
    if open_slot or (res.get("when") or {}).get("mode") == "venue_proposes":   # Sasha 253 · G7 — the old flow's quote email
        day = str(a.get("day") or "")[:10]
        try:
            day = date.fromisoformat(day).isoformat()
        except ValueError:
            day = ""
        body = GW.quote_email(rd["read_id"], res["who"]["name"], mine, _what(a), day or None)
        extra = {"open_slot": a.get("open_slot"), "say": GW.quote_sentence(venue, day or None)}
    else:
        body = {"read_id": rd["read_id"], "date": at[:10], "time": at[11:16], "party": res["how_many"]["count"], "name": res["who"]["name"],
                "email": mine or "", **({"nights": nights} if nights else {})}   # Sasha 253 · G8 — the room email (N nights)
        extra = {"nights": nights, "say": GW.room_email_sentence(venue, res["how_many"]["count"], at[:10], nights)} if nights else {}
    if plan:
        body["plan_line"] = plan
    status, j = await GW.api(ctx.account, "POST", "/api/booking/emails", body)
    if status != 200:
        raise _err("no_route", f"{venue} can't be asked from here right now — {GW.refusal_words(j, status)}")
    return _hold(ctx, "email", j["email_id"], j["read_back"], rd, res, extra={"trip_item_id": j.get("trip_item_id"), **extra})


async def _call(ctx, a: dict, rd: dict, res: dict, extra: Optional[dict] = None) -> dict:
    """The call: what she'll say, read back; on the yes, placed (or scheduled when the rules said wait)."""
    GW = _API()
    fi = ((rd.get("rungs") or {}).get("phone") or {}).get("fact_index")
    status, j = await GW.api(ctx.account, "POST", "/api/booking/calls",
                             {"reservation": res, "read_id": rd["read_id"], **({"fact_index": fi} if fi is not None else {})})
    if status != 200:
        raise _err("no_route", f"{GW.plain_venue(rd['venue'])} can't be called from here right now — {GW.refusal_words(j, status)}")
    return _hold(ctx, "call", j["call_id"], j["read_back"], rd, res, extra={"trip_item_id": j.get("trip_item_id"), **(extra or {})})


async def _call_and_email(ctx, a: dict, rd: dict, res: dict, at: str, d: dict) -> dict:
    """R6 · soon, a hotel: the call AND the email at once — both prepared, ONE read-back (the two together), ONE yes."""
    GW = _API()
    fi = ((rd.get("rungs") or {}).get("phone") or {}).get("fact_index")
    s1, cj = await GW.api(ctx.account, "POST", "/api/booking/calls",
                          {"reservation": res, "read_id": rd["read_id"], **({"fact_index": fi} if fi is not None else {})})
    if s1 != 200:
        raise _err("no_route", f"{GW.plain_venue(rd['venue'])} can't be called from here right now — {GW.refusal_words(cj, s1)}")
    from booking_signer import guest_receipt as GR
    mine = await GR.address_of(ctx.account)
    nights = _nights(ctx, a)
    s2, ej = await GW.api(ctx.account, "POST", "/api/booking/emails", {
        "read_id": rd["read_id"], "date": at[:10], "time": at[11:16], "party": res["how_many"]["count"], "name": res["who"]["name"],
        "email": mine or "", **({"nights": nights} if nights else {})})
    if s2 != 200:   # the email can't go: the call alone, said as a call
        return _hold(ctx, "call", cj["call_id"], cj["read_back"], rd, res, extra={"trip_item_id": cj.get("trip_item_id")})
    lines = list(cj["read_back"].get("lines") or []) + list(ej["read_back"].get("lines") or [])
    both = {"lines": lines, "sha256": hashlib.sha256((cj["read_back"]["sha256"] + ej["read_back"]["sha256"]).encode()).hexdigest()}
    return _hold(ctx, "call_email", cj["call_id"], both, rd, res,
                 extra={"trip_item_id": cj.get("trip_item_id"), "call": {"id": cj["call_id"], "sha": cj["read_back"]["sha256"]},
                        "email": {"id": ej["email_id"], "sha": ej["read_back"]["sha256"]}})


def _draft(ctx, a: dict, rd: dict, res: dict, at: str, now, ch: str) -> dict:
    """Sasha 212 · a message they send (their WhatsApp, drafted): it is NOT booked until the place replies."""
    GW = _API()
    val = str(((rd.get("rungs") or {}).get(ch) or {}).get("value") or "")
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
    # Sasha 273 · item 2 (Tyler's demo with Jon, 16 Oct): ONE CARD PATH — an account whose access sends nothing to venues gets this
    # draft, and the draft drew no card, so the same booking showed a card on one account and none on another. On the one path the
    # draft carries its read-back too: the same booking card (sasha.render → "read_back"), on every account and every device.
    card_lines = [GW.plain_venue(rd["venue"]), GW.summary(res), f"The message: “{msg}”"] if one_path(ctx) else None
    return {"status": "draft_message", "venue": GW.plain_venue(rd["venue"]), "route": ch, "message": msg,
            **({"read_back": card_lines} if card_lines else {}),
            **({"open_in_" + ch: link} if link else {}),
            "what_happens": f"they book by a {('WhatsApp' if ch == 'whatsapp' else 'Instagram')} message: on their yes, "
                            "Sasha sends the drafted message to their phone and they send it; it is NOT booked until the place replies"}


async def engine_channel(card: Optional[dict], budget_s: float = 30.0, listing: bool = False) -> Optional[dict]:
    """Sasha 248 · ONE BOOKING PATH: how this venue books, from the venue engine's read of its own site (agapi/venue_truth) —
    the same read its card and detail sheet show. None: no site / not readable (then Sasha's own read decides, as before).
    Sasha 254 · with every other way the engine read (`all`) — the booking rules weigh them all (booking_decide.channels_of)."""
    import asyncio
    from agapi import venue_truth as VT
    if not card or not (card.get("website") or (listing and card.get("place_id"))):   # Sasha 270 · listing: the one path, no website
        return None
    try:
        p = await asyncio.wait_for(VT.profile(card, listing=listing), timeout=budget_s)
    except Exception:
        p = VT.shape(card, VT.cached(card))
    ch = p.get("channel")
    if ch:
        ch = {**ch, "all": list((VT.cached(card) or {}).get("channels") or [])}
    return ch


# "page" — the tool's own route word (its schema unchanged: S1 parity) — what read_booking_route says a channel is
ENGINE_ROUTE = {"own_engine": "page", "form": "page", "widget": "page", "email": "email", "whatsapp": "page", "phone": "call",
                "instagram": "instagram"}


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
                          "place_id": rd.get("place_id"), "country": rd.get("country") or (res.get("where") or {}).get("country"),   # 259 · its calendar zone
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
                "call": "Sasha calls them; it's booked only if they say yes on the call",
                # Sasha 254 · R6 — the call AND the email, on this ONE yes
                "call_email": "Sasha calls them and emails them at once, on this one yes; it's booked only if they confirm",
                "agapi": "on their yes, Sasha sends it to the venue; it's booked only when they confirm"}.get(rung, "")}
    if (extra or {}).get("say"):   # Sasha 253 · G7 / G8 — the old flow's own sentence for a request with no slot / a room
        out["say"] = extra["say"]
    elif one_path(ctx) and getattr(ctx, "surface", "") in ("s2", "s1"):
        # Sasha 256 · demo path item 10 (short confirmations): found live — after "Handle it" she recited the whole read-back in five
        # sentences. On a screen the read-back is its CARD (sasha.render: hold_venue's awaiting_yes → read_back); she says one line.
        # WhatsApp and voice have no card: they keep the read-back in words.
        out["ask"] = READ_BACK_ASK.format(venue=out["venue"])
        out["how"] = "Say `ask` word for word — every detail is on the card on their screen; never read the details out."
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
        picked = chosen_route(ctx.user_said)
        if picked and one_path(ctx):   # Sasha 262/263 · their answer to the one question ("Handle it"): the read-back card, by the
            booking = {k: v for k, v in a.items() if k not in _NOT_BOOKING}   # ONE path — hold_venue with the booking she was given
            if booking.get("name") and booking.get("party"):                  # (never a booking remembered from an earlier question)
                return await hold_venue(ctx, {**booking, "route": picked})
            raise _err("hold_first", f"they answered the one question: call hold_venue now with the booking they asked for and route "
                                     f"{picked} — it reads it back; nothing is sent until their yes")
        raise _err("no_explicit_yes", "booking needs the person's explicit yes in this turn — ask them, then call book_venue")
    held = _HELD.get(ctx.account)
    from agapi import venue_submit as VS
    if not held:
        sent = _SENT.get(ctx.account)
        if sent and not stale(sent["at"]):   # Sasha 258 · the same yes again: already sent — said, with its status; never sent twice
            return await _tap_refused(ctx, {"venue": sent["venue"]}, "approval_consumed", {}, sent["venue"])
        if VS.TAP.get() is not None:   # Sasha 263 · in the app the yes sends ONLY the card on their screen: none waiting → said, nothing sent
            return {"status": "nothing_waiting", "booked": False, "in_app": True}
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
    if out.get("status") != "waiting_for_their_tap":   # Sasha 254 · nothing has gone yet: recorded when it does
        await OC.booked(ctx.account, held, venue, area_of(card) if card else None, result=out)
    if out.get("status") == "confirmed" and out.get("line"):   # Sasha 279 · C: a completed booking — the closing line, once, in the
        from booking_signer import live_events as LE           # line both doors say word for word (the email sent and read first)
        done = await LE.completed(ctx.account, f"venue:{held.get('trip_item_id') or held.get('id') or venue}:{held.get('when')}",
                                  lines=[f"{venue} — {held.get('summary') or held.get('when') or ''}"
                                         + (f" · reference {out['reference']}" if out.get("reference") else "")],
                                  title=venue, push=False)
        if done.get("text"):
            out = {**out, "line": f"{out['line']} {done['text']}", "emailed": done.get("emailed")}
    return _with_card(card, out)


async def _book_inner(ctx, held: dict, how: dict, venue: str, rung: str) -> dict:
    from booking_signer import slot_link as SL, wa_brain as WB
    GW = _API()
    where = await WB.trip_day_words(ctx.account, held["when"][:10], venue)
    if rung == "agapi":   # Sasha 254 · item 3 — the AgAPI send, on their yes (venue.submit_booking)
        return await _agapi_send(ctx, held, how, venue, where)
    if rung == "agapi_call":   # Sasha 265 · item 4 — the call act, on their tap (the approval); dialled only from the act
        return await _agapi_call(ctx, held, how, venue, where)
    if rung == "form":
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/forms/{held['id']}/send", {"read_back_sha256": held["sha"], "approval": how}, timeout=120)
        if status != 200:
            raise _err("not_sent", GW.refusal_words(j, status))
        result = (j.get("reading") or {}).get("result") if j.get("status") == "sent" else None
        ref = j.get("booking_reference") if result == "confirmed" else None
        return {"status": "confirmed" if result == "confirmed" else ("requested" if j.get("status") == "sent" else "not_sent"),
                "venue": venue, "when": held["summary"], "itinerary": where, **({"reference": ref} if ref else {}),
                "line": (f"✅ Booked: {venue}, {held['summary']}." + (f" Their reference: {ref}." if ref else "")) if result == "confirmed"
                else held.get("rules_say") or __import__("app.agent.voice", fromlist=["x"]).SENT}   # Sasha 254 · the rules' words
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
        if one_path(ctx):   # Sasha 283 · item 4c: the hand-over's way back (old S1: its own message, untouched)
            from app.agent import voice as _V
            from booking_signer import wa_agent as WA
            text = f"{text}\n\n{_V.way_back(WA.s2_link())}"
        sent = False
        try:
            ch = await GW.STORE.channel_of_account(ctx.account) if GW.STORE else None
            if ch:
                o = await GW._tell(ch, text)
                sent = "sent" in o and "not" not in o
        except Exception as e:
            log.warning("[venues] the prepared page was not sent to the phone: %s", type(e).__name__)
        # Sasha 254 · ONE TRUTH: "It's in your bookings" is true only because it IS — get_status reads this record
        await note_prepared(ctx.account, venue, held["when"], held["party"], held.get("url"))
        from app.agent import voice as V
        from agapi import venue_submit as VS
        # Sasha 264 · item 2 (Tyler's spa, 14 Oct): AgAPI gave no filled page — their own page opened EMPTY and she said "Done — it's
        # on your screen". No prepared link = not filled: said so, plainly, with the details to copy (never an empty page called done)
        filled = bool(prep)
        if not filled:
            log.info("[venues] %s: venue.prepare_booking gave no filled page — their own page and the details to copy", venue)
        fw = held.get("follow")
        if fw and filled:   # Sasha 284 · followed AgAPI's decision: its words and its button (prepare's own decision, with the prepared link)
            dec = prep.get("decision") or fw["decision"]
            label = V.OPEN_THEIR_PAGE if fw["refused"] else (dec.get("button") or {}).get("label") or V.OPEN_THEIR_PAGE
            return {"status": "page_on_phone" if sent else "page_link", "venue": venue, "when": held["summary"], "itinerary": where,
                    "booked": False, "route": dec.get("route"),
                    "prepared": {"venue": venue, "url": held["url"], "fields": held["fields"], "on_phone": sent, "filled": True, "button": label,
                                 **({"human_step": held["human_step"], "prepared_by": "venue.prepare_booking"} if held.get("human_step") else {})},
                    **({"in_app": True} if VS.TAP.get() is not None else {}),
                    "say": (prep.get("say") if fw["refused"] else dec.get("say_text")) or V.done_form(getattr(ctx, "surface", "s2"))}
        return {"status": "page_on_phone" if sent else "page_link", "venue": venue, "when": held["summary"], "itinerary": where, "booked": False,
                "prepared": {"venue": venue, "url": held["url"], "fields": held["fields"], "on_phone": sent, "filled": filled,
                             **({"human_step": held["human_step"], "prepared_by": "venue.prepare_booking"} if held.get("human_step") else {})},
                **({"in_app": True} if VS.TAP.get() is not None else {}),
                # Sasha 249 · her words for it are her voice's, never the engine's (which may name the booking platform)
                "say": (V.done_form(getattr(ctx, "surface", "s2")) if filled else V.NOT_FILLED) + " Say exactly that — never that it's booked."}
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
        if one_path(ctx):   # Sasha 283 · item 4c: the hand-over's way back (old S1: its own message, untouched)
            from app.agent import voice as _V
            from booking_signer import wa_agent as WA
            text = f"{text}\n\n{_V.way_back(WA.s2_link())}"
        out = await GW.tap_platform(ctx.account, text, url, held["id"], venue, held["when"])
        if one_path(ctx):   # Sasha 283 · item 4c: on the one row the way back reads, with its link's own record
            await note_prepared(ctx.account, venue, held["when"], held["party"], url, link_id=held["id"])
        sent = "sent" in out and "not" not in out
        if not sent:   # Sasha 264 · item 3: the reason was dropped — Tyler's tattoo link "never arrived" and nothing said why
            log.warning("[venues] %s's page not sent to the phone: %s", venue, out)
        from app.agent import voice as V
        from agapi import venue_submit as VS
        in_app = VS.TAP.get() is not None   # Sasha 264 · item 3: in the app the page is ALWAYS the card; the phone is an extra, its
        says = ""                            # failure said. Item 8: the one line, and the confirmation picked up from their Gmail
        if in_app:
            from booking_signer import mailbox as MB
            try:
                gmail = bool(MB.STORE is not None and await MB.STORE.get_link(ctx.account))
            except Exception as e:   # their Gmail link unreadable: the page still goes; she asks for the confirmation instead
                log.warning("[venues] Gmail link not read: %s", type(e).__name__)
                gmail = False
            if gmail and not sent:   # tap_platform starts the Gmail watch only when the phone got it — in the app, always
                GW._spawn(MB.watch_after_link(ctx.account, held["id"]))
            says = V.platform_line(venue, int(held["party"]), held["summary"], bool(held.get("slot_filled")), gmail)
        return {"status": "page_on_phone" if sent else "page_link", "venue": venue, "when": held["summary"], "itinerary": where,
                **({"in_app": True, "phone_line": V.phone_line(sent, out), "page_says": says} if in_app else {}),
                "platform": held.get("platform"), **({} if sent else {"open": url}), **({"page_url": url} if url else {}),
                # Sasha 236 · found live on /s2: "their page is on your phone" when it wasn't sent there
                **({} if sent else {"say": "Their page is on this screen — Tap to finish opens it. Never say it's on their phone."})}
    if rung == "email":
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/emails/{held['id']}/send", {"read_back_sha256": held["sha"], "approval": how}, timeout=60)
        if status != 200 or j.get("status") != "sent":
            raise _err("not_sent", (j or {}).get("say") or GW.refusal_words(j, status))
        return {"status": "requested", "venue": venue, "when": held["summary"], "itinerary": where,
                "line": held.get("rules_say") or __import__("app.agent.voice", fromlist=["x"]).SENT}   # Sasha 254 · the rules' words
    if rung == "call_email":   # Sasha 254 · R6 — the email AND the call, on the ONE yes
        mail = held["email"]
        s1, ej = await GW.api(ctx.account, "POST", f"/api/booking/emails/{mail['id']}/send", {"read_back_sha256": mail["sha"], "approval": how}, timeout=60)
        out = await _place(ctx, {**held, "id": held["call"]["id"], "sha": held["call"]["sha"]}, how, venue, where)
        return {**out, "email": "sent" if s1 == 200 and (ej or {}).get("status") == "sent" else
                f"not sent — {(ej or {}).get('say') or GW.refusal_words(ej, s1)}"}
    return await _place(ctx, held, how, venue, where)


async def _agapi_send(ctx, held: dict, how: dict, venue: str, where) -> dict:
    """venue.submit_booking with their yes → said in her voice: Booked (the venue's page confirmed it) / the rules' "sent" words /
    "not allowed" said kindly, with their prepared page / failed, said."""
    from agapi import booking_decide as BD, venue_submit as VS
    from agapi.booking_rules import booking_rules as BR
    r = await VS.submit(ctx.account, held, how.get("said") or "")
    if not r.get("ok"):
        code = r["error"]["code"]
        if code in VS.TAP_REFUSALS:   # Sasha 258 · the in-app yes refused: one plain line, never a dead end
            return await _tap_refused(ctx, held, code, r["error"], venue)
        raise _err("no_explicit_yes" if code == "no_explicit_yes" else "not_sent", r["error"]["message"])
    st = r.get("status")
    if st in ("confirmed", "sent"):
        _SENT[ctx.account] = {"venue": venue, "at": datetime.now(timezone.utc)}   # Sasha 258 · a repeated yes answers "already sent"
    if st == "waiting_for_their_tap":   # live: their tap on AgAPI's link is the approval — the hold stays for it
        _HELD[ctx.account] = held
        return {"status": "waiting_for_their_tap", "venue": venue, "when": held["summary"], "booked": False,
                "line": "It's on your phone: tap Yes there, then it goes."}
    if st == "confirmed":
        ref = r.get("reference")
        # Sasha 258 · demo path item 10 (≤ 2 sentences): ONE sentence with its reference, said word for word — then at most one question
        from app.agent import voice as V
        return {"status": "confirmed", "venue": venue, "when": held["summary"], "itinerary": where, **({"reference": ref} if ref else {}),
                "line": V.booked_line(venue, held["summary"], ref),
                **({"in_app": True} if VS.TAP.get() is not None else {}),   # Sasha 263 · the in-app yes: said by code (voice.yes_line)
                "how": "Say `line` word for word, then at most ONE short question (e.g. the calendar) — nothing else."}
    if st == "sent":
        if r.get("call_plan") and r.get("act_id"):   # Sasha 271 · CR 102 · R6 (a stay arriving within 24 h): the engine opened the call
            from agapi import venue_calls as VC       # WITH the email, under this same yes — Sasha dials only its call_plan, exactly
            dialled = await VC.dial(ctx.account, r, {**held, "timezone": _tz_of(held)})   # as a table's call (Sasha 269); said: its `say`
            from app.agent import voice as V
            return {"status": "requested", "venue": venue, "when": held["summary"], "itinerary": where, "act_id": r.get("act_id"),
                    "line": V.act_line(r.get("say")), "call": {"status": "calling", "dial": dialled.get("status"),
                                                               "reason": r["call_plan"].get("reason")},
                    **({"in_app": True} if VS.TAP.get() is not None else {}), "how": "Say `line` word for word — nothing else."}
        if (r.get("takeover") or {}).get("kind") == "their_listing":   # Sasha 272 · CR 103 · R6 was due, but their listing shows no number
            from app.agent import voice as V                            # now: the email went; said with their listing — never a silent skip
            link = r["takeover"].get("link")
            return {"status": "requested", "venue": venue, "when": held["summary"], "itinerary": where, "act_id": r.get("act_id"),
                    "line": V.takeover_line(r.get("say"), link), "call": {"status": "no_number", "reason": "R6"}, **_link_out(link),
                    **({"in_app": True} if VS.TAP.get() is not None else {}), "how": "Say `line` word for word — nothing else."}
        sent_line = BD.say({"say_text": BR.PHRASES["sent"], "takeover": {"say": BR.PHRASES["takeover"]}})
        # Sasha 272 · found by gate D: her own rules said "call AND email" from her own read, but the ENGINE opened no call with it (its
        # read-back named none: their listing shows no number now) — never promise a call the booking won't make: the sent line
        return {"status": "requested", "venue": venue, "when": held["summary"], "itinerary": where, "act_id": r.get("act_id"),
                "line": sent_line if held.get("agapi_action") == "call_and_email" else held.get("rules_say") or sent_line}
    if st == "not_allowed":   # not this person (yet): kindly, with their prepared page — nothing reached the venue
        link = held.get("link")
        return {"status": "not_allowed", "venue": venue, "when": held["summary"], "booked": False,
                "say": f"{BR.PHRASES['no_real_sends']} {BR.PHRASES['takeover']}", **({"open": link, "page_url": link} if link else {})}
    raise _err("not_sent", r.get("say") or f"{venue} didn't take it — nothing is booked")


async def _agapi_call(ctx, held: dict, how: dict, venue: str, where) -> dict:
    """Sasha 265 · item 4 · their answer → approvals.in_app_tap on the call's read-back (the tap; on WhatsApp the signed reply) → the act
    (status calling, act_id, call_plan) → Sasha dials ONLY what call_plan says (agapi.venue_calls). Said: ONLY the act's own `say`
    ("On it — I'll call them when they open at 13:00 and let you know.")."""
    from agapi import venue_calls as VC, venue_submit as VS
    r = await VS.submit(ctx.account, held, how.get("said") or "")
    if not r.get("ok"):
        code = r["error"]["code"]
        if code in VS.TAP_REFUSALS:
            return await _tap_refused(ctx, held, code, r["error"], venue)
        raise _err("not_sent", r["error"]["message"])
    st = r.get("status")
    if st == "waiting_for_their_tap":   # their WhatsApp number isn't verified yet: AgAPI's one-tap link (it verifies it) — said
        _HELD[ctx.account] = held
        return {"status": "waiting_for_their_tap", "venue": venue, "when": held["summary"], "booked": False,
                "line": "It's on your phone: tap Yes there, then I'll call them."}
    if st == "not_allowed":
        link = held.get("link")
        return {"status": "not_allowed", "venue": venue, "when": held["summary"], "booked": False, "say": r.get("say") or "",
                **({"open": link, "page_url": link} if link else {})}
    if st != "calling":
        raise _err("not_sent", r.get("say") or f"{venue} couldn't be called — nothing is booked")
    _SENT[ctx.account] = {"venue": venue, "at": datetime.now(timezone.utc)}
    dialled = await VC.dial(ctx.account, r, {**held, "timezone": _tz_of(held)})
    return {"status": "calling", "venue": venue, "when": held["summary"], "booked": False, "act_id": r.get("act_id"),
            "line": r.get("say") or "", "dial": dialled.get("status"), **({"in_app": True} if VS.TAP.get() is not None else {}),
            "how": "Say `line` word for word — nothing else."}


def _tz_of(held: dict) -> str:
    from booking_signer import venue_read as V
    return (V.COUNTRIES.get(str(held.get("country") or "").upper()) or (None, None, None, "Europe/Madrid"))[3]


_SENT: Dict[str, dict] = {}   # Sasha 258 · account → the last booking sent on their in-app yes (venue, at) — a repeated yes


async def _tap_refused(ctx, held: dict, code: str, err: dict, venue: str) -> dict:
    """Sasha 258 · AgAPI refused the in-app yes (CR 97): a stale or timed-out card → the NEW read-back on its card, asked again; not
    this person's session → sign in again; already tapped → "already sent" and the booking's status. Nothing is sent twice."""
    from agapi import venue_submit as VS
    from app.agent import voice as V
    if code in ("approval_void", "approval_expired"):
        fresh = (err.get("details") or {}).get("fresh")
        if fresh and fresh.get("ok"):
            held = {**held, "read_back_id": fresh["read_back_id"], "sha": fresh["sha256"], "lines": fresh["lines"],
                    "at": datetime.now(timezone.utc)}
            _HELD[ctx.account] = held
            return {"status": "awaiting_yes", "venue": venue, "when": held.get("summary"), "read_back": fresh["lines"], "booked": False,
                    "ask": V.tap_line(code), "how": "Say `ask` word for word — the new card is on their screen."}
        _HELD.pop(ctx.account, None)
        return {"status": "not_sent", "venue": venue, "booked": False, "say": V.tap_line(code) + " " + "Ask me to hold it again."}
    if code == "approval_untrusted_origin":
        _HELD[ctx.account] = held   # the card stays: after signing in, their yes still answers it
        return {"status": "not_sent", "venue": venue, "booked": False, "say": V.tap_line(code)}
    # approval_consumed: the yes was already taken — the booking's own status, never a second send
    _HELD.pop(ctx.account, None)
    row = next((b for b in await VS.bookings(ctx.account) if _base(b.get("venue") or "") == _base(venue)), None)
    from agapi import s2_status as ST
    status = ST.decide({"venues": [row], "booked": [], "failed": []})["line"] if row else None
    return {"status": "already_sent", "venue": venue, "booked": bool(row and row.get("status") == "confirmed"),
            "say": V.tap_line(code) + (f" {status}" if status else "")}


async def _place(ctx, held: dict, how: dict, venue: str, where) -> dict:
    """The call, on their yes. Sasha 254 · R10 refused at the dial (3 a day for this person, the server's net, 30 minutes since the
    last call to this venue, calls off) → booking_rules.stopped(): the person is told, in this turn and on get_status."""
    from agapi import booking_decide as BD
    GW = _API()
    body = {"read_back_sha256": held["sha"], "approval": how, **({"scheduled_for": held["scheduled_for"]} if held.get("scheduled_for") else {})}
    status, j = await GW.api(ctx.account, "POST", f"/api/booking/calls/{held['id']}/place", body, timeout=120)
    if status in (403, 422, 429) and (j or {}).get("rule") in BD.CALL_STOPS:
        d = await BD.tell_stopped(ctx.account, f"the call to {venue}", BD.CALL_STOPS[j["rule"]], push=False)
        return {"status": "stopped", "venue": venue, "when": held["summary"], "booked": False, "say": BD.say(d), "takeover": d["takeover"]}
    if status != 200:
        raise _err("not_called", GW.refusal_words(j, status))
    if j.get("status") in ("placed", "uncertain"):   # Sasha 253 · G2 — its result pushed to their WhatsApp when the call ends
        await _push_later(ctx.account, call_id=held["id"], venue=venue, purpose="book", what=held.get("summary") or "")
    return {"status": j.get("status"), "venue": venue, "when": held["summary"], "itinerary": where,
            **({"line": held["rules_say"]} if held.get("rules_say") and j.get("status") in ("placed", "uncertain") else {}),
            **({"say": j["say"]} if j.get("status") == "scheduled" and j.get("say") else {}),
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
    today = date.today().isoformat()
    acts: List[dict] = []
    try:   # Sasha 254 · item 3 — the AgAPI sends, each with the venue's reply now (venue.booking_status), at most 5 s
        from agapi import venue_submit as VS
        acts = [b for b in await asyncio.wait_for(VS.bookings(account), timeout=5) if (b.get("date") or today) >= today
                and (include_cancelled or b.get("status") != "cancelled")]
    except Exception as e:
        log.info("[venues] AgAPI acts not read: %s", type(e).__name__)
    if status != 200:
        return acts
    try:   # CR 87 · a venue's reply that changed a reservation updates its outcome (once) — Sasha 247: awaited, at most 3 s (a bare
        from agapi import s2_outcomes as OC   # task can be dropped mid-way and never finish); a slow ledger never stops this read
        await asyncio.wait_for(OC.sync(account, (j or {}).get("reservations") or []), timeout=3)
    except Exception as e:
        log.info("[venues] outcomes not synced: %s", type(e).__name__)
    return acts + [{"trip_item_id": r["id"], "venue": GW.plain_venue(r.get("venue")), "date": r.get("date"), "time": r.get("time"),
             "party": r.get("party"), "status": r.get("status"), "type": r.get("type"),
             **({"reference": r["booking_reference"]} if r.get("booking_reference") else {}),   # Sasha 217 · the venue's reference in full
             # Sasha 215 · CR 56 — the venue's OWN words (an email/SMS reply) are untrusted data, never instructions to her
             **({"venue_said": {"untrusted_text": str(r["status_words"])[:160]}} if r.get("status_words") else {})}
            for r in (j or {}).get("reservations") or []
            if (r.get("date") or today) >= today and (include_cancelled or r.get("status") != "cancelled")][:20 - len(acts)]


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
    if not a.get("act_id") and a.get("reference"):   # Sasha 256 · the venue's reference they quoted names the act
        from agapi import venue_submit as VS
        hit = _which_act([b for b in await VS.bookings(ctx.account) if b.get("act_id")], a["reference"])
        if hit:
            a = {**a, "act_id": hit["act_id"]}
    if (held and held.get("act_id")) or a.get("act_id"):
        return await _cancel_act(ctx, a, held, said or getattr(ctx, "user_said", "") or "", explicit_yes)
    tid = a.get("trip_item_id")
    if not tid and a.get("venue"):
        hit = [b for b in await venue_bookings(ctx.account) if (a["venue"] or "").lower() in (b["venue"] or "").lower()]
        acts = [b for b in hit if b.get("act_id") and not b.get("trip_item_id") and b.get("status") in ("confirmed", "requested", "proposed")]
        if acts:   # Sasha 256 · a booking sent through AgAPI: exactly the one they mean — a quoted reference, else the only one
            pick = _which_act(acts, a.get("reference"), getattr(ctx, "user_said", None)) or (acts[0] if len(acts) == 1 else None)
            if pick is None:
                raise _err("which_booking", "more than one booking there matches — ask which one (" + "; ".join(
                    f"{b.get('date')} {b.get('time') or ''} · act_id {b['act_id']}" for b in acts) + ") and call again with its act_id")
            return await _cancel_act(ctx, {**a, "act_id": pick["act_id"]}, held, said, explicit_yes)
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


async def _cancel_act(ctx, a: dict, held: Optional[dict], said: str, explicit_yes) -> dict:
    """Sasha 256 · item 3 — MANAGE a booking sent through AgAPI (an act): venue.cancel_booking (CR 94). Its read-back first; on their
    explicit yes in a LATER turn the cancellation goes to the venue as its own act, and it's cancelled only when the venue's reply
    says so (get_status, through venue.booking_status). A booking made on the venue's own form can't be cancelled from here: their
    own page, said kindly."""
    from agapi.v0 import claim
    from agapi import venue_submit as VS
    if held and held.get("act_id") and (not a.get("act_id") or a["act_id"] == held["act_id"]) and held["at"] < ctx.started:
        if not explicit_yes(said):
            raise _err("no_explicit_yes", "cancelling needs their explicit yes — ask them")
        await claim(ctx)
        r = await VS.cancel_submit(ctx.account, held, said)
        if not r.get("ok"):
            raise _err(r["error"]["code"], r["error"]["message"])
        _CANCEL.pop(ctx.account, None)
        if r.get("status") == "waiting_for_their_tap":
            return {"status": "waiting_for_their_tap", "venue": held.get("venue"),
                    "say": "I've sent you the link — the cancellation goes once you tap yes there."}
        return {"status": "requested", "venue": held.get("venue"),
                "say": "I've asked them to cancel it. It's still booked until they confirm — I'll tell you when they do."}
    rb = await VS.cancel_read_back(ctx.account, a["act_id"])
    if not rb.get("ok"):
        e = rb["error"]
        if e["code"] == "not_allowed":
            link = (e.get("details") or {}).get("link")
            return {"status": "not_cancelled", "say": e["message"], **({"open": link, "page_url": link} if link else {})}
        raise _err(e["code"], e["message"])
    venue = next((b.get("venue") for b in await VS.bookings(ctx.account) if b.get("act_id") == a["act_id"]), a.get("venue"))
    import hashlib as _hl   # the one-yes gate (CR 76) binds their yes to THIS read-back by its words
    _CANCEL[ctx.account] = {**rb, "at": datetime.now(timezone.utc), "venue": venue,
                            "sha": _hl.sha256("\n".join(str(x) for x in rb["lines"]).encode()).hexdigest()}
    return {"status": "awaiting_yes", "venue": venue, "route": "agapi", "read_back": rb["lines"]}


__all__ = ["read_booking_route", "hold_venue", "book_venue", "cancel_venue", "venue_bookings"]
