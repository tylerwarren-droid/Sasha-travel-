import anthropic
import asyncio
import json
from typing import Any

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
    """Classify what agents to activate for this message."""
    recent = conversation_history[-4:] if conversation_history else []
    context = "\n".join([f"{m['role']}: {m['content']}" for m in recent if isinstance(m.get('content'), str)])
    
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=200,
        system=INTENT_CLASSIFIER_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Conversation so far:\n{context}\n\nNew message: {user_message}"
        }]
    )
    
    text = response.content[0].text.strip()
    try:
        return json.loads(text)
    except:
        return {"intents": ["general"], "primary": "general", "context": user_message}


# ─────────────────────────────────────────────
# AGENT REGISTRY
# Each agent is registered here with its runner
# Adding a new agent = adding one entry here
# ─────────────────────────────────────────────

async def run_general(message: str, history: list) -> dict:
    """General Sasha conversation — travel advice, destinations, planning."""
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        system="""You are Sasha, a warm and knowledgeable AI travel concierge. 
You specialise in Vietnam but can help with travel anywhere.
Keep responses concise and conversational — you are speaking, not writing an essay.
Maximum 3 sentences unless asked for more detail.""",
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
    """Health agent — finds doctors, clinics, telemedicine near user."""
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        system="""You are Sasha's health specialist. Help travelers find medical assistance.
For Vietnam: recommend FV Hospital (HCMC), Vinmec (Hanoi/Danang), Family Medical Practice (all cities).
For urgent: always recommend calling the hotel front desk first — they have doctor-on-call services.
International SOS: +84 28 3829 8520.
Keep it calm, practical and reassuring.""",
        messages=history + [{"role": "user", "content": message}]
    )
    return {
        "agent": "health",
        "response": response.content[0].text,
        "data": {}
    }


async def run_beauty_intent(message: str, history: list) -> dict:
    """Beauty agent — spa, massage, nails, treatments."""
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        system="""You are Sasha's beauty and wellness specialist. Help travelers find spas, massages, nail services and beauty treatments.
For Vietnam: top options include Mia Spa, La Maison de L'Apothiquaire, Palmarosa Spa. 
Most luxury hotels have in-room treatment services — always check with concierge first.
Traditional Vietnamese massage typically $15-30/hour. Hot stone, aromatherapy $30-60.
You can arrange mobile beauticians to come to the hotel room.""",
        messages=history + [{"role": "user", "content": message}]
    )
    return {
        "agent": "beauty",
        "response": response.content[0].text,
        "data": {}
    }


async def run_dog_walking_intent(message: str, history: list) -> dict:
    """Dog walking agent — pet care while traveling."""
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        system="""You are Sasha's pet care specialist. Help travelers find dog walking and pet sitting services.
For Vietnam: recommend checking Rover.com, local Facebook expat groups, or asking the hotel concierge.
Many boutique hotels in Vietnam are pet-friendly and can arrange dog walkers.
Always confirm the walker's experience with the specific breed if relevant.""",
        messages=history + [{"role": "user", "content": message}]
    )
    return {
        "agent": "dog_walking",
        "response": response.content[0].text,
        "data": {}
    }


# Agent registry — maps intent names to runner functions
AGENT_REGISTRY = {
    "golf": run_golf_intent,
    "foto": run_foto_intent,
    "booking_confirmation": run_booking_confirmation_intent,
    "health": run_health_intent,
    "beauty": run_beauty_intent,
    "dog_walking": run_dog_walking_intent,
    "general": run_general,
}


# ─────────────────────────────────────────────
# THE CONDUCTOR
# Classifies, fires agents in parallel, merges
# ─────────────────────────────────────────────

MERGE_PROMPT = """You are Sasha, a warm AI travel concierge. 
You have received responses from multiple specialist agents.
Synthesize them into ONE natural, conversational response.
Do not mention "agents" or "specialists" — just be Sasha.
Keep it concise and warm. Max 4 sentences unless detail is needed."""


async def conduct(user_message: str, conversation_history: list = None) -> dict:
    """
    The Conductor — main entry point.
    Classifies intents, fires agents in parallel, merges results.
    """
    if conversation_history is None:
        conversation_history = []

    # Step 1 — Classify intents
    classification = await classify_intents(user_message, conversation_history)
    intents = classification.get("intents", ["general"])
    context = classification.get("context", user_message)
    
    print(f"[Conductor] Intents: {intents}")

    # Step 2 — Fire all relevant agents in parallel
    tasks = []
    for intent in intents:
        runner = AGENT_REGISTRY.get(intent, run_general)
        if intent == "foto":
            tasks.append(runner(user_message, conversation_history, context))
        else:
            tasks.append(runner(user_message, conversation_history))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Step 3 — Collect valid results
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

    # Step 4 — Merge responses
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
            system=MERGE_PROMPT,
            messages=[{"role": "user", "content": f"User asked: {user_message}\n\nAgent responses:\n{combined}"}]
        )
        final_response = merge_response.content[0].text

    # Step 5 — Update conversation history
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
