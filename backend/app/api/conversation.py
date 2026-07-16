from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from app.services.claude import chat, generate_sasha_context
from app.services.ratehawk import (
    search_hotels,
    search_regions,
    get_hotel_rates,
    confirm_rate,
    build_search_filters,
    build_guests_payload
)

router = APIRouter(prefix="/conversation", tags=["conversation"])

class Message(BaseModel):
    role: str
    # Bounded because this array is forwarded verbatim to Sonnet and billed by input token.
    # Unbounded, one accepted request could carry megabytes of attacker-chosen text — the
    # cheapest way to run up a bill here. 8k chars is far more than any real chat turn.
    content: str = Field(max_length=8000)

class ChatRequest(BaseModel):
    # Same reasoning: cap the conversation length rather than trusting the caller's array.
    messages: List[Message] = Field(max_length=50)
    user: dict
    itinerary: Optional[dict] = None

class UpdateContextRequest(BaseModel):
    user: dict
    trips: List[dict]

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # 1. Send to Claude
        result = await chat(
            messages=[m.dict() for m in request.messages],
            user=request.user,
            itinerary=request.itinerary
        )

        response_text = result["response"]
        intent = result["intent"]
        api_data = None
        api_error = None

        # 2. If Claude extracted an intent, try to execute it
        if intent:
            action = intent.get("action")
            params = intent.get("params", {})

            try:
                if action == "search_regions":
                    api_data = await search_regions(params.get("destination", ""))

                elif action == "search_hotels":
                    region_id = params.get("destination_id")
                    if not region_id:
                        try:
                            regions = await search_regions(params.get("destination", ""))
                            regions_list = regions.get("data", {}).get("regions", [])
                            if regions_list:
                                region_id = regions_list[0].get("id")
                        except Exception:
                            region_id = None

                    if region_id:
                        filters = build_search_filters(
                            params.get("ota_channel", "beach"),
                            request.user.get("preferences", []),
                            request.user.get("travellers", [])
                        )
                        guests = build_guests_payload(
                            request.user.get("travellers", [])
                        )
                        api_data = await search_hotels(
                            checkin=params.get("checkin"),
                            checkout=params.get("checkout"),
                            destination_id=str(region_id),
                            guests=guests,
                            currency=request.user.get("default_currency", "GBP"),
                            filters=filters
                        )

                elif action == "get_hotel_rates":
                    guests = build_guests_payload(
                        request.user.get("travellers", [])
                    )
                    api_data = await get_hotel_rates(
                        checkin=params.get("checkin"),
                        checkout=params.get("checkout"),
                        hotel_id=params.get("hotel_id"),
                        guests=guests
                    )

                elif action == "confirm_rate":
                    api_data = await confirm_rate(params.get("book_hash"))

            except Exception as e:
                # RateHawk not available yet — log but don't crash
                api_error = str(e)
                print(f"RateHawk API error (expected without credentials): {e}")

        return {
            "response": response_text,
            "intent": intent,
            "api_data": api_data,
            "api_error": api_error,
            "usage": result["usage"]
        }

    except Exception as e:
        print(f"Conversation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-context")
async def update_context_endpoint(request: UpdateContextRequest):
    try:
        context = await generate_sasha_context(
            user=request.user,
            trips=request.trips
        )
        return {"status": "ok", "sasha_context": context}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
