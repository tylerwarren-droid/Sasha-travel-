import os
import anthropic
import json
import re

client = anthropic.Anthropic()

API_ASSIMILATION_TOOLS = [
    {
        "name": "discover_apis",
        "description": "Search for and rank the best APIs for a given travel vertical, region, and use case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "vertical": {"type": "string", "description": "e.g. flights, hotels, transfers, experiences, insurance, golf, restaurants"},
                "region": {"type": "string", "description": "e.g. global, Southeast Asia, Europe, US"},
                "use_case": {"type": "string", "description": "e.g. booking, search only, content/data, white label"}
            },
            "required": ["vertical"]
        }
    },
    {
        "name": "generate_integration_code",
        "description": "Fetch API documentation and generate a working code template for authentication and a sample search or booking call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "api_name": {"type": "string", "description": "Name of the API to generate code for, e.g. Duffel, Amadeus, Viator"},
                "language": {"type": "string", "description": "python or typescript"}
            },
            "required": ["api_name", "language"]
        }
    }
]


async def discover_apis(vertical: str, region: str = "global", use_case: str = "") -> dict:
    region_ctx = " in " + region if region and region != "global" else " (global coverage)"
    use_ctx = " for " + use_case if use_case else ""
    query = (
        "Best travel APIs for " + vertical + region_ctx + use_ctx + " in 2025. "
        "Include established providers and newer alternatives. "
        "Return ONLY a JSON array of up to 5 APIs ranked by fit, each with: "
        "name, provider, coverage, pricing_model, sandbox_available (yes/no), "
        "approval_difficulty (easy/medium/hard), approval_notes, "
        "documentation_url, signup_url, best_for. "
        "Use empty string for unknown fields. No other text."
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5", max_tokens=800,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": query}]
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            return {"apis": json.loads(m.group()), "vertical": vertical, "region": region}
        return {"apis": [], "raw": text}
    except Exception as e:
        return {"apis": [], "error": str(e)}


async def generate_integration_code(api_name: str, language: str = "python") -> dict:
    query = (
        api_name + " API official documentation: authentication method, base URL, "
        "and a sample search or booking request. "
        "Return ONLY a JSON object with: "
        "auth_method, base_url, "
        "code_template (a working " + language + " code snippet for auth + one sample API call "
        "that follows the async conductor agent pattern used in FastAPI backends), "
        "env_vars_needed (list of environment variable names), "
        "docs_url, notes. No other text."
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5", max_tokens=1200,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": query}]
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return {"integration": json.loads(m.group()), "api_name": api_name, "language": language}
        return {"integration": {}, "raw": text}
    except Exception as e:
        return {"integration": {}, "error": str(e)}


SYSTEM_PROMPT = """You are Sasha's API assimilation specialist. Help travel companies find and integrate the best APIs for their specific needs. You know the travel API landscape deeply — flights, hotels, transfers, experiences, insurance, golf, restaurants, and more.

You evaluate APIs on: coverage, pricing model, ease of approval, sandbox availability, documentation quality, and fit for the use case.

WORKFLOW:
1. Use discover_apis to find and rank the top options for the requested vertical and region.
2. Present a clear comparison: coverage, pricing, approval difficulty, and signup link for each.
3. If the user wants to integrate a specific API, use generate_integration_code to fetch docs and produce a working code template.
4. Code templates should follow the async FastAPI + conductor agent pattern already used in this codebase.

Always highlight: which APIs have instant/easy approval (good for getting started fast) vs. which require business verification. Note sandbox availability — that determines how quickly they can test."""


async def run_api_assimilation_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-haiku-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=API_ASSIMILATION_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "discover_apis":
                        result = await discover_apis(**inp)
                    elif block.name == "generate_integration_code":
                        result = await generate_integration_code(**inp)
                    else:
                        result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "API assimilation agent error.", "tools_used": [], "messages": messages}
