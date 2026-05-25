import os
import httpx
from typing import Optional

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
UNSPLASH_BASE = "https://api.unsplash.com"

# Vietnam-specific search term mappings for better results
SEARCH_MAPPINGS = {
    "danang": "Da Nang Vietnam beach city",
    "da nang": "Da Nang Vietnam beach city",
    "hanoi": "Hanoi Vietnam old quarter",
    "ha noi": "Hanoi Vietnam old quarter",
    "hoi an": "Hoi An Vietnam lanterns ancient town",
    "hoian": "Hoi An Vietnam lanterns ancient town",
    "ho chi minh": "Ho Chi Minh City Saigon Vietnam",
    "saigon": "Ho Chi Minh City Saigon Vietnam",
    "ha long bay": "Ha Long Bay Vietnam karst limestone",
    "halong": "Ha Long Bay Vietnam karst limestone",
    "phu quoc": "Phu Quoc island Vietnam beach",
    "nha trang": "Nha Trang Vietnam beach coastal",
    "da lat": "Da Lat Vietnam highlands flower",
    "dalat": "Da Lat Vietnam highlands flower",
    "hue": "Hue Vietnam imperial citadel",
    "mekong": "Mekong Delta Vietnam river boats",
    "sapa": "Sapa Vietnam rice terraces mountains",
    "ha giang": "Ha Giang Vietnam mountain loop",
    "con dao": "Con Dao Vietnam island beach",
    "mui ne": "Mui Ne Vietnam sand dunes beach",
    "montgomerie links": "Montgomerie Links golf Vietnam Da Nang",
    "hoiana shores": "Hoiana Shores golf Vietnam Hoi An",
    "the bluffs": "The Bluffs Ho Tram golf Vietnam",
    "ba na hills golf": "Ba Na Hills golf Da Nang Vietnam",
    "vinpearl golf": "Vinpearl golf Vietnam resort",
    "laguna golf": "Laguna Lang Co golf Vietnam",
    "vietnam": "Vietnam landscape travel",
}

async def search_photos(query: str, count: int = 3) -> list:
    """Search Unsplash for photos matching the query."""
    if not UNSPLASH_ACCESS_KEY:
        return []
    
    # Check if we have a better search term
    query_lower = query.lower()
    search_term = query
    for key, value in SEARCH_MAPPINGS.items():
        if key in query_lower:
            search_term = value
            break
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{UNSPLASH_BASE}/search/photos",
                params={
                    "query": search_term,
                    "per_page": count,
                    "orientation": "landscape",
                    "content_filter": "high",
                },
                headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
                timeout=5.0
            )
            data = response.json()
            
            photos = []
            for photo in data.get("results", []):
                photos.append({
                    "url": photo["urls"]["regular"],
                    "thumb": photo["urls"]["small"],
                    "full": photo["urls"]["full"],
                    "description": photo.get("description") or photo.get("alt_description") or query,
                    "photographer": photo["user"]["name"],
                    "photographer_url": photo["user"]["links"]["html"],
                    "unsplash_url": photo["links"]["html"],
                    "color": photo.get("color", "#000000"),
                    "width": photo["width"],
                    "height": photo["height"],
                })
            return photos
    except Exception as e:
        print(f"[Foto Agent] Unsplash error: {e}")
        return []


async def get_destination_photo(destination: str) -> Optional[dict]:
    """Get a single best photo for a destination."""
    photos = await search_photos(destination, count=1)
    return photos[0] if photos else None


async def get_golf_course_photos(course_name: str) -> list:
    """Get photos for a specific golf course."""
    return await search_photos(course_name, count=3)


async def get_hotel_photos(hotel_name: str, location: str = "Vietnam") -> list:
    """Get photos for a hotel."""
    query = f"{hotel_name} {location} hotel"
    return await search_photos(query, count=3)


async def get_activity_photos(activity: str, location: str = "Vietnam") -> list:
    """Get photos for a tour or activity."""
    query = f"{activity} {location}"
    return await search_photos(query, count=3)


def extract_visual_context(text: str) -> dict:
    """
    Analyse a Sasha response and extract what visuals to show.
    Returns a dict with destination, courses, hotels, activities mentioned.
    """
    text_lower = text.lower()
    context = {
        "destinations": [],
        "golf_courses": [],
        "hotels": [],
        "activities": [],
    }
    
    # Destinations
    destinations = [
        "danang", "da nang", "hanoi", "hoi an", "ho chi minh", "saigon",
        "ha long bay", "halong", "phu quoc", "nha trang", "da lat", "dalat",
        "hue", "mekong", "sapa", "ha giang", "con dao", "mui ne"
    ]
    for dest in destinations:
        if dest in text_lower:
            context["destinations"].append(dest)
    
    # Golf courses
    courses = [
        "montgomerie links", "hoiana shores", "the bluffs", "ba na hills",
        "vinpearl golf", "laguna golf", "brg danang", "legend danang"
    ]
    for course in courses:
        if course in text_lower:
            context["golf_courses"].append(course)
    
    return context
