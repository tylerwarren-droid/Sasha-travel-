"""
Booking deep-links.

A travel concierge has to be actionable, not just conversational. For each turn we surface
a few real "book this" links based on the destination(s) Sasha is talking about. These are
deep search links into established booking platforms (Booking.com, Google Flights,
GetYourGuide, etc.) — no API keys, no integration, and they drop the user straight onto a
pre-filtered results page. The frontend renders them as clickable buttons under the chat.
"""

from urllib.parse import quote_plus

# Vietnam destinations → display name. Keys are matched (lowercased, substring) against the
# user message and Sasha's reply.
DESTINATIONS = {
    "hanoi": "Hanoi", "ha noi": "Hanoi",
    "ho chi minh": "Ho Chi Minh City", "saigon": "Ho Chi Minh City",
    "da nang": "Da Nang", "danang": "Da Nang",
    "hoi an": "Hoi An", "hoian": "Hoi An",
    "hue": "Hue",
    "sapa": "Sapa", "sa pa": "Sapa",
    "ha long": "Ha Long Bay", "halong": "Ha Long Bay",
    "phu quoc": "Phu Quoc", "phuquoc": "Phu Quoc",
    "nha trang": "Nha Trang",
    "da lat": "Da Lat", "dalat": "Da Lat",
    "ninh binh": "Ninh Binh",
    "mui ne": "Mui Ne",
    "mekong": "Mekong Delta",
    "con dao": "Con Dao",
}

# Intents for which we should always surface links even without a named destination.
_BOOKING_INTENTS = {"golf", "restaurant", "smart_sasha", "beauty", "health", "booking_confirmation"}


def _find_destinations(text: str) -> list:
    t = (text or "").lower()
    found = []
    for key, name in DESTINATIONS.items():
        if key in t and name not in found:
            found.append(name)
    return found


def build_booking_links(user_message: str, response_text: str, intents: list, context: str = "") -> list:
    """Return up to 4 actionable booking links for the current turn (or [] when irrelevant).

    `context` is recent conversation text — checked last so the destination persists across
    turns (e.g. the city was named earlier, not in this exact message).
    """
    dests = _find_destinations(user_message) or _find_destinations(response_text) or _find_destinations(context)
    has_booking_intent = any(i in _BOOKING_INTENTS for i in (intents or []))
    if not dests and not has_booking_intent:
        return []  # generic chit-chat — don't clutter with links

    primary = dests[0] if dests else "Vietnam"
    where = primary if primary != "Vietnam" else "Vietnam"
    q_where = quote_plus(f"{where}, Vietnam")
    links = []

    if "golf" in (intents or []):
        links.append({"label": f"Tee times · {where}",
                      "url": f"https://www.google.com/search?q={quote_plus(where + ' Vietnam golf tee times booking')}",
                      "type": "golf"})
    if "restaurant" in (intents or []):
        links.append({"label": f"Restaurants · {where}",
                      "url": f"https://www.google.com/maps/search/{quote_plus('restaurants ' + where + ' Vietnam')}",
                      "type": "restaurant"})

    # Core travel links — always useful for a destination.
    links.append({"label": f"Hotels · {where}",
                  "url": f"https://www.booking.com/searchresults.html?ss={q_where}",
                  "type": "hotel"})
    links.append({"label": f"Flights · {where}",
                  "url": f"https://www.google.com/travel/flights?q={quote_plus('flights to ' + where + ' Vietnam')}",
                  "type": "flight"})
    links.append({"label": f"Things to do · {where}",
                  "url": f"https://www.getyourguide.com/s/?q={q_where}",
                  "type": "activity"})

    seen, out = set(), []
    for link in links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        out.append(link)
    return out[:4]
