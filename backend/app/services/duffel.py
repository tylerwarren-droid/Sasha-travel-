"""
Optional Duffel Flights adapter for Sasha.

Design goals:
- Plug into the existing `flight` intent and booking-card shape.
- Make zero frontend changes for live flight search.
- Stay OFF unless DUFFEL_ENABLED=1 and DUFFEL_ACCESS_TOKEN is present.
- Fall back to Sasha's existing flight search if Duffel is unavailable.
- Preserve Duffel offer IDs/expiry/provider metadata so native booking can be added later
  without changing the conversation/card architecture again.

This module intentionally does NOT create live airline orders. Search is the first reversible
integration step; order creation needs real passenger data and an explicit customer-payment
flow. Duffel offers are revalidated before booking in the eventual order path.
"""

import asyncio
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote_plus

import httpx


DUFFEL_BASE_URL = os.getenv("DUFFEL_BASE_URL", "https://api.duffel.com").rstrip("/")
DUFFEL_ACCESS_TOKEN = os.getenv("DUFFEL_ACCESS_TOKEN", "").strip()
DUFFEL_ENABLED = os.getenv("DUFFEL_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
DUFFEL_TIMEOUT_S = float(os.getenv("DUFFEL_TIMEOUT_S", "16"))
DUFFEL_SUPPLIER_TIMEOUT_MS = int(os.getenv("DUFFEL_SUPPLIER_TIMEOUT_MS", "9000"))
DUFFEL_MAX_OFFERS = max(1, min(10, int(os.getenv("DUFFEL_MAX_OFFERS", "5"))))
DUFFEL_MAX_CONNECTIONS = max(0, min(3, int(os.getenv("DUFFEL_MAX_CONNECTIONS", "1"))))


class DuffelError(RuntimeError):
    pass


def duffel_enabled() -> bool:
    return DUFFEL_ENABLED and bool(DUFFEL_ACCESS_TOKEN)


def _headers() -> dict:
    return {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "Content-Type": "application/json",
        "Duffel-Version": "v2",
        "Authorization": f"Bearer {DUFFEL_ACCESS_TOKEN}",
    }


async def _request(method: str, path: str, *, params: Optional[dict] = None,
                   body: Optional[dict] = None):
    if not DUFFEL_ACCESS_TOKEN:
        raise DuffelError("DUFFEL_ACCESS_TOKEN is not configured")
    try:
        async with httpx.AsyncClient(base_url=DUFFEL_BASE_URL, timeout=DUFFEL_TIMEOUT_S) as http:
            response = await http.request(method, path, headers=_headers(), params=params, json=body)
    except httpx.HTTPError as exc:
        raise DuffelError(f"Duffel transport error: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text[:500]
        try:
            payload = response.json()
            errors = payload.get("errors") or []
            if errors:
                detail = "; ".join(
                    str(e.get("message") or e.get("title") or e.get("code") or e)
                    for e in errors[:3]
                )
        except Exception:
            pass
        raise DuffelError(f"Duffel {response.status_code}: {detail}")

    try:
        payload = response.json()
    except Exception as exc:
        raise DuffelError("Duffel returned non-JSON content") from exc
    return payload.get("data")


def _json_object(raw: str) -> Optional[dict]:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        value = json.loads(raw[start:end + 1])
        return value if isinstance(value, dict) else None
    except Exception:
        return None


async def _extract_search(message: str, context: str = "", dest_hint: str = "") -> dict:
    """Use Sasha's existing fast model only to structure what the guest already said.

    The model is not allowed to invent a route or date. Missing fields stay null so Sasha can
    ask the guest for them instead of quietly searching a made-up itinerary.
    """
    from app.services.llm import client, FAST_MODEL, cached_system

    today = date.today().isoformat()
    system = f"""Extract a flight-search request from the conversation.
Today is {today}. Resolve explicit relative dates such as "next Friday" against today.
Do NOT invent an origin, destination, departure date, return date, cabin, or party size.

Return ONLY one JSON object:
{{
  "origin_query": string|null,
  "destination_query": string|null,
  "departure_date": "YYYY-MM-DD"|null,
  "return_date": "YYYY-MM-DD"|null,
  "cabin_class": "economy"|"premium_economy"|"business"|"first"|null,
  "adults": integer|null
}}

Rules:
- Use city names, airport names, or IATA codes exactly as stated when possible.
- A return date is optional; do not infer one unless the guest stated it.
- If party size is not stated, use 1 adult.
- `dest_hint` may only be used if it is clearly the destination already established by Sasha.
"""
    prompt = (
        f"dest_hint: {dest_hint or '(none)'}\n"
        f"Recent conversation:\n{context[-5000:] if context else '(none)'}\n"
        f"Current guest message:\n{message}"
    )
    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=FAST_MODEL,
                max_tokens=180,
                system=cached_system(system),
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=6.0,
        )
        raw = "".join(getattr(block, "text", "") for block in response.content)
        data = _json_object(raw) or {}
    except Exception as exc:
        print(f"[duffel] flight query extraction failed: {exc}")
        data = {}

    if not data.get("destination_query") and dest_hint and dest_hint.lower() != "vietnam":
        data["destination_query"] = dest_hint
    try:
        adults = int(data.get("adults") or 1)
    except (TypeError, ValueError):
        adults = 1
    data["adults"] = max(1, min(9, adults))
    cabin = (data.get("cabin_class") or "economy").strip().lower()
    if cabin not in {"economy", "premium_economy", "business", "first"}:
        cabin = "economy"
    data["cabin_class"] = cabin
    return data


async def _resolve_place(query: str) -> Optional[str]:
    q = (query or "").strip()
    if not q:
        return None
    if re.fullmatch(r"[A-Za-z]{3}", q):
        return q.upper()

    data = await _request("GET", "/places/suggestions", params={"query": q})
    if not isinstance(data, list) or not data:
        return None

    cities = [p for p in data if isinstance(p, dict) and p.get("type") == "city" and p.get("iata_code")]
    if cities:
        return str(cities[0]["iata_code"]).upper()

    first = next((p for p in data if isinstance(p, dict) and p.get("iata_code")), None)
    return str(first["iata_code"]).upper() if first else None


def _duration_text(value: str) -> str:
    m = re.fullmatch(r"P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?", value or "")
    if not m:
        return value or ""
    h, mins = int(m.group(1) or 0), int(m.group(2) or 0)
    if h and mins:
        return f"{h}h {mins}m"
    if h:
        return f"{h}h"
    if mins:
        return f"{mins}m"
    return ""


def _money(amount: str, currency: str, party_size: int) -> str:
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return ""
    currency = (currency or "").upper()
    symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
    prefix = symbols.get(currency, f"{currency} ")
    number = f"{n:,.2f}".rstrip("0").rstrip(".")
    suffix = f" total for {party_size}" if party_size > 1 else ""
    return f"{prefix}{number}{suffix}"


def _google_flights_link(origin: str, destination: str, departure_date: str = "") -> str:
    q = f"flights from {origin} to {destination}"
    if departure_date:
        q += f" {departure_date}"
    return f"https://www.google.com/travel/flights?q={quote_plus(q)}"


def _normalise_offer(offer: dict, *, origin_query: str, destination_query: str,
                     departure_date: str) -> dict:
    slices = offer.get("slices") or []
    route_parts = []
    operating = []
    max_stops = 0
    durations = []

    for sl in slices:
        segments = sl.get("segments") or []
        if segments:
            first_origin = ((segments[0].get("origin") or {}).get("iata_code")
                            or (sl.get("origin") or {}).get("iata_code") or "")
            last_dest = ((segments[-1].get("destination") or {}).get("iata_code")
                         or (sl.get("destination") or {}).get("iata_code") or "")
            if first_origin or last_dest:
                route_parts.append(f"{first_origin}-{last_dest}".strip("-"))
            max_stops = max(max_stops, max(0, len(segments) - 1))
            for seg in segments:
                name = ((seg.get("operating_carrier") or {}).get("name") or "").strip()
                if name and name not in operating:
                    operating.append(name)
        d = _duration_text(str(sl.get("duration") or ""))
        if d:
            durations.append(d)

    owner = (offer.get("owner") or {}).get("name") or ""
    display_carrier = operating[0] if operating else owner or "Flight"
    stops = "nonstop" if max_stops == 0 else f"up to {max_stops} stop{'s' if max_stops != 1 else ''}"
    detail_bits = [" / ".join(route_parts), " / ".join(durations), stops]
    if operating:
        detail_bits.append("Operated by " + ", ".join(operating))
    detail = " · ".join(x for x in detail_bits if x)

    currency = str(offer.get("total_currency") or "").upper()
    amount = str(offer.get("total_amount") or "")
    passengers = offer.get("passengers") or []
    party_size = max(1, len(passengers))
    try:
        numeric = float(amount)
    except (TypeError, ValueError):
        numeric = 0.0

    return {
        "name": display_carrier,
        "detail": detail,
        "price": _money(amount, currency, party_size),
        "amount_usd": numeric if currency == "USD" else 0,
        "book_url": _google_flights_link(origin_query, destination_query, departure_date),
        "provider": "duffel",
        "provider_offer_id": offer.get("id"),
        "provider_amount": amount,
        "currency": currency,
        "party_size": party_size,
        "expires_at": offer.get("expires_at"),
        "live_mode": bool(offer.get("live_mode")),
    }


def card_has_live_offer(card: dict, *, safety_seconds: int = 90) -> bool:
    if not isinstance(card, dict) or card.get("_provider") != "duffel":
        return True
    now = datetime.now(timezone.utc) + timedelta(seconds=safety_seconds)
    for option in card.get("options") or []:
        exp = option.get("expires_at")
        if not exp:
            continue
        try:
            dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > now:
                return True
        except Exception:
            continue
    return False


async def get_offer(provider_offer_id: str) -> dict:
    data = await _request("GET", f"/air/offers/{provider_offer_id}")
    if not isinstance(data, dict):
        raise DuffelError("Duffel offer lookup returned no offer")
    return data


async def search_flights_from_text(message: str, *, context: str = "",
                                   dest_hint: str = "") -> Optional[dict]:
    if not duffel_enabled():
        return None

    query = await _extract_search(message, context=context, dest_hint=dest_hint)
    missing = [key for key in ("origin_query", "destination_query", "departure_date") if not query.get(key)]
    if missing:
        return {
            "_provider": "duffel",
            "_needs_input": missing,
            "type": "flight",
            "title": "Live flights",
            "dest": query.get("destination_query") or dest_hint or "",
            "origin_spoken": query.get("origin_query") or "",
            "options": [],
        }

    origin_code, destination_code = await asyncio.gather(
        _resolve_place(query["origin_query"]),
        _resolve_place(query["destination_query"]),
    )
    if not origin_code or not destination_code:
        missing_place = []
        if not origin_code:
            missing_place.append("origin")
        if not destination_code:
            missing_place.append("destination")
        return {
            "_provider": "duffel",
            "_needs_input": missing_place,
            "type": "flight",
            "title": "Live flights",
            "dest": query.get("destination_query") or "",
            "origin_spoken": query.get("origin_query") or "",
            "options": [],
        }

    slices = [{
        "origin": origin_code,
        "destination": destination_code,
        "departure_date": query["departure_date"],
    }]
    if query.get("return_date"):
        slices.append({
            "origin": destination_code,
            "destination": origin_code,
            "departure_date": query["return_date"],
        })

    body = {
        "data": {
            "slices": slices,
            "passengers": [{"type": "adult"} for _ in range(query["adults"])],
            "cabin_class": query["cabin_class"],
            "max_connections": DUFFEL_MAX_CONNECTIONS,
        }
    }
    try:
        data = await _request(
            "POST",
            "/air/offer_requests",
            params={"return_offers": "true", "supplier_timeout": str(DUFFEL_SUPPLIER_TIMEOUT_MS)},
            body=body,
        )
    except DuffelError as exc:
        print(f"[duffel] search failed, using legacy flight path: {exc}")
        return None

    offers = (data or {}).get("offers") if isinstance(data, dict) else None
    offers = [o for o in (offers or []) if isinstance(o, dict)]
    offers.sort(key=lambda o: float(o.get("total_amount") or 10**12))

    options = [
        _normalise_offer(
            offer,
            origin_query=query["origin_query"],
            destination_query=query["destination_query"],
            departure_date=query["departure_date"],
        )
        for offer in offers[:DUFFEL_MAX_OFFERS]
    ]

    if not options:
        return {
            "_provider": "duffel",
            "type": "flight",
            "title": f"Flights · {query['origin_query']} → {query['destination_query']}",
            "dest": query["destination_query"],
            "origin_spoken": query["origin_query"],
            "options": [{
                "name": "No Duffel offers returned",
                "detail": "Compare the same route on Google Flights",
                "price": "",
                "book_url": _google_flights_link(
                    query["origin_query"], query["destination_query"], query["departure_date"]
                ),
                "fallback": True,
            }],
        }

    return {
        "_provider": "duffel",
        "_duffel_offer_request_id": (data or {}).get("id"),
        "type": "flight",
        "title": f"Flights · {query['origin_query']} → {query['destination_query']}",
        "dest": query["destination_query"],
        "origin_spoken": query["origin_query"],
        "departure_date": query["departure_date"],
        "return_date": query.get("return_date"),
        "cabin_class": query["cabin_class"],
        "party_size": query["adults"],
        "options": options,
    }
