import os
import anthropic
import json
import re

client = anthropic.Anthropic()

AIRPORT_TRANSFER_TOOLS = [
    {
        "name": "find_transfer",
        "description": "Search for airport transfers, private cars, taxis and shuttles between two locations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Pickup location, e.g. Da Nang Airport"},
                "destination": {"type": "string", "description": "Drop-off location, e.g. hotel name or city area"},
                "date": {"type": "string", "description": "Transfer date"},
                "passengers": {"type": "string", "description": "Number of passengers"},
                "vehicle_type": {"type": "string", "description": "e.g. sedan, SUV, minivan, luxury, shuttle"}
            },
            "required": ["origin", "destination"]
        }
    }
]

async def find_transfer(origin: str, destination: str, date: str = "", passengers: str = "", vehicle_type: str = "") -> dict:
    pax = " for " + passengers + " passengers" if passengers else ""
    veh = ", vehicle: " + vehicle_type if vehicle_type else ""
    dt = " on " + date if date else ""
    query = (
        "Airport transfer from " + origin + " to " + destination + pax + veh + dt + ". "
        "Search GetTransfer, Blacklane, and local taxi/shuttle services. "
        "Return ONLY a JSON array of up to 4 options, each with: "
        "provider, vehicle_type, price_usd, duration_minutes, booking_link, notes. "
        "Use empty string for unknown fields. No other text."
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5", max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": query}]
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            return {"transfers": json.loads(m.group()), "origin": origin, "destination": destination}
        return {"transfers": [], "raw": text}
    except Exception as e:
        return {"transfers": [], "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's airport transfer specialist. Find and book airport transfers, private cars, taxis and shuttles anywhere in the world.

Always present options across price tiers (budget shuttle, standard private car, luxury/SUV) with clear pricing, duration, and booking links.
Collect: origin, destination, travel date, number of passengers, and any vehicle preference or luggage requirements."""

async def run_airport_transfer_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-haiku-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=AIRPORT_TRANSFER_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "find_transfer": result = await find_transfer(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Airport transfer agent error.", "tools_used": [], "messages": messages}
