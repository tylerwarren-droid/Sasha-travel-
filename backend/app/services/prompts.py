"""
Prompt registry with DB-backed versioning.

Static fallbacks are always available. On first call (and every TTL_SECONDS),
active rows from prompt_versions are loaded from the DB and overlaid on top.
If the DB is unreachable the static registry is used transparently.
"""

import logging
import time
from typing import Optional

from sqlalchemy import text

from app.db import SessionLocal

logger = logging.getLogger("kanoe.prompts")

TTL_SECONDS = 300  # 5-minute refresh window

# ── Static fallback registry ──────────────────────────────────────────────────

_REGISTRY: dict[str, dict] = {
    "conductor.general": {
        "current": "v1",
        "v1": (
            "You are Sasha, a warm and knowledgeable AI travel concierge. "
            "You specialise in Vietnam but can help with travel anywhere. "
            "Keep responses concise and conversational — you are speaking, not writing an essay. "
            "Maximum 3 sentences unless asked for more detail."
        ),
    },
    "conductor.merge": {
        "current": "v1",
        "v1": (
            "You are Sasha, a warm AI travel concierge. "
            "You have received responses from multiple specialist agents. "
            "Synthesize them into ONE natural, conversational response. "
            "Do not mention \"agents\" or \"specialists\" — just be Sasha. "
            "Keep it concise and warm. Max 4 sentences unless detail is needed."
        ),
    },
    "booking_confirmation.system": {
        "current": "v1",
        "v1": """You are Sasha's booking confirmation specialist. You help guests get their hotel's internal PMS reference number after booking through platforms like Booking.com, Expedia, Hotels.com, or Airbnb.

When a user gives you their booking details:
1. First find the hotel's contact details
2. Send a confirmation email to the hotel
3. Initiate an AI phone call to the hotel via Bland.ai
4. Also provide a phone script in case they want to call themselves

Always do email AND phone call simultaneously — both increase the chances of getting a response quickly.

Be efficient and professional. Collect all needed info before taking action:
- Hotel name and city/country
- Guest name
- Booking platform (Booking.com, Expedia etc)
- Booking reference number
- Check-in date
- Guest email (to receive hotel's response)""",
    },
}

# ── DB overlay cache: prompt_name → (text, expiry_epoch) ─────────────────────

_cache: dict[str, tuple[str, float]] = {}
_last_refresh: float = 0.0


async def _refresh_if_stale() -> None:
    global _last_refresh
    now = time.monotonic()
    if now - _last_refresh < TTL_SECONDS:
        return
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                text(
                    "SELECT prompt_name, prompt_text "
                    "FROM prompt_versions "
                    "WHERE is_active "
                    "ORDER BY created_at DESC"
                )
            )
            rows = result.fetchall()

        for row in rows:
            _cache[row.prompt_name] = (row.prompt_text, now + TTL_SECONDS)

        _last_refresh = now
        logger.debug("Loaded %d prompt(s) from DB", len(rows))
    except Exception:
        logger.warning("Could not refresh prompts from DB — using static registry")
        _last_refresh = now  # back off; don't hammer a down DB


def _static(name: str, version: Optional[str] = None) -> str:
    entry = _REGISTRY.get(name)
    if entry is None:
        raise KeyError(f"Unknown prompt: {name!r}")
    v = version or entry["current"]
    text_ = entry.get(v)
    if text_ is None:
        raise KeyError(f"Prompt {name!r} has no version {v!r}")
    return text_


def get_prompt(name: str, version: Optional[str] = None) -> str:
    """Synchronous accessor — returns DB-cached text or static fallback."""
    cached, expiry = _cache.get(name, ("", 0.0))
    if cached and expiry > time.monotonic():
        return cached
    return _static(name, version)


async def get_prompt_async(name: str, version: Optional[str] = None) -> str:
    """Async accessor — refreshes from DB if stale, then returns best available text."""
    await _refresh_if_stale()
    return get_prompt(name, version)


def current_version(name: str) -> str:
    entry = _REGISTRY.get(name)
    if entry is None:
        raise KeyError(f"Unknown prompt: {name!r}")
    return entry["current"]
