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
from kanoe_contract import ERR, OP  # Sasha 374 · THE ONE generated contract (CR 186)

import asyncio
import hashlib
import logging
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
import time as _clock   # Sasha 299 · (`time` here is datetime's)
from typing import Any, Dict, List, Optional, Tuple
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


async def note_prepared(account: str, venue: str, when: str, party: Any, url: Optional[str], link_id: Optional[str] = None,
                        route: Optional[str] = None, platform: Optional[str] = None, place_id: Optional[str] = None,
                        prepared_id: Optional[str] = None) -> None:
    """A prepared page drawn for them: on the record (the same booking prepared again replaces its line, never a second one).
    Sasha 283 · item 4c: EVERY page hand-over writes this row (the copy card, and a platform's page with its booking_links id) — the
    one place the way back reads."""
    row = {"venue": venue, "date": str(when or "")[:10], "time": str(when or "")[11:16], "party": int(party or 0),
           **({"url": url} if url else {}), **({"link_id": link_id} if link_id else {}), "at": datetime.now(timezone.utc).isoformat(),
           # Sasha 300 · the ONE itinerary's: the route it was handed over by, its platform, the venue's place ID (its map link)
           **({"route": route} if route else {}), **({"platform": platform} if platform else {}), **({"place_id": place_id} if place_id else {})}
    same = lambda r: _base(r.get("venue") or "") == _base(venue) and r.get("date") == row["date"] and r.get("time") == row["time"]
    rows = ([r for r in await prepared_pages(account) if not same(r)] + [row])[-10:]
    _PREPARED[account] = rows
    from agapi import s2_memory as M
    if not await M.put_kind(account, PREPARED_KIND, rows):
        log.info("[venues] prepared page kept in this process only (no memory table)")
    if prepared_id:   # CR 132 (a) · AgAPI's booking record holds the hand-over too — after her answer, never holding it up
        from agapi import venue_submit as VS
        how = {"your_whatsapp": "whatsapp_person", "platform": "platform"}.get(str(route or ""), "platform" if platform else "their_page")
        VS.handed_over_later(account, prepared_id, how, url)


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


# ── Sasha 299 · THE 11–15 SECONDS: a tap on a card's Book names the venue, so the two reads its booking makes — S2's own venue read
# (/api/booking/venues/read) and AgAPI's venue.profile (venue_truth, one read per site at a time, cached) — start AT THE TAP, while she
# is still thinking (3–4 s measured), instead of after. The same reads, never extra ones: read_booking_route takes this one (_read).
_AHEAD: Dict[Tuple[str, str], Tuple[float, Any]] = {}
AHEAD_S = 120.0


def read_ahead(account: str, place_id: str) -> bool:
    """Start the tapped card's reads now (the /s2 turn route calls it on a card's tap). → whether they were started."""
    import asyncio
    c = card_of(account, place_id)
    if not c or not place_id or ((account, place_id) in _AHEAD and _clock.time() - _AHEAD[(account, place_id)][0] < AHEAD_S):
        return False
    city = city_of(c.get("address"))   # the read needs a city (venue_read: 2–60 characters): the card's own address says it
    if not city:
        return False
    body = {"name": c.get("name"), "place_id": place_id, "website": c.get("website"), "city": city, "s2_demo": True}
    _AHEAD[(account, place_id)] = (_clock.time(), asyncio.create_task(_API().api(account, "POST", "/api/booking/venues/read",
                                                                                {k: v for k, v in body.items() if v})))
    from agapi import venue_truth as VT
    p = asyncio.create_task(VT.profile(c, listing=True))   # warms AgAPI's read: engine_channel then shares it (VT._INFLIGHT / cache)
    VT._BG.add(p)
    p.add_done_callback(VT._BG.discard)
    return True


#: Sasha 299 · (4) a search older than this is not "the search it came from" (the person may have moved on)
TAP_SLOT_S = 30 * 60


def tap_plan(account: str, session: Optional[str], place_id: str) -> Optional[List[Tuple[str, dict]]]:
    """Sasha 299 · (4) (Tyler, 27 Oct: "a Book tap runs the route and hold by code; the model only writes the words") · THE ONE PLACE a
    tap's two calls are decided: [read_booking_route, hold_venue], their arguments ONLY from what he already gave — the card he tapped
    (name, place_id, website, its address's city) and the search it came from in THIS session (day · time · party, v0.SEARCH_SLOT).
    Anything missing → None: the model's path, as before. Never a default day, time or party; nothing here decides a route."""
    from agapi import v0 as API
    c = card_of(account, place_id) if place_id else None
    slot = API.SEARCH_SLOT.get(account) or {}
    if not c or not c.get("name") or not session or slot.get("session") != session or _clock.time() - float(slot.get("at") or 0) > TAP_SLOT_S:
        return None
    at = str(slot.get("open_at") or "")
    party = slot.get("party")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", at) or not isinstance(party, int) or not 1 <= party <= 20:
        return None
    city = city_of(c.get("address")) or (str(slot.get("where") or "").split(",")[-1].strip() or None)
    if not city or not 2 <= len(city) <= 60:
        return None
    venue = {"name": str(c["name"])[:80], "city": city, "place_id": place_id, **({"website": c["website"]} if c.get("website") else {}),
             **({"country": slot["country"]} if slot.get("country") else {})}
    return [("read_booking_route", dict(venue)), ("hold_venue", {**venue, "day": at[:10], "time": at[11:16], "party": party})]


def city_of(address: Optional[str]) -> Optional[str]:
    """"Calle de Atocha 12, 28012 Madrid, Spain" → "Madrid": the locality before the country, its postcode dropped."""
    parts = [x.strip() for x in str(address or "").split(",") if x.strip()]
    if len(parts) < 2:
        return None
    c = re.sub(r"^\d[\d\s-]*", "", parts[-2]).strip()
    return c if 2 <= len(c) <= 60 else None


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
    ahead = _AHEAD.pop((ctx.account, str(body.get("place_id") or "")), None) if s2 else None   # Sasha 299 · started at his tap
    if ahead and _clock.time() - ahead[0] < AHEAD_S:
        try:
            status, rd = await ahead[1]
        except Exception:
            status, rd = 0, None
        if status != 200:   # the early read failed: the route's own read, as before — an early read only ever saves time
            log.info("[venues] the read started at the tap didn't answer (%s) — reading now", status)
            status, rd = await GW.api(ctx.account, "POST", "/api/booking/venues/read", {k2: v for k2, v in body.items() if v})
    else:
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


async def read_booking_route(ctx, a: dict) -> dict:
    from agapi import test_venues as TV
    a = await TV.vet(ctx, a)   # Sasha 256 · the test venue: a test person's card, never a live person's
    rd = await _read(ctx, a)
    card = card_of(ctx.account, a.get("place_id"), a.get("name"))   # Sasha 213 · the picked card is what's on screen
    # Sasha 378 · CR 188 · how it books = AgAPI's ONE decision (venue.profile → handoff.decide), on every surface — the same one
    # hold_venue follows. Never Sasha's own read of their channels; no decision → THE FLOOR.
    from agapi import venue_truth as VT
    from app.agent import voice as V
    place = place_of(rd, card, a)
    if place:
        await engine_channel(place, listing=True)
    dec = VT.decision(place)
    # Sasha 284 · AgAPI's words, whatever the route (never NO_LINK over it); a call: her own offer (voice.CALL_IT) until CR words it.
    # Sasha 286: never AgAPI's words asking for a link.
    if dec and dec["route"] != "none" and not V.asks_for_link(dec.get("say_text") or ""):
        return {**({"card": card} if card else {}), "venue": rd["venue"], "routes": [dec["route"]],
                "how": V.CALL_IT if dec.get("how_far") == "call" else dec["say_text"],
                "decision": {k: dec.get(k) for k in ("route", "say_text", "button")},
                "open_now": rd.get("open_now"), "opens_at": rd.get("opens_at")}
    f = await floor_out(ctx, a, rd, None, card, dec)
    return {**({"card": card} if card else {}), "venue": rd["venue"], "routes": [], "how": f["floor"]["say"], "floor": f["floor"],
            **_link_out(f["floor"]["button"]["link"]), "open_now": rd.get("open_now"), "opens_at": rd.get("opens_at")}


from app.agent.voice import READ_BACK_ASK   # noqa: E402 · Sasha 262 · the one read-back line lives in her voice (app/agent/voice.py)
# Sasha 263 · row 914: 262's second memory of "which booking the one question was about" (_ASKED_ROUTE) is gone — it kept item 7's
# 20:15 and the yes sent it in place of the 21:15 asked for. The one record is the read-back card (_HELD: AgAPI's read_back_id + sha).
_NOT_BOOKING = ("approval", "idempotency_key", "route")


TO_TYLER = "I'll hand this to Tyler — nothing was sent to them."   # Sasha 319 · = booking_signer.retired.TO_TYLER


def _to_tyler(venue: str, d: dict) -> dict:
    """Sasha 319 · AgAPI is the ONE sender to venues: where it can't send (no venues key on this server, no slot to ask for), nothing is
    sent — Tyler takes it from here. Said by code."""
    return _said({"status": "to_tyler", "venue": venue, "booked": False, "sent": False, "line": TO_TYLER,
                  "how": "Say `line` word for word — nothing else."}, d)


def one_path(ctx) -> bool:
    """Sasha 251 · the one path's SCHEMA and asks (under / open_slot / nights, the contact asked once, a Keep loyalty number) on /s2,
    WhatsApp's brain and /next under S1 parity; old S1 (SASHA_S1_PARITY=off) keeps its own schema byte-identical. Sasha 254 · the
    booking DECISION is the same for every surface: AgAPI's (Sasha 378 · CR 188: venue.profile's decision, followed by one_decision)."""
    if getattr(ctx, "surface", "s1") == "s2":
        return True
    from app.agent.sasha import s1_parity
    return s1_parity()


def place_of(rd: dict, card: Optional[dict], a: dict) -> Optional[dict]:
    """Sasha 378 · THE ONE place AgAPI's venue.profile is asked about (its `decision` is the route) — the same place venue.prepare_booking
    is given: the card on screen; else the venue being booked, by its listing (place_id) and the website the booking names. Found by
    the deploy gate: a venue named by its website alone (no card, no listing) had no decision, so it fell to the floor."""
    if card:
        return card
    pid, site = rd.get("place_id") or a.get("place_id"), a.get("website") or rd.get("website")
    if not pid and not site:
        return None
    return {"name": rd.get("venue") or a.get("name"), **({"place_id": pid} if pid else {}), **({"website": site} if site else {})}







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
            hhmm = CHECK_IN   # Sasha 253 · G8 — check-in, as the old flow's hotel request (a room is never "at" a time)
        elif open_slot:
            day = day if a.get("day") else None
        elif one_path(ctx):
            raise _err("when_invalid", "day is YYYY-MM-DD and time HH:MM — ask for them; or, when they want no set time, pass "
                                       "open_slot ('quote' for custom work they quote for, 'whenever' for 'whenever they have "
                                       "space'); a hotel stay is day + nights") from None
        else:
            raise _err("when_invalid", "day is YYYY-MM-DD and time HH:MM") from None
    party = max(1, min(20, int(a["party"])))   # Sasha 381 · never a default: their own, or asked first (_terms_asked, AgAPI's term_not_given)
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


async def booking_person(account: str, res: dict) -> Dict[str, Any]:
    """Sasha 328 · THE ONE PERSON every venue.prepare_booking is given (AgAPI fills a platform's form from it: CR 160's contact): the
    booking name (theirs, or the one they gave: `under`), their mobile — both from the ONE contact record — and THE booking email
    (contacts.booking_email: the address they named for bookings, else their linked Gmail's, else their sign-in address)."""
    from booking_signer import contacts as CT
    return {"name": res["who"]["name"], "phone": res["who"]["contact"].get("mobile_e164"), "email": await CT.booking_email(account)}


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
    """Sasha 253 · their booking name and mobile, from their own words, saved with the consent they were told.
    Sasha 328 · + email: THE address for their bookings ("use tylerwarren@gmail.com for my bookings"), in their own words, on the same
    ONE contact record — given to every venue from then on (booking_person). Alone, it changes only the email."""
    GW = _API()
    said = str(ctx.user_said or "")
    if a.get("email") and not (a.get("name") or a.get("mobile") or a.get("this_number")):
        return await _save_booking_email(ctx, a["email"])
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
    em = (await _save_booking_email(ctx, a["email"]))["booking_email"] if a.get("email") else None   # Sasha 328 · with them, same record
    return {"saved": True, "name": saved.get("name") or name, "mobile_e164": saved.get("mobile_e164") or mobile,
            **({"booking_email": em} if em else {}),
            "how": f"Say in a few words that bookings go under {saved.get('name') or name}, then call hold_venue again for the same "
                   "booking (same details) — never ask for these again."}


async def _save_booking_email(ctx, raw: Any) -> dict:
    """Sasha 328 · the address they named for bookings — only as they wrote it this turn — on their ONE contact record."""
    from booking_signer import contacts as CT
    email = CT.email_of(raw)
    if not email:
        raise _err("email_invalid", "that isn't an email address — ask them for it; nothing was saved")
    if email not in str(ctx.user_said or "").lower():
        raise _err("not_their_words", "they didn't write that address this turn — ask them for it; never write one for them")
    r = await CT.set_booking_email(ctx.account, email)
    if not r.get("ok"):
        if r.get("rule") == "contact_first":
            raise _err("contact_first", "their booking name and mobile aren't saved yet — ask for them once (with the consent sentence), "
                                        "then call save_contact with name, mobile AND this email together")
        raise _err("not_saved", f"I couldn't save that — {r.get('message')}. Nothing was saved.")
    return {"saved": True, "booking_email": email,
            "how": f"Say in a few words that their bookings use {email} from now on (confirmations and cancel links go there). Nothing else."}


SAVE_CONTACT_DESC = ("When a booking needs their name and mobile (hold_venue said contact_missing) and they've just told you: save "
                     "them on their account (with the consent sentence you said), then call hold_venue again. Pass only what they "
                     "said — never make up a name or a number. On WhatsApp leave mobile out (or this_number) for this WhatsApp number. "
                     "When they name ONE email for their bookings (\"use x@y.com for my bookings\"), pass email (alone, or with the "
                     "name and mobile) — venues get that address from then on.")


def _says_route(fn):
    """Sasha 331 · the booking question, with AgAPI's route said ONCE in front of it (voice.route_line: how she'll book and why, from
    AgAPI's decision — never a guess) — on every answer hold_venue gives."""
    import functools

    @functools.wraps(fn)
    async def wrapped(ctx, a: dict) -> dict:
        ctx.route_dec = None
        return with_route_line(ctx, await fn(ctx, a))
    return wrapped


def with_route_line(ctx, out: dict) -> dict:
    """Sasha 331 · AgAPI's route line on the ONE booking question (awaiting_yes / choose_route), once per booking: `route_line` on the
    result, said by code in front of her reply (sasha.turn's told lines) on S2, WhatsApp and voice."""
    from app.agent import voice as V
    dec = getattr(ctx, "route_dec", None)
    if not isinstance(out, dict) or out.get("status") not in ("awaiting_yes", "choose_route") or not isinstance(dec, dict):
        return out
    if out.get("route") == "platform_book":   # CR 160 · CR 188 · AgAPI books it for them: its own line
        dec = {**dec, "route": "platform_book"}
    line = V.route_line(dec)
    held = _HELD.get(ctx.account) if out.get("status") == "awaiting_yes" else None
    if not line or (held and held.get("route_said") == line):
        return out
    if held is not None:
        held["route_said"] = line
    return {**out, "route_line": line}


@_says_route
async def hold_venue(ctx, a: dict) -> dict:
    """Prepare the booking → what AgAPI decided (venue.profile's decision, then venue.prepare_booking — Sasha 378 · CR 188): the
    read-back the yes binds to, the hand-over for a step only they may do, or AgAPI's words with the take-over. Nothing is sent."""
    from agapi.v0 import stale
    from agapi import test_venues as TV
    a = await TV.vet(ctx, a)   # Sasha 256 · the test venue: held for a test person only — a live person's hold naming it is refused
    GW = _API()
    held = _HELD.get(ctx.account)
    if held and held.get("rung") == "platform_choice" and \
            ((a.get("place_id") and a.get("place_id") == held.get("place_id")) or _base(a.get("name") or "") == _base(held.get("venue") or "")):
        # Sasha 328 · the walk's question about THIS booking is open: their words answer it — else it stands, asked once (never a new hold)
        got = await platform_answer(ctx, ctx.user_said)
        if got is not None:
            return got
        return {**held["out"], "same_read_back": "asked already — the options are buttons on their screen; never ask a new question"}
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
    asked = await _terms_asked(ctx, a)
    if asked is not None:   # Sasha 381 · a term the person didn't give: AgAPI names it, Sasha asks ONLY it — never guessed, never a card
        return asked
    rd = await _read(ctx, a)
    res = await _reservation(ctx, a, rd)   # a day / time that isn't one: when_invalid, as before (it names open_slot)
    at = res["when"].get("at") or ""   # Sasha 253 · G7 — none when the venue proposes
    now = datetime.now(timezone.utc)
    route = a.get("route")
    card = card_of(ctx.account, a.get("place_id"), a.get("name"))   # Sasha 213 · this venue's card, highlighted on screen
    if route == "no":
        return _with_card(card, {"status": "not_booking", "venue": rd["venue"]})
    link = _link_of(ctx, a)
    if link:   # Sasha 270 · CR 101 · a link THEY handed over: the venue engine's one classifier says whose it is
        return _with_card(card, await _person_link(ctx, a, rd, res, at, now, card, link))
    from agapi import venue_truth as VT
    place = place_of(rd, card, a)
    if place:   # Sasha 378 · AgAPI's venue.profile, read once and cached — its `decision` is the ONE route (never Sasha's own read)
        await engine_channel(place, listing=True)
    dec = VT.decision(place)   # Sasha 377 · CR 188: AgAPI's ONE decision (venue.profile → handoff.decide), every surface
    ctx.route_dec = dec   # Sasha 331 · the decision the route line is said from
    if kanoe_route(dec) and at and not _open_slot(ctx, a):   # Sasha 287 · a WhatsApp venue: AgAPI's gate decides who sends it
        return _with_card(card, await kanoe_whatsapp(ctx, a, rd, res, at, now, card, dec))
    return _with_card(card, await one_decision(ctx, a, rd, res, at, now, card, dec))


def _ask_terms(a: dict, missing: List[str], words: str = "") -> dict:
    """Sasha 381 · exactly the terms AgAPI's term_not_given names (CR 196), asked in her words — said by code (voice.yes_line).
    Sasha 381h · the time, when their words hold a bare hour without its side of the day: "9am or 9pm?" (agapi.said.unsure_hours)."""
    from agapi import said as SD
    from app.agent import voice as V
    terms = [m for m in missing if m in V.TERM_ASK]
    unsure = list((SD.unsure_hours(words) or [None])[-1] or []) or None if "time" in terms else None
    return {"status": "need_term", "terms": terms, "venue": a.get("name"), "booked": False, "ask": V.term_ask(terms, unsure),
            **({"unsure": unsure} if unsure else {}),
            "how": "Say `ask` word for word — nothing else. When they answer, call hold_venue again with it."}


CHECK_IN = "15:00"   # Sasha 253 · G8 — a stay's time is the hotel's check-in (the old flow's), never a term the person gives


def _words_of(ctx) -> str:
    """Their own words in this conversation: what they said before + this turn."""
    return "\n".join(x for x in (getattr(ctx, "said_before", "") or "", str(getattr(ctx, "user_said", "") or "")) if x)


def said_terms(ctx, a: dict) -> Dict[str, Any]:
    """Sasha 381 · the booking's terms THE PERSON SAID — their own words in this conversation (ctx.said_before + this turn), each read by
    agapi.said and matching the booking (a detail that can't be read plainly is not said). Reads only; WHICH terms are required is
    AgAPI's (term_not_given). A stay's time is its check-in, not theirs."""
    from agapi import said as SD
    words = _words_of(ctx)
    out: Dict[str, Any] = {}
    try:
        d = date.fromisoformat(str(a.get("day") or ""))
        if SD.day(words, d, _today(a.get("country"))):
            out["date"] = d.isoformat()
    except ValueError:
        pass
    hhmm = str(a.get("time") or "")[:5]
    if _nights(ctx, a):
        out["time"] = hhmm or CHECK_IN
    elif re.fullmatch(r"\d{2}:\d{2}", hhmm) and SD.time_(words, hhmm):
        out["time"] = hhmm
    try:
        n = int(a.get("party") or 0)
    except (TypeError, ValueError):
        n = 0
    if n >= 1 and SD.people(words, n):
        out["party"] = n
    return out


async def _terms_asked(ctx, a: dict) -> Optional[dict]:
    """Sasha 381 · CR 196 · before a booking is made on their instruction: what they said, and when they left something out, AgAPI's ONE
    mandate says which terms it needs (approvals.mandate with ONLY the said terms → term_not_given, missing [...]; nothing is recorded).
    → None (every term theirs: book) | the ask (exactly AgAPI's missing terms) | why nothing was sent. A quote (open_slot) books nothing."""
    from agapi import venue_submit as VS
    from booking_signer import agapi_mandate as AM
    if _open_slot(ctx, a):
        return None
    said = said_terms(ctx, a)
    if {"party", "date", "time"} <= set(said):
        return None
    venue = a.get("name")
    eu = await VS.end_user(ctx.account)
    if not eu:
        return {"status": "not_sent", "venue": venue, "booked": False,
                "say": "The booking system doesn't know you yet, so nothing was sent — ask me again in a minute."}
    got = await AM.for_booking(ctx, eu, str(getattr(ctx, "user_said", "") or "") or str(venue or ""), said)
    missing = [m for m in got.get("missing") or [] if m != "prepared_id"]   # the booking isn't prepared yet: that one is Sasha's to do
    if got.get("code") == "term_not_given" and missing:
        return _ask_terms(a, missing, _words_of(ctx))
    log.error("[venues] %s: a term wasn't said but AgAPI named none to ask (%s) — nothing sent", venue, got.get("code"))
    return {"status": "not_sent", "venue": venue, "booked": False, "say": got.get("why") or "Nothing was sent — tell me again."}


#: Sasha 377 · CR 188 · the routes AgAPI ACTS on (Kanoe sends, or places the call) on the person's ONE yes — read back first
ACT_ROUTES = ("send_form", "ask_then_send", "message")
CALL_ROUTES = ("call", "call_at_opening", "call_no_voice")


def agapi_d(dec: dict) -> dict:
    """Sasha 377 · CR 188 · AgAPI's ONE decision in the shape the act executors take (_via_agapi, _call_question, _said) — its route and
    its words only; NOTHING is decided here. (Sasha's own decider over its own channel read is deleted.)"""
    from agapi.booking_rules import booking_rules as BR
    route, btn, hours = dec.get("route"), dec.get("button") or {}, dec.get("hours") or {}
    action = ("fill_form_zero_touch" if route in ("send_form", "ask_then_send") else "fill_platform_form" if route == "platform_book"
              else "request_email" if route == "message" and str(dec.get("channel") or "").lower() == "email"
              else "request_whatsapp" if route == "message" else "call" if route in CALL_ROUTES else "prepared_link")
    # an act's words are said AFTER the yes (the read-back card comes first): the send's own "Sent. I'll tell you when they reply." — the
    # vendored phrase, words only; AgAPI's decision line ("…just say yes") is the card's, before it
    sent = route in ACT_ROUTES and (btn.get("sends") is True)
    return {"action": action, "say": "sent" if sent else "ask_call" if route in CALL_ROUTES else route,
            "say_text": BR.PHRASES["sent"] if sent else dec.get("say_text") or "", "decision_say": dec.get("say_text") or "", "rung": route,
            "takeover": {"say": BR.PHRASES["takeover"], "link": btn.get("link")},
            "ctx": {"venue": {k: hours.get(k) for k in ("opens_at", "open_now") if hours.get(k) is not None}}}


async def one_decision(ctx, a: dict, rd: dict, res: dict, at: Optional[str], now, card: Optional[dict], dec: Optional[dict]) -> dict:
    """Sasha 377 · CR 188 · THE ONE BOOKING PATH: AgAPI's decision, followed. Its act (Kanoe's form / email / WhatsApp, or the call) →
    venue.prepare_booking → its read-back → the person's ONE yes → venue.submit_booking (_via_agapi / _call_question). The platform →
    venue.prepare_booking decides platform_book (the read-back, the yes, Sasha books it) or the hand-over for the step only the person
    may do (follow). No route → the floor. Sasha chooses no channel and reads no person's switch."""
    if not dec or dec.get("route") in (None, "none"):
        return await follow(ctx, a, rd, res, at, now, card, dec or {"route": "none"})
    route = dec["route"]
    acts = (route in ACT_ROUTES and (dec.get("button") or {}).get("sends")) or route in CALL_ROUTES
    if not acts:   # the platform (platform_book or its hand-over), their own WhatsApp, reserve with Google, no reservations: AgAPI's words
        return await follow(ctx, a, rd, res, at, now, card, dec)
    d = agapi_d(dec)
    venue = _API().plain_venue(rd["venue"])
    if _open_slot(ctx, a) and (a.get("day") or route not in CALL_ROUTES):
        # G7 · a quote / "whenever they have space": AgAPI's act books a day AND a time — no slot to ask for, so nothing is sent:
        # Tyler's (Sasha 319), and a call is said plainly. Never Sasha's own email or call in its place.
        if route in CALL_ROUTES:
            return await _no_call(ctx, a, rd, res, at, now, d, card, venue, "a call needs a day and a time to ask them for")
        return _to_tyler(venue, d)
    if not at or _open_slot(ctx, a):   # an act books a day and a time — AgAPI's prepare needs both: ask for them, once
        return _said({"status": "need_day", "venue": rd["venue"],
                      "how": "Their booking needs a day and a time: ask them which (one short question), then hold_venue again."}, d)
    if route in CALL_ROUTES:
        return await _call_question(ctx, a, rd, res, at, now, d, card)
    got = await _via_agapi(ctx, a, rd, res, at, now, d, card, **({"stay": _stay(ctx, a)} if _nights(ctx, a) else {}))
    if got is None and _nights(ctx, a):   # no booking service here: a stay is never Sasha's own email (its call would be nobody's)
        return await _no_engine(ctx, rd, d, venue)
    return got if got is not None else _to_tyler(venue, d)   # no booking service on this server: nothing sent


async def follow(ctx, a: dict, rd: dict, res: dict, at: Optional[str], now, card: Optional[dict], dec: dict, refused: bool = False) -> dict:
    """Sasha 284 · S2 FOLLOWS AGAPI'S DECISION (venue.profile → handoff.decide: route · say_text · button) through the ONE hand-over path
    (283): with a slot, venue.prepare_booking prepares it (nothing is sent) and its page goes to their screen and phone with the way
    back; without one, venue.profile's button as given. Either way the row the way back reads is written. Never re-decided here."""
    GW = _API()
    venue = GW.plain_venue(rd["venue"])
    link = (dec.get("button") or {}).get("link") or (card or {}).get("website")
    prep = None
    if _nights(ctx, a) and at and dec.get("route") in ("platform", "none") and "link" in (rd.get("rungs") or {}):
        # Sasha 138 · CR 188 · a hotel's own booking engine with the stay in its link — ONLY where AgAPI's decision hands it over (platform)
        # or has none: read back, and on their yes to their phone. Never in place of an act AgAPI decided.
        return await _page(ctx, a, rd, res, at)
    if at and not _open_slot(ctx, a) and dec.get("route") in ("platform_book", "platform") and not refused:
        # Sasha 328 · CR 160 · CR 188 · a platform venue: venue.prepare_booking WITH this person decides whether AgAPI books it (route
        # platform_book — its read-back, their yes, AgAPI presses Book) or hands over the step only they may do (that prepared booking).
        got = await _platform_book(ctx, a, rd, res, at, card, dec)
        if got.get("status"):
            return got
        prep = got.get("prep")
    if at and not _open_slot(ctx, a) and link:
        held = await _prepared(ctx, a, rd, res, at, now, {"kind": "agapi", "url": link, "name": dec.get("channel")}, card)
        if held.get("status") == "awaiting_yes" and ctx.account in _HELD:
            _HELD[ctx.account]["follow"] = {"decision": dec, "refused": refused}
            if prep:   # Sasha 328 · prepared once: the hand-over uses it (never a second venue.prepare_booking for the same booking)
                _HELD[ctx.account]["prep"] = prep
            out = await _finish(ctx, _HELD[ctx.account])
            out["how"] = "Say `say` exactly — never that it's booked."
            return out
    from app.agent import voice as V
    from agapi import itinerary as IT
    if not link:   # Sasha 286 · nothing of AgAPI's to hand over: THE FLOOR (never "send me their link")
        return await floor_out(ctx, a, rd, res, card, None, at)
    await note_prepared(ctx.account, venue, at or str(a.get("day") or "")[:10], res["how_many"]["count"], link,
                        platform=IT.platform_name(dec.get("channel"), (dec.get("button") or {}).get("label")), place_id=rd.get("place_id"))
    return {"status": "page_link", "venue": venue, "booked": False, "route": dec["route"], **_link_out(link),
            "button": {"label": V.OPEN_THEIR_PAGE if refused else (dec.get("button") or {}).get("label"), "link": link},
            # Sasha 284b (live, Boys Don't Cry — a quote, no slot): nothing was prepared here, so neither AgAPI's words ("I've written it")
            # nor FINISH_IT ("your booking ready") — the plain hand-over: their way in, and the way back
            "say": V.REACH_THEM + " Say exactly that — never that it's booked."}


# ── Sasha 328 · CR 160 · THE PLATFORM BOOKING LOOP: AgAPI fills the platform's form and presses Book, on the person's ONE yes ────────────
# ONE booking path: venue.prepare_booking (VS.prepare, with booking_person — ONCE) → venue.submit_booking's read-back → their yes →
# book_venue → _finish → _agapi_send → VS.submit. Sasha 329 · CR 161: when the walk stops to ask THE PERSON (venue.submit_booking failed
# with ask {choice, label, options} — their "Zona": Salón Interior or Terraza 1?), it is asked ONCE, AgAPI's options as taps, and their
# pick goes back as `choices` {<ask.choice>: <option>} on venue.submit_booking with the SAME prepared_id (its read-back, then the yes).
# Never `answers` on a second venue.prepare_booking (Sasha 328's path, deleted). docs/sasha/S-329-cr161.md.
PLATFORM_ACTION = "fill_platform_form"   # booking-rules/3.0's action where the platform permits a submit (route platform_book)


async def _platform_book(ctx, a: dict, rd: dict, res: dict, at: str, card: Optional[dict], dec: dict) -> dict:
    """venue.prepare_booking with this person. AgAPI decided platform_book (CR 188: for everyone) → its read-back, held for their yes:
    the awaiting_yes card. Anything else → {"prep": that prepared booking} (the hand-over uses it) or {} (not prepared)."""
    from agapi import itinerary as IT, venue_submit as VS
    GW = _API()
    venue = GW.plain_venue(rd["venue"])
    place = {"name": (card or {}).get("name") or venue, "website": (card or {}).get("website") or a.get("website"),
             "place_id": rd.get("place_id") or (card or {}).get("place_id"), "city": a.get("city"), "category": (res.get("what") or {}).get("category")}
    person = await booking_person(ctx.account, res)
    p = await VS.prepare(ctx.account, place, person, at[:10], at[11:16], int(res["how_many"]["count"]))
    if not p.get("ok"):
        return {}
    prep = {k: p[k] for k in ("link", "say", "human_step", "missing", "expires_at", "decision", "hand_over", "prepared_id") if p.get(k) is not None} \
        if str(p.get("link") or "").startswith("https://") else None
    pdec = p.get("decision") if isinstance(p.get("decision"), dict) else {}
    if pdec.get("route") != "platform_book":
        return {"prep": prep}
    ho = p.get("hand_over") if isinstance(p.get("hand_over"), dict) else {}
    page = ho.get("link") if _platform_page(ho.get("link")) else (p.get("link") if str(p.get("link") or "").startswith("https://") else None)
    platform = ho.get("platform") or IT.platform_name(dec.get("channel"), (dec.get("button") or {}).get("label")) or "their booking page"
    return await _act(ctx, "agapi", p, rd, res,
                      extra={"agapi_action": PLATFORM_ACTION, "platform_book": True, "platform": platform,
                             **({"link": page} if page else {}), "booking": {k: v for k, v in a.items() if k not in _NOT_BOOKING},
                             "category": (res.get("what") or {}).get("category")})


def _option_named(held: dict, words: Optional[str]) -> Optional[str]:
    """Their words (or a tap's) name exactly ONE of AgAPI's options — the option as AgAPI wrote it; else None (never a guess)."""
    from agapi.venue_submit import _fold
    b = lambda x: _fold(_base(str(x or ""))).strip()   # noqa: E731 · "salon interior" names "Salón Interior"
    w = b(words)
    if not w:
        return None
    opts = list(held.get("options") or [])
    exact = [o for o in opts if b(o) == w]
    if len(exact) == 1:
        return exact[0]
    named = [o for o in opts if b(o) and f" {b(o)} " in f" {w} "]
    return named[0] if len(named) == 1 else None


def _platform_question(ctx, held: dict, q: dict, venue: str, r: dict) -> dict:
    """The walk stopped on a question only the PERSON can answer (CR 161's ask): asked ONCE — AgAPI's label, its options as buttons
    (exactly AgAPI's), on the channel they asked on (Sasha 326: work in progress is the turn's own answer). Held for their pick (15 min)."""
    import hashlib as _h
    from app.agent import voice as V
    qid = "q_" + _h.sha256(f"{held.get('prepared_id')}|{q['choice']}|{'|'.join(q['options'])}".encode()).hexdigest()[:24]
    choices = [{"title": o, "route": "pick:" + o} for o in q["options"]]
    ask = V.platform_choice_ask(venue, q["label"], q["options"])
    out = {"status": "awaiting_yes", "venue": venue, "when": held.get("summary"), "booked": False, "route": "platform_book",
           "question": q["label"], "ask": ask, "say": ask, "choices": choices, "read_back_id": qid, "read_back": [],
           "how": "Say `ask` word for word — the options are buttons on their screen. Never choose for them. When they answer (a tap, or "
                  "their words naming ONE option), call book_venue for this same booking; nothing else is asked."}
    _HELD[ctx.account] = {**{k: v for k, v in held.items() if k not in ("out",)}, "rung": "platform_choice", "id": qid, "read_back_id": qid,
                          "choice": q["choice"], "field": q["label"], "options": list(q["options"]), "asked_at": datetime.now(timezone.utc),
                          "base": held.get("base") or held.get("same"), "failed_act": r.get("act_id"), "out": out}
    return out


async def platform_answer(ctx, words: Optional[str], tapped: bool = False) -> Optional[dict]:
    """Their answer to the walk's question (a tap on its card, or their words) → venue.submit_booking on the SAME prepared booking with
    choices {ask.choice: option} → AgAPI's read-back, now with their choice → sent. Their pick from the app or their verified WhatsApp, to
    the question about THIS booking whose read-back they already said yes to, is the yes (Sasha 314's rule: their own instruction, claimed
    once) — but only when the new read-back is exactly those words plus their choice; otherwise the new read-back is shown and their next
    yes sends it. None: nothing asked (or their words name no option)."""
    from agapi import venue_submit as VS
    from agapi.v0 import stale
    held = _HELD.get(ctx.account)
    if not held or held.get("rung") != "platform_choice":
        return None
    opt = _option_named(held, words)
    if opt is None:
        return None
    if stale(held.get("asked_at")):
        _HELD.pop(ctx.account, None)
        raise _err("read_back_stale", "that was asked over 15 minutes ago — call hold_venue again for the same booking")
    GW = _API()
    venue = GW.plain_venue(held["venue"])
    choices = {**(held.get("choices") or {}), held["choice"]: opt}
    nxt = {**{k: v for k, v in held.items() if k not in ("out", "field", "options", "asked_at", "failed_act", "choice", "mandate_id")},
           "rung": "agapi", "id": held["prepared_id"], "choices": choices}   # the SAME prepared booking, with their answer
    if held.get("failed_act"):   # the stop that asked is not a booking (My bookings skips it); the booking is the act that follows
        await VS._amend(ctx.account, held["failed_act"], question=held["choice"], answered=opt)
    # Sasha 381 · their answer is the term only they could give: with it the instruction is complete — its turn is the proof (CR 196) —
    # and acted on, never a new card
    asked = await _instruction(ctx, nxt)
    if asked is not None:
        _HELD.pop(ctx.account, None)
        return asked
    if not await claim_words(ctx, f"platform_choice|{held['id']}|{opt}"):
        _HELD.pop(ctx.account, None)
        return {"status": "already_sent", "venue": venue, "line": f"I've already sent your {held['field']} to {venue}.",
                "how": "Say `line` word for word — nothing else."}
    return await _finish(ctx, nxt, {"how": "tap" if tapped else "words", "said": f"{held['field']}: {opt}"}, claimed=True)


async def _platform_result(ctx, held: dict, r: dict, venue: str, where) -> dict:
    """AgAPI pressed Book (or stopped): booked → ONE line with venue, day, time, people, what they chose and the reference, said where they
    asked (this turn's answer); its act, with the reference, is in My bookings (VS.submit kept it). The walk's question (ask) → asked once.
    Any other stop, or the same question after their answer → nothing is booked: said, with their page and their details ready."""
    from agapi import venue_submit as VS
    in_app = {"in_app": True} if VS.TAP.get() is not None else {}
    area = ", ".join(str(v) for v in (held.get("choices") or {}).values())
    if r.get("status") == "confirmed":
        ref = r.get("reference")
        return {"status": "confirmed", "venue": venue, "when": held["summary"], "itinerary": where, "route": "platform",
                **({"platform": held["platform"]} if held.get("platform") else {}), **({"area": area} if area else {}),
                **({"reference": ref} if ref else {}), "act_id": r.get("act_id"), "line": _acted(held, r, True, ref), **in_app,
                "how": "Say `line` word for word, then at most ONE short question (e.g. the calendar) — nothing else."}
    q = VS.ask_of(r)
    asked = {str(k).casefold() for k in (held.get("choices") or {})}
    if q and q["choice"].casefold() not in asked:
        return _platform_question(ctx, held, q, venue, r)
    link = (r.get("hand_over") or {}).get("link") if isinstance(r.get("hand_over"), dict) else None
    link = link if str(link or "").startswith("https://") else held.get("link")
    if q:   # asked once: the same question after their answer is never asked twice (never a loop) — said, with their page
        say = (f"Their booking still asks for {q['label']} after I gave {area}, so I stopped before Book — nothing is booked. "
               "Their page has your details ready.")
    else:
        say = str(r.get("say") or f"{venue}'s page stopped me before Book — nothing is booked.")
    return {"status": "not_booked", "venue": venue, "when": held["summary"], "booked": False, "route": "platform", "say": say,
            **_link_out(link), **in_app, "how": "Say `say` word for word — nothing is booked."}


def kanoe_route(dec: Optional[dict]) -> bool:
    """Sasha 287 · AgAPI decided this venue books by a WhatsApp message (handoff.decide route message, channel WhatsApp)."""
    return bool(dec) and dec.get("route") == "message" and dec.get("channel") == "WhatsApp"


async def kanoe_whatsapp(ctx, a: dict, rd: dict, res: dict, at: str, now, card: Optional[dict], dec: Optional[dict]) -> dict:
    """Sasha 287 · KANOE'S WHATSAPP (beta). The ONE place S2 reads AgAPI's gate (venue_messages.kanoe_send_allowed): venue.prepare_booking
    with the person (end_user) → its decision's sender — "kanoe" only when the gate says yes for THIS person — then venue.submit_booking's
    read-back (the gate again). Then THE CONSENT RULE (kanoe_card): their own words gave venue, day, time and people → sent now, one line;
    S2 filled any in → ONE line asks ("Casa, Friday 21:00 for 2. Shall I send?"), never the message's text. Any no from the gate → the
    same line as their own WhatsApp (285's hand-over). S2 has no flag, no list and no sender of its own here."""
    from agapi import venue_submit as VS
    GW = _API()
    venue = GW.plain_venue(rd["venue"])
    place = {"name": (card or {}).get("name") or venue, "website": (card or {}).get("website") or a.get("website"),
             "place_id": rd.get("place_id") or (card or {}).get("place_id"), "city": a.get("city"), "category": (res.get("what") or {}).get("category")}
    person = await booking_person(ctx.account, res)   # Sasha 328 · the ONE person (its booking email)
    p = await VS.prepare(ctx.account, place, person, at[:10], at[11:16], int(res["how_many"]["count"]))
    pdec = p.get("decision") if p.get("ok") and isinstance(p.get("decision"), dict) else (dec or {})
    own = own_link(pdec, p)
    if not p.get("ok") or pdec.get("sender") != "kanoe":   # AgAPI's gate: not this person (or not prepared) — their own WhatsApp
        return await own_whatsapp(ctx, a, rd, res, at, card, own, pdec if pdec.get("sender") == "person" else None,
                                  prepared_id=p.get("prepared_id") if p.get("ok") else None)
    # Sasha 381 · AgAPI's gate again at the ONE submit: a no there is _kanoe_sent's hand-over (their own WhatsApp)
    return await _act(ctx, "agapi", p, rd, res, extra={"agapi_action": "request_whatsapp", "kanoe": True, "own": own,
                                                          "category": (res.get("what") or {}).get("category")})


def _today(country: Optional[str]) -> date:
    from zoneinfo import ZoneInfo
    from booking_signer import venue_read as VR
    return datetime.now(ZoneInfo((VR.COUNTRIES.get(str(country or "").upper()) or (None, None, None, "Europe/Madrid"))[3])).date()


def own_link(dec: Optional[dict], p: Optional[dict] = None) -> Optional[str]:
    """Their own WhatsApp, prefilled (AgAPI's wa.me link: the decision's WhatsApp option, its button, or prepare's person_send)."""
    d = dec or {}
    for u in [o.get("link") for o in d.get("options") or [] if o.get("kind") == "whatsapp"] + [(d.get("button") or {}).get("link"),
                                                                                                  ((p or {}).get("person_send") or {}).get("whatsapp")]:
        if str(u or "").startswith("https://wa.me/"):
            return u
    return None


async def own_whatsapp(ctx, a: dict, rd: dict, res: Optional[dict], at: Optional[str], card: Optional[dict], link: Optional[str],
                       dec: Optional[dict], prepared_id: Optional[str] = None) -> dict:
    """Sasha 287 · the same card when Kanoe may not send it: their own WhatsApp, prefilled (AgAPI's wa.me link and its button label), in
    her words (voice.OWN_WHATSAPP — AgAPI's line names the channel; `dec` is kept for the record). Never "can't". No link: THE FLOOR (286)."""
    from app.agent import voice as V
    from agapi import venue_submit as VS
    if not link:
        if dec and dec.get("route") not in (None, "none"):   # Sasha 289 · AgAPI's route with no way to take it (Mano Santa): said, never silent
            log.warning("[venues] %s: AgAPI decided %s/%s (sender %s) with no link to send it — the floor", _API().plain_venue(rd["venue"]),
                        dec.get("route"), dec.get("channel"), dec.get("sender"))
        return await floor_out(ctx, a, rd, res, card, None, at)
    venue = _API().plain_venue(rd["venue"])
    party = ((res or {}).get("how_many") or {}).get("count") or a.get("party") or 0
    await note_prepared(ctx.account, venue, at or str(a.get("day") or "")[:10], party, link, route="your_whatsapp",
                        place_id=rd.get("place_id"), prepared_id=prepared_id)   # the way back (283) · Sasha 300: the itinerary's route
    say = V.OWN_WHATSAPP   # her voice: AgAPI's message line names and limits the channel ("takes booking requests by WhatsApp")
    return {"status": "page_link", "venue": venue, "booked": False, "route": "message", **_link_out(link),
            "button": {"label": V.SEND_ON_WHATSAPP, "link": link}, "page_says": say,   # in the app: said by code (voice.page_line)
            # Sasha 298 · found live: without `in_app` page_line said nothing and the MODEL said it — splicing the drafted message into
            # her line ("…they'll reply to you. Would you have space? Thanks.\" It isn't booked…"). In the app: by code, word for word.
            **({"in_app": True} if VS.TAP.get() is not None else {}),
            "say": say + " Say exactly that — never that it's booked."}


def floor(card: Optional[dict], rd: dict, dec: Optional[dict] = None) -> dict:
    """Sasha 286 · THE FLOOR — S2's ONE last resort (Tyler, 24 Oct 08:06: she never asks for a link; the worst case is ALWAYS a
    hand-over). AgAPI's own floor when its decision gives one (route none: its say_text and its button — CR 118c), unless it asks for a
    link; else THEIR WEBSITE as the button (the place card S2 holds: venue.discover's link / Places' website), else their listing; the
    listing's WhatsApp and number beside it. Never empty: a listing link is built from the name and place_id."""
    from urllib.parse import quote as _q
    from app.agent import voice as V
    c, rungs = card or {}, rd.get("rungs") or {}
    phone = str(c.get("phone") or (rungs.get("phone") or {}).get("value") or "").strip()
    wa = re.sub(r"\D", "", str((rungs.get("whatsapp") or {}).get("value") or ""))
    alts = ([{"label": "WhatsApp", "link": f"https://wa.me/{wa}"}] if wa else []) + \
        ([{"label": "Their number", "link": "tel:" + re.sub(r"[^\d+]", "", phone)}] if re.sub(r"\D", "", phone) else [])
    b = (dec or {}).get("button") or {}
    if dec and dec.get("route") == "none" and dec.get("say_text") and not V.asks_for_link(dec["say_text"]) \
            and str(b.get("link") or "").startswith("http"):
        return {"say": dec["say_text"], "button": {"label": b.get("label") or V.OPEN_LISTING, "link": b["link"]}, "alternatives": alts,
                "from": "agapi"}
    site = next((u for u in (c.get("website"), c.get("link")) if str(u or "").startswith("http")), None)
    if site:
        return {"say": V.floor_line("website"), "button": {"label": V.OPEN_WEBSITE, "link": site}, "alternatives": alts, "from": "sasha"}
    name, pid = c.get("name") or rd.get("venue") or "", c.get("place_id") or rd.get("place_id")
    listing = c.get("listing_url") if str(c.get("listing_url") or "").startswith("http") else \
        f"https://www.google.com/maps/search/?api=1&query={_q(str(name))}" + (f"&query_place_id={_q(str(pid))}" if pid else "")
    return {"say": V.floor_line("listing"), "button": {"label": V.OPEN_LISTING, "link": listing}, "alternatives": alts, "from": "sasha"}


async def floor_out(ctx, a: dict, rd: dict, res: Optional[dict], card: Optional[dict], dec: Optional[dict] = None,
                    at: Optional[str] = None) -> dict:
    """Sasha 286 · the floor, handed over: the button on their screen (the hand-over card) and the row 283's way back reads."""
    f = floor(card, rd, dec)
    venue = _API().plain_venue(rd["venue"])
    party = ((res or {}).get("how_many") or {}).get("count") or a.get("party") or 0
    await note_prepared(ctx.account, venue, at or str(a.get("day") or "")[:10], party, f["button"]["link"], route="their_page",
                        place_id=rd.get("place_id"))
    return {"status": "page_link", "venue": venue, "booked": False, "floor": f, **_link_out(f["button"]["link"]),
            "button": f["button"], "say": f["say"] + " Say exactly that — never that it's booked."}


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
        d = agapi_d({"route": "send_form", "button": {"link": link, "sends": True}})   # Sasha 377 · AgAPI's classifier said Kanoe's form
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


async def _call_question(ctx, a: dict, rd: dict, res: dict, at: str, now, d: dict, card: Optional[dict]) -> dict:
    """Sasha 265 · item 4 (CR 99 §4b) · the call: venue.prepare_booking with the venue's call {phone, opens_at, open_now}, then
    venue.submit_booking route "call" → the call's read-back. Sasha 381: no card — the instruction IS the approval, the call act at once
    (_act), said in Tyler's ONE line."""
    from agapi import venue_submit as VS
    GW = _API()
    venue = GW.plain_venue(rd["venue"])
    place = {"name": (card or {}).get("name") or venue, "website": (card or {}).get("website") or a.get("website"),
             "place_id": rd.get("place_id") or (card or {}).get("place_id"), "city": a.get("city"), "category": (res.get("what") or {}).get("category")}
    v = (d.get("ctx") or {}).get("venue") or {}
    call = call_of(rd, card, place.get("place_id"))   # Sasha 272 · CR 103: once, here — a listing as its place_id, never its number
    if not call:
        return await _no_call(ctx, a, rd, res, at, now, d, card, venue, "there's no number for them to call")
    call = {**call, **({"opens_at": v["opens_at"]} if v.get("opens_at") else {}), "open_now": bool(v.get("open_now"))}
    person = await booking_person(ctx.account, res)   # Sasha 328 · the ONE person (its booking email)
    p = await VS.prepare(ctx.account, place, person, at[:10], at[11:16], int(res["how_many"]["count"]), call=call,
                         **({"stay": _stay(ctx, a)} if _stay(ctx, a) else {}))   # Sasha 271 · CR 102: a stay's call says the stay
    if not p.get("ok") and p["error"]["code"] == "not_configured":   # no venues key on this server: no act — so no call (never the old path)
        return await _no_call(ctx, a, rd, res, at, now, d, card, venue, "calls go through the booking service, which isn't on here")
    if not p.get("ok"):
        raise _err("not_prepared", f"{venue} couldn't be prepared from here right now — {p['error']['message']}. " + d["takeover"]["say"])
    link = p.get("link") if str(p.get("link") or "").startswith("https://") else d["takeover"].get("link")
    return await _act(ctx, "agapi_call", p, rd, res,
                      extra={"link": link, "call": call, "name": res["who"]["name"], "place_id": place.get("place_id"),
                             "booking": {k: v for k, v in a.items() if k not in _NOT_BOOKING}}, d=d)


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
    """Sasha 265 · Sasha 378 (CR 188) · a call AgAPI decided that the act can't make (why): said plainly, with AgAPI's take-over — never a
    channel of Sasha's own choosing in its place (the page fallback is gone). Never Sasha's own call."""
    raise _err("no_route", f"{venue} books by phone, and I can't call them from here — {why}. " + d["takeover"]["say"])


async def answer_card(ctx, read_back_id: str, choice: str) -> dict:
    """Sasha 265 · item 4 · THE TAP: the card's button, straight from the page (no model between). "call" → the tap IS the approval
    (approvals.in_app_tap on THIS read-back) → the act → "On it — …". "page" → their prepared page (nothing sent, no approval)."""
    held = _HELD.get(ctx.account)
    if str(choice or "").startswith("pick:"):   # Sasha 328 · a tap on the platform question's card: THAT card's option, as AgAPI wrote it
        if not held or held.get("rung") != "platform_choice" or held.get("read_back_id") != read_back_id:
            return {"status": "nothing_waiting", "booked": False, "in_app": True}
        got = await platform_answer(ctx, choice[5:], tapped=True)
        return got if got is not None else {"status": "nothing_waiting", "booked": False, "in_app": True}
    return {"status": "nothing_waiting", "booked": False, "in_app": True}   # Sasha 381 · a venue act has no card: nothing else to tap


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
    GW = _API()
    venue = GW.plain_venue(rd["venue"])
    place = {"name": (card or {}).get("name") or venue, "website": (card or {}).get("website") or a.get("website"), "place_id": rd.get("place_id") or (card or {}).get("place_id"),
             "city": a.get("city"), "category": (res.get("what") or {}).get("category")}
    person = await booking_person(ctx.account, res)   # Sasha 328 · the ONE person (its booking email)
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
    link = p.get("link") if str(p.get("link") or "").startswith("https://") else d["takeover"].get("link")
    return await _act(ctx, "agapi", p, rd, res,
                      extra={"link": link, "agapi_action": d["action"],
                             **({"call_source": call["source"], **({"place_id": call["place_id"]} if call.get("place_id") else {})}
                                if call else {}),   # its source (and a listing's place_id) only, never a number
                             **({"link_handed": link} if link else {}), **({"stay": stay} if stay else {}),
                             "category": (res.get("what") or {}).get("category")}, d=d)


async def _no_engine(ctx, rd: dict, d: dict, venue: str) -> dict:
    """Sasha 271 · a hotel stay with no booking service on this server: said, with the take-over — never Sasha's own room email (the
    call the rules attach to it would be nobody's)."""
    raise _err("no_route", f"I can't ask {venue} for the room from here right now. " + d["takeover"]["say"])


def refused_words(venue: str, agapi_say: Optional[str]) -> str:
    """Sasha 380 · AgAPI didn't send a booking (venue.submit_booking status not_allowed): AgAPI's reason is LOGGED (its own sentence,
    never lost again), and she hands over the page AgAPI prepared in her voice — voice.FINISH_IT, never "can't" (Sasha 288, rule 15)
    and never a reason of Sasha's own about the person or their account (the old no_real_sends phrase, "…yet on this account")."""
    from app.agent import voice as V
    w = " ".join(str(agapi_say or "").split())
    log.warning("[venues] AgAPI didn't send the booking at %s: %s", venue, w[:300] or "(no words)")
    return V.FINISH_IT


def _link_out(link: Optional[str]) -> dict:
    """The take-over link, drawn on their screen (the hand-over card) — or, when there is none, said plainly: never a page that
    isn't there (the rules' phrase offers "their page")."""
    if link:
        return {"open": link, "page_url": link}
    return {"no_page": "there is no page of theirs to give — say you can't contact them from here and that they can take it over; "
                       "never say a page is on their screen"}


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
    """Sasha 248 · Sasha 378 (CR 188) · AgAPI's venue.profile for this place, read once and cached (agapi/venue_truth) — the same read
    its card and detail sheet show — and how it books: AgAPI's ONE decision (VT.channel). None: no site and no listing, or no decision."""
    import asyncio
    from agapi import venue_truth as VT
    if not card or not (card.get("website") or (listing and card.get("place_id"))):   # Sasha 270 · listing: the one path, no website
        return None
    try:
        p = await asyncio.wait_for(VT.profile(card, listing=listing), timeout=budget_s)
    except Exception:
        p = VT.shape(card, VT.cached(card))
    return p.get("channel")


async def _prepared(ctx, a: dict, rd: dict, res: dict, at: str, now, eng: dict, card: Optional[dict]) -> dict:
    """"Fill it now", until AgAPI's venue.prepare_booking is live: their OWN booking page (the engine's evidence) on their phone,
    with every detail shown and one-tap copy — they confirm there (a CAPTCHA, if any, is theirs). Read back first; on the yes,
    book_venue sends it. The attempt goes in the outcomes ledger as human_tap."""
    import hashlib as _h
    GW = _API()
    url = eng.get("url") or (card or {}).get("website")
    if not url:
        return {"status": "no_route", "venue": rd["venue"], "say": "Their booking page isn't on their site — ask how they'd like to book."}
    email = (await booking_person(ctx.account, res))["email"]   # Sasha 328 · the ONE booking email, as AgAPI is given it
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


async def _act(ctx, rung: str, p: dict, rd: dict, res: dict, extra: Optional[dict] = None, d: Optional[dict] = None) -> dict:
    """Sasha 381 · THE INSTRUCTION IS THE APPROVAL (Tyler, KANOE_DECISIONS 12 Nov 20:11 — no separate yes; CR 196): AgAPI's prepared booking
    → the person's instruction recorded as its approval (approvals.mandate scope.booking — _instruction) → ONE venue.submit_booking
    {prepared_id, mandate_id}, in this turn, ONCE (claimed on the conversation and the booking's terms). Said in ONE line: AgAPI's
    instructed.say ("Booking now: <venue>, <N> people, <date> at <time>.") then the outcome. No read-back card, no tap. Every venue act
    comes here: Kanoe's form / email / WhatsApp, the call, the platform's Book."""
    import hashlib as _h
    from agapi.v0 import ToolError, claim
    GW = _API()
    venue = GW.plain_venue(rd["venue"])
    held = {"rung": rung, "id": p["prepared_id"], "at": datetime.now(timezone.utc), "venue": rd["venue"],
            "summary": GW.summary(res), "place_id": rd.get("place_id"), "country": rd.get("country") or (res.get("where") or {}).get("country"),
            "when": res["when"].get("at") or "", "party": res["how_many"]["count"], "sector": (res.get("what") or {}).get("category"),
            "prepared_id": p["prepared_id"], **(extra or {})}
    asked = await _instruction(ctx, held)
    if asked is not None:   # a term AgAPI says they didn't give → asked (only it); or the instruction wasn't taken → said, nothing sent
        return asked
    words = str(getattr(ctx, "user_said", "") or "")
    was = (ctx.idem, getattr(ctx, "act_name", None))
    # ONE booking, acted on ONCE in a conversation: its terms (the venue, the slot, the people) are the key — a later turn that holds the
    # same booking again (the same words resent, "did you book it?") never sends a second time; it's "already sent", with its status
    ctx.idem = "booking:" + _h.sha256(f"{ctx.account}|{getattr(ctx, 'session', '') or ''}|{_base(rd['venue'])}|{held['when']}|"
                                      f"{held['party']}".encode()).hexdigest()
    ctx.act_name = None   # claimed once before anything is sent (never the card's yes rule: there is no card)
    try:
        await claim(ctx)
    except ToolError as e:
        log.info("[venues] %s: the same instruction again (%s) — never a second send", venue, e.code)
        return await _tap_refused(ctx, held, "approval_consumed", {}, venue)
    finally:
        ctx.idem, ctx.act_name = was
    held["consent"] = {"kind": "instruction", "said": words[:300]}
    out = await _finish(ctx, held, {"how": "instruction", "said": words[:300]}, claimed=True)
    out.setdefault("route", rung)
    if out.get("status") in ("confirmed", "requested", "calling"):   # Tyler's ONE line: said by code, word for word (voice.yes_line)
        out["acted"] = True
    if d is not None:   # R11 · every answer carries the rules and the take-over (data on the answer; her line is Tyler's)
        out.update(rules=_rules(d), takeover=d["takeover"])
    return out


async def _instruction(ctx, held: dict) -> Optional[dict]:
    """Sasha 381 · CR 196 · THIS turn's instruction, recorded at AgAPI as the approval of THIS prepared booking (agapi_mandate.for_booking:
    the person's own party / date / time, the door's proof of the turn). → None when recorded (held["mandate_id"] set); else what to say —
    a term AgAPI says they didn't give, asked (only it: "For how many people?"), or why nothing was sent."""
    from agapi import venue_submit as VS
    from booking_signer import agapi_mandate as AM
    eu = held.get("end_user") or await VS.end_user(ctx.account)
    if not eu:
        return {"status": "not_sent", "venue": _API().plain_venue(held["venue"]), "booked": False,
                "say": "The booking system doesn't know you yet, so nothing was sent — ask me again in a minute."}
    held["end_user"] = eu
    words = str(getattr(ctx, "user_said", "") or "").strip() or held.get("summary") or held["venue"]
    got = await AM.for_booking(ctx, eu, words, {"prepared_id": held["prepared_id"], "party": held["party"],
                                                "date": str(held["when"])[:10], "time": str(held["when"])[11:16]})
    if got.get("mandate_id"):
        held["mandate_id"] = got["mandate_id"]
        return None
    if got.get("code") == "term_not_given" and got.get("missing"):
        return _ask_terms({"name": _API().plain_venue(held["venue"])}, got["missing"], _words_of(ctx))
    return {"status": "not_sent", "venue": _API().plain_venue(held["venue"]), "booked": False,
            "say": got.get("why") or "Nothing was sent — ask me again."}


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
                          "sector": (res.get("what") or {}).get("category"), **(extra or {}),   # CR 87 · the sector, for the outcomes ledger
                          # Sasha 331 · the same booking held again: its route line was already said (never twice)
                          **({"route_said": prev["route_said"]} if prev and prev.get("route_said") and at == prev.get("at") else {})}
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
    # Sasha 330 · the card's id (AgAPI's read_back_id, else this read-back's own sha): its Yes / No (sasha.yes_buttons) answer THIS one only
    out["read_back_id"] = str((extra or {}).get("read_back_id") or read_back["sha256"])[:80]
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
    q = _HELD.get(ctx.account)
    if q and q.get("rung") == "platform_choice":   # Sasha 328 · the walk's question is open: their words answer it (or it's asked again)
        got = await platform_answer(ctx, getattr(ctx, "user_said", None) or ((a.get("approval") or {}).get("said")))
        if got is not None:
            return got
        raise _err("which_option", f"their booking asks for {q['field']}: {', '.join(q['options'])} — the options are buttons on their "
                                   "screen; ask them which (never choose for them), then call book_venue with their answer this turn")
    said = ((a.get("approval") or {}).get("said")) or ""
    if not yes_to_book(said):
        raise _err("no_explicit_yes", "booking needs the person's explicit yes in this turn — ask them, then call book_venue")
    held = _HELD.get(ctx.account)
    from agapi import venue_submit as VS
    if not held:
        sent = await last_sent(ctx.account)
        if sent:   # Sasha 258 · the same yes again: already sent — said, with its status; never sent twice (Sasha 381h · read from the record)
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


async def _finish(ctx, held: dict, how: Optional[dict] = None, claimed: bool = False) -> dict:
    """Book what's held, once: claimed, recorded in the outcomes ledger (CR 87), its card with it. book_venue after a yes; a
    prefilled form straight away (Sasha 249 — the form is their go-ahead). `claimed`: already claimed by its caller (Sasha 328 · the
    platform question's answer: claim_words, the one-instruction rule)."""
    from agapi.v0 import claim
    GW = _API()
    if how and not claimed:   # an act on their yes: claimed first (a prefilled form sends nothing to the venue — nothing to claim)
        await claim(ctx)   # Sasha 215 · durable: sent once, across restarts and workers
    how = how or {"how": "chose_form", "said": "prefilled form"}
    venue, rung = GW.plain_venue(held["venue"]), held["rung"]
    _HELD.pop(ctx.account, None)
    card = card_of(ctx.account, held.get("place_id"), venue)
    from agapi import s2_outcomes as OC   # CR 87 · every real booking attempt goes in the outcomes ledger (never the person's details)
    try:   # CR 130 · the ledger is written AFTER her answer (OC.booked_later): never a wait on it (8.9 s, La Mi Venta's tap)
        out = await _book_inner(ctx, held, how, venue, rung)
    except Exception as e:
        OC.booked_later(ctx.account, held, venue, area_of(card) if card else None, error=str(getattr(e, "message", "") or type(e).__name__))
        raise
    if out.get("status") != "waiting_for_their_tap":   # Sasha 254 · nothing has gone yet: recorded when it does
        OC.booked_later(ctx.account, held, venue, area_of(card) if card else None, result=out)
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
    from booking_signer import channel as CH   # Sasha 326 · a work-in-progress step goes to WhatsApp ONLY when the request came from there
    if rung == "draft":   # Sasha 212 · the drafted message goes to THEIR phone; they send it — never "booked"
        sent = False
        try:
            ch = await GW.STORE.channel_of_account(ctx.account) if GW.STORE and CH.wip_on_phone(ctx) else None
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
        prep = held.get("prep") or await VT.prepare({"name": venue, "website": held.get("website"), "place_id": held.get("place_id")},
                                {"name": f.get("Name"), "phone": f.get("Mobile"), "email": f.get("Email")},
                                held["when"][:10], held["when"][11:16], int(held["party"]), account=ctx.account)   # CR 89 · nothing submitted
        if prep and one_path(ctx) and (prep.get("decision") or (held.get("follow") or {}).get("decision") or {}).get("route") == "platform":
            return await _platform_handover(ctx, held, prep, venue, where)   # Sasha 316 · ONE message, the platform's own page
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
            ch = await GW.STORE.channel_of_account(ctx.account) if GW.STORE and CH.wip_on_phone(ctx) else None
            if ch:
                o = await GW._tell(ch, text)
                sent = "sent" in o and "not" not in o
        except Exception as e:
            log.warning("[venues] the prepared page was not sent to the phone: %s", type(e).__name__)
        # Sasha 254 · ONE TRUTH: "It's in your bookings" is true only because it IS — get_status reads this record
        from agapi import itinerary as IT   # Sasha 300 · the platform it is on, when the decision names one (its channel or its button)
        dec = ((held.get("follow") or {}).get("decision")) or {}
        await note_prepared(ctx.account, venue, held["when"], held["party"], held.get("url"), place_id=held.get("place_id"),
                            platform=IT.platform_name(held.get("channel_name"), dec.get("channel"), (dec.get("button") or {}).get("label")),
                            prepared_id=(prep or {}).get("prepared_id"))   # CR 132 (a) · on AgAPI's record too
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
                                 **({"human_step": held["human_step"], "prepared_by": OP.VENUE_PREPARE_BOOKING} if held.get("human_step") else {})},
                    **({"in_app": True} if VS.TAP.get() is not None else {}),
                    "say": (said := next((x for x in ((prep.get("say") if fw["refused"] else dec.get("say_text")),)
                                          if x and not V.asks_for_link(x)), None) or V.done_form(getattr(ctx, "surface", "s2"))),   # 286: never a link ask
                    "page_says": said}   # Sasha 299 · in the app said by code (voice.page_line): no model step just to say it
        return {"status": "page_on_phone" if sent else "page_link", "venue": venue, "when": held["summary"], "itinerary": where, "booked": False,
                "prepared": {"venue": venue, "url": held["url"], "fields": held["fields"], "on_phone": sent, "filled": filled,
                             **({"human_step": held["human_step"], "prepared_by": OP.VENUE_PREPARE_BOOKING} if held.get("human_step") else {})},
                **({"in_app": True} if VS.TAP.get() is not None else {}),
                # Sasha 249 · her words for it are her voice's, never the engine's (which may name the booking platform)
                "say": (V.done_form(getattr(ctx, "surface", "s2")) if filled else V.NOT_FILLED) + " Say exactly that — never that it's booked."}
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
        out = await GW.tap_platform(ctx.account, text, url, held["id"], venue, held["when"]) if CH.wip_on_phone(ctx) else \
            "not sent: asked on S2 — the page is S2's card"   # Sasha 326
        if one_path(ctx):   # Sasha 283 · item 4c: on the one row the way back reads, with its link's own record
            await note_prepared(ctx.account, venue, held["when"], held["party"], url, link_id=held["id"], route="platform",
                                platform=held.get("platform"), place_id=held.get("place_id"))
        sent = "sent" in out and "not" not in out
        if not sent and CH.wip_on_phone(ctx):   # Sasha 264 · item 3: the reason was dropped (326: asked on S2 it was never meant to go)
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
                **({"in_app": True, "phone_line": V.phone_line(sent, out) if CH.wip_on_phone(ctx) else "", "page_says": says} if in_app else {}),   # 326: on S2, no phone words
                "platform": held.get("platform"), **({} if sent else {"open": url}), **({"page_url": url} if url else {}),
                # Sasha 236 · found live on /s2: "their page is on your phone" when it wasn't sent there
                **({} if sent else {"say": "Their page is on this screen — Tap to finish opens it. Never say it's on their phone."})}
    # Sasha 319 · Sasha's own email / form / call to a venue are gone: AgAPI's acts are the one sender
    return {"status": "not_sent", "venue": venue, "when": held.get("summary"), "booked": False, "line": TO_TYLER,
            "how": "Say `line` word for word — nothing else."}


def _platform_page(u) -> bool:
    return isinstance(u, str) and u.startswith("https://") and "/prepared/" not in u


async def _platform_handover(ctx, held: dict, prep: dict, venue: str, where) -> dict:
    """Sasha 316 · A PLATFORM HAND-OVER IS ONE MESSAGE (La Mi Venta via CoverManager, 30 Oct 07:25: a copy card, AgAPI's /prepared/ page,
    "Done? Back to Sasha" — then the model's "Your details are filled in", and CoverManager opened empty). ONE truth: AgAPI's decision
    (route platform) and its hand_over (CR 107's platform-link table: the platform's own page, what it carries). The message goes to his
    phone once and IS her answer (wa_agent sends nothing after it); its "booked" is answered on the hand-over's own record."""
    from agapi import itinerary as IT, venue_submit as VS
    from app.agent import voice as V
    GW = _API()
    fw = held.get("follow") or {}
    dec = prep.get("decision") or fw.get("decision") or {}
    ho = prep.get("hand_over") or {}
    fdec = fw.get("decision") or {}
    link = next((u for u in (ho.get("link"), (fdec.get("button") or {}).get("link"), held.get("url"), (dec.get("button") or {}).get("link"))
                 if _platform_page(u)), None) or prep["link"]   # the platform's own page; AgAPI's /prepared/ page only if none is given
    platform = ho.get("platform") or IT.platform_name(held.get("channel_name"), dec.get("channel"), (dec.get("button") or {}).get("label")) \
        or "their booking page"
    fields = await _with_loyalty(ctx, held)   # Sasha 253 · G14 — a loyalty number's value only here, on their phone
    by = {x["label"]: x["value"] for x in fields}
    details = [by.get("Name"), by.get("Email"), by.get("Mobile")] + \
        [f"{x['label']}: {x['value']}" for x in fields if x["label"] not in ("Day", "Time", "People", "Name", "Email", "Mobile") and x.get("value")]
    text = V.handover_message(venue, platform, held["when"], int(held["party"]), ho.get("carried") or [], details, link)
    from booking_signer import channel as CH   # Sasha 326 · the hand-over goes to WhatsApp ONLY when it was asked there
    sent, ch = False, None
    try:
        ch = await GW.STORE.channel_of_account(ctx.account) if GW.STORE and CH.wip_on_phone(ctx) else None
        if ch:
            o = await GW._tell(ch, text)
            sent = "sent" in o and "not" not in o
    except Exception as e:
        log.warning("[venues] the platform hand-over was not sent to the phone: %s", type(e).__name__)
    await note_prepared(ctx.account, venue, held["when"], held["party"], link, place_id=held.get("place_id"), route="platform",
                        platform=platform, prepared_id=prep.get("prepared_id"))   # the row "Did it go through?" and his "booked" read
    if sent:   # his "booked" answers it, in one line (guest_whatsapp: kind "handed")
        await GW.await_booked(ch, venue, held["when"])
    line = text.split("\n")[0]
    label = V.OPEN_THEIR_PAGE if fw.get("refused") else (dec.get("button") or {}).get("label") or V.OPEN_THEIR_PAGE
    return {"status": "page_on_phone" if sent else "page_link", "venue": venue, "when": held["summary"], "itinerary": where,
            "booked": False, "route": "platform", **({} if sent else {"open": link}),
            "prepared": {"venue": venue, "url": link, "fields": held["fields"], "on_phone": sent, "button": label,
                         "platform": platform},   # never "filled": the platform was given nothing (page_line says page_says)
            **({"in_app": True} if VS.TAP.get() is not None else {}),
            "say": line, "page_says": line}


async def _agapi_send(ctx, held: dict, how: dict, venue: str, where) -> dict:
    """venue.submit_booking with the instruction's approval → said in Tyler's ONE line (Sasha 381): Booked (the venue confirmed it, its
    reference) / Requested (sent: a request until they reply) / "not allowed" with their prepared page / failed, said."""
    from agapi import venue_submit as VS
    from agapi.booking_rules import booking_rules as BR
    # Sasha 381 · CR 196 · the instruction IS the approval; a read-back outside it (no mandate on it) goes on the person's own yes
    r = await (VS.submit_instructed(ctx.account, held, how.get("said") or "") if held.get("mandate_id") else
               VS.submit(ctx.account, held, how.get("said") or ""))
    if not r.get("ok"):
        return await _not_sent(ctx, held, r["error"], venue)
    st = r.get("status")
    if held.get("platform_book"):   # Sasha 328 · CR 160 · AgAPI pressed Book on their platform page (or stopped): said as it is
        return await _platform_result(ctx, held, r, venue, where)
    if held.get("kanoe"):   # Sasha 287 · Kanoe's WhatsApp: sent → when, and who it waits for; AgAPI's gate said no at the send → their own
        return await _kanoe_sent(ctx, held, r, venue, where)
    if st == "confirmed":
        ref = r.get("reference")
        # Sasha 381 · Tyler's ONE line: "Booking now: …" then "Booked — reference X."
        return {"status": "confirmed", "venue": venue, "when": held["summary"], "itinerary": where, **({"reference": ref} if ref else {}),
                "line": _acted(held, r, True, ref),
                **({"in_app": True} if VS.TAP.get() is not None else {}),   # Sasha 263 · the in-app yes: said by code (voice.yes_line)
                "how": "Say `line` word for word, then at most ONE short question (e.g. the calendar) — nothing else."}
    if st == "sent":
        if r.get("call_plan") and r.get("act_id"):   # Sasha 271 · CR 102 · R6 (a stay arriving within 24 h): the engine opened the call
            from agapi import venue_calls as VC       # WITH the email, under this same yes — Sasha dials only its call_plan, exactly
            dialled = await VC.dial(ctx.account, r, {**held, "timezone": _tz_of(held)})   # as a table's call (Sasha 269)
            return {"status": "requested", "venue": venue, "when": held["summary"], "itinerary": where, "act_id": r.get("act_id"),
                    "line": _acted(held, r, False), "call": {"status": "calling", "dial": dialled.get("status"),
                                                               "reason": r["call_plan"].get("reason")},
                    **({"in_app": True} if VS.TAP.get() is not None else {}), "how": "Say `line` word for word — nothing else."}
        if (r.get("takeover") or {}).get("kind") == "their_listing":   # Sasha 272 · CR 103 · R6 was due, but their listing shows no number
            log.info("[venues] %s: R6's call not opened (their listing shows no number) — the request went", venue)
        # Sasha 381 · sent = a request until they reply: Tyler's ONE line (never a call promised that the booking won't make — Sasha 272)
        return {"status": "requested", "venue": venue, "when": held["summary"], "itinerary": where, "act_id": r.get("act_id"),
                "line": _acted(held, r, False), **({"in_app": True} if VS.TAP.get() is not None else {}),
                "how": "Say `line` word for word — nothing else."}
    if st == "not_allowed":   # Sasha 380 · AgAPI didn't send it: its reason logged, their prepared page handed over — nothing reached the venue
        link = held.get("link")
        return {"status": "not_allowed", "venue": venue, "when": held["summary"], "booked": False,
                "say": f"{refused_words(venue, r.get('say'))} {BR.PHRASES['takeover']}", **({"open": link, "page_url": link} if link else {})}
    raise _err("not_sent", r.get("say") or f"{venue} didn't take it — nothing is booked")


async def _kanoe_sent(ctx, held: dict, r: dict, venue: str, where) -> dict:
    """Sasha 287 · AgAPI's answer to the Kanoe send: "sent" (its reference is Twilio's message id, on the booking) → Sasha 381's ONE line
    ("Booking now: … Requested — I'll tell you when they reply."); anything else (the gate, a STOP, no approved template — nothing was
    sent) → their own WhatsApp."""
    from agapi import venue_submit as VS
    in_app = {"in_app": True} if VS.TAP.get() is not None else {}
    if r.get("status") == "sent":
        line = _acted(held, r, False)
        return {"status": "requested", "venue": venue, "when": held["summary"], "itinerary": where, "booked": False, "act_id": r.get("act_id"),
                **({"reference": r["reference"]} if r.get("reference") else {}), "wa_sent": True, "line": line, **in_app,
                "how": "Say `line` word for word — nothing else; it's a request until they reply."}
    if r.get("status") == "not_allowed":   # Sasha 380 · AgAPI's reason, kept (the hand-over below is Sasha 288's, unchanged)
        refused_words(venue, r.get("say"))
    log.info("[venues] %s: Kanoe's message not sent (%s) — handed over", venue, r.get("status"))
    # Sasha 288 · the same hand-over for every channel: their own WhatsApp when AgAPI wrote one, else THE FLOOR (286) — never "can't"
    out = await own_whatsapp(ctx, held.get("booking") or {}, {"venue": held["venue"], "place_id": held.get("place_id")},
                             {"how_many": {"count": held.get("party")}}, held.get("when"), None, held.get("own"), None)
    return {**out, **in_app, "line": out.get("page_says") or (out.get("floor") or {}).get("say") or ""}


async def confirm_number(ctx, held: dict, venue: str, act: str = "book_venue") -> dict:
    """Sasha 309 · THE YES THAT COULD NEVER GO (Tyler, DiverXO): AgAPI takes a WhatsApp yes only from the person's VERIFIED number (CR 99),
    and a number linked before CR 100 never was — the one-tap link was refused too. The number is confirmed the CR 100 way, ONCE:
    users.link_whatsapp's code, which they send from it (guest_whatsapp: the code from a linked number → users.confirm_whatsapp). The
    read-back stays held: after that, their yes sends it. Said by code, the turn ending on it — never "tap", never a call on top."""
    from agapi import venue_submit as VS
    from app.agent import voice as V
    store = _CANCEL if act == "cancel_venue" else _HELD   # Sasha 314 · a cancel's yes too
    if held.get("number_confirmed_at"):   # Sasha 311 · refused AGAIN after the number was confirmed: never a loop — said, the hold dropped
        store.pop(ctx.account, None)
        log.warning("[venues] %s: the yes was refused again after the number was confirmed", venue)
        return {"status": "not_sent", "venue": venue, "when": held["summary"], "booked": False, "line": V.still_refused_line(venue),
                "how": "Say `line` word for word — nothing else."}
    store[ctx.account] = held
    # Sasha 311 · his yes was consumed at the claim (CR 76's yes gate), but nothing went: the SAME read-back (its words and sha, unchanged)
    # stands shown again, so his next yes — from his now-verified number — counts once. Found by the proof: "no_read_back" on that yes
    from agapi import yes_gate as YG
    YG.shown(ctx, act, {"read_back": [held.get("summary") or venue]})
    from booking_signer import guest_whatsapp as GWS
    ch = await GWS.STORE.channel_of_account(ctx.account) if GWS.STORE is not None else None
    got = await VS.link_whatsapp(ctx.account, ch["number_e164"]) if ch else {"ok": False}
    line = V.NUMBER_NOT_CONFIRMED
    if got.get("ok") and got.get("state") == "verified" and await VS.whatsapp_verified(ctx.account, ch["number_e164"]):
        # Sasha 311 · already verified (read back): the yes was refused for another reason (a stale tap) — his next yes sends it, by code
        held["number_confirmed_at"] = datetime.now(timezone.utc).isoformat()
        line = V.number_confirmed_line(venue)
    elif got.get("ok") and got.get("code"):
        ok = await GWS.STORE.put_code({"code": got["code"], "account_id": ctx.account, "consent_at": ch.get("consent_at") or GWS.NOW(),
                                       "consent_wording_version": ch.get("consent_wording_version"),
                                       "consent_text_sha256": ch.get("consent_text_sha256"), "created_at": GWS.NOW()})
        if ok:
            line = V.confirm_number_line(str(got.get("text") or f"Kanoe link {got['code']}"))
    else:
        log.info("[venues] %s: the number couldn't be confirmed (%s)", venue, (got.get("error") or {}).get("code"))
    return {"status": "confirm_number", "venue": venue, "when": held["summary"], "booked": False, "line": line,
            "how": "Say `line` word for word — nothing else."}


async def _agapi_call(ctx, held: dict, how: dict, venue: str, where) -> dict:
    """Sasha 265 · item 4 · Sasha 381: the instruction's ONE venue.submit_booking route "call" (CR 196) → the act (status calling, act_id,
    call_plan) → Sasha dials ONLY what call_plan says (agapi.venue_calls). Said: Tyler's ONE line (AgAPI's instructed.say + Requested)."""
    from agapi import venue_calls as VC, venue_submit as VS
    # Sasha 381 · CR 196 · the instruction IS the approval; a read-back outside it (no mandate on it) goes on the person's own yes
    r = await (VS.submit_instructed(ctx.account, held, how.get("said") or "") if held.get("mandate_id") else
               VS.submit(ctx.account, held, how.get("said") or ""))
    if not r.get("ok"):
        return await _not_sent(ctx, held, r["error"], venue)
    st = r.get("status")
    if st == "not_allowed":
        link = held.get("link")
        return {"status": "not_allowed", "venue": venue, "when": held["summary"], "booked": False, "say": r.get("say") or "",
                **({"open": link, "page_url": link} if link else {})}
    if st != "calling":
        raise _err("not_sent", r.get("say") or f"{venue} couldn't be called — nothing is booked")
    dialled = await VC.dial(ctx.account, r, {**held, "timezone": _tz_of(held)})
    return {"status": "calling", "venue": venue, "when": held["summary"], "booked": False, "act_id": r.get("act_id"),
            "line": _acted(held, r, False), "dial": dialled.get("status"), **({"in_app": True} if VS.TAP.get() is not None else {}),
            "how": "Say `line` word for word — nothing else."}


def _acted(held: dict, r: dict, booked: bool, ref: Optional[str] = None) -> str:
    """Sasha 381 · Tyler's ONE line for a venue act: AgAPI's instructed.say ("Booking now: <venue>, <N> people, <date> at <time>." — CR 196,
    from the booking record: the ONE source of those words) + Booked / Requested."""
    from app.agent import voice as V
    say = str((r.get("instructed") or {}).get("say") or "")
    if not say and held.get("mandate_id"):   # a contract breach: an instructed act's answer always carries it — never a wording of her own
        log.error("[venues] AgAPI's instructed act %s carries no instructed.say", r.get("act_id"))
    return V.acted_line(say, booked, ref)


async def _not_sent(ctx, held: dict, err: dict, venue: str) -> dict:
    """Sasha 381 · the instructed submit didn't go. Outside the instruction (CR 196: AgAPI's reasons — another booking, party or time;
    already used): the booking has terms the person never gave, so AgAPI's read-back keeps its OWN yes — shown with the reason said,
    nothing sent until they say yes to THESE terms (book_venue → VS.submit, their tap / reply). An approval refused → _tap_refused."""
    from agapi import venue_submit as VS
    from app.agent import voice as V
    if err.get("code") == "outside_instruction" and err.get("read_back_id") and err.get("lines"):
        held = {**{k: v for k, v in held.items() if k != "mandate_id"}, "read_back_id": err["read_back_id"], "sha": err["sha256"],
                "lines": list(err["lines"]), "at": datetime.now(timezone.utc)}   # their yes, in a LATER turn, sends exactly these lines
        out = {"status": "awaiting_yes", "venue": venue, "route": held["rung"], "when": held.get("summary"), "booked": False,
               "read_back": _API().guest_lines("agapi", held["lines"]), "read_back_id": str(err["read_back_id"])[:80],
               "outside": err.get("outside"), "ask": V.outside_ask([o.get("why") for o in err.get("outside") or []]),
               "how": "Say `ask` word for word — the booking's terms are on the card; nothing is sent until they say yes to them."}
        held["out"] = out
        _HELD[ctx.account] = held
        return out
    if err.get("code") == "outside_instruction":   # no read-back to show: said, nothing sent
        _HELD.pop(ctx.account, None)
        return {"status": "not_sent", "venue": venue, "booked": False, "outside": err.get("outside"),
                "say": V.outside_line([o.get("why") for o in err.get("outside") or []])}
    if err.get("code") in VS.TAP_REFUSALS:
        return await _tap_refused(ctx, held, err["code"], err, venue)
    raise _err("not_sent", err.get("message") or f"{venue} didn't take it — nothing is booked")


def _tz_of(held: dict) -> str:
    from booking_signer import venue_read as V
    return (V.COUNTRIES.get(str(held.get("country") or "").upper()) or (None, None, None, "Europe/Madrid"))[3]


async def last_sent(account: str) -> Optional[dict]:
    """Sasha 381h · the booking they last sent, read from THE record of what was sent (venue_submit's acts, written durably as AgAPI
    acts — the one memory; the old in-process copy is deleted) → {venue, at} while a repeated yes is still that yes, else None."""
    from agapi import v0 as API, venue_submit as VS
    acts = [a for a in await VS.acts_of(account) if a.get("venue") and not (a.get("cancels") or a.get("changes"))]
    if not acts:
        return None
    a = max(acts, key=lambda x: float(x.get("at") or 0))
    at = datetime.fromtimestamp(float(a.get("at") or 0), timezone.utc)
    return None if API.stale(at) else {"venue": a["venue"], "at": at}


async def already_sent(ctx, first: dict) -> dict:
    """Sasha 381i · a booking act's answer asked for again (the same call, its once-only key): nothing acts now — "already sent" and the
    booking's status, from the record (the one line for every repeat: the claim's and the key's)."""
    return await _already_sent_line(ctx, str(first.get("venue") or ""))   # nothing held is touched: it's an answer, not an act


async def _already_sent_line(ctx, venue: str) -> dict:
    """"That's already been sent." + the booking's own status, from the record — never a second send."""
    from agapi import venue_submit as VS, s2_status as ST
    from app.agent import voice as V
    row = next((b for b in await VS.bookings(ctx.account) if _base(b.get("venue") or "") == _base(venue)), None)
    status = ST.decide({"venues": [row], "booked": [], "failed": []})["line"] if row else None
    return {"status": "already_sent", "venue": venue, "booked": bool(row and row.get("status") == "confirmed"),
            "say": V.tap_line("approval_consumed") + (f" {status}" if status else "")}


async def _tap_refused(ctx, held: dict, code: str, err: dict, venue: str) -> dict:
    """AgAPI refused the approval (CR 97 / CR 196). Sasha 381 · a venue act has no card, so nothing is ever shown to be answered again:
    the booking changed or timed out under the instruction, or it isn't provably theirs → said, nothing sent, nothing held; already sent
    → "already sent" and the booking's status. Nothing is sent twice."""
    from agapi import venue_submit as VS
    from app.agent import voice as V
    if code in (ERR.APPROVAL_VOID, ERR.APPROVAL_EXPIRED, ERR.APPROVAL_UNTRUSTED_ORIGIN):
        _HELD.pop(ctx.account, None)
        return {"status": "not_sent", "venue": venue, "booked": False, "say": V.tap_line(code)}
    # approval_consumed: the yes was already taken — the booking's own status, never a second send
    _HELD.pop(ctx.account, None)
    return await _already_sent_line(ctx, venue)


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


async def venue_bookings(account: str, include_cancelled: bool = False) -> List[dict]:
    """Pacioli's venue rows: what was asked of each venue, and its status in words (Requested / Confirmed… — from proof only)."""
    GW = _API()
    status, j = await GW.api(account, "GET", "/api/booking/reservations")
    if status >= 500 or status in (0, 408, 429):   # Sasha 215 · the records not answering is never "no bookings"
        from agapi.v0 import unreachable
        raise unreachable("store_unreachable")
    today = date.today().isoformat()
    acts: List[dict] = []
    from agapi import venue_submit as VS
    try:   # Sasha 254 · item 3 — the AgAPI sends, each with the venue's reply now (venue.booking_status), at most 5 s
        got = await asyncio.wait_for(VS.bookings(account), timeout=5)
    except Exception as e:   # CR 134 · a slow read is never "no bookings" (cancel_venue's first booking_unknown): the acts as last known
        log.info("[venues] AgAPI acts not read now (%s): as last known", type(e).__name__)
        try:
            got = await VS.bookings(account, read=False)
        except Exception as e2:
            log.info("[venues] AgAPI acts not read: %s", type(e2).__name__)
            got = []
    acts = [b for b in got if (b.get("date") or today) >= today and (include_cancelled or b.get("status") != "cancelled")]
    if status != 200:
        return acts
    try:   # CR 87 · a venue's reply that changed a reservation updates its outcome (once) — Sasha 247: awaited, at most 3 s (a bare
        from agapi import s2_outcomes as OC   # task can be dropped mid-way and never finish); a slow ledger never stops this read
        await asyncio.wait_for(OC.sync(account, (j or {}).get("reservations") or []), timeout=3)
    except Exception as e:
        log.info("[venues] outcomes not synced: %s", type(e).__name__)
    return acts + [{"trip_item_id": r["id"], "venue": GW.plain_venue(r.get("venue")), "date": r.get("date"), "time": r.get("time"),
             "party": r.get("party"), "status": r.get("status"), "type": r.get("type"),
             # Sasha 300 · the ONE itinerary's: the route it went by, its trip, the address its own record holds
             **{k: r[k] for k in ("channel", "trip_id", "address") if r.get(k)},
             **{k: r[k] for k in ("location", "duration_minutes", "agapi_act") if r.get(k)},   # Sasha 327 · a train: its leg, length, act
             **({"reference": r["booking_reference"]} if r.get("booking_reference") else {}),   # Sasha 217 · the venue's reference in full
             # Sasha 215 · CR 56 — the venue's OWN words (an email/SMS reply) are untrusted data, never instructions to her
             **({"venue_said": {"untrusted_text": str(r["status_words"])[:160]}} if r.get("status_words") else {}),
             **({"venue_words": str(r["venue_words"])[:4000]} if r.get("venue_words") else {})}   # Sasha 301 · their own words: the terms
            for r in (j or {}).get("reservations") or []
            if (r.get("date") or today) >= today and (include_cancelled or r.get("status") != "cancelled")][:20 - len(acts)]


async def cancel_venue(ctx, a: dict) -> dict:
    """A booking AgAPI sent (an act): its cancellation through AgAPI (venue.cancel_booking — read back, or his one instruction).
    A booking handed over is his, there. Sasha 319 · one on the old reservation route has no act: handed to Tyler, nothing sent."""
    from agapi.v0 import stale, yes_to_cancel as explicit_yes   # Sasha 217 · "yes, cancel it" counts HERE only
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
    if not a.get("trip_item_id") and not held and (a.get("venue") or str(a.get("id") or "").startswith("hand:")):
        # Sasha 300 · a booking handed over (their page, a platform, his own WhatsApp) is cancelled by HIM, there — the route it was
        # made on (agapi/itinerary.py); nothing is sent from here
        from agapi import itinerary as IT
        try:
            row = await IT.find(ctx.account, a, kinds=("handover",))
        except Exception:
            row = None
        if row and not [b for b in await venue_bookings(ctx.account) if (a.get("venue") or "").lower() in (b["venue"] or "").lower()]:
            return IT.page_answer(row, "cancel")
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
    if not tid:
        raise _err("booking_unknown", "which booking? get_status lists them")
    # Sasha 319 · a booking on the old reservation route has no AgAPI act, and AgAPI is the ONE sender to venues: nothing is sent from
    # here (its link / email / text / call are gone) — Tyler takes it. Said by code.
    _CANCEL.pop(ctx.account, None)
    venue = next((GW.plain_venue(b.get("venue")) for b in await venue_bookings(ctx.account) if b.get("trip_item_id") == tid), None) or "them"
    return {"status": "to_tyler", "venue": venue, "sent": False, "line": TO_TYLER, "how": "Say `line` word for word — nothing else."}


async def _cancel_act(ctx, a: dict, held: Optional[dict], said: str, explicit_yes) -> dict:
    """Sasha 256 · item 3 — MANAGE a booking sent through AgAPI (an act): venue.cancel_booking (CR 94). Its read-back first; on their
    explicit yes in a LATER turn the cancellation goes to the venue as its own act, and it's cancelled only when the venue's reply
    says so (get_status, through venue.booking_status). A booking made on the venue's own form can't be cancelled from here: their
    own page, said kindly.
    Sasha 329 · CR 161 · a booking AgAPI made on a platform's page goes down THIS same path (Sasha 328's link-only answer is gone): AgAPI
    decides (booking-rules/2.6 decide_cancel) whether it presses their own cancel for the person (cancelled: said with their page's words)
    or hands their cancel link over (not_allowed: why, the link, the venue's phone). Its read-back is ALWAYS shown first — the
    one-instruction rule never sends a platform cancel."""
    from agapi.v0 import claim
    from agapi import venue_submit as VS
    aid = a.get("act_id") or (held or {}).get("act_id")
    act = next((x for x in await VS.acts_of(ctx.account) if x.get("act_id") == aid), None) if aid else None
    plat = bool((act or {}).get("route") == "platform" or (held or {}).get("route") == "platform")
    if not (held and held.get("act_id")) and a.get("act_id") and not plat:
        # Sasha 323 · CR 152 · a booking he made himself (a train): AgAPI's fare answers what can be cancelled, and he does it on the
        # operator's own page (one button) — nothing is sent. A booking AgAPI sent itself has no such page: its own cancel act, below.
        from agapi import self_booked as SB
        m = await SB.manage(ctx.account, a["act_id"])
        if m:
            _CANCEL.pop(ctx.account, None)
            return SB.answer(m, "cancel")
    if held and held.get("act_id") and (not a.get("act_id") or a["act_id"] == held["act_id"]) and held["at"] < ctx.started:
        if not explicit_yes(said):
            raise _err("no_explicit_yes", "cancelling needs their explicit yes — ask them")
        await claim(ctx)
        r = await VS.cancel_submit(ctx.account, held, said)
        if not r.get("ok"):
            raise _err(r["error"]["code"], r["error"]["message"])
        _CANCEL.pop(ctx.account, None)
        if r.get("status") == "confirm_number":   # Sasha 314 · their WhatsApp number isn't verified yet: its one-time code (311) — never a link
            return await confirm_number(ctx, held, held.get("venue") or "them", act="cancel_venue")
        if r.get("status") == "person_sends":   # CR 132 (d)3 · booked from his own WhatsApp: AgAPI's words, for HIM to send there
            m = r.get("message") or {}
            return {"status": "yours_to_send", "venue": held.get("venue"), "sent": False, "say": r.get("say") or "",
                    **({"open": m["link"], "button": {"label": "Send on WhatsApp", "link": m["link"]}} if m.get("link") else {})}
        if r.get("status") == "cancelled":   # Sasha 329 · CR 161 · AgAPI pressed their own cancel, and their page said so
            return _platform_cancelled(held, r)
        if r.get("status") == "not_allowed":   # CR 132 · not sent (their window closed, no approved message yet): said, with his own way
            tk = r.get("takeover")
            link = tk if isinstance(tk, str) else (tk or {}).get("link") or r.get("link") or r.get("manage_url")
            if plat:   # Sasha 329 · CR 161 · a fee, a security check, a sign-in, their page not naming it: why, their link, their phone
                return _platform_not_cancelled(ctx, held, r.get("say") or "", link, r.get("why"))
            return {"status": "not_cancelled", "venue": held.get("venue"), "say": r.get("say") or "",
                    **({"open": link, "page_url": link} if link else {})}
        return {"status": "requested", "venue": held.get("venue"), "line": V_cancel_line(held), "how": "Say `line` word for word — nothing else."}
    rb = await VS.cancel_read_back(ctx.account, a["act_id"])
    rows = await VS.bookings(ctx.account)
    row = next((b for b in rows if b.get("act_id") == a["act_id"]), {})
    venue = row.get("venue") or a.get("venue")
    if not rb.get("ok"):
        e = rb["error"]
        if e["code"] == "already_cancelled":   # Sasha 317 · the same cancel asked again: AgAPI's own words, nothing sent twice
            return {"status": "already_sent", "line": e["message"], "how": "Say `line` word for word — nothing else."}
        if e["code"] == "not_allowed":
            link = (e.get("details") or {}).get("link")
            if plat:   # Sasha 329 · CR 161 · outside the beta (or AgAPI may not cancel there): their own link, the phone, why
                _CANCEL.pop(ctx.account, None)
                return _platform_not_cancelled(ctx, {**(act or {}), "venue": venue}, e["message"], link, (e.get("details") or {}).get("why"))
            return {"status": "not_cancelled", "say": e["message"], **({"open": link, "page_url": link} if link else {})}
        raise _err(e["code"], e["message"])
    import hashlib as _hl   # the one-yes gate (CR 76) binds their yes to THIS read-back by its words
    _CANCEL[ctx.account] = {**rb, "at": datetime.now(timezone.utc), "venue": venue, "date": row.get("date"), "time": row.get("time"),
                            "party": row.get("party"), "sha": _hl.sha256("\n".join(str(x) for x in rb["lines"]).encode()).hexdigest(),
                            **({"route": "platform", "reference": row.get("reference") or (act or {}).get("reference"),
                                "platform": (act or {}).get("platform"), "place_id": (act or {}).get("place_id")} if plat else {})}
    if plat:   # Sasha 329 · CR 161 · pressing a cancel on their page can't be undone: AgAPI's read-back and ONE question, then their yes
        from app.agent import voice as V
        c = _CANCEL[ctx.account]
        ask = V.platform_cancel_ask(_API().plain_venue(venue) or "them", c["date"], c["time"], c["party"], c.get("reference"))
        return {"status": "awaiting_yes", "venue": venue, "route": "agapi", "read_back": rb["lines"], "ask": ask,
                "read_back_id": rb["read_back_id"],   # Sasha 330 · its card's Yes / No (sasha.yes_buttons) answer THIS read-back only
                "how": "Say `ask` word for word — nothing is cancelled until they say yes. On their yes, call cancel_venue again with "
                       "approval.said = their words."}
    if await one_instruction(ctx, venue, "cancel", rows):
        # Sasha 314 / 317 · "cancel my DiverXO booking", exactly one booking, from the app or their verified WhatsApp: that message IS the approval
        return await _cancel_now(ctx, _CANCEL[ctx.account], said)
    from app.agent import voice as V
    c = _CANCEL[ctx.account]   # Sasha 330 · the same ONE question as a platform cancel's, over its card's Yes / No
    return {"status": "awaiting_yes", "venue": venue, "route": "agapi", "read_back": rb["lines"], "read_back_id": rb["read_back_id"],
            "ask": V.platform_cancel_ask(_API().plain_venue(venue) or "them", c.get("date"), c.get("time"), c.get("party"), row.get("reference"))}


async def cancel_card(ctx, read_back_id: str, choice: str) -> dict:
    """Sasha 330 · "give me a button" · a tap on the cancel read-back's card (sasha.card_tap, /s2 or WhatsApp) — the booking card's rule:
    ONLY for the read-back held now (its read_back_id), once (card_tap's ctx.idem, claimed durably). "cancel" → the SAME path as a typed
    yes (_cancel_act, said = the button's words: an explicit yes in a later turn, CR 76's one-yes gate, venue.cancel_booking with the
    tap). "keep" → the held cancel dropped, nothing sent. A card already answered → nothing_waiting (AgAPI is not called)."""
    from agapi.v0 import ToolError, claim, stale, yes_to_cancel, _unclaim
    from agapi import yes_gate as YG
    from app.agent import voice as V
    held = _CANCEL.get(ctx.account)
    if not held or held.get("read_back_id") != read_back_id or not held.get("act_id"):
        return {"status": "nothing_waiting", "line": V.CARD_ANSWERED}
    if stale(held["at"]):   # over 15 minutes: never acted on (as cancel_venue) — read back afresh when they ask again
        _CANCEL.pop(ctx.account, None)
        return {"status": "nothing_waiting", "line": V.CARD_ANSWERED}
    if choice == "keep":
        try:
            await claim(ctx)   # card_tap's key: this card's "keep", once
        except ToolError:
            return {"status": "nothing_waiting", "line": V.CARD_ANSWERED}
        _CANCEL.pop(ctx.account, None)
        YG.dropped(ctx.account, "cancel_venue")
        return {"status": "kept", "venue": held.get("venue"), "sent": False, "line": V.CANCEL_KEPT,
                "how": "Say `line` word for word — nothing was sent."}
    said = next(c["title"] for c in V.CANCEL_CHOICES if c["route"] == "cancel")
    if getattr(ctx, "surface", "") == "s2":   # CR 76 · the ONE-YES gate, as for a typed yes: this tap, heard as the yes to the read-back shown
        ctx.act_name, ctx.act_said = "cancel_venue", said
        YG.heard(ctx, "cancel_venue", said)
    try:
        return await _cancel_act(ctx, {"act_id": held["act_id"]}, held, said, yes_to_cancel)
    except ToolError as e:
        if e.code == "already_done":   # the same card tapped twice at once: the first one went
            return {"status": "nothing_waiting", "line": V.CARD_ANSWERED}
        await _unclaim(ctx)   # refused before anything was sent: the card's next yes may act
        raise
    finally:
        ctx.act_name = ctx.act_said = None


def _platform_cancelled(held: dict, r: dict) -> dict:
    """Sasha 329 · CR 161 · venue.cancel_booking answered cancelled: AgAPI pressed their own cancel for THIS booking and their page said so.
    Said by code — what was cancelled and their page's words; the ONE record (venue.booking_status) now reads cancelled."""
    from app.agent import voice as V
    vw = r.get("venue_words") or {}
    words = (vw.get("untrusted_text") or vw.get("text")) if isinstance(vw, dict) else vw
    venue = _API().plain_venue(held.get("venue")) or "them"
    line = V.platform_cancelled_line(venue, held.get("date"), held.get("time"), held.get("party"), held.get("reference"), words) \
        if words else (str(r.get("say") or "").strip() or V.platform_cancelled_line(venue, held.get("date"), held.get("time"),
                                                                                  held.get("party"), held.get("reference"), None))
    return {"status": "cancelled", "venue": venue, "sent": True, "cancelled": True, "route": "platform", "line": line,
            **({"cancel_act_id": r["cancel_act_id"]} if r.get("cancel_act_id") else {}),
            "how": "Say `line` word for word — nothing else."}


def _platform_not_cancelled(ctx, b: dict, say: str, link: Optional[str], why=None) -> dict:
    """Sasha 329 · CR 161 · AgAPI didn't press their cancel (a fee, a security check, a sign-in, their page not naming the booking, the
    person outside the beta): AgAPI's own words (why), their cancel link as the button (AgAPI's takeover / link — else the link their
    confirmation email gave), and the venue's phone when its card is on screen (shown now, never kept: row 942). Nothing was cancelled."""
    from app.agent import voice as V
    venue = _API().plain_venue(b.get("venue")) or "them"
    link = link if str(link or "").startswith("http") else (b.get("cancel_link") if str(b.get("cancel_link") or "").startswith("https://") else None)
    card = card_of(ctx.account, b.get("place_id"), venue)
    phone = (card or {}).get("phone") if str((card or {}).get("phone") or "").startswith("+") else None
    platform = b.get("platform") or "their page"
    out = {"status": "yours_there", "venue": venue, "route": "platform", "sent": False, "cancelled": False, "booked": True,
           "line": V.platform_not_cancelled_line(say, phone), "how": "Say `line` word for word — nothing was cancelled.",
           **({"why": list(why)} if isinstance(why, list) else {}), **({"phone": phone} if phone else {})}
    if link:
        out.update(open=link, page_url=link, button={"label": f"Cancel on {platform}", "link": link})
    return out


_CANCEL_WORDS = re.compile(r"\b(?:cancel|cancela|cancelar|anula|anular|annule|annuler)\b", re.I)
# Sasha 317 · the verb of each manage action — the action his words ask for (the venue is found by name, below)
ACTION_WORDS = {
    "cancel": _CANCEL_WORDS,
    "change": re.compile(r"\b(?:change|move|switch|reschedule|push|bring\s+(?:it\s+)?forward|make\s+it|cambia(?:r)?|mueve|mover|"
                         r"modifica(?:r)?|d[ée]place[rz]?|change[rz]?)\b", re.I),
    "late": re.compile(r"\b(?:late|running\s+behind|delayed|held\s+up|retras\w*|tarde|en\s+retard)\b", re.I),
}
# Sasha 317 · words that say what KIND of place it is, not which one: "Taberna Las Sobrinas" is named by "Las Sobrinas" (found live,
# 31 Oct: "Cancel my Las Sobrinas booking" asked again — the whole name was required, so only "DiverXO"-style names ever matched)
_CATEGORY = {"taberna", "restaurante", "restaurant", "bar", "cafe", "café", "cafeteria", "cafetería", "hotel", "hostal", "meson", "mesón",
             "bistro", "bistrot", "tasca", "cerveceria", "cervecería", "marisqueria", "marisquería", "asador", "pizzeria", "trattoria",
             "brasserie", "spa", "club", "bodega", "casa de comidas", "gastrobar", "the", "taverna", "tavern", "osteria", "ristorante",
             "cantina", "pub", "inn", "grill", "steakhouse", "chiringuito", "bistró", "restaurant & bar"}


def names_venue(words: str, venue: str) -> bool:
    """Sasha 317 · his words NAME this venue: its whole name, or its name without the words for its kind ("Las Sobrinas" for "Taberna
    Las Sobrinas") — whole words, at least four letters. Nothing fuzzy: a misspelling is a read-back, never a guess."""
    said, full = f" {_base(words)} ", _base(venue)
    core = _base(" ".join(t for t in full.split() if t not in _CATEGORY))
    return bool(full) and (f" {full} " in said or (len(core) >= 4 and f" {core} " in said))


async def one_instruction(ctx, venue: str, kind: str, rows: Optional[List[dict]] = None) -> bool:
    """Sasha 314 · 317 · THE ONE RULE for every manage action (cancel, change, late) on every route: his OWN words — the action's verb and a
    name that names exactly ONE active booking of his, this one — from the app or his verified WhatsApp, ARE the approval. Nothing was
    inferred, so nothing is asked again. Anything less (two bookings there, no name, no verb, another channel) is a read-back."""
    from agapi import venue_submit as VS
    if VS.TAP.get() is None and VS.WA.get() is None:
        return False
    said = str(getattr(ctx, "user_said", "") or "")
    if not ACTION_WORDS[kind].search(said) or not venue or not names_venue(said, venue):
        return False
    if rows is None:
        rows = await VS.bookings(ctx.account)
    live = [b for b in rows if b.get("status") not in ("cancelled", "declined", "failed") and names_venue(said, b.get("venue") or "")]
    return len({_base(b.get("venue") or "") for b in live}) == 1 and len(live) == 1 and _base(live[0].get("venue") or "") == _base(venue)


async def claim_words(ctx, booking: str) -> bool:
    """Sasha 314 · 317 · his instruction is sent ONCE: a durable claim on these words for this booking (a retried turn sends nothing).
    False → already sent."""
    import hashlib as _h
    from agapi.v0 import ToolError, claim
    words = str(getattr(ctx, "user_said", "") or "")
    key = "manage_words:" + _h.sha256(f"{ctx.account}|{booking}|{words.strip().casefold()}".encode()).hexdigest()
    was = (ctx.idem, getattr(ctx, "act_name", None))
    ctx.idem, ctx.act_name = key, None
    try:
        await claim(ctx)
        return True
    except ToolError:
        return False
    finally:
        ctx.idem, ctx.act_name = was


async def _cancel_now(ctx, held: dict, said: str) -> dict:
    """Sasha 314 · their instruction was the yes: the cancellation sent ONCE (a durable claim on these words for this booking), from
    their verified WhatsApp / the app — the same send as a tap (venue_submit.cancel_submit)."""
    from agapi import venue_submit as VS
    words = str(getattr(ctx, "user_said", "") or "")
    if not await claim_words(ctx, f"cancel|{held.get('act_id')}"):
        _CANCEL.pop(ctx.account, None)
        return {"status": "already_sent", "venue": held.get("venue"), "line": f"I've already asked {held.get('venue')} to cancel it.",
                "how": "Say `line` word for word — nothing else."}
    r = await VS.cancel_submit(ctx.account, held, words)
    if not r.get("ok"):
        raise _err(r["error"]["code"], r["error"]["message"])
    _CANCEL.pop(ctx.account, None)
    if r.get("status") == "confirm_number":
        return await confirm_number(ctx, held, held.get("venue") or "them", act="cancel_venue")
    if r.get("status") == "not_allowed":
        tk = r.get("takeover")
        link = tk if isinstance(tk, str) else (tk or {}).get("link")
        return {"status": "not_cancelled", "venue": held.get("venue"), "say": r.get("say") or "", **({"open": link, "page_url": link} if link else {})}
    return {"status": "requested", "venue": held.get("venue"), "line": V_cancel_line(held), "how": "Say `line` word for word — nothing else."}


def V_cancel_line(held: dict) -> str:
    from app.agent import voice as V
    return V.cancel_sent_line(held.get("venue") or "them", held.get("date"), held.get("time"), held.get("party"))


__all__ = ["read_booking_route", "hold_venue", "book_venue", "cancel_venue", "cancel_card", "venue_bookings"]
