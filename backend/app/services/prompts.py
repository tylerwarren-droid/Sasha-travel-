"""
Prompt registry with DB-backed versioning via Supabase REST API.

Static fallbacks are always available. On first call (and every TTL_SECONDS),
active rows from prompt_versions are fetched via the REST API and overlaid.
If the API is unreachable the static registry is used transparently.
"""

import asyncio
import logging
import os
import time
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("kanoe.prompts")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
TTL_SECONDS = 300

# Appended to every specialist agent's system prompt. The final reply is read aloud by a
# real-time avatar, so it must be short and contain no markdown/lists.
VOICE_BREVITY = (
    "\n\n--- VOICE MODE (CRITICAL) ---\n"
    "This is a real-time spoken conversation and your reply is READ ALOUD by an avatar. "
    "Reply in at most ONE or TWO short sentences. Never use markdown, lists, bullet points, "
    "headings, numbered steps, tables, or emojis. Ask only one question at a time. "
    "Keep any options to a brief spoken phrase, not a list."
)

_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
}

# ── Static fallback registry ──────────────────────────────────────────────────

_REGISTRY: dict[str, dict] = {
    "conductor.general": {
        "current": "v1",
        "v1": (
            "You are Sasha, a warm, knowledgeable AI travel concierge specialising in Vietnam. "
            "This is a REAL-TIME VOICE conversation, so keep EVERY reply to one or two short "
            "spoken sentences — never longer. Be warm and natural, ask only ONE question at a "
            "time, and never use lists, bullet points, headings, or numbered steps. "
            "CRITICAL: you cannot do anything after you finish speaking — there is no "
            "background work, no email, no document being prepared. NEVER say you will "
            "'create', 'build', 'put together', 'send', or 'have something ready shortly' "
            "later. Instead, give the actual suggestion right now, spoken and concise: e.g. "
            "for a trip, name a couple of stops in one sentence and ask if they'd like you to "
            "go day by day. Always deliver value in the same turn; never defer or promise a "
            "follow-up that won't come. "
            "Once you know who is travelling, roughly how many days, and their main interests, "
            "OFFER to build the full plan — e.g. 'Shall I put together your full day-by-day "
            "itinerary?' — then STOP and wait for their answer. "
            "NEVER claim the itinerary is ready, built, done, or 'on the right', and never say "
            "you'll have it ready shortly — you do NOT build or display it yourself, and it "
            "does NOT appear just because you say so. Only OFFER; a separate step builds and "
            "shows it on the right after the guest confirms."
        ),
    },
    "conductor.merge": {
        "current": "v1",
        "v1": (
            "You are Sasha, a warm AI travel concierge on a REAL-TIME VOICE call. "
            "Synthesize the specialist responses into ONE natural reply of at most TWO short "
            "spoken sentences. Never mention \"agents\" or \"specialists\", never use lists or "
            "bullet points — just speak as Sasha, and ask only one question at a time. "
            "Never promise to prepare or deliver something later — give the actual answer now."
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

# ── REST-backed overlay cache: prompt_name → (text, expiry_epoch) ─────────────

_cache: dict[str, tuple[str, float]] = {}
_last_refresh: float = 0.0
_refreshing: bool = False


async def _do_refresh() -> None:
    """Fetch active prompt rows and overlay them onto the cache. Runs in the background."""
    global _last_refresh, _refreshing
    now = time.monotonic()
    try:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            return  # no DB configured — static registry is authoritative
        async with httpx.AsyncClient() as http:
            r = await http.get(
                f"{SUPABASE_URL}/rest/v1/prompt_versions",
                params={
                    "select": "prompt_name,prompt_text",
                    "is_active": "eq.true",
                    "order": "created_at.desc",
                },
                headers=_HEADERS,
                timeout=5,
            )
        rows = r.json() if r.status_code == 200 else []
        for row in rows:
            _cache[row["prompt_name"]] = (row["prompt_text"], now + TTL_SECONDS)
        logger.debug("Loaded %d prompt(s) from REST API", len(rows))
    except Exception:
        logger.warning("Could not refresh prompts from REST API — using static registry")
    finally:
        _last_refresh = now
        _refreshing = False


def _kick_refresh_if_stale() -> None:
    """Start a background refresh if the cache is stale — NEVER awaited.

    The conductor calls this on every turn. Awaiting a Supabase round-trip here would put
    the DB on the spoken-response hot path (adding up to the 5s timeout to one turn every
    TTL). Instead we fire-and-forget: the current cached/static prompt is served instantly
    and the refresh updates the cache for subsequent turns.
    """
    global _refreshing
    now = time.monotonic()
    if _refreshing or (now - _last_refresh < TTL_SECONDS):
        return
    _refreshing = True
    try:
        asyncio.get_running_loop().create_task(_do_refresh())
    except RuntimeError:
        # No running loop (sync context) — skip; the next async call will refresh.
        _refreshing = False


def _static(name: str, version: Optional[str] = None) -> str:
    entry = _REGISTRY.get(name)
    if entry is None:
        raise KeyError(f"Unknown prompt: {name!r}")
    v = version or entry["current"]
    text = entry.get(v)
    if text is None:
        raise KeyError(f"Prompt {name!r} has no version {v!r}")
    return text


def get_prompt(name: str, version: Optional[str] = None) -> str:
    """Synchronous accessor — returns REST-cached text or static fallback."""
    cached, expiry = _cache.get(name, ("", 0.0))
    if cached and expiry > time.monotonic():
        return cached
    return _static(name, version)


async def get_prompt_async(name: str, version: Optional[str] = None) -> str:
    """Async accessor — kicks a background refresh if stale, returns best text instantly.

    Supabase is intentionally OFF the response path: this returns the cached (or static)
    prompt without awaiting any network call.
    """
    _kick_refresh_if_stale()
    return get_prompt(name, version)


def current_version(name: str) -> str:
    entry = _REGISTRY.get(name)
    if entry is None:
        raise KeyError(f"Unknown prompt: {name!r}")
    return entry["current"]
