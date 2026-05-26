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

HEALTH_TOOLS = [
    {
        "name": "find_medical_provider",
        "description": "Search for doctors, clinics, hospitals, telemedicine, or pharmacies near a location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service_type": {"type": "string"},
                "location": {"type": "string"},
                "urgency": {"type": "string"},
                "specialty": {"type": "string"}
            },
            "required": ["service_type", "location"]
        }
    },
    {
        "name": "send_medical_request_email",
        "description": "Send an appointment request email to a clinic on behalf of the guest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clinic_email": {"type": "string"},
                "clinic_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "guest_email": {"type": "string"},
                "guest_phone": {"type": "string"},
                "symptoms": {"type": "string"},
                "urgency": {"type": "string"},
                "preferred_time": {"type": "string"},
                "hotel_name": {"type": "string"},
                "hotel_address": {"type": "string"}
            },
            "required": ["clinic_email", "clinic_name", "guest_name", "guest_email", "symptoms", "urgency"]
        }
    },
    {
        "name": "call_clinic",
        "description": "Call a clinic via AI phone call to book an appointment or arrange a house call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clinic_phone": {"type": "string"},
                "clinic_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "symptoms": {"type": "string"},
                "urgency": {"type": "string"},
                "hotel_name": {"type": "string"},
                "hotel_address": {"type": "string"},
                "preferred_time": {"type": "string"}
            },
            "required": ["clinic_phone", "clinic_name", "guest_name", "symptoms", "urgency"]
        }
    },
    {
        "name": "get_emergency_info",
        "description": "Get emergency contact numbers for a location.",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"]
        }
    }
]

async def find_medical_provider(service_type, location, urgency="routine", specialty="") -> dict:
    pref = specialty or "general"
    query = "Find top 2 " + service_type + " " + pref + " in " + location + " for foreign traveler needing " + urgency + " care. Return ONLY a JSON array, each with: name, phone, email, address, notes. No other text."
    try:
        response = client.messages.create(
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

async def send_medical_request_email(clinic_email, clinic_name, guest_name, guest_email, symptoms, urgency, guest_phone="", preferred_time="", hotel_name="", hotel_address="") -> dict:
    if not RESEND_API_KEY:
        return {"sent": False, "error": "Resend not configured"}
    label = {"urgent": "URGENT Same Day", "same_day": "Same Day", "routine": "Routine"}.get(urgency, urgency)
    body = "Dear " + clinic_name + ",\n\nGuest: " + guest_name + "\nEmail: " + guest_email + "\nPhone: " + (guest_phone or "N/A") + "\nPriority: " + label + "\nSymptoms: " + symptoms + "\nHotel: " + (hotel_name or "N/A") + " " + (hotel_address or "") + "\nPreferred time: " + (preferred_time or "ASAP") + "\n\nPlease contact guest directly. House call preferred if available.\n\nSasha Travel Concierge"
    guest_body = "Hi " + guest_name + ",\n\nWe sent a " + label + " appointment request to " + clinic_name + ".\nThey will reply to " + guest_email + ".\n\nIf emergency: call 115 or ask hotel front desk.\n\nSasha"
    try:
        async with httpx.AsyncClient() as http:
            await http.post("https://api.resend.com/emails",
                headers={"Authorization": "Bearer " + RESEND_API_KEY, "Content-Type": "application/json"},
                json={"from": SASHA_FROM_EMAIL, "to": [clinic_email], "reply_to": guest_email,
                    "subject": "[" + label + "] Medical Appointment Request - " + guest_name, "text": body})
            await http.post("https://api.resend.com/emails",
                headers={"Authorization": "Bearer " + RESEND_API_KEY, "Content-Type": "application/json"},
                json={"from": SASHA_FROM_EMAIL, "to": [guest_email, SASHA_NOTIFY_EMAIL],
                    "subject": "We contacted " + clinic_name + " for your appointment", "text": guest_body})
        return {"sent": True}
    except Exception as e:
        return {"sent": False, "error": str(e)}

async def call_clinic(clinic_phone, clinic_name, guest_name, symptoms, urgency, hotel_name="", hotel_address="", preferred_time="") -> dict:
    if not BLAND_API_KEY:
        return {"called": False, "error": "Bland not configured"}
    phrase = "as soon as possible today" if urgency == "urgent" else "at earliest convenience"
    task = "You are a travel concierge calling " + clinic_name + " for guest " + guest_name + " who needs help with: " + symptoms + ". Need appointment " + phrase + ". House call to " + (hotel_address or "their hotel") + " preferred. Preferred time: " + (preferred_time or "ASAP") + ". Be calm and professional."
    try:
        async with httpx.AsyncClient() as http:
            r = await http.post("https://api.bland.ai/v1/calls",
                headers={"Authorization": BLAND_API_KEY, "Content-Type": "application/json"},
                json={"phone_number": clinic_phone, "task": task, "model": "enhanced", "language": "en",
                    "voice": "nat", "max_duration": 5, "wait_for_greeting": True, "record": True,
                    "metadata": {"guest": guest_name, "type": "health"}}, timeout=30.0)
            return {"called": True, "call_id": r.json().get("call_id"), "status": "Clinic being called now."}
    except Exception as e:
        return {"called": False, "error": str(e)}

def get_emergency_info(location) -> dict:
    base = {"ambulance": "115", "police": "113", "international_sos": "+84 28 3829 8520", "tip": "Ask hotel front desk first - they have 24hr doctor-on-call."}
    loc = location.lower()
    if any(x in loc for x in ["ho chi minh", "saigon", "hcmc"]):
        base.update({"hospital": "FV Hospital +84 28 5411 3333", "clinic": "Family Medical Practice +84 28 3822 7848"})
    elif "hanoi" in loc:
        base.update({"hospital": "Vinmec Times City +84 24 3974 3556", "clinic": "Family Medical Practice +84 24 3843 0748"})
    elif any(x in loc for x in ["da nang", "danang"]):
        base.update({"hospital": "Vinmec Da Nang +84 236 3711 111", "clinic": "Family Medical Practice +84 236 3582 699"})
    return base

SYSTEM_PROMPT = """You are Sasha's health specialist. Help travelers find and book medical assistance anywhere.
Steps: 1) Find providers near their location 2) Email clinic 3) Call clinic simultaneously 4) Give emergency numbers.
Triage: URGENT (chest pain, breathing, severe injury) -> emergency numbers first. SAME_DAY (flu, stomach, minor injury). ROUTINE (checkup, dental).
Collect: guest name, location/hotel, symptoms, preferred time, guest email."""

async def run_health_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024, system=SYSTEM_PROMPT, tools=HEALTH_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "find_medical_provider": result = await find_medical_provider(**inp)
                    elif block.name == "send_medical_request_email": result = await send_medical_request_email(**inp)
                    elif block.name == "call_clinic": result = await call_clinic(**inp)
                    elif block.name == "get_emergency_info": result = get_emergency_info(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Health agent error.", "tools_used": [], "messages": messages}
