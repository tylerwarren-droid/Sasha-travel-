"""Sasha 213 · NO LIVE GOOGLE PLACES IN TESTS. Places (New) costs real money (€237 this month, ~€25 on 8 Oct alone, much of it
from the suites): every suite and the deploy gate answer Google's Places hosts from HERE — never the network. A live Places
call from a test needs the founder's say-so (SASHA_TEST_PLACES=live, set by hand, never by a suite).

What it answers, in Places (New)'s own response shape, deterministically (the same question → the same answer):
  · places:searchText   → up to 8 FICTIONAL places for the query's kind and city (names say so: "… (test)"), with ratings,
                          review counts, price levels, opening hours and types — no website and no photo, so nothing else
                          is fetched because of them
  · places/{id}          → that place's details (the same fictional record)
  · …/media (photos)     → refused (no photo), as for a listing without one
Anything else on a Google Maps/Places host is REFUSED here, never sent. Every other host (a venue's own site, our own test
venue) passes through untouched. `CALLS` lists what was answered, so a suite can say how many Places calls it saved.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Optional
from urllib.parse import urlsplit

CALLS: list = []
_REAL = None
_GOOGLE = ("places.googleapis.com", "maps.googleapis.com", "maps.google.com")
KINDS = [  # (words in the query, primary type, display type, name stems)
    (r"\b(?:hotels?|hostels?|stays?|resorts?|lodging)\b", "hotel", "Hotel", ["Hotel Alba", "Casa Mirador", "Hotel Patio", "The Courtyard House", "Hotel Ribera", "Posada Luna", "Hotel Jardín", "The Station Rooms"]),
    (r"\b(?:spas?|massages?|hammam|wellness)\b", "spa", "Spa", ["Spa Agua", "Calma Spa", "Baños Lumen", "Spa Raíz", "Hammam Sol", "Bruma Spa", "Spa Olivo", "Mar Spa"]),
    (r"\btattoo", "tattoo_shop", "Tattoo shop", ["Tinta Norte Tattoo", "Línea Fina Studio", "Aguja Tattoo", "Tinta Sur", "Rama Ink", "Trazo Studio", "Punto Negro Tattoo", "Hilo Ink"]),
    (r"\b(?:bars?|pubs?|wine|cocktails?|rooftop)\b", "bar", "Bar", ["Bar Terraza", "La Bodeguita Gris", "Bar Faro", "The Copper Tap", "Vinos Ocho", "Bar Azotea", "El Barril", "Taberna Nube"]),
    (r"\b(?:caf[eé]s?|coffee|brunch|pastr\w*|bakery)\b", "cafe", "Café", ["Café Lienzo", "Brunch Club Sol", "Café Ocre", "Panadería Lúa", "Café Norte", "Taza Azul", "Café Verbena", "Miga"]),
    (r".*", "restaurant", "Restaurant", ["Casa Marea", "El Fogón Viejo", "La Mesa Larga", "Bistró Salvia", "Taberna Ancla", "Comedor Real", "La Cocina de Nur", "Mesón Encina"]),
]


class _R:
    def __init__(self, status: int, body: Any):
        self.status_code, self._body, self.headers = status, body, {}
        self.text = json.dumps(body)

    def json(self):
        return self._body


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _what(q: str) -> str:
    return re.split(r"\s+in\s+", q, maxsplit=1, flags=re.I)[0].strip()


def _kind(q: str):
    for rx, ptype, label, stems in KINDS:
        if re.search(rx, _what(q), re.I):
            return ptype, label, stems
    return KINDS[-1][1:]


def _city(q: str) -> str:
    m = re.search(r"\bin\s+(.+)$", q, re.I)
    return (m.group(1) if m else "Madrid").split(",")[0].strip().title() or "Madrid"


def _place(q: str, i: int) -> dict:
    ptype, label, stems = _kind(q)
    city = _city(q)
    h = _h(f"{q.lower()}|{i}")
    pid = "ChIJtest" + h[:20]
    return {"id": pid, "displayName": {"text": f"{stems[i % len(stems)]} (test)", "languageCode": "en"},
            "formattedAddress": f"Calle Prueba {1 + int(h[:2], 16) % 90}, {city}, Test",
            # the words asked for ride in the type ("Seafood restaurant"), as a real listing's do — the cuisine filter reads them
            "primaryTypeDisplayName": {"text": _what(q).capitalize() or label}, "types": [ptype, "point_of_interest", "establishment"],
            "businessStatus": "OPERATIONAL", "rating": round(3.9 + (int(h[2:4], 16) % 11) / 10, 1),
            "userRatingCount": 40 + int(h[4:8], 16) % 2400, "priceLevel": ["PRICE_LEVEL_INEXPENSIVE", "PRICE_LEVEL_MODERATE",
                                                                         "PRICE_LEVEL_EXPENSIVE"][int(h[8:10], 16) % 3],
            "location": {"latitude": 40.40 + (int(h[10:12], 16) % 100) / 1000, "longitude": -3.72 + (int(h[12:14], 16) % 100) / 1000},
            "regularOpeningHours": {"periods": [{"open": {"day": d, "hour": 8, "minute": 0}, "close": {"day": d, "hour": 23, "minute": 59}}
                                               for d in range(7)]},
            "addressComponents": [{"longText": city, "shortText": city, "types": ["locality"]},
                                  {"longText": "Spain", "shortText": "ES", "types": ["country"]}]}


async def replay(method: str, url: str, headers: Optional[dict] = None, json: Optional[dict] = None, **kw):
    host = (urlsplit(url).hostname or "").lower()
    if not any(host == g or host.endswith("." + g) for g in _GOOGLE):
        return await _REAL(method, url, headers or {}, json)
    path = urlsplit(url).path
    CALLS.append((method, path))
    if path.endswith("places:searchText"):
        q = str((json or {}).get("textQuery") or "")
        n = min(int((json or {}).get("maxResultCount") or 8), 8)
        return _R(200, {"places": [_place(q, i) for i in range(n)]})
    m = re.fullmatch(r"/v1/places/(ChIJtest[0-9a-f]{20})", path)
    if m:
        return _R(200, {**_place("restaurant in Madrid", 0), "id": m.group(1)})
    return _R(403, {"error": {"code": 403, "message": "refused by places_fake: no live Google Places from tests", "status": "PERMISSION_DENIED"}})


def install() -> None:
    """Every Google Places call in this process → the replay. Idempotent. SASHA_TEST_PLACES=live (the founder's say-so only)
    leaves the real transport in place, and says so."""
    global _REAL
    from booking_signer import ladder_routes as LR
    if os.getenv("SASHA_TEST_PLACES", "") == "live":
        print("PLACES: LIVE (SASHA_TEST_PLACES=live — the founder's say-so) — these calls cost money", flush=True)
        return
    if getattr(LR.HTTP, "_places_fake", False):
        return
    _REAL = LR.HTTP
    replay._places_fake = True
    LR.HTTP = replay
    # belt and braces: the process's own key is replaced too — even a call that slipped past the replay could bill nothing
    os.environ["GOOGLE_PLACES_API_KEY"] = "places-fake-no-billing"
    print("PLACES: recorded-shape fixtures (scripts/places_fake.py) — no live Google Places call", flush=True)


__all__ = ["install", "replay", "CALLS"]
