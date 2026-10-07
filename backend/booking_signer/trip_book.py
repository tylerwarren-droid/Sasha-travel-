"""Sasha 169 (2) · BOOK THE WHOLE TRIP — the plan's hotels (TEST bookings: no hotel contacted) and its flights (Duffel TEST
mode), in ONE read-back, ONE yes, ONE Stripe TEST payment, ONE tap on the guest's phone (desktop books, phone confirms).

  prepare → the stays (consecutive days at the same hotel = one stay) and the flights out (the day before day 1, so day 1 is
  spent there) and back (the day after the last day), each priced: hotels at the TEST rate (hotel_test, a placeholder, said
  so), flights at Duffel's TEST fares → the read-back lines and their hash.
  pay     → the yes, bound to that hash → one Stripe TEST checkout for the total → the tap to pay on the phone.
  status  → once Stripe records the TEST payment: every hotel recorded (TEST- refs) and every Duffel TEST order placed, each
            on the account's list (and so on its day of the plan, by date). Done once per payment.
Nothing is reserved, nothing is charged; every line says TEST.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("booking_signer.trip_book")
router = APIRouter(prefix="/travel", tags=["travel"])
_QUOTES: Dict[str, dict] = {}    # account → its last bundle (the offers the yes was to)
_BOOKED: Dict[str, dict] = {}    # Stripe session → what it booked (once)
SEARCH = None                    # tests replace it (travel.search)


def stays(days: List[dict], start: date) -> List[dict]:
    """Consecutive days at the same hotel → one stay {hotel, city, checkin, nights}."""
    out: List[dict] = []
    for i, d in enumerate(days):
        h = d.get("hotel")
        name = (h.get("name") if isinstance(h, dict) else h) or f"a hotel in {d.get('city')}"
        on = str(d.get("date") or "")[:10] or (start + timedelta(days=i)).isoformat()
        if out and out[-1]["hotel"] == name and out[-1]["city"] == d.get("city"):
            out[-1]["nights"] += 1
        else:
            out.append({"hotel": name, "city": d.get("city") or "", "checkin": on, "nights": 1})
    return out


def _eur(x: Any) -> float:
    return round(float(x), 2)


async def bundle(account: str, origin: str) -> dict:
    """{stays, flights, lines, sha256, eur, party, title} — or {why}."""
    from . import hotel_test as HT, plan_store as PS, travel as T
    p = await PS.latest(account)
    if not p or not (p.get("plan") or {}).get("days"):
        return {"why": "there's no trip plan on your account to book yet — ask me to plan one"}
    m = PS.merge(p, [])
    days = m["days"]
    start = date.fromisoformat(str(days[0].get("date") or p.get("start") or "")[:10]) if (days[0].get("date") or p.get("start")) else None
    if start is None:
        return {"why": "the plan has no dates yet — tell me when it starts (e.g. “from 12 November”)"}
    pl = p.get("plan") or {}
    try:
        party = max(1, min(9, int(pl.get("party") or pl.get("travelers") or 2)))
    except (TypeError, ValueError):
        party = 2
    from .wa_brain import _country_of
    tz = HT.tz_of(_country_of(p.get("title") or "", []))
    ss = stays(days, start)
    last = date.fromisoformat(str(days[-1].get("date"))[:10])
    first_city, last_city = days[0].get("city") or "", days[-1].get("city") or ""
    search = SEARCH or T.search
    # Sasha 182 · 8, not 3: the cheapest test fares are often ones Duffel's test system won't book (China Eastern: 422), and
    # with three of them the bundle refused "no test fare … will book" while Iberia and Duffel Airways were bookable
    out_s, back_s = await asyncio.gather(search(origin, first_city, (start - timedelta(days=1)).isoformat(), adults=party, limit=8),
                                         search(last_city, origin, (last + timedelta(days=1)).isoformat(), adults=party, limit=8))
    flights = []
    for s in (out_s, back_s):
        if "why" in s:
            return {"why": f"the flights couldn't be priced — {s['why']}"}
        c = await _orderable([c for c in s["cards"] if c.get("currency") == "EUR"])
        if c is None:
            return {"why": "no test fare in euros that the airline's test system will book"}
        flights.append(c)
    lines = [f"⚠ TEST bookings — no hotel or airline is contacted, nothing is reserved and nothing is charged. For {party}."]
    total = 0.0
    for st in ss:
        eur = _eur(HT.rate_eur() * st["nights"])
        total += eur
        out = (date.fromisoformat(st["checkin"]) + timedelta(days=st["nights"])).isoformat()
        lines.append(f"🏨 {st['hotel']}, {st['city']} — {st['checkin']} to {out}, {st['nights']} night{'s' if st['nights'] != 1 else ''} · "
                     f"€{eur:.2f} (TEST price, {HT.rate_eur():.0f}/night placeholder)")
    for c in flights:
        total += _eur(c["amount"])
        lines.append(f"✈️ {T.card_line(c)}")
    lines.append(f"Total €{total:.2f} (TEST) — ONE tap to pay on your phone: Apple Pay or a saved card on Stripe's TEST page.")
    lines.append("Each goes in your itinerary on its day, marked TEST, with its reference.")
    sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    b = {"stays": ss, "flights": flights, "lines": lines, "sha256": sha, "eur": round(total, 2), "party": party, "title": p.get("title"), "tz": tz}
    _QUOTES[account] = b
    return b


import re  # noqa: E402

ASK = re.compile(r"^\s*(?:(?:ok(?:ay)?|yes|great|perfect|lovely|now|and)[,!. ]+)*(?:please\s+|let'?s\s+|can you\s+)?"
                 r"book\s+(?:it(?:\s+all)?|everything|(?:the|my|this)\s+(?:whole\s+|entire\s+)?trip|the\s+(?:hotels?|stays?)\s+and\s+(?:the\s+)?flights?|"
                 r"(?:the\s+)?hotels?\s+and\s+(?:the\s+)?flights?)"
                 r"(?:[,]?\s+(?:with\s+)?(?:the\s+)?(?:hotels?\s+and\s+(?:the\s+)?flights?))?"
                 r"(?:[,]?\s+(?:flying\s+)?from\s+(?P<origin>[A-ZÁÉÍÓÚa-záéíóúñ][\w .'-]{1,40}?))?\s*(?:please)?\s*[.!]?\s*$", re.I)


def asked(message: str) -> Optional[str]:
    """"book it" / "book the whole trip from Madrid" → the origin said ("" when none), else None."""
    m = ASK.match(message or "")
    return None if not m else (m["origin"] or "").strip()


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


@router.post("/trip/prepare")
async def prepare(request: Request):
    from .account import account_for
    from . import travel as T
    if not T.token():
        return _refuse(422, "travel_off", "flights need a Duffel TEST token, and none is set")
    try:
        body = await request.json()
    except Exception:
        body = {}
    origin = str((body or {}).get("from") or "Madrid").strip()[:60] or "Madrid"
    b = await bundle(account_for(request), origin)
    if "why" in b:
        return _refuse(422, "trip_not_bookable", b["why"])
    return {"ok": True, "read_back": {"lines": b["lines"], "sha256": b["sha256"]}, "eur": b["eur"], "title": b["title"]}


@router.post("/trip/pay")
async def pay(request: Request):
    from . import guest_whatsapp as GW, test_deposit as TD, yes as YS
    from .account import account_for
    account = account_for(request)
    body = await request.json()
    if not YS.approval_ok(body.get("approval")):
        return _refuse(422, "approval_void", YS.APPROVAL_VOID)
    b = _QUOTES.get(account)
    if not b or body.get("read_back_sha256") != b["sha256"]:
        return _refuse(422, "approval_void", "the yes was to different words — prepare it again")
    got = await TD.checkout(f"{b['eur']:.2f}", "EUR", f"TEST — {b['title'] or 'your trip'}: {len(b['stays'])} hotels + 2 flights", b["sha256"][:16])
    if "why" in got:
        return _refuse(422, "test_payment_unavailable", got["why"])
    _QUOTES[got["id"]] = b   # the session's own bundle: a later prepare never changes what was paid for
    phone = await GW.tap_to_pay(account, f"€{b['eur']:.2f}", f"{b['title'] or 'your trip'} — {len(b['stays'])} hotels and 2 flights (TEST)", got["url"])
    return {"ok": True, "url": got["url"], "session_id": got["id"], "phone": phone}


ORDERABLE = None   # tests replace it


async def _orderable(cards: List[dict]) -> Optional[dict]:
    """Sasha 171 · the cheapest fare Duffel TEST still holds when asked for it again — live, its China Eastern fares came back
    from the search but were 'gone' when booked (the founder paid, and the flight home wasn't booked)."""
    from . import travel as T
    check = ORDERABLE or (lambda c: T.HTTP("GET", f"/air/offers/{c['id']}"))
    for c in cards:
        try:
            st, _j = await check(c)
        except Exception:
            continue
        if st == 200:
            return c
    return None


async def _same_or_cheaper(c: dict, party: int) -> Optional[dict]:
    from . import travel as T
    search = SEARCH or T.search
    try:
        r = await search(c.get("from_city") or c["from"], c.get("to_city") or c["to"], str(c["departs"])[:10], adults=party, limit=8)
    except Exception as e:
        log.warning("[trip_book] re-price failed: %s: %s", type(e).__name__, e)
        return None
    same = [x for x in r.get("cards") or [] if x.get("currency") == c.get("currency")]
    ok = [x for x in same if float(x["amount"]) <= float(c["amount"])] or \
         [x for x in same if float(x["amount"]) <= float(c["amount"]) * 1.5]   # TEST mode: a dearer test fare, said, not dropped
    return ok[0] if ok else None


async def book_paid(account: str, sid: str) -> dict:
    """Once paid: every hotel and flight, each recorded. Idempotent per session."""
    from . import hotel_test as HT, test_deposit as TD, travel as T, guest_whatsapp as GW, guest_receipt as GR
    if sid in _BOOKED:
        return _BOOKED[sid]
    b = _QUOTES.get(sid)
    if not b:
        return {"status": "failed", "say": "paid (TEST), but this server no longer holds what was paid for — nothing booked; ask me again"}
    _BOOKED[sid] = {"status": "booking"}
    done, failed = [], []
    for st in b["stays"]:
        ref = HT.new_ref()
        try:
            await HT.RECORD(account, st["hotel"], st["city"], b.get("tz") or "Europe/Madrid", st["checkin"],
                            st["nights"], b["party"], ref)
            done.append(f"🏨 {st['hotel']} — {st['checkin']}, {st['nights']} night{'s' if st['nights'] != 1 else ''} · {ref}")
        except Exception as e:
            log.error("[trip_book] hotel not recorded: %s: %s", type(e).__name__, e)
            failed.append(st["hotel"])
    _s, cj = await GW.api(account, "GET", "/api/booking/contact")
    contact = (cj or {}).get("contact") or {}
    email = await GR.address_of(account)
    for c in b["flights"]:
        o = await T.order(c, contact.get("name") or "Guest Test", email or "", contact.get("mobile_e164"))
        note = ""
        if "why" in o:
            # a TEST fare can be withdrawn between the quote and the payment (seen live): the same route and day, priced again,
            # booked only if it costs no more than what was paid — and said so
            alt = await _same_or_cheaper(c, b["party"])
            if alt is not None:
                o2 = await T.order(alt, contact.get("name") or "Guest Test", email or "", contact.get("mobile_e164"))
                if "why" not in o2:
                    diff = float(alt["amount"]) - float(c["amount"])
                    note = (f" (the fare priced had gone; this one is €{alt['amount']}" +
                            (f" — €{diff:.2f} more, TEST" if diff > 0 else ", not more") + ")")
                    c, o = alt, o2
        if "why" in o:
            failed.append(f"{c['from']}→{c['to']} ({o['why']})")
            continue
        await T.RECORD(account, c, o["booking_reference"] or "")
        done.append(f"✈️ {c['owner']} {c['flights']} {c['from']}→{c['to']} · {o['booking_reference']}{note}")
    say = "✅ Booked (TEST — nothing reserved or charged):\n" + "\n".join(done)
    if failed:
        say += "\nNot booked: " + "; ".join(failed)
    out = {"status": "booked" if done else "failed", "say": say, "booked": done, "failed": failed}
    _BOOKED[sid] = out
    TD.note(sid, bool(done), say.split("\n")[0])
    return out


@router.get("/trip/status")
async def trip_status(request: Request):
    from . import test_deposit as TD
    from .account import account_for
    sid = request.query_params.get("session_id") or ""
    if (_BOOKED.get(sid) or {}).get("status") in ("booked", "failed"):
        return {"ok": True, **_BOOKED[sid]}
    if (_BOOKED.get(sid) or {}).get("status") == "booking":
        return {"ok": True, "status": "awaiting_payment"}
    if not await TD.session_paid(sid):
        return {"ok": True, "status": "awaiting_payment"}
    return {"ok": True, **(await book_paid(account_for(request), sid))}


__all__ = ["router", "stays", "bundle", "book_paid", "asked", "ASK"]
