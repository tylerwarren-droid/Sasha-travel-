import os
import anthropic
import json
import re

client = anthropic.Anthropic()

LOYALTY_TOOLS = [
    {
        "name": "get_loyalty_advice",
        "description": "Research and compare airline and hotel loyalty programs, status requirements, points values, and earning strategies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "airlines_used": {"type": "string", "description": "Airlines the traveler typically flies, e.g. United, Singapore Airlines, Vietnam Airlines"},
                "hotels_used": {"type": "string", "description": "Hotel brands typically stayed at, e.g. Marriott, Hilton, IHG"},
                "home_airport": {"type": "string", "description": "Home airport code or city, e.g. SFO, London Heathrow"},
                "travel_frequency": {"type": "string", "description": "How often they travel, e.g. 4 trips/year, weekly business travel"},
                "goals": {"type": "string", "description": "What they want to achieve, e.g. free flights, hotel upgrades, lounge access, status"}
            },
            "required": []
        }
    }
]

async def get_loyalty_advice(airlines_used: str = "", hotels_used: str = "", home_airport: str = "",
                              travel_frequency: str = "", goals: str = "") -> dict:
    profile_parts = []
    if airlines_used: profile_parts.append("airlines: " + airlines_used)
    if hotels_used: profile_parts.append("hotels: " + hotels_used)
    if home_airport: profile_parts.append("home airport: " + home_airport)
    if travel_frequency: profile_parts.append("travel frequency: " + travel_frequency)
    if goals: profile_parts.append("goals: " + goals)
    profile = ", ".join(profile_parts) if profile_parts else "general traveler"

    query = (
        "Travel loyalty program advice for: " + profile + ". "
        "Search current program benefits, transfer partners, status tier requirements, and points valuations. "
        "Return ONLY a JSON object with: "
        "recommended_airline_programs (list of {program, why, status_to_target, earning_tips}), "
        "recommended_hotel_programs (list of {program, why, status_to_target, earning_tips}), "
        "transfer_partners (list of useful credit card to airline/hotel transfer options), "
        "quick_wins (list of actionable tips to earn points or status faster), "
        "notes. No other text."
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5", max_tokens=700,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": query}]
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return {"advice": json.loads(m.group())}
        return {"advice": {}, "raw": text}
    except Exception as e:
        return {"advice": {}, "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's travel loyalty program specialist. Advise on the best airline and hotel loyalty programs based on travel patterns, recommend which programs to join, how to earn status faster, and how to maximize points value.

Always include: recommended programs with reasoning, status tiers worth targeting, transfer partner opportunities, and quick wins to accelerate earning.
Collect: which airlines and hotels they use, home airport, how often they travel, and what they want to achieve (free flights, upgrades, lounge access, status)."""

async def run_loyalty_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-haiku-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=LOYALTY_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "get_loyalty_advice": result = await get_loyalty_advice(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Loyalty agent error.", "tools_used": [], "messages": messages}
