import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from app.services.conductor import conduct
from app.services.llm import client, FAST_MODEL
from app.services.prompts import get_prompt_async
from app.services import chat_store

router = APIRouter()


@router.get("/warmup")
async def warmup():
    """Pre-warm the LLM path so the FIRST real turn isn't cold.

    The frontend fires this (best-effort) the moment the avatar session starts. It kicks
    the background prompt refresh and opens the TLS/HTTP-2 connection to Anthropic with a
    1-token call, so DNS, handshake, and the shared client pool are hot before the user
    speaks. Without this, the first spoken turn pays cold-connection setup on top of the
    LLM latency — exactly the lag an investor notices on the opening question.
    """
    try:
        await get_prompt_async("conductor.general")
        await client.messages.create(
            model=FAST_MODEL,
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return {"warm": True}
    except Exception as e:
        # Warmup is best-effort — never surface an error that would alarm the client.
        return {"warm": False, "detail": str(e)[:120]}


class ConductorRequest(BaseModel):
    # Bounded: every turn is billed by input token, and the conductor can fan out into paid
    # web_search. A spoken turn is never anywhere near 4k characters.
    message: str = Field(max_length=4000)
    conversation_history: list = Field(default=[], max_length=100)
    language: str = "en"
    # Chat persistence + personalization (single hardcoded user for the demo).
    session_id: Optional[str] = None
    user_name: Optional[str] = None
    # Set when the UI already knows the intent (e.g. the guest tapped "Build this" on an idea),
    # so the conductor doesn't have to infer it from the wording and get it wrong.
    force_intent: Optional[str] = None


class ConductorResponse(BaseModel):
    response: str
    intents: list
    photos: list
    tools_used: list
    links: list = []
    hotels: list = []
    bookings: list = []
    itinerary: Optional[dict] = None
    action: Optional[str] = None
    booking_ref: Optional[str] = None
    # The stored trip a payment would apply to. Checkout is priced from this server-side
    # record, so the browser never gets to state its own amount.
    itinerary_id: Optional[str] = None
    conversation_history: list


@router.post("/conductor")
async def conductor_endpoint(body: ConductorRequest, request: Request):
    try:
        client_config = getattr(request.state, "client", None)
        # Mint the session id BEFORE conducting: the conductor needs it to look up whether a
        # real itinerary exists for this session, and to file any plan it builds against it.
        session_id = body.session_id or str(uuid.uuid4())
        result = await conduct(
            user_message=body.message,
            conversation_history=body.conversation_history,
            client_config=client_config,
            language=body.language,
            user_name=body.user_name,
            force_intent=body.force_intent,
            session_id=session_id,
            user_id=chat_store.DEMO_USER_ID,
        )
        # Persist this turn (best-effort; a DB hiccup must never break the conversation).
        await chat_store.save_turn(
            session_id=session_id,
            user_id=chat_store.DEMO_USER_ID,
            user_message=body.message,
            assistant_response=result["response"],
            intents=result.get("intents"),
            booking_ref=result.get("booking_ref"),
            language=body.language,
            title=body.message,
        )
        return ConductorResponse(
            response=result["response"],
            intents=result["intents"],
            photos=result["photos"],
            tools_used=result["tools_used"],
            links=result.get("links", []),
            hotels=result.get("hotels", []),
            bookings=result.get("bookings", []),
            itinerary=result.get("itinerary"),
            action=result.get("action"),
            booking_ref=result.get("booking_ref"),
            itinerary_id=result.get("itinerary_id"),
            conversation_history=result["messages"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
