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

DOG_TOOLS = [
    {
        "name": "find_pet_service",
        "description": "Search for dog walkers, pet sitters, groomers, kennels, or vets near a location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service_type": {"type": "string"},
                "location": {"type": "string"},
                "dog_breed": {"type": "string"},
                "duration": {"type": "string"}
            },
            "required": ["service_type", "location"]
        }
    },
    {
        "name": "send_pet_booking_email",
        "description": "Send a pet service booking request email on behalf of the guest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "provider_email": {"type": "string"},
                "provider_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "guest_email": {"type": "string"},
                "guest_phone": {"type": "string"},
                "service_requested": {"type": "string"},
                "dog_name": {"type": "string"},
                "dog_breed": {"type": "string"},
                "dog_age": {"type": "string"},
                "special_notes": {"type": "string"},
                "preferred_date": {"type": "string"},
                "preferred_time": {"type": "string"},
                "duration": {"type": "string"},
                "hotel_name": {"type": "string"},
                "hotel_address": {"type": "string"}
            },
            "required": ["provider_email", "provider_name", "guest_name", "guest_email", "service_requested", "preferred_date", "preferred_time"]
        }
    },
    {
        "name": "call_pet_provider",
        "description": "Call a dog walker or pet service to confirm availability and book.",
        "input_schema": {
            "type": "object",
            "properties": {
                "provider_phone": {"type": "string"},
                "provider_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "service_requested": {"type": "string"},
                "dog_name": {"type": "string"},
                "dog_breed": {"type": "string"},
                "preferred_date": {"type": "string"},
                "preferred_time": {"type": "string"},
                "duration": {"type": "string"},
                "hotel_name": {"type": "string"},
                "hotel_address": {"type": "string"}
            },
            "required": ["provider_phone", "provider_name", "guest_name", "service_requested", "preferred_date", "preferred_time"]
        }
    },
    {
        "name": "find_expat_pet_groups",
        "description": "Find local expat groups or community resources for pet services in a city.",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"]
        }
    }
]

async def find_pet_service(service_type, location, dog_breed="", duration="") -> dict:
    try:
        response = client.messages.create(model="claude-haiku-4-5", max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": f"Top 2 {service_type} services in {location} for a traveler with a {dog_breed or \'dog\'}. Return ONLY a JSON array, each with: name, phone, email, address, price_range, notes. No other text."}])
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        m = re.search(r\'\[.*\]\', text, re.DOTALL)
        if m: return {"providers": json.loads(m.group()), "location": location}
        return {"providers": [], "raw": text}
    except Exception as e:
        return {"providers": [], "error": str(e)}

async def send_pet_booking_email(provider_email, provider_name, guest_name, guest_email, service_requested, preferred_date, preferred_time, guest_phone="", dog_name="", dog_breed="", dog_age="", special_notes="", duration="", hotel_name="", hotel_address="") -> dict:
    if not RESEND_API_KEY: return {"sent": False, "error": "Resend not configured"}
    pickup = f"{hotel_name}, {hotel_address}" if hotel_address else "To be confirmed"
    try:
        async with httpx.AsyncClient() as http:
            await http.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={"from": SASHA_FROM_EMAIL, "to": [provider_email], "reply_to": guest_email,
                    "subject": f"Pet Service Booking — {guest_name} — {preferred_date} {preferred_time}",
                    "text": f"Dear {provider_name},\n\nGuest: {guest_name}\nService: {service_requested}\nDate: {preferred_date} at {preferred_time}\nDuration: {duration or \'TBC\'}\nPickup: {pickup}\n\nDog: {dog_name or \'TBC\'} / Breed: {dog_breed or \'TBC\'} / Age: {dog_age or \'TBC\'}\nNotes: {special_notes or \'None\'}\n\nContact: {guest_email} / {guest_phone}\nPlease confirm to {guest_email}.\n\nSasha Travel Concierge"})
            await http.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={"from": SASHA_FROM_EMAIL, "to": [guest_email, SASHA_NOTIFY_EMAIL],
                    "subject": f"Pet care booked — {provider_name}",
                    "text": f"Hi {guest_name},\n\nBooked {service_requested} with {provider_name} for {preferred_date} {preferred_time}.\nPickup: {pickup}\nDog: {dog_name or \'your dog\'}\n\nThey will confirm to {guest_email}.\n\nSasha"})
        return {"sent": True}
    except Exception as e:
        return {"sent": False, "error": str(e)}

async def call_pet_provider(provider_phone, provider_name, guest_name, service_requested, preferred_date, preferred_time, dog_name="", dog_breed="", duration="", hotel_name="", hotel_address="") -> dict:
    if not BLAND_API_KEY: return {"called": False, "error": "Bland not configured"}
    pickup = f"from {hotel_name} at {hotel_address}" if hotel_address else "from their accommodation"
    try:
        async with httpx.AsyncClient() as http:
            r = await http.post("https://api.bland.ai/v1/calls",
                headers={"Authorization": BLAND_API_KEY, "Content-Type": "application/json"},
                json={"phone_number": provider_phone, "model": "enhanced", "language": "en", "voice": "nat",
                    "max_duration": 5, "wait_for_greeting": True, "record": True,
                    "task": f"You are a travel concierge booking a {service_requested} for guest {guest_name}'s {dog_breed or \'dog\'} named {dog_name or \'their dog\'} on {preferred_date} at {preferred_time} for {duration or \'about an hour\'}. Pickup {pickup}. Confirm availability and get a reference. Be warm and professional.",
                    "metadata": {"guest": guest_name, "type": "pet"}}, timeout=30.0)
            return {"called": True, "call_id": r.json().get("call_id"), "status": f"{provider_name} being called now."}
    except Exception as e:
        return {"called": False, "error": str(e)}

def find_expat_pet_groups(location: str) -> dict:
    return {
        "tip": "Search Facebook expat groups for trusted local walker recommendations.",
        "rover": "Rover.com — check coverage in this city.",
        "petbacker": "PetBacker.com — active in many cities worldwide.",
        "hotel": "Ask hotel concierge — often knows trusted local walkers.",
        "facebook": f"Search Facebook: \'{location} Expats\'  or \'{location} Dog Owners\'"
    }

SYSTEM_PROMPT = """You are Sasha's pet care specialist. Find and book dog walkers, sitters, groomers, kennels, and vets anywhere in the world.
Steps: 1) Find providers near their location 2) Email booking request 3) Call provider simultaneously 4) Suggest PetBacker/Rover/expat groups as backup.
Collect: guest name, dog name/breed/age, location/hotel, service, date/time, duration, guest email. Always ask about special needs or behavioural notes."""

async def run_dog_walking_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None: conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024, system=SYSTEM_PROMPT, tools=DOG_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "find_pet_service": result = await find_pet_service(**inp)
                    elif block.name == "send_pet_booking_email": result = await send_pet_booking_email(**inp)
                    elif block.name == "call_pet_provider": result = await call_pet_provider(**inp)
                    elif block.name == "find_expat_pet_groups": result = find_expat_pet_groups(**inp)
                    else: result = {"error": f"Unknown: {block.name}"}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Dog walking agent error.", "tools_used": [], "messages": messages}
