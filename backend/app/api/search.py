from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from app.services.ratehawk import (
    search_hotels,
    get_hotel_rates,
    confirm_rate,
    search_regions,
    build_search_filters,
    build_guests_payload
)

router = APIRouter(prefix="/search", tags=["search"])

class SearchRequest(BaseModel):
    checkin: str
    checkout: str
    destination_id: str
    ota_channel: str = "beach"
    currency: str = "GBP"
    travellers: List[dict] = []
    preferences: List[dict] = []

class RegionSearchRequest(BaseModel):
    query: str

class RateConfirmRequest(BaseModel):
    book_hash: str

@router.post("/hotels")
async def search_hotels_endpoint(request: SearchRequest):
    try:
        filters = build_search_filters(
            request.ota_channel,
            request.preferences,
            request.travellers
        )
        guests = build_guests_payload(request.travellers)
        results = await search_hotels(
            checkin=request.checkin,
            checkout=request.checkout,
            destination_id=request.destination_id,
            guests=guests,
            currency=request.currency,
            filters=filters
        )
        return {"status": "ok", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/hotel/rates")
async def get_rates_endpoint(
    hotel_id: str,
    checkin: str,
    checkout: str,
    travellers: List[dict] = []
):
    try:
        guests = build_guests_payload(travellers)
        results = await get_hotel_rates(
            checkin=checkin,
            checkout=checkout,
            hotel_id=hotel_id,
            guests=guests
        )
        return {"status": "ok", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/confirm-rate")
async def confirm_rate_endpoint(request: RateConfirmRequest):
    try:
        result = await confirm_rate(request.book_hash)
        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/regions")
async def search_regions_endpoint(request: RegionSearchRequest):
    try:
        results = await search_regions(request.query)
        return {"status": "ok", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
