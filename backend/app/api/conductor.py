import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from app.services.conductor import conduct, classify_intents
from app.services.llm import client, FAST_MODEL
from app.services.prompts import get_prompt_async
from app.services import chat_store
from app.services.chat_account import chat_account, own_session

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


class ClassifyRequest(BaseModel):
    message: str = Field(max_length=4000)
    conversation_history: list = Field(default=[], max_length=100)
    session_id: Optional[str] = None


@router.post("/classify")
async def classify(body: ClassifyRequest, request: Request):
    """Report which agents a message will fire — WITHOUT running them.

    Exists so the UI can react at the START of a turn instead of the end. An itinerary build
    takes 13-45s, and the conductor only reveals that it happened once it's finished, so the
    guest sat through the whole thing with no idea anything was underway.

    The frontend previously guessed with its own regex. That could never work: the backend
    reaches "itinerary" three different ways — the phrase list, a build-verb regex, and (most
    commonly in real speech) a bare affirmation like "yes please" answering Sasha's offer to
    build one. The last is invisible to any client-side check, so the banner never showed on
    the most common path. This returns the REAL classification from the same function the
    conductor uses, so the two can never drift.

    Pure keyword matching, no LLM and no agents — a few ms. Meant to be fired in PARALLEL with
    the conductor call so it costs the turn nothing.
    """
    # S-62 step 7 · only the caller's own session is looked into
    sid = await own_session(body.session_id, await chat_account(request)) if body.session_id else None
    stored = await chat_store.latest_itinerary_for_session(sid) if sid else None
    has_itinerary = bool(stored) if body.session_id else None
    result = await classify_intents(body.message, body.conversation_history, has_itinerary)
    return {"intents": result.get("intents", []), "primary": result.get("primary")}


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
    # A single matched option the guest asked to book by VOICE — the frontend opens the
    # payment popup for it directly (same flow as tapping Book & Pay on its card).
    payment_item: Optional[dict] = None
    # The saved card Sasha offers / charges on a booking turn (action confirm_card or
    # pay_saved_card): {"last4": "1003", "method": "saved_card"}.
    saved_card: Optional[dict] = None
    session_id: Optional[str] = None  # S-62 step 7 · the session this turn was filed under (a new one if the sent id was not yours)
    booking_find: Optional[dict] = None  # S-66 chat booking (Stage B)
    reservation_draft: Optional[dict] = None  # S-66 chat booking (Stage B)
    conversation_history: list


@router.post("/conductor")
async def conductor_endpoint(body: ConductorRequest, request: Request):
    # S-62 step 7 · WHO: a verified guest, or the public demo. A bad token is refused here, never turned into the demo.
    account = await chat_account(request)
    try:
        client_config = getattr(request.state, "client", None)
        # Mint the session id BEFORE conducting: the conductor needs it to look up whether a
        # real itinerary exists for this session, and to file any plan it builds against it.
        # S-62 step 7 · a session someone else owns is never appended to or read: this turn starts a new one.
        session_id = await own_session(body.session_id, account) or str(uuid.uuid4())
        result = await conduct(
            user_message=body.message,
            conversation_history=body.conversation_history,
            client_config=client_config,
            language=body.language,
            user_name=body.user_name,
            force_intent=body.force_intent,
            session_id=session_id,
            user_id=account,
        )
        # Persist this turn (best-effort; a DB hiccup must never break the conversation).
        await chat_store.save_turn(
            session_id=session_id,
            user_id=account,
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
            payment_item=result.get("payment_item"),
            saved_card=result.get("saved_card"),
            booking_find=result.get("booking_find"),  # S-66 chat booking (Stage B)
            reservation_draft=result.get("reservation_draft"),  # S-66 chat booking (Stage B)
            session_id=session_id,
            conversation_history=result["messages"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
