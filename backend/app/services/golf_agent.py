import anthropic
import json
from typing import Any

client = anthropic.Anthropic()

GOLF_TOOLS = [
    {
        "name": "search_courses",
        "description": "Search for golf courses in Vietnam by region. Returns course name, location, par, green fees, and availability.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {"type": "string", "description": "Region in Vietnam, e.g. 'Danang', 'Hanoi', 'Ho Tram', 'Phu Quoc'"},
                "max_green_fee_usd": {"type": "number", "description": "Maximum green fee in USD"},
                "date": {"type": "string", "description": "Requested date in YYYY-MM-DD format"}
            },
            "required": ["region"]
        }
    },
    {
        "name": "get_course_details",
        "description": "Get detailed info about a specific golf course: facilities, caddy policy, dress code.",
        "input_schema": {
            "type": "object",
            "properties": {"course_name": {"type": "string"}},
            "required": ["course_name"]
        }
    },
    {
        "name": "book_tee_time",
        "description": "Book a tee time at a golf course. Returns booking confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "course_name": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM"},
                "num_players": {"type": "integer"},
                "include_caddy": {"type": "boolean"},
                "include_cart": {"type": "boolean"}
            },
            "required": ["course_name", "date", "time", "num_players"]
        }
    },
    {
        "name": "arrange_transfer",
        "description": "Arrange hotel-to-course transfer and return.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hotel_name": {"type": "string"},
                "course_name": {"type": "string"},
                "pickup_time": {"type": "string", "description": "HH:MM"},
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
                "club_brand_preference": {"type": "string", "description": "e.g. Callaway, TaylorMade"},
                "num_sets": {"type": "integer"},
                "date": {"type": "string"}
            },
            "required": ["course_name", "num_sets", "date"]
        }
    }
]


def execute_tool(tool_name: str, tool_input: dict) -> Any:
    if tool_name == "search_courses":
        region = tool_input.get("region", "").lower()
        all_courses = {
            "danang": [
                {"name": "BRG Danang Golf Resort", "par": 72, "holes": 18, "green_fee_usd": 120, "designer": "Luke Donald", "available_times": ["07:00", "08:30", "10:00", "14:00"]},
                {"name": "Montgomerie Links", "par": 72, "holes": 18, "green_fee_usd": 95, "designer": "Colin Montgomerie", "available_times": ["07:30", "09:00", "11:00"]},
                {"name": "Danang Golf Club", "par": 72, "holes": 36, "green_fee_usd": 75, "designer": "Greg Norman", "available_times": ["06:30", "08:00", "09:30", "13:00"]},
            ],
            "ho tram": [
                {"name": "The Bluffs Ho Tram Strip", "par": 71, "holes": 18, "green_fee_usd": 180, "designer": "Greg Norman", "available_times": ["07:00", "09:00", "11:00"]},
            ],
            "phu quoc": [
                {"name": "Vinpearl Golf Phu Quoc", "par": 71, "holes": 18, "green_fee_usd": 110, "designer": "IMG", "available_times": ["07:00", "08:30", "10:00"]},
            ],
            "hanoi": [
                {"name": "BRG Kings Island Golf Resort", "par": 72, "holes": 36, "green_fee_usd": 85, "designer": "Lee Trevino", "available_times": ["07:00", "09:00", "11:30"]},
                {"name": "Long Bien Golf Course", "par": 72, "holes": 18, "green_fee_usd": 55, "designer": "Local design", "available_times": ["06:30", "08:00", "10:00"]},
            ]
        }
        for key, data in all_courses.items():
            if key in region:
                max_fee = tool_input.get("max_green_fee_usd")
                if max_fee:
                    data = [c for c in data if c["green_fee_usd"] <= max_fee]
                return {"courses": data, "region": region}
        return {"courses": [], "region": region, "message": "No courses found for that region"}

    elif tool_name == "get_course_details":
        name = tool_input.get("course_name", "")
        return {
            "course_name": name,
            "facilities": ["Pro shop", "Driving range", "Putting green", "Clubhouse restaurant", "Locker rooms"],
            "caddy_policy": "Caddies are mandatory and included in the green fee. Tip $15-25 USD per round.",
            "dress_code": "Collared shirts required. No denim. Soft spikes only.",
            "club_hire": "Callaway, TaylorMade, Titleist sets from $30-50 USD per round",
            "cart_fee": "$20 USD optional",
            "notes": "Book 48h+ ahead on weekends. Early morning tee times are coolest."
        }

    elif tool_name == "book_tee_time":
        ref = f"VGF-{tool_input['course_name'][:3].upper()}-{tool_input['date'].replace('-','')}-{tool_input['time'].replace(':','')}"
        return {
            "confirmed": True,
            "booking_ref": ref,
            "course": tool_input["course_name"],
            "date": tool_input["date"],
            "time": tool_input["time"],
            "players": tool_input["num_players"],
            "caddy": tool_input.get("include_caddy", True),
            "message": "Booking confirmed. Email confirmation within 15 minutes."
        }

    elif tool_name == "arrange_transfer":
        return {
            "confirmed": True,
            "pickup": f"{tool_input['hotel_name']} at {tool_input['pickup_time']}",
            "destination": tool_input["course_name"],
            "return_transfer": "Arranged approx 4 hours after tee time",
            "vehicle": "Air-conditioned minivan",
            "cost_usd": 25 * (tool_input.get("num_passengers", 1) // 4 + 1),
            "driver_contact": "+84 90 123 4567"
        }

    elif tool_name == "arrange_equipment_hire":
        brand = tool_input.get("club_brand_preference", "Callaway")
        sets = tool_input["num_sets"]
        return {
            "confirmed": True,
            "brand": brand,
            "sets": sets,
            "total_usd": 40 * sets,
            "note": f"{brand} clubs ready at pro shop 30 mins before tee time."
        }

    return {"error": f"Unknown tool: {tool_name}"}


SYSTEM_PROMPT = """You are Sasha's golf specialist for Vietnam. Help travelers plan and book golf experiences across Vietnam's world-class courses.

Use your tools proactively — if someone asks about golf in Danang, search the courses immediately and present real options with prices and times.

Be warm, efficient, and action-oriented. Always confirm before booking: "Shall I go ahead and book that?"

Key Vietnam golf facts:
- Best season: November–April. May–October is hot and rainy.
- Book 48h+ ahead on weekends — tee times sell out fast.
- Caddies are mandatory and included in green fees. Tip $15-25 USD.
- Early morning (6:30–8am) is cooler and the best time to play.
- The Bluffs Ho Tram and BRG Danang are world-ranked courses."""


def run_golf_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []

    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=GOLF_TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"[Golf Agent] {block.name}({block.input})")
                    result = execute_tool(block.name, block.input)
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
