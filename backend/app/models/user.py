from pydantic import BaseModel, EmailStr
from typing import Optional, List
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum

class TravellerRelation(str, Enum):
    self_ = "self"
    partner = "partner"
    child = "child"
    other = "other"

class Traveller(BaseModel):
    id: UUID = uuid4()
    user_id: UUID
    relation: TravellerRelation
    first_name: str
    last_name: str
    date_of_birth: str
    dietary: List[str] = []

class PaymentMethod(BaseModel):
    id: UUID = uuid4()
    type: str  # "card" or "crypto"
    label: str  # "Visa ending 4242" or "BTC wallet"
    token: Optional[str] = None
    wallet_address: Optional[str] = None
    is_default: bool = False

class User(BaseModel):
    id: UUID = uuid4()
    email: str
    display_name: str
    phone: Optional[str] = None
    default_currency: str = "GBP"
    default_crypto: Optional[str] = None
    ota_affinity: List[str] = []
    sasha_context: Optional[str] = None
    travellers: List[Traveller] = []
    payment_methods: List[PaymentMethod] = []
    created_at: datetime = datetime.utcnow()
    last_active_at: datetime = datetime.utcnow()

class UserCreate(BaseModel):
    email: str
    display_name: str
    phone: Optional[str] = None
    default_currency: str = "GBP"

class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    sasha_context: Optional[str]
    ota_affinity: List[str]
    created_at: datetime
