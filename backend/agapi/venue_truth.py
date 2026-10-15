"""Sasha 248 · ONE VENUE TRUTH — what a place IS, how it books, and how it's shown, from ONE source: AgAPI's read of the venue's
OWN site (Pacioli-checked: every fact quoted from a page, verbatim, on the business's own domain). Tyler's S2 test, 12 Oct: a Spanish
restaurant labelled "Korean", the booking form never brought up, thumbnails that don't open — each because Sasha decided venue facts,
the channel and the card in several places of her own (inventory: docs/sasha/s248-report.md).

  profile(place)   → PLACE: the one data shape every surface shows (S2, /next, WhatsApp) — name, type, hours, price, photos, site,
                     the booking channel — each fact with its source. A map/Places category is only a LABELLED fallback
                     ("listed on the map as …"), never stated as fact.
  channel(prof)    → the venue's ONE booking channel, from the engine (its rung), and whether there's another way to ask.
  ASK_FILL         → the one question, word for word, when a form AND another channel exist.

THE ENGINE is one adapter: ENGINE_OP. Today CR 83's dive.onboard (on the sandbox, agapi_route family "venues"); when CR 89's
venue.profile is live, switching is this one line (and the family's route). Reads happen on AgAPI's server, never from Sasha's
machine; a booking platform is never read (dive refuses one).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

log = logging.getLogger("agapi.venue_truth")

ENGINE_OP = "venue.profile"           # CR 89 (agapi v1.6.0, 12 Oct) — was "dive.onboard"; _from_engine reads either shape
FAMILY = "venues"
TTL_S = 24 * 3600
ENGINE_TIMEOUT_S = 75.0
from app.agent.voice import ASK_BOOK as ASK_FILL   # Sasha 249 · the one booking question lives in her voice (app/agent/voice.py)
FILLABLE = ("form", "own_engine", "widget")            # the venue's own booking form / engine: rung 2
PREPARED = FILLABLE + ("whatsapp",)                    # prepared by venue.prepare_booking: a form to confirm, a WhatsApp to send
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
    from agapi import agapi_route as AR
    url, key = await AR.client_for(FAMILY)   # Sasha 249 · ONE ROUTE (the copied URL/key block is gone)
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "the venue engine isn't switched on"}}
    return await AR.post(url, key, op, body, {"Authorization": f"Bearer {key}", "content-type": "application/json",
                                             "Idempotency-Key": "s2vt_" + secrets.token_hex(12)}, ENGINE_TIMEOUT_S)   # Sasha 261 · the one transport (agapi_route.post): an AgAPI outage is named there, once, for every family


CALL: Callable[..., Awaitable[Dict[str, Any]]] = _agapi   # tests / the gate replace it (scripts/venue_engine_fake.py)


def _fact(f: Optional[dict]) -> Optional[dict]:
    """A fact only when it was found AND Pacioli passed it: its value, the line it came from, the page."""
    if not f or f.get("state") != "found" or not (f.get("pacioli") or {}).get("passed") or not f.get("value"):
        return None
    return {"value": str(f["value"])[:200], "quote": str(f.get("quote") or "")[:400], "source_url": f.get("source_url"), "source": "site"}


def _vp_fact(f: Optional[dict]) -> Optional[dict]:
    """venue.profile's fact: every value it returns is Pacioli-checked (else it's in `withheld`). A map category comes back only as
    a FALLBACK (facts.type.fallback) — said "listed on the map as …", never as what the place is (CR 89, row 775)."""
    if not isinstance(f, dict) or not f.get("value"):
        return None
    if f.get("fallback"):   # Sasha 250 · a map category is never what the place is (D3: the cuisine from their own site only)
        return None
    return {"value": str(f["value"])[:200], "quote": str(f.get("quote") or "")[:400], "source_url": f.get("source_url"), "source": "site",
            **({"map_says": (f.get("map_says") or {}).get("listed_as")} if isinstance(f.get("map_says"), dict) else {})}


def _from_profile(res: dict) -> dict:
    """CR 89's venue.profile → the same site facts and channel shape (facts.*, photos, booking.{rung, channel, evidence, also})."""
    facts, bk = res.get("facts") or {}, res.get("booking") or {}
    kinds = []
    if bk.get("rung") == 2:
        ch = str(bk.get("channel") or "")
        kinds.append({"kind": "own_engine" if "engine" in ch else ("widget" if "widget" in ch.lower() else "form"), "name": ch,
                      "url": bk.get("evidence") if str(bk.get("evidence") or "").startswith("http") else bk.get("evidence_on")})
    elif bk.get("rung") in (3, 4):
        kinds.append({"kind": "email" if bk["rung"] == 3 else "whatsapp", "value": bk.get("evidence")})
    for a in bk.get("also") or []:
        if a.get("kind") in ("email", "whatsapp", "phone") and a.get("value") and not a.get("note"):   # a conditional one ("groups of 12+") isn't a way to book this
            kinds.append({"kind": a["kind"], "value": a["value"]})
    if bk.get("rung") == 2 and kinds and isinstance(res.get("form"), dict):   # Sasha 270 · the engine's own CAPTCHA reading (CR 101: on
        kinds[0]["engine_captcha"] = bool(res["form"].get("captcha"))      # evidence only) — the one path reads it, never Sasha's guess
    photos = [p.get("url") for p in res.get("photos") or [] if isinstance(p, dict) and str(p.get("url") or "").startswith("https://")]
    return {"name": _vp_fact(facts.get("name")), "type": _vp_fact(facts.get("type")), "hours": _vp_fact(facts.get("hours")),
            "price": _vp_fact(facts.get("price_range")), "city": _vp_fact(facts.get("city")), "channels": kinds, "photos": photos,
            "rung": bk.get("rung"), "rung_label": bk.get("rung_label"), "engine_said": bk.get("say"), "confirm": res.get("confirm"),
            "form": res.get("form"),
            # Sasha 270 · CR 101 (row 1000): their listing's reservable as a fact with its source and its words; every channel the
            # engine classified (site / person), each with its owner — Sasha reads these, never decides "has a form" herself
            **({"reservable": res["reservable"]} if isinstance(res.get("reservable"), dict) else {}),
            **({"sources": [c for c in res["channels"] if isinstance(c, dict)]} if isinstance(res.get("channels"), list) else {}),
            "venue_id": res.get("venue_id"), "cant_read": _said(res.get("cant_read"))}


def _from_engine(res: dict) -> dict:
    """The engine's answer → the profile's site facts and channel: venue.profile (CR 89) or dive.onboard's stages (CR 83)."""
    if isinstance(res.get("facts"), dict):
        return _from_profile(res)
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
            "cant_read": _said(res.get("cant_read"))}


async def _read_site(website: Optional[str], replay: bool = False, place: Optional[dict] = None, key: Optional[str] = None) -> Optional[dict]:
    place = place or {"website": website}
    host = key or _host(website)   # Sasha 270 · a listing read (no website) is kept under "place:<place_id>"
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
        r = await CALL(ENGINE_OP, {"url": website, **({"replay": True} if replay else {})} if ENGINE_OP == "dive.onboard" else
                       {"place": {k: v for k, v in place.items() if v}})
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


async def prepare(place: dict, person: dict, date: str, time_: str, party: int) -> Optional[dict]:
    """"Fill it now" (CR 89's venue.prepare_booking): a ready-to-confirm link for their phone — NOTHING is submitted; human_step is
    theirs. None when the engine doesn't prepare it (then their own page + the details to copy, as before)."""
    if ENGINE_OP != "venue.profile":
        return None
    body = {"place": {k: v for k, v in {"name": place.get("name"), "website": place.get("website"), "place_id": place.get("place_id")}.items() if v},
            "person": {k: v for k, v in person.items() if v}, "date": date, "time": time_, "party": int(party)}
    try:
        r = await CALL("venue.prepare_booking", body)
    except Exception as e:
        log.warning("[venue_truth] prepare_booking failed: %s", type(e).__name__)
        return None
    res = r.get("result") or {}
    if not r.get("ok") or res.get("submitted") or not str(res.get("link") or "").startswith("https://"):
        return None   # never a booking that went out by itself; never a link that isn't one
    return {"link": res["link"], "say": res.get("say"), "human_step": res.get("human_step"), "missing": res.get("missing") or [],
            "expires_at": res.get("expires_at")}


def _key_of(place: dict) -> str:
    """The cache key: their website's host; with no website, their listing ("place:<place_id>" — Sasha 270)."""
    h = _host(place["website"]) if place.get("website") else ""   # never _host(None): that is "none", one key for every listing
    return h or (f"place:{place['place_id']}" if place.get("place_id") else "")


def cached(place: dict) -> Optional[dict]:
    hit = _CACHE.get(_key_of(place))
    return hit["profile"] if hit and time.time() - hit["at"] < TTL_S else None


def _said(x) -> Optional[str]:
    """Sasha 250 · why a site couldn't be read, as ONE sentence on every surface: the engine sends {rule, say, evidence, at} — the
    detail sheet rendered that object and the whole page crashed (found live on /s2: "the sheet closes")."""
    if isinstance(x, dict):
        return str(x.get("say") or x.get("evidence") or x.get("rule") or "their site couldn't be read")[:300]
    return str(x)[:300] if x else None


def shape(place: dict, site: Optional[dict]) -> dict:
    """THE ONE PLACE SHAPE — the card and its detail sheet, on every surface."""
    site = site or {}
    known = (place.get("place") or {}).get("type") if isinstance(place.get("place"), dict) else None
    if isinstance(known, dict) and known.get("source") != "site":
        known = None   # Sasha 250 · a map category kept from an older card is not what the place is
    if not site.get("type") and not known and place.get("type_source") == "site" and place.get("type"):
        known = {"value": place["type"], "source": "site"}   # the site's words this card already carries — never relabelled as the map's
    own = list((site or {}).get("photos") or [])
    photos = own + [p for p in ([place.get("photo")] + [g.get("uri") for g in place.get("gphotos") or [] if isinstance(g, dict)]
                                + ([(place.get("gphoto") or {}).get("uri")] if isinstance(place.get("gphoto"), dict) else [])) if p]
    oa = place.get("open_at")
    held = place.get("facts") or {}   # Sasha 252 · facts another engine read quoted for THIS card (an activity's day): kept first
    # Sasha 252 · an activity keeps its own name: its official site can be an umbrella's (the Jerónimos card read "Museus e
    # Monumentos de Portugal")
    name = place.get("name") if place.get("activity") else ((site.get("name") or {}).get("value") or place.get("name"))
    return {"place_id": place.get("place_id"), "name": name,
            "listing_name": place.get("name"), "website": place.get("website"),
            # Sasha 250 · WHAT IT IS comes from their own site, or nothing — never the map's category, not even labelled (D3; the
            # map called arroz restaurants "Korean"). The map's word stays on the record (map_says) and in google_type for filters.
            "type": held.get("type") or site.get("type") or known,
            **({"map_says": place.get("google_type") or place.get("type")} if (place.get("google_type") or place.get("type_source") != "site") and (place.get("google_type") or place.get("type")) else {}),
            "hours": held.get("hours") or site.get("hours") or ({"value": oa.get("words"), "source": "google"} if isinstance(oa, dict) and oa.get("words") else None),
            "price": held.get("price") or site.get("price") or ({"value": place["price_words"], "source": "google"} if place.get("price_words") else None),
            "photos": list(dict.fromkeys(photos))[:6], "photos_source": "site" if own else ("google" if photos else None),
            "photos_own": len([p for p in dict.fromkeys(photos) if p in own][:6]),   # the first N are the venue's own; the rest Google's
            "rating": place.get("rating"), "rating_count": place.get("rating_count"), "area": place.get("area") or place.get("address"),
            "listing_url": place.get("listing_url"),
            "channel": channel(site) if site else None,
            "read": "site" if site and not site.get("cant_read") else ("cant_read" if site.get("cant_read") else "pending"),
            **({"cant_read": _said(site["cant_read"])} if site.get("cant_read") else {})}


async def profile(place: dict, replay: bool = False, listing: bool = False) -> dict:
    """The place, from its own site (the engine), shaped once. No website → the listing only, labelled.
    Sasha 270 · listing=True (the one path's booking, never a search's cards): no website but a place_id → venue.profile on their listing
    alone (CR 101: reservable, its website if Places has one) — the engine's answer, kept under "place:<place_id>"."""
    meta = {"name": place.get("name"), "website": place.get("website"),
            "category": place.get("google_type") or (place.get("type") if place.get("type_source") != "site" else None),
            "place_id": place.get("place_id")}
    if place.get("website"):
        site = await _read_site(place["website"], replay, meta)
    elif listing and place.get("place_id") and ENGINE_OP == "venue.profile":
        site = await _read_site(None, replay, {"place_id": place["place_id"], "name": place.get("name")}, key=_key_of(place))
    else:
        site = None
    return shape(place, site)


def person_channel(res: dict, url: str) -> Optional[dict]:
    """The channel venue.profile classified for the link the person handed over (source "person"): its kind, owner, say."""
    ch = [c for c in res.get("channels") or [] if isinstance(c, dict) and c.get("source") == "person"]
    return next((c for c in reversed(ch) if str(c.get("url") or "") == str(url)[:500]), ch[-1] if ch else None)


async def link_profile(place: dict, url: str) -> Dict[str, Any]:
    """Sasha 270 · CR 101 · A LINK THE PERSON HANDED OVER (chat, a voice transcript, WhatsApp): venue.profile link {url} (+ place.place_id
    and their website when Sasha has them). The ONE classifier says what it IS and whose it is — channels[].owner: "kanoe" (Sasha fills
    it after the one yes) or "the person" (handed to them with its say). Sasha never loads the link herself.
      → {ok, channel {kind, owner, say, host, url, note?}, reservable?, booking?, form?} or {ok: False, error}"""
    body = {"link": {"url": str(url)[:500]},
            **({"place": {k: v for k, v in {"place_id": place.get("place_id"), "name": place.get("name")}.items() if v}}
               if place.get("place_id") or place.get("name") else {}),
            **({"url": place["website"]} if place.get("website") else {})}
    try:
        r = await CALL(ENGINE_OP, body)
    except Exception as e:
        log.warning("[venue_truth] a handed-over link wasn't classified: %s", type(e).__name__)
        return {"ok": False, "error": {"code": "unavailable", "message": "the venue engine didn't answer"}}
    if not r.get("ok"):
        return {"ok": False, "error": {"code": (r.get("error") or {}).get("code") or "unavailable",
                                       "message": (r.get("error") or {}).get("message") or "the venue engine didn't answer"}}
    res = r.get("result") or {}
    return {"ok": True, "channel": person_channel(res, url), "booking": res.get("booking"), "form": res.get("form"),
            **({"reservable": res["reservable"]} if isinstance(res.get("reservable"), dict) else {})}


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
    labelled "listed on the map as …"; the raw Google type is kept apart (google_type) for search filters only; the card carries its
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
    return {**first, **({"alternative": alt} if alt else {}), "ask": ASK_FILL if alt else None,
            "confirm": ((site or {}).get("confirm") or {}).get("type"), "has_form": bool((site or {}).get("form"))}


def text(p: dict) -> str:
    """WhatsApp: the same detail as the sheet, as text + its link."""
    lines = [f"*{p.get('name')}*"]
    for k, label in (("type", None), ("hours", "Hours"), ("price", "Prices")):
        f = p.get(k)
        if f and f.get("value"):
            v = f"{label}: {f['value']}" if label else f["value"]
            src = " (their site)" if f.get("source") == "site" else (" (Google)" if f.get("source") == "google" else "")
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
    """What she may SAY the place is: the site's own words — nothing else (Sasha 250: never the map's category)."""
    t = p.get("type") or {}
    return t.get("value") or ""


def reservable_say(place: Optional[dict]) -> Optional[str]:
    """Sasha 270 · CR 101 · what their listing says about reservations, in the engine's words ("They take reservations."), when it said."""
    r = ((cached(place) or {}) if place else {}).get("reservable") or {}
    return str(r["say"]) if isinstance(r, dict) and r.get("say") else None


__all__ = ["profile", "profiles", "enrich", "shape", "channel", "cached", "text", "type_words", "ASK_FILL", "ENGINE_OP", "CALL",
           "link_profile", "person_channel", "reservable_say"]
