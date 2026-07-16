import os
import httpx
import anthropic
from app.services.llm import SPECIALIST_MODEL
import json
import re

from app.services.prompts import VOICE_BREVITY
client = anthropic.AsyncAnthropic()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
BLAND_API_KEY = os.getenv("BLAND_API_KEY", "").strip()
SASHA_FROM_EMAIL = "onboarding@resend.dev"
SASHA_NOTIFY_EMAIL = os.getenv("SASHA_NOTIFY_EMAIL", "")  # no hardcoded inbox; unset = no CC

BEAUTY_TOOLS = [
    {
        "name": "find_beauty_provider",
        "description": "Search for spas, massage, nail salons, hair, or mobile beauty near a location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service_type": {"type": "string"},
                "location": {"type": "string"},
                "preference": {"type": "string"},
                "budget": {"type": "string"}
            },
            "required": ["service_type", "location"]
        }
    },
    {
        "name": "send_beauty_booking_email",
        "description": "Send a booking request email to a spa or beauty provider.",
        "input_schema": {
            "type": "object",
            "properties": {
                "provider_email": {"type": "string"},
                "provider_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "guest_email": {"type": "string"},
                "guest_phone": {"type": "string"},
                "service_requested": {"type": "string"},
                "preferred_date": {"type": "string"},
                "preferred_time": {"type": "string"},
                "duration_minutes": {"type": "string"},
                "num_guests": {"type": "string"},
                "hotel_name": {"type": "string"},
                "hotel_address": {"type": "string"},
                "special_requests": {"type": "string"}
            },
            "required": ["provider_email", "provider_name", "guest_name", "guest_email", "service_requested", "preferred_date", "preferred_time"]
        }
    },
    {
        "name": "call_beauty_provider",
        "description": "Call a spa or beauty provider to book an appointment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "provider_phone": {"type": "string"},
                "provider_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "service_requested": {"type": "string"},
                "preferred_date": {"type": "string"},
                "preferred_time": {"type": "string"},
                "num_guests": {"type": "string"},
                "hotel_name": {"type": "string"},
                "hotel_address": {"type": "string"},
                "in_room_requested": {"type": "boolean"}
            },
            "required": ["provider_phone", "provider_name", "guest_name", "service_requested", "preferred_date", "preferred_time"]
        }
    }
]

async def find_beauty_provider(service_type, location, preference="", budget="") -> dict:
    pref = preference or "any"
    bud = budget or "any"
    query = "Top 2 " + service_type + " providers in " + location + " for a traveler. Preference: " + pref + ". Budget: " + bud + ". Return ONLY a JSON array, each with: name, phone, email, address, price_range, notes. No other text."
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5", max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": query}]
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            return {"providers": json.loads(m.group()), "location": location}
        return {"providers": [], "raw": text}
    except Exception as e:
        return {"providers": [], "error": str(e)}

async def send_beauty_booking_email(provider_email, provider_name, guest_name, guest_email, service_requested, preferred_date, preferred_time, guest_phone="", duration_minutes="", num_guests="1", hotel_name="", hotel_address="", special_requests="") -> dict:
    if not RESEND_API_KEY:
        return {"sent": False, "error": "Resend not configured"}
    duration = duration_minutes or "standard"
    special = special_requests or "none"
    location = ("IN-ROOM at " + hotel_name + ", " + hotel_address) if hotel_address else "At your premises"
    body = "\n".join([
        "Dear " + provider_name + ",",
        "",
        "Guest: " + guest_name,
        "Service: " + service_requested,
        "Date: " + preferred_date + " at " + preferred_time,
        "Duration: " + duration + " mins",
        "Guests: " + num_guests,
        "Location: " + location,
        "Special requests: " + special,
        "Contact: " + guest_email + " / " + (guest_phone or "N/A"),
        "",
        "Please confirm to " + guest_email + ".",
        "",
        "Sasha Travel Concierge"
    ])
    guest_body = "\n".join([
        "Hi " + guest_name + ",",
        "",
        "Booked " + service_requested + " at " + provider_name + " for " + preferred_date + " " + preferred_time + ".",
        "Location: " + location,
        "",
        "They will confirm to " + guest_email + ".",
        "",
        "Enjoy! Sasha"
    ])
    try:
        async with httpx.AsyncClient() as http:
            await http.post("https://api.resend.com/emails",
                headers={"Authorization": "Bearer " + RESEND_API_KEY, "Content-Type": "application/json"},
                json={"from": SASHA_FROM_EMAIL, "to": [provider_email], "reply_to": guest_email,
                    "subject": "Booking Request - " + service_requested + " - " + guest_name + " - " + preferred_date, "text": body})
            await http.post("https://api.resend.com/emails",
                headers={"Authorization": "Bearer " + RESEND_API_KEY, "Content-Type": "application/json"},
                json={"from": SASHA_FROM_EMAIL, "to": [guest_email, SASHA_NOTIFY_EMAIL],
                    "subject": "Your " + service_requested + " booking - " + provider_name, "text": guest_body})
        return {"sent": True}
    except Exception as e:
        return {"sent": False, "error": str(e)}

async def call_beauty_provider(provider_phone, provider_name, guest_name, service_requested, preferred_date, preferred_time, num_guests="1", hotel_name="", hotel_address="", in_room_requested=False) -> dict:
    if not BLAND_API_KEY:
        return {"called": False, "error": "Bland not configured"}
    location = ("at their hotel (" + hotel_address + ")") if in_room_requested and hotel_address else "at your location"
    task = "You are a travel concierge booking a " + service_requested + " for " + num_guests + " guest(s) named " + guest_name + " on " + preferred_date + " at " + preferred_time + " " + location + ". Confirm availability and get a booking reference. If unavailable ask for nearest slot. Be warm and professional."
    try:
        async with httpx.AsyncClient() as http:
            r = await http.post("https://api.bland.ai/v1/calls",
                headers={"Authorization": BLAND_API_KEY, "Content-Type": "application/json"},
                json={"phone_number": provider_phone, "task": task, "model": "enhanced", "language": "en",
                    "voice": "nat", "max_duration": 5, "wait_for_greeting": True, "record": True,
                    "metadata": {"guest": guest_name, "type": "beauty"}}, timeout=30.0)
            return {"called": True, "call_id": r.json().get("call_id"), "status": provider_name + " being called now."}
    except Exception as e:
        return {"called": False, "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's beauty and wellness specialist. Book spas, massages, nails, facials, hair, mobile beauty anywhere in the world.
Steps: 1) Find providers near their location 2) Email booking request 3) Call provider simultaneously.
Always ask if they want in-room/hotel service.
Collect: guest name, location/hotel, service wanted, date/time, number of people, guest email."""

async def run_beauty_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = await client.messages.create(model=SPECIALIST_MODEL, max_tokens=1024, system=SYSTEM_PROMPT + VOICE_BREVITY, tools=BEAUTY_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "find_beauty_provider": result = await find_beauty_provider(**inp)
                    elif block.name == "send_beauty_booking_email": result = await send_beauty_booking_email(**inp)
                    elif block.name == "call_beauty_provider": result = await call_beauty_provider(**inp)
                    else: result = {"error": "Unknown: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Beauty agent error.", "tools_used": [], "messages": messages}
