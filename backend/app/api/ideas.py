"""Ideas endpoint — personalized ready-made trip cards for the workspace's Ideas tab."""

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ideas_agent import generate_ideas

router = APIRouter()


class IdeasRequest(BaseModel):
    name: Optional[str] = None
    travellers: List[str] = []
    preferences: List[str] = []
    past_trips: List[str] = []
    # Groups a visit: ideas stay put while the guest flicks between tabs, but a new session
    # gets a fresh set rather than the same three trips every time.
    session_id: Optional[str] = None
    # Set by the tab's Refresh control to regenerate now.
    force: bool = False


@router.post("/ideas")
async def ideas_endpoint(body: IdeasRequest):
    """Return 3 trip ideas tailored to the guest.

    Never fails the request: generate_ideas() falls back to generic cards if the model is
    unavailable, because an empty Ideas tab is a worse outcome than an unpersonalized one.
    """
    result = await generate_ideas(
        profile={
            "name": body.name,
            "travellers": body.travellers,
            "preferences": body.preferences,
            "past_trips": body.past_trips,
        },
        session=body.session_id or "",
        force=body.force,
    )
    return result
