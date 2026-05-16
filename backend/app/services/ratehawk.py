import os
import hmac
import hashlib
import httpx
import json
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

RATEHAWK_API_URL = os.getenv("RATEHAWK_API_URL", "https://api-sandbox.worldota.net")
RATEHAWK_KEY_ID = os.getenv("RATEHAWK_KEY_ID")
RATEHAWK_API_KEY = os.getenv("RATEHAWK_API_KEY")

def generate_auth():
    """RateHawk uses HTTP Basic Auth with key_id:api_key"""
    return (RATEHAWK_KEY_ID, RATEHAWK_API_KEY)

async def ratehawk_post(endpoint: str, payload: dict) -> dict:
    """Core HTTP client for all RateHawk API calls"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{RATEHAWK_API_URL}{endpoint}",
            json=payload,
            auth=generate_auth(),
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()

# ─────────────────────────────────────────
# SEARCH
# ─────────────────────────────────────────

async def search_hotels(
    checkin: str,
    checkout: str,
    destination_id: str,
    guests: list[dict],
    currency: str = "GBP",
    filters: Optional[dict] = None
) -> dict:
    """
    Search for available hotels.
    guests: [{"adults": 2, "children": [8, 11]}]
    filters: pre-computed from user preferences
    """
    payload = {
        "checkin": checkin,
        "checkout": checkout,
        "residency": "gb",
        "language": "en",
        "guests": guests,
        "region_id": destination_id,
        "currency": currency,
    }

    if filters:
        payload.update(filters)

    return await ratehawk_post("/api/b2b/v3/search/serp/region/", payload)


async def search_hotels_by_ids(
    checkin: str,
    checkout: str,
    hotel_ids: list[str],
    guests: list[dict],
    currency: str = "GBP"
) -> dict:
    """Search specific hotels by property ID"""
    payload = {
        "checkin": checkin,
        "checkout": checkout,
        "residency": "gb",
        "language": "en",
        "guests": guests,
        "ids": hotel_ids,
        "currency": currency,
    }
    return await ratehawk_post("/api/b2b/v3/search/serp/hotels/", payload)


async def get_hotel_rates(
    checkin: str,
    checkout: str,
    hotel_id: str,
    guests: list[dict],
    currency: str = "GBP"
) -> dict:
    """Get all available rates for a specific hotel"""
    payload = {
        "checkin": checkin,
        "checkout": checkout,
        "residency": "gb",
        "language": "en",
        "guests": guests,
        "id": hotel_id,
        "currency": currency,
    }
    return await ratehawk_post("/api/b2b/v3/search/hp/", payload)


# ─────────────────────────────────────────
# RATE CONFIRMATION (before booking)
# ─────────────────────────────────────────

async def confirm_rate(book_hash: str) -> dict:
    """
    Confirm a rate is still available and price is valid.
    Must be called before every booking attempt.
    book_hash comes from search results.
    """
    payload = {"book_hash": book_hash}
    return await ratehawk_post("/api/b2b/v3/search/check/", payload)


# ─────────────────────────────────────────
# BOOKING
# ─────────────────────────────────────────

async def create_booking(
    book_hash: str,
    guests: list[dict],
    leader: dict,
    itinerary_id: str,
    language: str = "en"
) -> dict:
    """
    Create a booking.
    leader: {"first_name": "Jon", "last_name": "Smith", 
             "email": "jon@example.com", "phone": "+447700123456"}
    guests: [{"first_name": "Jon", "last_name": "Smith", "is_child": False}]
    """
    payload = {
        "book_hash": book_hash,
        "language": language,
        "user_ip": "127.0.0.1",
        "partner_order_id": itinerary_id,
        "leader": leader,
        "guests": guests,
    }
    return await ratehawk_post("/api/b2b/v3/order/booking/form/", payload)


async def get_booking(booking_id: str) -> dict:
    """Retrieve a booking by ID"""
    payload = {"booking_id": booking_id}
    return await ratehawk_post("/api/b2b/v3/order/booking/info/", payload)


async def cancel_booking(booking_id: str) -> dict:
    """Cancel a booking"""
    payload = {"booking_id": booking_id}
    return await ratehawk_post("/api/b2b/v3/order/booking/cancel/", payload)


# ─────────────────────────────────────────
# HOTEL CONTENT
# ─────────────────────────────────────────

async def get_hotel_info(hotel_id: str, language: str = "en") -> dict:
    """Get static hotel content - name, photos, amenities, description"""
    payload = {
        "id": hotel_id,
        "language": language,
    }
    return await ratehawk_post("/api/b2b/v3/hotel/info/", payload)


async def search_regions(query: str, language: str = "en") -> dict:
    """Search for destination region IDs by name"""
    payload = {
        "query": query,
        "language": language,
    }
    return await ratehawk_post("/api/b2b/v3/search/multicomplete/", payload)


# ─────────────────────────────────────────
# OTA FILTER SCHEMAS
# Maps vacation type + user preferences → RateHawk API params
# ─────────────────────────────────────────

OTA_BASE_FILTERS = {
    "beach": {
        "amenities": ["beach_access", "pool", "water_sports"],
        "property_types": ["resort", "hotel"],
        "stars": [4, 5],
    },
    "mountain": {
        "amenities": ["ski_access", "mountain_view"],
        "property_types": ["resort", "lodge", "chalet"],
        "stars": [4, 5],
    },
    "romance": {
        "amenities": ["spa", "adults_only", "fine_dining"],
        "property_types": ["resort", "boutique_hotel"],
        "stars": [5],
    },
    "adventure": {
        "amenities": ["outdoor_activities"],
        "property_types": ["lodge", "safari_camp", "resort"],
        "stars": [4, 5],
    },
    "city": {
        "amenities": ["concierge", "restaurant"],
        "property_types": ["hotel", "boutique_hotel"],
        "stars": [4, 5],
    },
}


def build_search_filters(
    ota_channel: str,
    preferences: list[dict],
    travellers: list[dict]
) -> dict:
    """
    Merge OTA base filters with user preferences into 
    RateHawk API parameters.
    preferences: list of Preference objects from DB
    travellers: list of Traveller objects
    """
    filters = OTA_BASE_FILTERS.get(ota_channel, {}).copy()

    has_children = any(t.get("relation") == "child" for t in travellers)

    for pref in preferences:
        key = pref.get("key")
        value = pref.get("value")

        if key == "accommodation.stars":
            filters["stars"] = [value] if isinstance(value, int) else value

        elif key == "accommodation.type":
            types = value if isinstance(value, list) else [value]
            filters["property_types"] = types

        elif key == "accommodation.board":
            board_map = {
                "all_inclusive": "all_inclusive",
                "half_board": "half_board",
                "bed_breakfast": "breakfast",
                "room_only": "room_only"
            }
            filters["meal"] = board_map.get(value, value)

        elif key == "budget.hotel_per_night":
            if isinstance(value, dict):
                filters["price_min"] = value.get("min")
                filters["price_max"] = value.get("max")

    if has_children:
        existing = filters.get("amenities", [])
        if "kids_club" not in existing:
            filters["amenities"] = existing + ["kids_club"]

    return filters


def build_guests_payload(travellers: list[dict]) -> list[dict]:
    """
    Convert Traveller objects into RateHawk guests format.
    RateHawk expects: [{"adults": N, "children": [age1, age2]}]
    Groups all travellers into one room by default.
    """
    from datetime import date

    adults = 0
    child_ages = []
    today = date.today()

    for t in travellers:
        if t.get("relation") == "child":
            dob = t.get("date_of_birth")
            if dob:
                birth = datetime.strptime(str(dob), "%Y-%m-%d").date()
                age = (today - birth).days // 365
                child_ages.append(age)
        else:
            adults += 1

    return [{"adults": max(adults, 1), "children": child_ages}]
