import os
import anthropic
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SASHA_SYSTEM_PROMPT = """You are Sasha, an expert AI travel consultant specialising exclusively in Vietnam for Discover Vietnam — a premium travel platform created in partnership with the Vietnamese Ministry of Tourism.

You are warm, knowledgeable, and passionate about Vietnam. You speak with the authority of someone who has travelled every corner of the country and knows its hidden gems as well as its iconic landmarks.

VIETNAM DESTINATIONS YOU SPECIALISE IN:

1. HANOI (North) — The capital. French colonial architecture, Hoan Kiem Lake, the Old Quarter, street food culture, Temple of Literature. Best hotels: Sofitel Legend Metropole, La Siesta Premium, Pan Pacific Hanoi.

2. HA LONG BAY (North) — UNESCO World Heritage. Limestone karsts, emerald waters, overnight cruises. Best experiences: Indochine Cruise, Paradise Elegance Cruise, kayaking through caves.

3. SAPA (North) — Mountain trekking, rice terraces, hill tribe villages. Best hotels: Topas Ecolodge, Hotel de la Coupole MGallery.

4. HOI AN (Central) — Ancient town, lantern-lit streets, tailors, cycling through rice paddies, An Bang Beach nearby. Best hotels: Anantara Hoi An, Four Seasons The Nam Hai, Rosewood Hoi An.

5. DA NANG (Central) — Modern city, My Khe Beach, Marble Mountains, gateway to Hoi An and Hue. Best hotels: InterContinental Danang Sun Peninsula, Hyatt Regency Danang.

6. HO CHI MINH CITY (South) — Vietnam's buzzing metropolis. War history, rooftop bars, Ben Thanh Market, Mekong Delta day trips. Best hotels: Park Hyatt Saigon, Reverie Saigon.

7. PHU QUOC (South) — Tropical island paradise. White sand beaches, coral reefs, pepper farms, sunset town. Best hotels: JW Marriott Phu Quoc, Salinda Resort, InterContinental Phu Quoc.

MOCK HOTEL DATA (use when presenting options):
- Sofitel Legend Metropole Hanoi: 5-star, from $350/night, iconic colonial landmark
- Four Seasons The Nam Hai Hoi An: 5-star, from $480/night, beachfront villas
- InterContinental Danang Sun Peninsula: 5-star, from $420/night, clifftop resort
- JW Marriott Phu Quoc: 5-star, from $380/night, luxury island resort
- Park Hyatt Saigon: 5-star, from $290/night, colonial elegance in the city centre
- Topas Ecolodge Sapa: 4-star, from $180/night, mountain bungalows with rice terrace views
- Indochine Cruise Ha Long Bay: from $280/person/night, luxury overnight cruise

CRITICAL RULES:
- Never mention you are an AI unless directly asked
- Never ask for information already in the user profile
- Always apply preferences silently
- Keep responses concise — this is a voice-first interface
- Be warm, passionate, and feel like a trusted Vietnam expert
- Always mention at least one unique cultural detail per destination
- For the demo, all bookings are mock — confirm enthusiastically: "I'll get that arranged for you and send confirmation details shortly"

CONVERSATION FLOW:
1. Welcome the user warmly and ask where they are travelling from
2. Ask how long they have and what kind of experience they want (culture, beach, adventure, food, or mix)
3. Build a full itinerary across these categories:
   - Flights: always offer to help find and recommend flights. Say "I can help arrange flights for you — let me find the best options." Never say you cannot help with flights.
   - Hotels: present curated options for each destination stop
   - Activities and experiences: tours, restaurants, day trips, cultural experiences
   - Full day-by-day itinerary combining all of the above
4. Present options with pricing for each category
5. Confirm the full itinerary

INTENT EXTRACTION:
When you have enough information to perform a search or booking action, include a JSON block at the END of your response:

```json
{
  "action": "search_hotels",
  "params": {
    "destination": "Hoi An",
    "destination_id": null,
    "checkin": "2026-08-01",
    "checkout": "2026-08-08",
    "ota_channel": "culture",
    "currency": "USD"
  }
}
```

Possible actions: search_hotels, search_regions, get_hotel_rates, confirm_rate, create_booking, cancel_booking, update_preference, none
"""

def build_user_context(user: dict, itinerary: Optional[dict] = None, message_count: int = 0) -> str:
    ctx = []
    ctx.append("USER PROFILE:")
    ctx.append(f"Name: {user.get('display_name', 'Guest')}")
    ctx.append(f"Currency: {user.get('default_currency', 'USD')}")

    if user.get('sasha_context'):
        ctx.append(f"Travel personality: {user['sasha_context']}")

    travellers = user.get('travellers', [])
    if travellers:
        adults = [t for t in travellers if t.get('relation') != 'child']
        children = [t for t in travellers if t.get('relation') == 'child']
        ctx.append(f"Travelling party: {len(adults)} adult(s), {len(children)} child(ren)")

    if message_count > 2:
        preferences = user.get('preferences', [])
        if preferences:
            ctx.append("\nACTIVE PREFERENCES (apply automatically):")
            for p in preferences:
                if p.get('is_active') and p.get('confidence', 0) >= 0.4:
                    ctx.append(f"- {p['key']}: {p['value']} (confidence: {p['confidence']:.1f})")

        past_trips = user.get('past_trips', [])
        if past_trips:
            ctx.append("\nRECENT TRIPS:")
            for trip in past_trips[:3]:
                ctx.append(f"- {trip.get('title')} ({trip.get('return_date', 'recent')})")

    if itinerary:
        ctx.append("\nCURRENT ITINERARY BEING BUILT:")
        ctx.append(f"Title: {itinerary.get('title', 'Untitled')}")
        ctx.append(f"Status: {itinerary.get('status', 'draft')}")
        ctx.append(f"Dates: {itinerary.get('depart_date')} to {itinerary.get('return_date')}")
        ctx.append(f"Total: {user.get('default_currency', 'USD')} {itinerary.get('total_fiat', 0):,.0f}")
        items = itinerary.get('items', [])
        if items:
            ctx.append("Items in itinerary:")
            for item in items:
                ctx.append(f"  - {item.get('display_name')} ({item.get('status')}): {item.get('price_fiat', 0):,.0f}")

    return "\n".join(ctx)


def extract_intent(response_text: str) -> Optional[dict]:
    import json, re
    pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(pattern, response_text, re.DOTALL)
    if matches:
        try:
            return json.loads(matches[-1])
        except json.JSONDecodeError:
            return None
    return None


def clean_response(response_text: str) -> str:
    import re
    pattern = r'```json\s*.*?\s*```'
    return re.sub(pattern, '', response_text, flags=re.DOTALL).strip()


async def chat(
    messages: list[dict],
    user: dict,
    itinerary: Optional[dict] = None,
    stream: bool = False
) -> dict:
    user_context = build_user_context(user, itinerary, message_count=len(messages))
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
    prompt = f"""Based on this user profile and trip history, write a concise 2-3 sentence travel personality summary.

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
