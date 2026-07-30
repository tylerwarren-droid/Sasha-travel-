"""
Itinerary builder — turns the gathered trip details into a structured, day-by-day plan
with per-day images, real hotels, and booking links.

The conductor calls this when the user asks to build / see the full itinerary (or confirms
after Sasha offers). The LLM produces the day-by-day structure as JSON; we then enrich it
with images (foto) and booking deep-links (hotels_db + Google), so the frontend can render
a rich, bookable itinerary the user can ask Sasha to revise.
"""

import asyncio
import json
import os
import re
from typing import Optional
from urllib.parse import quote_plus

from app.services.llm import client, SPECIALIST_MODEL, FAST_MODEL, cached_system
from app.services.hotels_db import VIETNAM_HOTELS, _booking_url, social_proof
from app.services.booking_links import _find_destinations
from app.services.foto_agent import search_photos

_SYSTEM = """You are Sasha's expert Vietnam itinerary planner. From the conversation, produce \
a DETAILED day-by-day itinerary as a SINGLE JSON object and NOTHING else (no markdown).

Schema:
{
  "title": "<catchy trip title>",
  "summary": "<one warm sentence overview>",
  "days": [
    {
      "day": 1,
      "city": "<Vietnamese city/area>",
      "title": "<short day title>",
      "description": "<2-3 vivid sentences about the day>",
      "hotel": "<EXACT hotel name from the provided list for that city, or empty string if same hotel as the night before>",
      "activities": [
        {"time": "Morning|Afternoon|Evening", "name": "<activity>", "blurb": "<one line>"}
      ]
    }
  ],
  "estimated_total_usd": <integer total for hotels + activities + meals for the whole group>
}

Rules:
- The number of days MUST match what the user asked for (default 7 if unclear).
- Use REAL Vietnamese destinations with logical routing (don't criss-cross the country).
- Hotels: ONLY use names from this list, matched to the right city -> {hotels_context}
- 2-4 activities per day, tailored to the travellers and interests in the conversation.
- PARTY SIZE: {travellers_context}
- Output ONLY the JSON object."""


def _parse_json(raw: str):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(raw[s:e + 1])
    except Exception:
        return None


def _activity_link(name: str, city: str) -> str:
    # GetYourGuide is a real activity-booking marketplace — far more useful than a web search.
    return f"https://www.getyourguide.com/s/?q={quote_plus(f'{name} {city}')}"


# Real nightly rates from the hotel DB so the trip total is computed, not guessed.
_PRICE_BY_NAME = {h["name"]: h.get("price_from", 0) for hs in VIETNAM_HOTELS.values() for h in hs}
_STARS_BY_NAME = {h["name"]: h.get("stars", 5) for hs in VIETNAM_HOTELS.values() for h in hs}


_WORD_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
              "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _explicit_count_in_utterance(t: str) -> Optional[int]:
    """A HARD, stated head-count in one utterance ("2 travellers", "party of 4", "for four"),
    or None. Deliberately excludes relationship/solo inferences ("my wife" → 2, "family" → 4,
    "just me" → 1): those are guesses that additive phrasing can extend ("me and my wife, plus
    my friend and his wife" = 4), so they must NOT short-circuit the additive resolver — only a
    number the guest actually stated is safe to trust without the model.
    """
    t = (t or "").lower()

    # Explicit counts: "2 travellers", "for 3 people", "party of 4", "total of 4".
    # "party|group|total of N" all state a new head-count — guests say "so it'll be a
    # total of four" as often as "party of four", and both must re-price the trip.
    m = re.search(r"\b(\d+)\s*(?:travel|people|person|adult|guest|of us|pax)", t)
    if not m:
        m = re.search(r"\b(?:party|group|total)\s+of\s*(\d+)", t)
    if not m:
        # A head-count stated as who the trip is FOR: "package for 4", "make it a booking for 3",
        # "a plan for 4". The negative lookahead keeps a DURATION ("package for 4 days", "trip for
        # 5 nights") from being misread as a party size — the exact silent failure that shipped a
        # plan titled "for four" priced for two.
        m = re.search(
            r"\b(?:package|booking|reservation|trip|holiday|vacation|table|group|party|plan)"
            r"\s+for\s+(\d+)\b(?!\s*(?:day|days|night|nights|week|weeks|month|months|hour|hours|year|years))",
            t,
        )
    if m:
        try:
            n = int(m.group(1))
            if 1 <= n <= 12:
                return n
        except Exception:
            pass
    for w, n in _WORD_NUMS.items():
        if re.search(rf"\b{w}\s+(?:of us|travel|people|person|adult|guest)", t):
            return n
        if re.search(rf"\b(?:party|group|total) of {w}\b", t):
            return n
        if re.search(
            rf"\b(?:package|booking|reservation|trip|holiday|vacation|table|group|party|plan)"
            rf"\s+for\s+{w}\b(?!\s*(?:day|days|night|nights|week|weeks|month|months|hour|hours|year|years))",
            t,
        ):
            return n
    return None


def _travellers_in_utterance(t: str) -> Optional[int]:
    """Traveller count stated in ONE utterance, or None if it doesn't mention it.

    Ordered most-specific first: an explicit number beats a solo phrase beats a relationship
    hint, so "just me and my wife" resolves to 2 (the wife wins over "just me"), while
    "only I'm travelling" resolves to 1. Used only as the deterministic FALLBACK (regex can't
    do additive party math — the LLM resolver handles that; see _resolve_travellers).
    """
    if (n := _explicit_count_in_utterance(t)) is not None:
        return n
    t = (t or "").lower()

    # Party members named alongside the speaker — checked BEFORE the solo phrases so
    # "just me and my partner" isn't read as solo.
    if re.search(r"\b(my (wife|husband|partner|girlfriend|boyfriend|spouse))\b", t):
        return 2
    if "couple" in t and "couple of days" not in t and "couple of weeks" not in t:
        return 2
    if re.search(r"\bfamily\b", t):
        return 4

    # Solo. "only i", "only me", "just myself", "price for one", "travelling alone"…
    if re.search(r"\b(solo|alone|by myself|on my own|just myself|only myself)\b", t) \
       or re.search(r"\bonly\s+(i|me)\b", t) \
       or re.search(r"\bjust\s+(me|i)\b", t) \
       or re.search(r"\b(for|price for|just)\s+(one|1)\s*(person|traveller|traveler)?\b", t) \
       or re.search(r"\bi'?m\s+travell?ing\s+(alone|solo|by myself)\b", t) \
       or re.search(r"\bsingle\s+travell?er\b", t):
        return 1

    return None


def _travellers_from(history: list, message: str, default: int = 2) -> int:
    """Traveller count for this trip, from what the GUEST has said — most recent wins.

    Two rules, both learned from real failures:

    1. Only the guest's own words count. This used to scan the whole conversation as one
       string, INCLUDING Sasha's replies — so the moment she said "the estimated total for
       two travellers", that phrase became evidence of two travellers. The count fed itself
       and could never come down, no matter what the guest said next.

    2. The most recent statement wins. Scanning everything at once meant an early "with my
       wife" permanently outvoted a later "actually only I'm travelling" — the guest could
       correct Sasha and be ignored.
    """
    # This message first (it's the newest thing said), then back through the guest's history.
    if (n := _travellers_in_utterance(message)) is not None:
        return n
    for m in reversed(history or []):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue   # never let Sasha's own words be evidence
        if (n := _travellers_in_utterance(m.get("content") or "")) is not None:
            return n
    return default


async def _resolve_travellers(history: list, message: str) -> int:
    """Total party size for this trip, resolving natural-language party math.

    Regex can read an explicit count ("4 travellers", "just me"), but not the additive way
    guests actually grow a party: "my friend and his wife want to come with us" means +2, and
    the total is me + wife + friend + wife = 4. Getting that wrong is what shipped a plan titled
    "for Four" whose price and card still said two. So: an explicit count in the newest message
    still wins instantly (deterministic, zero latency); otherwise the fast model totals the party
    from the whole conversation. The build already costs a multi-second specialist call, so this
    small fast-model call adds nothing the guest notices, and it falls back to the regex scan on
    any failure.
    """
    # A HARD count stated right now — trust it, no model call. Relationship/solo/additive
    # phrasing deliberately does NOT short-circuit here: "me and my wife, and my friend and his
    # wife are joining" must reach the resolver to total 4, not stop at the first "my wife" → 2.
    if (n := _explicit_count_in_utterance(message)) is not None:
        return n

    convo = "\n".join(
        f"{'Guest' if m.get('role') == 'user' else 'Sasha'}: {m.get('content', '')}"
        for m in (history or [])
        if isinstance(m, dict) and (m.get("content") or "").strip()
    )
    convo = (convo + f"\nGuest: {message}").strip()
    try:
        resp = await asyncio.wait_for(
            client.messages.create(
                model=FAST_MODEL,
                max_tokens=4,
                system=cached_system(
                    "Count how many people are travelling ON THIS TRIP in total, from the whole "
                    "conversation. Include the guest unless they clearly exclude themselves. Add "
                    "each companion as they are mentioned — 'my wife' is +1, 'my friend and his "
                    "wife' is +2, 'a couple of friends' is +2. If the guest restates the count, the "
                    "MOST RECENT statement wins. If the number of travellers is NOT stated or "
                    "implied ANYWHERE in the conversation, answer 2 — the default booking is a "
                    "couple; do NOT default to 1. Only answer 1 when the guest clearly signals they "
                    "travel alone ('just me', 'solo', 'travelling by myself'). Reply with ONLY one "
                    "integer from 1 to 12 and nothing else."
                ),
                messages=[{"role": "user", "content": convo}],
            ),
            timeout=6.0,
        )
        out = "".join(b.text for b in resp.content if hasattr(b, "text"))
        if (m := re.search(r"\d+", out)):
            n = int(m.group())
            if 1 <= n <= 12:
                return n
    except Exception as e:
        print(f"[Itinerary] traveller resolver failed ({e}) — falling back to regex scan")

    # Deterministic fallback: most-recent explicit count in the transcript, else the default.
    return _travellers_from(history, message)


async def _enrich(data: dict, travellers: int = 2) -> None:
    days = data.get("days", []) or []

    # One image per day, matched to THAT DAY'S CITY.
    #
    # This used to run a single generic "Vietnam landscape travel scenery" search and deal the
    # results out by index, so a Hanoi day could be illustrated with a Ha Long Bay shot and a
    # Hoi An day with Sapa. (The old comment here claimed the results were "city-relevant" —
    # they never could be, the query never named a city.)
    #
    # Fetch per DISTINCT city, not per day: a 5-day trip across 3 cities costs 3 lookups, not 5,
    # which matters against a 50/hour Unsplash demo key. search_photos caches by resolved search
    # term, so a repeated city is free, and it falls back to the curated set rather than failing.
    cities = []
    for d in days:
        c = (d.get("city") or "").strip() or "Vietnam"
        if c not in cities:
            cities.append(c)

    async def _city_photos(city: str) -> tuple:
        try:
            # count=3 so days sharing a city get different shots rather than the same one twice.
            return city, await search_photos(f"{city} Vietnam travel", count=3)
        except Exception:
            return city, []

    by_city = dict(await asyncio.gather(*[_city_photos(c) for c in cities])) if cities else {}

    # Generic backstop for any city whose lookup came back empty.
    try:
        generic = await search_photos("Vietnam landscape travel scenery", count=max(len(days), 6))
    except Exception:
        generic = []

    seen_per_city: dict = {}

    carried_name = None         # last assigned hotel + its city + nightly rate, carried across
    carried_city = None         # genuine "same hotel" nights and day-trips from a base city
    carried_price = 0
    hotel_total = 0
    activity_count = 0
    for i, d in enumerate(days):
        city = d.get("city") or "Vietnam"
        # Rotate within this city's own set so consecutive days in one city differ, then fall
        # back to the generic batch, then to no image (the UI already guards on `d.image`).
        pool = by_city.get(city) or []
        if pool:
            n = seen_per_city.get(city, 0)
            seen_per_city[city] = n + 1
            d["image"] = pool[n % len(pool)]["url"]
        elif generic:
            d["image"] = generic[i % len(generic)]["url"]
        else:
            d["image"] = None
        given = (d.get("hotel") or "").strip()
        pool = VIETNAM_HOTELS.get(city)
        if given:
            hname, hcity = given, city
        elif carried_city == city and carried_name:
            hname, hcity = carried_name, carried_city          # genuinely the same hotel
        elif pool:
            hname, hcity = pool[0]["name"], city               # moved cities -> that city's stay
        elif carried_name:
            hname, hcity = carried_name, carried_city          # day-trip from the base city
        else:
            hname, hcity = None, None
        if hname:
            stars = _STARS_BY_NAME.get(hname, 5)
            price = _PRICE_BY_NAME.get(hname, 0) or carried_price
            carried_name, carried_city, carried_price = hname, hcity, price
            d["hotel"] = {
                "name": hname,
                "book_url": _booking_url(hname, hcity, travellers),
                "price_from": _PRICE_BY_NAME.get(hname, 0) or price,
                **social_proof(hname, stars),
            }
        else:
            d["hotel"] = None
        # Accommodation cost for THIS night (the final day is departure — no night).
        if i < len(days) - 1:
            hotel_total += carried_price
        acts = d.get("activities", []) or []
        activity_count += len(acts)
        for a in acts:
            a["book_url"] = _activity_link(a.get("name", ""), city)

    # Deterministic, defensible trip total — computed from real rates so Sasha never quotes a
    # random inflated figure. Rooms are per-night (cover the whole party); experiences and
    # meals scale with travellers; a flat allowance covers domestic transfers/cruise legs.
    n_days = len(days)
    experiences = activity_count * 35 * travellers
    meals = n_days * 45 * travellers
    transport = 350
    total = hotel_total + experiences + meals + transport
    data["estimated_total_usd"] = int(round(total / 10.0) * 10)  # nearest $10
    # Canonical party size on the itinerary itself, so the trip view reads the count Sasha
    # actually resolved for THIS plan — not a stale profile field. When the guest changes the
    # party ("make it 4"), the rebuilt plan carries the new number and the panel follows it.
    data["travellers"] = travellers
    data["cost_breakdown"] = {
        "hotels": int(hotel_total),
        "experiences": int(experiences),
        "meals": int(meals),
        "transport": int(transport),
        "travellers": travellers,
    }


# Local-first itinerary composition (default ON — demo requirement: everything local, near-
# realtime). The deterministic composer handles first builds and structural rebuilds (trip
# length, cities, party size) in milliseconds; only free-form REVISIONS — the guest asking to
# change something specific inside an existing plan — need the LLM's judgement, detected by
# the keywords below. Set DEMO_LOCAL_ITINERARY=0 to route every build through the LLM again.
_LOCAL_ITINERARY = os.getenv("DEMO_LOCAL_ITINERARY", "1").strip() in ("1", "true", "yes")
_REVISION_WORDS = (
    "swap", "replace", "instead of", "different hotel", "another hotel", "other hotel",
    "change the hotel", "change hotel", "different activit", "another activit", "remove",
    "skip ", "drop ", "take out", "get rid", "without ", "don't want", "dont want",
    "no longer", "cheaper", "upgrade", "more luxur", "less expensive", "switch",
)


def _is_revision(message: str) -> bool:
    low = (message or "").lower()
    return any(w in low for w in _REVISION_WORDS)


async def build_itinerary(message: str, history: list,
                          current_itinerary: "Optional[dict]" = None,
                          hotel_swap: "Optional[dict]" = None) -> dict:
    """Generate + enrich a day-by-day itinerary. Returns the itinerary dict or None.

    `current_itinerary` is the guest's STORED plan (enriched payload). Revisions edit it
    locally in milliseconds (add/remove a city, hotel swaps, cheaper/upgrade, activity
    changes); rebuilds keep its route. Only an unparseable revision reaches the LLM builder.
    `hotel_swap` = {"name","city"} — an already-resolved hotel change from the conductor,
    applied verbatim by the reviser (the name may not be in the curated pool).
    """
    history = history or []

    if _LOCAL_ITINERARY and (current_itinerary or {}).get("days"):
        # Reviser FIRST whenever a stored plan exists: it owns the change vocabulary
        # (add/remove city, hotel swap/cheaper/upgrade/named, activity swap/remove) and
        # returns None for anything that isn't a change — no gate mismatch possible.
        from app.services.local_itinerary import revise_local_itinerary
        data = revise_local_itinerary(current_itinerary, message, hotel_swap=hotel_swap)
        if data and data.get("days"):
            travellers = await _resolve_travellers(history, message)
            await _enrich(data, travellers)
            print(f"[Itinerary] revised locally: {len(data['days'])} days, {travellers} travellers")
            return data
        if _is_revision(message):
            print("[Itinerary] revision not locally parseable — falling back to LLM build")

    if _LOCAL_ITINERARY and not _is_revision(message):
        from app.services.local_itinerary import build_local_itinerary
        data = build_local_itinerary(message, history, current=current_itinerary)
        if data and data.get("days"):
            # Same party-resolution + enrichment the LLM path gets: real hotel rates,
            # booking links, per-city images, deterministic cost breakdown.
            travellers = await _resolve_travellers(history, message)
            await _enrich(data, travellers)
            print(f"[Itinerary] composed locally: {len(data['days'])} days, "
                  f"{travellers} travellers")
            return data
        print("[Itinerary] local composer unavailable — falling back to LLM build")

    ctx = " ".join(m.get("content", "") for m in history if isinstance(m, dict)) + " " + message
    cities = _find_destinations(ctx) or list(VIETNAM_HOTELS.keys())[:6]
    hotels_context = "; ".join(
        f"{c}: " + ", ".join(h["name"] for h in VIETNAM_HOTELS.get(c, [])) for c in cities
    )
    # Resolve the party size ONCE and tell the model explicitly. Left to infer it from the
    # transcript, it wrote couples' activities ("a romantic dinner for two") into a solo
    # trip — the words on the page contradicting the price beside them.
    travellers = await _resolve_travellers(history, message)
    system = _SYSTEM.replace("{hotels_context}", hotels_context).replace(
        "{travellers_context}",
        f"This trip is for EXACTLY {travellers} traveller{'s' if travellers != 1 else ''}. "
        + ("Write it for one person travelling alone: no couples' or group framing, no "
           "'the two of you'." if travellers == 1
           else f"Write activities suited to a party of {travellers}."),
    )
    messages = history[-12:] + [
        {"role": "user", "content": message + "\n\n(Generate the complete day-by-day itinerary now as JSON.)"}
    ]
    try:
        resp = await asyncio.wait_for(
            # 4000 tokens: a detailed 7-day itinerary (2-4 activities/day + descriptions)
            # overflowed the old 2200 cap, truncating the JSON so it failed to parse — the
            # card then kept the STALE plan while Sasha claimed she'd updated it. Higher cap
            # lets the full JSON come back intact.
            client.messages.create(model=SPECIALIST_MODEL, max_tokens=4000, system=system, messages=messages),
            # 25s (was 40): run_itinerary_intent retries once on a malformed result, and two
            # 40s attempts blew through the conductor's 45s ceiling -> agent timeout -> the
            # guest heard the generic failure line. 25 x 2 + resolver fits the budget.
            timeout=25.0,
        )
        raw = "".join(b.text for b in resp.content if hasattr(b, "text"))
    except Exception as e:
        print(f"[Itinerary] generation failed: {e}")
        return None

    data = _parse_json(raw)
    if not data or not data.get("days"):
        print("[Itinerary] could not parse itinerary JSON")
        return None

    # Same count the model was given, so the prose and the price can't disagree.
    await _enrich(data, travellers)
    return data
