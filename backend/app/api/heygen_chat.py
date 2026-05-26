from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.services.conductor import conduct
import json
import asyncio

router = APIRouter()

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
    """
    OpenAI-compatible endpoint for HeyGen custom LLM.
    All messages now route through The Conductor.
    """
    try:
        body = await request.json()
        messages = body.get("messages", [])

        user_message = ""
        conversation_history = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                if role == "user":
                    user_message = content
                elif role == "assistant":
                    conversation_history.append({"role": role, "content": content})

        if not user_message:
            return StreamingResponse(
                stream_text("How can I help you with your trip?"),
                media_type="text/event-stream"
            )

        # Route through The Conductor
        try:
            result = await asyncio.wait_for(
                conduct(user_message, conversation_history),
                timeout=10.0
            )
            reply = result["response"]
        except asyncio.TimeoutError:
            reply = "I\'m working on that for you — could you give me just a moment and ask again?"
        except Exception as e:
            print(f"[HeyGen Chat] Conductor error: {e}")
            reply = "I\'m here to help with your Vietnam trip. What would you like to know?"

        return StreamingResponse(stream_text(reply), media_type="text/event-stream")

    except Exception:
        return StreamingResponse(
            stream_text("I\'m here to help with your Vietnam adventure!"),
            media_type="text/event-stream"
        )
