"""
Ideas agent — generates a small set of ready-made trip ideas, personalized to the guest.

These are the cards on the workspace's Ideas tab. They are deliberately NOT full itineraries:
an idea is a pitch (title, hook, shape, rough price) that costs one cheap LLM call, whereas a
real itinerary costs a slow enrichment pass (photos, hotel lookups, booking links). When the
guest taps "Build this", the frontend sends a normal conductor turn built from the idea's
`build_prompt`, so the itinerary is produced by the SAME path as any spoken request — one
builder, one set of rules, no second source of truth for what a trip looks like.

Personalization comes from the guest's saved preferences and past trips, so a returning guest
is not pitched the places they have already been.
"""

import asyncio
import json
import re
from collections import OrderedDict

from app.services.llm import client, FAST_MODEL
from app.services.foto_agent import search_photos, FALLBACK_PHOTOS, UNSPLASH_ACCESS_KEY

# Cache key = profile + session. Two competing needs: the cards must NOT reshuffle under the
# guest every time they flick back to the tab mid-conversation (so we cache), but they must
# also not be the same three trips on every visit forever (so the key includes the session —
# a new call means a fresh set). Bounded so a long-lived process can't grow this unchecked.
_CACHE: "OrderedDict[str, list]" = OrderedDict()
_CACHE_MAX = 64
_LOCK = asyncio.Lock()

_SYSTEM = """You are Sasha, a Vietnam travel concierge. Propose exactly 3 DISTINCT ready-made \
trip ideas for this guest, as a SINGLE JSON object and NOTHING else (no markdown).

Schema:
{
  "ideas": [
    {
      "title": "<3-4 word evocative name, no colon>",
      "blurb": "<1 sentence, max 22 words: the route and what makes it special>",
      "days": <integer 4-10>,
      "tags": ["<2-3 one-word themes, e.g. Culture, Food, Golf, Island>"],
      "estimated_total_usd": <integer, realistic for the whole party at their comfort level>,
      "match": "<short reason it suits THIS guest, max 8 words, or empty string>",
      "photo_query": "<2-4 words naming the single most photogenic REAL place in this trip, \
for an image search, e.g. 'Hue Imperial Citadel'>",
      "build_prompt": "<a first-person instruction from the guest asking Sasha to build this \
exact trip, naming the cities, the number of days, the party size and the interests>"
    }
  ]
}

Rules:
- Use REAL Vietnamese destinations with logical routing (do not criss-cross the country).
- Ideas must be genuinely different from each other in region AND in pace.
- The FIRST idea must be the strongest fit for the guest's stated preferences; give it a
  "match" reason. Leave "match" empty for ideas that are a deliberate change of pace.
- Do NOT repeat a place the guest has already visited unless the idea is explicitly a
  different experience of it; prefer somewhere new.
- Prices must reflect the party size and the guest's comfort level, not a generic budget.
- Vietnam is wide: draw from its full range (the north, the centre, the highlands, the south,
  the delta, the islands). Do not default to the same famous shortlist every time.
- Output ONLY the JSON object."""


def _parse_json(raw: str):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(raw[s:e + 1])
    except Exception:
        return None


# Last-resort cards. If the LLM is down, the Ideas tab must still show something bookable
# rather than an empty panel — these are generic (no "match" claim, since nothing was
# personalized) and still route through the same build_prompt path.
_FALLBACK = [
    {
        "title": "Heritage & Flavours",
        "blurb": "Hanoi, Ha Long Bay and Hoi An — boutique heritage stays, street food, and a cooking class.",
        "days": 7,
        "tags": ["Culture", "Food"],
        "estimated_total_usd": 8400,
        "match": "",
        "photo_query": "Ha Long Bay",
        "build_prompt": "Build me a 7-day Vietnam itinerary for 2 travellers through Hanoi, Ha Long Bay and Hoi An, with boutique heritage hotels, street food walks and a cooking class.",
    },
    {
        "title": "Coast & Fairways",
        "blurb": "Da Nang and Hoi An — championship links in the morning, beach and Marble Mountains after.",
        "days": 6,
        "tags": ["Golf", "Beach"],
        "estimated_total_usd": 9200,
        "match": "",
        "photo_query": "Da Nang beach",
        "build_prompt": "Build me a 6-day Vietnam golf itinerary for 2 travellers around Da Nang and Hoi An, with three championship courses, beach time and a resort stay.",
    },
    {
        "title": "Phu Quoc Slow Escape",
        "blurb": "One island, one villa, no schedule — reef snorkelling, night market, and long sunsets.",
        "days": 5,
        "tags": ["Island", "Quiet"],
        "estimated_total_usd": 6700,
        "photo_query": "Phu Quoc island beach",
        "build_prompt": "Build me a relaxed 5-day Phu Quoc island itinerary for 2 travellers with a beach villa, snorkelling and the night market.",
        "match": "",
    },
]


def _set_photo(idea: dict, photo: dict) -> None:
    idea["image"] = photo.get("url")
    idea["image_thumb"] = photo.get("thumb") or photo.get("url")
    idea["image_by"] = photo.get("photographer")


async def _attach_photos(ideas: list) -> None:
    """Give each idea a photo of the place, in place.

    With an Unsplash key, each idea gets a real photo of ITS destination (concurrent lookups,
    so three ideas cost one round-trip, not three). Without a key, foto_agent serves the same
    curated fallback list for every query — taking [0] each time painted all three cards with
    the identical Ha Long Bay shot, which looks broken. So in that case we deal out DIFFERENT
    curated photos by index instead: still generic, but no longer visibly wrong.

    A photo failure never fails the tab — the card's gradient shows through.
    """
    if not UNSPLASH_ACCESS_KEY:
        for i, idea in enumerate(ideas):
            if FALLBACK_PHOTOS:
                _set_photo(idea, FALLBACK_PHOTOS[i % len(FALLBACK_PHOTOS)])
        return

    async def one(idea: dict):
        q = (idea.get("photo_query") or idea.get("title") or "").strip()
        if not q:
            return
        try:
            photos = await search_photos(f"{q} Vietnam", count=1)
            if photos:
                _set_photo(idea, photos[0])
        except Exception as e:
            print(f"[ideas] photo lookup failed for {q!r}: {e}")

    await asyncio.gather(*(one(i) for i in ideas), return_exceptions=True)


def _profile_text(profile: dict) -> str:
    """Flatten the guest profile into the prompt's context block."""
    name = profile.get("name") or "the guest"
    travellers = profile.get("travellers") or []
    prefs = profile.get("preferences") or []
    past = profile.get("past_trips") or []
    party = ", ".join(t for t in travellers if t) or "1 traveller"
    pref_lines = "; ".join(str(p) for p in prefs if p) or "none recorded"
    past_lines = "; ".join(str(t) for t in past if t) or "no past trips on file"
    return (
        f"Guest: {name}\n"
        f"Travelling as: {party}\n"
        f"Known preferences: {pref_lines}\n"
        f"Already visited: {past_lines}"
    )


def _signature(profile: dict, session: str = "") -> str:
    try:
        return json.dumps(profile, sort_keys=True) + "|" + (session or "")
    except Exception:
        return str(profile) + "|" + (session or "")


def _remember(sig: str, ideas: list) -> None:
    _CACHE[sig] = ideas
    _CACHE.move_to_end(sig)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


async def generate_ideas(profile: dict, session: str = "", force: bool = False) -> dict:
    """Return 3 personalized trip ideas for this guest profile.

    Stable within a session (so the cards don't reshuffle when the guest switches tabs) but
    fresh across sessions, so a returning guest isn't pitched the same three trips forever.
    Pass force=True to regenerate now (the tab's Refresh control).
    Never raises — a failure returns the generic fallback cards so the tab always renders.
    """
    sig = _signature(profile, session)
    if not force:
        cached = _CACHE.get(sig)
        if cached:
            return {"ideas": cached, "cached": True}

    async with _LOCK:
        # Another request may have populated the cache while we waited for the lock.
        if not force and _CACHE.get(sig):
            return {"ideas": _CACHE[sig], "cached": True}
        try:
            msg = await client.messages.create(
                model=FAST_MODEL,
                max_tokens=1400,
                system=_SYSTEM,
                messages=[{"role": "user", "content": _profile_text(profile)}],
            )
            raw = "".join(getattr(b, "text", "") for b in msg.content)
            data = _parse_json(raw) or {}
            ideas = data.get("ideas") or []
            clean = [i for i in ideas if i.get("title") and i.get("build_prompt")][:3]
            if not clean:
                raise ValueError("no usable ideas in model output")
            await _attach_photos(clean)
            _remember(sig, clean)
            return {"ideas": clean, "cached": False}
        except Exception as e:
            print(f"[ideas] generation failed, serving fallback: {e}")
            fallback = [dict(i) for i in _FALLBACK]
            await _attach_photos(fallback)
            return {"ideas": fallback, "cached": False, "fallback": True}
