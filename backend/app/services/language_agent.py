import os
import anthropic
import json
import re

client = anthropic.Anthropic()

LANGUAGE_TOOLS = [
    {
        "name": "get_language_info",
        "description": "Search for key local phrases with pronunciation, cultural dos and don'ts, dining etiquette, bargaining customs, and dress codes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "Country or city to get language and culture info for"},
                "context": {"type": "string", "description": "Context or situation, e.g. restaurant, market, temple, business, general"}
            },
            "required": ["destination"]
        }
    }
]

async def get_language_info(destination: str, context: str = "general") -> dict:
    query = (
        "Language and cultural etiquette guide for " + destination + " — context: " + context + ". "
        "Return ONLY a JSON object with: language, essential_phrases (list of {phrase, pronunciation, meaning}), "
        "cultural_dos (list), cultural_donts (list), dining_etiquette, bargaining_tips, "
        "dress_code, religious_customs, taboos, useful_gestures, notes. No other text."
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
            return {"language_info": json.loads(m.group()), "destination": destination}
        return {"language_info": {}, "raw": text}
    except Exception as e:
        return {"language_info": {}, "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's language and cultural etiquette specialist. Provide key local phrases, cultural dos and don'ts, dining etiquette, bargaining customs, and dress codes.
Always provide: essential phrases with pronunciation, cultural rules, dining etiquette, dress code, and taboos to avoid.
Make phrases practical and phonetic — traveler-friendly, not academic.
Collect: destination and context (restaurant, market, temple, business, etc.)."""

async def run_language_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=LANGUAGE_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "get_language_info": result = await get_language_info(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Language agent error.", "tools_used": [], "messages": messages}
