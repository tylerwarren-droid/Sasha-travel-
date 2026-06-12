import os
import anthropic
import json
import re

client = anthropic.Anthropic()

EMERGENCY_TOOLS = [
    {
        "name": "get_emergency_info",
        "description": "Search for embassy contacts, local emergency numbers, nearest hospitals, and crisis management steps for travelers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "Country or city where the emergency is occurring"},
                "emergency_type": {"type": "string", "description": "Type of emergency: lost_passport, medical, robbery, accident, arrest, natural_disaster, or general"}
            },
            "required": ["destination", "emergency_type"]
        }
    }
]

async def get_emergency_info(destination: str, emergency_type: str) -> dict:
    query = (
        "Emergency travel guide for " + emergency_type + " in " + destination + " for foreign tourist. "
        "Return ONLY a JSON object with: local_emergency_number, police_number, ambulance_number, "
        "fire_number, nearest_hospital, embassy_contacts (list with country and phone), "
        "insurance_claim_steps (list), immediate_action_plan (list of steps), "
        "useful_local_phrases, notes. No other text."
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
            return {"emergency_info": json.loads(m.group()), "destination": destination, "type": emergency_type}
        return {"emergency_info": {}, "raw": text}
    except Exception as e:
        return {"emergency_info": {}, "error": str(e)}

SYSTEM_PROMPT = """You are Sasha's emergency response specialist. Help travelers in crisis situations with calm, clear, actionable guidance.
Always provide: local emergency numbers, embassy contacts, nearest hospital, immediate action steps, and insurance claim guidance.
Triage by severity — life-threatening situations get emergency numbers first, everything else gets step-by-step guidance.
Collect: current location/destination and type of emergency."""

async def run_emergency_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=EMERGENCY_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "get_emergency_info": result = await get_emergency_info(**inp)
                    else: result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Emergency agent error.", "tools_used": [], "messages": messages}
