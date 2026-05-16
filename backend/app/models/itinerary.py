from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime, date
from enum import Enum

class ItineraryStatus(str, Enum):
    draft = "draft"
    held = "held"
    confirmed = "confirmed"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"

class ItemType(str, Enum):
    flight = "flight"
    hotel = "hotel"
    transfer = "transfer"
    activity = "activity"
    car_hire = "car_hire"

class ItemStatus(str, Enum):
    suggested = "suggested"
    selected = "selected"
    held = "held"
    booked = "booked"
    cancelled = "cancelled"

class ItineraryItem(BaseModel):
    id: UUID = uuid4()
    itinerary_id: UUID
    type: ItemType
    status: ItemStatus = ItemStatus.suggested
    sort_order: int = 0
    expedia_product_id: Optional[str] = None
    expedia_rate_id: Optional[str] = None
    display_name: str
    detail: Dict[str, Any] = {}
    traveller_ids: List[UUID] = []
    price_fiat: float = 0.0
    price_currency: str = "GBP"
    price_locked_at: Optional[datetime] = None
    is_refundable: bool = True
    cancellation_policy: Dict[str, Any] = {}
    confirmation_ref: Optional[str] = None
    media: List[Dict[str, Any]] = []
    sasha_rationale: Optional[str] = None

class Itinerary(BaseModel):
    id: UUID = uuid4()
    user_id: UUID
    title: str
    ota_channel: str
    status: ItineraryStatus = ItineraryStatus.draft
    traveller_ids: List[UUID] = []
    destination_summary: Dict[str, Any] = {}
    depart_date: Optional[date] = None
    return_date: Optional[date] = None
    total_fiat: float = 0.0
    total_crypto: Optional[Dict[str, float]] = None
    hold_expires_at: Optional[datetime] = None
    expedia_booking_refs: Dict[str, str] = {}
    conversation_id: Optional[UUID] = None
    review: Optional[Dict[str, Any]] = None
    items: List[ItineraryItem] = []
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()

class ItineraryCreate(BaseModel):
    title: str
    ota_channel: str
    traveller_ids: List[UUID] = []
    depart_date: Optional[date] = None
    return_date: Optional[date] = None
