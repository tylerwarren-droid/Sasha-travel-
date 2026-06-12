import os
import anthropic
import json
import re

client = anthropic.Anthropic()

PACKING_TOOLS = [
    {
        "name": "create_packing_list",
        "description": "Generate a smart, personalized packing list based on destination, duration, activities, weather, and traveler profile.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "Country or city being visited"},
                "duration_days": {"type": "string", "description": "Length of trip in days"},
                "activities": {"type": "string", "description": "Planned activities, e.g. beach, hiking, business, temple visits, safari"},
                "weather": {"type": "string", "description": "Expected weather, e.g. hot and humid, cold, rainy season, mixed"},
                "traveler_type": {"type": "string", "description": "Traveler profile, e.g. couple, solo female, family with kids, business traveler"}
            },
            "required": ["destination"]
        }
    }
]

async def create_packing_list(destination: str, duration_days: str = "", activities: str = "",
                               weather: str = "", traveler_type: str = "") -> dict:
    ctx_parts = [destination]
    if duration_days: ctx_parts.append(duration_days + " days")
    if activities: ctx_parts.append("activities: " + activities)
    if weather: ctx_parts.append("weather: " + weather)
    if traveler_type: ctx_parts.append("traveler: " + traveler_type)
    ctx = ", ".join(ctx_parts)

    query = (
        "Packing list for trip to " + ctx + ". "
        "Return ONLY a JSON object with categories: clothing (list), shoes (list), toiletries (list), "
        "documents (list), electronics (list), medications (list), activity_specific (list), "
        "carry_on_essentials (list), tips (list). No other text."
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
            return {"packing_list": json.loads(m.group()), "destination": destination}
        return {"packing_list": {}, "raw": text}
    except Exception as e:
        return {"packing_list": {}, "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's packing specialist. Create personalized packing lists based on destination, duration, activities, weather, and traveler profile.
Always provide a categorized list: clothing, toiletries, documents, electronics, activity-specific items, and carry-on essentials.
Tailor recommendations to the specific trip — a beach holiday needs different items than a mountain trek or business trip.
Collect: destination, trip length, planned activities, weather/season, and traveler type."""

async def run_packing_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=PACKING_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "create_packing_list": result = await create_packing_list(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Packing agent error.", "tools_used": [], "messages": messages}
