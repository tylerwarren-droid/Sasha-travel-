from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.services.golf_agent import run_golf_agent
from app.services.vietnam_golf_database import get_total_course_count
import anthropic
import json
import asyncio

router = APIRouter()
client = anthropic.Anthropic()

GOLF_KEYWORDS = ['golf', 'tee time', 'tee-time', 'fairway', 'caddy', 'green fee',
                 'montgomerie', 'hoiana', 'bluffs', 'vinpearl golf', 'ba na hills', 'course']

def is_golf_message(text: str) -> bool:
    lower = text.lower()
    return any(k in lower for k in GOLF_KEYWORDS)

SASHA_SYSTEM = f"""You are Sasha, an AI travel concierge specializing in Vietnam. 
You help travelers plan trips, book hotels, discover experiences, and explore Vietnam's culture and cuisine.
You are warm, knowledgeable, and efficient. Keep responses concise — under 3 sentences when possible.
You also have a golf specialist capability covering {get_total_course_count()} Vietnam courses."""

async def stream_text(text: str):
    words = text.split(' ')
    for i, word in enumerate(words):
        chunk = {
            "id": "chatcmpl-sasha",
            "object": "chat.completion.chunk",
            "model": "gpt-4o-mini",
            "choices": [{
                "index": 0,
                "delta": {"content": word + (' ' if i < len(words)-1 else '')},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.01)
    final = {
        "id": "chatcmpl-sasha",
        "object": "chat.completion.chunk",
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def heygen_chat_completions(request: Request):
    try:
        body = await request.json()
        messages = body.get("messages", [])

        # Get latest user message
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                user_message = content if isinstance(content, str) else ""
                break

        if not user_message:
            return StreamingResponse(stream_text("How can I help you with your Vietnam trip?"), media_type="text/event-stream")

        # Route to golf agent if golf-related
        if is_golf_message(user_message):
            try:
                # Timeout after 8 seconds to avoid dead air
                result = await asyncio.wait_for(
                    run_golf_agent(user_message, []),
                    timeout=8.0
                )
                reply = result["response"]
            except asyncio.TimeoutError:
                reply = "I'm checking golf availability for you. Give me just a moment and ask again."
            except Exception:
                reply = "I had trouble reaching the golf system. Please try again."
            
            return StreamingResponse(stream_text(reply), media_type="text/event-stream")

        # General conversation — use Claude
        try:
            claude_messages = []
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content", "")
                if role in ["user", "assistant"] and isinstance(content, str) and content.strip():
                    claude_messages.append({"role": role, "content": content})

            if not claude_messages:
                claude_messages = [{"role": "user", "content": user_message}]

            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=150,
                system=SASHA_SYSTEM,
                messages=claude_messages[-10:]  # last 10 messages max
            )
            reply = response.content[0].text
        except Exception:
            reply = "I'm here to help with your Vietnam trip. What would you like to know?"

        return StreamingResponse(stream_text(reply), media_type="text/event-stream")

    except Exception:
        return StreamingResponse(
            stream_text("I'm here to help with your Vietnam adventure. What would you like to know?"),
            media_type="text/event-stream"
        )
