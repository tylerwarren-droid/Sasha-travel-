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


# Cache the compiled patterns: classify_intents runs on every turn and these lists are static.
_MENTION_CACHE: dict = {}


def _mentions(text: str, phrases) -> bool:
    """True if `text` mentions any phrase as WHOLE WORDS.

    Plain `phrase in text` substring matching quietly wrecked intent routing, in two ways:

      mid-word   "eat" matched "gr-EAT"       -> "Bom is great, book it" = restaurant search
                 "image" matches "imagine", "table" matches "comfortable", "tour" matches
                 "tourist" / "detour" / "tournament", "experience" matches "experienced".
      prefix     "need a cab" matched "need a cab-in" -> "we need a cabin on the cruise" = taxi
                 search. CAB_WORDS was written phrase-first specifically to stop "cab" hitting
                 "cabin", and the comment claims it works — it never did, because the phrase is
                 itself a prefix of the wrong word.

    Both need a boundary on BOTH ends, so this is \\b...\\b rather than a word-start anchor.
    The cost is morphology: \\beat\\b won't catch "eating". That's fine here — these lists
    already spell out the variants they care about ("tour"/"tours", "flight"/"flights",
    "experience"/"experiences") and any gap is one more list entry, whereas a false positive
    silently fires a live web search and shows the guest a card for something they never asked
    about.
    """
    # Keyed on the CONTENT, not id(). These lists are locals rebuilt on every call, so their
    # ids are recycled by CPython the moment one is freed — an id key served RESTAURANT_WORDS
    # the pattern compiled for CAB_WORDS, and "recommend a restaurant" classified as a taxi.
    key = tuple(phrases)
    pat = _MENTION_CACHE.get(key)
    if pat is None:
        # Some entries carry a trailing space as a hand-rolled boundary ("fly "). Strip it —
        # \b does that job properly, and "fly " would otherwise never match "fly?" or "fly.".
        pat = re.compile("|".join(r"\b" + re.escape(p.strip()) + r"\b" for p in phrases if p.strip()))
        _MENTION_CACHE[key] = pat
    return bool(pat.search(text))


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
    # Plurals must be listed explicitly: _mentions is whole-word (\brestaurant\b), so it does NOT
    # match "restaurants" — which silently dropped the most common phrasings ("find restaurants",
    # "recommend seafood restaurants") to general chat with no card.
    RESTAURANT_WORDS = ["restaurant", "restaurants", "dinner", "lunch", "breakfast", "eat", "eating", "food", "table", "tables", "reservation", "book a table", "dining", "cuisine", "cafe", "cafes", "bar", "bars", "rooftop", "where to eat", "hungry"]
    # Unambiguous restaurant NOUNS that fire on their own — no action word required. "seafood
    # restaurants in Hanoi", "a nice bistro" and "show me restaurants" are all clearly requests,
    # but carry no verb from RESTAURANT_ACTION_WORDS, so requiring topic+action dropped them to
    # general/foto with no restaurant card. Kept deliberately narrow (only words a guest almost
    # never types except when they want one) so a stray mention can't fire a spurious search;
    # the weaker topic words (dinner/food/table/bar) still need an action so "we had a great
    # dinner last night" stays ordinary chat.
    # Includes unambiguous food-intent words ("hungry", "starving", "grab a bite") and named venue
    # phrases ("rooftop bar", "cocktail bar") a guest states without any action verb — "I'm
    # hungry", "best rooftop bar in Hanoi", "any good places to eat" all mean "find me somewhere"
    # but carry no RESTAURANT_ACTION_WORDS verb, so topic+action alone dropped them to general.
    RESTAURANT_STRONG_WORDS = ["restaurant", "restaurants", "cafe", "cafes", "bistro", "bistros", "eatery", "eateries", "steakhouse", "steakhouses", "hungry", "starving", "rooftop bar", "cocktail bar", "wine bar", "sky bar", "grab a bite", "bite to eat", "places to eat", "place to eat"]
    # "confirm booking"/"confirm my booking"/"reservation number" REMOVED for the demo: the
    # booking_confirmation agent asks for a Booking.com/Expedia reference — after paying via
    # Stripe, a guest saying "can you confirm my booking?" was hijacked into a third-party
    # reference-collection flow instead of hearing their KNO-… ref. The remaining phrases only
    # fire on genuinely third-party references.
    BOOKING_WORDS = ["hotel reference", "pms", "booking.com ref", "expedia ref", "booking number"]
    # "what do"/"what does" removed: they are whole-word matches inside "what do you think
    # about Hue", which a boundary cannot help with, and they fired a photo search on ordinary
    # conversation. "look like" still catches the real ask ("what does Hoi An look like").
    # Split so "show me" is a WEAK photo cue. "show me restaurants / flights / tours" asks to SEE
    # those CARDS, not stock photography, so "show me" must not pre-empt a card-producing intent
    # (the old single FOTO_WORDS list sent "show me restaurants" to a photo strip with no cards).
    # The strong cues (photo/picture/image/look like) always mean the guest wants a picture.
    FOTO_STRONG_WORDS = ["photo", "picture", "image", "look like"]
    FOTO_SHOW_WORDS = ["show me", "show"]
    # Flights — catches "book me a flight to Hanoi", "fly to Da Nang", "cheapest flights", etc.
    # Every entry must actually imply AIR travel. "how do i get to" / "getting there" used to
    # live here and caught road questions ("how do I get to Ba Na Hills from Hoi An?"), sending
    # them to a flight search for a place with no airport.
    FLIGHT_WORDS = ["flight", "flights", "fly ", "flying", "airfare", "air fare", "airline", "airlines", "plane ticket", "plane tickets", "fly to", "direct flight", "nonstop"]
    # Cabs / airport transfers. The bare nouns (cab/taxi/car) are SAFE now that _mentions uses
    # \bword\b on both ends: "\bcab\b" does NOT match "cabin"/"cabinet", "\bcar\b" does NOT match
    # "care"/"cargo"/"scarf". This was the old phrase-only list's real gap — "book me a cab",
    # "cab please" and "arrange a car" all carry no listed PHRASE, so they fell through to general
    # chat and the guest got hotel cards (or nothing) instead of a ride. The phrases are kept for
    # the multi-word intents ("airport transfer", "private transfer") the bare nouns don't cover.
    CAB_WORDS = ["taxi", "taxis", "cab", "cabs", "car", "cars", "rideshare", "book a cab", "grab a cab", "call a cab", "need a cab", "get a cab", "cab to", "cab from", "airport transfer", "airport pickup", "airport pick up", "airport pick-up", "pick up from the airport", "pickup from airport", "car to the airport", "ride to the airport", "ride from the airport", "private car", "private transfer", "airport car", "chauffeur", "shuttle", "transfer to my hotel", "transfer from the airport"]
    # "what can/should/could we|I do", "what is there to do", "anything to do" — the most
    # natural spoken phrasings of the activity ask; live-tested "what can we do in Hoi An?"
    # fell through to general chat (no card) because only "what to do" was listed.
    ACTIVITY_WORDS = ["things to do", "thing to do", "activities", "activity", "tour", "tours", "excursion", "experience", "experiences", "what to do", "what can we do", "what can i do", "what should we do", "what should i do", "what could we do", "what is there to do", "what's there to do", "anything to do", "anything fun", "something to do", "something fun", "cooking class", "snorkel", "snorkeling", "diving", "scuba", "boat trip", "boat tour", "day trip", "sightseeing", "attractions", "kayak", "kayaking", "trekking", "hiking", "cyclo", "street food tour", "food tour", "lantern making", "market tour", "workshop", "sunrise tour", "sunset cruise"]

    if _mentions(lower, GOLF_WORDS):
        intents.append("golf")
        intents.append("foto")
    if _mentions(lower, FLIGHT_WORDS):
        intents.append("flight")
    if _mentions(lower, CAB_WORDS):
        intents.append("cab")
    # Spa & wellness is an activity FLAVOUR: same intent, same card, same Book & Pay —
    # travel_search routes spa-flavoured interest to its own catalogue. Guarded so a spa
    # named as a hotel AMENITY ("a hotel with a spa") stays a stay ask, not a treatment ask.
    SPA_WORDS = ["spa", "spas", "spa day", "massage", "massages", "sauna", "facial",
                 "wellness", "jacuzzi", "reflexology", "body scrub", "hot spring",
                 "hot springs", "mud bath", "herbal bath", "onsen", "foot massage"]
    _spa_amenity = re.search(r"with (a |an )?(spa|sauna|jacuzzi|massage|wellness)", lower)
    if _mentions(lower, ACTIVITY_WORDS):
        intents.append("activity")
    elif _mentions(lower, SPA_WORDS) and not _spa_amenity:
        intents.append("activity")
    # Restaurant only fires when actively seeking a restaurant — not just mentioning food/dining
    # "where can"/"where should" alongside "where to": the list only had the latter, so the most
    # natural phrasing of all — "where can I eat in Hoi An?" — matched the topic but no action
    # and fell through to ordinary chat, surfacing no card. (Pre-existing; unrelated to the
    # substring fix below.) Safe to widen: an action word alone does nothing without a topic
    # word, so "where can I find a hotel" still isn't a restaurant search.
    RESTAURANT_ACTION_WORDS = ["find", "book", "reserve", "recommend", "suggestion", "where to", "where can", "where should", "looking for", "need a", "want a", "good restaurant", "best restaurant", "good restaurants", "best restaurants", "book a table", "make a reservation", "dinner tonight", "lunch today", "place to eat",
        # View/seek verbs so a WEAK topic word still fires with a natural request:
        # "show me dinner options", "give me a lunch spot", "list the best food". Paired with a
        # topic word only, so "show me Hoi An" / "give me a hand" never become a restaurant search.
        "show me", "show", "give me", "list", "suggest", "options for", "where's", "wheres",
        # "somewhere" is topic-gated (needs a food word too), so "somewhere nice for dinner" fires
        # but "somewhere nice to stay" (a hotel ask) does not.
        "somewhere", "somewhere to eat", "somewhere for"]
    # Match on WORD STARTS, not raw substrings.
    #
    # `"eat" in "bomb is great"` is True — so "Bom is great, book it" satisfied both the topic
    # ("eat" inside "gr-EAT") and the action ("book"), re-fired the restaurant search, and made
    # Sasha re-read the same list instead of helping book the place the guest just named. Same
    # trap caught "creating my plan", "I want meat", "book a seat", "a comfortable table".
    # CAB_WORDS was already made phrase-based for exactly this reason ("cab" vs "cabin");
    # restaurants never were.
    #
    # \b + the word (rather than \bword\b) keeps the useful morphology — "eat" still matches
    # "eating"/"eats", "table" still matches "tables" — while refusing a match mid-word.
    restaurant_action = _mentions(lower, RESTAURANT_ACTION_WORDS)
    restaurant_topic = _mentions(lower, RESTAURANT_WORDS)
    restaurant_strong = _mentions(lower, RESTAURANT_STRONG_WORDS)
    # A strong noun ("restaurants", "bistro") is a request on its own; weaker topic words still
    # need an action verb. This is what lets "seafood restaurants in Hanoi" and "show me
    # restaurants" produce a card, while "we had a great dinner" stays chat.
    if restaurant_strong or (restaurant_topic and restaurant_action):
        intents.append("restaurant")
    # NOTE: restaurant deliberately has NO follow-up carry-forward, unlike every earlier
    # version of this block. It existed to catch "book the second one" after a restaurant
    # card, but it did more harm than good and every fix to it just moved the damage:
    #
    #   - Scanning the whole history made one "recommend a restaurant" bolt dining onto every
    #     later turn for the rest of the session.
    #   - Narrowing to the last 2 turns still re-armed itself, because Sasha's OWN summary
    #     ("a few great places to EAT ... tap any to RESERVE") contains both a topic and an
    #     action word, so her reply re-triggered her own intent forever.
    #   - Narrowing again to USER turns still re-fired on "Bom is great, book it", because the
    #     guest's ORIGINAL "recommend restaurants" ask is itself in the last two user turns —
    #     so naming a place and asking to book it re-ran the search and re-read the same list
    #     instead of helping them book it.
    #
    # flight/cab/activity never had a carry-forward and handle this correctly: they fall
    # through to `general`, which reads the card out of the history and says "tap VietJet on
    # the card to book it". Restaurant now matches them. The card is already on screen and
    # already in the transcript — general can see it, and it can't fabricate a booking (see
    # NEVER_FAKE_BOOKING).
    if _mentions(lower, BOOKING_WORDS):
        intents.append("booking_confirmation")
    if _mentions(lower, FOTO_STRONG_WORDS) and "foto" not in intents:
        intents.append("foto")
    # "show me X" adds a photo strip ONLY when no card-producing intent already fired this turn.
    # "show me Hoi An" -> photos; "show me restaurants / flights / a tour" -> the cards for those.
    _CARD_INTENTS = {"golf", "flight", "cab", "activity", "restaurant", "itinerary"}
    if _mentions(lower, FOTO_SHOW_WORDS) and "foto" not in intents and not (set(intents) & _CARD_INTENTS):
        intents.append("foto")

    # Itinerary build — the user explicitly asks to see the full plan, OR confirms after
    # Sasha has just offered to build it. This supersedes other intents (it's the action).
    ITINERARY_WORDS = [
        "itinerary", "day by day", "day-by-day", "day to day", "full plan", "whole plan",
        "the full trip", "put it together", "put it all together", "plan it all out",
        "build the plan", "build my trip", "create the plan", "finalize", "finalise",
        "show me the plan", "see the plan", "full trip plan",
        # "can you plan everything", "plan it all", "sort out the whole trip" — a guest handing the
        # whole trip over. Unambiguous build requests that carry no day-count for the ITINERARY_RE.
        "plan everything", "plan it all", "plan the whole thing", "sort out the whole trip",
        "sort everything out", "organise everything", "organize everything",
    ]
    # Fixed phrases can't cover how people actually ask. "Build a 5-day trip to Hue with a
    # cooking class" matched none of the above but DID match the activity keywords, so Sasha
    # answered with a list of tours and built nothing. A build verb aimed at a trip is an
    # itinerary request however it's worded.
    ITINERARY_RE = re.compile(
        r"\b(build|plan|create|put together|map out|design|organi[sz]e|sort out)\b"
        r"[^.?!]{0,40}?\b(\d+\s*[-–]?\s*days?\b|itinerary|trip|holiday|vacation|week\b)",
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

    # Booking-completion follow-up ("book Cha Ca La Vong", "reserve that one", "pay for it")
    # right after Sasha surfaced restaurant/flight/transfer cards must STAY in that booking
    # context. Left to fall through to general chat, the turn surfaces HOTEL cards that REPLACE
    # the very cards the guest is trying to book — they then tap the wrong card and pay for the
    # wrong thing (a real bug: "book Cha Ca La Vong" booked a Sofitel hotel because hotels had
    # just clobbered the restaurant panel). Re-firing the same booking intent keeps those cards
    # on the panel and points the guest at Book & Pay; crucially it also keeps _want_hotels off.
    def _booking_kind(text: str) -> "Optional[str]":
        if any(k in text for k in ("restaurant", "to eat", "places to eat", "menu", "table",
                                   "dining", "dinner", "lunch", "reserve your table")):
            return "restaurant"
        if any(k in text for k in ("flight", "airline", "fare", " fly ", "flights")):
            return "flight"
        if any(k in text for k in ("transfer", "airport", "cab", "taxi", "car service",
                                   "pickup", "pick-up", "pick up")):
            return "cab"
        # Activities are payable cards too (tours, classes, spa & wellness) — without this,
        # "book it" after an activity card fell through to hotels/general chat.
        if any(k in text for k in ("tour", "activity", "experience", "excursion",
                                   "things to do", "things you can book", "spa", "massage",
                                   "wellness", "cooking class")):
            return "activity"
        # Checked LAST: "cab to my hotel" is a ride, but "book grand hotel" is a stay. A
        # hotel ask was previously invisible here, so it inherited the LAST card's kind —
        # "can you book grand hotel for me?" was answered with the restaurant confirmation.
        if any(k in text for k in ("hotel", "resort", "room", "accommodation", "a stay",
                                   "place to stay", "night at")) or _names_hotel(text):
            return "hotel"
        return None

    # "book the whole trip / everything / the package" targets the TRIP, never the card Sasha
    # happened to show last turn. Without this escape, a guest who browsed restaurants and then
    # said "book the whole trip" was bounced back to "tap Book & Pay on whichever of these…" and
    # the payment flow never opened — on the finale of the pitch.
    _WHOLE_TRIP_WORDS = ("whole trip", "the trip", "this trip", "my trip", "entire trip",
                         "everything", "all of it", "the plan", "whole plan", "the package",
                         "whole package", "full itinerary", "the itinerary", "whole itinerary")
    # Only meaningful when a REAL plan exists: without one, an itinerary-word in Sasha's
    # free prose ("shall I add it to your plan?") is just chat and must not suppress the
    # card-booking branch ("perfect, reserve it" fell to the LLM instead of the popup).
    _last_was_itinerary = bool(has_itinerary) and any(w in last_assistant for w in
                              ("itinerary", "day-by-day", "your plan", "full plan", "updated your",
                               "-day plan", "day plan", "is live on the right"))
    if any(w in lower for w in BOOK_COMPLETE_WORDS) and not any(w in lower for w in _WHOLE_TRIP_WORDS) \
            and not _last_was_itinerary:
        # The kind named in the MESSAGE stands alone — "book the Sofitel" declares itself a
        # hotel booking even when Sasha's previous reply carried no kind words at all
        # (an LLM stay reply like "Hanoi has some wonderful options…" matched nothing, so
        # the whole branch used to be skipped and the ask fell to plain chat).
        _msg_kind = _booking_kind(lower)
        # Hotel-name TOKEN collisions must not out-rank the card the guest is reading:
        # "book the Ba Na Hills & Golden Bridge" (a tour, named verbatim off the activity
        # card) tripped _names_hotel via the "golden" of "Danang Golden Bay" and opened a
        # HOTEL payment popup. When hotel-ness rests only on name tokens (no stay word) and
        # every such token also appears in Sasha's last reply, the guest is naming something
        # she just listed — let the last card's kind decide instead.
        if _msg_kind == "hotel" and not any(k in lower for k in (
                "hotel", "resort", "room", "accommodation", "a stay", "place to stay", "night at")):
            _hot_toks = set(re.findall(r"[a-z]{5,}", lower)) & _HOTEL_NAME_TOKENS
            if _hot_toks and all(t in last_assistant for t in _hot_toks):
                _msg_kind = None
        _last_kind = None
        if not _msg_kind:
            _last_kind = _booking_kind(last_assistant)   # what Sasha just offered
            # Sasha's card offer may be more than one turn back ("thanks" in between must not
            # reroute "book Tam Vi" to hotels) — scan the last few assistant lines, newest first.
            if not _last_kind:
                _assistant_lines = [m.get("content", "").lower() for m in (conversation_history or [])
                                    if isinstance(m, dict) and m.get("role") == "assistant"]
                for _line in reversed(_assistant_lines[-4:]):
                    _last_kind = _booking_kind(_line)
                    if _last_kind:
                        break
        if _msg_kind or _last_kind:
            _bk = _msg_kind or _last_kind
            if _bk == "hotel":
                # No dedicated hotel runner — the general path surfaces hotel cards (FORCED,
                # since "book the Sofitel" carries no stay word), and the guarded LLM points
                # at their Book & Pay buttons; a matched name auto-opens the payment popup.
                return {"intents": ["general"], "primary": "general", "context": user_message,
                        "force_hotels": True}
            return {"intents": [_bk], "primary": _bk, "context": user_message}
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
    if _mentions(lower, ITINERARY_WORDS) or ITINERARY_RE.search(lower) or (user_affirms and offered_itinerary):
        intents = ["itinerary"]

    # Intake follow-up: Sasha just asked for the trip brief (where / how long / who). The
    # guest's answer ("Hanoi and Hoi An, 6 days, the two of us") carries no build verb, so
    # without this it fell to general chat and the brief was never acted on.
    if not intents and "where in vietnam would you like to go" in last_assistant:
        _gave_brief = (
            bool(_find_destinations(lower))
            or re.search(r"\b\d+\s*[-–]?\s*(?:day|days|night|nights|week|weeks)\b", lower)
            or re.search(r"\b(a|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
                         r"(?:day|days|night|nights|week|weeks)\b", lower)
            or re.search(r"\b(solo|alone|honeymoon|couple|family|friends)\b"
                         r"|\b(two|three|four|five|\d+)\s*(?:of us|people|adults|travell?ers)\b"
                         r"|\bmy (wife|husband|partner|girlfriend|boyfriend|kids|family)\b", lower)
            or re.search(r"you (decide|choose|pick)|surprise me|up to you", lower)
        )
        if _gave_brief:
            intents = ["itinerary"]

    # Revise an EXISTING itinerary — once a structured plan is on the board, a swap/change
    # request must REBUILD it. Otherwise a conversational agent just claims the change
    # ("I've swapped you to Capella Hanoi") while the card keeps the old hotel, so Sasha
    # and the card contradict each other. Gate on a plan already existing in the history so
    # these broad verbs don't hijack ordinary chat.
    # A modify verb + a plan target catches natural phrasings like "change my HANOI hotel to
    # Capella" or "swap the day-3 resort", which a fixed-phrase list misses.
    REVISE_VERBS = ["swap", "replace", "switch", "change", "upgrade", "downgrade", "different", "move", "update"]
    REVISE_TARGETS = ["hotel", "hotels", "stay", "resort", "cruise", "night", "nights",
                      "package", "plan", "itinerary", "trip"]
    revise_combo = any(v in lower for v in REVISE_VERBS) and any(t in lower for t in REVISE_TARGETS)
    REVISE_STANDALONE = [
        "cheaper", "more luxurious", "more luxury", "more budget", "tighter budget",
        "add a day", "remove a day", "drop a day", "extra day", "fewer days", "more days",
        "shorten", "extend the trip", "revise", "rebuild the", "redo the",
    ]
    revise_standalone = _mentions(lower, REVISE_STANDALONE)
    # Changing WHO is travelling re-prices the whole trip (experiences and meals scale per
    # head), so it has to REBUILD, not just get talked about. Without this, "only I will be
    # travelling, give me the price for that" fell through to ordinary chat and Sasha simply
    # halved the number out loud — a figure that matched no itinerary, while the plan on the
    # right still said two.
    party_change = re.search(
        r"\b(only|just)\s+(i|me)\b|\bby myself\b|\bon my own\b|\b(solo|alone)\b"
        r"|\bjust\s+(one|1)\b|\b(price|total|cost)\s+for\s+(one|1|just me|myself)\b"
        r"|\b(\d+|one|two|three|four|five|six)\s+(of us|travell?ers?|people|adults)\b"
        # "so it'll be a total of four", "group of 4", "party of five" — a stated head-count
        # with the number AFTER the noun, which the pattern above (number-first) misses.
        r"|\b(total|group|party)\s+of\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b"
        # "make it a package for 4", "booking for three" — party size stated as who it's FOR. The
        # lookahead excludes a duration ("package for 4 days") so a length never forces a rebuild.
        r"|\b(package|booking|reservation|trip|holiday|vacation|table|group|party|plan)\s+for\s+"
        r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b(?!\s*(?:day|night|week|month|hour|year))"
        # A companion joining re-prices per head: "my friend and his wife want to go with us".
        r"|\b(go|going|come|coming|join|joining)\s+with\s+us\b"
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
    # Whole-word matching matters MOST here: this is the branch that takes money. As raw
    # substrings, "i'll take it" matched "i'll take itinerary advice" and "book it" matched
    # "book its location" — either would have opened Stripe checkout for a trip the guest
    # never agreed to buy.
    if itinerary_exists and (_mentions(lower, BOOK_WORDS) or (user_affirms and offered_booking)):
        intents = ["book_trip"]

    # Cab route follow-up. After Sasha asks "where are you being picked up, and where are you
    # heading?", the guest's reply ("from my hotel to the airport", "Sofitel to Noi Bai airport")
    # carries no cab keyword and would fall to general. Route it back to the cab agent — but ONLY
    # when the reply actually looks like a route (a from/to/place), so a topic change after the
    # question ("actually, tell me about Hoi An") isn't dragged into a taxi search.
    _asked_cab = re.search(r"pick(ed|ing)?[ -]?up|where are you heading|heading to", last_assistant)
    _looks_route = re.search(r"\b(from|to|airport|hotel|pick|drop|heading|going)\b", lower) or bool(_find_destinations(lower))
    _topic_change = re.search(r"\b(tell me|what|whats|show me|how|why|when|recommend|about|instead|actually)\b", lower)
    if not intents and _asked_cab and _looks_route and not _topic_change:
        intents = ["cab"]

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

# Appended to the general prompt IN CODE, not stored in the prompt registry, because
# `get_prompt()` prefers the Supabase-cached text over the static one — so editing the static
# conductor.general prompt is silently a no-op wherever a Supabase row exists. This guard must
# hold regardless of what any row says, so it is concatenated on every call (same reasoning as
# the per-agent VOICE_BREVITY suffix).
#
# Why it exists: on a follow-up like "book the second one" after an activity card, the general
# agent fabricated a booking roughly 1 turn in 3 — "Perfect! I've sent the My Son Sanctuary
# tour to your booking — you'll see the confirmation details appear on the right in just a
# moment." Nothing is sent and no confirmation ever appears. This is the same fake-confirmation
# failure the restaurant email agent was removed for; it came back in through general chat.
NEVER_FAKE_BOOKING = (
    "\n\nHARD RULE — NEVER claim a booking, reservation, order or enquiry has been made, sent, "
    "submitted, requested or confirmed. You have NO ability to book, reserve or contact any "
    "provider. Never say you have 'sent', 'added', 'put through' or 'confirmed' anything, and "
    "never say a confirmation is coming. The ONLY way anything gets booked is the guest tapping "
    "a link on a card themselves. When they ask you to book an individual flight, taxi, tour or "
    "restaurant, say plainly that they can tap that option on the card to complete it. (The one "
    "exception is the whole-trip Stripe checkout, which is handled elsewhere, not by you.)"
)


# Sibling to NEVER_FAKE_BOOKING, and appended for the same reason: run_general only ever runs
# when NO itinerary was (re)built this turn, so it is ALWAYS wrong for the general agent to talk
# as if it changed the plan. The reported failure: after "make it a total of four", the general
# agent said "Brilliant — I've updated it for four travellers, ~$9,240" while the trip card still
# showed two and $4,620. She can and should DISCUSS any change; she must not CLAIM she performed
# one. When a change really is wanted, the router (keyword + semantic backstop below) sends it to
# a real rebuild instead of here — so this guard only catches the rare miss, and turns a lie into
# a truthful "let me update that", which naturally re-triggers the change on the guest's next word.
NEVER_FAKE_ITINERARY_CHANGE = (
    "\n\nHARD RULE — you cannot edit the trip plan from within this reply. NEVER say you have "
    "updated, changed, rebuilt, re-priced, added to, removed from, upgraded, downgraded or "
    "adjusted the itinerary, the traveller/party count, the dates or length, the destinations, "
    "the hotels or the total, and never state a new total or a changed plan as though it were "
    "done. If the guest is asking for such a change, briefly restate the change you understood "
    "and say you'll update the plan now so it refreshes on the right — never claim it is already "
    "done. Discussing, comparing and advising on options is always fine; only completed edits to "
    "the plan are forbidden."
)

# num→word for the spoken trip total, so "for four travellers" reads naturally in TTS.
_TRAVELLER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
                    7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}

# A cheap pre-filter so the semantic backstop's LLM call fires ONLY on turns that plausibly ask
# for a change — pure questions ("what's the food like in Hue?") never pay the latency.
_CHANGE_CUE = re.compile(
    r"\d|\b(add|remove|drop|change|update|swap|replace|switch|make it|bump|upgrade|downgrade|"
    r"more|less|fewer|cheaper|pricier|luxur|fancier|nicer|budget|instead|rather|extend|shorten|"
    r"longer|shorter|extra|another|also|join|joining|bring|bringing|plus|bigger|smaller|"
    r"different|redo|rebuild|revise|remove|now that|no longer)\b",
    re.I,
)


async def wants_trip_change(message: str, history: list) -> bool:
    """Fast yes/no: given an EXISTING plan, is the guest asking to MODIFY it?

    Keyword routing (party_change / revise) can't enumerate every phrasing a guest uses to
    change a trip — "bump us to a bigger group", "let's make Hoi An the base instead", "a bit
    more upmarket on the hotels". A missed change is this app's worst failure: Sasha talks as
    if she changed the plan while the card sits stale. So when keyword routing falls through to
    plain chat AND a real plan exists, one fast-model yes/no decides whether to force a rebuild.
    Gated behind _CHANGE_CUE so ordinary questions never trigger the extra call.
    """
    if not _CHANGE_CUE.search(message or ""):
        return False
    try:
        resp = await asyncio.wait_for(
            client.messages.create(
                model=FAST_MODEL,
                max_tokens=1,
                system=cached_system(
                    "A travel guest already has a day-by-day trip plan on screen. Decide if their "
                    "next message asks to CHANGE that plan in any way — traveller/party size, dates "
                    "or trip length, which destinations are included, the hotels or hotel tier, the "
                    "budget, the pace, or the activities. Reply with EXACTLY one character and "
                    "nothing else: Y if they want the plan changed, N if it is a question, comment, "
                    "booking request, or anything that is not a change to the plan."
                ),
                messages=[{"role": "user", "content": message}],
            ),
            timeout=6.0,
        )
        out = "".join(b.text for b in resp.content if hasattr(b, "text")).strip().upper()
        return out.startswith("Y")
    except Exception as e:
        print(f"[Conductor] trip-change backstop failed ({e}) — leaving as chat")
        return False


# Turns where the guest is talking about WHO is travelling. On these, the chat model must not
# do its own arithmetic — it demonstrably gets it wrong mid-conversation ("I have two
# daughters" after "three of you total" became "five of you altogether": it ADDED the two
# instead of replacing the one). The additive party resolver is the single source of truth.
_PARTY_TALK = ("wife", "husband", "partner", "spouse", "daughter", "son", " kid", "child",
               "family", "friend", "people", "of us", "together", "alone", "solo", "myself",
               "travel with", "travelling with", "traveling with", "join", "group", "party of",
               "how many", "the two of", "the three of", "the four of", "the five of")


async def run_general(message: str, history: list, general_prompt: str) -> dict:
    """General Sasha conversation — travel advice, destinations, planning."""
    system = general_prompt + NEVER_FAKE_BOOKING + NEVER_FAKE_ITINERARY_CHANGE
    # CURRENT message only: the miscount risk is the turn where the GUEST restates the party.
    # Triggering off history too made every turn near party talk pay the ~1s resolver call
    # ("wife" in Sasha's own previous reply added a visible delay to an unrelated answer).
    if any(w in message.lower() for w in _PARTY_TALK):
        try:
            from app.services.itinerary_agent import _resolve_travellers
            _n = await _resolve_travellers(history, message)
            system += (
                f"\n\nPARTY COUNT — AUTHORITATIVE: the travelling party is exactly {_n} "
                f"{'person' if _n == 1 else 'people'} in total, including the guest, recomputed "
                "from the entire conversation just now. When you state or imply how many people "
                "are travelling, use EXACTLY this number. NEVER add up the party yourself — "
                "recounting mid-conversation is how you previously told a family of four they "
                "were five. If the guest's latest message seems to change the party, this number "
                "already reflects it."
            )
        except Exception:
            pass  # never let a resolver hiccup break an ordinary chat turn
    response = await client.messages.create(
        model=CONDUCTOR_MODEL,
        max_tokens=200,  # short spoken replies — voice interface
        system=cached_system(system),
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
    # The PLACE these photos are of. Kept separate from `query` (which carries search filler
    # like "Vietnam travel") because the UI labels each shot with this.
    location = ""

    if visual_ctx["golf_courses"]:
        location = visual_ctx["golf_courses"][0]
        query = f"{location} golf Vietnam"
        photo_type = "golf"
    elif visual_ctx["destinations"]:
        location = visual_ctx["destinations"][0]
        query = f"{location} Vietnam travel"
        photo_type = "destination"
    else:
        # Nothing named in this turn — fall back to whatever place is already in play so the
        # label is still a real location rather than the raw user sentence.
        location = _dest_in_play(message, history)
        query = f"{location} Vietnam travel"

    photos = await search_photos(query, count=3)
    # Stamp the location onto every photo. The UI used to label the panel with the photo's
    # Unsplash `description`, which is the photographer's free-text caption — that is how the
    # header ended up reading "Exploring 4:51pm" instead of "Exploring Ha Long Bay".
    #
    # _find_destinations matches case-insensitively and hands back the lowercased key
    # ("ha long bay"), which is fine for lookups but not for a caption the guest reads.
    label = " ".join(w if w.isupper() else w.capitalize() for w in location.split())
    photos = [{**p, "location": label} for p in photos]
    location = label
    return {
        "agent": "foto",
        "response": "",  # Foto doesn't speak — it just provides visuals
        "data": {"photos": photos, "query": query, "type": photo_type, "location": location}
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


async def run_restaurant_intent(message: str, history: list, session_id: "Optional[str]" = None) -> dict:
    """Real restaurants via live web search — surfaced as a booking card with reserve links.

    (Replaces the old email/phone reservation agent, which faked a 'sent' confirmation when
    Resend/Bland keys were absent and CC'd a hardcoded personal inbox. For the demo we show
    real places and hand off to the provider to reserve — honest and can't-fail.)
    """
    dest = _dest_in_play(message, history)
    _h = _req_hint("restaurant", message)
    card = await _stable_card(session_id, "restaurant", dest, lambda: find_restaurants(dest, request_hint=message),
                              hint=_h, always_cache=(_is_book_complete(message) and not _h))
    card["options"] = _tier_sort(card.get("options", []), message)
    opts = card.get("options", [])
    # Skip deep-link fallback options when naming places aloud. Restaurants carry no price, so
    # unlike the flight/cab/activity handlers there is no has_prices check to fall back on, and
    # a failed search made Sasha say the placeholder as if it were a restaurant:
    # "A few great places to eat in Hanoi — Restaurants · Hanoi."
    names_list = [o["name"] for o in opts if o.get("name") and not o.get("fallback")]
    names = ", ".join(names_list[:3]) + (" and more on the card" if len(names_list) > 3 else "")

    # Browsing vs booking are different asks. "book/reserve a table at X" must NOT get the same
    # "here are a few places" list read back — that reads as a repeated non-answer (the guest
    # already sees the list). Reservation + payment happen by tapping "Book & Pay" on the card
    # (the browser drives Stripe), so point them at that button, naming the place when the guest
    # named one clearly enough to match.
    lower = message.lower()
    wants_book = any(w in lower for w in
                     ("book", "reserve", "reservation", "table", "make a booking", "get us in"))
    matched = _match_named_ctx(message, names_list, history)

    if wants_book and names_list:
        if matched:
            spoken = (f"Great choice — {matched} is pulled up on the right. Tap Book & Pay on its "
                      "card to reserve your table.")
            card["matched_option"] = matched
        elif _foreign_referent(message, names_list):
            spoken = (f"Hmm, I don't see that one on my current list — what I have in {dest} is "
                      f"{', '.join(names_list[:3])} and more on the card. Tap Book & Pay on any of them, or ask me to look for something else.")
        else:
            spoken = (f"Of course — tap Book & Pay on whichever of these you'd like ({names}) and "
                      "I'll get your table reserved.")
    elif names:
        if _h:
            # A qualified ask ("seafood", "fine dining") gets the same stable list by design —
            # acknowledge the request so the repeat doesn't read as Sasha ignoring the guest.
            spoken = f"For that, my favourite spots in {dest} are {names} — I've pulled them up. Tap any one to see the menu and reserve."
        else:
            spoken = f"A few great places to eat in {dest} — {names}. I've pulled them up for you — tap any one to see the menu and reserve."
    else:
        spoken = f"Here's where to find and reserve a table in {dest} — I've pulled it up for you."
    return {"agent": "restaurant", "response": spoken, "data": {"booking": card}}


def _match_named(message: str, names: list, fuzzy: bool = True) -> "Optional[str]":
    """Best-effort: which listed option (if any) the guest named — tolerant of STT garbling.

    Matches a significant word of an option name appearing in the message (either direction),
    so "book La Badiane" resolves to "La Badiane". Deliberately conservative: an unmatched name
    just yields a generic "tap Book & Pay" reply rather than guessing the wrong restaurant.
    """
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())
    msg_norm = norm(message)
    all_tokens = re.findall(r"[a-z0-9]+", (message or "").lower())
    tokset = set(all_tokens)
    tok4 = [t for t in all_tokens if len(t) >= 4]
    _skip = _NAME_MATCH_SKIP
    for name in names:
        mn = norm(name)
        # Whole-name run in the normalized stream: catches "TamVi"-style STT junctions for
        # short-word names that have no 4+ letter token.
        if mn and len(mn) >= 5 and mn in msg_norm:
            return name
        # STT garbles name tails ("Tamv" → Tam Vi): mutual >=4-char prefix on TOKENS. Never
        # raw substring across word boundaries — "some(thing)"/"every(thing)" used to match
        # "Pho THIN" and opened the payment popup for the wrong restaurant.
        if fuzzy and mn and len(mn) >= 4 and any(mn.startswith(t) or t.startswith(mn) for t in tok4):
            return name
        for w in re.findall(r"[A-Za-z]{4,}", name):
            wl = w.lower()
            if wl in _skip:
                continue
            if wl in tokset:
                return name
            if fuzzy and any((t.startswith(wl) or wl.startswith(t)) and min(len(t), len(wl)) >= 4
                             for t in tok4):
                return name
    return None


# Name-words that are never a referent on their own: kind nouns that appear INSIDE property
# names, plus every destination word. "book the Danang Golden Bay hotel" (a property NOT on
# the current list) used to fuzzy-match "InterContinental DANANG Sun Peninsula" on the shared
# city word and open a $420 payment popup for the wrong hotel.
_NAME_MATCH_SKIP = {"restaurant", "the", "and", "cafe", "bar", "vietnam", "hanoi", "saigon",
                    "hotel", "hotels", "resort", "hostel", "villa", "lodge", "homestay",
                    "airport", "airlines", "airways"}
try:
    from app.services.booking_links import DESTINATIONS as _NM_DESTS
    for _k, _v in _NM_DESTS.items():
        _NAME_MATCH_SKIP.update(_k.lower().split())
        _NAME_MATCH_SKIP.update(w.lower() for w in _v.split())
except Exception:
    pass

_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "last": -1}

# Words that carry no referent in a booking ask — booking verbs, function words, kind nouns,
# time words, and every Vietnam destination. Whatever remains after stripping these is the
# guest naming a SPECIFIC thing.
_BOOKING_STOP = {
    "book", "books", "booking", "reserve", "reservation", "pay",
    "can", "could", "would", "will", "you", "please", "for", "me", "us", "the", "a", "an",
    "it", "that", "this", "one", "get", "make", "made", "my", "our", "your", "in", "at",
    "to", "and", "of", "on", "now", "again", "also", "yes", "yeah", "okay", "ok", "sure",
    "go", "ahead", "with", "there", "then", "table", "restaurant", "flight", "flights",
    "hotel", "hotels", "room", "cab", "taxi", "ride", "car", "transfer", "seat", "seats",
    "spot", "place", "tonight", "today", "tomorrow", "dinner", "lunch", "breakfast",
    "perfect", "great", "awesome", "lovely", "nice", "cool", "alright", "right", "well",
    "then", "lets", "let's", "her", "him", "them", "really", "definitely", "just",
    "night", "nights", "first", "second", "third", "last", "whole", "trip", "everything",
    "people", "person", "two", "three", "four", "five", "actually", "want", "like", "need",
    # Treatment/experience kind-nouns — "book me a spa massage" names WHAT the guest wants,
    # not WHICH venue; these must not read as a foreign referent over the spa card.
    "spa", "spas", "massage", "massages", "sauna", "facial", "wellness", "treatment",
    "tour", "tours", "activity", "experience",
}
try:
    from app.services.booking_links import DESTINATIONS as _DESTS
    for _k, _v in _DESTS.items():
        _BOOKING_STOP.update(_k.split())
        _BOOKING_STOP.update(w.lower() for w in _v.split())
except Exception:
    pass


def _foreign_referent(message: str, names: list) -> bool:
    """True when the guest explicitly named something that matches NONE of the options —
    "book grand hotel" over a restaurant card. History fallback must not run then: the
    July failure shape was answering that with "Tam Vi is pulled up"."""
    def _n(s):
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())
    name_norms = [_n(n) for n in names if n]
    name_words = {w.lower() for n in names for w in re.findall(r"[A-Za-z]{3,}", n or "")}
    for tok in re.findall(r"[a-z']+", (message or "").lower()):
        if len(tok) < 3 or tok in _BOOKING_STOP:
            continue
        tn = _n(tok)
        if tok in name_words or any(len(tn) >= 4 and len(nn) >= 4 and
                                    (nn.startswith(tn) or tn.startswith(nn)) for nn in name_norms):
            continue
        if any(len(tn) >= 4 and len(w) >= 4 and (w.startswith(tn) or tn.startswith(w))
               for w in name_words):
            continue
        return True
    return False


def _match_named_ctx(message: str, names: list, history: list) -> "Optional[str]":
    """Which listed option the guest means — named in this message, by ordinal ("the second
    one"), or referenced from recent turns ("Can you book it?" right after Sasha described
    Tam Vi). The screenshot failure this fixes: an anaphoric booking ask got the generic
    "tap Book & Pay on whichever of these" instead of the place the guest was clearly
    talking about."""
    if not names:
        return None
    m = _match_named(message, names)
    if m:
        return m
    low = (message or "").lower()
    for w, i in _ORDINALS.items():
        if re.search(rf"\bthe {w}( one)?\b", low) or re.search(rf"\b{w} one\b", low):
            try:
                return names[i]
            except IndexError:
                return None
    # The guest named something specific that matches NO option — do not guess from
    # history; the runner answers honestly instead.
    if _foreign_referent(message, names):
        return None
    # Anaphora / bare booking ask: the referent is whatever single option was discussed most
    # recently. USER messages are checked first (they name what they mean; keep garble
    # tolerance), then Sasha's replies with STRICT matching (her free prose misspells names
    # and once fuzzy-matched a different venue). Messages mentioning 2+ options (her own
    # list line) are ambiguous and skipped, so "book it" straight after the list stays a
    # generic prompt — correct.
    recent = [m for m in (history or [])[-6:] if isinstance(m, dict)]
    for role, use_fuzzy in (("user", True), ("assistant", False)):
        for msg in reversed(recent):
            if msg.get("role") != role:
                continue
            content = msg.get("content") or ""
            hits = [n for n in names if _match_named(content, [n], fuzzy=use_fuzzy)]
            if len(hits) == 1:
                return hits[0]
    return None


from app.services.hotels_db import VIETNAM_HOTELS as _VH_POOL
_HOTEL_GENERIC = {"hotel", "hotels", "resort", "beach", "island", "garden", "village", "house",
                  "grand", "legend", "luxury", "boutique", "premium", "paradise", "riverside",
                  "suites", "centre", "center", "residence", "residences", "premier", "hanoi",
                  "saigon", "trang", "vietnam", "quang", "binh", "giang", "dalat", "danang"}
_HOTEL_NAME_TOKENS = {w.lower() for _hs in _VH_POOL.values() for _h in _hs
                      for w in __import__("re").findall(r"[A-Za-z]{5,}", _h.get("name", ""))
                      } - _HOTEL_GENERIC


def _names_hotel(text: str) -> bool:
    """True when the text mentions a specific property from the hotel pool ("the Sofitel")."""
    toks = set(re.findall(r"[a-z]{5,}", (text or "").lower()))
    return bool(toks & _HOTEL_NAME_TOKENS)


_LUX_WORDS = ("luxur", "upscale", "high end", "high-end", "fine dining", "five star",
              "5 star", "5-star", "premium", "fanciest", "finest", "splurge")
_BUDGET_WORDS = ("cheap", "budget", "affordable", "inexpensive", "low cost", "low-cost",
                 "street food", "economical", "value")


def _price_of(o: dict) -> float:
    """Numeric price for tier sorting, whatever this option kind carries."""
    v = o.get("amount_usd") or o.get("per_person_usd")
    if v:
        return float(v)
    m = re.search(r"\d+", str(o.get("price") or ""))
    return float(m.group()) if m else 0.0


def _tier_sort(options: list, message: str) -> list:
    """Reorder card options to honour a tier-worded ask ('luxury', 'cheapest', 'street
    food', 'michelin') — the data carries prices and tiers, so use them. Reorders only,
    never drops: the card still shows everything, and the spoken top-3 matches the ask."""
    low = (message or "").lower()
    opts = list(options)
    if "michelin" in low:
        opts.sort(key=lambda o: 0 if "michelin" in str(o.get("detail", "")).lower() else 1)
    elif any(w in low for w in _LUX_WORDS):
        opts.sort(key=lambda o: -_price_of(o))
    elif any(w in low for w in _BUDGET_WORDS):
        opts.sort(key=lambda o: _price_of(o) or 10 ** 9)
    return opts


def _dest_in_play(message: str, history: list) -> str:
    """Best-guess Vietnam destination from this message, else recent history, else 'Vietnam'."""
    htext = " ".join(m.get("content", "") for m in (history or []) if isinstance(m, dict))
    found = _find_destinations(message) or _find_destinations(htext)
    return found[0] if found else "Vietnam"


def _route_dest(message: str, history: list) -> str:
    """Destination for a ROUTE phrase — the city after the last " to ".

    _find_destinations returns matches in DESTINATIONS-dict order, so "flight from Hanoi to
    Phu Quoc" used to resolve to HANOI (the origin) and Sasha searched flights to the city
    the guest was leaving. Flights and cabs use this; everything else keeps _dest_in_play.
    """
    m = (message or "").lower()
    idx = m.rfind(" to ")
    if idx != -1:
        found = _find_destinations(m[idx + 4:])
        if found:
            return found[0]
    return _dest_in_play(message, history)


def _named_options(options: list, limit: int = 3) -> str:
    """A brief spoken phrase naming a few options with prices, for the avatar to read."""
    parts = []
    for o in options[:limit]:
        price = o.get("price")
        parts.append(f"{o.get('name', 'an option')}{f' from {price}' if price else ''}")
    return ", ".join(parts)


# A booking-completion utterance ("book X", "reserve that", "pay for it"). Shared by
# classify_intents (to keep booking context) and the runners (to always reuse the cached list
# the guest is looking at, rather than refetching a different one out from under them).
BOOK_COMPLETE_WORDS = ("book", "reserve", "reservation", "pay for", "table for",
                       "get me a table", "get us a table", "get us in", "reserve a table")


def _is_book_complete(message: str) -> bool:
    low = (message or "").lower()
    return any(w in low for w in BOOK_COMPLETE_WORDS)


# Qualifier words that make a search a genuine REFINEMENT ("seafood restaurants", "cheaper
# hotels", "SUV transfer") rather than a repeat. Only these curated tokens bust the per-session
# cache — an ordinary rephrasing ("good restaurants" vs "restaurants") keeps the same empty hint
# and stays stable, so a follow-up still matches the list on screen.
_QUALIFIERS = {
    "restaurant": (
        "seafood", "vegetarian", "vegan", "halal", "vietnamese", "french", "italian", "japanese",
        "korean", "chinese", "thai", "indian", "street food", "fine dining", "michelin", "rooftop",
        "romantic", "cheap", "budget", "luxury", "upscale", "bbq", "hotpot", "vegan", "buffet",
        "brunch", "breakfast",
    ),
    "hotel": (
        "cheap", "budget", "affordable", "luxury", "five star", "5 star", "5-star", "boutique",
        "resort", "beachfront", "spa", "family", "cheaper", "pricier", "upscale", "hostel",
    ),
    "flight": ("business", "first class", "cheapest", "nonstop", "non-stop", "direct", "economy",
               "premium"),
    "cab": ("suv", "van", "7-seat", "seven seat", "luxury", "sedan", "private", "shared",
            "meet and greet", "limo"),
}


def _req_hint(kind: str, message: str) -> str:
    """Stable signature of the refinement qualifiers in a request (empty = a generic ask)."""
    low = (message or "").lower()
    return "|".join(sorted({q for q in _QUALIFIERS.get(kind, ()) if q in low}))


async def _stable_card(session_id, kind: str, dest: str, fetch,
                       hint: str = "", always_cache: bool = False) -> dict:
    """A booking card for (session, kind, dest) that stays the SAME across a session.

    Live web search returns different places each call, so re-listing "restaurants in Hanoi"
    every turn silently swaps the options out — and a follow-up like "book Cha Ca La Vong" then
    can't match the list the guest is looking at. Caching the first real result per session
    keeps the options (and their Book & Pay offers) stable, and skips the repeat search latency.

    `hint` is the request's refinement signature: a cached card is reused only when the new
    request has the SAME hint (or `always_cache`, set for booking-completion turns). A different
    hint means a genuine refinement ("seafood restaurants"), so we refetch and REPLACE the cache.
    Fallback-only results are never cached, so a failed search retries next turn.
    """
    if session_id:
        cached = await chat_store.get_session_card(session_id, kind, dest)
        if cached and cached.get("options") and (always_cache or cached.get("_hint", "") == hint):
            return cached
    card = await fetch()
    opts = card.get("options", []) if isinstance(card, dict) else []
    if session_id and opts and not all(o.get("fallback") for o in opts):
        card["_hint"] = hint
        await chat_store.save_session_card(session_id, kind, dest, card)
    return card


async def run_flight_intent(message: str, history: list, session_id: "Optional[str]" = None) -> dict:
    """Real flight options via live web search — surfaced as a booking card."""
    dest = _route_dest(message, history)
    _h = _req_hint("flight", message)
    card = await _stable_card(session_id, "flight", dest, lambda: find_flights(dest, when=message),
                              hint=_h, always_cache=(_is_book_complete(message) and not _h))
    if "cheapest" in (message or "").lower():
        card["options"] = sorted(card.get("options", []), key=_price_of)
    else:
        card["options"] = _tier_sort(card.get("options", []), message)
    opts = card.get("options", [])
    has_prices = any(o.get("price") for o in opts)
    names_list = [o["name"] for o in opts if o.get("name") and not o.get("fallback")]
    matched = _match_named_ctx(message, names_list, history) if (_is_book_complete(message) and names_list) else None
    if _is_book_complete(message) and names_list:
        if matched:
            spoken = (f"Great — the {matched} flight is pulled up on the right. Tap Book & Pay "
                      "on its card and I'll get your seats held.")
            card["matched_option"] = matched
        elif _foreign_referent(message, names_list):
            spoken = (f"I don't see that airline on the current list — what I have is "
                      f"{', '.join(names_list[:3])} and more on the card. Tap Book & Pay on any of them, or ask me to search again.")
        else:
            spoken = (f"Of course — tap Book & Pay on whichever flight suits you best "
                      f"({', '.join(names_list[:3])}) and I'll take care of it.")
    elif has_prices:
        spoken = f"I found a few flights to {dest} — {_named_options(opts)}. I've pulled them up — just tap one to book."
    else:
        spoken = f"Here's where to compare and book your flights to {dest} — I've pulled it up for you."
    return {"agent": "flight", "response": spoken, "data": {"booking": card}}


# A ride needs a pickup AND a drop-off to price and book. Checks this turn plus the most recent
# user turn, so a two-step answer ("a cab" → "from my hotel to the airport") is read as one route.
def _has_cab_route(message: str, history: list) -> bool:
    parts = [message or ""]
    for m in reversed(history or []):
        if isinstance(m, dict) and m.get("role") == "user":
            parts.append(m.get("content") or "")
            break
    t = " ".join(parts).lower()
    pickup = re.search(r"\bfrom\b|\bpick(ed|ing)?[ -]?up\b|\bleaving\b|\bat the airport\b|\bat my hotel\b", t)
    dropoff = re.search(r"\bto\b|\bdrop[ -]?off\b|\bheading\b|\bgoing to\b", t)
    return bool(pickup and dropoff)


async def run_cab_intent(message: str, history: list, session_id: "Optional[str]" = None) -> dict:
    """Real airport-transfer / taxi options via live web search — surfaced as a booking card.

    A ride can't be priced without knowing where FROM and where TO, so if the guest hasn't given
    both yet, ask for them instead of showing a generic default route (which read as if she'd
    ignored the question). The classifier carries the guest's reply back here (see the cab
    route-follow-up branch) even though "from my hotel to the airport" has no cab keyword.
    """
    if not _has_cab_route(message, history):
        spoken = ("Happy to sort a ride for you! Where are you being picked up, and where are you "
                  "heading to? Once I know the route I'll pull up the best cars and taxis with fares.")
        return {"agent": "cab", "response": spoken, "data": {}}
    dest = _route_dest(message, history)
    _h = _req_hint("cab", message)
    card = await _stable_card(session_id, "cab", dest, lambda: find_cabs(dest, detail_hint=message),
                              hint=_h, always_cache=(_is_book_complete(message) and not _h))
    card["options"] = _tier_sort(card.get("options", []), message)
    opts = card.get("options", [])
    has_prices = any(o.get("price") for o in opts)
    names_list = [o["name"] for o in opts if o.get("name") and not o.get("fallback")]
    matched = _match_named_ctx(message, names_list, history) if (_is_book_complete(message) and names_list) else None
    if _is_book_complete(message) and names_list:
        if matched:
            spoken = (f"Done — {matched} is pulled up on the right. Tap Book & Pay on its card "
                      "and your ride is set.")
            card["matched_option"] = matched
        elif _foreign_referent(message, names_list):
            spoken = (f"I don't see that provider on the current list — what I have is "
                      f"{', '.join(names_list[:3])}. Tap Book & Pay on any of them, or ask me to look again.")
        else:
            spoken = (f"Of course — tap Book & Pay on whichever ride you'd like "
                      f"({', '.join(names_list[:3])}) and I'll sort it out.")
    elif has_prices:
        spoken = f"For getting around {dest}, here are a few transfer options — {_named_options(opts)}. Tap any one to book."
    else:
        spoken = f"Here's where to book a private car or taxi for {dest} — I've pulled it up for you."
    return {"agent": "cab", "response": spoken, "data": {"booking": card}}


async def run_activity_intent(message: str, history: list) -> dict:
    """Real bookable activities via live web search — surfaced as a booking card."""
    from app.services.travel_search import _SPA_RE
    dest = _dest_in_play(message, history)
    # Carry the spa flavour across a booking follow-up: "book it" right after the spa card
    # says nothing spa-ish, and resolving it against the generic activity catalogue would
    # re-surface tours over the very options the guest is booking.
    _recent = " ".join((m.get("content") or "") for m in (history or [])[-4:] if isinstance(m, dict))
    _spa = bool(_SPA_RE.search(message)) or (_is_book_complete(message) and bool(_SPA_RE.search(_recent)))
    card = await find_activities(dest, interest=message, spa=_spa)
    card["options"] = _tier_sort(card.get("options", []), message)
    opts = card.get("options", [])
    has_prices = any(o.get("price") for o in opts)
    names_list = [o["name"] for o in opts if o.get("name") and not o.get("fallback")]
    matched = _match_named_ctx(message, names_list, history) if (_is_book_complete(message) and names_list) else None
    if _is_book_complete(message) and names_list:
        if matched:
            spoken = (f"Lovely choice — {matched} is pulled up on the right. Tap Book & Pay "
                      "on its card and I'll reserve your spot.")
            card["matched_option"] = matched
        elif _foreign_referent(message, names_list):
            spoken = (f"I don't see that one on the current list — what I have is "
                      f"{', '.join(names_list[:3])} and more on the card. Tap Book & Pay on any of them, or ask me for other ideas.")
        else:
            spoken = (f"Of course — tap Book & Pay on whichever one you'd like "
                      f"({', '.join(names_list[:3])}) and you're all set.")
    elif has_prices:
        spoken = f"A few things you can book in {dest} — {_named_options(opts)}. I've pulled them up with prices, ready to book."
    else:
        spoken = f"Here are some experiences you can book in {dest} — I've pulled it up for you."
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

async def run_itinerary_intent(message: str, history: list,
                               current_itinerary: "Optional[dict]" = None,
                               hotel_swap: "Optional[dict]" = None) -> dict:
    """Build (or locally revise) the full day-by-day itinerary and surface it to the UI.

    `hotel_swap` = {"name","city"} — a hotel change already resolved by the conductor from
    the conversation (guest confirmed a property Sasha offered); applied verbatim."""
    from app.services.itinerary_agent import build_itinerary, _is_revision

    # A fresh build with a BLANK brief must ask, not guess. "I wanna build a trip" used to
    # instantly compose a default 7-day plan for 2 — no destination, no length, no party ever
    # asked. One round of questions; the classifier routes the guest's answer back here (see
    # the intake follow-up branch), and "you decide" builds the default plan on request.
    if not ((current_itinerary or {}).get("days")) and not _is_revision(message) and not hotel_swap:
        _user_ctx = " ".join(
            m.get("content", "") for m in (history or [])
            if isinstance(m, dict) and m.get("role") == "user"
        ) + " " + (message or "")
        try:
            from app.services.local_itinerary import _days_in_text
            _knows_days = _days_in_text(_user_ctx.lower()) is not None
        except ImportError:
            _knows_days = bool(re.search(r"\b\d+\s*(?:day|days|night|nights)\b", _user_ctx.lower()))
        _knows_dest = bool(_find_destinations(_user_ctx))
        _hands_off = re.search(
            r"you (decide|choose|pick)|surprise me|up to you|whatever you (think|suggest|recommend)"
            r"|anything (works|is fine)|dealer'?s choice",
            (message or "").lower())
        if not _knows_dest and not _knows_days and not _hands_off:
            return {
                "agent": "itinerary",
                "response": (
                    "With pleasure! Just a couple of quick things so I get it right — "
                    "where in Vietnam would you like to go, how many days do you have, "
                    "and who's travelling? Or just say \"you decide\" and I'll plan "
                    "something special for you."
                ),
                "data": {},
            }

    itin = await build_itinerary(message, history, current_itinerary=current_itinerary,
                                 hotel_swap=hotel_swap)
    if not itin and not _is_revision(message):
        # The builder occasionally returns nothing (LLM returned malformed JSON, etc.).
        # Retry once — a bare empty response leaves the avatar silent AND the panel stale,
        # which is exactly the "it said ready but nothing changed" failure. One more try
        # usually succeeds. Revisions do NOT retry: they run the slow LLM path, and two
        # attempts blew through the 45s agent ceiling into the generic failure line —
        # better to ask the guest to try once more than to time the whole turn out.
            itin = await build_itinerary(message, history, current_itinerary=current_itinerary)
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
    if hotel_swap and hotel_swap.get("name"):
        spoken = (
            f"Done — you're now staying at {hotel_swap['name']}, and your {n}-day plan on "
            "the right reflects it. Anything else you'd like to change?"
        )
    elif _is_revision(message):
        spoken = (
            f"Done — I've updated your {n}-day plan, it's on the right. "
            "Anything else you'd like to change?"
        )
    else:
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

    # An empty/whitespace transcript (a mic blip) must never reach the LLM — Anthropic 400s
    # on empty content, both run_general calls fail, and the guest heard "I'm having a brief
    # connection issue" for saying nothing.
    if not (user_message or "").strip():
        return {"response": "Sorry, I didn't catch that — could you say it again?",
                "intents": ["general"], "photos": [], "tools_used": [], "links": [],
                "hotels": [], "bookings": [], "itinerary": None, "action": None,
                "booking_ref": None, "itinerary_id": None,
                "messages": list(conversation_history)}

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
    classification = {}
    if force_intent and force_intent in AGENT_REGISTRY:
        intents = [force_intent]
        context = user_message
        print(f"[Conductor] Intent forced by caller: {force_intent}")
    else:
        classification = await classify_intents(user_message, conversation_history, has_itinerary)
        intents = classification.get("intents", ["general"])
        context = classification.get("context", user_message)

        # Semantic backstop: a change to an EXISTING plan that the keyword layer missed must
        # still rebuild, not fall through to chat where Sasha would only TALK about the change.
        # Scoped to the pure-chat fallthrough so it never hijacks a specific booking intent.
        _REV_VERB = re.compile(
            r"\b(swap|replace|switch|remove|drop|skip|instead|cheaper|upgrade|luxur\w*|add|include|change)\b"
            r"|take out|get rid|don'?t want|no longer", re.I)
        if has_itinerary and not ({"itinerary", "book_trip", "flight", "cab", "restaurant"} & set(intents)) \
                and _REV_VERB.search(user_message) \
                and not re.search(r"photo|picture|image|\bfoto\b", user_message.lower()):
            print("[Conductor] plan-change wording over a stored plan — routing to itinerary")
            intents = ["itinerary"]
        elif has_itinerary and intents == ["general"] and await wants_trip_change(user_message, conversation_history):
            print("[Conductor] general fell through but guest wants a plan change — routing to itinerary")
            intents = ["itinerary"]

    # Asking to book with nothing built is a different conversation from asking to book a real
    # plan. Route it somewhere that offers to build instead of somewhere that takes money.
    if intents == ["book_trip"] and session_id and not stored_itinerary:
        print("[Conductor] book_trip requested but no itinerary exists for this session")
        intents = ["book_trip_no_plan"]

    # ── Context-aware confirmations over a stored trip ────────────────────────────────
    # While the guest is CHANGING something about their trip (hotel, a city, an activity),
    # a confirmation — "book it", "yes, do that", naming the property Sasha offered — must
    # apply that change TO THE TRIP, never open a standalone booking beside it. The
    # standalone path double-charges (the trip total already carries a hotel) and leaves
    # the plan contradicting what Sasha just agreed to.
    _revision_msg = None        # what the itinerary reviser parses instead of the raw message
    _hotel_swap_target = None   # {"name","city"} resolved from the conversation, applied verbatim
    if stored_itinerary:
        _recent_user = [m.get("content", "") for m in conversation_history[-8:]
                        if isinstance(m, dict) and m.get("role") == "user"]
        _CHANGE_VOCAB = re.compile(
            r"\b(change|swap|switch|replace|different|another|other|instead|rather|upgrade|"
            r"downgrade|cheaper|budget|luxur\w*|nicer|better|add|include|remove|skip|drop|"
            r"extend|shorten)\b")
        _TRIP_TARGET = re.compile(
            r"\b(hotel|hotels|stay|resort|accommodation|itinerary|plan|trip|day|days|night|"
            r"nights|activity|activities|city|cities)\b")
        # Change-pending detection is BROADER than the reviser's vocabulary: "I don't like
        # this hotel" carries no revise verb (it lands in general chat, where Sasha offers
        # alternatives) but it IS a hotel-change conversation — the reported bug's exact shape.
        _DISSATISFIED = re.compile(
            r"don'?t (like|love|want)|not (happy|a fan|keen|sure)|hate|dislike|what else|"
            r"other options|alternatives|something else|any other")
        _hotel_change_pending = any(
            (_CHANGE_VOCAB.search(t.lower()) or _DISSATISFIED.search(t.lower())) and
            re.search(r"\b(hotel|hotels|stay|resort|accommodation)\b", t.lower())
            for t in _recent_user)
        # A short confirmation carries no instruction of its own — the instruction lives in
        # the turns before it.
        _conf = user_message.strip().lower().rstrip(".!?")
        _confirmish = len(_conf.split()) <= 7 and bool(re.match(
            r"^(yes|yeah|yep|yup|sure|ok(ay)?|perfect|great|lovely|absolutely|sounds good|"
            r"that works|do (it|that)|go (ahead|for it)|let'?s (do|go with) (it|that)|"
            r"book (it|that)|that one|please do|yes please)\b", _conf))

        async def _resolve_offered_hotel():
            """The specific property this confirmation refers to — named in the guest's own
            message, else the one Sasha just offered."""
            _payload = (stored_itinerary or {}).get("payload") or {}
            _plan_cities = list(dict.fromkeys(
                d.get("city") for d in _payload.get("days", []) if d.get("city")))
            _cands = []   # (hotel name, city) — curated pool + this session's live-searched card
            for _c in _plan_cities:
                for _hh in _VH_POOL.get(_c, []) or []:
                    if _hh.get("name"):
                        _cands.append((_hh["name"], _c))
                if session_id:
                    _raw = await chat_store.get_session_card(session_id, "hotel", _c)
                    _items = _raw.get("items") if isinstance(_raw, dict) else (
                        _raw if isinstance(_raw, list) else [])
                    for _hh in _items or []:
                        if _hh.get("name"):
                            _cands.append((_hh["name"], _hh.get("city") or _c))
            _names = [n for n, _ in _cands]
            _t = _match_named(user_message, _names) if _names else None
            if not _t and _names:
                _alines = [m.get("content", "") for m in conversation_history
                           if isinstance(m, dict) and m.get("role") == "assistant"]
                for _line in reversed(_alines[-4:]):
                    _t = _match_named(_line, _names, fuzzy=False)
                    if _t:
                        break
            if not _t:
                return None
            return {"name": _t, "city": next((c for n, c in _cands if n == _t), "")}

        # (a) "Book it / book the Capella" that classification read as a standalone hotel
        # purchase — during a hotel-change conversation it's the swap being confirmed.
        if classification.get("force_hotels") and "itinerary" not in intents and _hotel_change_pending:
            _hotel_swap_target = await _resolve_offered_hotel()
            if _hotel_swap_target:
                _revision_msg = f"change the hotel to {_hotel_swap_target['name']}"
                intents = ["itinerary"]
                classification["force_hotels"] = False
                print(f"[Conductor] hotel-change confirmed — updating the trip: {_revision_msg}")
        # (b) A bare confirmation already routed to the itinerary ("shall I…?" → "yes") —
        # resolve WHAT was confirmed, or the builder would recompose instead of revising.
        elif "itinerary" in intents and _confirmish and not _CHANGE_VOCAB.search(_conf):
            if _hotel_change_pending:
                _hotel_swap_target = await _resolve_offered_hotel()
            if _hotel_swap_target:
                _revision_msg = f"change the hotel to {_hotel_swap_target['name']}"
                print(f"[Conductor] confirmed hotel change — updating the trip: {_revision_msg}")
            else:
                # Replay the guest's own pending change ask (add/remove a city, swap an
                # activity, cheaper hotels…) — exactly what would have run had they not
                # paused to confirm.
                for _t in reversed(_recent_user):
                    _tl = _t.lower()
                    if _CHANGE_VOCAB.search(_tl) and (_TRIP_TARGET.search(_tl) or _find_destinations(_tl)):
                        _revision_msg = _t
                        print(f"[Conductor] confirmed pending change — replaying: {_revision_msg!r}")
                        break
    
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
    _stay_hint = _strong_stay or any(w in _lower_msg for w in ("hotel", "stay", "resort", "accommodation"))
    # Hotels surface ONLY on a stay cue. The old rule ((not specific) or strong_stay) pushed
    # hotel cards on chit-chat/general/itinerary/book_trip turns: "thanks" wiped the restaurant
    # card the guest was about to book and replaced it with hotel Book & Pay buttons (the July
    # "paid for a Sofitel instead of a table" shape), and the itinerary turn offered a hotels-
    # only checkout price that disagreed with the trip total beside it.
    _want_hotels = (_stay_hint and not (_specific_booking and not _strong_stay)) \
        or bool(classification.get("force_hotels"))
    early_hotels = recommend_hotels(user_message, "", intents, history_text) if _want_hotels else []
    if early_hotels:
        _hcity = early_hotels[0].get("city", "") or _dest_in_play(user_message, conversation_history)
        # Cache the hotel list per session so the SAME properties persist across turns — the
        # live search returns a different set each call, which is what let a hotel card silently
        # replace the restaurant cards mid-booking. A refinement ("cheaper/luxury hotels") carries
        # a different hint and refetches; a generic ask reuses the cached set. Stored as
        # {"_hint", "items"} so the hint travels with the list.
        _hhint = _req_hint("hotel", user_message)
        _raw = await chat_store.get_session_card(session_id, "hotel", _hcity) if session_id else None
        cached_hotels = None
        if isinstance(_raw, dict) and _raw.get("_hint", "") == _hhint:
            cached_hotels = _raw.get("items")
        elif isinstance(_raw, list) and _hhint == "":   # legacy list cache == generic
            cached_hotels = _raw
        if cached_hotels:
            early_hotels = cached_hotels
        else:
            try:
                live_hotels = await find_hotels_live(_hcity)
                if live_hotels:
                    early_hotels = live_hotels
            except Exception as e:
                print(f"[Conductor] live hotels failed, using curated: {e}")
            if session_id and early_hotels:
                await chat_store.save_session_card(session_id, "hotel", _hcity,
                                                   {"_hint": _hhint, "items": early_hotels})
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
        elif intent in ("flight", "cab", "restaurant"):
            # These cache their cards per session, so pass the session for stable results.
            tasks.append((intent, runner(user_message, conversation_history, session_id=session_id)))
        elif intent == "itinerary":
            # Pass the STORED plan so revisions edit what the guest is looking at (and
            # rebuilds keep its route) instead of re-deriving from a history window. A
            # confirmed change arrives as "book it"/"yes" — the reviser gets the resolved
            # instruction (or the guest's own replayed ask) instead of the confirmation.
            _cur = (stored_itinerary or {}).get("payload") if isinstance(stored_itinerary, dict) else None
            tasks.append((intent, runner(_revision_msg or user_message, conversation_history,
                                         current_itinerary=_cur, hotel_swap=_hotel_swap_target)))
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
        service_error = False
        try:
            gen = await asyncio.wait_for(
                run_general(user_message, conversation_history, general_prompt), timeout=20.0
            )
            final_response = (gen.get("response") or "").strip()
        except Exception as e:
            # run_general is a raw LLM call — a timeout, a rate limit, or an EXHAUSTED API key all
            # land here. This is the failure behind the demo's "it got worse each time and then
            # just looped": once the key runs dry every turn throws, and the old code answered each
            # one with the SAME "tell me more about what you're after" — a line that both blames
            # the guest for our outage and repeats forever. Flag it so we say something honest.
            print(f"[Conductor] general fallback failed ({e})")
            final_response = ""
            service_error = True
        if not final_response:
            # Two different failures, two different things to say — and NEVER the same sentence the
            # guest just heard (that identical repeat is what read as a broken loop).
            last_assistant = next(
                (m.get("content", "") for m in reversed(conversation_history or [])
                 if isinstance(m, dict) and m.get("role") == "assistant"),
                "",
            ).strip()
            if service_error:
                pool = [
                    "Sorry — I'm having a brief connection issue on my end, not you. Give me a moment and ask me that again.",
                    "I hit a technical snag just now — that's on me, not you. One moment and let's try that again.",
                ]
            else:
                pool = [
                    "Could you tell me a little more about what you're after?",
                    "Tell me a bit more about the trip you have in mind and I'll take it from there.",
                    "Where would you like to start — a destination, some dates, or shall I begin planning?",
                ]
            final_response = next((p for p in pool if p.strip() != last_assistant), pool[0])
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
        # Party size drives the price, so the spoken total must name the RIGHT count — the old
        # hardcoded "for two" said "two" even after a rebuild for four, contradicting the card.
        _trav = (itinerary.get("cost_breakdown") or {}).get("travellers") or itinerary.get("travellers")
        _party_phrase = "one traveller" if _trav == 1 else f"{_TRAVELLER_WORDS.get(_trav, 'two')} travellers"
        _total_str = (
            f" The estimated total for {_party_phrase} — hotels, activities and meals — comes to about ${int(_total):,}."
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

    # Tier-worded stay asks ("luxury hotels", "budget hotels") must be honoured by the FINAL
    # list — the static-cache rows arrive in curated flagship-first order and previously
    # overrode any earlier sorting. Reorder here, whatever the source.
    if hotels:
        _hl = user_message.lower()
        if any(w in _hl for w in _LUX_WORDS):
            hotels = sorted(hotels, key=lambda h: (-(h.get("stars", 0)), -(h.get("price_from", 0))))
        elif any(w in _hl for w in _BUDGET_WORDS):
            hotels = sorted(hotels, key=lambda h: h.get("price_from", 10 ** 9))

    # ── Persist bookable offers so each card checks out at a SERVER-SET price ──────────
    # Same trust model as the whole trip: a hotel/flight/cab is priced from its stored offer at
    # checkout, never from an amount the browser sends (flight/cab fares are LLM-generated per
    # turn and would be unverifiable otherwise). We attach the offer_id + amount back onto each
    # card so the UI can render "Book & Pay $X" and hand the offer_id to /api/payments.
    if session_id:
        # Hotel = full stay: nightly rate × the trip's night count (this turn's plan, else the
        # stored one), falling back to a single night when no trip exists yet.
        _nsrc = itinerary if (itinerary and itinerary.get("days")) else (
            (stored_itinerary or {}).get("payload") if isinstance(stored_itinerary, dict) else None)
        # Nights = days - 1 (the last day is departure) — the SAME model the itinerary's own
        # cost breakdown uses (_enrich skips the final day's night). Billing len(days) nights
        # made the hotel card price disagree with the trip total on screen.
        _days = len((_nsrc or {}).get("days", []))
        _nights = max(1, _days - 1) if _days else 1
        # Party size (for per-head pricing, e.g. a restaurant table) — from the trip if one
        # exists, else from what the GUEST has said (a solo guest who just told Sasha
        # "I'm travelling alone" must not be quoted "Table for 2"), else assume a couple.
        _party = ((_nsrc or {}).get("cost_breakdown") or {}).get("travellers") \
            or (_nsrc or {}).get("travellers")
        if not _party:
            from app.services.itinerary_agent import _travellers_from
            _party = _travellers_from(conversation_history, user_message)
        try:
            _party = int(_party)
        except (TypeError, ValueError):
            _party = 2
        _uid = user_id or chat_store.DEMO_USER_ID
        for h in hotels:
            try:
                per_night = int(h.get("price_from") or 0)
                if per_night <= 0:
                    continue
                amount = per_night * _nights
                label = f"{_nights} night{'s' if _nights != 1 else ''} · {h.get('name', 'Hotel')}"
                oid = str(uuid.uuid4())
                await chat_store.create_offer(
                    offer_id=oid, session_id=session_id, user_id=_uid, kind="hotel",
                    name=h.get("name", ""), label=label, amount_usd=amount,
                    meta={"nights": _nights, "price_from": per_night, "city": h.get("city", "")},
                )
                h["offer_id"] = oid
                h["amount_usd"] = amount
                h["nights"] = _nights
            except Exception as e:
                print(f"[Conductor] hotel offer persist failed: {e}")
        for card in (bookings or []):
            kind = card.get("type")
            if kind not in ("flight", "cab", "restaurant", "activity"):
                continue
            for o in card.get("options", []):
                try:
                    if kind == "restaurant":
                        # A reservation is a prepaid table: per-person meal estimate × party.
                        per = int(o.get("per_person_usd") or 0)
                        amt = per * _party
                        label = f"Table for {_party} · {o.get('name', '')}"
                    else:
                        amt = int(o.get("amount_usd") or 0)
                        # Cached activity rows predate amount_usd and carry only the display
                        # price ("$45") — recover the number so tours check out in-app through
                        # Stripe like every other card, instead of a third-party link.
                        if not amt and kind == "activity":
                            amt = int(re.sub(r"[^0-9]", "", str(o.get("price") or "")) or 0)
                        label = f"{card.get('title') or kind.title()} · {o.get('name', '')}"
                        # A flight fare is per SEAT (cabs are per vehicle) — say so on the
                        # label the guest sees at checkout, so a 4-traveller party isn't led
                        # to think one tap covers everyone.
                        if kind == "flight":
                            label += " · per person"
                        # Tour prices are per head too.
                        if kind == "activity":
                            label += " · per person"
                    if amt <= 0:
                        continue   # fallback/no-price options remain a plain external link
                    oid = str(uuid.uuid4())
                    await chat_store.create_offer(
                        offer_id=oid, session_id=session_id, user_id=_uid, kind=kind,
                        name=o.get("name", ""), label=label, amount_usd=amt,
                        meta={"dest": card.get("dest", ""), "detail": o.get("detail", ""),
                              "party": _party if kind == "restaurant" else None},
                    )
                    o["offer_id"] = oid
                    o["amount_usd"] = amt   # so the card shows "Book & Pay $X" (restaurants had none)
                except Exception as e:
                    print(f"[Conductor] {kind} offer persist failed: {e}")

    # Voice-driven single-item booking: the guest named (or contextually meant) ONE option
    # on a card ("book Tam Vi", "reserve it"). Now that its server-priced offer exists,
    # hand the frontend everything it needs to open the payment popup directly — the guest
    # asked Sasha to book, not to be told which button to press. Never stomps a whole-trip
    # await_payment.
    payment_item = None
    if not action:
        for _card in (bookings or []):
            _m = _card.pop("matched_option", None)
            if not _m or payment_item:
                continue
            for _o in _card.get("options", []):
                if _o.get("name") == _m and _o.get("offer_id") and (_o.get("amount_usd") or 0) > 0:
                    payment_item = {
                        "offer_id": _o["offer_id"],
                        "label": f"{_card.get('title') or _card.get('type', '').title()} · {_o['name']}",
                        "amount_usd": _o["amount_usd"],
                        "kind": _card.get("type", ""),
                        "name": _o["name"],
                    }
                    break
        # A named HOTEL booking ("book the Sofitel") routes through the general/stay path —
        # its offers live on the hotels list, not a card. Never on a trip-revision turn: the
        # change just went INTO the trip, so no standalone stay checkout may open beside it.
        if not payment_item and hotels and not (_revision_msg or _hotel_swap_target) \
                and any(w in _lower_msg for w in BOOK_COMPLETE_WORDS):
            _hm = _match_named(user_message, [h.get("name", "") for h in hotels])
            if _hm:
                for _h in hotels:
                    if _h.get("name") == _hm and _h.get("offer_id") and (_h.get("amount_usd") or 0) > 0:
                        payment_item = {
                            "offer_id": _h["offer_id"],
                            "label": f"{_h.get('nights', 1)} night{'s' if _h.get('nights', 1) != 1 else ''} · {_h['name']}",
                            "amount_usd": _h["amount_usd"],
                            "kind": "hotel",
                            "name": _h["name"],
                        }
                        break
    if payment_item:
        action = "await_payment_item"
        final_response = (
            f"Great choice — {payment_item['name']}. I've opened the booking for you — "
            "just pop in your name and email, and tap Pay to confirm."
        )

    return {
        "response": final_response,
        "payment_item": payment_item,
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
