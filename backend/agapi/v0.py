"""AgAPI v0 — THE CONTRACT. Every tool an agent (Sasha's, or any outside client later: REST, MCP) may call, in ONE place:
its agent, its input/output JSON schemas, its errors, and the guards that hold whatever the caller says.

    Magellan  finds        search_flights · search_stays · search_venues · propose_trip · swap_stay
    Sherlock  checks       check_offer · read_booking_route
    Austen    acts         choose_offer · save_travellers · hold_booking · book   (idempotency_key required; book needs a yes)
    Pacioli   records      get_status · get_trip · get_total

Rules of the contract (they live HERE, not in any prompt):
  · Scope: every call runs for ONE account — the caller's authenticated account (Ctx.account), never an id in the input.
  · Mode: "test" only in v0 (Duffel TEST, Stripe TEST, TEST hotels). A "live" Ctx is refused: mode_not_available.
  · Austen's calls carry an idempotency_key: the same key twice returns the first result, never a second action.
  · book needs approval.said = the person's OWN words in the current turn, an explicit yes. Sasha's agent fills it from the
    real user message — the model cannot supply it.
  · Prices and totals come only from these results; booked / paid / confirmed only from Pacioli (get_status).
  · Every error is {"ok": false, "error": {"code", "message"}} — honest, for the caller to explain.

docs/agapi/api-v0.md is GENERATED from TOOLS (scripts/agapi_doc.py).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

log = logging.getLogger("agapi.v0")
VERSION = "v0"


@dataclass
class Ctx:
    account: str                       # the authenticated account — the only scope
    mode: str = "test"                 # v0: "test" only
    user_said: Optional[str] = None    # the person's own words this turn (Sasha's agent fills it; REST: approval.said)
    session: Optional[str] = None
    calls: List[dict] = field(default_factory=list)   # what was called this turn (for the caller's guards and logs)


class ToolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


ERR = {"type": "object", "properties": {"ok": {"const": False}, "error": {"type": "object", "properties": {
    "code": {"type": "string"}, "message": {"type": "string"}}, "required": ["code", "message"]}}}
IDEM = {"type": "string", "minLength": 8, "maxLength": 128, "description": "Idempotency key: the same key returns the first result."}
DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
FLIGHT = {"type": "object", "properties": {
    "offer_id": {"type": "string"}, "airline": {"type": "string"}, "flights": {"type": "string"}, "from": {"type": "string"},
    "to": {"type": "string"}, "departs": {"type": "string"}, "arrives": {"type": "string"}, "stops": {"type": "integer"},
    "duration_minutes": {"type": "integer"}, "price_eur": {"type": "number"}, "test": {"const": True}}}
TOTAL = {"type": "object", "properties": {"total_eur": {"type": "number"}, "items": {"type": "integer"},
                                          "price_sources": {"type": "array", "items": {"type": "string"}}}}

_YES = re.compile(r"(?i)^\s*(?:(?:ok(?:ay)?|right|so|then|great|perfect|lovely|sasha)[,!. ]+)*(?:yes|yeah|yep|yup|sure|definitely|"
                  r"absolutely|go ahead|do it|please do|book it|book (?:the|my|our) (?:whole )?trip|confirm|let'?s do it|let'?s book)\b")
_NO = re.compile(r"(?i)\b(?:no|not|don'?t|do not|wait|hold on|later|cancel|stop|maybe)\b")


def explicit_yes(said: Optional[str]) -> bool:
    """An explicit yes in the person's own words — "Yes, book it", "Then book it.", "go ahead" — and no no/wait/not in it."""
    t = (said or "").strip()
    return bool(t) and bool(_YES.search(t)) and not _NO.search(t)


# ── shared reads ─────────────────────────────────────────────────────────────────────────────────────────────────────────

async def _plan(ctx: Ctx) -> dict:
    from booking_signer import plan_store as PS
    p = await PS.latest(ctx.account)
    if not p:
        raise ToolError("no_trip", "there is no trip on this account yet — propose_trip first")
    return p


def _party(p: dict) -> int:
    pl = p.get("plan") or {}
    try:
        return max(1, min(9, int(pl.get("party") or pl.get("travelers") or 2)))
    except (TypeError, ValueError):
        return 2


def _flight_out(r_or_card: dict, row: Optional[dict] = None) -> dict:
    c = r_or_card
    return {"offer_id": c.get("id") or (row or {}).get("provider_ref"), "airline": c.get("owner"), "flights": c.get("flights"),
            "from": c.get("from"), "to": c.get("to"), "departs": str(c.get("departs") or ""), "arrives": str(c.get("arrives") or ""),
            "stops": int(c.get("stops") or 0), "duration_minutes": int(c.get("minutes") or 0),
            "price_eur": round(float(c.get("amount") or (row or {}).get("price_amount") or 0), 2), "test": True,
            **({"state": row["state"]} if row else {})}


async def _total(ctx: Ctx, p: dict) -> dict:
    """The whole trip's total — the SAME figure booking would charge (basket_book.quote: stays at their provider's rate, the
    chosen flights re-checked). One source, so a total never changes between asking and booking."""
    from booking_signer import basket as BK, basket_book as BB
    q = await BB.quote(ctx.account, "Madrid")
    if "why" in q:
        raise ToolError("not_priced", q["why"])
    rows = BK.to_book(await BK.items(ctx.account, p["trip_id"], ("suggested", "chosen")))
    return {"total_eur": q["eur"], "items": len(rows), "flights_chosen": sum(1 for r in rows if r["kind"] == "flight"),
            "price_sources": sorted({r.get("price_source") or "unpriced" for r in rows})}


# Sasha 203 · where each place in a trip flies from: its airport (a plan can end in the Mekong Delta, which has none)
AIRPORT = {"hanoi": "HAN", "ha long bay": "HAN", "halong bay": "HAN", "sapa": "HAN", "ninh binh": "HAN", "cat ba": "HAN", "ha giang": "HAN",
           "ho chi minh city": "SGN", "saigon": "SGN", "mekong delta": "SGN", "mui ne": "SGN", "can tho": "VCA",
           "hoi an": "DAD", "da nang": "DAD", "hue": "HUI", "phu quoc": "PQC", "nha trang": "CXR", "da lat": "DLI",
           "con dao": "VCS", "phong nha": "VDH"}


def airport_of(place: str) -> str:
    """A trip's city → the airport to fly from/to (its IATA code), else the place as said."""
    p = (place or "").split(",")[0].strip()
    return AIRPORT.get(p.lower(), p)


def _best(cards: List[dict], earliest: str = "07:00") -> Optional[dict]:
    """Magellan's pick: direct if there is one, a sensible departure (earliest–21:00), then the best price."""
    def hh(c):
        return str(c.get("departs") or "")[11:16] or "12:00"
    sensible = [c for c in cards if earliest <= hh(c) <= "21:00"]
    direct = [c for c in sensible if not c.get("stops")]
    pool = direct or sensible or cards
    return min(pool, key=lambda c: float(c.get("amount") or 9e9)) if pool else None


async def _suggest_flights(ctx: Ctx, trip_id: str, cards: List[dict], origin: str, dest: str, day: str, party: int,
                           leg: str = "out") -> List[str]:
    from booking_signer import basket as BK
    sk = f"{leg}:{origin}→{dest} {day}"   # the leg first: choosing a flight replaces only that leg's
    return await BK.suggest(ctx.account, trip_id, "flight", [{
        "provider": "duffel", "provider_ref": c["id"], "slice_key": sk, "day": day, "party": party, "expires_at": c.get("expires_at"),
        "price_amount": float(c["amount"]), "price_currency": c["currency"], "price_source": "quoted",
        "snapshot": {**c, "name": c.get("owner")}} for c in cards], slice_key=sk)


# ── Magellan ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def search_flights(ctx: Ctx, a: dict) -> dict:
    from booking_signer import travel as T
    party = int(a.get("passengers") or 2)
    leg = a.get("leg") or "out"
    r = await T.search(airport_of(a["origin"]), airport_of(a["destination"]), a["date"], adults=party, limit=12)
    if "why" in r:
        raise ToolError("no_flights", r["why"])
    cards = [c for c in r["cards"] if c.get("currency") == "EUR"] or r["cards"]
    pref = (a.get("preferences") or "").lower()
    if "direct" in pref or "nonstop" in pref:
        cards = [c for c in cards if not c.get("stops")] or cards
    if "morning" in pref:
        cards = [c for c in cards if str(c.get("departs"))[11:13] < "12"] or cards
    elif "evening" in pref:
        cards = [c for c in cards if str(c.get("departs"))[11:13] >= "17"] or cards
    cards = cards[:6]
    from booking_signer import plan_store as PS
    p = await PS.latest(ctx.account)
    if p:   # the flights shown are the trip's suggestions (the basket), so choose_offer can take any of them
        await _suggest_flights(ctx, p["trip_id"], cards, a["origin"], a["destination"], a["date"], party, leg)
    return {"leg": leg, "flights": [_flight_out(c) for c in cards], "note": "Duffel TEST fares — nothing is held until book"}


async def search_stays(ctx: Ctx, a: dict) -> dict:
    from app.services.hotels_db import VIETNAM_HOTELS
    city = next((k for k in VIETNAM_HOTELS if k.lower() == (a.get("city") or "").strip().lower()), None)
    if not city:
        raise ToolError("city_not_covered", f"v0 has stays for Vietnam's cities only ({', '.join(list(VIETNAM_HOTELS)[:8])}, …)")
    pref = (a.get("preference") or "").lower()
    hs = VIETNAM_HOTELS[city]
    if pref:
        hs = sorted(hs, key=lambda h: -sum(w in f"{h['name']} {h.get('blurb', '')}".lower() for w in re.findall(r"[a-z]{4,}", pref)))
    return {"city": city, "stays": [{"name": h["name"], "stars": h.get("stars"), "about": h.get("blurb"),
                                     "estimate_eur_per_night": round(float(h.get("price_from") or 0) * 0.92)} for h in hs[:5]],
            "note": "estimates from Sasha's hotel list; a booking is a TEST booking (no hotel contacted)"}


async def search_venues(ctx: Ctx, a: dict) -> dict:
    from booking_signer import venue_read as V, ladder_routes as LR
    try:
        r = await V.find_venues(LR.HTTP, what=a["what"], where=a["where"], country=a.get("country"), now=datetime.now(timezone.utc))
    except V.FindRefused as e:
        raise ToolError(e.rule, str(e))
    out = []
    for c in (r.get("candidates") or r.get("venues") or [])[:6]:
        out.append({"name": c.get("name"), "address": c.get("address"), "type": c.get("type"), "rating": c.get("rating"),
                    "reviews": c.get("reviews") or c.get("rating_count"), "place_id": c.get("place_id"), "website": c.get("website")})
    return {"venues": out, "note": "Google listings; nothing contacted"}


async def propose_trip(ctx: Ctx, a: dict) -> dict:
    """The itinerary with somewhere to stay each night AND a flight that fits, chosen — and the total. Nothing booked."""
    from app.services.itinerary_agent import build_itinerary
    from booking_signer import basket as BK, basket_book as BB, plan_store as PS, travel as T
    try:
        start = date.fromisoformat(a["start_date"])
    except (KeyError, ValueError):
        raise ToolError("start_date_invalid", "start_date is YYYY-MM-DD")
    nights, party = int(a.get("nights") or 7), int(a.get("party") or 2)
    if not 1 <= nights <= 30 or not 1 <= party <= 9:
        raise ToolError("size_invalid", "nights 1–30, party 1–9")
    msg = (f"Plan a {nights + 1}-day trip to {a['destination']} from {start.day} {start.strftime('%B %Y')} for {party} people."
           + (f" Interests: {a['interests']}." if a.get("interests") else ""))
    itin = await build_itinerary(msg, [])
    if not itin or not itin.get("days"):
        raise ToolError("plan_failed", "the itinerary couldn't be built just now — try again")
    itin["party"] = party
    trip_id = await PS.save(ctx.account, itin, msg, datetime.now(timezone.utc))
    if not trip_id:
        raise ToolError("plan_not_saved", "the itinerary couldn't be saved on the account")
    days = itin["days"]
    first_city = (next((d.get("city") for d in days if d.get("city")), a["destination"]) or "").split(",")[0]
    last_city = (next((d.get("city") for d in reversed(days) if d.get("city")), first_city) or "").split(",")[0]
    origin = a.get("origin") or "Madrid"
    await BK.unchoose_flights(ctx.account, trip_id)
    flights, why = {}, []
    import asyncio as _aio
    legs = [("out", origin, airport_of(first_city), (start - timedelta(days=1)).isoformat()),
            ("back", airport_of(last_city), origin, (start + timedelta(days=nights)).isoformat())]   # home on the last day, after midday
    found = await _aio.gather(*[T.search(o, d, day, adults=party, limit=12) for _, o, d, day in legs])
    for (leg, o, d, day), r in zip(legs, found):   # out AND back: a flight that fits on each leg, chosen
        if "why" in r:
            why.append(f"{leg}: {r['why']}")
            continue
        cards = [c for c in r["cards"] if c.get("currency") == "EUR"] or r["cards"]
        ids = await _suggest_flights(ctx, trip_id, cards, o, d, day, party, leg)
        best = _best(cards, "12:00" if leg == "back" else "07:00")
        await BK.choose(ctx.account, ids[cards.index(best)])
        flights[leg] = _flight_out(best)
    q = await BB.quote(ctx.account, origin)
    hotel = lambda d: (d.get("hotel") or {}).get("name") if isinstance(d.get("hotel"), dict) else d.get("hotel")
    return {"trip_id": trip_id, "title": itin.get("title"),
            "days": [{"day": d.get("day"), "city": d.get("city"), "stay": hotel(d), "title": d.get("title")} for d in days],
            "flight_out": flights.get("out"), "flight_back": flights.get("back"), **({"flight_note": "; ".join(why)} if why else {}),
            "total_eur": q.get("eur") if "eur" in q else None, **({"total_note": q.get("why")} if "why" in q else {}),
            "prices": "stays at the TEST hotel rate, the flight at its Duffel TEST fare — nothing is booked"}


async def swap_stay(ctx: Ctx, a: dict) -> dict:
    from app.services.itinerary_agent import build_itinerary
    from booking_signer import plan_store as PS
    p = await _plan(ctx)
    plan = p.get("plan") or {}
    city = a["city"]
    if not any((d.get("city") or "").lower().startswith(city.lower()) for d in plan.get("days") or []):
        raise ToolError("city_not_in_trip", f"{city} isn't in this trip")
    new = await build_itinerary(f"change the hotel in {city} to {a['stay_name']}", [], current_itinerary=plan,
                                hotel_swap={"name": a["stay_name"], "city": city})
    if not new or not new.get("days"):
        raise ToolError("swap_failed", "the stay couldn't be changed just now")
    new["party"] = plan.get("party")
    await PS.save(ctx.account, {**new, "title": plan.get("title") or new.get("title")}, f"change the hotel in {city}", datetime.now(timezone.utc))
    p = await _plan(ctx)
    return {"city": city, "stay": a["stay_name"], **(await _total(ctx, p))}


# ── Sherlock ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def check_offer(ctx: Ctx, a: dict) -> dict:
    from booking_signer import travel as T
    st, j = await T.HTTP("GET", f"/air/offers/{a['offer_id']}")
    if st != 200:
        return {"available": False, "reason": T._err(j, st)}
    o = j["data"]
    return {"available": True, "price_eur": float(o["total_amount"]), "currency": o["total_currency"], "expires_at": o.get("expires_at")}


async def read_booking_route(ctx: Ctx, a: dict) -> dict:
    from booking_signer import venue_read as V, ladder_routes as LR, ladder as L
    try:
        read = await V.read_venue(LR.HTTP, name=a["name"], city=a["city"], country=a.get("country"), website=a.get("website"),
                                  now=datetime.now(timezone.utc), place_id=a.get("place_id"))
    except V.ReadRefused as e:
        raise ToolError(e.rule, str(e))
    read = read.to_json() if hasattr(read, "to_json") else dict(read)
    chosen = L.choose(read, account=ctx.account)
    lad = LR._ladder_for(read, chosen["rungs"], a.get("at"), a.get("party"))
    return {"venue": (read.get("listing") or {}).get("name") or a["name"], "routes": [r.get("rung") or r.get("kind") for r in chosen["rungs"]],
            "how": (lad or {}).get("line") or chosen.get("say")}


# ── Austen ───────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def choose_offer(ctx: Ctx, a: dict) -> dict:
    from booking_signer import basket as BK
    p = await _plan(ctx)
    row = await BK.by_ref(ctx.account, p["trip_id"], a["offer_id"])
    if not row:
        raise ToolError("offer_not_in_trip", "that flight isn't one shown for this trip — search_flights first")
    leg = (row.get("slice_key") or "out:").split(":", 1)[0]
    for other in await BK.items(ctx.account, p["trip_id"], ("chosen",)):   # one flight per LEG (searches of the leg may differ)
        if other["kind"] == "flight" and other["id"] != row["id"] and (other.get("slice_key") or "").split(":", 1)[0] == leg:
            async def fn(conn, oid=other["id"]):
                import uuid as _u
                await conn.execute("update trip_basket_items set state = 'suggested', updated_at = now() where id = $1", _u.UUID(oid))
            await BK._go(fn)
    try:
        row = await BK.choose(ctx.account, row["id"])
    except BK.BasketError as e:
        raise ToolError("not_choosable", str(e))
    return {"chosen": _flight_out(row.get("snapshot") or {}, row), **(await _total(ctx, p))}


async def save_travellers(ctx: Ctx, a: dict) -> dict:
    from booking_signer import passengers as PX
    people, bad = [], []
    for t in a.get("travellers") or []:
        try:
            born = date.fromisoformat(t["date_of_birth"])
        except (KeyError, ValueError):
            bad.append(f"{t.get('given_name', '?')} {t.get('family_name', '')}: date_of_birth YYYY-MM-DD"); continue
        title = (t.get("title") or "").lower().strip(".")
        if title not in ("mr", "ms", "mrs", "miss", "dr"):
            bad.append(f"{t.get('given_name')}: title mr/ms/mrs/miss/dr"); continue
        gender = {"mr": "m", "ms": "f", "mrs": "f", "miss": "f"}.get(title) or {"male": "m", "female": "f"}.get((t.get("gender") or "").lower())
        if not gender:
            bad.append(f"{t.get('given_name')}: gender"); continue
        if not (t.get("given_name") and t.get("family_name")):
            bad.append("a full name (given and family)"); continue
        people.append({"given_name": t["given_name"].strip().title(), "family_name": t["family_name"].strip().title(),
                       "born_on": born, "title": title, "gender": gender})
    n = await PX.save(ctx.account, people) if people else 0
    return {"saved": n, "travellers_on_file": len(await PX.saved(ctx.account)), "invalid": bad}


async def hold_booking(ctx: Ctx, a: dict) -> dict:
    """The read-back: every item re-checked (Sherlock) and priced; no money moves. book() binds the yes to its sha256."""
    from booking_signer import basket_book as BB, passengers as PX
    p = await _plan(ctx)
    have, need = len(await PX.saved(ctx.account)), _party(p)
    if have < need:
        raise ToolError("travellers_missing", f"the airline needs each traveller's full name, title and date of birth — {have} of {need} on file")
    q = await BB.quote(ctx.account, a.get("origin") or "Madrid")
    if "why" in q:
        raise ToolError("not_bookable", q["why"])
    return {"read_back": [l for l in q["lines"] if not l.startswith("Note:")], "notes": [l for l in q["lines"] if l.startswith("Note:")],
            "read_back_sha256": q["sha256"], "total_eur": q["eur"], "status": "not booked — waiting for the yes"}


async def book(ctx: Ctx, a: dict) -> dict:
    """The yes → ONE Stripe TEST payment for exactly the read-back; the link goes to the phone. Booked only after payment
    (Pacioli: get_status)."""
    from booking_signer import basket_book as BB
    said = ((a.get("approval") or {}).get("said")) or ""
    if not explicit_yes(said):
        raise ToolError("no_explicit_yes", "booking needs the person's explicit yes in this turn — ask them, then call book")
    got = await BB.pay(ctx.account, a.get("read_back_sha256") or "")
    if "why" in got:
        raise ToolError("read_back_changed" if "different words" in got["why"] else "not_bookable", got["why"])
    sent = str(got.get("phone") or "").startswith("sent")
    return {"status": "awaiting_payment", "payment": "sent_to_phone" if sent else "link", **({} if sent else {"payment_url": got["url"]}),
            "session_id": got["session_id"], "total_eur": got["eur"], "booked": False}


# ── Pacioli ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def get_status(ctx: Ctx, a: dict) -> dict:
    from booking_signer import basket as BK, paid_watch as PW
    p = await _plan(ctx)
    await PW.sweep(ctx.account)   # a payment waiting is settled first (Pacioli writes the outcome)
    rows = await BK.items(ctx.account, p["trip_id"], ("pending_payment", "booked", "failed", "cancelled"))
    return {"booked": [r["status_line"] for r in rows if r["state"] == "booked"],
            "failed": [r["status_line"] for r in rows if r["state"] == "failed"],
            "cancelled": [r["status_line"] for r in rows if r["state"] == "cancelled"],
            "awaiting_payment": sum(1 for r in rows if r["state"] == "pending_payment"),
            "anything_booked": any(r["state"] == "booked" for r in rows)}


async def get_trip(ctx: Ctx, a: dict) -> dict:
    from booking_signer import basket as BK
    p = await _plan(ctx)
    rows = await BK.items(ctx.account, p["trip_id"])
    hotel = lambda d: (d.get("hotel") or {}).get("name") if isinstance(d.get("hotel"), dict) else d.get("hotel")
    return {"trip_id": p["trip_id"], "title": p.get("title"), "start": str(p.get("start") or ""), "end": str(p.get("end") or ""),
            "party": _party(p), "days": [{"day": d.get("day"), "city": d.get("city"), "stay": hotel(d)} for d in (p.get("plan") or {}).get("days") or []],
            "flights": [_flight_out(r.get("snapshot") or {}, r) for r in rows if r["kind"] == "flight" and r["state"] != "suggested"],
            "stays": [{"name": (r.get("snapshot") or {}).get("name"), "from": r.get("day"), "nights": (r.get("snapshot") or {}).get("nights"),
                       "state": r["state"], "price_eur": r.get("price_amount"), "price_source": r.get("price_source")} for r in rows if r["kind"] == "stay"]}


async def get_total(ctx: Ctx, a: dict) -> dict:
    return await _total(ctx, await _plan(ctx))


# ── the contract ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def _t(name: str, agent: str, fn: Callable[[Ctx, dict], Awaitable[dict]], description: str, props: dict, required: List[str],
       output: dict, errors: List[str], austen: bool = False) -> dict:
    inp = {"type": "object", "properties": {**props, **({"idempotency_key": IDEM} if austen else {})},
           "required": required + (["idempotency_key"] if austen else []), "additionalProperties": False}
    return {"name": name, "agent": agent, "fn": fn, "description": description, "input_schema": inp, "output_schema": output,
            "errors": errors, "idempotent": austen}


TOOLS: List[dict] = [
    _t("search_flights", "Magellan", search_flights, "Flights between two places on a day, cheapest first (TEST fares). Shown "
       "flights become the trip's suggestions for that leg.", {"origin": {"type": "string"}, "destination": {"type": "string"}, "date": DATE,
                                                  "leg": {"enum": ["out", "back"], "description": "out (there) or back (home); default out"},
                                                  "passengers": {"type": "integer", "minimum": 1, "maximum": 9},
                                                  "preferences": {"type": "string", "description": "e.g. direct, morning"}},
       ["origin", "destination", "date"], {"type": "object", "properties": {"flights": {"type": "array", "items": FLIGHT}}}, ["no_flights"]),
    _t("search_stays", "Magellan", search_stays, "Places to stay in a city, best match first (estimates; TEST bookings).",
       {"city": {"type": "string"}, "preference": {"type": "string", "description": "e.g. on the beach, boutique"}}, ["city"],
       {"type": "object", "properties": {"stays": {"type": "array"}}}, ["city_not_covered"]),
    _t("search_venues", "Magellan", search_venues, "Restaurants, spas or other places in a city (Google listings; nothing contacted).",
       {"what": {"type": "string"}, "where": {"type": "string"}, "country": {"type": "string", "pattern": "^[A-Z]{2}$"}}, ["what", "where"],
       {"type": "object", "properties": {"venues": {"type": "array"}}}, ["what_invalid", "where_invalid", "places_not_configured"]),
    _t("propose_trip", "Magellan", propose_trip, "THE PROPOSAL: a day-by-day itinerary with somewhere to stay each night, a flight "
       "that fits on each leg (there and back) already chosen, and the whole trip's total. Replaces the account's current proposal. Nothing is booked.",
       {"destination": {"type": "string"}, "start_date": DATE, "nights": {"type": "integer", "minimum": 1, "maximum": 30},
        "party": {"type": "integer", "minimum": 1, "maximum": 9}, "interests": {"type": "string"},
        "origin": {"type": "string", "description": "where they fly from"}},
       ["destination", "start_date", "nights", "party", "origin"],
       {"type": "object", "properties": {"trip_id": {"type": "string"}, "days": {"type": "array"}, "flight_out": FLIGHT, "flight_back": FLIGHT,
                                         "total_eur": {"type": "number"}}},
       ["start_date_invalid", "size_invalid", "plan_failed", "plan_not_saved"]),
    _t("swap_stay", "Magellan", swap_stay, "Change where they stay in one city of the trip (take a name from search_stays). Returns the new total.",
       {"city": {"type": "string"}, "stay_name": {"type": "string"}}, ["city", "stay_name"], TOTAL, ["no_trip", "city_not_in_trip", "swap_failed", "not_priced"]),
    _t("check_offer", "Sherlock", check_offer, "Is this flight offer still available, and at what price?", {"offer_id": {"type": "string"}},
       ["offer_id"], {"type": "object", "properties": {"available": {"type": "boolean"}, "price_eur": {"type": "number"}}}, []),
    _t("read_booking_route", "Sherlock", read_booking_route, "How a venue takes bookings (its own page, email, phone…) and how Sasha would book it.",
       {"name": {"type": "string"}, "city": {"type": "string"}, "country": {"type": "string"}, "place_id": {"type": "string"},
        "website": {"type": "string"}, "at": {"type": "string", "description": "ISO local date-time wanted"}, "party": {"type": "integer"}},
       ["name", "city"], {"type": "object", "properties": {"routes": {"type": "array"}, "how": {"type": "string"}}}, ["name_invalid", "city_invalid"]),
    _t("choose_offer", "Austen", choose_offer, "Put a flight from search_flights into the trip, replacing the flight on that leg. Returns the new total.",
       {"offer_id": {"type": "string"}}, ["offer_id"], {"type": "object", "properties": {"chosen": FLIGHT, **TOTAL["properties"]}},
       ["no_trip", "offer_not_in_trip", "not_choosable"], austen=True),
    _t("save_travellers", "Austen", save_travellers, "Save the travellers the airline needs (asked once, kept on the account).",
       {"travellers": {"type": "array", "items": {"type": "object", "properties": {
           "given_name": {"type": "string"}, "family_name": {"type": "string"}, "date_of_birth": DATE,
           "title": {"enum": ["mr", "ms", "mrs", "miss", "dr"]}, "gender": {"enum": ["male", "female"]}},
           "required": ["given_name", "family_name", "date_of_birth", "title"]}}}, ["travellers"],
       {"type": "object", "properties": {"saved": {"type": "integer"}, "travellers_on_file": {"type": "integer"}, "invalid": {"type": "array"}}},
       [], austen=True),
    _t("hold_booking", "Austen", hold_booking, "The read-back before booking: every item re-checked and priced, the total, and the "
       "sha256 the yes binds to. No money moves; nothing is booked.", {"origin": {"type": "string"}}, [],
       {"type": "object", "properties": {"read_back": {"type": "array"}, "read_back_sha256": {"type": "string"}, "total_eur": {"type": "number"}}},
       ["no_trip", "travellers_missing", "not_bookable"], austen=True),
    _t("book", "Austen", book, "After the person's explicit yes in THIS turn: one payment (Stripe TEST) for exactly the read-back, sent "
       "to their phone. Nothing is booked until it is paid — get_status says when.",
       {"read_back_sha256": {"type": "string"}, "approval": {"type": "object", "properties": {"said": {"type": "string"}},
                                                               "description": "the person's own words (filled by the caller from the real message)"}},
       ["read_back_sha256"], {"type": "object", "properties": {"status": {"const": "awaiting_payment"}, "booked": {"const": False}}},
       ["no_explicit_yes", "read_back_changed", "not_bookable"], austen=True),
    _t("get_status", "Pacioli", get_status, "What is booked, failed, cancelled or awaiting payment — the ONLY source for booked/paid/confirmed.",
       {}, [], {"type": "object", "properties": {"booked": {"type": "array"}, "anything_booked": {"type": "boolean"}}}, ["no_trip"]),
    _t("get_trip", "Pacioli", get_trip, "The trip as it stands: days and stays, the chosen flights, each item's state.", {}, [],
       {"type": "object"}, ["no_trip"]),
    _t("get_total", "Pacioli", get_total, "The whole trip's total from the basket (what booking would charge).", {}, [], TOTAL, ["no_trip"]),
]
BY_NAME = {t["name"]: t for t in TOOLS}
_IDEM: Dict[str, dict] = {}


async def call(ctx: Ctx, name: str, args: dict) -> dict:
    """The one entry: {"ok": true, "result": …} or {"ok": false, "error": {"code", "message"}}. Never raises."""
    t = BY_NAME.get(name)
    if not t:
        return {"ok": False, "error": {"code": "unknown_tool", "message": f"no tool {name} in AgAPI {VERSION}"}}
    if ctx.mode != "test":
        return {"ok": False, "error": {"code": "mode_not_available", "message": "AgAPI v0 runs in TEST mode only"}}
    args = dict(args or {})
    miss = [k for k in t["input_schema"]["required"] if args.get(k) in (None, "")]
    if miss:
        return {"ok": False, "error": {"code": "missing_input", "message": f"missing: {', '.join(miss)}"}}
    key = None
    if t["idempotent"]:
        key = f"{ctx.account}:{name}:{args['idempotency_key']}"
        if key in _IDEM:
            return {**_IDEM[key], "replayed": True}
    try:
        res = {"ok": True, "result": await t["fn"](ctx, args)}
    except ToolError as e:
        res = {"ok": False, "error": {"code": e.code, "message": e.message}}
    except Exception as e:
        log.error("[agapi] %s failed: %s: %s", name, type(e).__name__, e)
        res = {"ok": False, "error": {"code": "internal", "message": f"{name} failed ({type(e).__name__}) — nothing was changed by this call"}}
    ctx.calls.append({"tool": name, "ok": res["ok"], "agent": t["agent"]})
    if key and res["ok"]:
        _IDEM[key] = res
        try:
            from booking_signer import basket as BK
            await BK.event("agapi", hashlib.sha256(key.encode()).hexdigest()[:40], name, {"args": {k: v for k, v in args.items() if k != "approval"}},
                           verified=True)
        except Exception as e:
            log.info("[agapi] idempotency not recorded: %s", type(e).__name__)
    return res


def schema_for_model(t: dict) -> dict:
    """The tool as the model sees it: no idempotency_key and no approval (the caller fills both, never the model)."""
    s = json.loads(json.dumps(t["input_schema"]))
    for k in ("idempotency_key", "approval"):
        s["properties"].pop(k, None)
        if k in s.get("required", []):
            s["required"].remove(k)
    return {"name": t["name"], "description": f"[{t['agent']}] {t['description']}", "input_schema": s}


__all__ = ["VERSION", "Ctx", "ToolError", "TOOLS", "BY_NAME", "call", "explicit_yes", "schema_for_model"]
