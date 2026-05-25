from fastapi import APIRouter
from pydantic import BaseModel
from app.services.foto_agent import search_photos, get_golf_course_photos, get_hotel_photos, get_destination_photo, extract_visual_context
from typing import Optional

router = APIRouter()

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
