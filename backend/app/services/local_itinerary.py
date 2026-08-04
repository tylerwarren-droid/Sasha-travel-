"""
Deterministic, fully-local itinerary composer — the demo-speed replacement for the LLM
day-by-day generator in itinerary_agent.py.

Builds the SAME schema the LLM returns (title/summary/days[...]) in a few milliseconds from
local data only: route templates below, activities from the static Vietnam demo cache
(travel_search._static_get), hotels left to _enrich's VIETNAM_HOTELS pool selection. The
caller (build_itinerary) still runs _resolve_travellers and _enrich, so party sizing, real
hotel rates, booking links, images and the cost breakdown are identical to the LLM path.

Scope: first builds, structural rebuilds (days count, cities, party size) AND local
revisions of the stored plan — revise_local_itinerary handles add/remove city, hotel
swap / named hotel / cheaper / upgrade, and activity swap/remove in milliseconds.
build_itinerary tries the reviser first whenever a stored plan exists; only asks neither
path can parse fall back to the LLM builder.
"""

import copy
import re
from typing import Optional

from app.services.booking_links import _find_destinations
from app.services.hotels_db import VIETNAM_HOTELS
from app.services.travel_search import _static_get

# North → south, used to keep guest-named cities in a sane travel order.
_GEO_ORDER = ["Ha Giang", "Sapa", "Hanoi", "Ninh Binh", "Ha Long Bay", "Cat Ba",
              "Phong Nha", "Hue", "Da Nang", "Hoi An", "Nha Trang", "Da Lat", "Mui Ne",
              "Ho Chi Minh City", "Mekong Delta", "Con Dao", "Phu Quoc"]

# Default routes by trip length (city, nights-ish days there). Chosen for logical routing:
# arrive Hanoi, work south, depart from the last city.
_ROUTES = {
    3: [("Hanoi", 2), ("Ha Long Bay", 1)],
    4: [("Hanoi", 2), ("Ha Long Bay", 1), ("Hoi An", 1)],
    5: [("Hanoi", 2), ("Ha Long Bay", 1), ("Hoi An", 2)],
    6: [("Hanoi", 2), ("Ha Long Bay", 1), ("Hoi An", 2), ("Ho Chi Minh City", 1)],
    7: [("Hanoi", 2), ("Ha Long Bay", 1), ("Hoi An", 2), ("Ho Chi Minh City", 2)],
    8: [("Hanoi", 2), ("Ha Long Bay", 1), ("Hue", 1), ("Hoi An", 2), ("Ho Chi Minh City", 2)],
    9: [("Hanoi", 2), ("Ha Long Bay", 1), ("Hue", 1), ("Hoi An", 2), ("Ho Chi Minh City", 2),
        ("Mekong Delta", 1)],
    10: [("Hanoi", 2), ("Ha Long Bay", 1), ("Hue", 1), ("Hoi An", 2), ("Ho Chi Minh City", 2),
         ("Phu Quoc", 2)],
}

# Two day-description variants per city (first day / later days), written once so the plan
# reads warm without an LLM. {city} day titles pair with them below.
_DAY_TEXT = {
    "Hanoi": [
        ("Hello Hanoi", "Land in the capital and dive straight into the Old Quarter's maze of "
         "silk shops, street kitchens and lakeside temples. Finish with an egg coffee as the "
         "evening motorbikes hum past."),
        ("Hanoi like a local", "A slower morning around Hoan Kiem Lake, then eat your way "
         "through the city's legendary street food before an evening water puppet show."),
    ],
    "Ha Long Bay": [
        ("Karsts and kayaks", "Cruise out among Ha Long Bay's two thousand limestone islands, "
         "kayak into hidden lagoons and watch the sun drop behind the karsts from the deck."),
        ("Morning on the bay", "Wake on emerald water, visit a floating village and glide back "
         "past the karsts before returning to shore."),
    ],
    "Hue": [
        ("The imperial city", "Walk the moats and gates of the Nguyen citadel, then drift down "
         "the Perfume River to Thien Mu Pagoda as the dragon boats light up."),
        ("Royal Hue", "Tombs, gardens and bun bo Hue — the old capital at an unhurried pace."),
    ],
    "Hoi An": [
        ("Lanterns of Hoi An", "Wander the mustard-yellow old town, get measured by a tailor, "
         "and release a lantern onto the Thu Bon river after dark."),
        ("Hoi An hands-on", "Market shopping and a basket-boat ride before cooking your own "
         "five-dish Vietnamese lunch, with beach time at An Bang to finish."),
    ],
    "Da Nang": [
        ("Golden Bridge day", "Ride the cable car into the Ba Na hills to walk the Golden "
         "Bridge, then unwind on My Khe beach as the city lights come on."),
        ("Coast and caves", "Marble Mountains in the morning, surf or seafood along the "
         "beachfront for the rest of the day."),
    ],
    "Ho Chi Minh City": [
        ("Saigon energy", "Feel the pace shift in Vietnam's biggest city — war-history museums, "
         "rooftop views and the best banh mi of the trip."),
        ("Beneath and beyond Saigon", "Crawl the Cu Chi tunnels in the morning, then spend the "
         "evening eating your way through District 1 by scooter."),
    ],
    "Mekong Delta": [
        ("Into the delta", "Sampan rides through coconut-palm canals, floating markets and "
         "orchard islands — the river life of southern Vietnam."),
        ("Delta mornings", "Dawn at Cai Rang floating market with a noodle-soup breakfast "
         "afloat, then back through the islets."),
    ],
    "Phu Quoc": [
        ("Island time", "Trade cities for sand — cable-car over the sea, snorkel the southern "
         "islands and catch a legendary Phu Quoc sunset."),
        ("Beach day", "Nothing but white sand, warm water and a seafood feast — the trip's "
         "exhale before heading home."),
    ],
    "Sapa": [
        ("Up into the clouds", "Terraced rice valleys and Hmong villages on foot, with the "
         "Fansipan cable car if the clouds open."),
        ("Valley trails", "A gentle trek through Muong Hoa valley with lunch in a homestay."),
    ],
    "Nha Trang": [
        ("Bay of islands", "Boat-hop the bay with snorkel stops, then soak it all off in the "
         "Thap Ba mud baths."),
        ("Easy coast day", "Beach morning, seafood lunch, and the promenade at golden hour."),
    ],
    "Ninh Binh": [
        ("Ha Long on land", "Row through the Trang An grottoes and climb Hang Mua's 500 steps "
         "for the dragon-ridge view over the paddies."),
        ("Tam Coc slow day", "Cycle between karsts and rice fields, goat-meat lunch included."),
    ],
    "Da Lat": [
        ("Highland air", "Pine forests, waterfalls and coffee farms in Vietnam's cool-weather "
         "hill town."),
        ("Adventure day", "Canyoning for the brave or an easy-rider countryside loop for the "
         "rest."),
    ],
    "Mui Ne": [
        ("Dunes at dawn", "Sunrise over the red and white sand dunes, then the fairy stream "
         "and a lazy beach afternoon."),
        ("Wind and water", "Kitesurf lesson morning, seafood-street dinner night."),
    ],
    "Con Dao": [
        ("Wild island", "Vietnam's best reefs and a moving colonial history, far from any "
         "crowd."),
        ("Reef day", "Two-tank dive or a slow loop of the island's empty bays."),
    ],
    "Cat Ba": [
        ("Lan Ha Bay day", "Kayak the quieter sister of Ha Long — empty lagoons, floating "
         "villages and Cat Co beaches."),
        ("Island trails", "Hike the national park to the Ngu Lam viewpoint, then a slow "
         "beach afternoon."),
    ],
    "Phong Nha": [
        ("Into the caves", "Boat straight into Phong Nha cave, then the dizzying chambers "
         "of Paradise Cave."),
        ("Karst country", "Cycle the Bong Lai valley — duck farms, swimming holes and "
         "riverside hammocks."),
    ],
    "Ha Giang": [
        ("The great loop", "Switchbacks over the Ma Pi Leng pass — Vietnam's most jaw-"
         "dropping road, by easy-rider or jeep."),
        ("Market morning", "Hmong and Dao hill markets, then the Nho Que river gorge by "
         "boat."),
    ],
}

_GENERIC_TEXT = ("Exploring {city}", "A full day to explore {city} at your own pace — Sasha "
                 "has picked the best local experiences below.")

_WORD_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
              "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14}

_SLOTS = ["Morning", "Afternoon", "Evening"]


def _days_in_text(t: str) -> Optional[int]:
    t = (t or "").lower()
    m = re.search(r"\b(\d{1,2})\s*(?:-|\s)?(?:day|days|night|nights)\b", t)
    if m:
        n = int(m.group(1))
        return min(n, 14) if 2 <= n <= 30 else None
    for w, n in _WORD_NUMS.items():
        if re.search(rf"\b{w}\s+(?:day|days|night|nights)\b", t):
            return n
    if re.search(r"\b(?:a|one)\s+week\b", t):
        return 7
    if re.search(r"\btwo\s+weeks?\b|\b2\s+weeks?\b", t):
        return 14
    return None


def _resolve_days(message: str, history: list, default: int = 7) -> int:
    """Trip length from the guest's words — newest statement wins (same rule as travellers)."""
    if (n := _days_in_text(message)) is not None:
        return n
    for m in reversed(history or []):
        if isinstance(m, dict) and m.get("role") == "user":
            if (n := _days_in_text(m.get("content") or "")) is not None:
                return n
    return default


def _default_route(n_days: int) -> list:
    if n_days in _ROUTES:
        return list(_ROUTES[n_days])
    if n_days < 3:
        return [("Hanoi", n_days)]
    # 11+ days: stretch the 10-day route by adding slack days to the beach finale.
    route = list(_ROUTES[10])
    route[-1] = (route[-1][0], route[-1][1] + (n_days - 10))
    return route


def _blend_into(route: list, n_days: int, city: str) -> list:
    """`route` with `city` woven in at its geographic position, total days preserved — for a
    guest who showed interest in ONE place ("tell me about Sapa") or asked to add one.
    Ignoring it shipped a plan without the city they asked about; making the WHOLE trip that
    one city was the earlier collapse bug.
    """
    route = [tuple(s) for s in route]
    if any(c == city for c, _ in route):
        return route
    span = 2 if n_days >= 6 else 1
    # Insert in geographic order, but never before the Hanoi arrival day (Sapa has no
    # airport — trips start in a gateway city and detour from there).
    gi = _GEO_ORDER.index(city) if city in _GEO_ORDER else len(_GEO_ORDER)
    pos = 1
    for i, (c, _) in enumerate(route):
        if c in _GEO_ORDER and _GEO_ORDER.index(c) <= gi:
            pos = i + 1
    route.insert(pos, (city, span))
    # Give the inserted days back: shorten multi-day stops from the end first, then drop
    # trailing stops — never the city the guest actually asked for.
    total = sum(s for _, s in route)
    while total > n_days:
        for i in range(len(route) - 1, -1, -1):
            c, s = route[i]
            if c != city and s > 1:
                route[i] = (c, s - 1)
                total -= 1
                break
        else:
            for i in range(len(route) - 1, -1, -1):
                if route[i][0] != city:
                    total -= route[i][1]
                    route.pop(i)
                    break
            else:
                break
    return route


def _despans(current: dict) -> list:
    """[(city, span)] extracted from an existing (enriched) itinerary's days."""
    spans = []
    for d in (current or {}).get("days", []) or []:
        c = d.get("city") or "Vietnam"
        if spans and spans[-1][0] == c:
            spans[-1] = (c, spans[-1][1] + 1)
        else:
            spans.append((c, 1))
    return spans


def _rescale_spans(spans: list, n_days: int) -> list:
    """Stretch/shrink a route to a new day count, keeping the city sequence."""
    spans = [tuple(s) for s in spans if s[1] > 0]
    if not spans:
        return _default_route(n_days)
    total = sum(s for _, s in spans)
    i = 0
    while total < n_days:      # add days round-robin so no one stop balloons
        c, s = spans[i % len(spans)]
        spans[i % len(spans)] = (c, s + 1)
        total += 1
        i += 1
    while total > n_days:      # trim from the end: multi-day stops first, then drop stops
        for j in range(len(spans) - 1, -1, -1):
            c, s = spans[j]
            if s > 1:
                spans[j] = (c, s - 1)
                total -= 1
                break
        else:
            total -= spans[-1][1]
            spans.pop()
    return spans


def _route(n_days: int, named_cities: list, blend_single: bool = False,
           base: Optional[list] = None) -> list:
    """[(city, days)] plan. Guest-named cities win (geo-ordered, days spread evenly);
    a single city of INTEREST is blended into `base` (the current plan's route when one
    exists, else the default route) when blend_single is set."""
    cities = [c for c in _GEO_ORDER if c in (named_cities or [])]
    if len(cities) == 1 and blend_single:
        return _blend_into(base or _default_route(n_days), n_days, cities[0])
    if cities:
        base_, extra = divmod(n_days, len(cities))
        # Spread days across the named cities; earlier cities absorb the remainder.
        return [(c, base_ + (1 if i < extra else 0)) for i, c in enumerate(cities) if base_ + (1 if i < extra else 0) > 0]
    return base or _default_route(n_days)


def _activities_for(city: str) -> list:
    """The city's cached activity options (name + detail), else []. Local file only."""
    card = _static_get("activity", city) or {}
    return [o for o in card.get("options", []) if o.get("name") and not o.get("fallback")]

def _hotels_by_city(current: Optional[dict]) -> dict:
    """{city: hotel name} from an existing (enriched) plan — the guest's accepted/swapped
    hotels. Every recompose must carry these forward: a rebuild that reset day 1 to the
    pool default silently reverted the hotel the guest had JUST swapped away from (the
    live-demo failure: Capella back to the Sofitel they refused over cockroaches)."""
    out = {}
    for d in (current or {}).get("days", []) or []:
        h = d.get("hotel")
        name = (h or {}).get("name", "") if isinstance(h, dict) else (h or "")
        city = d.get("city")
        if city and name and city not in out:
            out[city] = name
    return out


def _compose(plan: list, keep_hotels: Optional[dict] = None) -> Optional[dict]:
    """Turn a [(city, span)] route into the pre-_enrich itinerary dict.

    `keep_hotels` = {city: hotel name} carried from the plan being replaced, so a rebuild
    (new day count, added city, new party) never reverts the guest's hotel choices —
    _enrich only pool-defaults cities that have no carried name."""
    if not plan or not _static_get("activity", "Hanoi"):
        return None  # cache absent — let the LLM path handle it
    keep_hotels = keep_hotels or {}
    n_days = sum(s for _, s in plan)

    days = []
    day_no = 0
    for city, span in plan:
        acts = _activities_for(city)
        used = 0
        for k in range(span):
            day_no += 1
            variants = _DAY_TEXT.get(city) or [_GENERIC_TEXT]
            if k < len(variants):
                title_t, desc_t = variants[k]
            else:
                # 3rd+ day in one city: a distinct free-day line instead of repeating the
                # day-2 text verbatim (which read as a copy-paste plan).
                title_t = f"{city} at your own pace"
                desc_t = ("A free-paced day — revisit favourites, browse the markets, or "
                          f"settle into a cafe and watch {city} go by.")
            # 2 activities on a first day in a city, remaining ones on later days — mirrors
            # how the cached set of 3 per city naturally splits across a 1-2 day stay. A
            # single-day stop gets ONE headline activity: its cached options are usually
            # alternatives (e.g. Ha Long's overnight cruise vs day cruise), not a sequence.
            take = (2 if span > 1 else 1) if k == 0 else max(1, len(acts) - used)
            todays = acts[used:used + take]
            used += len(todays)
            if not todays and acts:
                todays = [acts[day_no % len(acts)]]
            day = {
                "day": day_no,
                "city": city,
                "title": title_t.replace("{city}", city),
                "description": desc_t.replace("{city}", city),
                # First day of a stay names the carried hotel (guest's choice survives the
                # rebuild); "" lets _enrich pick the city's curated default / carry within.
                "hotel": keep_hotels.get(city, "") if k == 0 else "",
                "activities": [
                    {"time": _SLOTS[i % 3], "name": a["name"],
                     "blurb": (a.get("detail") or "").split(" · ")[-1]}
                    for i, a in enumerate(todays)
                ],
            }
            if day_no == 1:
                day["description"] = "Arrive and settle in. " + day["description"]
            days.append(day)
    if days:
        days[-1]["description"] += " Then it's time to head home with a camera roll full of Vietnam."

    stops = " → ".join(dict.fromkeys(c for c, _ in plan))
    return {
        "title": f"{n_days} Days in Vietnam: {stops}",
        "summary": f"A {n_days}-day journey through {stops}, balancing icons, food and downtime.",
        "days": days,
    }


def build_local_itinerary(message: str, history: list, current: Optional[dict] = None) -> Optional[dict]:
    """Compose the itinerary dict (pre-_enrich schema) from local data. Returns None only
    if the static cache is missing, so the caller can fall back to the LLM.

    `current` is the guest's stored plan (enriched payload): rebuilds keep ITS route (scaled
    to a new day count / re-priced for a new party) instead of re-deriving from a history
    window that may have scrolled past the cities they chose.
    """
    n_days = _resolve_days(message, history)
    # Cities in the BUILD message itself are an explicit route request — honour them even if
    # it's a single city ("just Hanoi please", exclusive words keep it exclusive; otherwise a
    # single message city is blended in). Cities that only appear in HISTORY: 2+ distinct
    # places -> spread the trip across them; exactly ONE ("tell me about Sapa… we'd love to
    # visit") -> weave it INTO the base route — dropping it shipped a plan without the city
    # the guest asked about, and making the whole trip that one city was the earlier
    # collapse bug ("7 Days in Vietnam: Hanoi").
    blend_single = False
    named = _find_destinations(message)
    if named:
        exclusive = any(w in (message or "").lower() for w in ("just ", "only "))
        blend_single = not exclusive
    elif (current or {}).get("days"):
        # A stored plan exists: its route already reflects every city choice so far. History
        # scanning here rewrote the route on a simple "make it 10 days" because revision
        # chatter mentions cities ("skip Ha Long", "the hotel in Hanoi").
        named = []
    else:
        hist_text = " ".join(
            m.get("content", "") for m in (history or [])[-8:]
            if isinstance(m, dict) and m.get("role") == "user"
        )
        named = list(dict.fromkeys(_find_destinations(hist_text)))
        blend_single = True
    base = _rescale_spans(_despans(current), n_days) if (current or {}).get("days") else None
    plan = _route(n_days, named, blend_single=blend_single, base=base)
    return _compose(plan, keep_hotels=_hotels_by_city(current))


# ── Local revisions ─────────────────────────────────────────────────────────
# Sasha's own closing line invites changes ("tell me if you'd like to swap any of the hotels
# or activities"), so revisions are ON the demo path. The LLM reviser was slow (~25s) and
# never even saw the current plan. These handle the common asks against the STORED plan in
# milliseconds; anything they can't parse still falls back to the LLM builder.

_norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())

_ADD_WORDS = ("add", "include", "also visit", "also go", "can we visit", "can we go",
              "want to visit", "want to see", "as well", "put in", "squeeze in")
_REMOVE_WORDS = ("remove", "skip", "drop", "cut", "take out", "without", "get rid",
                 "don't want", "dont want", "no longer", "not interested in")
_SWAP_WORDS = ("swap", "change", "different", "another", "switch", "replace", "instead")
_CHEAPER_WORDS = ("cheaper", "less expensive", "budget", "lower the price", "more affordable",
                  "cost less", "too expensive", "bring the price down")
_UPGRADE_WORDS = ("upgrade", "more luxur", "luxury", "nicer", "fancier", "high end",
                  "high-end", "best hotel", "better hotel", "five star", "5 star", "5-star")

_ACT_STOP = {"tour", "trip", "day", "class", "ride", "the", "and", "with", "boat"}


def _preenrich_days(days: list) -> list:
    """Enriched days back to the pre-_enrich shape (hotel dict -> name string) so the same
    enrichment pass can re-price/re-link the revised plan identically to a fresh build."""
    out = []
    for d in days or []:
        h = d.get("hotel")
        hname = (h or {}).get("name", "") if isinstance(h, dict) else (h or "")
        out.append({
            "day": d.get("day"),
            "city": d.get("city") or "Vietnam",
            "title": d.get("title", ""),
            "description": d.get("description", ""),
            "hotel": hname,
            "activities": [{"time": a.get("time", "Morning"), "name": a.get("name", ""),
                            "blurb": a.get("blurb", "")} for a in (d.get("activities") or [])],
        })
    return out


def _apply_hotels(days: list, choice: dict) -> None:
    """Set the chosen hotel NAME on the first day of each affected city stay ('' carries)."""
    prev_city = None
    for d in days:
        city = d["city"]
        if city in choice:
            d["hotel"] = choice[city] if city != prev_city else ""
        prev_city = city


def _pick_hotel(city: str, current_name: str, mode: str, target: Optional[str] = None) -> Optional[str]:
    pool = VIETNAM_HOTELS.get(city) or []
    if not pool:
        return None
    if target:
        return target
    others = [h for h in pool if h.get("name") != current_name] or pool
    if mode == "cheaper":
        pick = min(others, key=lambda h: h.get("price_from", 0))
    elif mode == "upgrade":
        pick = max(others, key=lambda h: h.get("price_from", 0))
    else:  # rotate
        names = [h.get("name") for h in pool]
        idx = names.index(current_name) if current_name in names else -1
        pick = pool[(idx + 1) % len(pool)]
        if pick.get("name") == current_name and len(pool) > 1:
            pick = pool[(idx + 2) % len(pool)]
    return pick.get("name")


def revise_local_itinerary(current: dict, message: str,
                           hotel_swap: Optional[dict] = None) -> Optional[dict]:
    """Apply a revision to the STORED plan. Returns a pre-_enrich dict, or None when the ask
    isn't one of the supported shapes (caller falls back to the LLM builder).

    `hotel_swap` = {"name", "city"} — an ALREADY-RESOLVED hotel swap from the conductor
    (the guest confirmed a specific property Sasha offered). Applied verbatim, no text
    parsing: the name may be a live-searched hotel that isn't in the curated pool, which
    the token matcher below can never find (it would rotate to the wrong property)."""
    if not (current or {}).get("days"):
        return None
    if hotel_swap and hotel_swap.get("name"):
        days = _preenrich_days(current["days"])
        cities = [d["city"] for d in days]
        city = hotel_swap.get("city")
        scope = [city] if city in cities else list(dict.fromkeys(cities))
        _apply_hotels(days, {c: hotel_swap["name"] for c in scope})
        return {"title": current.get("title", ""), "summary": current.get("summary", ""),
                "days": days}
    low = (message or "").lower()
    spans = _despans(current)
    n_days = sum(s for _, s in spans)
    plan_cities = [c for c, _ in spans]
    named = [c for c in dict.fromkeys(_find_destinations(message))]

    # ── Add / remove a city (route change -> recompose text/activities for the new route)
    if named:
        for city in named:
            if any(w in low for w in _REMOVE_WORDS) and city in plan_cities and len(plan_cities) > 1:
                kept = [(c, s) for c, s in spans if c != city]
                data = _compose(_rescale_spans(kept, n_days), keep_hotels=_hotels_by_city(current))
                return data
            if any(w in low for w in _ADD_WORDS) and city not in plan_cities:
                data = _compose(_blend_into(spans, n_days, city), keep_hotels=_hotels_by_city(current))
                return data

    # ── Hotel changes (preserve the current days; only the hotel assignment changes)
    hotel_word = ("hotel" in low) or ("stay" in low) or ("resort" in low) or ("accommodation" in low)
    # A specific property named? ("change the Hanoi hotel to the Capella"). Guests say the
    # distinctive word, not the full listing name — match on significant tokens too.
    _generic = {"hotel", "resort", "legend", "luxury", "beach", "bay", "spa"} | {
        _norm(c) for c in plan_cities} | {w.lower() for c in plan_cities for w in c.split()}
    target_city, target_name = None, None
    msg_norm = _norm(message)
    msg_tokens = set(re.findall(r"[a-z]{5,}", low))
    for city in plan_cities:
        for h in VIETNAM_HOTELS.get(city) or []:
            name = h.get("name") or ""
            distinct = {w.lower() for w in re.findall(r"[A-Za-z]{5,}", name)} - _generic
            if (_norm(name) and _norm(name) in msg_norm) or (distinct & msg_tokens):
                target_city, target_name = city, name
                break
        if target_name:
            break
    wants_hotel_change = target_name or (hotel_word and any(
        w in low for w in _SWAP_WORDS + _CHEAPER_WORDS + _UPGRADE_WORDS))
    global_price_move = (not hotel_word) and (
        any(w in low for w in _CHEAPER_WORDS) or any(w in low for w in _UPGRADE_WORDS))
    if wants_hotel_change or global_price_move:
        mode = "cheaper" if any(w in low for w in _CHEAPER_WORDS) else (
            "upgrade" if any(w in low for w in _UPGRADE_WORDS) else "rotate")
        scope = [c for c in (named or []) if c in plan_cities]
        if target_city:
            scope = [target_city]
        if not scope:
            scope = list(dict.fromkeys(plan_cities))
        days = _preenrich_days(current["days"])
        # Current hotel per city (from the first day of that city's stay)
        current_by_city = {}
        for d in days:
            if d["city"] not in current_by_city and d["hotel"]:
                current_by_city[d["city"]] = d["hotel"]
        # Direction check: naming a property can mean EITHER "change TO it" or "get me AWAY
        # from it". "I want to swap OUT the Sofitel — I don't want to stay there" matched the
        # Sofitel as the target and cheerfully re-assigned the guest the very hotel they were
        # refusing. When the named property IS the current hotel for its city, it's the thing
        # being replaced — rotate (or price-move) away from it instead.
        if target_name and target_city and current_by_city.get(target_city) == target_name:
            target_name = None
        choice = {}
        for city in scope:
            pick = _pick_hotel(city, current_by_city.get(city, ""), mode,
                               target_name if city == target_city else None)
            if pick:
                choice[city] = pick
        if not choice:
            return None
        _apply_hotels(days, choice)
        return {"title": current.get("title", ""), "summary": current.get("summary", ""),
                "days": days}

    # ── Remove / swap a specific activity by name
    if any(w in low for w in _REMOVE_WORDS + _SWAP_WORDS):
        msg_words = {w for w in re.findall(r"[a-z]{4,}", low)} - _ACT_STOP
        days = _preenrich_days(current["days"])
        for d in days:
            for a in list(d["activities"]):
                act_words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", a["name"])} - _ACT_STOP
                if act_words and (act_words & msg_words):
                    d["activities"].remove(a)
                    if any(w in low for w in _SWAP_WORDS):
                        # Replace with an unused cached activity for that city, if any.
                        used = {x["name"] for dd in days for x in dd["activities"]}
                        for cand in _activities_for(d["city"]):
                            if cand["name"] not in used and cand["name"] != a["name"]:
                                d["activities"].append({
                                    "time": a.get("time", "Afternoon"),
                                    "name": cand["name"],
                                    "blurb": (cand.get("detail") or "").split(" · ")[-1]})
                                break
                    return {"title": current.get("title", ""),
                            "summary": current.get("summary", ""), "days": days}

    return None
