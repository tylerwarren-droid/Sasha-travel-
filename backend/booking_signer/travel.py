"""Sasha 132 · FLIGHTS IN DUFFEL TEST MODE — cards → "Book it" → one-touch test payment → a TEST order → the itinerary.

Every step says TEST. The Duffel token must be a TEST token (duffel_test_…): a live token is refused here, always — a
test order issues no ticket and charges nothing. The fare is paid in one touch on Stripe's TEST page (Apple Pay or the
phone's saved card; nothing is charged); only when Stripe records it paid is the Duffel test order made, with Duffel's
test "balance" payment. Duffel needs a passenger's birth date, title and gender to make an order: in test mode Sasha
uses PLACEHOLDERS, and the read-back says so.

Hotels are NOT here: Duffel Stays isn't enabled on this account (403, 3 Oct) and RateHawk has no credentials — hotels are
found as cards and requested from the hotel itself (guest_whatsapp), said as such.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger("booking_signer.travel")
DUFFEL = "https://api.duffel.com"
PLACEHOLDERS = {"born_on": "1980-01-01", "title": "mr", "gender": "m"}
LABEL = "TEST booking — Duffel test mode: no real ticket, nothing charged"


def token() -> Optional[str]:
    t = os.getenv("DUFFEL_ACCESS_TOKEN", "").strip()
    return t if t.startswith("duffel_test_") else None   # ⛔ a live token is never used here


async def _duffel(method: str, path: str, body: Optional[dict] = None, params: Optional[dict] = None):
    import httpx
    h = {"Authorization": f"Bearer {token() or ''}", "Duffel-Version": "v2", "Accept": "application/json", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as c:
        r = await c.request(method, f"{DUFFEL}{path}", headers=h, json=body, params=params)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"errors": [{"message": r.text[:200]}]}


HTTP = _duffel   # tests replace it


def _err(j: Any, s: int) -> str:
    return ((j or {}).get("errors") or [{}])[0].get("message") or f"HTTP {s}"


class DuffelDown(Exception):
    """Sasha 215 · CR 56 #3/#4 — Duffel didn't answer (a 5xx, a 429, a timeout, the network): an OUTAGE, never "no such city",
    "no flights" or "that flight is gone"."""


def down_status(s: int) -> bool:
    return s >= 500 or s in (0, 408, 429)


async def call_duffel(method: str, path: str, body: Optional[dict] = None, params: Optional[dict] = None):
    """HTTP, with an outage RAISED as DuffelDown (retried once first)."""
    for k in range(2):
        try:
            s, j = await HTTP(method, path, body, params) if params is not None else await HTTP(method, path, body)
        except Exception as e:   # timeout, connection refused, DNS
            if k:
                raise DuffelDown(type(e).__name__) from e
            continue
        if down_status(s):
            if k:
                raise DuffelDown(f"HTTP {s}")
            continue
        return s, j
    raise DuffelDown("no answer")


async def place(q: str, strict: bool = False) -> Optional[dict]:
    """'Madrid' → {code: MAD, name, tz} — Duffel's own place suggestions (a city first, else an airport); an IATA code as is.
    `strict`: Duffel not answering raises DuffelDown (never read as "no such place")."""
    q = (q or "").strip()
    if re.fullmatch(r"[A-Za-z]{3}", q):
        q = q.upper()
    if strict:
        s, j = await call_duffel("GET", "/places/suggestions", None, {"query": q})
    else:
        s, j = await HTTP("GET", "/places/suggestions", params={"query": q})
    if s != 200:
        return None
    rows = j.get("data") or []
    best = next((p for p in rows if p.get("type") == "city"), None) or next((p for p in rows if p.get("type") == "airport"), None)
    if not best:
        return None
    tz = best.get("time_zone") or next((a.get("time_zone") for a in best.get("airports") or [] if a.get("time_zone")), None)
    return {"code": best.get("iata_city_code") or best.get("iata_code"), "name": best.get("city_name") or best.get("name"), "tz": tz}


def _minutes(iso_dur: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", iso_dur or "")
    return (int(m[1] or 0) * 1440 + int(m[2] or 0) * 60 + int(m[3] or 0)) if m else 0


def card_of(o: dict) -> dict:
    sl = o["slices"][0]
    segs = sl["segments"]
    first, last = segs[0], segs[-1]
    return {"id": o["id"], "owner": o["owner"]["name"], "flights": " + ".join(f"{s['marketing_carrier']['iata_code']} {s['marketing_carrier_flight_number']}" for s in segs),
            "from": first["origin"]["iata_code"], "to": last["destination"]["iata_code"], "from_city": first["origin"].get("city_name") or first["origin"]["name"],
            "to_city": last["destination"].get("city_name") or last["destination"]["name"], "departs": first["departing_at"], "arrives": last["arriving_at"],
            "from_tz": first["origin"].get("time_zone"), "stops": len(segs) - 1, "minutes": _minutes(sl.get("duration") or ""),
            "amount": o["total_amount"], "currency": o["total_currency"], "expires_at": o.get("expires_at"),
            "passengers": [p["id"] for p in o.get("passengers") or []]}


def card_line(c: dict) -> str:
    dep = datetime.fromisoformat(c["departs"])
    arr = datetime.fromisoformat(c["arrives"])
    plus = (arr.date() - dep.date()).days
    stops = "direct" if not c["stops"] else f"{c['stops']} stop{'s' if c['stops'] > 1 else ''}"
    return (f"{c['owner']} {c['flights']} · {dep.strftime('%a %d %b %H:%M')} {c['from']} → {arr.strftime('%H:%M')}{f'+{plus}' if plus else ''} {c['to']} · "
            f"{stops} · {c['minutes'] // 60}h {c['minutes'] % 60:02d}m · {c['currency']} {c['amount']} (TEST)")


async def search(origin: str, dest: str, day: str, adults: int = 1, limit: int = 3) -> Dict[str, Any]:
    """{cards: [...3 cheapest...]} or {why}. TEST mode only."""
    if not token():
        return {"why": "flights need a Duffel TEST token (duffel_test_…), and none is set"}
    try:   # Sasha 215 · an outage is said as one: {"why", "outage": True}
        a, b = await place(origin, strict=True), await place(dest, strict=True)
        if not a or not b:
            return {"why": f"I couldn't find {'where you fly from' if not a else 'where you fly to'} as a city or airport"}
        s, j = await call_duffel("POST", "/air/offer_requests?return_offers=true&supplier_timeout=20000",
                                 {"data": {"slices": [{"origin": a["code"], "destination": b["code"], "departure_date": day}],
                                           "passengers": [{"type": "adult"} for _ in range(max(1, adults))], "cabin_class": "economy"}})
    except DuffelDown as e:
        log.warning("[travel] Duffel down on search: %s", e)
        return {"why": "the airline's system isn't answering right now", "outage": True}
    if s not in (200, 201):
        return {"why": f"Duffel (test) refused the search: {_err(j, s)}"}
    if (j.get("data") or {}).get("live_mode"):
        return {"why": "Duffel answered in LIVE mode — refused"}
    offers = sorted((j.get("data") or {}).get("offers") or [], key=lambda o: float(o["total_amount"]))
    if not offers:
        return {"why": f"no flights found from {a['name']} to {b['name']} on {day}"}
    return {"cards": [card_of(o) for o in offers[:limit]], "from": a, "to": b}


def read_back(c: dict, name: str, email: str) -> List[str]:
    # Sasha 183 · only what's true: no saved traveller details or passport are used (Duffel's TEST mode takes placeholders),
    # payment is Apple Pay on the phone (Stripe TEST), and no confirmation email is sent for a test flight
    return [f"I'll book {card_line(c)} for {name}.",
            "Traveller details: no saved details or passport are used — Duffel's test mode needs a birth date, title and gender, "
            "so I'll use test placeholders (1 Jan 1980, Mr, M).",
            "Payment: Apple Pay on your phone, on Stripe's TEST page — nothing is charged, and I never see your card.",
            f"⚠ {LABEL}.",
            "Once it's paid it goes straight into your itinerary on the platform, and I'll confirm it here."]


async def order(c: dict, name: str, email: str, phone: Optional[str], people: Optional[list] = None,
                documents: Optional[list] = None) -> Dict[str, Any]:
    """The Duffel TEST order — only after Stripe recorded the test payment. {booking_reference, order_id} or {why}."""
    if not token():
        return {"why": "no Duffel TEST token"}
    s, j = await HTTP("GET", f"/air/offers/{c['id']}")   # still there, still this price
    if s != 200:
        return {"why": f"the offer has gone ({_err(j, s)}) — search again"}
    o = j["data"]
    if o["total_amount"] != c["amount"] or o["total_currency"] != c["currency"]:
        return {"why": f"the price changed to {o['total_currency']} {o['total_amount']} — nothing booked; ask again"}
    from . import passengers as PX   # Sasha 198 R7 · the travellers asked once and saved; placeholders only without them (TEST)
    pax = PX.for_order(people or [], [p["id"] for p in o["passengers"]], email, phone)
    if pax is None:
        given, _, family = (name or "Guest Test").partition(" ")
        pax = [{"id": p["id"], "type": "adult", "given_name": given, "family_name": family or "Guest", "email": email or "guest@example.com",
                "phone_number": phone or "+34600000000", **PLACEHOLDERS} for p in o["passengers"]]
    if documents and "supported_passenger_identity_document_types" in o:   # Sasha 228 · only what THIS airline takes (easyJet takes none:
        ok_types = set(o.get("supported_passenger_identity_document_types") or [])   # sending one anyway would fail the order)
        documents = [d for d in documents if d.get("type") in ok_types]
    if documents and pax:   # Sasha 224 · CR 63 — the Keep's identity documents (opened just for this order) → the account holder's passenger
        pax[next((k for k, p in enumerate(people or []) if p.get("is_account_holder")), 0) % len(pax)]["identity_documents"] = documents
    s, j = await HTTP("POST", "/air/orders", {"data": {"type": "instant", "selected_offers": [c["id"]], "passengers": pax,
                                                       "payments": [{"type": "balance", "currency": o["total_currency"], "amount": o["total_amount"]}],
                                                       "metadata": {"sasha": "test_booking"}}})
    if s not in (200, 201):
        return {"why": f"Duffel (test) refused the order: {_err(j, s)}"}
    d = j["data"]
    if d.get("live_mode"):
        return {"why": "Duffel answered in LIVE mode — refused"}
    return {"booking_reference": d.get("booking_reference"), "order_id": d.get("id"), "documents_sent": len(documents or [])}


async def _record(account: str, c: dict, ref: str) -> Optional[str]:
    """The flight on the guest's own list — type flight, confirmed (the airline's test order), with its reference; the
    calendar mirror picks it up from there."""
    from . import ladder_routes as LR
    from .store import BOOKINGS_TRIP_TITLE
    if not hasattr(LR.LADDER_STORE, "_run"):
        return None
    dep = datetime.fromisoformat(c["departs"])
    tz = c.get("from_tz") or "Europe/Madrid"
    dt = dep.replace(tzinfo=ZoneInfo(tz)) if dep.tzinfo is None else dep
    name = f"Flight {c['flights']} {c['from_city']} → {c['to_city']} (TEST booking)"

    async def go(conn):
        async with conn.transaction():
            a = uuid.UUID(account)
            trip = await conn.fetchval("select id from trips where owner_id = $1 and title = $2 limit 1", a, BOOKINGS_TRIP_TITLE)
            if trip is None:
                trip = await conn.fetchval("insert into trips (owner_id, title) values ($1,$2) returning id", a, BOOKINGS_TRIP_TITLE)
            tid = await conn.fetchval("insert into trip_items (trip_id, type, status, provider_name, date_time, duration_minutes, local_timezone, "
                                      "location_name) values ($1,'flight','requested',$2,$3,$4,$5,$6) returning id",
                                      trip, name, dt, c["minutes"] or 120, tz, f"{c['from']} → {c['to']}")
            await conn.execute("update trip_items set status = 'confirmed', booking_reference = $2, updated_at = now() where id = $1", tid, ref)
            return str(tid)
    return await LR.LADDER_STORE._run(go)


RECORD = _record   # tests replace it

# ── Sasha 183 · an expired offer is priced again; one booking per search list ──────────────────────────────────────
OFFER_ROUTE: Dict[str, dict] = {}   # offer id → {from, to, day, adults, owner, list}  (this server's memory: offers live ~30 min)
USED_LISTS: set = set()             # the lists a booking was made from (Duffel refuses a second order from one search)
LIST_USED = "You've booked one from this list — want me to search again?"


def register_list(offers: list, origin: str, dest: str, day: str, adults: int) -> None:
    key = uuid.uuid4().hex[:12]
    for oid, owner in offers:
        if oid:
            OFFER_ROUTE[oid] = {"from": origin, "to": dest, "day": day, "adults": adults, "owner": owner, "list": key}
    if len(OFFER_ROUTE) > 3000:
        for k in list(OFFER_ROUTE)[:1000]:
            OFFER_ROUTE.pop(k, None)


def list_used(offer_id: str) -> bool:
    return (OFFER_ROUTE.get(offer_id) or {}).get("list") in USED_LISTS


def mark_used(offer_id: str) -> None:
    k = (OFFER_ROUTE.get(offer_id) or {}).get("list")
    if k:
        USED_LISTS.add(k)


async def refreshed(offer_id: str) -> Optional[str]:
    """An expired offer → the same airline, route and day, priced again now → its new offer id (or None)."""
    r = OFFER_ROUTE.get(offer_id)
    if not r:
        return None
    got = await search(r["from"], r["to"], r["day"], adults=r["adults"], limit=8)
    same = [c for c in got.get("cards") or [] if (c.get("owner") or "").lower() == (r.get("owner") or "").lower()] or (got.get("cards") or [])
    for c in same:
        st, _j = await HTTP("GET", f"/air/offers/{c['id']}")
        if st == 200:
            OFFER_ROUTE[c["id"]] = {**r, "list": uuid.uuid4().hex[:12]}
            return c["id"]
    return None

__all__ = ["search", "order", "read_back", "card_line", "card_of", "place", "token", "LABEL", "RECORD"]


# ── the web's "Book it (TEST)" — the same steps as WhatsApp, bound to the read-back's hash ─────────────────────────────

from fastapi import APIRouter, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

router = APIRouter(prefix="/travel", tags=["travel"])
_BOOKED: Dict[str, dict] = {}   # Stripe session → the order it made (once)


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


async def _card_and_lines(account: str, offer_id: str):
    import hashlib
    from . import guest_receipt as GR, guest_whatsapp as GW
    s, j = await HTTP("GET", f"/air/offers/{offer_id}")
    if s != 200:
        return None, None, None, None
    c = card_of(j["data"])
    _s, cj = await GW.api(account, "GET", "/api/booking/contact")
    contact = (cj or {}).get("contact") or {}
    email = await GR.address_of(account)
    lines = read_back(c, contact.get("name") or "you", email or "")
    return c, lines, hashlib.sha256("\n".join(lines).encode()).hexdigest(), {"name": contact.get("name") or "", "email": email or "",
                                                                            "phone": contact.get("mobile_e164")}


@router.post("/flight/prepare")
async def prepare(request: Request):
    from .account import account_for
    if not token():
        return _refuse(422, "travel_off", "flights need a Duffel TEST token, and none is set")
    body = await request.json()
    oid = str(body.get("offer_id") or "")
    if list_used(oid):   # Sasha 183 · never a dead end: Duffel refuses a 2nd order from one search
        return _refuse(409, "list_used", LIST_USED)
    c, lines, sha, _who = await _card_and_lines(account_for(request), oid)
    note = None
    if c is None:   # Sasha 183 · expired: the same airline, route and day, priced again — never a dead card
        new = await refreshed(oid)
        if new:
            c, lines, sha, _who = await _card_and_lines(account_for(request), new)
            oid, note = new, "That offer had expired — here it is priced again now."
    if c is None:
        return _refuse(404, "offer_gone", "that flight offer has gone and couldn't be priced again — ask me to search again")
    return {"ok": True, "offer_id": oid, "note": note, "card": c, "line": card_line(c), "read_back": {"lines": lines, "sha256": sha}}


@router.post("/flight/pay")
async def pay(request: Request):
    from . import test_deposit as TD, yes as YS
    from .account import account_for
    body = await request.json()
    if not YS.approval_ok(body.get("approval")):
        return _refuse(422, "approval_void", YS.APPROVAL_VOID)
    c, _lines, sha, _who = await _card_and_lines(account_for(request), str(body.get("offer_id") or ""))
    if c is None:
        return _refuse(404, "offer_gone", "that flight offer has gone — search again")
    if body.get("read_back_sha256") != sha:
        return _refuse(422, "approval_void", "the yes was to different words (the offer or its price changed) — prepare it again")
    got = await TD.checkout(c["amount"], c["currency"], f"{c['owner']} {c['flights']} {c['from']}→{c['to']}", sha[:16])
    if "why" in got:
        return _refuse(422, "test_payment_unavailable", got["why"])
    from . import paid_watch as PWT   # Sasha 183 · written down before paying — a restart never loses it
    await PWT.remember(account_for(request), "flight", got["id"], {"card": c, **(_who or {})},
                       f"Flight {c['flights']} {c['from']} → {c['to']}", c.get("departs"), c.get("from_tz") or "Europe/Madrid")
    from . import guest_whatsapp as GW   # Sasha 161 · desktop books, phone confirms
    phone = await GW.tap_to_pay(account_for(request), f"{c['amount']} {c['currency']}", f"{c['owner']} {c['from']}→{c['to']}", got["url"])
    return {"ok": True, "url": got["url"], "session_id": got["id"], "phone": phone}


@router.get("/flight/status")
async def flight_status(request: Request):
    from . import test_deposit as TD
    from .account import account_for
    account = account_for(request)
    sid, offer = request.query_params.get("session_id") or "", request.query_params.get("offer_id") or ""
    if sid in _BOOKED:
        return {"ok": True, "status": "booked", **_BOOKED[sid]}
    from . import paid_watch as PWT   # Sasha 183 · the one booking path after a payment
    r = await PWT.settle(sid)
    if r is not None:
        if r.get("status") == "booking":
            return {"ok": True, "status": "awaiting_payment"}
        return {"ok": True, "status": r["status"], "say": r.get("say"), "booking_reference": r.get("booking_reference")}
    paid = await TD.session_paid(sid)
    if not paid:
        return {"ok": True, "status": "awaiting_payment"}
    c, _l, _sha, who = await _card_and_lines(account, offer)
    if c is None:
        return {"ok": True, "status": "failed", "say": "paid (test), but the offer has gone — nothing booked"}
    o = await order(c, who["name"], who["email"], who["phone"])
    if "why" in o:
        TD.note(sid, False, f"Paid (TEST), but not booked: {o['why']}")
        return {"ok": True, "status": "failed", "say": f"paid (test), but not booked: {o['why']}"}
    await RECORD(account, c, o["booking_reference"] or "")
    mark_used(offer)
    _BOOKED[sid] = {"booking_reference": o["booking_reference"], "say": f"✅ Booked (TEST): {card_line(c)}. Reference {o['booking_reference']} — {LABEL}."}
    TD.note(sid, True, _BOOKED[sid]["say"])
    return {"ok": True, "status": "booked", **_BOOKED[sid]}
