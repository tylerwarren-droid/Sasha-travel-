import asyncio
import json
import os
import re
import uuid
from typing import Any, Optional

from app.services.prompts import get_prompt_async
from app.services.llm import client, FAST_MODEL, cached_system
from app.services.booking_links import build_booking_links, _find_destinations
from app.services.hotels_db import recommend_hotels
from app.services.travel_search import find_flights, find_cabs, find_activities, find_restaurants, find_hotels_live
from app.services.tenant import ClientConfig
from app.services import chat_store

# Latency: spoken replies are read aloud in real time, so time-to-first-token dominates
# the felt delay. The general + merge calls run on the FAST_MODEL (Haiku 4.5, ≈2x faster
# wall-clock than Sonnet for these short 1–2 sentence replies). Specialist agents keep
# their own model choices (some need the smart model + tool use).
CONDUCTOR_MODEL = FAST_MODEL

# A spoken concierge reply only needs recent context. Trimming the history sent to the
# LLM shortens the prompt and cuts time-to-first-token on every turn. The full,
# untrimmed history is still returned to the client — this only bounds what we SEND.
# Env-tunable so the latency/context tradeoff can be dialed without a redeploy.
MAX_HISTORY_MESSAGES = int(os.getenv("CONDUCTOR_MAX_HISTORY", "20"))  # ≈10 turns

# Per-agent time budgets. Most agents are one short LLM call, where 20s is generous. The
# itinerary builder is different in kind: a large JSON generation PLUS enrichment (per-day
# photos, hotel lookups, booking links), measured at 13-21s for a 5-7 day plan — and
# run_itinerary_intent retries once on a malformed result, so its real worst case is ~2x a
# single build. Held to the flat 20s it was cancelled mid-build roughly half the time on
# 7-day plans, producing the worst failure this product has: Sasha announcing a plan that
# never appeared. (itinerary_agent even allows itself 40s internally for the LLM alone — a
# budget the caller made unreachable.) Kept below the frontend's 60s request timeout so the
# client still wins the race if something truly hangs.
DEFAULT_AGENT_TIMEOUT = float(os.getenv("AGENT_TIMEOUT_S", "20"))
AGENT_TIMEOUTS = {"itinerary": float(os.getenv("ITINERARY_TIMEOUT_S", "45"))}


def _trim_history(history: list) -> list:
    return history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history

# ─────────────────────────────────────────────
# INTENT CLASSIFICATION
# The Conductor reads every message and decides
# which agents to fire — can be multiple at once
# ─────────────────────────────────────────────

INTENT_CLASSIFIER_PROMPT = """You are The Conductor — the orchestrator of Sasha's specialist agents.

Your ONLY job is to read the user message and return a JSON object identifying which agents to activate.

Available agents:
- "golf": anything about golf courses, tee times, green fees, caddies, golf bookings
- "foto": requests for photos, images, visuals of destinations, hotels, courses, attractions
- "booking_confirmation": confirming existing hotel bookings, getting PMS reference numbers, contacting hotels about reservations
- "health": doctors, medical, pharmacy, clinic, telemedicine, illness, injury, prescription
- "beauty": spa, massage, nails, facial, hair, beauty treatments, salon
- "dog_walking": dog walker, pet care, dog sitting
- "golf": any mention of golf, playing, tee time, course, round, caddy, green fee, fairway
- "beauty": massage, spa, nails, facial, treatment, relaxation, beauty, salon, manicure, pedicure
- "health": doctor, medical, sick, pharmacy, clinic, hospital, hurt, ill, prescription, nurse
- "dog_walking": dog, pet, walk, sitting, kennel, grooming
- "booking_confirmation": confirm booking, hotel reference, PMS, booking.com ref, expedia ref
- "general": ONLY if absolutely nothing else fits

Return ONLY a JSON object like this:
{
  "intents": ["golf", "foto"],
  "primary": "golf",
  "context": "User wants golf courses in Danang with photos"
}

Examples:
- "I want to play golf in Danang" -> {"intents": ["golf", "foto"], "primary": "golf", "context": "golf in Danang"}
- "I need a massage after golf" -> {"intents": ["golf", "beauty"], "primary": "golf", "context": "golf and massage"}
- "Can you confirm my hotel booking" -> {"intents": ["booking_confirmation"], "primary": "booking_confirmation", "context": "confirm booking"}
- "I feel sick need a doctor" -> {"intents": ["health"], "primary": "health", "context": "medical help"}
- "Find me a dog walker in Hanoi" -> {"intents": ["dog_walking"], "primary": "dog_walking", "context": "dog walker Hanoi"}

Rules:
- Always include at least one intent
- "foto" should be added whenever a visual would help (destinations, courses, hotels)
- Multiple intents are fine — fire them all
- "general" is the fallback if nothing else fits
- Never return anything except the JSON object"""


async def classify_intents(user_message: str, conversation_history: list,
                           has_itinerary: Optional[bool] = None) -> dict:
    """Classify intents using fast keyword matching."""
    lower = user_message.lower()
    intents = []

    # Core travel-concierge domains. Non-travel agents (credit_card, health, beauty,
    # dog_walking, car_rental-insurance) and the old hallucination-prone smart_sasha flight
    # stub are intentionally DISABLED for the demo — a stray "points"/"sick"/"insurance"
    # must never hijack a travel turn. Flights/cabs/activities are now real web-searched
    # domains (see travel_search.py). Golf stays as a Vietnam activity.
    # "ba na hills" alone is the Golden Bridge / cable-car attraction, not the golf club —
    # asking about the bridge was routing people to a tee-time search. Name the course.
    GOLF_WORDS = ["golf", "tee time", "tee-time", "fairway", "caddy", "green fee", "golf course", "play golf", "montgomerie", "hoiana", "bluffs", "ba na hills golf", "vinpearl golf"]
    RESTAURANT_WORDS = ["restaurant", "dinner", "lunch", "breakfast", "eat", "food", "table", "reservation", "book a table", "dining", "cuisine", "cafe", "bar", "rooftop", "where to eat", "hungry"]
    BOOKING_WORDS = ["confirm booking", "hotel reference", "pms", "booking.com ref", "expedia ref", "booking number", "confirm my booking", "reservation number"]
    FOTO_WORDS = ["show me", "photo", "picture", "image", "what does", "what do", "look like"]
    # Flights — catches "book me a flight to Hanoi", "fly to Da Nang", "cheapest flights", etc.
    # Every entry must actually imply AIR travel. "how do i get to" / "getting there" used to
    # live here and caught road questions ("how do I get to Ba Na Hills from Hoi An?"), sending
    # them to a flight search for a place with no airport.
    FLIGHT_WORDS = ["flight", "flights", "fly ", "flying", "airfare", "air fare", "airline", "airlines", "plane ticket", "plane tickets", "fly to", "direct flight", "nonstop"]
    # Cabs / airport transfers — phrase-based so "cab" never matches "cabin" (Ha Long cruise cabins).
    CAB_WORDS = ["taxi", "book a cab", "grab a cab", "call a cab", "need a cab", "get a cab", "cab to", "cab from", "airport transfer", "airport pickup", "airport pick up", "airport pick-up", "pick up from the airport", "pickup from airport", "car to the airport", "ride to the airport", "ride from the airport", "private car", "private transfer", "airport car", "chauffeur", "shuttle", "transfer to my hotel", "transfer from the airport"]
    ACTIVITY_WORDS = ["things to do", "thing to do", "activities", "activity", "tour", "tours", "excursion", "experience", "experiences", "what to do", "cooking class", "snorkel", "snorkeling", "diving", "scuba", "boat trip", "boat tour", "day trip", "sightseeing", "attractions", "kayak", "kayaking", "trekking", "hiking", "cyclo", "street food tour", "food tour", "lantern making", "market tour", "workshop", "sunrise tour", "sunset cruise"]

    if any(w in lower for w in GOLF_WORDS):
        intents.append("golf")
        intents.append("foto")
    if any(w in lower for w in FLIGHT_WORDS):
        intents.append("flight")
    if any(w in lower for w in CAB_WORDS):
        intents.append("cab")
    if any(w in lower for w in ACTIVITY_WORDS):
        intents.append("activity")
    # Restaurant only fires when actively seeking a restaurant — not just mentioning food/dining
    RESTAURANT_ACTION_WORDS = ["find", "book", "reserve", "recommend", "suggestion", "where to", "looking for", "need a", "want a", "good restaurant", "best restaurant", "book a table", "make a reservation", "dinner tonight", "lunch today", "place to eat"]
    restaurant_action = any(w in lower for w in RESTAURANT_ACTION_WORDS)
    restaurant_topic = any(w in lower for w in RESTAURANT_WORDS)
    if restaurant_topic and restaurant_action:
        intents.append("restaurant")
    # Carry restaurant context into an immediate FOLLOW-UP ("book the second one"), but only
    # from the last couple of turns. This used to scan the ENTIRE conversation, so one
    # "recommend a restaurant" early on made every later turn — golf, flights, anything — fire
    # a live restaurant search and bolt dining suggestions onto unrelated answers for the rest
    # of the session.
    recent_text = " ".join(
        (m.get("content") or "") for m in conversation_history[-2:] if isinstance(m, dict)
    ).lower()
    if ("restaurant" not in intents
            and any(w in recent_text for w in RESTAURANT_WORDS)
            and any(w in recent_text for w in RESTAURANT_ACTION_WORDS)):
        intents.append("restaurant")
    if any(w in lower for w in BOOKING_WORDS):
        intents.append("booking_confirmation")
    if any(w in lower for w in FOTO_WORDS) and "foto" not in intents:
        intents.append("foto")

    # Itinerary build — the user explicitly asks to see the full plan, OR confirms after
    # Sasha has just offered to build it. This supersedes other intents (it's the action).
    ITINERARY_WORDS = [
        "itinerary", "day by day", "day-by-day", "day to day", "full plan", "whole plan",
        "the full trip", "put it together", "put it all together", "plan it all out",
        "build the plan", "build my trip", "create the plan", "finalize", "finalise",
        "show me the plan", "see the plan", "full trip plan",
    ]
    # Fixed phrases can't cover how people actually ask. "Build a 5-day trip to Hue with a
    # cooking class" matched none of the above but DID match the activity keywords, so Sasha
    # answered with a list of tours and built nothing. A build verb aimed at a trip is an
    # itinerary request however it's worded.
    ITINERARY_RE = re.compile(
        r"\b(build|plan|create|put together|map out|design|organi[sz]e|sort out)\b"
        r"[^.?!]{0,40}?\b(\d+\s*[-–]?\s*day\b|itinerary|trip|holiday|vacation|week\b)",
    )
    AFFIRMATIONS = {
        "yes", "yes please", "sure", "go ahead", "please do", "do it", "build it",
        "create it", "sounds good", "okay", "ok", "yep", "yeah", "absolutely",
        "lets do it", "let's do it", "go for it", "yes go ahead", "please",
    }
    last_assistant = ""
    for m in reversed(conversation_history):
        if isinstance(m, dict) and m.get("role") == "assistant":
            last_assistant = (m.get("content") or "").lower()
            break
    # Loose affirmation: a short reply that IS or STARTS WITH an affirmation token
    # ("yeah lets do that", "yes please build it", "sure go ahead"), not just an exact
    # one-word match — voice STT almost never returns a bare "yes", so exact matching
    # silently dropped real confirmations and the itinerary never built.
    _clean = lower.strip().rstrip(".!?")
    _words = _clean.split()
    _first = _words[0] if _words else ""
    user_affirms = (
        _clean in AFFIRMATIONS
        or (_first in {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "absolutely",
                       "definitely", "perfect", "great", "sounds"} and len(_words) <= 6)
        or any(_clean.startswith(a) for a in
               ("lets do", "let's do", "go ahead", "do it", "build it", "sounds good",
                "please do", "go for it"))
    )
    # Broadened offer detection: Sasha offers to build the plan in many phrasings
    # ("map out the week", "shall I plan your trip", "put together your itinerary"). If the
    # last thing Sasha said was an OFFER to build, an affirmation MUST trigger the build —
    # otherwise the general agent just claims it's "ready on the right" while the panel
    # keeps the starter card.
    OFFER_CUES = (
        "itinerary", "day-by-day", "day by day", "put together", "map out", "map it out",
        "plan out", "plan your", "plan the", "build your", "build the", "full plan",
        "whole week", "full week", "the week", "shall i", "want me to",
        "would you like me to",
    )
    offered_itinerary = any(k in last_assistant for k in OFFER_CUES)
    if any(w in lower for w in ITINERARY_WORDS) or ITINERARY_RE.search(lower) or (user_affirms and offered_itinerary):
        intents = ["itinerary"]

    # Revise an EXISTING itinerary — once a structured plan is on the board, a swap/change
    # request must REBUILD it. Otherwise a conversational agent just claims the change
    # ("I've swapped you to Capella Hanoi") while the card keeps the old hotel, so Sasha
    # and the card contradict each other. Gate on a plan already existing in the history so
    # these broad verbs don't hijack ordinary chat.
    # A modify verb + a plan target catches natural phrasings like "change my HANOI hotel to
    # Capella" or "swap the day-3 resort", which a fixed-phrase list misses.
    REVISE_VERBS = ["swap", "replace", "switch", "change", "upgrade", "downgrade", "different", "move"]
    REVISE_TARGETS = ["hotel", "hotels", "stay", "resort", "cruise", "night", "nights"]
    revise_combo = any(v in lower for v in REVISE_VERBS) and any(t in lower for t in REVISE_TARGETS)
    REVISE_STANDALONE = [
        "cheaper", "more luxurious", "more luxury", "more budget", "tighter budget",
        "add a day", "remove a day", "drop a day", "extra day", "fewer days", "more days",
        "shorten", "extend the trip", "revise", "rebuild the", "redo the",
    ]
    revise_standalone = any(w in lower for w in REVISE_STANDALONE)
    # Changing WHO is travelling re-prices the whole trip (experiences and meals scale per
    # head), so it has to REBUILD, not just get talked about. Without this, "only I will be
    # travelling, give me the price for that" fell through to ordinary chat and Sasha simply
    # halved the number out loud — a figure that matched no itinerary, while the plan on the
    # right still said two.
    party_change = re.search(
        r"\b(only|just)\s+(i|me)\b|\bby myself\b|\bon my own\b|\b(solo|alone)\b"
        r"|\bjust\s+(one|1)\b|\b(price|total|cost)\s+for\s+(one|1|just me|myself)\b"
        r"|\b(\d+|one|two|three|four|five|six)\s+(of us|travell?ers?|people|adults)\b"
        r"|\bmy (wife|husband|partner|girlfriend|boyfriend)\s+(is|will be)\s+(coming|joining)\b"
        r"|\bbringing\s+(my|the)\b",
        lower,
    ) is not None
    # Changing WHERE the trip goes must rebuild too. "Actually I'd rather go to Hoi An than
    # Hanoi" names no hotel and uses no revise verb, so it fell through to chat: Sasha talked
    # happily about Hoi An while every day on the plan still said Hanoi. Requires BOTH a named
    # destination and an explicit change cue, so ordinary questions ("tell me about Hoi An")
    # stay conversational and don't blow away the plan.
    DEST_CHANGE_CUES = ("rather", "instead", "prefer", "change to", "switch to", "swap to",
                        "skip", "swap out", "replace")
    dest_change = bool(_find_destinations(lower)) and any(c in lower for c in DEST_CHANGE_CUES)

    revise_standalone = revise_standalone or party_change or dest_change
    # Does a real plan exist? `has_itinerary` is the authoritative answer — the caller looked
    # it up in the DB. Fall back to scanning Sasha's own words only when the caller couldn't
    # tell us (no session). That fallback is WRONG and is why "book it" used to take payment
    # for a trip that was never built: Sasha's OFFER ("shall I put together your day-by-day
    # itinerary?") contains the very words the check looks for, so it matched itself.
    if has_itinerary is None:
        assistant_text = " ".join(
            (m.get("content") or "") for m in conversation_history
            if isinstance(m, dict) and m.get("role") == "assistant"
        ).lower()
        itinerary_exists = any(k in assistant_text for k in ("on the right", "day plan", "day-by-day", "day by day"))
    else:
        itinerary_exists = bool(has_itinerary)

    # A revise word only means "rebuild the plan" when the turn isn't already about something
    # specific. Otherwise the bare word "cheaper" in "find me a cheaper FLIGHT to Hanoi"
    # clobbered the correct flight intent and rebuilt the whole itinerary instead.
    if not intents and itinerary_exists and (revise_combo or revise_standalone):
        intents = ["itinerary"]

    # Book the whole trip — once a plan exists and the user says to book it, confirm the
    # booking (the UI then locks the final itinerary, ends the session, and offers PDF/share).
    BOOK_WORDS = [
        "book it", "book the trip", "book this trip", "book this", "book the whole",
        "book my trip", "book everything", "book the plan", "book all of it", "book now",
        "make the booking", "confirm the trip", "confirm the booking", "lets book",
        "let's book", "go ahead and book", "reserve the trip", "reserve it",
        "purchase the trip", "purchase it", "i'll take it", "ill take it", "i will take it",
    ]
    offered_booking = any(k in last_assistant for k in (
        "book the whole trip", "shall i book", "ready to book", "save it as a pdf",
        # Sasha's own payment request — "yes"/"go ahead" after it must re-surface the
        # payment step rather than falling through to ordinary chat.
        "make the payment", "finish booking",
    ))
    if itinerary_exists and (any(w in lower for w in BOOK_WORDS) or (user_affirms and offered_booking)):
        intents = ["book_trip"]

    if not intents:
        intents = ["general"]

    primary = intents[0]
    print(f"[Conductor] Keywords matched: {intents}")
    return {"intents": list(dict.fromkeys(intents)), "primary": primary, "context": user_message}


# ─────────────────────────────────────────────
# AGENT REGISTRY
# Each agent is registered here with its runner
# Adding a new agent = adding one entry here
# ─────────────────────────────────────────────

async def run_general(message: str, history: list, general_prompt: str) -> dict:
    """General Sasha conversation — travel advice, destinations, planning."""
    response = await client.messages.create(
        model=CONDUCTOR_MODEL,
        max_tokens=200,  # short spoken replies — voice interface
        system=cached_system(general_prompt),
        messages=_trim_history(history) + [{"role": "user", "content": message}]
    )
    return {
        "agent": "general",
        "response": response.content[0].text,
        "data": {}
    }


async def run_golf_intent(message: str, history: list) -> dict:
    """Route to golf agent."""
    from app.services.golf_agent import run_golf_agent
    result = await run_golf_agent(message, history)
    return {
        "agent": "golf",
        "response": result["response"],
        "data": {"tools_used": result.get("tools_used", [])}
    }


async def run_foto_intent(message: str, history: list, context: str = "") -> dict:
    """Route to foto agent — fetch contextual photos."""
    from app.services.foto_agent import search_photos, extract_visual_context
    
    # Extract what to search for
    visual_ctx = extract_visual_context(context or message)
    
    query = message
    photo_type = "general"
    
    if visual_ctx["golf_courses"]:
        query = f"{visual_ctx['golf_courses'][0]} golf Vietnam"
        photo_type = "golf"
    elif visual_ctx["destinations"]:
        query = f"{visual_ctx['destinations'][0]} Vietnam travel"
        photo_type = "destination"
    
    photos = await search_photos(query, count=3)
    return {
        "agent": "foto",
        "response": "",  # Foto doesn't speak — it just provides visuals
        "data": {"photos": photos, "query": query, "type": photo_type}
    }


async def run_booking_confirmation_intent(message: str, history: list) -> dict:
    """Route to booking confirmation agent."""
    from app.services.booking_confirmation_agent import run_booking_agent
    result = await run_booking_agent(message, history)
    return {
        "agent": "booking_confirmation",
        "response": result["response"],
        "data": {"tools_used": result.get("tools_used", [])}
    }


async def run_health_intent(message: str, history: list) -> dict:
    """Route to health agent."""
    from app.services.health_agent import run_health_agent
    result = await run_health_agent(message, history)
    return {
        "agent": "health",
        "response": result["response"],
        "data": {"tools_used": result.get("tools_used", [])}
    }


async def run_beauty_intent(message: str, history: list) -> dict:
    """Route to beauty agent."""
    from app.services.beauty_agent import run_beauty_agent
    result = await run_beauty_agent(message, history)
    return {
        "agent": "beauty",
        "response": result["response"],
        "data": {"tools_used": result.get("tools_used", [])}
    }


async def run_dog_walking_intent(message: str, history: list) -> dict:
    """Route to dog walking agent."""
    from app.services.dog_walking_agent import run_dog_walking_agent
    result = await run_dog_walking_agent(message, history)
    return {
        "agent": "dog_walking",
        "response": result["response"],
        "data": {"tools_used": result.get("tools_used", [])}
    }


async def run_restaurant_intent(message: str, history: list) -> dict:
    """Real restaurants via live web search — surfaced as a booking card with reserve links.

    (Replaces the old email/phone reservation agent, which faked a 'sent' confirmation when
    Resend/Bland keys were absent and CC'd a hardcoded personal inbox. For the demo we show
    real places and hand off to the provider to reserve — honest and can't-fail.)
    """
    dest = _dest_in_play(message, history)
    card = await find_restaurants(dest, request_hint=message)
    opts = card.get("options", [])
    names = ", ".join(o["name"] for o in opts[:3] if o.get("name"))
    spoken = f"A few great places to eat in {dest} — {names}. They're on the right, tap any to see the menu and reserve."
    return {"agent": "restaurant", "response": spoken, "data": {"booking": card}}


def _dest_in_play(message: str, history: list) -> str:
    """Best-guess Vietnam destination from this message, else recent history, else 'Vietnam'."""
    htext = " ".join(m.get("content", "") for m in (history or []) if isinstance(m, dict))
    found = _find_destinations(message) or _find_destinations(htext)
    return found[0] if found else "Vietnam"


def _named_options(options: list, limit: int = 3) -> str:
    """A brief spoken phrase naming a few options with prices, for the avatar to read."""
    parts = []
    for o in options[:limit]:
        price = o.get("price")
        parts.append(f"{o.get('name', 'an option')}{f' from {price}' if price else ''}")
    return ", ".join(parts)


async def run_flight_intent(message: str, history: list) -> dict:
    """Real flight options via live web search — surfaced as a booking card."""
    dest = _dest_in_play(message, history)
    card = await find_flights(dest, when=message)
    opts = card.get("options", [])
    has_prices = any(o.get("price") for o in opts)
    if has_prices:
        spoken = f"I found a few flights to {dest} — {_named_options(opts)}. They're on the right, just tap one to book."
    else:
        spoken = f"Here's where to compare and book your flights to {dest} — the card's on the right."
    return {"agent": "flight", "response": spoken, "data": {"booking": card}}


async def run_cab_intent(message: str, history: list) -> dict:
    """Real airport-transfer / taxi options via live web search — surfaced as a booking card."""
    dest = _dest_in_play(message, history)
    card = await find_cabs(dest, detail_hint=message)
    opts = card.get("options", [])
    has_prices = any(o.get("price") for o in opts)
    if has_prices:
        spoken = f"For getting around {dest}, here are a few transfer options — {_named_options(opts)}. Tap any to book on the right."
    else:
        spoken = f"Here's where to book a private car or taxi for {dest} — the card's on the right."
    return {"agent": "cab", "response": spoken, "data": {"booking": card}}


async def run_activity_intent(message: str, history: list) -> dict:
    """Real bookable activities via live web search — surfaced as a booking card."""
    dest = _dest_in_play(message, history)
    card = await find_activities(dest, interest=message)
    opts = card.get("options", [])
    has_prices = any(o.get("price") for o in opts)
    if has_prices:
        spoken = f"A few things you can book in {dest} — {_named_options(opts)}. They're on the right with prices and links."
    else:
        spoken = f"Here are some experiences you can book in {dest} — the card's on the right."
    return {"agent": "activity", "response": spoken, "data": {"booking": card}}



async def run_credit_card_intent(message: str, history: list) -> dict:
    """Route to credit card intelligence agent."""
    from app.services.credit_card_agent import run_credit_card_agent
    result = await run_credit_card_agent(message, history)
    return {
        "agent": "credit_card",
        "response": result["response"],
        "data": {"tools_used": result.get("tools_used", [])}
    }


async def run_car_rental_intent(message: str, history: list) -> dict:
    """Route to car rental insurance agent."""
    from app.services.car_rental_agent import run_car_rental_agent
    result = await run_car_rental_agent(message, history)
    return {
        "agent": "car_rental",
        "response": result["response"],
        "data": {"tools_used": result.get("tools_used", [])}
    }



async def run_smart_sasha_intent(message: str, history: list) -> dict:
    """Route to Smart Sasha search agent."""
    from app.services.smart_sasha_agent import run_smart_sasha_agent
    result = await run_smart_sasha_agent(message, history)
    return {
        "agent": "smart_sasha",
        "response": result["response"],
        "data": {"tools_used": result.get("tools_used", [])}
    }

async def run_itinerary_intent(message: str, history: list) -> dict:
    """Build the full day-by-day itinerary and surface it to the UI."""
    from app.services.itinerary_agent import build_itinerary
    itin = await build_itinerary(message, history)
    if not itin:
        # The builder occasionally returns nothing (LLM returned malformed JSON, etc.).
        # Retry once — a bare empty response leaves the avatar silent AND the panel stale,
        # which is exactly the "it said ready but nothing changed" failure. One more try
        # usually succeeds.
        itin = await build_itinerary(message, history)
    if not itin:
        # Still failed — speak a graceful line instead of going silent, and do NOT claim
        # the plan is on the right (it isn't).
        return {
            "agent": "itinerary",
            "response": (
                "I hit a snag pulling your full plan together just now — give me one more "
                "moment and ask me to build it again."
            ),
            "data": {},
        }
    n = len(itin.get("days", []))
    spoken = (
        f"Here's your full {n}-day itinerary — take a look on the right! Have a browse, and "
        "just tell me if you'd like to swap any of the hotels or activities."
    )
    return {"agent": "itinerary", "response": spoken, "data": {"itinerary": itin}}


async def run_book_trip_no_plan_intent(message: str, history: list) -> dict:
    """The guest asked to book, but nothing has actually been built yet.

    Reachable because Sasha OFFERS to plan long before she plans, and a guest can say "book
    it" at any point. Previously this path still asked for payment and claimed the itinerary
    was "up on the right" — selling a trip that did not exist. Ask to build it instead.
    """
    return {
        "agent": "book_trip",
        "response": (
            "I'd love to get that booked for you — I just haven't built your plan yet. "
            "Shall I put the full day-by-day itinerary together now, so you can see exactly "
            "what you're booking?"
        ),
        "data": {},
    }


async def run_book_trip_intent(message: str, history: list) -> dict:
    """The customer asked to book. Take them to PAYMENT — do not confirm the booking here.

    This intent used to mint a booking ref and announce "your trip is booked!" outright, with
    no money ever changing hands. That made Sasha lie: the customer heard a confirmation for a
    trip nobody had paid for. Now this step only *requests* payment (action=await_payment); the
    UI shows the complete itinerary and opens Stripe Checkout. The booking is confirmed — and
    the ref minted — only after Stripe reports a successful payment, on the way back.
    """
    spoken = (
        "Lovely — I've put your complete itinerary up on the right so you can look it over. "
        "Make the payment to finish booking, and I'll have everything reserved for you the "
        "moment it goes through."
    )
    return {"agent": "book_trip", "response": spoken, "data": {"action": "await_payment"}}


# Agent registry — maps intent names to runner functions. Only the travel-concierge
# domains are wired for the demo; the non-travel agents (health/beauty/dog_walking/
# credit_card/car_rental) and the smart_sasha flight stub are disabled in classify_intents
# and intentionally left out here so they can never be routed.
AGENT_REGISTRY = {
    "itinerary": run_itinerary_intent,
    "book_trip": run_book_trip_intent,
    "book_trip_no_plan": run_book_trip_no_plan_intent,
    "flight": run_flight_intent,
    "cab": run_cab_intent,
    "activity": run_activity_intent,
    "golf": run_golf_intent,
    "foto": run_foto_intent,
    "booking_confirmation": run_booking_confirmation_intent,
    "restaurant": run_restaurant_intent,
    "general": run_general,
}


# ─────────────────────────────────────────────
# THE CONDUCTOR
# Classifies, fires agents in parallel, merges
# ─────────────────────────────────────────────

# Display name → instruction language for the LLM. English is the default no-op.
LANGUAGE_NAMES = {
    "en": "English", "vi": "Vietnamese", "ko": "Korean", "zh": "Chinese (Mandarin)",
    "ja": "Japanese", "fr": "French", "es": "Spanish", "de": "German", "hi": "Hindi",
}


async def conduct(
    user_message: str,
    conversation_history: list = None,
    client_config: Optional[ClientConfig] = None,
    language: str = "en",
    user_name: Optional[str] = None,
    force_intent: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """
    The Conductor — main entry point.
    Classifies intents, fires agents in parallel, merges results.

    `force_intent` skips keyword classification when the CALLER already knows what the user
    asked for — e.g. they tapped "Build this" on an idea card. Classification has to guess
    from wording, and it guessed wrong here: an idea's prompt ("build a 5-day trip to Hue,
    royal tombs, cooking class") tripped the activity keywords and Sasha answered with a list
    of tours instead of building the plan. A pressed button is not a sentence to interpret.
    """
    if conversation_history is None:
        conversation_history = []

    # Recent conversation text — used so booking links/hotels keep the destination in mind
    # across turns (e.g. the city was named two turns ago, not in this message).
    history_text = " ".join(
        m.get("content", "") for m in conversation_history[-6:] if isinstance(m, dict)
    )

    # Step 1 — Load system prompts from DB (TTL-cached; falls back to static)
    general_prompt = await get_prompt_async("conductor.general")
    merge_prompt = await get_prompt_async("conductor.merge")

    # Apply client-specific persona name if different from default
    persona = (client_config.persona_name if client_config else None) or "Sasha"
    if persona != "Sasha":
        general_prompt = general_prompt.replace("Sasha", persona)
        merge_prompt = merge_prompt.replace("Sasha", persona)

    # Multilingual: instruct the spoken agents to reply entirely in the chosen language.
    lang_name = LANGUAGE_NAMES.get((language or "en").lower())
    if lang_name and lang_name != "English":
        lang_directive = (
            f"\n\nIMPORTANT: The traveller is speaking {lang_name}. Reply ENTIRELY in "
            f"{lang_name}, naturally and fluently — every word, including greetings."
        )
        general_prompt += lang_directive
        merge_prompt += lang_directive

    # Personalization: address the traveller by name (single hardcoded user for now; when a
    # real auth flow lands, user_name flows straight through from the authenticated principal).
    name = (user_name or "").strip().split()[0] if (user_name or "").strip() else ""
    if name:
        name_directive = (
            f"\n\nThe traveller's name is {name}. Open the conversation by greeting them warmly "
            f"by name (e.g. \"Hi {name}!\"), and use their first name occasionally when it feels "
            f"natural. Do not overuse it."
        )
        general_prompt += name_directive
        merge_prompt += name_directive

    # Is there a REAL plan for this session? Ask the database, not Sasha's own wording.
    stored_itinerary = await chat_store.latest_itinerary_for_session(session_id) if session_id else None
    has_itinerary = bool(stored_itinerary) if session_id else None

    # Step 2 — Classify intents (unless the caller already told us the intent)
    if force_intent and force_intent in AGENT_REGISTRY:
        intents = [force_intent]
        context = user_message
        print(f"[Conductor] Intent forced by caller: {force_intent}")
    else:
        classification = await classify_intents(user_message, conversation_history, has_itinerary)
        intents = classification.get("intents", ["general"])
        context = classification.get("context", user_message)

    # Asking to book with nothing built is a different conversation from asking to book a real
    # plan. Route it somewhere that offers to build instead of somewhere that takes money.
    if intents == ["book_trip"] and session_id and not stored_itinerary:
        print("[Conductor] book_trip requested but no itinerary exists for this session")
        intents = ["book_trip_no_plan"]
    
    print(f"[Conductor] Intents: {intents}")

    # If a destination is named, ground the general agent in the REAL hotels we'll show as
    # booking cards, so Sasha names the same properties she's recommending (not invented ones).
    # The curated list gates relevance instantly; when it fires we upgrade it to LIVE
    # web-searched hotels for that destination (real current inventory), keeping the curated
    # set as a fallback. Resolved ONCE here and reused for the final card so speech and card agree.
    # Keep each turn focused: when the guest asked for a specific booking (flight/cab/activity/
    # restaurant), don't also clutter with hotel cards (and skip the live-hotel search latency)
    # UNLESS they explicitly ask where to stay. "to my hotel" (a transfer) must not surface hotels.
    _lower_msg = user_message.lower()
    _specific_booking = bool({"flight", "cab", "activity", "restaurant"} & set(intents))
    _strong_stay = any(p in _lower_msg for p in (
        "where to stay", "where should i stay", "place to stay", "somewhere to stay",
        "book a hotel", "find a hotel", "find me a hotel", "recommend a hotel", "need a hotel",
        "want a hotel", "hotel recommendation", "hotels in", "stay in ",
    ))
    _want_hotels = (not _specific_booking) or _strong_stay
    early_hotels = recommend_hotels(user_message, "", intents, history_text) if _want_hotels else []
    if early_hotels:
        try:
            live_hotels = await find_hotels_live(early_hotels[0].get("city", ""))
            if live_hotels:
                early_hotels = live_hotels
        except Exception as e:
            print(f"[Conductor] live hotels failed, using curated: {e}")
    if early_hotels:
        hotel_lines = "; ".join(
            f"{h['name']} ({h['stars']}-star, from ${h['price_from']}/night)" for h in early_hotels
        )
        general_prompt = general_prompt + (
            "\n\nIf the user asks where to stay or about hotels, recommend ONE or TWO of these "
            "specific properties by name in your spoken reply (their booking links appear "
            f"automatically below the chat): {hotel_lines}."
        )

    # Step 3 — Fire all relevant agents in parallel
    tasks = []
    for intent in intents:
        runner = AGENT_REGISTRY.get(intent, run_general)
        if intent == "foto":
            tasks.append((intent, runner(user_message, conversation_history, context)))
        elif intent == "general":
            tasks.append((intent, runner(user_message, conversation_history, general_prompt)))
        else:
            tasks.append((intent, runner(user_message, conversation_history)))

    async def run_with_timeout(intent, task):
        # Agents are not equally fast, so one flat ceiling was wrong. A chat reply is a single
        # short LLM call; building an itinerary is a large JSON generation PLUS enrichment
        # (per-day photos, hotel lookups, booking links) and measures 13-21s. At the old flat
        # 20s it was a coin flip: a 7-day plan (the centrepiece of the demo) got cancelled
        # mid-build roughly half the time, Sasha said the plan was ready, and the Trip tab
        # stayed empty. itinerary_agent even allows itself 40s internally for the LLM alone —
        # a budget the caller made unreachable.
        timeout = AGENT_TIMEOUTS.get(intent, DEFAULT_AGENT_TIMEOUT)
        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"[Conductor] Agent '{intent}' timed out after {timeout}s")
            return {"agent": "timeout", "response": "", "data": {}}
        except Exception as e:
            print(f"[Conductor] Agent '{intent}' error: {e}")
            return {"agent": "error", "response": "", "data": {}}

    results = await asyncio.gather(*[run_with_timeout(i, t) for i, t in tasks], return_exceptions=True)

    # Step 4 — Collect valid results
    agent_responses = []
    photos = []
    tools_used = []
    itinerary = None
    action = None
    booking_ref = None
    bookings = []  # typed booking cards (flight/cab/activity) surfaced this turn

    for result in results:
        if isinstance(result, Exception):
            print(f"[Conductor] Agent error: {result}")
            continue

        if result["agent"] == "foto":
            photos = result["data"].get("photos", [])
        elif result["agent"] in ("flight", "cab", "activity", "restaurant"):
            card = result["data"].get("booking")
            if card:
                bookings.append(card)
            if result.get("response"):
                agent_responses.append({"agent": result["agent"], "response": result["response"]})
        elif result["agent"] == "itinerary":
            itinerary = result["data"].get("itinerary")
            if result.get("response"):
                agent_responses.append({"agent": "itinerary", "response": result["response"]})
        elif result["agent"] in ("book_trip", "book_trip_no_plan"):
            action = result["data"].get("action")
            booking_ref = result["data"].get("booking_ref")
            if result.get("response"):
                agent_responses.append({"agent": "book_trip", "response": result["response"]})
        elif result.get("response"):
            agent_responses.append({
                "agent": result["agent"],
                "response": result["response"]
            })
            if result["data"].get("tools_used"):
                tools_used.extend(result["data"]["tools_used"])

    # A freshly built plan becomes the server's record of this trip: what it is and what it
    # costs. Everything downstream depends on this existing — "is there a plan to book?" and
    # "what is the real price?" are both answered from here, not from the browser.
    if itinerary and itinerary.get("days"):
        itinerary_id = str(uuid.uuid4())
        itinerary["id"] = itinerary_id
        await chat_store.save_itinerary(
            itinerary_id=itinerary_id,
            session_id=session_id or "",
            user_id=user_id or chat_store.DEMO_USER_ID,
            title=itinerary.get("title") or "",
            total_usd=itinerary.get("estimated_total_usd") or 0,
            payload=itinerary,
        )

    # Step 5 — Merge responses
    if len(agent_responses) == 0:
        # No specialist produced a usable reply (e.g. a tool agent returned nothing on a
        # simple follow-up like "No."). Fall back to the GENERAL conversational agent so
        # Sasha stays in context instead of a canned "I'm here to help" that derails the chat.
        try:
            gen = await asyncio.wait_for(
                run_general(user_message, conversation_history, general_prompt), timeout=20.0
            )
            final_response = gen.get("response") or "Could you tell me a little more about what you're after?"
        except Exception as e:
            print(f"[Conductor] general fallback failed ({e})")
            final_response = "Could you tell me a little more about what you're after?"
    elif len(agent_responses) == 1:
        final_response = agent_responses[0]["response"]
    else:
        # Multiple agents responded — merge them
        combined = "\n\n".join([f"[{r['agent'].upper()}]: {r['response']}" for r in agent_responses])
        try:
            merge_response = await asyncio.wait_for(
                client.messages.create(
                    model=CONDUCTOR_MODEL,
                    max_tokens=250,  # short spoken replies — voice interface
                    system=cached_system(merge_prompt),
                    messages=[{"role": "user", "content": f"User asked: {user_message}\n\nAgent responses:\n{combined}"}]
                ),
                timeout=20.0,
            )
            final_response = merge_response.content[0].text
        except Exception as e:
            # Never let a merge failure swallow the whole turn — fall back to the
            # first agent's answer so the avatar always says something useful.
            print(f"[Conductor] Merge failed ({e}) — using first agent response")
            final_response = agent_responses[0]["response"]

    # When a structured itinerary was (re)built this turn, the SPOKEN reply MUST match the
    # card. The conversational/merge agents otherwise invent hotel names and totals that
    # contradict the real itinerary (e.g. Sasha says "Capella, ~$3,200" while the card shows
    # "Sofitel, $8,400"). Ground the speech in the actual itinerary data so they always agree.
    if itinerary:
        _days = itinerary.get("days", []) or []
        _n = len(_days)
        _total = itinerary.get("estimated_total_usd")
        _title = (itinerary.get("title") or "your itinerary").strip()
        _first_hotel = next(
            ((d.get("hotel") or {}).get("name")
             for d in _days
             if isinstance(d.get("hotel"), dict) and (d.get("hotel") or {}).get("name")),
            None,
        )
        _total_str = (
            f" The estimated total for two — hotels, activities and meals — comes to about ${int(_total):,}."
            if isinstance(_total, (int, float)) and _total else ""
        )
        _hotel_str = f" You'll start at {_first_hotel}." if _first_hotel else ""
        final_response = (
            f"All set — your {_n}-day plan, {_title}, is live on the right.{_hotel_str}{_total_str} "
            "Have a browse, and just tell me if you'd like to swap any of the hotels or activities."
        )

    # Step 6 — Update conversation history
    updated_history = conversation_history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": final_response}
    ]

    # Actionable booking surfaces for whatever Sasha is recommending this turn.
    links = build_booking_links(user_message, final_response, intents, history_text)
    # Reuse the hotels resolved up front (live, grounded to the spoken reply). Fall back to a
    # fresh curated lookup only when hotels are wanted this turn AND the destination was named
    # solely in Sasha's reply (so `early_hotels` was empty). Respects the focus/suppression gate.
    if early_hotels:
        hotels = early_hotels
    elif _want_hotels:
        hotels = recommend_hotels(user_message, final_response, intents, history_text)
    else:
        hotels = []

    return {
        "response": final_response,
        "intents": intents,
        "photos": photos,
        "tools_used": tools_used,
        "links": links,
        "hotels": hotels,
        "bookings": bookings,
        "itinerary": itinerary,
        "action": action,
        "booking_ref": booking_ref,
        # Which stored trip a payment would be for. On a book_trip turn no new itinerary is
        # produced, so the client needs this to point checkout at the right record — and the
        # server prices it from that record, never from the browser.
        "itinerary_id": (itinerary or {}).get("id") or (stored_itinerary or {}).get("id"),
        "messages": updated_history
    }
