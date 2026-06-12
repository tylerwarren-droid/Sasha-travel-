import os
import anthropic
import json
import re

client = anthropic.Anthropic()

CURRENCY_TOOLS = [
    {
        "name": "get_currency_info",
        "description": "Search for current exchange rates, best ways to get local currency, ATM availability and fees, card acceptance, and local tipping culture.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "Country or city being visited"},
                "home_currency": {"type": "string", "description": "Traveler's home currency, e.g. USD, GBP, AUD"}
            },
            "required": ["destination"]
        }
    }
]

async def get_currency_info(destination: str, home_currency: str = "USD") -> dict:
    query = (
        "Money and currency guide for " + home_currency + " traveler visiting " + destination + ". "
        "Return ONLY a JSON object with: local_currency, exchange_rate (1 " + home_currency + " = X local), "
        "best_exchange_method, atm_advice, card_acceptance, recommended_cards, tipping_guide, cash_needed, notes. "
        "Use current rates. No other text."
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
            return {"currency_info": json.loads(m.group()), "destination": destination}
        return {"currency_info": {}, "raw": text}
    except Exception as e:
        return {"currency_info": {}, "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's money and currency specialist. Advise on exchange rates, best ways to get local currency, ATM fees, card usage, and local tipping culture.
Always provide: current exchange rate, best exchange method, ATM advice, tipping guide, and card recommendations.
Collect: destination and traveler's home currency."""

async def run_currency_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=CURRENCY_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "get_currency_info": result = await get_currency_info(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Currency agent error.", "tools_used": [], "messages": messages}
