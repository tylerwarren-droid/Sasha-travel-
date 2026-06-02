from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
import os
from datetime import datetime

router = APIRouter()

# ─────────────────────────────────────────────
# CARDS API
# Endpoints for card lookup and guest submissions
# ─────────────────────────────────────────────

class CardSubmission(BaseModel):
    card_name: str
    issuer: str
    points_currency: str
    annual_fee: Optional[float] = 0
    flights_earn_rate: Optional[float] = 1
    hotels_earn_rate: Optional[float] = 1
    dining_earn_rate: Optional[float] = 1
    base_earn_rate: Optional[float] = 1
    notable_credits: Optional[str] = ""
    transfer_partners: Optional[str] = ""
    source_url: Optional[str] = ""
    submitted_by: Optional[str] = ""
    notes: Optional[str] = ""


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


@router.post("/cards/submit")
async def submit_card(submission: CardSubmission):
    """
    Guest submits a card not yet in our database.
    Saves to a pending review file for manual verification before adding.
    """
    pending_path = "/tmp/pending_card_submissions.jsonl"

    record = {
        "submitted_at": datetime.utcnow().isoformat(),
        "status": "pending_review",
        **submission.dict()
    }

    # Append to pending submissions file
    with open(pending_path, "a") as f:
        f.write(json.dumps(record) + "\n")

    return {
        "success": True,
        "message": f"Thank you! We've received your submission for '{submission.card_name}'. Our team will verify the benefits and add it to Sasha's database within 24-48 hours.",
        "submitted_card": submission.card_name,
        "status": "pending_review"
    }


@router.get("/cards/pending/list")
async def list_pending_submissions():
    """
    Internal endpoint — list all pending card submissions awaiting review.
    In production this would be auth-protected.
    """
    pending_path = "/tmp/pending_card_submissions.jsonl"
    if not os.path.exists(pending_path):
        return {"pending": [], "total": 0}

    submissions = []
    with open(pending_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                submissions.append(json.loads(line))

    return {"pending": submissions, "total": len(submissions)}
