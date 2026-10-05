"""Sasha 143 · A HOTEL STAY ON THE WEB, as on WhatsApp: "a hotel in Madrid, Spain from 2027-03-01 to 2027-03-04 for 1"
(the products' trip-plan hand-off, or a guest's own words) → real hotels found on Google, each with "Reserve (TEST)".

Before: the web's hotel cards came only from a curated list (and a model-written one) that has no Madrid, so the
hand-off fell to the general chat, which either failed ("a brief connection issue", CR's rehearsal) or PROMISED cards
that never came. Now the stay is read the same way as WhatsApp (guest_whatsapp.stay_of) and found the same way
(/venues/find, what="hotel"); a card says only what Google's listing says — no price is invented (the web card shows
the address where a curated card shows a price), and its "Reserve (TEST)" says no hotel is contacted.
Search only: nothing is contacted, nothing stored. When nothing is found, it says so — never "you'll see them".
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

log = logging.getLogger("booking_signer.hotel_web")

SHOW = 3


def _plural(n: int, one: str) -> str:
    return f"{n} {one}{'' if n == 1 else 's'}"


async def web_turn(message: str, user_id: Optional[str], now: datetime) -> Optional[dict]:
    """None unless the message is a hotel stay with a place and dates; then the conductor's answer for it."""
    from . import guest_whatsapp as GW, sentences as SN
    if not user_id or not GW.HOTEL.search(message or ""):
        return None
    stay = GW.stay_of(message, now)
    if stay is None:
        return None
    f, where = stay["find"], stay["find"].get("where") or stay["where"]
    city = where.split(",")[0].strip()
    status, j = await GW.api(user_id, "POST", "/api/booking/venues/find", {"what": "hotel", "where": where, "country": f.get("country")})
    cands = (j or {}).get("candidates") or [] if status == 200 else []
    order = (((j or {}).get("ranking") or {}).get("orders") or {}).get("rated") or [c.get("place_id") for c in cands]
    by = {c.get("place_id"): c for c in cands}
    shown: List[dict] = [by[i] for i in order if i in by and i != "sasha-test-venue" and by[i].get("name")][:SHOW]
    nights, party, day = stay["nights"], stay["party"], SN.day_words(stay["a"])
    head = f"Hotels in {city} for {_plural(nights, 'night')} from {day}, {party} {'person' if party == 1 else 'people'}"
    if not shown:
        why = "Google's search didn't answer" if status != 200 else "Google found none"
        return _answer(f"{head}: {why}, so I have none to show you yet. Try another area or name a hotel.", [])
    # Sasha 155 · photo cards, as on WhatsApp: each hotel's OWN share picture from its own site, within a short budget
    # (the late ones are left to fill the cache; a card never waits longer, and none is shown rather than a stand-in)
    try:
        photos, _late = await GW._photos_within(shown, GW.photo_wait() + 1.5)
    except Exception as e:
        log.info("[hotel_web] no photos: %s", type(e).__name__)
        photos = {}
    hotels = [{"name": c["name"], "city": city, "nights": nights, "checkin": stay["a"], "party": party,
               "address": c.get("address"), "rating": c.get("rating"), "rating_count": c.get("rating_count"),   # Google's 1–5, as its listing says
               "book_url": c.get("listing_url"), "source": "google",
               **({"photo": photos[c["place_id"]], "photo_source": c.get("website"),
                   **({"photo_google": True, "photo_source": c.get("listing_url"), "photo_by": (c.get("gphoto") or {}).get("by") or []}
                      if _is_google(photos[c["place_id"]]) else {})} if photos.get(c.get("place_id")) else {})}
              for c in shown]
    return _answer(f"{head}, from Google Maps. On each: “Reserve (TEST)” makes a TEST booking (no hotel contacted, "
                   f"nothing charged); “View” opens its Google listing.", hotels)


def _is_google(url: str) -> bool:
    """Sasha 156 · Google's listing photo (the fallback), credited as Google's — never as the hotel's own."""
    from urllib.parse import urlsplit
    h = (urlsplit(url or "").hostname or "").lower()
    return h.endswith(".googleusercontent.com") or h.endswith("googleapis.com")


def _answer(text: str, hotels: List[dict]) -> dict:
    return {"response": text, "intents": ["hotel"], "photos": [], "tools_used": ["venues_find"], "links": [], "hotels": hotels,
            "bookings": [], "itinerary": None, "action": None, "booking_ref": None, "itinerary_id": None, "payment_item": None,
            "saved_card": None}


__all__ = ["web_turn"]
