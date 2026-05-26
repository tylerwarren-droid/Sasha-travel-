import os
import httpx
import anthropic
import json
import re

client = anthropic.Anthropic()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
BLAND_API_KEY = os.getenv("BLAND_API_KEY", "").strip()
SASHA_FROM_EMAIL = "onboarding@resend.dev"
SASHA_NOTIFY_EMAIL = "tylerwarren@gmail.com"

RESTAURANT_TOOLS = [
    {
        "name": "find_restaurant",
        "description": "Search for restaurants near a location by cuisine, budget, or occasion.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "cuisine": {"type": "string", "description": "e.g. Vietnamese, seafood, Italian, rooftop, fine dining"},
                "budget": {"type": "string", "description": "budget, mid_range, or luxury"},
                "occasion": {"type": "string", "description": "e.g. romantic dinner, business lunch, family, birthday"}
            },
            "required": ["location"]
        }
    },
    {
        "name": "send_reservation_email",
        "description": "Send a table reservation request email to a restaurant on behalf of the guest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "restaurant_email": {"type": "string"},
                "restaurant_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "guest_email": {"type": "string"},
                "guest_phone": {"type": "string"},
                "date": {"type": "string"},
                "time": {"type": "string"},
                "party_size": {"type": "string"},
                "occasion": {"type": "string"},
                "special_requests": {"type": "string"},
                "hotel_name": {"type": "string"}
            },
            "required": ["restaurant_email", "restaurant_name", "guest_name", "guest_email", "date", "time", "party_size"]
        }
    },
    {
        "name": "call_restaurant",
        "description": "Call a restaurant via AI phone call to book a table.",
        "input_schema": {
            "type": "object",
            "properties": {
                "restaurant_phone": {"type": "string"},
                "restaurant_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "date": {"type": "string"},
                "time": {"type": "string"},
                "party_size": {"type": "string"},
                "occasion": {"type": "string"},
                "special_requests": {"type": "string"}
            },
            "required": ["restaurant_phone", "restaurant_name", "guest_name", "date", "time", "party_size"]
        }
    }
]

async def find_restaurant(location: str, cuisine: str = "", budget: str = "", occasion: str = "") -> dict:
    cuis = cuisine or "any"
    bud = budget or "any"
    occ = occasion or "any"
    query = "Find 2 " + cuis + " restaurants in " + location + " good for " + occ + ". Budget: " + bud + ". Return ONLY a JSON array with whatever contact info is available, each object with: name, phone (or best guess), email (or best guess), address, price_range, cuisine, notes. Make your best effort even if some fields are unknown - use empty string for missing fields. No other text."
    try:
        response = client.messages.create(
            model="claude-haiku-4-5", max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": query}]
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            return {"restaurants": json.loads(m.group()), "location": location}
        return {"restaurants": [], "raw": text}
    except Exception as e:
        return {"restaurants": [], "error": str(e)}

async def send_reservation_email(
    restaurant_email: str, restaurant_name: str, guest_name: str, guest_email: str,
    date: str, time: str, party_size: str, guest_phone: str = "",
    occasion: str = "", special_requests: str = "", hotel_name: str = ""
) -> dict:
    if not RESEND_API_KEY:
        return {"sent": False, "error": "Resend not configured"}

    occasion_line = "Occasion: " + occasion if occasion else ""
    special_line = "Special requests: " + special_requests if special_requests else ""
    hotel_line = "Hotel: " + hotel_name if hotel_name else ""

    body = "\n".join(filter(None, [
        "Dear " + restaurant_name + ",",
        "",
        "We would like to make a reservation on behalf of our guest.",
        "",
        "RESERVATION DETAILS",
        "━━━━━━━━━━━━━━━━━━━━",
        "Guest: " + guest_name,
        "Date: " + date,
        "Time: " + time,
        "Party size: " + party_size + " people",
        occasion_line,
        special_line,
        hotel_line,
        "",
        "CONTACT",
        "━━━━━━━━━━━━━━━━━━━━",
        "Email: " + guest_email,
        "Phone: " + (guest_phone or "See email"),
        "",
        "Please confirm the reservation to " + guest_email + ".",
        "",
        "This reservation was arranged by Sasha — an AI travel concierge.",
        "",
        "Kind regards,",
        "Sasha Travel Concierge"
    ]))

    guest_body = "\n".join(filter(None, [
        "Hi " + guest_name + ",",
        "",
        "We have sent a reservation request to " + restaurant_name + ".",
        "",
        "YOUR BOOKING",
        "━━━━━━━━━━━━━━━━━━━━",
        "Restaurant: " + restaurant_name,
        "Date: " + date + " at " + time,
        "Party: " + party_size + " people",
        occasion_line,
        "",
        "They will confirm directly to " + guest_email + ".",
        "",
        "Bon appétit!",
        "Sasha Travel Concierge"
    ]))

    try:
        async with httpx.AsyncClient() as http:
            await http.post("https://api.resend.com/emails",
                headers={"Authorization": "Bearer " + RESEND_API_KEY, "Content-Type": "application/json"},
                json={"from": SASHA_FROM_EMAIL, "to": [restaurant_email], "reply_to": guest_email,
                    "subject": "Table Reservation Request - " + guest_name + " - " + date + " " + time + " - " + party_size + " guests",
                    "text": body})
            await http.post("https://api.resend.com/emails",
                headers={"Authorization": "Bearer " + RESEND_API_KEY, "Content-Type": "application/json"},
                json={"from": SASHA_FROM_EMAIL, "to": [guest_email, SASHA_NOTIFY_EMAIL],
                    "subject": "Your reservation request - " + restaurant_name,
                    "text": guest_body})
        return {"sent": True}
    except Exception as e:
        return {"sent": False, "error": str(e)}

async def call_restaurant(
    restaurant_phone: str, restaurant_name: str, guest_name: str,
    date: str, time: str, party_size: str,
    occasion: str = "", special_requests: str = ""
) -> dict:
    if not BLAND_API_KEY:
        return {"called": False, "error": "Bland not configured"}

    occ = "It is a " + occasion + "." if occasion else ""
    special = "Special requests: " + special_requests + "." if special_requests else ""

    task = "You are a travel concierge calling " + restaurant_name + " to book a table for guest " + guest_name + ". Party of " + party_size + " on " + date + " at " + time + ". " + occ + " " + special + " Confirm availability, get a booking reference or confirmation name. If that time is not available ask for the nearest available slot. Be warm and professional."

    try:
        async with httpx.AsyncClient() as http:
            r = await http.post("https://api.bland.ai/v1/calls",
                headers={"Authorization": BLAND_API_KEY, "Content-Type": "application/json"},
                json={"phone_number": restaurant_phone, "task": task, "model": "enhanced",
                    "language": "en", "voice": "nat", "max_duration": 5,
                    "wait_for_greeting": True, "record": True,
                    "metadata": {"guest": guest_name, "type": "restaurant"}}, timeout=30.0)
            return {"called": True, "call_id": r.json().get("call_id"), "status": restaurant_name + " being called now."}
    except Exception as e:
        return {"called": False, "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's restaurant specialist. Find and book restaurants anywhere in the world.
Steps: 1) Find top restaurants matching the guest's criteria 2) Send reservation email 3) Call restaurant simultaneously.
Collect: guest name, location, cuisine preference, date, time, party size, occasion, special requests, guest email.
Always ask about dietary requirements or special occasions — these matter for restaurant bookings."""

async def run_restaurant_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=RESTAURANT_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "find_restaurant": result = await find_restaurant(**inp)
                    elif block.name == "send_reservation_email": result = await send_reservation_email(**inp)
                    elif block.name == "call_restaurant": result = await call_restaurant(**inp)
                    else: result = {"error": "Unknown: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Restaurant agent error.", "tools_used": [], "messages": messages}
