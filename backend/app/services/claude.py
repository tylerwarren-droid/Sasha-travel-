import os
import anthropic
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SASHA_SYSTEM_PROMPT = """You are Sasha, an expert AI travel consultant for a luxury travel platform. You are warm, knowledgeable, and deeply personal in your approach.

You have access to the user's complete travel profile, their current itinerary being built, and their travel preferences. Use all of this context naturally in conversation — never ask for information you already know.

Your job is to:
1. Understand what the user wants through natural conversation
2. Build their itinerary by extracting structured booking intent
3. Present hotel and flight options conversationally
4. Apply their preferences automatically without mentioning you're doing so
5. Confirm bookings and manage existing trips

CRITICAL RULES:
- Never mention you are an AI unless directly asked
- Never ask for information already in the user profile
- Always apply preferences silently — don't say "as per your preference"
- Keep responses concise — this is a voice-first interface
- When you have enough information to search, output a JSON block with intent
- Be warm, confident, and feel like a trusted travel advisor who knows the user well

INTENT EXTRACTION:
When you have enough information to perform a search or booking action, include a JSON block at the END of your response in this exact format:

```json
{
  "action": "search_hotels",
  "params": {
    "destination": "Maldives",
    "destination_id": null,
    "checkin": "2026-06-25",
    "checkout": "2026-07-02",
    "ota_channel": "beach",
    "currency": "GBP"
  }
}
```

Possible actions: search_hotels, search_regions, get_hotel_rates, confirm_rate, create_booking, cancel_booking, update_preference, none
"""

def build_user_context(user: dict, itinerary: Optional[dict] = None) -> str:
    """Build the personalised context block injected into every session"""
    ctx = []

    ctx.append(f"USER PROFILE:")
    ctx.append(f"Name: {user.get('display_name', 'Guest')}")
    ctx.append(f"Currency: {user.get('default_currency', 'GBP')}")

    if user.get('sasha_context'):
        ctx.append(f"Travel personality: {user['sasha_context']}")

    travellers = user.get('travellers', [])
    if travellers:
        adults = [t for t in travellers if t.get('relation') != 'child']
        children = [t for t in travellers if t.get('relation') == 'child']
        ctx.append(f"Travelling party: {len(adults)} adult(s), {len(children)} child(ren)")

    preferences = user.get('preferences', [])
    if preferences:
        ctx.append(f"\nACTIVE PREFERENCES (apply automatically):")
        for p in preferences:
            if p.get('is_active') and p.get('confidence', 0) >= 0.4:
                ctx.append(f"- {p['key']}: {p['value']} (confidence: {p['confidence']:.1f})")

    past_trips = user.get('past_trips', [])
    if past_trips:
        ctx.append(f"\nRECENT TRIPS:")
        for trip in past_trips[:3]:
            ctx.append(f"- {trip.get('title')} ({trip.get('return_date', 'recent')})")

    if itinerary:
        ctx.append(f"\nCURRENT ITINERARY BEING BUILT:")
        ctx.append(f"Title: {itinerary.get('title', 'Untitled')}")
        ctx.append(f"Status: {itinerary.get('status', 'draft')}")
        ctx.append(f"Destination: {itinerary.get('destination_summary', {}).get('country', 'TBD')}")
        ctx.append(f"Dates: {itinerary.get('depart_date')} to {itinerary.get('return_date')}")
        ctx.append(f"Total: {user.get('default_currency', 'GBP')} {itinerary.get('total_fiat', 0):,.0f}")

        items = itinerary.get('items', [])
        if items:
            ctx.append(f"Items in itinerary:")
            for item in items:
                ctx.append(f"  - {item.get('display_name')} ({item.get('status')}): {item.get('price_fiat', 0):,.0f}")

    return "\n".join(ctx)


def extract_intent(response_text: str) -> Optional[dict]:
    """Extract JSON intent block from Claude's response if present"""
    import json
    import re

    pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(pattern, response_text, re.DOTALL)

    if matches:
        try:
            return json.loads(matches[-1])
        except json.JSONDecodeError:
            return None
    return None


def clean_response(response_text: str) -> str:
    """Remove JSON intent block from response before sending to user"""
    import re
    pattern = r'```json\s*.*?\s*```'
    return re.sub(pattern, '', response_text, flags=re.DOTALL).strip()


async def chat(
    messages: list[dict],
    user: dict,
    itinerary: Optional[dict] = None,
    stream: bool = False
) -> dict:
    """
    Main chat function. Returns cleaned response text and extracted intent.
    messages: [{"role": "user/assistant", "content": "..."}]
    """
    user_context = build_user_context(user, itinerary)

    system = f"{SASHA_SYSTEM_PROMPT}\n\n{user_context}"

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=system,
        messages=messages
    )

    raw_text = response.content[0].text
    intent = extract_intent(raw_text)
    clean_text = clean_response(raw_text)

    return {
        "response": clean_text,
        "intent": intent,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens
        }
    }


async def generate_sasha_context(user: dict, trips: list[dict]) -> str:
    """
    After a trip completes, generate an updated sasha_context summary.
    This is what gets injected into every future session.
    """
    prompt = f"""Based on this user's profile and trip history, write a concise 2-3 sentence 
travel personality summary that captures how they like to travel. 
This will be used to personalise future conversations.

User: {user.get('display_name')}
Trip history: {trips}
Current preferences: {user.get('preferences', [])}

Write only the summary, no preamble."""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()
