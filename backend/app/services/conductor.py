import anthropic
import asyncio
import json
from typing import Any, Optional

from app.services.prompts import get_prompt_async
from app.services.tenant import ClientConfig

client = anthropic.Anthropic()

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


async def classify_intents(user_message: str, conversation_history: list) -> dict:
    """Classify intents using fast keyword matching."""
    lower = user_message.lower()
    intents = []

    GOLF_WORDS = ["golf", "tee time", "tee-time", "fairway", "caddy", "green fee", "golf course", "play golf", "montgomerie", "hoiana", "bluffs", "ba na hills", "vinpearl golf"]
    BEAUTY_WORDS = ["massage", "spa", "nails", "facial", "manicure", "pedicure", "beauty", "salon", "treatment", "relaxation", "wellness"]
    HEALTH_WORDS = ["doctor", "medical", "sick", "pharmacy", "clinic", "hospital", "hurt", "ill", "prescription", "nurse", "health", "medicine"]
    DOG_WORDS = ["dog", "pet", "dog walk", "dog sit", "kennel", "grooming", "puppy"]
    RESTAURANT_WORDS = ["restaurant", "dinner", "lunch", "breakfast", "eat", "food", "table", "reservation", "book a table", "dining", "cuisine", "cafe", "bar", "rooftop", "where to eat", "hungry"]
    BOOKING_WORDS = ["confirm booking", "hotel reference", "pms", "booking.com ref", "expedia ref", "booking number", "confirm my booking", "reservation number"]
    FOTO_WORDS = ["show me", "photo", "picture", "image", "what does", "what do", "look like"]
    CREDIT_CARD_WORDS = ["credit card", "which card", "points", "miles", "rewards", "amex", "chase sapphire", "capital one", "bilt", "card to use", "earn points", "transfer points", "annual credit", "card benefits", "maximize points", "best card"]
    CAR_RENTAL_WORDS = ["rental car", "car rental", "rent a car", "hire a car", "rental insurance", "cdw", "collision waiver", "rental coverage", "hertz", "avis", "enterprise rental", "europcar", "should i take insurance"]
    VISA_WORDS = ["visa", "entry requirements", "passport", "do i need a visa", "travel documents", "entry restriction", "visa on arrival", "evisa", "e-visa", "tourist visa", "transit visa"]
    CURRENCY_WORDS = ["currency", "exchange rate", "money", "atm", "cash", "should i use my card", "tipping", "tip", "local money", "how much is", "convert", "dong", "baht", "peso", "rupiah", "ringgit", "won"]
    WEATHER_WORDS = ["weather", "what to pack", "climate", "best time to visit", "rainy season", "temperature", "hot or cold", "forecast", "will it rain", "typhoon", "monsoon", "dry season"]
    EMERGENCY_WORDS = ["emergency", "lost passport", "stolen", "hospital", "police", "help me", "robbery", "accident", "embassy", "arrested", "lost my", "stolen my", "hurt badly", "need help urgently", "crisis"]
    LANGUAGE_WORDS = ["language", "phrases", "how do i say", "translation", "etiquette", "customs", "culture", "local words", "speak", "greetings", "thank you in", "hello in", "dress code", "cultural"]
    PACKING_WORDS = ["packing", "what to bring", "luggage", "what should i pack", "suitcase", "carry on", "what do i need to bring", "what to pack", "packing list", "bag", "baggage"]
    FAMILY_WORDS = ["kids", "children", "family", "baby", "toddler", "kid-friendly", "family travel", "stroller", "car seat", "with children", "my kids", "travelling with kids", "child friendly", "infant"]

    if any(w in lower for w in GOLF_WORDS):
        intents.append("golf")
        intents.append("foto")
    if any(w in lower for w in BEAUTY_WORDS):
        intents.append("beauty")
    if any(w in lower for w in HEALTH_WORDS):
        intents.append("health")
    if any(w in lower for w in DOG_WORDS):
        intents.append("dog_walking")
    # Restaurant only fires when actively seeking a restaurant — not just mentioning food/dining
    RESTAURANT_ACTION_WORDS = ["find", "book", "reserve", "recommend", "suggestion", "where to", "looking for", "need a", "want a", "good restaurant", "best restaurant", "book a table", "make a reservation", "dinner tonight", "lunch today", "place to eat"]
    restaurant_action = any(w in lower for w in RESTAURANT_ACTION_WORDS)
    restaurant_topic = any(w in lower for w in RESTAURANT_WORDS)
    if restaurant_topic and restaurant_action:
        intents.append("restaurant")
    # Keep restaurant context if conversation already has restaurant intent (follow-up messages)
    history_text = " ".join([m.get("content", "") for m in conversation_history]).lower()
    if "restaurant" not in intents and any(w in history_text for w in RESTAURANT_WORDS) and any(w in history_text for w in RESTAURANT_ACTION_WORDS):
        intents.append("restaurant")
    if any(w in lower for w in BOOKING_WORDS):
        intents.append("booking_confirmation")
    if any(w in lower for w in FOTO_WORDS) and "foto" not in intents:
        intents.append("foto")
    SMART_SASHA_WORDS = ["cheapest", "best deal", "find me a flight", "search for flights", "plan a trip", "want to travel", "want to go to", "looking to travel", "trip to", "fly to", "flying to", "vacation to", "holiday to", "book a trip", "travel to", "where should i go", "best time to visit", "how do i get to"]
    if any(w in lower for w in SMART_SASHA_WORDS) and any(w in lower for w in ["flight", "fly", "travel", "trip", "vacation", "holiday", "visit", "go to", "europe", "asia", "caribbean", "mexico", "africa", "australia"]):
        intents.append("smart_sasha")
    if any(w in lower for w in CREDIT_CARD_WORDS):
        intents.append("credit_card")
    if any(w in lower for w in CAR_RENTAL_WORDS):
        intents.append("car_rental")
    if any(w in lower for w in VISA_WORDS):
        intents.append("visa")
    if any(w in lower for w in CURRENCY_WORDS):
        intents.append("currency")
    if any(w in lower for w in WEATHER_WORDS):
        intents.append("weather")
    if any(w in lower for w in EMERGENCY_WORDS):
        intents.append("emergency")
    if any(w in lower for w in LANGUAGE_WORDS):
        intents.append("language")
    if any(w in lower for w in PACKING_WORDS):
        intents.append("packing")
    if any(w in lower for w in FAMILY_WORDS):
        intents.append("family")

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
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        system=general_prompt,
        messages=history + [{"role": "user", "content": message}]
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
    """Route to restaurant agent."""
    from app.services.restaurant_agent import run_restaurant_agent
    result = await run_restaurant_agent(message, history)
    return {
        "agent": "restaurant",
        "response": result["response"],
        "data": {"tools_used": result.get("tools_used", [])}
    }



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

async def run_visa_intent(message: str, history: list) -> dict:
    """Route to visa requirements agent."""
    from app.services.visa_agent import run_visa_agent
    result = await run_visa_agent(message, history)
    return {"agent": "visa", "response": result["response"], "data": {"tools_used": result.get("tools_used", [])}}


async def run_currency_intent(message: str, history: list) -> dict:
    """Route to currency and money agent."""
    from app.services.currency_agent import run_currency_agent
    result = await run_currency_agent(message, history)
    return {"agent": "currency", "response": result["response"], "data": {"tools_used": result.get("tools_used", [])}}


async def run_weather_intent(message: str, history: list) -> dict:
    """Route to weather and climate agent."""
    from app.services.weather_agent import run_weather_agent
    result = await run_weather_agent(message, history)
    return {"agent": "weather", "response": result["response"], "data": {"tools_used": result.get("tools_used", [])}}


async def run_emergency_intent(message: str, history: list) -> dict:
    """Route to emergency response agent."""
    from app.services.emergency_agent import run_emergency_agent
    result = await run_emergency_agent(message, history)
    return {"agent": "emergency", "response": result["response"], "data": {"tools_used": result.get("tools_used", [])}}


async def run_language_intent(message: str, history: list) -> dict:
    """Route to language and cultural etiquette agent."""
    from app.services.language_agent import run_language_agent
    result = await run_language_agent(message, history)
    return {"agent": "language", "response": result["response"], "data": {"tools_used": result.get("tools_used", [])}}


async def run_packing_intent(message: str, history: list) -> dict:
    """Route to packing list agent."""
    from app.services.packing_agent import run_packing_agent
    result = await run_packing_agent(message, history)
    return {"agent": "packing", "response": result["response"], "data": {"tools_used": result.get("tools_used", [])}}


async def run_family_intent(message: str, history: list) -> dict:
    """Route to family travel agent."""
    from app.services.family_agent import run_family_agent
    result = await run_family_agent(message, history)
    return {"agent": "family", "response": result["response"], "data": {"tools_used": result.get("tools_used", [])}}


# Agent registry — maps intent names to runner functions
AGENT_REGISTRY = {
    "golf": run_golf_intent,
    "foto": run_foto_intent,
    "booking_confirmation": run_booking_confirmation_intent,
    "health": run_health_intent,
    "beauty": run_beauty_intent,
    "dog_walking": run_dog_walking_intent,
    "restaurant": run_restaurant_intent,
    "smart_sasha": run_smart_sasha_intent,
    "credit_card": run_credit_card_intent,
    "car_rental": run_car_rental_intent,
    "visa": run_visa_intent,
    "currency": run_currency_intent,
    "weather": run_weather_intent,
    "emergency": run_emergency_intent,
    "language": run_language_intent,
    "packing": run_packing_intent,
    "family": run_family_intent,
    "general": run_general,
}


# ─────────────────────────────────────────────
# THE CONDUCTOR
# Classifies, fires agents in parallel, merges
# ─────────────────────────────────────────────

async def conduct(
    user_message: str,
    conversation_history: list = None,
    client_config: Optional[ClientConfig] = None,
) -> dict:
    """
    The Conductor — main entry point.
    Classifies intents, fires agents in parallel, merges results.
    """
    if conversation_history is None:
        conversation_history = []

    # Step 1 — Load system prompts from DB (TTL-cached; falls back to static)
    general_prompt = await get_prompt_async("conductor.general")
    merge_prompt = await get_prompt_async("conductor.merge")

    # Apply client-specific persona name if different from default
    persona = (client_config.persona_name if client_config else None) or "Sasha"
    if persona != "Sasha":
        general_prompt = general_prompt.replace("Sasha", persona)
        merge_prompt = merge_prompt.replace("Sasha", persona)

    # Step 2 — Classify intents
    classification = await classify_intents(user_message, conversation_history)
    intents = classification.get("intents", ["general"])
    context = classification.get("context", user_message)
    
    print(f"[Conductor] Intents: {intents}")

    # Step 3 — Fire all relevant agents in parallel
    tasks = []
    for intent in intents:
        runner = AGENT_REGISTRY.get(intent, run_general)
        if intent == "foto":
            tasks.append(runner(user_message, conversation_history, context))
        elif intent == "general":
            tasks.append(runner(user_message, conversation_history, general_prompt))
        else:
            tasks.append(runner(user_message, conversation_history))

    async def run_with_timeout(task, timeout=30.0):
        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"[Conductor] Agent timed out after {timeout}s")
            return {"agent": "timeout", "response": "", "data": {}}
        except Exception as e:
            print(f"[Conductor] Agent error: {e}")
            return {"agent": "error", "response": "", "data": {}}

    results = await asyncio.gather(*[run_with_timeout(t) for t in tasks], return_exceptions=True)

    # Step 4 — Collect valid results
    agent_responses = []
    photos = []
    tools_used = []

    for result in results:
        if isinstance(result, Exception):
            print(f"[Conductor] Agent error: {result}")
            continue
        
        if result["agent"] == "foto":
            photos = result["data"].get("photos", [])
        elif result.get("response"):
            agent_responses.append({
                "agent": result["agent"],
                "response": result["response"]
            })
            if result["data"].get("tools_used"):
                tools_used.extend(result["data"]["tools_used"])

    # Step 5 — Merge responses
    if len(agent_responses) == 0:
        final_response = "I'm here to help — could you tell me a bit more about what you need?"
    elif len(agent_responses) == 1:
        final_response = agent_responses[0]["response"]
    else:
        # Multiple agents responded — merge them
        combined = "\n\n".join([f"[{r['agent'].upper()}]: {r['response']}" for r in agent_responses])
        merge_response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            system=merge_prompt,
            messages=[{"role": "user", "content": f"User asked: {user_message}\n\nAgent responses:\n{combined}"}]
        )
        final_response = merge_response.content[0].text

    # Step 6 — Update conversation history
    updated_history = conversation_history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": final_response}
    ]

    return {
        "response": final_response,
        "intents": intents,
        "photos": photos,
        "tools_used": tools_used,
        "messages": updated_history
    }
