from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ─────────────────────────────────────────────
# CARDS API
# Endpoints for card lookup (the public catalogue). Sasha 370: the unused submission routes
# (/cards/submit wrote a guest's name to disk; /cards/pending/list read it back to anyone) are gone.
# ─────────────────────────────────────────────

class CardLookup(BaseModel):
    card_name: str


@router.get("/cards")
async def list_cards():
    """Return all cards in the benefits database."""
    from app.services.card_benefits_db import list_cards as get_cards
    return {"cards": get_cards(), "total": len(get_cards())}


@router.get("/cards/{card_id}")
async def get_card(card_id: str):
    """Return full details for a specific card."""
    from app.services.card_benefits_db import get_card as fetch_card
    card = fetch_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card '{card_id}' not found in database.")
    return {"card_id": card_id, "card": card}


@router.get("/cards/{card_id}/rental")
async def get_rental_coverage(card_id: str, country: str = "United States", days: int = 7):
    """Return rental car coverage for a specific card and scenario."""
    from app.services.card_benefits_db import get_rental_coverage as fetch_coverage, get_card as fetch_card
    card = fetch_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card '{card_id}' not found.")
    coverage = fetch_coverage(card_id)
    if not coverage:
        raise HTTPException(status_code=404, detail=f"No rental coverage data for '{card_id}'.")
    return {"card_id": card_id, "card_name": card["name"], "rental_country": country, "rental_days": days, "coverage": coverage}
