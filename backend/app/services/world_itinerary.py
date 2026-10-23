"""Sasha 211 · SASHA PLANS ANY COUNTRY (the /next agent's propose_trip, beside the Vietnam planner).

  route    one model call: the days, the cities in a sensible order (no criss-crossing), a highlight per place, the airports
           to fly into and home from — from the intake (where, how long, who, what they love, from where)
  stays    REAL hotels from Google Places per city (name, Google's own rating and review count, area, its photo) — never an
           invented one; the nightly price is an ESTIMATE (country × the listing's price level / rating), always labelled "est."
  photos   a picture per place (Unsplash, as the Vietnam planner's), a hotel's own (its listing's)
The plan has the Vietnam planner's shape (days[].hotel {name, price_from (USD), …}, days[].image, activities[]), so the plan
store, the basket, the Trip view and the booking read it as they read any plan. Vietnam's curated list stays the Vietnam
planner's (agapi routes Vietnam there); this one never limits to it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import quote_plus

log = logging.getLogger("world_itinerary")
MODEL = os.getenv("SASHA_WORLD_PLANNER_MODEL", "claude-haiku-4-5")
from booking_signer import fx as FX   # noqa: E402 · Sasha 249 · ONE RATE: every USD→EUR is booking_signer/fx.py's dated rate
USD_EUR = FX.rate("USD")   # Sasha 249 · kept for any reader of the name; the conversion below asks fx when it's made

# a good, well-rated hotel for two, one night, in USD — the base of the ESTIMATE (never shown as a price, only as "est.")
NIGHT_USD = {"JP": 210, "EC": 105, "MA": 120, "PT": 150, "VN": 90, "ES": 160, "FR": 220, "IT": 200, "GB": 230, "IE": 210, "US": 240,
             "CA": 200, "MX": 130, "PE": 110, "CO": 100, "AR": 110, "CL": 130, "BR": 120, "CR": 150, "TH": 95, "ID": 100, "MY": 90,
             "SG": 260, "KH": 80, "LA": 75, "PH": 100, "IN": 100, "LK": 95, "NP": 70, "CN": 130, "KR": 160, "TW": 140, "AU": 210,
             "NZ": 190, "ZA": 130, "KE": 170, "TZ": 180, "EG": 110, "TR": 120, "GR": 170, "HR": 160, "DE": 170, "NL": 200,
             "CH": 280, "AT": 170, "IS": 260, "NO": 230, "SE": 190, "DK": 220, "CZ": 130, "HU": 120, "PL": 110, "AE": 220, "JO": 140}
DEFAULT_NIGHT_USD = 150
LEVEL = {1: 0.6, 2: 0.85, 3: 1.25, 4: 1.9}

_SYSTEM = """You are Sasha's trip planner for ANY country. Plan the trip as ONE JSON object and nothing else (no markdown):
{"title": "<short warm title, e.g. '12 Days in Ecuador: Andes, Cloud Forest & Galápagos'>",
 "summary": "<one warm sentence>",
 "country": "<the country's name>", "country_code": "<ISO 3166-1 alpha-2>",
 "arrive_airport": "<IATA code of the airport they land at>", "depart_airport": "<IATA code they fly home from>",
 "days": [{"day": 1, "city": "<the city or base where they SLEEP that night (a real place)>",
           "title": "<short day title>", "description": "<one or two vivid sentences>",
           "highlight": "<the place's best-known sight, for a photo>",
           "activities": [{"time": "Morning|Afternoon|Evening", "name": "<activity>", "blurb": "<one line>"}]}]}
Rules:
- EXACTLY {days} days. Day 1 is arrival, the last day is the journey home.
- A sensible route: few bases (2–3 nights each where it makes sense), no criss-crossing, travel times that are realistic.
- arrive_airport is the international airport nearest the FIRST night's city; depart_airport the one nearest the LAST
  night's city (they fly home from there on the last day) — never a long drive back to where they started.
- 2–3 activities a day, real places, fitted to who is travelling and what they love. {party}
- Only real cities and sights. Output ONLY the JSON."""


def _parse(raw: str) -> Optional[dict]:
    raw = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip()).strip()
    s, e = raw.find("{"), raw.rfind("}")
    try:
        return json.loads(raw[s:e + 1]) if s >= 0 and e > s else None
    except ValueError:
        return None


def estimate_usd(country: Optional[str], cand: dict) -> int:
    """The ESTIMATED nightly price (USD) for a listing: the country's base × its Google price level, else a little more for
    a top rating. An estimate, labelled as one wherever it's shown."""
    base = NIGHT_USD.get((country or "").upper(), DEFAULT_NIGHT_USD)
    lvl = cand.get("price_level")
    f = LEVEL.get(int(lvl), 1.0) if isinstance(lvl, (int, float)) and lvl else (1.15 if (cand.get("rating") or 0) >= 4.6 else 1.0)
    return int(round(base * f / 5.0) * 5)


class StaysDown(Exception):
    """Sasha 215 · the hotel search (Google Places, through the booking API) didn't answer — raised only when `strict`."""


# Sasha 246 · a hotel's NAME, never its web page's title: Google's listing name can carry the owner's marketing tail ("Tings Lisbon -
# better rates…", "Hotel Patio | Official Site | Best Price Guaranteed"). The name is cut at the first such part; a part that is
# the place's own words ("Pestana Palace Lisboa - Hotel & National Monument") stays.
_NAME_SEP = re.compile(r"\s+[-–—·]\s+|\s*\|\s*")
_MARKETING = re.compile(r"(?i)\b(?:better|best|lowest|cheap\w*|great)\s+(?:rates?|prices?|deals?|offers?)\b|\brates?\b|\bofficial\b|"
                        r"\bbook(?:ing)?\s+(?:now|direct\w*|online|here|today)\b|\bdeals?\b|\bdiscounts?\b|\bspecial offers?\b|"
                        r"\bsave\b|\bguarantee\w*\b|\bfree\s+(?:wi-?fi|cancell?ation|breakfast|parking)\b|\bweb\s?site\b|"
                        r"\bsite\s+oficial\b|\bmejor\s+precio\b|\bmelhor\s+pre[çc]o\b|\bmeilleur\s+prix\b|\bsite\s+officiel\b|"
                        r"\bhome\s*page\b|\bwelcome to\b|\bcheck (?:rates|availability)\b|…|\.\.\.")


def hotel_name(raw: Optional[str]) -> str:
    """Sasha 246 · the hotel's own name from a listing name that may be a page title: everything from the first marketing part
    on is dropped ("Tings Lisbon - better rates…" → "Tings Lisbon"); a name with none is returned as it is (trimmed)."""
    name = " ".join(str(raw or "").split())
    seps = list(_NAME_SEP.finditer(name))
    for i, m in enumerate(seps):
        part = name[m.end(): seps[i + 1].start() if i + 1 < len(seps) else len(name)]
        if _MARKETING.search(part):
            head = name[:m.start()].strip()
            return head if len(head) >= 2 else name
    return name


async def hotels_in(account: Optional[str], city: str, country_name: str, country_code: Optional[str], prefer: str = "",
                    strict: bool = False) -> List[dict]:
    """Real hotels in a city (Google Places, best rated first): name, Google's rating and count, area, photo, est. price.
    `strict`: the search not answering raises StaysDown (never read as "no hotels")."""
    from booking_signer import guest_whatsapp as GW
    where = f"{city}, {country_name}" if country_name and "," not in city else city
    what = f"{prefer} hotel".strip()[:60] if prefer else "hotel"
    try:
        status, j = await GW.api(account, "POST", "/api/booking/venues/find", {"what": what, "where": where[:80]})
    except Exception as e:
        if strict:
            raise StaysDown(type(e).__name__) from e
        log.info("[world] no hotels for %s: %s", where, type(e).__name__)
        return []
    if status != 200:
        log.info("[world] no hotels for %s: HTTP %s", where, status)
        if strict and (status >= 500 or status in (0, 408, 429)):
            raise StaysDown(f"HTTP {status}")
        return []
    cands = [c for c in (j or {}).get("candidates") or [] if c.get("name") and c.get("place_id") != "sasha-test-venue"
             and (c.get("status") in (None, "OPERATIONAL"))]
    lodging = [c for c in cands if {"lodging", "hotel", "resort_hotel", "guest_house", "bed_and_breakfast", "hostel", "inn"} & set(c.get("types") or [])]
    cands = lodging or cands
    cands.sort(key=lambda c: (-(c.get("rating") or 0) * min(1.0, (c.get("rating_count") or 0) / 80.0), c.get("name") or ""))
    out = []
    for c in cands[:5]:
        est = estimate_usd(country_code, c)
        # Sasha 246 · its name, not a page title. Sasha 249 · this comment used to sit at the end of the line below and swallowed
        # the "address" and "rating" keys (EU 245 §1 side bug): they are back
        out.append({"name": hotel_name(c["name"]) or c["name"], "place_id": c["place_id"], "address": c.get("address"), "rating": c.get("rating"),
                    "rating_count": c.get("rating_count"), "listing_url": c.get("listing_url"), "website": c.get("website"),
                    "gphoto": c.get("gphoto"), "est_usd": est, "est_eur": int(round(FX.to_eur(est, "USD") or 0))})
    return out


async def _photos(cands: List[dict]) -> Dict[str, str]:
    from booking_signer import guest_whatsapp as GW
    try:
        got, _late = await GW._photos_within(cands, GW.photo_wait() + 2.5)
        return got
    except Exception as e:
        log.info("[world] hotel photos: %s", type(e).__name__)
        return {}


async def _place_photo(query: str) -> Optional[str]:
    """A picture OF this place — or none. Sasha 213: the photo layer's stand-in set is one country's pictures (it served
    Vietnam photos for an Ecuador trip when Unsplash failed): never used here."""
    from app.services.foto_agent import search_photos, FALLBACK_PHOTOS
    try:
        got = await search_photos(query, count=1)
        url = (got or [{}])[0].get("url")
        return None if url in {p.get("url") for p in FALLBACK_PHOTOS} else url
    except Exception:
        return None


def hotel_entry(h: dict, city: str, photo: Optional[str] = None) -> dict:
    """A plan day's hotel, in the plan's shape: price_from (USD) is the ESTIMATE, flagged est (labelled "est." on the card)."""
    return {"name": h["name"], "book_url": h.get("listing_url") or f"https://www.google.com/maps/search/{quote_plus(h['name'] + ' ' + city)}",
            "price_from": h["est_usd"], "est": True, "price_label": f"est. €{h['est_eur']}/night",
            "rating": h.get("rating"), "reviews": h.get("rating_count"), "address": h.get("address"), "source": "google",
            **({"photo": photo} if photo else {})}


async def build_world(a: dict, account: Optional[str] = None) -> Optional[dict]:
    """{destination, start_date, nights, party, interests, origin} → the plan (the Vietnam planner's shape), or None."""
    from app.services.llm import client
    nights, party = int(a.get("nights") or 7), int(a.get("party") or 2)
    n_days = nights + 1
    start = date.fromisoformat(a["start_date"])
    who = (f"This trip is for EXACTLY {party} traveller{'s' if party != 1 else ''}"
           + (" — one person travelling alone: no couples' framing." if party == 1 else "."))
    ask = (f"Plan {n_days} days in {a['destination']} from {start.day} {start.strftime('%B %Y')} for {party}"
           + ("." if a.get("flights") is False else f", flying from {a.get('origin') or 'Madrid'}.")   # Sasha 283 · item 2: no flights, no home city
           + (f" They love: {a['interests']}." if a.get("interests") else ""))
    import time as _t
    t0, laps = _t.perf_counter(), {}   # Sasha 257 · where the itinerary's 13–24 s goes (row 863)
    def lap(k: str) -> None:
        laps[k] = int((_t.perf_counter() - t0) * 1000) - sum(laps.values())
    # Sasha 257 · the real cause of a slow plan (row 863, measured on production): the plan model (8–9.5 s) and THEN the hotel
    # search (3.6–3.9 s). Most plans stay in the city they name: its hotels are searched NOW, beside the model, and used only when the
    # plan's stays are exactly that city and every hotel is in the plan's country (else searched after the plan, as before)
    dest_city = (a.get("destination") or "").split(",")[0].strip()
    early = asyncio.ensure_future(hotels_in(account, dest_city, "", None, "")) if dest_city else None
    try:
        r = await asyncio.wait_for(client.messages.create(
            model=MODEL, max_tokens=6000, system=_SYSTEM.replace("{days}", str(n_days)).replace("{party}", who),
            messages=[{"role": "user", "content": ask}]), timeout=60)
        plan = _parse("".join(getattr(b, "text", "") for b in r.content))
    except Exception as e:
        log.error("[world] the route was not planned: %s: %s", type(e).__name__, e)
        if early:
            early.cancel()
        return None
    lap("plan_model")
    days = (plan or {}).get("days") or []
    if len(days) < 2:
        return None
    days = days[:n_days]
    country, code = plan.get("country") or a["destination"], (plan.get("country_code") or "").upper()[:2] or None
    cities = list(dict.fromkeys((d.get("city") or "").strip() for d in days[:-1] if (d.get("city") or "").strip()))
    interests = (a.get("interests") or "").lower()
    prefer = "boutique" if "boutique" in interests else ("beach" if "beach" in interests else "")
    # Sasha 257 · each day's place photo doesn't depend on the hotels: fetched BESIDE the hotel search, not after it
    place_photos = asyncio.gather(*[_place_photo(f"{d.get('highlight') or d.get('city')} {country}") for d in days])
    found, early_used = None, False
    if early is not None:
        try:
            got = await early
            if [c.lower() for c in cities] == [dest_city.lower()] and got and all(str(country).lower() in str(h.get("address") or "").lower() for h in got[:3]):
                found, early_used = [got], True
        except Exception as e:
            log.info("[world] the early hotel search failed (%s) — searching now", type(e).__name__)
    if found is None:
        found = await asyncio.gather(*[hotels_in(account, c, country, code, "") for c in cities])
    lap("hotels")
    stays = {c: (hs[0] if hs else None) for c, hs in zip(cities, found)}
    chosen = [h for h in stays.values() if h]
    hphotos, pphotos = await asyncio.gather(_photos(chosen), place_photos)
    lap("photos")
    log.warning("[world] itinerary ms %s (%d days, %d cities, model %s, hotels searched beside the plan: %s)", laps, len(days), len(cities),
                MODEL, early_used)
    hotel_total, acts = 0, 0
    for i, d in enumerate(days):
        d["day"] = i + 1
        city = (d.get("city") or "").strip()
        d["country"] = country
        d["image"] = pphotos[i]
        h = stays.get(city) if i < len(days) - 1 else None
        d["hotel"] = hotel_entry(h, city, hphotos.get(h["place_id"])) if h else ""
        if h:
            hotel_total += h["est_usd"]
        for x in d.get("activities") or []:
            acts += 1
            x["book_url"] = f"https://www.getyourguide.com/s/?q={quote_plus((x.get('name') or '') + ' ' + city)}"
    meals, experiences, transport = n_days * 45 * party, acts * 35 * party, 350
    return {"title": plan.get("title") or f"{n_days} Days in {country}", "summary": plan.get("summary") or "",
            "days": days, "country": country, "country_code": code, "planner": "world",
            "airports": {"arrive": (plan.get("arrive_airport") or "").upper()[:3] or None,
                         "depart": (plan.get("depart_airport") or "").upper()[:3] or None},
            "travellers": party, "party": party,
            "estimated_total_usd": int(round((hotel_total + meals + experiences + transport) / 10.0) * 10),
            "cost_breakdown": {"hotels": hotel_total, "experiences": experiences, "meals": meals, "transport": transport,
                               "travellers": party, "hotels_are_estimates": True},
            "stay_options": {c: hs for c, hs in zip(cities, found)}}


__all__ = ["build_world", "hotels_in", "hotel_entry", "estimate_usd", "NIGHT_USD", "hotel_name"]   # Sasha 246 · + hotel_name
