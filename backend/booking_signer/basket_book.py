"""Sasha 198 · R6 · "BOOK IT" FROM THE BASKET — the whole trip in one read-back, one yes, one Stripe payment; nothing in memory.

    quote()     Sherlock re-checks every chosen flight at Duffel. Still there at that price → kept. Gone or repriced → the SAME
                flight (same flight numbers, same day) searched again and kept, the difference said; not found → said, never
                swapped. No flight chosen → Magellan searches out and back, the cheapest bookable fare is suggested and chosen
                (said in the read-back). Stays are priced by their provider (the TEST hotel's placeholder rate, labelled).
                The read-back's lines are built from the rows alone, so the same rows always give the same sha256.
    pay()       the yes is bound to those lines (sha256 recomputed from the rows, not remembered); one Stripe TEST checkout; Austen
                holds every item with the session (pending_payment); paid_watch remembers the session for restarts.
    book_paid() after payment: each held item booked by its provider; Pacioli writes booked / failed with its line.

trip_book.py routes here when SASHA_BASKET=1 (basket.on()); its in-memory _QUOTES / _BOOKED are not used on this path.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import basket as BK

log = logging.getLogger(__name__)
SEARCH = None   # tests replace it (travel.search)


def _card(r: Dict[str, Any]) -> Dict[str, Any]:
    """A flight row → the card the Duffel order takes (travel.card_of's shape, kept in the snapshot)."""
    s = dict(r.get("snapshot") or {})
    s["id"] = r.get("provider_ref") or s.get("id")
    return s


async def _same_flight(account: str, r: Dict[str, Any], party: int) -> Optional[Dict[str, Any]]:
    """Sherlock: the guest's flight, re-found — the same flight numbers on the same day (a new offer id, maybe a new price)."""
    from . import travel as T
    c = _card(r)
    search = SEARCH or T.search
    try:
        res = await search(c.get("from") or "", c.get("to") or "", str(c.get("departs") or r.get("day") or "")[:10], adults=party, limit=50)
    except Exception as e:
        log.warning("[basket_book] re-search failed: %s: %s", type(e).__name__, e)
        return None
    return next((x for x in res.get("cards") or [] if x.get("flights") == c.get("flights") and x.get("owner") == c.get("owner")), None)


async def _validate_flight(account: str, r: Dict[str, Any], party: int) -> Dict[str, Any]:
    """{row, note} or {why}."""
    from . import travel as T
    c = _card(r)
    st, j = await T.HTTP("GET", f"/air/offers/{c['id']}")
    if st == 200 and str(j["data"]["total_amount"]) == str(c.get("amount")) and j["data"]["total_currency"] == c.get("currency"):
        return {"row": r, "note": ""}
    again = await _same_flight(account, r, party)
    if again is None:
        return {"why": f"the {c.get('owner')} flight {c.get('flights')} you picked is no longer offered — shall I look again?"}
    diff = float(again["amount"]) - float(c.get("amount") or 0)
    row = await BK.refresh(account, r["id"], provider_ref=again["id"], snapshot={**(r.get("snapshot") or {}), **again},
                           expires_at=again.get("expires_at"), price_amount=float(again["amount"]), price_currency=again["currency"])
    note = "" if abs(diff) < 0.005 else (f" (its price moved {'up' if diff > 0 else 'down'} €{abs(diff):.2f} since you picked it)")
    return {"row": row, "note": note}


async def _choose_cheapest(account: str, trip_id: str, frm: str, to: str, day: str, party: int) -> Optional[Dict[str, Any]]:
    """No flight chosen: Magellan searches, the cheapest fare Duffel TEST will still hold is suggested and chosen."""
    from . import travel as T, trip_book as TB
    search = SEARCH or T.search
    res = await search(frm, to, day, adults=party, limit=8)
    cards = [c for c in res.get("cards") or [] if c.get("currency") == "EUR"]
    c = await TB._orderable(cards)
    if c is None:
        return None
    sk = f"{frm}→{to} {day}"
    ids = await BK.suggest(account, trip_id, "flight", [{
        "provider": "duffel", "provider_ref": c["id"], "slice_key": sk, "day": day, "party": party, "expires_at": c.get("expires_at"),
        "price_amount": float(c["amount"]), "price_currency": c["currency"], "price_source": "quoted",
        "snapshot": {**c, "name": c.get("owner"), "picked_by": "Sasha — the cheapest bookable fare"}}], slice_key=sk)
    return await BK.choose(account, ids[0])


def lines_of(rows: List[Dict[str, Any]], party: int) -> List[str]:
    """The read-back, from the rows alone (the yes is bound to these words; a price-moved note is said beside them)."""
    from . import travel as T
    out = [f"⚠ TEST bookings — no hotel or airline is contacted, nothing is reserved and nothing is charged. For {party}."]
    for r in rows:
        s = r.get("snapshot") or {}
        if r["kind"] == "stay":
            out.append(f"🏨 {s.get('name')}, {s.get('city') or ''} — {r.get('day')} to {s.get('checkout')}, {s.get('nights')} "
                       f"night{'s' if s.get('nights') != 1 else ''} · €{float(r['price_amount']):.2f} "
                       f"({'TEST price, placeholder rate' if r.get('price_source') == 'placeholder' else r.get('price_source')})")
        elif r["kind"] == "flight":
            try:
                line = T.card_line(_card(r))
            except Exception:
                line = f"{s.get('owner')} {s.get('flights')} {s.get('from')}→{s.get('to')} · {r.get('price_currency')} {r.get('price_amount')} (TEST)"
            out.append(f"✈️ {line}" + (f" — {s['picked_by']}" if s.get("picked_by") else ""))
    t = BK.total(rows)
    out.append(f"Total €{t['amount']:.2f} (TEST) — ONE tap to pay on your phone: Apple Pay or a saved card on Stripe's TEST page.")
    out.append("Each goes in your itinerary on its day, marked TEST, with its reference.")
    return out


async def quote(account: str, origin: str) -> Dict[str, Any]:
    """The whole trip, validated and priced from the basket: {lines, sha256, eur, flights, chosen, ...} or {why}."""
    from . import hotel_test as HT, plan_store as PS
    p = await PS.latest(account)
    if not p or not (p.get("plan") or {}).get("days"):
        return {"why": "there's no trip plan on your account to book yet — ask me to plan one"}
    pl, trip = p.get("plan") or {}, p["trip_id"]
    try:
        party = max(1, min(9, int(pl.get("party") or pl.get("travelers") or 2)))
    except (TypeError, ValueError):
        party = 2
    m = PS.merge(p, [])
    days = m["days"]
    start = date.fromisoformat(str(days[0].get("date") or p.get("start") or "")[:10]) if (days[0].get("date") or p.get("start")) else None
    if start is None:
        return {"why": "the plan has no dates yet — tell me when it starts (e.g. “from 12 November”)"}
    rows = await BK.items(account, trip)
    if not [r for r in rows if r["kind"] == "stay"]:
        await BK.sync_stays(account, trip, days, start, party)
    notes: Dict[str, str] = {}
    chosen_fl = [r for r in await BK.items(account, trip, ("chosen",)) if r["kind"] == "flight"]
    picked_by_guest = bool(chosen_fl)
    if not chosen_fl:   # nothing chosen: out and back, the cheapest bookable (said in the read-back)
        last = date.fromisoformat(str(days[-1].get("date"))[:10])
        first_city, last_city = days[0].get("city") or "", days[-1].get("city") or ""
        got = await asyncio.gather(_choose_cheapest(account, trip, origin, first_city, (start - timedelta(days=1)).isoformat(), party),
                                   _choose_cheapest(account, trip, last_city, origin, (last + timedelta(days=1)).isoformat(), party))
        if None in got:
            return {"why": "no test fare in euros that the airline's test system will book"}
    for r in [r for r in await BK.items(account, trip, ("chosen",)) if r["kind"] == "flight"]:
        v = await _validate_flight(account, r, party)
        if "why" in v:
            return {"why": v["why"]}
        if v["note"]:
            notes[r["id"]] = v["note"]
    rate = HT.rate_eur()
    from .wa_brain import _country_of
    tz = HT.tz_of(_country_of(p.get("title") or "", []))
    for r in [r for r in await BK.items(account, trip, ("suggested", "chosen")) if r["kind"] == "stay"]:
        s = r.get("snapshot") or {}
        nights = int(s.get("nights") or 1)
        if r.get("price_source") != "placeholder" or float(r.get("price_amount") or 0) != round(rate * nights, 2) or s.get("tz") != tz:
            await BK.refresh(account, r["id"], price_amount=round(rate * nights, 2), price_currency="EUR", snapshot={**s, "tz": tz})
            await _source(account, r["id"], "placeholder", "test_hotel")
    rows = BK.to_book(await BK.items(account, trip, ("suggested", "chosen")))
    rows.sort(key=lambda r: (0 if r["kind"] == "stay" else 1, r.get("day") or "", r["id"]))
    lines = lines_of(rows, party)
    flights = [_card(r) for r in rows if r["kind"] == "flight"]
    t = BK.total(rows)
    return {"lines": lines + [f"Note: {(r.get('snapshot') or {}).get('owner')}{n}" for r in rows for k, n in notes.items() if k == r["id"]],
            "sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest(), "eur": t["amount"], "party": party,
            "title": p.get("title"), "trip_id": trip, "origin": origin, "tz": tz,
            "flights": flights, "chosen": picked_by_guest, "stays": [r for r in rows if r["kind"] == "stay"],
            "summary": {"hotels": sum(1 for r in rows if r["kind"] == "stay"),
                        "cities": [(r.get("snapshot") or {}).get("city") for r in rows if r["kind"] == "stay"], "party": party, "eur": t["amount"],
                        "flights": [f"{c.get('owner')} {c.get('flights')} · {c.get('from')}→{c.get('to')} · {str(c.get('departs') or '')[:10]}" for c in flights]}}


async def _source(account: str, item_id: str, source: str, provider: str) -> None:
    """Sherlock: the price now comes from the provider that will book it (the TEST hotel's placeholder rate)."""
    import uuid as _u

    async def fn(conn):
        await conn.execute("update trip_basket_items set price_source = $3, provider = $4, updated_at = now() where account_id = $1 and id = $2",
                           _u.UUID(account), _u.UUID(item_id), source, provider)
    await BK._go(fn)


async def current(account: str) -> Optional[Dict[str, Any]]:
    """The read-back as the rows stand NOW (no re-search, no re-price) — what pay() binds the yes to."""
    from . import plan_store as PS
    p = await PS.latest(account)
    if not p:
        return None
    pl = p.get("plan") or {}
    party = max(1, min(9, int(pl.get("party") or pl.get("travelers") or 2)))
    rows = BK.to_book(await BK.items(account, p["trip_id"], ("suggested", "chosen")))
    rows.sort(key=lambda r: (0 if r["kind"] == "stay" else 1, r.get("day") or "", r["id"]))
    return {"rows": rows, "party": party, "trip_id": p["trip_id"], "title": p.get("title")}


async def pay(account: str, read_back_sha256: str) -> Dict[str, Any]:
    """The yes → one Stripe TEST checkout for exactly the rows read back → every item held with the session (Austen)."""
    from . import guest_whatsapp as GW, test_deposit as TD, paid_watch as PWT
    cur = await current(account)
    if not cur or not cur["rows"]:
        return {"why": "there's nothing in this trip to book — ask me to price it again"}
    lines = lines_of(cur["rows"], cur["party"])
    sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    if sha != read_back_sha256:
        return {"why": "the yes was to different words — prepare it again"}
    t = BK.total(cur["rows"])
    n_st, n_fl = sum(1 for r in cur["rows"] if r["kind"] == "stay"), sum(1 for r in cur["rows"] if r["kind"] == "flight")
    what = f"{n_st} hotel{'s' if n_st != 1 else ''} + {n_fl} flight{'s' if n_fl != 1 else ''}"
    got = await TD.checkout(f"{t['amount']:.2f}", "EUR", f"TEST — {cur['title'] or 'your trip'}: {what}", sha[:16])
    if "why" in got:
        return {"why": got["why"]}
    await BK.hold(account, cur["trip_id"], got["id"])
    await PWT.remember(account, "trip", got["id"], {"basket": cur["trip_id"], "sha256": sha},
                       f"{cur['title'] or 'Your trip'} — {what}", None, "Europe/Madrid")
    phone = await GW.tap_to_pay(account, f"€{t['amount']:.2f}", f"{cur['title'] or 'your trip'} — {what} (TEST)", got["url"])
    return {"url": got["url"], "session_id": got["id"], "phone": phone, "eur": t["amount"]}


async def book_paid(account: str, sid: str) -> Dict[str, Any]:
    """After payment: every held item booked by its provider; Pacioli writes each outcome. Idempotent: a booked row is skipped."""
    from . import hotel_test as HT, travel as T, trip_book as TB, guest_whatsapp as GW, guest_receipt as GR
    rows = [r for r in await BK.by_session(sid) if r["account_id"] == account]
    if not rows:
        return {"status": "failed", "say": "paid (TEST), but no trip items are held for this payment — nothing booked; ask me again"}
    _s, cj = await GW.api(account, "GET", "/api/booking/contact")
    contact = (cj or {}).get("contact") or {}
    email = await GR.address_of(account)
    from . import passengers as PX
    people = await PX.saved(account)   # Sasha 198 R7 · the real travellers (asked once at "book it")
    for r in [r for r in rows if r["state"] == "pending_payment"]:
        s = r.get("snapshot") or {}
        if r["kind"] == "stay":
            ref = HT.new_ref()
            try:
                tid = await HT.RECORD(account, s.get("name"), s.get("city") or "", s.get("tz") or "Europe/Madrid",
                                      r["day"], int(s.get("nights") or 1), int(r.get("party") or 2), ref)
                await BK.booked(account, r["id"], booking_reference=ref, trip_item_id=tid)
            except Exception as e:
                await BK.failed(account, r["id"], f"not recorded ({type(e).__name__})")
        elif r["kind"] == "flight":
            c = _card(r)
            o = await T.order(c, contact.get("name") or "Guest Test", email or "", contact.get("mobile_e164"), people)
            if "why" in o:   # a TEST fare withdrawn between the quote and the payment: the same flight, priced again
                again = await TB._same_or_cheaper(c, int(r.get("party") or 2))
                if again is not None and again.get("flights") == c.get("flights"):
                    o2 = await T.order(again, contact.get("name") or "Guest Test", email or "", contact.get("mobile_e164"), people)
                    if "why" not in o2:
                        c, o = again, o2
            if "why" in o:
                await BK.failed(account, r["id"], o["why"])
                continue
            tid = await T.RECORD(account, c, o["booking_reference"] or "")
            await BK.booked(account, r["id"], booking_reference=o["booking_reference"] or "", order_id=o.get("order_id"), trip_item_id=tid)
            await BK.event("duffel_order", o.get("order_id") or f"{sid}:{r['id']}", "order.created", o, verified=True, item_id=r["id"])
    rows = await BK.by_session(sid)
    done = [r for r in rows if r["state"] == "booked"]
    bad = [r for r in rows if r["state"] == "failed"]
    say = "✅ Booked — everything's in your itinerary." if done and not bad else ("Partly booked:" if done else "Not booked:")
    say += "\n" + "\n".join(r.get("status_line") or "" for r in done + bad)   # Pacioli's lines, word for word
    return {"status": "booked" if done else "failed", "say": say, "booked": [r["status_line"] for r in done],
            "failed": [r["status_line"] for r in bad]}


__all__ = ["quote", "current", "pay", "book_paid", "lines_of"]
