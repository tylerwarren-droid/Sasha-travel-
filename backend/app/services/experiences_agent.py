import os
import anthropic
import json
import re

client = anthropic.Anthropic()

EXPERIENCES_TOOLS = [
    {
        "name": "find_experiences",
        "description": "Search for local experiences, tours, cooking classes, cultural activities and excursions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "City or region"},
                "experience_type": {"type": "string", "description": "e.g. cooking class, food tour, cultural tour, day trip, adventure, nightlife"},
                "date": {"type": "string", "description": "Date or date range"},
                "participants": {"type": "string", "description": "Number of people"}
            },
            "required": ["destination"]
        }
    }
]

async def find_experiences(destination: str, experience_type: str = "", date: str = "", participants: str = "") -> dict:
    exp = experience_type or "tours and experiences"
    pax = " for " + participants + " people" if participants else ""
    dt = " on " + date if date else ""
    query = (
        "Top 3 " + exp + " in " + destination + pax + dt + ". "
        "Search Viator, GetYourGuide, Airbnb Experiences, and local operators. "
        "Return ONLY a JSON array of 3 options, each with: "
        "name, provider, price_per_person_usd, duration, highlights (list), booking_link, notes. "
        "Use empty string for unknown fields. No other text."
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
            return {"experiences": json.loads(m.group()), "destination": destination}
        return {"experiences": [], "raw": text}
    except Exception as e:
        return {"experiences": [], "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's local experiences specialist. Find unique local experiences, tours, cooking classes, cultural activities and excursions anywhere in the world.

Always return 3 options across different styles (e.g. group tour, private tour, hands-on class). Include price per person, duration, what makes each special, and a direct booking link.
Collect: destination, type of experience they want, date, and number of participants."""

async def run_experiences_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-haiku-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=EXPERIENCES_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "find_experiences": result = await find_experiences(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Experiences agent error.", "tools_used": [], "messages": messages}
