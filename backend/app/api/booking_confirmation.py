from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.booking_confirmation_agent import run_booking_agent

router = APIRouter()

class BookingRequest(BaseModel):
    message: str
    conversation_history: list = []

class BookingResponse(BaseModel):
    response: str
    tools_used: list
    conversation_history: list

@router.post("/booking-confirmation")
async def booking_confirmation_endpoint(request: BookingRequest):
    try:
        result = await run_booking_agent(
            user_message=request.message,
            conversation_history=request.conversation_history
        )
        return BookingResponse(
            response=result["response"],
            tools_used=result["tools_used"],
            conversation_history=result["messages"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
