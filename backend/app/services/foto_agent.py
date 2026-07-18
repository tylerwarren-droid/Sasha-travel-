import copy
import os
import time
import httpx
from typing import Optional

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
UNSPLASH_BASE = "https://api.unsplash.com"

# Unsplash quota is small and exhaustible: a DEMO app key allows 50 requests/HOUR (a Production
# key allows 5000). An itinerary now fetches one photo set per distinct city, and the foto
# intent fetches on top of that, so an unlucky demo could burn the hourly budget and every
# panel would silently drop to the curated fallback set mid-pitch. Cache by search term so a
# repeated city costs nothing. Photo URLs are stable, so the TTL only exists to keep a
# long-lived process from serving the same shots forever.
#
# Process-local, same caveat as the travel_search card cache: fine on Railway's single uvicorn
# worker, would need Redis if WEB_CONCURRENCY is ever raised.
_PHOTO_TTL_S = float(os.getenv("PHOTO_CACHE_TTL_S", "3600"))
_photo_cache: dict = {}

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

# Curated Vietnam set served when no UNSPLASH_ACCESS_KEY is configured (e.g. local dev),
# so the photo panel degrades to a sensible default instead of an empty/broken state.
FALLBACK_PHOTOS = [
    {
        "url": "https://images.unsplash.com/photo-1528127269322-539801943592?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwxfHxWaWV0bmFtJTIwbGFuZHNjYXBlJTIwdHJhdmVsfGVufDF8MHx8fDE3ODIyODYzNTR8MA&ixlib=rb-4.1.0&q=80&w=1080",
        "thumb": "https://images.unsplash.com/photo-1528127269322-539801943592?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwxfHxWaWV0bmFtJTIwbGFuZHNjYXBlJTIwdHJhdmVsfGVufDF8MHx8fDE3ODIyODYzNTR8MA&ixlib=rb-4.1.0&q=80&w=400",
        "full": "https://images.unsplash.com/photo-1528127269322-539801943592?crop=entropy&cs=srgb&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwxfHxWaWV0bmFtJTIwbGFuZHNjYXBlJTIwdHJhdmVsfGVufDF8MHx8fDE3ODIyODYzNTR8MA&ixlib=rb-4.1.0&q=85",
        "description": "Ha Long Bay",
        "photographer": "Ammie Ngo",
        "photographer_url": "https://unsplash.com/@ammiengo",
        "unsplash_url": "https://unsplash.com/photos/high-angle-photography-of-boats-on-water-near-hill-during-daytime-vcu-OZBxxRk",
        "color": "#264040",
        "width": 6000,
        "height": 4000
    },
    {
        "url": "https://images.unsplash.com/photo-1609412058473-c199497c3c5d?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwyfHxWaWV0bmFtJTIwbGFuZHNjYXBlJTIwdHJhdmVsfGVufDF8MHx8fDE3ODIyODYzNTR8MA&ixlib=rb-4.1.0&q=80&w=1080",
        "thumb": "https://images.unsplash.com/photo-1609412058473-c199497c3c5d?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwyfHxWaWV0bmFtJTIwbGFuZHNjYXBlJTIwdHJhdmVsfGVufDF8MHx8fDE3ODIyODYzNTR8MA&ixlib=rb-4.1.0&q=80&w=400",
        "full": "https://images.unsplash.com/photo-1609412058473-c199497c3c5d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwyfHxWaWV0bmFtJTIwbGFuZHNjYXBlJTIwdHJhdmVsfGVufDF8MHx8fDE3ODIyODYzNTR8MA&ixlib=rb-4.1.0&q=85",
        "description": "Mu Cang Chai rice terraces",
        "photographer": "Hoach Le Dinh",
        "photographer_url": "https://unsplash.com/@hoachld",
        "unsplash_url": "https://unsplash.com/photos/green-grass-field-near-body-of-water-during-daytime-PeRt3uMmjYM",
        "color": "#26260c",
        "width": 7952,
        "height": 5304
    },
    {
        "url": "https://images.unsplash.com/photo-1691927644490-e1a24b366a5e?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwxfHxIb2klMjBBbiUyMFZpZXRuYW0lMjBsYW50ZXJucyUyMGFuY2llbnQlMjB0b3dufGVufDF8MHx8fDE3ODIyODYzNTV8MA&ixlib=rb-4.1.0&q=80&w=1080",
        "thumb": "https://images.unsplash.com/photo-1691927644490-e1a24b366a5e?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwxfHxIb2klMjBBbiUyMFZpZXRuYW0lMjBsYW50ZXJucyUyMGFuY2llbnQlMjB0b3dufGVufDF8MHx8fDE3ODIyODYzNTV8MA&ixlib=rb-4.1.0&q=80&w=400",
        "full": "https://images.unsplash.com/photo-1691927644490-e1a24b366a5e?crop=entropy&cs=srgb&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwxfHxIb2klMjBBbiUyMFZpZXRuYW0lMjBsYW50ZXJucyUyMGFuY2llbnQlMjB0b3dufGVufDF8MHx8fDE3ODIyODYzNTV8MA&ixlib=rb-4.1.0&q=85",
        "description": "Hoi An ancient town",
        "photographer": "Hieu Do Quang",
        "photographer_url": "https://unsplash.com/@magicaleye7",
        "unsplash_url": "https://unsplash.com/photos/a-bunch-of-lanterns-that-are-hanging-from-a-tree-nj70WidlPjc",
        "color": "#0c2626",
        "width": 4898,
        "height": 3265
    },
    {
        "url": "https://images.unsplash.com/photo-1698744822195-e461f814a6a1?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwyfHxIb2klMjBBbiUyMFZpZXRuYW0lMjBsYW50ZXJucyUyMGFuY2llbnQlMjB0b3dufGVufDF8MHx8fDE3ODIyODYzNTV8MA&ixlib=rb-4.1.0&q=80&w=1080",
        "thumb": "https://images.unsplash.com/photo-1698744822195-e461f814a6a1?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwyfHxIb2klMjBBbiUyMFZpZXRuYW0lMjBsYW50ZXJucyUyMGFuY2llbnQlMjB0b3dufGVufDF8MHx8fDE3ODIyODYzNTV8MA&ixlib=rb-4.1.0&q=80&w=400",
        "full": "https://images.unsplash.com/photo-1698744822195-e461f814a6a1?crop=entropy&cs=srgb&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwyfHxIb2klMjBBbiUyMFZpZXRuYW0lMjBsYW50ZXJucyUyMGFuY2llbnQlMjB0b3dufGVufDF8MHx8fDE3ODIyODYzNTV8MA&ixlib=rb-4.1.0&q=85",
        "description": "Vietnam",
        "photographer": "RE Walsh",
        "photographer_url": "https://unsplash.com/@lutruwita_exposure",
        "unsplash_url": "https://unsplash.com/photos/a-couple-of-boats-that-are-sitting-in-the-water-o2yDssRqgog",
        "color": "#c0c0d9",
        "width": 4032,
        "height": 3024
    },
    {
        "url": "https://images.unsplash.com/photo-1573270689103-d7a4e42b609a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwxfHxIYSUyMExvbmclMjBCYXklMjBWaWV0bmFtJTIwa2Fyc3QlMjBsaW1lc3RvbmV8ZW58MXwwfHx8MTc4MjI4NjM1N3ww&ixlib=rb-4.1.0&q=80&w=1080",
        "thumb": "https://images.unsplash.com/photo-1573270689103-d7a4e42b609a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwxfHxIYSUyMExvbmclMjBCYXklMjBWaWV0bmFtJTIwa2Fyc3QlMjBsaW1lc3RvbmV8ZW58MXwwfHx8MTc4MjI4NjM1N3ww&ixlib=rb-4.1.0&q=80&w=400",
        "full": "https://images.unsplash.com/photo-1573270689103-d7a4e42b609a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwxfHxIYSUyMExvbmclMjBCYXklMjBWaWV0bmFtJTIwa2Fyc3QlMjBsaW1lc3RvbmV8ZW58MXwwfHx8MTc4MjI4NjM1N3ww&ixlib=rb-4.1.0&q=85",
        "description": "Vietnam",
        "photographer": "Lewis J Goetz",
        "photographer_url": "https://unsplash.com/@lgoetz",
        "unsplash_url": "https://unsplash.com/photos/body-of-water-near-mountain-during-daytime-p3zbb3Efczw",
        "color": "#d9f3f3",
        "width": 4578,
        "height": 3052
    },
    {
        "url": "https://images.unsplash.com/photo-1504805526346-8d03d1ca73de?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwyfHxIYSUyMExvbmclMjBCYXklMjBWaWV0bmFtJTIwa2Fyc3QlMjBsaW1lc3RvbmV8ZW58MXwwfHx8MTc4MjI4NjM1N3ww&ixlib=rb-4.1.0&q=80&w=1080",
        "thumb": "https://images.unsplash.com/photo-1504805526346-8d03d1ca73de?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwyfHxIYSUyMExvbmclMjBCYXklMjBWaWV0bmFtJTIwa2Fyc3QlMjBsaW1lc3RvbmV8ZW58MXwwfHx8MTc4MjI4NjM1N3ww&ixlib=rb-4.1.0&q=80&w=400",
        "full": "https://images.unsplash.com/photo-1504805526346-8d03d1ca73de?crop=entropy&cs=srgb&fm=jpg&ixid=M3w5NjA1NTR8MHwxfHNlYXJjaHwyfHxIYSUyMExvbmclMjBCYXklMjBWaWV0bmFtJTIwa2Fyc3QlMjBsaW1lc3RvbmV8ZW58MXwwfHx8MTc4MjI4NjM1N3ww&ixlib=rb-4.1.0&q=85",
        "description": "Vietnam",
        "photographer": "Ryan Waring",
        "photographer_url": "https://unsplash.com/@ryanwaring",
        "unsplash_url": "https://unsplash.com/photos/white-watercraft-on-body-of-water-EqQ9oQ0bLis",
        "color": "#f3f3f3",
        "width": 5472,
        "height": 3648
    }
]


async def search_photos(query: str, count: int = 3) -> list:
    """Search Unsplash for photos matching the query."""
    if not UNSPLASH_ACCESS_KEY:
        # No key — serve the curated fallback rather than an empty panel.
        return FALLBACK_PHOTOS[:count]

    # Check if we have a better search term
    query_lower = query.lower()
    search_term = query
    for key, value in SEARCH_MAPPINGS.items():
        if key in query_lower:
            search_term = value
            break

    # Keyed on the RESOLVED search term, so "Hoi An" and "hoian" that both map through
    # SEARCH_MAPPINGS to the same term share one cache entry and one API call.
    cache_key = (search_term.lower(), count)
    now = time.monotonic()
    hit = _photo_cache.get(cache_key)
    if hit and hit[1] > now:
        return copy.deepcopy(hit[0])

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
            if not photos:
                # Empty results is the shape a quota-exhausted key returns too: Unsplash answers
                # 403 with no `results`, which parses cleanly and yields []. Returning [] left the
                # gallery blank with no error anywhere. Degrade to the curated set instead, and
                # do NOT cache it — the quota resets hourly and we want live shots back after.
                print(f"[Foto Agent] no results for {search_term!r} "
                      f"(http {response.status_code}) — serving fallback")
                return FALLBACK_PHOTOS[:count]
            _photo_cache[cache_key] = (copy.deepcopy(photos), now + _PHOTO_TTL_S)
            return photos
    except Exception as e:
        print(f"[Foto Agent] Unsplash error: {e}")
        return FALLBACK_PHOTOS[:count]


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
