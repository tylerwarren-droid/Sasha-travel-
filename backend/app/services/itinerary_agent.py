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
import re
from typing import Optional
from urllib.parse import quote_plus

from app.services.llm import client, SPECIALIST_MODEL
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


def _travellers_in_utterance(t: str) -> Optional[int]:
    """Traveller count stated in ONE utterance, or None if it doesn't mention it.

    Ordered most-specific first: an explicit number beats a solo phrase beats a relationship
    hint, so "just me and my wife" resolves to 2 (the wife wins over "just me"), while
    "only I'm travelling" resolves to 1.
    """
    t = (t or "").lower()

    # Explicit counts: "2 travellers", "for 3 people", "party of 4".
    m = re.search(r"\b(\d+)\s*(?:travel|people|person|adult|guest|of us|pax)", t)
    if not m:
        m = re.search(r"\bparty of\s*(\d+)", t)
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
        if re.search(rf"\bparty of {w}\b", t):
            return n

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


async def _enrich(data: dict, travellers: int = 2) -> None:
    days = data.get("days", []) or []

    # One image per day. Fetch a batch (varied even with the no-key fallback) and assign by
    # index; with a real Unsplash key these are city-relevant Vietnam shots.
    try:
        batch = await search_photos("Vietnam landscape travel scenery", count=max(len(days), 6))
    except Exception:
        batch = []

    carried_name = None         # last assigned hotel + its city + nightly rate, carried across
    carried_city = None         # genuine "same hotel" nights and day-trips from a base city
    carried_price = 0
    hotel_total = 0
    activity_count = 0
    for i, d in enumerate(days):
        d["image"] = batch[i % len(batch)]["url"] if batch else None
        city = d.get("city") or "Vietnam"
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
    data["cost_breakdown"] = {
        "hotels": int(hotel_total),
        "experiences": int(experiences),
        "meals": int(meals),
        "transport": int(transport),
        "travellers": travellers,
    }


async def build_itinerary(message: str, history: list) -> dict:
    """Generate + enrich a day-by-day itinerary. Returns the itinerary dict or None."""
    history = history or []
    ctx = " ".join(m.get("content", "") for m in history if isinstance(m, dict)) + " " + message
    cities = _find_destinations(ctx) or list(VIETNAM_HOTELS.keys())[:6]
    hotels_context = "; ".join(
        f"{c}: " + ", ".join(h["name"] for h in VIETNAM_HOTELS.get(c, [])) for c in cities
    )
    # Resolve the party size ONCE and tell the model explicitly. Left to infer it from the
    # transcript, it wrote couples' activities ("a romantic dinner for two") into a solo
    # trip — the words on the page contradicting the price beside them.
    travellers = _travellers_from(history, message)
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
            timeout=40.0,
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
