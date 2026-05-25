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

async def stream_text(text: str, model_name: str = "sasha"):
    """Stream a text response in OpenAI SSE format."""
    words = text.split(' ')
    for i, word in enumerate(words):
        chunk = {
            "id": "chatcmpl-sasha",
            "object": "chat.completion.chunk",
            "model": model_name,
            "choices": [{
                "index": 0,
                "delta": {"content": word + (' ' if i < len(words)-1 else '')},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.02)
    
    # Send final chunk
    final = {
        "id": "chatcmpl-sasha",
        "object": "chat.completion.chunk", 
        "model": model_name,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def heygen_chat_completions(request: Request):
    """
    OpenAI-compatible endpoint for HeyGen custom LLM.
    HeyGen calls this on every user voice turn.
    We route golf questions to our golf agent, everything else to Claude.
    """
    body = await request.json()
    messages = body.get("messages", [])
    
    # Get the latest user message
    user_message = ""
    conversation_history = []
    for msg in messages:
        if msg["role"] == "user":
            user_message = msg["content"] if isinstance(msg["content"], str) else ""
        elif msg["role"] == "assistant":
            conversation_history.append(msg)

    if not user_message:
        async def empty():
            yield "data: [DONE]\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    # Route to golf agent if golf-related
    if is_golf_message(user_message):
        # Send acknowledgment first to avoid dead air
        ack = "Let me check golf availability for you... "
        
        # Run golf agent
        golf_history = []
        result = await run_golf_agent(user_message, golf_history)
        full_response = result["response"]
        
        return StreamingResponse(
            stream_text(full_response),
            media_type="text/event-stream"
        )
    
    # Regular conversation — use Claude
    claude_messages = [
        {"role": msg["role"], "content": msg["content"]} 
        for msg in messages 
        if msg["role"] in ["user", "assistant"] and isinstance(msg.get("content"), str)
    ]
    
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=256,
        system=SASHA_SYSTEM,
        messages=claude_messages
    )
    
    reply = response.content[0].text
    
    return StreamingResponse(
        stream_text(reply),
        media_type="text/event-stream"
    )
