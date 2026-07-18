"""
Live web-search-backed travel finders: flights, airport transfers (cabs), activities, hotels.

No paid third-party booking API is wired yet, so each finder pulls REAL, current options from
Claude's `web_search` tool and returns them as normalized "booking cards". Every option carries
a deep-link to the real provider (Google Flights, Klook, GetYourGuide, Booking.com) where the
guest completes the booking.

Reliability first (this drives a live investor demo): every finder is hard-timeboxed and, on a
slow/empty/failed search, falls back to a single deep-link option so a card ALWAYS renders and
a turn NEVER hard-fails. The spoken summary is built deterministically from the returned card,
so what Sasha says always matches what the card shows.

Card shape (consumed by the frontend `bookings` renderer):
    {"type": "flight"|"cab"|"activity", "title": str, "dest": str,
     "options": [{"name": str, "detail": str, "price": str, "book_url": str}]}
"""

import asyncio
import copy
import json
import os
import re
import time
from urllib.parse import quote_plus

from app.services.llm import client
from app.services.hotels_db import recommend_hotels, _booking_url, social_proof

_SEARCH_MODEL = "claude-haiku-4-5"
_WEB_SEARCH_TOOL = [{"type": "web_search_20250305", "name": "web_search"}]
# web_search adds real latency; bound it hard so a slow search degrades to a deep-link card
# instead of stalling the spoken turn. Sits below the conductor's 20s per-agent ceiling.
_FINDER_TIMEOUT = 12.0


# ── Result stability ────────────────────────────────────────────────────────
# Every finder hits a LIVE web search, so the same question asked twice returned a different
# list ("Tam Vi, Pho Khoi Hoi" then "Banh Mi 25, Pho Gia Truyen Bat Dan" then "Tam Vi, Banh
# Mi 25" — measured against prod, 3 runs, 3 answers, sometimes the same place under different
# spellings). That is not a cosmetic wobble: the guest reads a card, says "book the second
# one", the intent re-fires, the list is rebuilt from a fresh search, and "the second one" now
# silently means a DIFFERENT place than the one on their screen.
#
# So resolve each (kind, destination) ONCE and reuse it, which is what the hotels path already
# does ("live-search-with-static-fallback resolved once"). TTL keeps a long-lived process from
# pinning stale fares.
#
# Keyed on (kind, dest) only, deliberately NOT on the free-text hint: every caller passes the
# raw user message as that hint, so including it would miss on every turn and restore the bug.
# Consequence: a same-city refinement reuses the resolved list instead of re-searching.
# Stability at the booking moment is worth more than re-rolling.
#
# Process-local. Railway runs ONE uvicorn worker today (backend/railway.json startCommand has
# no --workers), so this is coherent. backend/Dockerfile defaults WEB_CONCURRENCY=2 — if that
# path is ever used, two workers hold independent caches and one guest can still see two
# different lists. Move this to chat_store/Redis before scaling out.
_CARD_TTL_S = float(os.getenv("FINDER_CACHE_TTL_S", "1800"))  # 30 min ≈ one demo session
_card_cache: dict = {}


def _is_fallback(card: dict) -> bool:
    """True when the search failed and the card is just a deep-link placeholder."""
    return any(o.get("fallback") for o in (card.get("options") or []))


async def _resolve_once(kind: str, dest: str, build):
    """Return a previously-resolved card for this (kind, dest), else build and remember it."""
    key = (kind, (dest or "").strip().lower())
    now = time.monotonic()
    hit = _card_cache.get(key)
    if hit and hit[1] > now:
        return copy.deepcopy(hit[0])  # deepcopy: callers must not mutate the cached card
    card = await build()
    # Never cache a fallback. It means the search timed out or came back empty; pinning it for
    # the full TTL would lock the guest out of live options for the rest of the session.
    if not _is_fallback(card):
        _card_cache[key] = (copy.deepcopy(card), now + _CARD_TTL_S)
    return card


async def _web_search_json(query: str, max_tokens: int = 700) -> list:
    """Run one web_search-augmented completion and parse a JSON array out of the reply.

    Returns [] on timeout, error, or unparseable output — callers supply a deep-link fallback.
    """
    try:
        resp = await asyncio.wait_for(
            client.messages.create(
                model=_SEARCH_MODEL,
                max_tokens=max_tokens,
                tools=_WEB_SEARCH_TOOL,
                messages=[{"role": "user", "content": query}],
            ),
            timeout=_FINDER_TIMEOUT,
        )
    except Exception as e:
        print(f"[travel_search] web search failed: {e}")
        return []
    text = "".join(getattr(b, "text", "") for b in resp.content)
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _usd(v) -> str:
    try:
        n = float(v)
        if n <= 0:
            return ""
        return f"${int(round(n)):,}"
    except (TypeError, ValueError):
        return ""


def _amt(v) -> int:
    """Numeric USD for server-side checkout pricing (0 = not bookable / unknown)."""
    try:
        n = int(round(float(v)))
        return n if n > 0 else 0
    except (TypeError, ValueError):
        return 0


# ── Flights ────────────────────────────────────────────────────────────────

def _flights_link(origin: str, dest: str) -> str:
    q = "flights " + (f"from {origin} " if origin else "") + f"to {dest}"
    return f"https://www.google.com/travel/flights?q={quote_plus(q.strip())}"


async def _find_flights_live(dest: str, origin: str = "", when: str = "") -> dict:
    dest = dest or "Vietnam"
    # Infer a sensible origin so the model never stalls asking for one: domestic Vietnam legs
    # usually start in Hanoi or Ho Chi Minh City; leave international to the model's judgement.
    origin_clause = f"from {origin}" if origin else (
        "from Hanoi or Ho Chi Minh City if the destination is inside Vietnam, otherwise from a "
        "major international hub"
    )
    q = (
        f"You are a flight-search assistant. Traveller request: \"{when or ('flight to ' + dest)}\". "
        f"List 3 real airlines that actually fly to {dest} {origin_clause}, with typical current fares. "
        "Do NOT ask any questions and do NOT add prose. Assume sensible defaults for anything missing. "
        'Respond with ONLY a JSON array (no preamble, no markdown), each item exactly: '
        '{"airline": "Vietnam Airlines", "route": "HAN-DAD", "duration": "1h 20m", '
        '"stops": "nonstop", "price_usd": 85}.'
    )
    rows = await _web_search_json(q, max_tokens=900)
    book = _flights_link(origin, dest)
    options = []
    for r in rows[:3]:
        if not isinstance(r, dict):
            continue
        name = (r.get("airline") or "").strip() or "Flight"
        detail = " · ".join(
            [s for s in [str(r.get("route") or "").strip(), str(r.get("duration") or "").strip(),
                         str(r.get("stops") or "").strip()] if s]
        )
        options.append({"name": name, "detail": detail, "price": _usd(r.get("price_usd")),
                        "amount_usd": _amt(r.get("price_usd")), "book_url": book})
    if not options:
        options = [{
            "name": f"Flights to {dest}",
            "detail": "Compare live fares and book on Google Flights",
            "price": "",
            "book_url": book,
            "fallback": True,
        }]
    return {"type": "flight", "title": f"Flights to {dest}", "dest": dest, "options": options}


# ── Airport transfers / cabs ────────────────────────────────────────────────

def _transfer_link(dest: str) -> str:
    return f"https://www.klook.com/en-US/search/?query={quote_plus(dest + ' Vietnam airport transfer')}"


async def _find_cabs_live(dest: str, detail_hint: str = "") -> dict:
    dest = dest or "Vietnam"
    q = (
        f"Find 3 real airport-transfer, private-car or taxi options in {dest}, Vietnam"
        f"{(' ' + detail_hint) if detail_hint else ''}. Use real providers (Grab, Klook private "
        "transfer, hotel car service, reputable local taxi firms like Mai Linh / Vinasun) and "
        'realistic fares. Return ONLY a JSON array, each item: {"provider": str, "vehicle": '
        '"sedan"/"SUV"/"7-seat van", "notes": "e.g. meet & greet, 45 min", "price_usd": number}. No other text.'
    )
    rows = await _web_search_json(q)
    book = _transfer_link(dest)
    options = []
    for r in rows[:3]:
        if not isinstance(r, dict):
            continue
        name = (r.get("provider") or "").strip() or "Private transfer"
        detail = " · ".join(
            [s for s in [str(r.get("vehicle") or "").strip(), str(r.get("notes") or "").strip()] if s]
        )
        options.append({"name": name, "detail": detail, "price": _usd(r.get("price_usd")),
                        "amount_usd": _amt(r.get("price_usd")), "book_url": book})
    if not options:
        options = [{
            "name": f"Airport transfer · {dest}",
            "detail": "Private cars and taxis, book on Klook",
            "price": "",
            "book_url": book,
            "fallback": True,
        }]
    return {"type": "cab", "title": f"Airport transfers · {dest}", "dest": dest, "options": options}


# ── Activities / experiences ────────────────────────────────────────────────

def _activity_link(name: str, dest: str) -> str:
    q = f"{name} {dest}".strip() if name else f"{dest} Vietnam"
    return f"https://www.getyourguide.com/s/?q={quote_plus(q)}"


async def _find_activities_live(dest: str, interest: str = "") -> dict:
    dest = dest or "Vietnam"
    q = (
        f"Find 3 real, bookable things to do in {dest}, Vietnam"
        f"{(' focused on ' + interest) if interest else ''}. Use real tours/experiences and realistic "
        'prices. Return ONLY a JSON array, each item: {"name": str, "duration": "3 hours" style, '
        '"notes": "short highlight", "price_usd": number}. No other text.'
    )
    rows = await _web_search_json(q)
    fallback = f"https://www.getyourguide.com/s/?q={quote_plus(dest + ' Vietnam')}"
    options = []
    for r in rows[:3]:
        if not isinstance(r, dict):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        detail = " · ".join(
            [s for s in [str(r.get("duration") or "").strip(), str(r.get("notes") or "").strip()] if s]
        )
        options.append({
            "name": name,
            "detail": detail,
            "price": _usd(r.get("price_usd")),
            "book_url": _activity_link(name, dest),
        })
    if not options:
        options = [{
            "name": f"Things to do · {dest}",
            "detail": "Tours and experiences, book on GetYourGuide",
            "price": "",
            "book_url": fallback,
            "fallback": True,
        }]
    return {"type": "activity", "title": f"Things to do · {dest}", "dest": dest, "options": options}


# ── Restaurants ─────────────────────────────────────────────────────────────

def _restaurant_link(name: str, dest: str) -> str:
    q = f"{name} {dest} Vietnam".strip() if name else f"restaurants {dest} Vietnam"
    return f"https://www.google.com/maps/search/{quote_plus(q)}"


# A reservation is priced as a prepaid table: estimated meal cost per person (× party size,
# applied in the conductor where the traveller count is known). When the model omits a number
# we fall back from the $ tier so every restaurant is still bookable.
_PRICE_TIER_USD = {"$": 15, "$$": 35, "$$$": 70, "$$$$": 120}


def _meal_usd(row: dict) -> int:
    """Per-person meal estimate in USD (0 if genuinely unknown)."""
    n = _amt(row.get("avg_meal_usd"))
    if n:
        return n
    tier = str(row.get("price_range") or "").strip()
    return _PRICE_TIER_USD.get(tier, 0)


async def _find_restaurants_live(dest: str, request_hint: str = "") -> dict:
    dest = dest or "Vietnam"
    q = (
        f"Find 3 real, currently-open restaurants in {dest}, Vietnam"
        f"{(' ' + request_hint) if request_hint else ''}. Use real, well-regarded places. "
        'Return ONLY a JSON array, each item: {"name": str, "cuisine": str, "price_range": '
        '"$"/"$$"/"$$$", "avg_meal_usd": number (typical cost per person for a meal), '
        '"notes": "one short highlight"}. No other text.'
    )
    rows = await _web_search_json(q)
    options = []
    for r in rows[:3]:
        if not isinstance(r, dict):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        detail = " · ".join(
            [s for s in [str(r.get("cuisine") or "").strip(), str(r.get("price_range") or "").strip(),
                         str(r.get("notes") or "").strip()] if s]
        )
        options.append({"name": name, "detail": detail, "price": "",
                        "per_person_usd": _meal_usd(r), "book_url": _restaurant_link(name, dest)})
    if not options:
        options = [{
            "name": f"Restaurants · {dest}",
            "detail": "Find, view menus and reserve on Google Maps",
            "price": "",
            "book_url": _restaurant_link("", dest),
            "fallback": True,
        }]
    return {"type": "restaurant", "title": f"Restaurants · {dest}", "dest": dest, "options": options}


# ── Cached public finders ───────────────────────────────────────────────────
# Thin wrappers over the _live finders above. Same signatures, so no caller changes; the only
# difference is that asking twice for the same destination now returns the SAME card.

async def find_flights(dest: str, origin: str = "", when: str = "") -> dict:
    dest = dest or "Vietnam"
    return await _resolve_once("flight", dest, lambda: _find_flights_live(dest, origin, when))


async def find_cabs(dest: str, detail_hint: str = "") -> dict:
    dest = dest or "Vietnam"
    return await _resolve_once("cab", dest, lambda: _find_cabs_live(dest, detail_hint))


async def find_activities(dest: str, interest: str = "") -> dict:
    dest = dest or "Vietnam"
    return await _resolve_once("activity", dest, lambda: _find_activities_live(dest, interest))


async def find_restaurants(dest: str, request_hint: str = "") -> dict:
    dest = dest or "Vietnam"
    return await _resolve_once("restaurant", dest, lambda: _find_restaurants_live(dest, request_hint))


# ── Hotels (live search with static fallback) ───────────────────────────────

async def find_hotels_live(dest: str, prefs: str = "") -> list:
    """Live-searched hotels in the same shape the frontend hotel card expects.

    Returns [] on failure so the caller can fall back to the curated static list.
    """
    if not dest:
        return []
    q = (
        f"Find 3 real hotels to stay at in {dest}, Vietnam"
        f"{(' — ' + prefs) if prefs else ''}. Use real, currently-operating properties and realistic "
        'nightly prices in USD. Return ONLY a JSON array, each item: {"name": str, "stars": number 1-5, '
        '"price_from_usd": number, "blurb": "one short line"}. No other text.'
    )
    rows = await _web_search_json(q)
    out = []
    for r in rows[:3]:
        if not isinstance(r, dict):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        try:
            stars = int(round(float(r.get("stars") or 5)))
        except (TypeError, ValueError):
            stars = 5
        stars = max(1, min(5, stars))
        try:
            price = int(round(float(r.get("price_from_usd") or 0)))
        except (TypeError, ValueError):
            price = 0
        out.append({
            "name": name,
            "stars": stars,
            "price_from": price,
            "blurb": (r.get("blurb") or "").strip(),
            "city": dest,
            "book_url": _booking_url(name, dest),
            **social_proof(name, stars),
        })
    return out


async def resolve_hotels(user_message: str, response_text: str, intents: list, context: str, dest: str) -> list:
    """Prefer live-searched hotels for `dest`; fall back to the curated static list.

    Keeps the exact record shape the frontend renders. Never raises.
    """
    try:
        live = await find_hotels_live(dest)
        if live:
            return live
    except Exception as e:
        print(f"[travel_search] live hotels failed, using static: {e}")
    return recommend_hotels(user_message, response_text, intents, context)
