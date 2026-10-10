"""CR 71 · S2 ON AGAPI — the switch SASHA_S2_VIA_AGAPI, read ONLY at /s2's own tool selection (app/agent/sasha.py, the
`surface == "s2"` block). /next and S1 never read it: their tools run through agapi.v0.call exactly as before.

  0 (default, or anything unrecognised)  S2 exactly as today: Sasha's own engine, no AgAPI call.
  shadow   Sasha's own engine answers (shown and done as today); AgAPI is asked the same READ question alongside (search_flights,
           search_venues), the two answers are compared and the differences logged — nothing from AgAPI is shown or done.
  reads    search_flights is answered by AgAPI live (the same Duffel offers, by their ids), fed into Sasha's basket exactly as her own
           search does, so choose_offer and book work unchanged; if AgAPI can't answer, Sasha's own engine answers (never a gap).
           search_venues stays on Sasha's engine (AgAPI's venues don't carry the card's fields yet: photo, phone, website, ranking) and
           stays compared as in shadow.
  1        reads, today. Acts (book, book_venue, send_email…) move to AgAPI once AgAPI accepts S2's in-chat yes as an approval —
           an AgAPI/EU decision, named in docs/sasha/s2-via-agapi-wiring.md. Until then every act stays on Sasha's own engine.
FLIP BACK: SASHA_S2_VIA_AGAPI=0 (or unset) — the next tool call is Sasha's own again; nothing else changes.

Each guest's own sign-in token goes with every AgAPI call (X-Sasha-Guest-Token), so AgAPI acts as THAT guest at Sasha's booking
routes. The AgAPI key (SASHA_AGAPI_KEY, agp_live_…) and URL (SASHA_AGAPI_URL) are Railway variables; never printed."""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import time
from collections import deque
from typing import Any, Awaitable, Callable, Dict, List, Optional

log = logging.getLogger("agapi.via_agapi")

MODES = ("0", "shadow", "reads", "1")
GUEST_TOKEN: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("s2_guest_token", default=None)
SHADOW_LOG: deque = deque(maxlen=200)      # the last comparisons (ops and tests read it); no guest data — names, numbers, prices
SHADOW_TASKS: set = set()                  # tests await these; the turn never does
TIMEOUT_S = 12.0


def mode() -> str:
    m = os.getenv("SASHA_S2_VIA_AGAPI", "0").strip().lower()
    return m if m in MODES else "0"


def _url() -> str:
    return os.getenv("SASHA_AGAPI_URL", "https://agapi-live-production.up.railway.app").rstrip("/")


async def _agapi(op: str, body: dict) -> Dict[str, Any]:
    """One AgAPI live call as this guest. → the envelope (ok/result/error); a transport failure is an envelope too."""
    import httpx
    key = os.getenv("SASHA_AGAPI_KEY", "").strip()
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "SASHA_AGAPI_KEY isn't set"}}
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    tok = GUEST_TOKEN.get()
    if tok:
        h["X-Sasha-Guest-Token"] = tok
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S)) as c:
            r = await c.post(f"{_url()}/v1/{op}", headers=h, content=json.dumps(body))
        return r.json()
    except Exception as e:
        return {"ok": False, "error": {"code": "unreachable", "message": type(e).__name__}}


CALL: Callable[[str, dict], Awaitable[Dict[str, Any]]] = _agapi   # tests replace it


# ── S2's read tools, as AgAPI questions ────────────────────────────────────────────────────────────────────────────────

def _flights_in(a: dict) -> dict:
    from agapi.v0 import airport_of
    return {"origin": {"query": airport_of(a["origin"])}, "destination": {"query": airport_of(a["destination"])}, "date": a["date"],
            "passengers": int(a.get("passengers") or 2), **({"preferences": ["direct"]} if "direct" in str(a.get("preferences") or "").lower()
                                                            or "nonstop" in str(a.get("preferences") or "").lower() else {})}


def _venues_in(a: dict) -> dict:
    where = str(a.get("where") or a.get("city") or "").strip()
    return {"what": str(a.get("what") or "restaurant")[:60], "where": {"query": where[:80] or "Madrid",
                                                                       **({"country": a["country"]} if a.get("country") else {})}}


READS = {"search_flights": ("travel.find_flights", _flights_in), "search_venues": ("venues.find_venues", _venues_in)}


def _offer_card(o: dict) -> dict:
    """AgAPI's offer → Sasha's flight card (the fields _flight_out and the basket read). The id IS Duffel's offer id."""
    return {"id": o["offer_ref"], "owner": (o.get("carrier") or {}).get("name", {}).get("text") if isinstance((o.get("carrier") or {}).get("name"), dict)
            else (o.get("carrier") or {}).get("name"), "flights": " + ".join(o.get("flight_numbers") or []), "from": o.get("from"), "to": o.get("to"),
            "departs": o.get("departs"), "arrives": o.get("arrives"), "stops": int(o.get("stops") or 0), "minutes": int(o.get("duration_minutes") or 0),
            "amount": f"{(o.get('price') or {}).get('amount_minor', 0) / 100:.2f}", "currency": (o.get("price") or {}).get("currency"),
            "expires_at": o.get("expires_at")}


def _key_flights(fl: List[dict]) -> set:
    return {(str(f.get("flights") or "").replace(" ", ""), str(f.get("departs") or "")[:16], round(float(f.get("price_eur") or 0), 2)) for f in fl}


def _key_venues(vs: List[dict]) -> set:
    return {str((v.get("name") or {}).get("text") if isinstance(v.get("name"), dict) else v.get("name") or "").strip().lower() for v in vs} - {""}


def compare(tool: str, mine: Dict[str, Any], theirs: Dict[str, Any], ms: int) -> dict:
    """Sasha's answer vs AgAPI's, for the log: the same? what only one side had (names, flight numbers, prices — no guest data)."""
    entry: Dict[str, Any] = {"tool": tool, "mode": mode(), "agapi_ms": ms, "at": time.time()}
    if not theirs.get("ok"):
        entry.update(same=False, agapi_error=(theirs.get("error") or {}).get("code"))
    elif not mine.get("ok"):
        entry.update(same=False, sasha_error=(mine.get("error") or {}).get("code"))
    else:
        if tool == "search_flights":
            a = _key_flights(mine["result"].get("flights") or [])
            b = _key_flights([_flight_from_offer(o) for o in theirs["result"].get("offers") or []])
        else:
            a = _key_venues(mine["result"].get("venues") or [])
            b = _key_venues(theirs["result"].get("venues") or [])
        entry.update(same=a == b, sasha_n=len(a), agapi_n=len(b), only_sasha=sorted(map(str, a - b))[:5], only_agapi=sorted(map(str, b - a))[:5])
    SHADOW_LOG.append(entry)
    log.warning("[s2-via-agapi] %s", json.dumps(entry, default=str))
    return entry


def _flight_from_offer(o: dict) -> dict:
    from agapi.v0 import _flight_out
    return _flight_out(_offer_card(o))


async def _flights_from_agapi(ctx, a: dict, theirs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """reads: AgAPI's offers as Sasha's search_flights result, fed into her basket as her own search does. None → Sasha answers."""
    from agapi import v0 as API
    offers = (theirs.get("result") or {}).get("offers") or [] if theirs.get("ok") else []
    cards = [_offer_card(o) for o in offers]
    cards = [c for c in cards if c.get("currency") == "EUR"] or cards
    pref = str(a.get("preferences") or "").lower()
    if "morning" in pref:
        cards = [c for c in cards if str(c.get("departs"))[11:13] < "12"] or cards
    elif "evening" in pref:
        cards = [c for c in cards if str(c.get("departs"))[11:13] >= "17"] or cards
    cards = cards[:6]
    if not cards:
        return None                              # nothing from AgAPI (or the nearest-day healing it doesn't do): Sasha's own engine
    leg, party = a.get("leg") or "out", int(a.get("passengers") or 2)
    p = await API._latest(ctx)
    if p:   # the flights shown are the trip's suggestions (the basket), exactly as her own search does
        await API._suggest_flights(ctx, p["trip_id"], cards, a["origin"], a["destination"], a["date"], party, leg)
    return {"ok": True, "result": {"leg": leg, "date": a["date"], "flights": [API._flight_out(c) for c in cards],
                                   "note": "Duffel TEST fares — nothing is held until book"}}


# ── the runner /s2's tool selection installs ───────────────────────────────────────────────────────────────────────────

def runner(base: Callable[..., Awaitable[Dict[str, Any]]], m: Optional[str] = None) -> Callable[..., Awaitable[Dict[str, Any]]]:
    """/s2 only. → the tool runner for this turn: `base` (agapi.v0.call) itself in mode 0, otherwise base + AgAPI per the mode."""
    m = m or mode()
    if m == "0":
        return base

    asked = {t.strip() for t in os.getenv("SASHA_S2_SHADOW_TOOLS", "search_flights").split(",") if t.strip()}   # Sasha 225 · flights only
                                                                                                                # (venues would spend Places calls)
    async def run(ctx, name: str, args: dict) -> Dict[str, Any]:
        if name not in READS or name not in asked:
            return await base(ctx, name, args)          # every act and every other tool: Sasha's own engine (see the module doc)
        op, shape = READS[name]
        try:
            q = shape(args)
        except Exception:
            return await base(ctx, name, args)
        t0 = time.perf_counter()
        task = asyncio.ensure_future(CALL(op, q))
        if m in ("reads", "1") and name == "search_flights":
            try:
                theirs = await asyncio.wait_for(asyncio.shield(task), TIMEOUT_S)
            except Exception:
                theirs = {"ok": False, "error": {"code": "timeout"}}
            got = await _flights_from_agapi(ctx, args, theirs)
            if got is not None:
                SHADOW_LOG.append({"tool": name, "mode": m, "served_by": "agapi", "agapi_ms": int((time.perf_counter() - t0) * 1000), "at": time.time()})
                return got
            mine = await base(ctx, name, args)          # AgAPI had nothing: Sasha answers, and it's logged
            compare(name, mine, theirs, int((time.perf_counter() - t0) * 1000))
            return mine
        mine = await base(ctx, name, args)              # shadow (and venues in reads/1): Sasha's answer is the one used

        async def later():
            try:
                theirs = await asyncio.wait_for(task, TIMEOUT_S)
            except Exception:
                theirs = {"ok": False, "error": {"code": "timeout"}}
            compare(name, mine, theirs, int((time.perf_counter() - t0) * 1000))
        t = asyncio.ensure_future(later())
        SHADOW_TASKS.add(t)
        t.add_done_callback(SHADOW_TASKS.discard)
        return mine
    return run


__all__ = ["mode", "runner", "GUEST_TOKEN", "SHADOW_LOG", "SHADOW_TASKS", "MODES", "compare"]
