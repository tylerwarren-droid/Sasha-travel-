"""The sandbox's upstreams — test mode only, recorded fixtures, 0 live calls (Part 4 §5):
  duffel        Sasha's booking_signer.travel (search, offer read, order) over scripts/duffel_fake — Duffel TEST answers recorded
                7 Oct 2026 from Kanoe's Duffel TEST account
  google_places Sasha's booking_signer.venue_read.find_venues over scripts/places_fake — fictional places in Places (New)'s shape
  sandbox_venue fixture venues: NO real venue is ever contacted in test mode (Tyler, CR 58)
  stripe_test   the payment link's page is the sandbox's own (Stripe test, simulated — no Stripe call)
Magic refs (Part 4 §5): off_test_sold_out · off_test_timeout_before · off_test_timeout_after · off_test_price_jump · src_test_down.
Every outbound connection is refused except to a registered webhook endpoint (block_network)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date as Date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from . import config  # noqa: F401  (backend on the path)
from .registry import AgapiError
from .rules import wrap
from .store import ts

MAGIC = ("off_test_sold_out", "off_test_timeout_before", "off_test_timeout_after", "off_test_price_jump")
_INSTALLED = False
ALLOWED_HOSTS: set = {"api.anthropic.com"}   # webhook endpoint hosts (added as endpoints are registered) + CR 69: magellan's AI reader


class Upstream:
    """One call's upstream trace entries (Part 1 §1.2 trace.upstream)."""

    def __init__(self):
        self.calls: List[dict] = []

    def add(self, service: str, t0: float, ok: bool, code: Optional[str] = None) -> None:
        e = {"service": service, "ms": int((time.perf_counter() - t0) * 1000), "ok": ok}
        if code:
            e["code"] = code
        self.calls.append(e)


def block_network() -> None:
    import httpx

    def guard(url) -> None:
        host = (httpx.URL(str(url)).host or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1", "testserver") and host not in ALLOWED_HOSTS:
            raise httpx.ConnectError(f"AgAPI sandbox: outbound call to {host} refused (test mode, fixtures only)")
    if getattr(httpx.AsyncClient.send, "_agapi_guard", False):
        return
    ra, rs = httpx.AsyncClient.send, httpx.Client.send

    async def asend(self, request, *a, **k):
        if not request.extensions.get("agapi_magellan"):   # CR 69 · magellan.read_site's own reads (public pages only, checked there)
            guard(request.url)
        return await ra(self, request, *a, **k)

    def ssend(self, request, *a, **k):
        guard(request.url)
        return rs(self, request, *a, **k)
    asend._agapi_guard = True
    httpx.AsyncClient.send, httpx.Client.send = asend, ssend


def live_hosts() -> set:
    """The live providers' hosts + Sasha's booking service (the ladder, over HTTPS)."""
    from urllib.parse import urlsplit
    return set(config.LIVE_HOSTS) | {urlsplit(os.getenv("AGAPI_SASHA_API_URL", "https://sasha-travel-production.up.railway.app")).hostname}


def install_live() -> None:
    """CR 70 · agapi-live: NO fixtures; the network guard lets only the live providers' hosts out (config.LIVE_HOSTS)."""
    global _INSTALLED
    if _INSTALLED:
        return
    ALLOWED_HOSTS.update(live_hosts())
    block_network()
    _INSTALLED = True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    os.environ.setdefault("GOOGLE_PLACES_API_KEY", "places-fake-no-billing")
    from scripts import duffel_fake, places_fake

    async def no_other_host(method, url, headers=None, json=None, **kw):
        raise ConnectionError("AgAPI sandbox: only recorded fixtures answer here")
    duffel_fake.install()
    places_fake._REAL = no_other_host
    block_network()
    _INSTALLED = True


def _down(inp: Any) -> bool:
    return "src_test_down" in json.dumps(inp)


def _sha(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _minor(amount: str) -> int:
    whole, _, frac = str(amount).partition(".")
    sign = -1 if whole.startswith("-") else 1
    return sign * (abs(int(whole)) * 100 + int((frac + "00")[:2]))


def _local(dt_local: str, tz: str) -> str:
    """'2026-11-12T07:30:00' in Europe/Madrid → '2026-11-12T07:30:00+01:00' (local time with its UTC offset)."""
    d = datetime.fromisoformat(dt_local).replace(tzinfo=ZoneInfo(tz))
    return d.isoformat(timespec="seconds")


def _arrival(departs_local: str, from_tz: str, minutes: int, arrives_local: str) -> str:
    """The arrival's offset, derived exactly: departure in UTC + the duration = arrival in UTC; local − UTC = its offset."""
    dep = datetime.fromisoformat(departs_local).replace(tzinfo=ZoneInfo(from_tz))
    arr_utc = dep.astimezone(timezone.utc) + timedelta(minutes=minutes)
    naive = datetime.fromisoformat(arrives_local)
    off = round((naive - arr_utc.replace(tzinfo=None)).total_seconds() / 900) * 900
    return naive.replace(tzinfo=timezone(timedelta(seconds=off))).isoformat(timespec="seconds")


# ── Magellan: find ─────────────────────────────────────────────────────────────────────────────────────────────────────

async def find_flights(inp: dict, up: Upstream) -> List[dict]:
    """One source (duffel). → [{source, ok, code?, items}] for rules.classify."""
    from booking_signer import travel as T
    t0 = time.perf_counter()
    if _down(inp):
        up.add("duffel", t0, False, "upstream_unreachable")
        return [{"source": "duffel", "ok": False, "code": "upstream_unreachable"}]
    o, d = inp["origin"], inp["destination"]
    try:
        got = await T.search(o.get("iata") or o["query"], d.get("iata") or d["query"], inp["date"], adults=inp["passengers"], limit=8)
    except Exception:
        up.add("duffel", t0, False, "upstream_unreachable")
        return [{"source": "duffel", "ok": False, "code": "upstream_unreachable"}]
    if "why" in got and "couldn't find" not in got["why"].lower() and "no flights" not in got["why"].lower():
        up.add("duffel", t0, False, "upstream_failed")
        return [{"source": "duffel", "ok": False, "code": "upstream_failed"}]
    up.add("duffel", t0, True)
    now_s = ts()
    items = []
    for c in got.get("cards") or []:
        fnums = [f.replace(" ", "") for f in c["flights"].split(" + ")]
        dep = _local(c["departs"], c.get("from_tz") or "UTC")
        arr = _arrival(c["departs"], c.get("from_tz") or "UTC", int(c.get("minutes") or 0), c["arrives"])
        items.append({"offer_ref": c["id"], "carrier": {"code": fnums[0][:2], "name": wrap(c["owner"], "duffel", now_s, cap=300)},
                      "flight_numbers": fnums, "from": c["from"], "to": c["to"], "departs": dep, "arrives": arr,
                      "stops": int(c.get("stops") or 0), "duration_minutes": int(c.get("minutes") or 0),
                      "price": {"amount_minor": _minor(c["amount"]), "currency": c["currency"]}, "price_source": "quoted",
                      "expires_at": _z(c.get("expires_at")), "_card": c})
    if "direct" in (inp.get("preferences") or []):
        items = [i for i in items if i["stops"] == 0]
    return [{"source": "duffel", "ok": True, "items": items}]


def _z(s: Optional[str]) -> str:
    if not s:
        return ts(datetime.now(timezone.utc) + timedelta(minutes=30))
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return ts(d)


async def _places(what: str, where: dict, up: Upstream, source: str = "google_places", http=None) -> Tuple[bool, Optional[str], List[dict]]:
    """http: the recorded replay in the sandbox (default); CR 70 · on agapi-live, the real HTTP (adapters_live.places)."""
    from booking_signer import venue_read as V
    from scripts import places_fake
    t0 = time.perf_counter()
    if _down(where) or _down(what):
        up.add(source, t0, False, "upstream_unreachable")
        return False, "upstream_unreachable", []
    try:
        got = await V.find_venues(http or places_fake.replay, what=what, where=where["query"], country=where.get("country"),
                                  now=datetime.now(timezone.utc))
    except V.FindRefused as e:
        code = "upstream_unreachable" if "unreachable" in str(e) else "upstream_rate_limited" if "HTTP 429" in str(e) \
            else "upstream_refused" if "refused" in str(e) else "upstream_failed"     # CR 70: Google's daily quota (429) is a rate limit
        up.add(source, t0, False, code)
        return False, code, []
    except Exception:
        up.add(source, t0, False, "upstream_unreachable")
        return False, "upstream_unreachable", []
    up.add(source, t0, True)
    return True, None, got.get("candidates") or []


def _fixture_price(ref: str, lo: int, hi: int) -> int:
    """The sandbox's own quoted price for a fixture stay: deterministic per ref (the same question, the same answer)."""
    return lo + int(hashlib.sha256(ref.encode()).hexdigest()[:6], 16) % (hi - lo)


async def find_stays(inp: dict, up: Upstream) -> List[dict]:
    ok, code, cands = await _places("hotel", inp["city"], up)
    if not ok:
        return [{"source": "google_places", "ok": False, "code": code}]
    now_s, items = ts(), []
    for c in cands:
        ref = "sty_" + c["place_id"]
        nightly = _fixture_price(ref, 8000, 22000)
        items.append({"stay_ref": ref, "name": wrap(c["name"], "google_places", now_s, cap=300),
                      **({"area": wrap(c["address"], "google_places", now_s, cap=300)} if c.get("address") else {}),
                      **({"rating": f"{float(c['rating']):.1f}"} if c.get("rating") is not None else {}),
                      "price_per_night": {"amount_minor": nightly, "currency": "EUR"}, "price_source": "quoted",
                      "_fixture": {"place_id": c["place_id"], "name": c["name"], "address": c.get("address")}})
    return [{"source": "google_places", "ok": True, "items": items}]


async def find_venues(inp: dict, up: Upstream, http=None) -> List[dict]:
    ok, code, cands = await _places(inp["what"], inp["where"], up, http=http)
    if not ok:
        return [{"source": "google_places", "ok": False, "code": code}]
    now_s, items = ts(), []
    for c in cands:
        v = {"venue_ref": "ven_" + c["place_id"], "name": wrap(c["name"], "google_places", now_s, cap=300)}
        if c.get("address"):
            v["address"] = wrap(c["address"], "google_places", now_s)
        if c.get("type"):
            v["kind"] = str(c["type"])[:40]
        if c.get("rating") is not None:
            v["rating"] = f"{float(c['rating']):.1f}"
        if c.get("rating_count") is not None:
            v["reviews"] = int(c["rating_count"])
        v["_fixture"] = {"place_id": c["place_id"], "name": c["name"], "address": c.get("address")}
        items.append(v)
    return [{"source": "google_places", "ok": True, "items": items}]


# ── Sherlock inside Austen: re-check an item at hold time ──────────────────────────────────────────────────────────────

def magic_offer(ref: str) -> dict:
    """A fixture flight for a magic ref (Part 4 §5), so partners can force each outcome."""
    d = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    return {"offer_ref": ref, "carrier": {"code": "ZZ", "name": {"text": "Sandbox Air", "source": "sandbox", "retrieved_at": ts()}},
            "flight_numbers": ["ZZ100"], "from": "MAD", "to": "LHR", "departs": f"{d}T10:00:00+01:00",
            "arrives": f"{d}T11:30:00+00:00", "stops": 0, "duration_minutes": 150,
            "price": {"amount_minor": 10000, "currency": "EUR"}, "price_source": "quoted", "expires_at": ts(datetime.now(timezone.utc) + timedelta(hours=2)),
            "_magic": ref}


async def recheck_flight(offer: dict, up: Upstream, passengers: int) -> Tuple[dict, str]:
    """→ (offer as re-checked now, rechecked_at). A gone or failed offer is an error, never a silent swap."""
    if offer.get("_magic"):
        o = dict(offer)
        return o, ts()
    from booking_signer import travel as T
    t0 = time.perf_counter()
    st, j = await T.HTTP("GET", f"/air/offers/{offer['offer_ref']}")
    if st == 404:
        up.add("duffel", t0, False, "upstream_refused")
        raise AgapiError("upstream_refused", "The airline no longer offers that fare; search again.",
                         {"service": "duffel", "reason": "offer_gone"})
    if st != 200:
        up.add("duffel", t0, False, "upstream_failed")
        raise AgapiError("upstream_failed", "The airline system answered with an error; nothing was held.", {"service": "duffel"})
    up.add("duffel", t0, True)
    o = dict(offer)
    o["price"] = {"amount_minor": _minor(j["data"]["total_amount"]), "currency": j["data"]["total_currency"]}
    return o, ts()


# ── Austen: the act (fixtures; a payment link first where money moves) ─────────────────────────────────────────────────

async def order_flight(offer: dict, travellers: List[dict], up: Upstream) -> Dict[str, Any]:
    """Duffel TEST order on the recorded replay. → {reference, words, sha256} — or an AgapiError with the right code."""
    from booking_signer import travel as T
    t0 = time.perf_counter()
    if offer.get("_magic"):
        return _magic_act(offer["_magic"], up, "duffel", t0)
    lead = travellers[0] if travellers else {"given_name": "Sandbox", "family_name": "Traveller"}
    try:
        got = await T.order(offer["_card"], f"{lead['given_name']} {lead['family_name']}", "sandbox-traveller@example.test", None)
    except Exception:
        up.add("duffel", t0, False, "upstream_unreachable")
        raise AgapiError("upstream_unreachable", "The airline system couldn't be reached; nothing was booked.", {"service": "duffel"})
    if "why" in got:
        up.add("duffel", t0, False, "upstream_refused")
        raise AgapiError("upstream_refused", "The airline refused the booking.", {"service": "duffel", "reason": "order_refused"})
    up.add("duffel", t0, True)
    ref = got.get("booking_reference") or "TEST"
    return {"reference": ref, "service": "duffel", "words": f"Order {got.get('order_id') or ''} — booking reference {ref} (Duffel TEST).",
            "sha256": _sha(got)}


def _magic_act(magic: str, up: Upstream, service: str, t0: float) -> Dict[str, Any]:
    if magic == "off_test_sold_out":
        up.add(service, t0, False, "upstream_refused")
        raise AgapiError("upstream_refused", "The fare is sold out.", {"service": service, "reason": "sold_out"})
    if magic == "off_test_timeout_before":
        up.add(service, t0, False, "upstream_timeout")
        raise AgapiError("upstream_timeout", "The airline didn't answer in time; nothing was sent.", {"service": service}, retry_after_s=5)
    if magic == "off_test_timeout_after":
        up.add(service, t0, False, "upstream_timeout")
        raise _Unknown(service)
    up.add(service, t0, True)
    ref = "SBX" + hashlib.sha256(str(time.time()).encode()).hexdigest()[:5].upper()
    return {"reference": ref, "service": service, "words": f"Booking reference {ref} (sandbox fixture).", "sha256": _sha({"ref": ref})}


class _Unknown(Exception):
    def __init__(self, service: str):
        super().__init__(service)
        self.service = service


async def send_documents(service: str, kind: str, values: Dict[str, str], up: Upstream) -> Dict[str, Any]:
    """CR 63 · the provider receiving a saved item at the moment of use (sandbox: accepted, NOTHING kept — not even a hash).
    Tests patch this to see what a provider would get."""
    t0 = time.perf_counter()
    up.add(service + "_documents", t0, True)
    ref = "DOC" + hashlib.sha256(f"{service}{time.time()}{os.urandom(8).hex()}".encode()).hexdigest()[:8].upper()
    return {"reference": ref, "service": service + "_documents",
            "words": f"Travel details received for the booking, reference {ref} (sandbox: nothing kept)."}


async def book_fixture(kind: str, item: dict, up: Upstream) -> Dict[str, Any]:
    """A fixture stay or venue: nothing is ever sent to a real venue in test mode. Confirmed by the fixture, said so."""
    t0 = time.perf_counter()
    service = "sandbox_venue" if kind == "venue" else "sandbox_stays"
    up.add(service, t0, True)
    ref = ("SBXV" if kind == "venue" else "SBXH") + hashlib.sha256(f"{item['ref']}{time.time()}".encode()).hexdigest()[:6].upper()
    words = (f"Table confirmed, reference {ref} — sandbox fixture venue; no real venue was contacted." if kind == "venue"
             else f"Stay confirmed, reference {ref} — sandbox fixture; no real hotel was contacted.")
    return {"reference": ref, "service": service, "words": words, "sha256": _sha({"ref": ref, "item": item["ref"]})}


async def cancel_fixture(service: str, act_id: str, up: Upstream) -> Dict[str, Any]:
    """The provider's cancellation (sandbox fixture: nothing real was booked, so nothing real is cancelled)."""
    t0 = time.perf_counter()
    up.add(service, t0, True)
    return {"reference": "CXL" + hashlib.sha256(f"{act_id}{time.time()}".encode()).hexdigest()[:6].upper(), "service": service,
            "words": "Cancellation confirmed (sandbox fixture; nothing real was booked or charged).", "sha256": _sha({"cancel": act_id})}


def resolve_unknown(service: str) -> Dict[str, Any]:
    """off_test_timeout_after: the act DID happen; status finds it (Part 1 I8)."""
    ref = "SBX" + hashlib.sha256(f"unknown{time.time()}".encode()).hexdigest()[:5].upper()
    return {"reference": ref, "service": service, "words": f"Found on status: booking reference {ref} (sandbox fixture).",
            "sha256": _sha({"ref": ref})}
