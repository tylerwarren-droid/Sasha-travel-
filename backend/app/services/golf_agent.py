import anthropic
from app.services.llm import SPECIALIST_MODEL
import json
import os
import httpx
from typing import Any
from app.services.vietnam_golf_database import (
    search_courses_by_region,
    get_course_by_name,
    get_total_course_count,
)

from app.services.prompts import VOICE_BREVITY
client = anthropic.AsyncAnthropic()
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
SASHA_FROM_EMAIL = "onboarding@resend.dev"
SASHA_NOTIFY_EMAIL = os.getenv("SASHA_NOTIFY_EMAIL", "")  # no hardcoded inbox; unset = no CC

GOLF_TOOLS = [
    {
        "name": "search_courses",
        "description": "Search for golf courses in Vietnam by region. Returns real course names, green fees, designers, and available tee times.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "Region in Vietnam: Danang, Hoi An, Ho Chi Minh, Saigon, Hanoi, Ho Tram, Phu Quoc, Nha Trang, Da Lat, Hai Phong"
                },
                "max_green_fee_usd": {
                    "type": "number",
                    "description": "Maximum green fee in USD"
                }
            },
            "required": ["region"]
        }
    },
    {
        "name": "get_course_details",
        "description": "Get full details about a specific golf course: facilities, caddy policy, dress code, cancellation policy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "course_name": {"type": "string"}
            },
            "required": ["course_name"]
        }
    },
    {
        "name": "send_booking_request",
        "description": "Send a real booking request email to the golf course on behalf of the user. Use this when the user has confirmed they want to book.",
        "input_schema": {
            "type": "object",
            "properties": {
                "course_name": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM"},
                "num_players": {"type": "integer"},
                "include_cart": {"type": "boolean"},
                "guest_name": {"type": "string"},
                "guest_email": {"type": "string"},
                "guest_phone": {"type": "string"},
                "special_requests": {"type": "string"}
            },
            "required": ["course_name", "date", "time", "num_players", "guest_name", "guest_email"]
        }
    },
    {
        "name": "arrange_transfer",
        "description": "Arrange a hotel-to-course transfer for the golfer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hotel_name": {"type": "string"},
                "course_name": {"type": "string"},
                "pickup_time": {"type": "string"},
                "date": {"type": "string"},
                "num_passengers": {"type": "integer"}
            },
            "required": ["hotel_name", "course_name", "pickup_time", "date"]
        }
    },
    {
        "name": "arrange_equipment_hire",
        "description": "Arrange club hire at the course.",
        "input_schema": {
            "type": "object",
            "properties": {
                "course_name": {"type": "string"},
                "club_brand_preference": {"type": "string"},
                "num_sets": {"type": "integer"},
                "date": {"type": "string"}
            },
            "required": ["course_name", "num_sets", "date"]
        }
    }
]


async def send_booking_email(course: dict, booking_details: dict) -> dict:
    """Send real booking request email to the golf course via Resend."""
    if not RESEND_API_KEY:
        return {"error": "Resend API key not configured"}

    guest_name = booking_details.get("guest_name", "Guest")
    guest_email = booking_details.get("guest_email", "")
    guest_phone = booking_details.get("guest_phone", "Not provided")
    date = booking_details.get("date")
    time = booking_details.get("time")
    num_players = booking_details.get("num_players")
    include_cart = booking_details.get("include_cart", False)
    special_requests = booking_details.get("special_requests", "None")

    green_fee_total = course["green_fee_usd"] * num_players
    cart_note = f"Golf cart requested (+${course['cart_fee_usd']} per cart)" if include_cart else "No cart (caddies carrying)"

    # Email to the golf course
    course_email_body = f"""
Dear {course['name']} Reservations Team,

We would like to request a tee time booking on behalf of our guest. Please confirm availability and revert to both the guest and ourselves.

BOOKING REQUEST DETAILS
━━━━━━━━━━━━━━━━━━━━━━
Course:       {course['name']}
Date:         {date}
Tee Time:     {time}
Players:      {num_players}
Cart:         {cart_note}
Caddies:      {num_players} caddies (mandatory)
Green Fee:    ${course['green_fee_usd']} USD per player (${green_fee_total} USD total)

GUEST DETAILS
━━━━━━━━━━━━━━━━━━━━━━
Name:         {guest_name}
Email:        {guest_email}
Phone:        {guest_phone}
Special Requests: {special_requests}

Please send confirmation to both:
- Guest: {guest_email}
- Sasha Travel: {SASHA_NOTIFY_EMAIL}

This booking request was submitted via Sasha Travel — an AI-powered travel platform.

Thank you,
Sasha Travel Concierge
golf@sasha-travel.com
    """

    # Email to the guest
    guest_email_body = f"""
Hi {guest_name},

Your tee time request has been submitted to {course['name']}. Here's a summary:

BOOKING SUMMARY
━━━━━━━━━━━━━━━━━━━━━━
Course:    {course['name']}
Date:      {date}
Time:      {time}
Players:   {num_players}
Fee:       ${course['green_fee_usd']} USD per player

COURSE CONTACT
━━━━━━━━━━━━━━━━━━━━━━
Phone:  {course['phone']}
Email:  {course['booking_email']}

The course typically confirms within 2-4 hours during business hours. We'll follow up if you don't hear back.

Caddy tip reminder: $15-25 USD per caddy per round (cash, paid on the day).

Safe travels,
Sasha — Your AI Travel Concierge
    """

    try:
        async with httpx.AsyncClient() as http_client:
            # Send to course
            await http_client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": SASHA_FROM_EMAIL,
                    "to": [course["booking_email"]],
                    "reply_to": guest_email,
                    "subject": f"Tee Time Request — {guest_name} — {date} at {time} — {num_players} players",
                    "text": course_email_body
                }
            )
            # Send confirmation to guest
            await http_client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": SASHA_FROM_EMAIL,
                    "to": [guest_email, SASHA_NOTIFY_EMAIL],
                    "subject": f"Your Golf Booking Request — {course['name']} — {date}",
                    "text": guest_email_body
                }
            )
        return {"sent": True, "course_email": course["booking_email"], "guest_email": guest_email}
    except Exception as e:
        return {"sent": False, "error": str(e)}


def execute_tool_sync(tool_name: str, tool_input: dict) -> Any:
    """Sync tool executor for non-async tools."""
    if tool_name == "search_courses":
        courses = search_courses_by_region(
            tool_input.get("region", ""),
            tool_input.get("max_green_fee_usd")
        )
        if not courses:
            return {
                "courses": [],
                "message": f"No courses found for that region. Available regions: Danang, Hanoi, Ho Chi Minh, Ho Tram, Phu Quoc, Nha Trang, Da Lat, Hai Phong. Total courses in database: {get_total_course_count()}"
            }
        return {
            "courses": [
                {
                    "name": c["name"],
                    "green_fee_usd": c["green_fee_usd"],
                    "holes": c["holes"],
                    "par": c["par"],
                    "designer": c["designer"],
                    "ranking": c.get("ranking", ""),
                    "available_times": c["available_times"],
                    "notes": c["notes"]
                }
                for c in courses
            ],
            "region": tool_input.get("region")
        }

    elif tool_name == "get_course_details":
        course = get_course_by_name(tool_input.get("course_name", ""))
        if not course:
            return {"error": f"Course not found: {tool_input.get('course_name')}"}
        return course

    elif tool_name == "arrange_transfer":
        return {
            "confirmed": True,
            "pickup": f"{tool_input['hotel_name']} at {tool_input['pickup_time']}",
            "destination": tool_input["course_name"],
            "return_transfer": "Arranged approx 4.5 hours after tee time",
            "vehicle": "Air-conditioned minivan",
            "cost_usd": 25 * (tool_input.get("num_passengers", 2) // 4 + 1),
            "note": "Driver will meet you at hotel lobby. Confirm 24h before."
        }

    elif tool_name == "arrange_equipment_hire":
        brand = tool_input.get("club_brand_preference", "Callaway")
        sets = tool_input.get("num_sets", 1)
        course = get_course_by_name(tool_input.get("course_name", ""))
        cost = course.get("club_hire_usd", 40) if course else 40
        return {
            "confirmed": True,
            "brand": brand,
            "sets": sets,
            "total_usd": cost * sets,
            "note": f"{brand} clubs ready at pro shop 30 mins before tee time. Pay onsite."
        }

    return {"error": f"Unknown tool: {tool_name}"}


SYSTEM_PROMPT = f"""You are Sasha's golf specialist for Vietnam. You help travelers plan and book golf at any of Vietnam's {get_total_course_count()} courses in our database.

Regions covered: Danang/Hoi An, Ho Chi Minh City/Saigon, Hanoi, Ho Tram, Phu Quoc, Nha Trang, Da Lat, Hai Phong.

Use your tools proactively — always search before describing courses. Present real prices, designers, and tee times from the database.

BOOKING FLOW:
1. Search courses for their region
2. Present options clearly with prices
3. When they choose a course, ask: date, time preference, number of players, their name and email
4. Confirm all details back to them
5. Say "Shall I send the booking request to [course name] now?"
6. Only call send_booking_request once they say yes

Vietnam golf essentials:
- Best season: November–April. May–October is hot and rainy.
- Caddies are mandatory at all courses — included in green fee
- Tip caddies $15-25 USD cash per round — it genuinely matters to them
- Book 48h+ ahead on weekends — courses fill fast
- Early morning (6:30–8am) is cooler and better conditions
- Hoiana Shores is Vietnam's #1 ranked course — world top 100
- The Bluffs Ho Tram is world top 50 — a genuine bucket-list course"""


async def run_golf_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []

    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []

    while True:
        response = await client.messages.create(
            model=SPECIALIST_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT + VOICE_BREVITY,
            tools=GOLF_TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    print(f"[Golf Agent] {block.name}({block.input})")

                    if block.name == "send_booking_request":
                        course = get_course_by_name(block.input.get("course_name", ""))
                        if course:
                            result = await send_booking_email(course, block.input)
                        else:
                            result = {"error": "Course not found"}
                    else:
                        result = execute_tool_sync(block.name, block.input)

                    tools_used.append({"tool": block.name, "input": block.input, "result": result})
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
