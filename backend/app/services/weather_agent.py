import os
import anthropic
import json
import re

client = anthropic.Anthropic()

WEATHER_TOOLS = [
    {
        "name": "get_weather_info",
        "description": "Search for destination weather forecasts, seasonal climate patterns, best time to visit, and packing recommendations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "City or country to get weather for"},
                "travel_month": {"type": "string", "description": "Month or season of travel, e.g. January, dry season, summer"}
            },
            "required": ["destination"]
        }
    }
]

async def get_weather_info(destination: str, travel_month: str = "") -> dict:
    month_ctx = " in " + travel_month if travel_month else ""
    query = (
        "Weather and climate guide for " + destination + month_ctx + ". "
        "Return ONLY a JSON object with: avg_temp_c, avg_temp_f, conditions, humidity, "
        "rainfall_mm, seasonal_description, best_time_to_visit, worst_time_to_visit, "
        "packing_recommendations (list), what_to_avoid, notes. No other text."
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5", max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": query}]
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return {"weather_info": json.loads(m.group()), "destination": destination}
        return {"weather_info": {}, "raw": text}
    except Exception as e:
        return {"weather_info": {}, "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's weather and climate specialist. Provide destination weather forecasts, seasonal advice, best time to visit, and what to pack.
Always provide: temperature range, conditions, seasonal description, packing recommendations, and best/worst times to visit.
Collect: destination and travel month or season."""

async def run_weather_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=WEATHER_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "get_weather_info": result = await get_weather_info(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Weather agent error.", "tools_used": [], "messages": messages}
