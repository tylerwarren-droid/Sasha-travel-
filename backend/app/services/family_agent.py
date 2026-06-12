import os
import anthropic
import json
import re

client = anthropic.Anthropic()

FAMILY_TOOLS = [
    {
        "name": "get_family_info",
        "description": "Search for kid-friendly hotels, family restaurants, age-appropriate activities, and practical travel tips for families with children.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "City or country being visited"},
                "children_ages": {"type": "string", "description": "Ages of children, e.g. baby 6 months, toddler 2, kids 5 and 8"},
                "query_type": {"type": "string", "description": "What to search for: hotels, restaurants, activities, tips, or all"}
            },
            "required": ["destination"]
        }
    }
]

async def get_family_info(destination: str, children_ages: str = "", query_type: str = "all") -> dict:
    age_ctx = " with children aged " + children_ages if children_ages else " with young children"
    query = (
        "Family travel guide for " + destination + age_ctx + " — focus: " + query_type + ". "
        "Return ONLY a JSON object with: kid_friendly_hotels (list of {name, why_good_for_families, price_range}), "
        "family_restaurants (list of {name, cuisine, why_kids_love_it}), "
        "age_appropriate_activities (list of {activity, suitable_ages, notes}), "
        "practical_tips (list), baby_toddler_essentials (list), "
        "safety_notes (list), stroller_accessibility, notes. No other text."
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
            return {"family_info": json.loads(m.group()), "destination": destination}
        return {"family_info": {}, "raw": text}
    except Exception as e:
        return {"family_info": {}, "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's family travel specialist. Help families travel with children of all ages — from babies to teenagers.
Recommend kid-friendly hotels, family restaurants, and age-appropriate activities. Provide practical advice for traveling with babies, toddlers, and children.
Always consider stroller accessibility, nap schedules, food pickiness, and safety.
Collect: destination, children's ages, and what kind of help they need (hotels, activities, restaurants, or general tips)."""

async def run_family_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=FAMILY_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "get_family_info": result = await get_family_info(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Family agent error.", "tools_used": [], "messages": messages}
