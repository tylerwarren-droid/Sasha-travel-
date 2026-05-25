import os
import httpx
import anthropic
import json
from typing import Optional

client = anthropic.Anthropic()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
BLAND_API_KEY = os.getenv("BLAND_API_KEY", "").strip()
SASHA_FROM_EMAIL = "onboarding@resend.dev"
SASHA_NOTIFY_EMAIL = "tylerwarren@gmail.com"

# ─────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────

BOOKING_TOOLS = [
    {
        "name": "find_hotel_contact",
        "description": "Search for a hotel's direct phone number and email address for reservations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hotel_name": {"type": "string"},
                "city": {"type": "string"},
                "country": {"type": "string"}
            },
            "required": ["hotel_name"]
        }
    },
    {
        "name": "send_confirmation_email",
        "description": "Send a professional booking confirmation request email to the hotel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hotel_email": {"type": "string"},
                "hotel_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "booking_platform": {"type": "string"},
                "booking_reference": {"type": "string"},
                "check_in_date": {"type": "string"},
                "check_out_date": {"type": "string"},
                "guest_email": {"type": "string"}
            },
            "required": ["hotel_email", "hotel_name", "guest_name", "booking_platform", "booking_reference", "check_in_date", "guest_email"]
        }
    },
    {
        "name": "call_hotel",
        "description": "Call the hotel via AI phone call to confirm the booking and get the hotel's internal PMS reference number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hotel_phone": {"type": "string", "description": "Hotel phone number with country code e.g. +84235394888"},
                "hotel_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "booking_platform": {"type": "string"},
                "booking_reference": {"type": "string"},
                "check_in_date": {"type": "string"},
                "check_out_date": {"type": "string"}
            },
            "required": ["hotel_phone", "hotel_name", "guest_name", "booking_platform", "booking_reference", "check_in_date"]
        }
    },
    {
        "name": "generate_phone_script",
        "description": "Generate a phone script the guest can use to call the hotel themselves.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hotel_name": {"type": "string"},
                "guest_name": {"type": "string"},
                "booking_platform": {"type": "string"},
                "booking_reference": {"type": "string"},
                "check_in_date": {"type": "string"}
            },
            "required": ["hotel_name", "guest_name", "booking_platform", "booking_reference", "check_in_date"]
        }
    }
]


# ─────────────────────────────────────────────
# TOOL EXECUTORS
# ─────────────────────────────────────────────

async def find_hotel_contact(hotel_name: str, city: str = "", country: str = "") -> dict:
    """Use Claude with web search to find hotel contact details."""
    try:
        search_client = anthropic.Anthropic()
        response = search_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": f"Find the direct reservations phone number and email for {hotel_name} {city} {country}. Return ONLY a JSON object with keys: phone, email, address. No other text."
            }]
        )
        # Extract text from response
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        # Try to parse JSON from response
        import re
        json_match = re.search(r'\{[^}]+\}', text)
        if json_match:
            return json.loads(json_match.group())
        return {"phone": "Not found", "email": "Not found", "address": f"{city}, {country}"}
    except Exception as e:
        return {"phone": "Not found", "email": "Not found", "error": str(e)}


async def send_confirmation_email(
    hotel_email: str, hotel_name: str, guest_name: str,
    booking_platform: str, booking_reference: str,
    check_in_date: str, check_out_date: str = "", guest_email: str = ""
) -> dict:
    """Send booking confirmation request email to hotel via Resend."""
    if not RESEND_API_KEY:
        return {"sent": False, "error": "Resend not configured"}

    email_body = f"""Dear {hotel_name} Reservations Team,

I am writing on behalf of our guest regarding an upcoming reservation.

BOOKING DETAILS
━━━━━━━━━━━━━━━━━━━━━━
Guest Name:        {guest_name}
Booking Platform:  {booking_platform}
Reference Number:  {booking_reference}
Check-in Date:     {check_in_date}
Check-out Date:    {check_out_date or 'Please confirm'}

REQUEST
━━━━━━━━━━━━━━━━━━━━━━
Could you please confirm:
1. Your internal hotel/PMS booking reference number
2. That the reservation is confirmed in your system
3. The room type and rate as booked

Please reply to both:
- Guest: {guest_email}
- Sasha Travel Concierge: {SASHA_NOTIFY_EMAIL}

This request was sent on behalf of your guest by Sasha — an AI travel concierge service.

Thank you for your assistance.

Kind regards,
Sasha Travel Concierge
"""

    guest_body = f"""Hi {guest_name},

We have sent a booking confirmation request to {hotel_name} on your behalf.

WHAT WE REQUESTED
━━━━━━━━━━━━━━━━━━━━━━
- Your internal hotel PMS reference number
- Confirmation the booking is in their system
- Room type and rate confirmation

YOUR BOOKING DETAILS
━━━━━━━━━━━━━━━━━━━━━━
Hotel:             {hotel_name}
Platform:          {booking_platform}
Reference:         {booking_reference}
Check-in:          {check_in_date}

The hotel will reply directly to you at {guest_email}.
We typically see responses within 2-4 hours during business hours.

Sasha Travel Concierge
"""

    try:
        async with httpx.AsyncClient() as http:
            # Email to hotel
            await http.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": SASHA_FROM_EMAIL,
                    "to": [hotel_email],
                    "reply_to": guest_email,
                    "subject": f"Booking Confirmation Request — {guest_name} — {check_in_date} — Ref: {booking_reference}",
                    "text": email_body
                }
            )
            # Confirmation to guest
            await http.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": SASHA_FROM_EMAIL,
                    "to": [guest_email, SASHA_NOTIFY_EMAIL],
                    "subject": f"We've contacted {hotel_name} about your booking",
                    "text": guest_body
                }
            )
        return {"sent": True, "hotel_email": hotel_email, "guest_email": guest_email}
    except Exception as e:
        return {"sent": False, "error": str(e)}


async def call_hotel(
    hotel_phone: str, hotel_name: str, guest_name: str,
    booking_platform: str, booking_reference: str,
    check_in_date: str, check_out_date: str = ""
) -> dict:
    """Call the hotel via Bland.ai AI phone call."""
    if not BLAND_API_KEY:
        return {"called": False, "error": "Bland.ai API key not configured. Add BLAND_API_KEY to environment variables."}

    task = f"""You are a professional travel concierge calling on behalf of a guest.

Your goal: Get the hotel's internal PMS/property reference number for this booking.

Say: "Hello, I'm calling from Sasha Travel on behalf of our guest {guest_name}. 
They have a reservation with you booked through {booking_platform} with reference number {booking_reference}, 
checking in on {check_in_date}. Could you please confirm the booking is in your system and provide 
your internal hotel reference number? We want to make sure everything is in order for our guest's arrival."

If they give you a reference number, repeat it back to confirm and thank them.
If they need to look it up, wait politely.
If they say they cannot find it, ask them to check by guest name: {guest_name}.
Always be polite, professional and brief."""

    try:
        async with httpx.AsyncClient() as http:
            response = await http.post(
                "https://api.bland.ai/v1/calls",
                headers={"Authorization": BLAND_API_KEY, "Content-Type": "application/json"},
                json={
                    "phone_number": hotel_phone,
                    "task": task,
                    "model": "enhanced",
                    "language": "en",
                    "voice": "nat",
                    "max_duration": 5,
                    "wait_for_greeting": True,
                    "record": True,
                    "answered_by_enabled": True,
                    "metadata": {
                        "guest_name": guest_name,
                        "booking_reference": booking_reference,
                        "hotel_name": hotel_name
                    }
                },
                timeout=30.0
            )
            data = response.json()
            call_id = data.get("call_id")
            return {
                "called": True,
                "call_id": call_id,
                "status": "Call initiated — the hotel is being contacted now.",
                "note": "The AI will have a real conversation with the hotel to get your PMS reference number. Results typically available within 5 minutes."
            }
    except Exception as e:
        return {"called": False, "error": str(e)}


def generate_phone_script(
    hotel_name: str, guest_name: str,
    booking_platform: str, booking_reference: str, check_in_date: str
) -> dict:
    script = f"""PHONE SCRIPT — Call {hotel_name} directly
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When they answer:
"Hello, I'd like to confirm a reservation please."

When connected to reservations:
"Hi, my name is {guest_name}. I have a reservation booked through {booking_platform} 
with reference number {booking_reference}, checking in on {check_in_date}.

Could you please confirm the booking is in your system and give me your internal 
hotel reference number? I'd like to have that for my records."

If they find it:
"Thank you so much. Could you repeat that reference number please? 
[Write it down]
Perfect, thank you. I look forward to my stay."

If they can't find it:
"Could you try searching by my name? It's {guest_name}.
[Spell it out if needed]
The booking was made through {booking_platform} — they may have it listed under that."

Tips:
- Call during business hours (9am-6pm local hotel time)
- Be patient — they may need to look it up
- Ask for the duty manager if the front desk can't help
"""
    return {"script": script, "hotel_name": hotel_name}


# ─────────────────────────────────────────────
# AGENT LOOP
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are Sasha's booking confirmation specialist. You help guests get their hotel's internal PMS reference number after booking through platforms like Booking.com, Expedia, Hotels.com, or Airbnb.

When a user gives you their booking details:
1. First find the hotel's contact details
2. Send a confirmation email to the hotel
3. Initiate an AI phone call to the hotel via Bland.ai
4. Also provide a phone script in case they want to call themselves

Always do email AND phone call simultaneously — both increase the chances of getting a response quickly.

Be efficient and professional. Collect all needed info before taking action:
- Hotel name and city/country
- Guest name
- Booking platform (Booking.com, Expedia etc)
- Booking reference number
- Check-in date
- Guest email (to receive hotel's response)"""


async def run_booking_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []

    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=BOOKING_TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    print(f"[Booking Agent] {block.name}({block.input})")
                    inp = block.input

                    if block.name == "find_hotel_contact":
                        result = await find_hotel_contact(inp.get("hotel_name"), inp.get("city", ""), inp.get("country", ""))
                    elif block.name == "send_confirmation_email":
                        result = await send_confirmation_email(**inp)
                    elif block.name == "call_hotel":
                        result = await call_hotel(**inp)
                    elif block.name == "generate_phone_script":
                        result = generate_phone_script(**inp)
                    else:
                        result = {"error": f"Unknown tool: {block.name}"}

                    tools_used.append({"tool": block.name, "input": inp, "result": result})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result)
                    })

            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            final_text = "".join(b.text for b in response.content if hasattr(b, "text"))
            return {"response": final_text, "tools_used": tools_used, "messages": messages}

        else:
            return {"response": "Something went wrong.", "tools_used": [], "messages": messages}
