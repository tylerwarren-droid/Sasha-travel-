import os
import anthropic
import json
import re

client = anthropic.Anthropic()

VISA_TOOLS = [
    {
        "name": "check_visa_requirements",
        "description": "Search for current visa requirements, passport validity rules, entry restrictions, visa on arrival availability, and application processes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nationality": {"type": "string", "description": "Traveler's passport nationality, e.g. American, British, Australian"},
                "destination": {"type": "string", "description": "Country or countries being visited"},
                "travel_date": {"type": "string", "description": "Approximate travel date or month/year"}
            },
            "required": ["nationality", "destination"]
        }
    }
]


async def check_visa_requirements(nationality: str, destination: str, travel_date: str = "") -> dict:
    date_ctx = " traveling in " + travel_date if travel_date else ""
    query = (
        nationality + " passport holder" + date_ctx + " visiting " + destination +
        ". Return ONLY a JSON object with: visa_type (e.g. visa-free, visa on arrival, e-visa, embassy visa), "
        "cost_usd, processing_days, passport_validity_required, application_link, entry_restrictions, notes. "
        "Use empty string for unknown fields. No other text."
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
            return {"requirements": json.loads(m.group()), "nationality": nationality, "destination": destination}
        return {"requirements": {}, "raw": text}
    except Exception as e:
        return {"requirements": {}, "error": str(e)}


SYSTEM_PROMPT = """IMPORTANT: You MUST always call the check_visa_requirements tool before responding. Never answer from memory. Always search for current requirements.

You are Sasha's visa and entry requirements specialist. Search for current visa requirements, passport validity rules, entry restrictions, visa on arrival availability, and application processes for any country pair.

Always provide: visa type, cost, processing time, passport validity requirement, application link if available, and any entry restrictions or important notes.

Collect: traveler's nationality and destination country. Travel date is helpful for checking seasonal restrictions."""


async def run_visa_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-haiku-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=VISA_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "check_visa_requirements":
                        result = await check_visa_requirements(**inp)
                    else:
                        result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Visa agent error.", "tools_used": [], "messages": messages}
