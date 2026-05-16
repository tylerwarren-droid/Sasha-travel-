from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from app.services.ratehawk import (
    create_booking,
    get_booking,
    cancel_booking,
    confirm_rate
)

router = APIRouter(prefix="/bookings", tags=["bookings"])

class LeaderDetails(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str

class GuestDetails(BaseModel):
    first_name: str
    last_name: str
    is_child: bool = False

class CreateBookingRequest(BaseModel):
    book_hash: str
    itinerary_id: str
    leader: LeaderDetails
    guests: List[GuestDetails]
    language: str = "en"

class CancelBookingRequest(BaseModel):
    booking_id: str

@router.post("/create")
async def create_booking_endpoint(request: CreateBookingRequest):
    try:
        # Always confirm rate is still valid before booking
        rate_check = await confirm_rate(request.book_hash)
        if rate_check.get("data", {}).get("status") != "ok":
            raise HTTPException(
                status_code=409,
                detail="Rate is no longer available. Please search again."
            )

        result = await create_booking(
            book_hash=request.book_hash,
            guests=[g.dict() for g in request.guests],
            leader=request.leader.dict(),
            itinerary_id=request.itinerary_id,
            language=request.language
        )
        return {"status": "ok", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{booking_id}")
async def get_booking_endpoint(booking_id: str):
    try:
        result = await get_booking(booking_id)
        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cancel")
async def cancel_booking_endpoint(request: CancelBookingRequest):
    try:
        result = await cancel_booking(request.booking_id)
        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
