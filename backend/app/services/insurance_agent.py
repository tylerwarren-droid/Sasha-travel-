import os
import anthropic
import json
import re

client = anthropic.Anthropic()

INSURANCE_TOOLS = [
    {
        "name": "compare_insurance",
        "description": "Compare travel insurance plans from SafetyWing, World Nomads, and InsureMyTrip for a given trip profile.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "Destination country or region"},
                "duration_days": {"type": "string", "description": "Length of trip in days"},
                "trip_cost_usd": {"type": "string", "description": "Total prepaid trip cost in USD (for cancellation coverage)"},
                "age": {"type": "string", "description": "Traveler age or ages"},
                "activities": {"type": "string", "description": "Planned activities, e.g. scuba diving, skiing, motorbike, hiking"},
                "needs_cancellation": {"type": "string", "description": "yes or no — whether trip cancellation coverage is needed"}
            },
            "required": ["destination"]
        }
    }
]

async def compare_insurance(destination: str, duration_days: str = "", trip_cost_usd: str = "",
                             age: str = "", activities: str = "", needs_cancellation: str = "") -> dict:
    profile_parts = ["destination: " + destination]
    if duration_days: profile_parts.append("duration: " + duration_days + " days")
    if trip_cost_usd: profile_parts.append("trip cost: $" + trip_cost_usd)
    if age: profile_parts.append("age: " + age)
    if activities: profile_parts.append("activities: " + activities)
    if needs_cancellation: profile_parts.append("trip cancellation needed: " + needs_cancellation)
    profile = ", ".join(profile_parts)

    query = (
        "Compare travel insurance for: " + profile + ". "
        "Search current pricing and coverage for SafetyWing Nomad Insurance, World Nomads Explorer/Standard, and InsureMyTrip top results. "
        "Return ONLY a JSON array of 3 options, each with: "
        "provider, plan_name, price_usd, medical_limit_usd, evacuation_limit_usd, "
        "trip_cancellation (yes/no/amount), adventure_sports_covered (yes/no), "
        "best_for, link. Use empty string for unknown fields. No other text."
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5", max_tokens=700,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": query}]
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            return {"plans": json.loads(m.group()), "destination": destination}
        return {"plans": [], "raw": text}
    except Exception as e:
        return {"plans": [], "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's travel insurance specialist. Compare and recommend the best travel insurance for any trip profile. Always compare at least SafetyWing, World Nomads, and InsureMyTrip.

Always present a clear comparison table with price, medical limit, evacuation coverage, cancellation coverage, and a "best for" summary for each option.
Collect before comparing: destination, trip duration, total prepaid trip cost, traveler age(s), planned activities (especially adventure sports), and whether trip cancellation coverage is needed."""

async def run_insurance_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-haiku-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=INSURANCE_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "compare_insurance": result = await compare_insurance(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Insurance agent error.", "tools_used": [], "messages": messages}
