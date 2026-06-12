import os
import anthropic
import json
import re

client = anthropic.Anthropic()

COWORKING_TOOLS = [
    {
        "name": "find_coworking",
        "description": "Search for coworking spaces and laptop-friendly cafes for remote workers and digital nomads.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "City or neighbourhood"},
                "requirements": {"type": "string", "description": "e.g. fast wifi, 24h access, quiet, standing desks, private offices, budget, cafe vibe"}
            },
            "required": ["destination"]
        }
    }
]

async def find_coworking(destination: str, requirements: str = "") -> dict:
    reqs = " with requirements: " + requirements if requirements else ""
    query = (
        "Best coworking spaces and laptop-friendly cafes in " + destination + reqs + ". "
        "Search Workfrom, NomadList, Coworker.com, and local listings. "
        "Return ONLY a JSON array of up to 4 options, each with: "
        "name, type (coworking or cafe), wifi_speed_mbps, price_per_day_usd, "
        "hours, vibe, address, highlights (list), booking_link. "
        "Use empty string or null for unknown fields. No other text."
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
            return {"spaces": json.loads(m.group()), "destination": destination}
        return {"spaces": [], "raw": text}
    except Exception as e:
        return {"spaces": [], "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's remote work specialist. Find the best coworking spaces and laptop-friendly cafes anywhere in the world for digital nomads and remote workers.

Always include a mix of dedicated coworking spaces and cafe options. Highlight wifi speed, pricing, vibe, and whether reservations are needed.
Collect: destination, any specific requirements (fast wifi, quiet, 24h access, budget, private office, cafe vibe)."""

async def run_coworking_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-haiku-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=COWORKING_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "find_coworking": result = await find_coworking(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Coworking agent error.", "tools_used": [], "messages": messages}
