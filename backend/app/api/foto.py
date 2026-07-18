import asyncio

from fastapi import APIRouter
from pydantic import BaseModel
from app.services.foto_agent import search_photos, get_golf_course_photos, get_hotel_photos, get_destination_photo, extract_visual_context
from typing import Optional

router = APIRouter()

# The places Sasha opens with when the guest hasn't said anything yet. Ordered as a pitch: the
# two postcard icons first, then the cities, then the outliers. Each is a real DESTINATIONS key
# in booking_links.py, so tapping one routes cleanly through the normal intent path.
OPENING_DESTINATIONS = [
    {"location": "Ha Long Bay", "blurb": "Limestone karsts and overnight cruises"},
    {"location": "Hoi An",      "blurb": "Lantern-lit old town and tailors"},
    {"location": "Hanoi",       "blurb": "Old Quarter, street food, coffee"},
    {"location": "Da Nang",     "blurb": "Beaches, Golden Bridge, golf"},
    {"location": "Sapa",        "blurb": "Rice terraces and hill trekking"},
    {"location": "Phu Quoc",    "blurb": "Island beaches and seafood"},
]

class PhotoRequest(BaseModel):
    query: str
    count: int = 3
    type: str = "general"  # general, golf, hotel, destination

class VisualContextRequest(BaseModel):
    text: str

@router.post("/photos/search")
async def search(request: PhotoRequest):
    if request.type == "golf":
        photos = await get_golf_course_photos(request.query)
    elif request.type == "hotel":
        photos = await get_hotel_photos(request.query)
    elif request.type == "destination":
        photo = await get_destination_photo(request.query)
        photos = [photo] if photo else []
    else:
        photos = await search_photos(request.query, request.count)
    return {"photos": photos, "query": request.query}

@router.post("/photos/context")
async def visual_context(request: VisualContextRequest):
    context = extract_visual_context(request.text)
    return {"context": context}


@router.get("/photos/destinations")
async def destinations():
    """One photo per iconic Vietnam destination — the opening state of the workspace.

    Fans out concurrently rather than serially so the panel fills in one round trip. Each
    lookup goes through search_photos, which caches by search term and degrades to the curated
    set, so this is one burst of Unsplash calls per hour at most (the key is a DEMO key capped
    at 50/hour) and it can never leave the panel empty.
    """
    async def one(d: dict) -> dict:
        try:
            shots = await search_photos(f"{d['location']} Vietnam travel", count=1)
        except Exception:
            shots = []
        shot = shots[0] if shots else {}
        return {
            "location": d["location"],
            "blurb": d["blurb"],
            "url": shot.get("url", ""),
            "thumb": shot.get("thumb", ""),
            "photographer": shot.get("photographer", ""),
            "unsplash_url": shot.get("unsplash_url", ""),
        }

    items = await asyncio.gather(*[one(d) for d in OPENING_DESTINATIONS])
    # Drop any that came back with no image at all rather than rendering a broken tile.
    return {"destinations": [i for i in items if i["url"]]}
