from pydantic import BaseModel
from typing import Optional, List, Any
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum

class PreferenceSource(str, Enum):
    explicit = "explicit"
    inferred = "inferred"
    post_trip = "post_trip"
    corrected = "corrected"

class Preference(BaseModel):
    id: UUID = uuid4()
    user_id: UUID
    key: str
    value: Any
    source: PreferenceSource = PreferenceSource.inferred
    confidence: float = 0.4
    evidence_count: int = 1
    itinerary_ids: List[UUID] = []
    applies_to_traveller: Optional[UUID] = None
    expedia_filter_params: dict = {}
    created_at: datetime = datetime.utcnow()
    last_applied_at: Optional[datetime] = None
    is_active: bool = True

class PreferenceCreate(BaseModel):
    key: str
    value: Any
    source: PreferenceSource = PreferenceSource.explicit
    applies_to_traveller: Optional[UUID] = None

class PreferenceKeys:
    FLIGHT_TIMING = "flight.timing"
    FLIGHT_CABIN = "flight.cabin"
    FLIGHT_STOPS = "flight.stops"
    FLIGHT_AIRLINE = "flight.airline"
    ACCOMMODATION_TYPE = "accommodation.type"
    ACCOMMODATION_STARS = "accommodation.stars"
    ACCOMMODATION_BOARD = "accommodation.board"
    ACTIVITY_KIDS = "activity.kids"
    ACTIVITY_INTERESTS = "activity.interests"
    PAYMENT_METHOD = "payment.method"
    BUDGET_HOTEL_PER_NIGHT = "budget.hotel_per_night"
    DATES_FLEXIBILITY = "dates.flexibility"
