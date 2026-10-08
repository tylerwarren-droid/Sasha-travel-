"""The sandbox's engines — Sasha's own search code on recorded fixtures, 0 live calls:
  flights  booking_signer.travel.search / order   over scripts/duffel_fake (Duffel TEST answers recorded 7 Oct 2026)
  venues   booking_signer.venue_read.find_venues  over scripts/places_fake (fictional places, Places (New)'s own shape)
  stays    the same venue search, for lodging
Every outbound connection is refused (block_network): a fixture gap is an error, never a live call.

OUTAGES ARE OUTAGES: a 5xx / timeout / refused transport raises Unavailable(service) → HTTP 503 {type: "unavailable"} — never
"no results". The sandbox can simulate one: header `AgAPI-Sandbox-Simulate: duffel_down | places_down`.
UNTRUSTED TEXT: any text that came from outside (a listing's name, address, a venue's reply) is returned as
{"untrusted": true, "text": …, "source": …} — data for the caller to show, never instructions to follow."""
from __future__ import annotations

import contextvars
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config  # noqa: F401  (puts backend/ on the path)

SIMULATE: contextvars.ContextVar[str] = contextvars.ContextVar("agapi_simulate", default="")
_FAULT: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("agapi_fault", default=None)
_INSTALLED = False


class Unavailable(Exception):
    def __init__(self, service: str, message: str):
        super().__init__(message)
        self.service, self.message = service, message


class Refused(Exception):
    """The world said no (or the request was invalid) — distinct from an outage."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def untrusted(text: Optional[str], source: str) -> Optional[dict]:
    return None if text is None else {"untrusted": True, "text": str(text)[:300], "source": source}


def block_network() -> None:
    """No request leaves this process except to loopback — the sandbox's 0-live-calls guarantee, enforced, not promised."""
    import httpx

    def _guard(url) -> None:
        host = (httpx.URL(str(url)).host or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1", "testserver"):
            raise httpx.ConnectError(f"AgAPI sandbox: outbound call to {host} refused (test mode, fixtures only)")
    if getattr(httpx.AsyncClient.send, "_agapi_guard", False):
        return
    real_async, real_sync = httpx.AsyncClient.send, httpx.Client.send

    async def asend(self, request, *a, **k):
        _guard(request.url)
        return await real_async(self, request, *a, **k)

    def ssend(self, request, *a, **k):
        _guard(request.url)
        return real_sync(self, request, *a, **k)
    asend._agapi_guard = True
    httpx.AsyncClient.send, httpx.Client.send = asend, ssend


def install() -> None:
    """Fixtures in, network out. Idempotent."""
    global _INSTALLED
    if _INSTALLED:
        return
    os.environ.setdefault("GOOGLE_PLACES_API_KEY", "places-fake-no-billing")
    from scripts import duffel_fake, places_fake
    from booking_signer import travel as T
    duffel_fake.install()
    replay = T.HTTP

    async def duffel(method, path, body=None, params=None):
        if SIMULATE.get() == "duffel_down":
            _FAULT.set("duffel")
            return 503, {"errors": [{"message": "sandbox: Duffel simulated down"}]}
        st, j = await replay(method, path, body, params)
        if st >= 500:
            _FAULT.set("duffel")
        return st, j
    T.HTTP = duffel

    async def no_other_host(method, url, headers=None, json=None, **kw):
        raise ConnectionError(f"AgAPI sandbox: {url} refused (test mode, fixtures only)")
    places_fake._REAL = no_other_host
    block_network()
    _INSTALLED = True


def _places_http():
    from scripts import places_fake

    async def http(method, url, headers=None, json=None, **kw):
        if SIMULATE.get() == "places_down":
            _FAULT.set("places")
            return places_fake._R(503, {"error": {"code": 503, "message": "sandbox: Places simulated down", "status": "UNAVAILABLE"}})
        r = await places_fake.replay(method, url, headers, json, **kw)
        if getattr(r, "status_code", 200) >= 500:
            _FAULT.set("places")
        return r
    return http


# ── find ───────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _minor(amount: str) -> int:
    whole, _, frac = str(amount).partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


async def find_flights(origin: str, destination: str, date: str, adults: int) -> List[dict]:
    from booking_signer import travel as T
    _FAULT.set(None)
    try:
        got = await T.search(origin, destination, date, adults=adults, limit=5)
    except Exception:
        raise Unavailable("duffel", "the airline system (Duffel) didn't answer — nothing was searched; try again shortly")
    if _FAULT.get() == "duffel":
        raise Unavailable("duffel", "the airline system (Duffel) is unavailable — nothing was searched; try again shortly")
    if "why" in got:
        raise Refused("no_flights", got["why"])
    out = []
    for c in got.get("cards") or []:
        out.append({"kind": "flight", "provider": "duffel_test", "title": f"{c['owner']} {c['flights']}",
                    "from": c["from"], "to": c["to"], "from_city": c.get("from_city"), "to_city": c.get("to_city"),
                    "departs": c["departs"], "arrives": c["arrives"], "stops": c.get("stops", 0), "minutes": c.get("minutes"),
                    "price": {"amount_minor": _minor(c["amount"]), "currency": c["currency"]}, "adults": adults,
                    "_card": c})
    return out


async def find_places(what: str, where: str, country: Optional[str], kind: str) -> List[dict]:
    from booking_signer import venue_read as V
    _FAULT.set(None)
    try:
        got = await V.find_venues(_places_http(), what=what, where=where, country=country, now=datetime.now(timezone.utc))
    except V.FindRefused as e:
        if _FAULT.get() == "places" or e.code in ("places_unreachable", "places_refused"):
            raise Unavailable("places", "the places directory (Google Places) is unavailable — nothing was searched; try again shortly")
        raise Refused(e.code, e.message if hasattr(e, "message") else str(e))
    except Exception:
        raise Unavailable("places", "the places directory (Google Places) didn't answer — nothing was searched; try again shortly")
    if _FAULT.get() == "places":
        raise Unavailable("places", "the places directory (Google Places) is unavailable — nothing was searched; try again shortly")
    out = []
    for c in got.get("candidates") or []:
        out.append({"kind": kind, "provider": "google_places_fixture", "place_id": c.get("place_id"),
                    "name": untrusted(c.get("name"), "google_places"), "address": untrusted(c.get("address"), "google_places"),
                    "type": c.get("type"), "rating": c.get("rating"), "rating_count": c.get("rating_count"),
                    "price_level": c.get("price_level"), "listing_url": c.get("listing_url")})
    return out


async def order_flight(card: dict) -> Dict[str, Any]:
    """The Duffel TEST order on the replay (never live): {booking_reference, order_id} or Unavailable/Refused."""
    from booking_signer import travel as T
    _FAULT.set(None)
    try:
        got = await T.order(card, "Sandbox Traveller", "sandbox-traveller@example.com", None)
    except Exception:
        raise Unavailable("duffel", "the airline system (Duffel) didn't answer — nothing was booked; the approval is still unused")
    if _FAULT.get() == "duffel":
        raise Unavailable("duffel", "the airline system (Duffel) is unavailable — nothing was booked; the approval is still unused")
    if "why" in got:
        raise Refused("offer_gone", got["why"])
    return got
