"""Sasha 248 · ONE VENUE TRUTH — what a place IS, how it books, and how it's shown, from ONE source: AgAPI's read of the venue's
OWN site (Pacioli-checked: every fact quoted from a page, verbatim, on the business's own domain). Tyler's S2 test, 12 Oct: a Spanish
restaurant labelled "Korean", the booking form never brought up, thumbnails that don't open — each because Sasha decided venue facts,
the channel and the card in several places of her own (inventory: docs/sasha/s248-report.md).

  profile(place)   → PLACE: the one data shape every surface shows (S2, /next, WhatsApp) — name, type, hours, price, photos, site,
                     the booking channel — each fact with its source. A map/Places category is only a LABELLED fallback
                     ("listed on Google as …"), never stated as fact.
  channel(prof)    → the venue's ONE booking channel, from the engine (its rung), and whether there's another way to ask.
  ASK_FILL         → the one question, word for word, when a form AND another channel exist.

THE ENGINE is one adapter: ENGINE_OP. Today CR 83's dive.onboard (on the sandbox, agapi_route family "venues"); when CR 89's
venue.profile is live, switching is this one line (and the family's route). Reads happen on AgAPI's server, never from Sasha's
machine; a booking platform is never read (dive refuses one).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

log = logging.getLogger("agapi.venue_truth")

ENGINE_OP = "dive.onboard"            # ← CR 89: "venue.profile" (one line)
FAMILY = "venues"
TTL_S = 24 * 3600
ENGINE_TIMEOUT_S = 75.0
ASK_FILL = ("Want me to fill it in now so you just tap confirm on your phone, or shall I send them the request and let you know "
            "when they reply?")
FILLABLE = ("form", "own_engine", "widget")            # the venue's own booking form / engine: rung 2
REQUESTS = ("email", "whatsapp")                       # a request they answer
_CACHE: Dict[str, Dict[str, Any]] = {}                 # website host → {"at", "profile"}
_INFLIGHT: Dict[str, asyncio.Future] = {}


def _host(url: Optional[str]) -> str:
    from urllib.parse import urlsplit
    try:
        h = (urlsplit(url if "://" in str(url or "") else f"https://{url}").hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


async def _agapi(op: str, body: dict) -> Dict[str, Any]:
    """The engine's transport — the family's AgAPI (agapi_route), its own key. Never printed."""
    import httpx
    from agapi import agapi_route as AR
    live = AR.route(FAMILY) == "live"
    url = (os.getenv("SASHA_AGAPI_URL", "https://agapi-live-production.up.railway.app") if live
           else os.getenv("SASHA_AGAPI_TEST_URL", "https://agapi-sandbox-production.up.railway.app")).rstrip("/")
    key = os.getenv("SASHA_AGAPI_KEY" if live else "SASHA_AGAPI_TEST_KEY", "").strip()
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "the venue engine isn't switched on"}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(ENGINE_TIMEOUT_S)) as c:
            r = await c.post(f"{url}/v1/{op}", headers={"Authorization": f"Bearer {key}", "content-type": "application/json",
                                                         "Idempotency-Key": "s2vt_" + secrets.token_hex(12)}, content=json.dumps(body))
        return r.json()
    except Exception as e:
        return {"ok": False, "error": {"code": "unreachable", "message": type(e).__name__}}


CALL: Callable[..., Awaitable[Dict[str, Any]]] = _agapi   # tests / the gate replace it (scripts/venue_engine_fake.py)


def _fact(f: Optional[dict]) -> Optional[dict]:
    """A fact only when it was found AND Pacioli passed it: its value, the line it came from, the page."""
    if not f or f.get("state") != "found" or not (f.get("pacioli") or {}).get("passed") or not f.get("value"):
        return None
    return {"value": str(f["value"])[:200], "quote": str(f.get("quote") or "")[:400], "source_url": f.get("source_url"), "source": "site"}


def _from_engine(res: dict) -> dict:
    """dive.onboard's stages → the profile's site facts and channel. (venue.profile: the same keys, read directly.)"""
    st = {s.get("stage"): s for s in res.get("stages") or [] if isinstance(s, dict)}
    facts = {f.get("field"): f for f in (st.get("understood") or {}).get("facts") or []}
    hb = st.get("how_it_books") or {}
    read = {f.get("kind"): f for f in hb.get("channels_read") or [] if (f.get("pacioli") or {}).get("passed")}
    kinds = []
    if hb.get("rung") == 2:
        kinds.append({"kind": "own_engine" if "booking engine" in str(hb.get("channel") or "") else
                      ("widget" if "widget" in read else "form"), "name": hb.get("channel"), "url": hb.get("evidence")})
    for a in hb.get("also") or []:
        if a.get("kind") in ("email", "whatsapp", "phone") and a.get("value"):
            kinds.append({"kind": a["kind"], "value": a["value"]})
    if hb.get("rung") in (3, 4) and not any(k["kind"] in REQUESTS for k in kinds):
        kinds.insert(0, {"kind": "email" if hb.get("rung") == 3 else "whatsapp", "value": hb.get("evidence")})
    return {"name": _fact(facts.get("name")), "type": _fact(facts.get("type")), "hours": _fact(facts.get("hours")),
            "price": _fact(facts.get("price_range")), "city": _fact(facts.get("city")), "channels": kinds,
            "rung": hb.get("rung"), "rung_label": hb.get("rung_label"), "engine_said": hb.get("say"),
            "cant_read": (res.get("cant_read") or {}).get("say") if isinstance(res.get("cant_read"), dict) else res.get("cant_read")}


async def _read_site(website: str, replay: bool = False) -> Optional[dict]:
    host = _host(website)
    if not host:
        return None
    hit = _CACHE.get(host)
    if hit and time.time() - hit["at"] < TTL_S:
        return hit["profile"]
    if host in _INFLIGHT:   # one read per site at a time (a search and a tap on the same place share it)
        return await asyncio.shield(_INFLIGHT[host])
    fut = asyncio.get_running_loop().create_future()
    _INFLIGHT[host] = fut
    try:
        r = await CALL(ENGINE_OP, {"url": website, **({"replay": True} if replay else {})})
        out = _from_engine(r["result"]) if r.get("ok") else {"cant_read": (r.get("error") or {}).get("message") or "the venue engine didn't answer"}
        if r.get("ok"):
            _CACHE[host] = {"at": time.time(), "profile": out}
        fut.set_result(out)
        return out
    except Exception as e:
        log.warning("[venue_truth] %s not read: %s", host, type(e).__name__)
        fut.set_result(None)
        return None
    finally:
        _INFLIGHT.pop(host, None)


def cached(place: dict) -> Optional[dict]:
    hit = _CACHE.get(_host(place.get("website")))
    return hit["profile"] if hit and time.time() - hit["at"] < TTL_S else None


def google_label(place: dict) -> Optional[dict]:
    t = place.get("google_type") or place.get("type")
    return {"value": f"listed on Google as {t}", "source": "google"} if t else None


def shape(place: dict, site: Optional[dict]) -> dict:
    """THE ONE PLACE SHAPE — the card and its detail sheet, on every surface."""
    site = site or {}
    photos = [p for p in ([place.get("photo")] + [g.get("uri") for g in place.get("gphotos") or [] if isinstance(g, dict)]
                          + ([(place.get("gphoto") or {}).get("uri")] if isinstance(place.get("gphoto"), dict) else [])) if p]
    oa = place.get("open_at")
    return {"place_id": place.get("place_id"), "name": (site.get("name") or {}).get("value") or place.get("name"),
            "listing_name": place.get("name"), "website": place.get("website"),
            "type": site.get("type") or google_label(place),
            "hours": site.get("hours") or ({"value": oa.get("words"), "source": "google"} if isinstance(oa, dict) and oa.get("words") else None),
            "price": site.get("price") or ({"value": place["price_words"], "source": "google"} if place.get("price_words") else None),
            "photos": list(dict.fromkeys(photos))[:6], "photos_source": "google" if photos else None,
            "rating": place.get("rating"), "rating_count": place.get("rating_count"), "area": place.get("area") or place.get("address"),
            "listing_url": place.get("listing_url"),
            "channel": channel(site) if site else None,
            "read": "site" if site and not site.get("cant_read") else ("cant_read" if site.get("cant_read") else "pending"),
            **({"cant_read": site["cant_read"]} if site.get("cant_read") else {})}


async def profile(place: dict, replay: bool = False) -> dict:
    """The place, from its own site (the engine), shaped once. No website → the listing only, labelled."""
    site = await _read_site(place["website"], replay) if place.get("website") else None
    return shape(place, site)


_BG: set = set()   # reads that outlast a search's budget: held here until they finish (they warm the cache for the detail sheet)


async def profiles(places: List[dict], budget_s: float = 3.0) -> List[dict]:
    """A search's cards: each read within the budget (a cached read is instant); one not ready is shown with the listing,
    labelled, and its read finishes for its detail sheet (held in _BG — never a dropped task)."""
    async def one(p):
        t = asyncio.ensure_future(profile(p))
        _BG.add(t)
        t.add_done_callback(_BG.discard)
        try:
            return await asyncio.wait_for(asyncio.shield(t), timeout=budget_s)
        except asyncio.TimeoutError:
            return shape(p, None)
    return list(await asyncio.gather(*[one(p) for p in places]))


async def enrich(cards: List[dict], budget_s: float = 3.0) -> None:
    """THE CARDS' FACTS, ONE SOURCE (Sasha 248): each shown card's display type is the site's own words, else Google's category
    labelled "listed on Google as …"; the raw Google type is kept apart (google_type) for search filters only; the card carries its
    place shape for the detail sheet."""
    for c in cards:
        c.setdefault("google_type", c.get("type"))
    shaped = await profiles(cards, budget_s)
    for c, p in zip(cards, shaped):
        c["type"] = type_words(p) or None
        c["type_source"] = (p.get("type") or {}).get("source")
        c["place"] = p


def channel(site: Optional[dict]) -> Optional[dict]:
    """The venue's ONE booking channel (the engine's rung) — and its request alternative, for the one question."""
    ks = (site or {}).get("channels") or []
    first = next((k for k in ks if k["kind"] in FILLABLE), None) or next((k for k in ks if k["kind"] in REQUESTS), None) \
        or next((k for k in ks if k["kind"] == "phone"), None)
    if not first:
        return None
    alt = next((k for k in ks if k["kind"] in REQUESTS), None) if first["kind"] in FILLABLE else None
    return {**first, **({"alternative": alt} if alt else {}), "ask": ASK_FILL if alt else None}


def text(p: dict) -> str:
    """WhatsApp: the same detail as the sheet, as text + its link."""
    lines = [f"*{p.get('name')}*"]
    for k, label in (("type", None), ("hours", "Hours"), ("price", "Prices")):
        f = p.get(k)
        if f and f.get("value"):
            v = f["value"] if f.get("source") == "google" and k == "type" else (f"{label}: {f['value']}" if label else f["value"])
            src = " (their site)" if f.get("source") == "site" else (" (Google)" if f.get("source") == "google" and k != "type" else "")
            lines.append(v[0].upper() + v[1:] + src)
    if p.get("rating"):
        lines.append(f"★{p['rating']}" + (f" ({p['rating_count']} reviews on Google)" if p.get("rating_count") else " on Google"))
    ch = p.get("channel")
    if ch:
        lines.append("Books: " + {"own_engine": "their own booking engine", "form": "their own booking form", "widget": "their booking page",
                                   "email": "by email", "whatsapp": "on WhatsApp", "phone": "by phone"}.get(ch["kind"], ch["kind"]))
    if p.get("website"):
        lines.append(p["website"])
    return "\n".join(lines)


def type_words(p: dict) -> str:
    """What she may SAY the place is: the site's own words; Google's only as "listed on Google as …"."""
    t = p.get("type") or {}
    return t.get("value") or ""


__all__ = ["profile", "profiles", "enrich", "shape", "channel", "cached", "text", "type_words", "google_label", "ASK_FILL", "ENGINE_OP", "CALL"]
