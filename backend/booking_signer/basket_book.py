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
    except Exception as e:   # Sasha 215 · a failed re-search is an outage — never "the flight is gone"
        log.warning("[basket_book] re-search failed: %s: %s", type(e).__name__, e)
        raise T.DuffelDown(type(e).__name__) from e
    if res.get("outage"):
        raise T.DuffelDown(res.get("why") or "")
    return next((x for x in res.get("cards") or [] if x.get("flights") == c.get("flights") and x.get("owner") == c.get("owner")), None)


async def _validate_flight(account: str, r: Dict[str, Any], party: int) -> Dict[str, Any]:
    """{row, note} or {why} — and {why, outage: True} when the airline can't be reached: Sasha 215 · CR 56 #3, a 5xx or a
    timeout is NEVER "no longer offered" (which swaps the person's chosen flight); the flight stays exactly as it was."""
    from . import travel as T
    c = _card(r)
    outage = {"why": f"I can't reach the airline to re-check your {c.get('owner')} flight right now — it's unchanged", "outage": True}
    try:
        st, j = await T.call_duffel("GET", f"/air/offers/{c['id']}")
    except T.DuffelDown as e:
        log.warning("[basket_book] offer check: Duffel down (%s) — the flight is kept, said as an outage", e)
        return outage
    if st == 200 and str(j["data"]["total_amount"]) == str(c.get("amount")) and j["data"]["total_currency"] == c.get("currency"):
        return {"row": r, "note": ""}
    try:
        again = await _same_flight(account, r, party)
    except T.DuffelDown:
        return outage
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
            return {"why": v["why"], **({"outage": True} if v.get("outage") else {})}
        if v["note"]:
            notes[r["id"]] = v["note"]
    rate = HT.rate_eur()
    from .wa_brain import _country_of
    tz = HT.tz_of(_country_of(p.get("title") or "", []))
    for r in [r for r in await BK.items(account, trip, ("suggested", "chosen")) if r["kind"] == "stay"]:
        s = r.get("snapshot") or {}
        if s.get("est") and r.get("price_amount"):   # Sasha 211 · a real hotel's ESTIMATE (the world planner): kept, said as one
            continue
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


async def _all_booked(account: str) -> bool:
    from . import plan_store as PS
    p = await PS.latest(account)
    return bool(p) and bool(await BK.items(account, p["trip_id"], ("booked",)))


async def in_progress(account: str) -> Optional[Dict[str, Any]]:
    """Sasha 220 · the basket's payment already under way (its items held with a Stripe session): {sid, trip_id, rows} or None."""
    from . import plan_store as PS
    p = await PS.latest(account)
    if not p:
        return None
    rows = await BK.items(account, p["trip_id"], ("pending_payment",))
    sids = {r.get("paid_session") for r in rows if r.get("paid_session")}
    return {"sid": sorted(sids)[0], "trip_id": p["trip_id"], "rows": rows} if len(sids) == 1 else None


async def _supersede(account: str, pend: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sasha 221b · a payment under way for rows that are NO LONGER what was read back: expired at Stripe first (so it can never be
    paid), its items cancelled → None (the caller opens the checkout for the new read-back). Paid already → refused: never two."""
    from . import test_deposit as TD, paid_watch as PWT
    sid = pend["sid"]
    st = await TD.session_state(sid)
    settled = await PWT.settle(sid)
    if (st and st["paid"]) or (settled and settled.get("status") in ("booked", "booking", "failed")):
        return {"why": "your earlier payment for this trip has already gone through, so I haven't opened a second one — "
                       "let me confirm what that booked first"}
    if st and st["status"] == "open" and not await TD.expire(sid):
        st = await TD.session_state(sid)
        if st and st["paid"]:
            return {"why": "your earlier payment for this trip has just gone through, so I haven't opened a second one"}
        return {"why": "I couldn't close the earlier payment page, so I haven't opened another — nothing was charged. Try me again in a minute."}
    await BK.cancel_held(account, pend["trip_id"], sid)
    log.info("[basket_book] payment %s superseded by a new read-back — expired, its items cancelled", sid[:14])
    return None


async def _resume(account: str, pend: Dict[str, Any], where: str) -> Optional[Dict[str, Any]]:
    """Sasha 220 · ONE PAYMENT PER BASKET. A payment already under way: paid → "already paid" (never a second charge); the same
    channel again → the same session (its link resent, or its card again); the other channel → the open session is EXPIRED at
    Stripe first (so it can never also be paid), its items released, and None (the caller opens the new one)."""
    from . import guest_whatsapp as GW, test_deposit as TD, paid_watch as PWT
    sid = pend["sid"]
    st = await TD.session_state(sid)
    settled = await PWT.settle(sid)
    if (st and st["paid"]) or (settled and settled.get("status") in ("booked", "booking", "failed")):
        return {"already_paid": True, "session_id": sid, "eur": (st or {}).get("amount")}
    if st and st["status"] == "open" and st.get("where") == where:
        if where == "here":
            return {"where": "here", "session_id": sid, "client_secret": st.get("client_secret"), "url": st.get("url"), "eur": st["amount"],
                    "resumed": True}
        phone = await GW.tap_to_pay(account, f"€{st['amount']:.2f}", "your trip (TEST)", st["url"])
        return {"where": "phone", "session_id": sid, "url": st["url"], "phone": phone, "eur": st["amount"], "resumed": True}
    if st and st["status"] == "open" and not await TD.expire(sid):   # the switch: the old one can never also be paid
        st = await TD.session_state(sid)
        if st and st["paid"]:
            return {"already_paid": True, "session_id": sid, "eur": st.get("amount")}
        return {"why": "I couldn't close the first payment page, so I haven't opened another — nothing was charged twice. Try me again in a minute."}
    await BK.release(account, pend["trip_id"], sid)
    # the payment MOVES: exactly the rows that were held, for exactly the amount they were held for (never re-picked from the basket)
    return {"move": {"rows": pend["rows"], "trip_id": pend["trip_id"], "amount": (st or {}).get("amount")}}


async def pay(account: str, read_back_sha256: str, where: str = "phone") -> Dict[str, Any]:
    """The yes → one Stripe TEST checkout for exactly the rows read back → every item held with the session (Austen). Sasha 220:
    `where` — "phone": the link to their WhatsApp, as before; "here": an embedded checkout for the page they're on."""
    from . import guest_whatsapp as GW, test_deposit as TD, paid_watch as PWT
    pend = await in_progress(account)
    if pend:   # Sasha 221b · the yes is to a NEW read-back (the rows now chosen, word for word): the old payment never stands in for it
        cur = await current(account)
        if cur and cur["rows"] and hashlib.sha256("\n".join(lines_of(cur["rows"], cur["party"])).encode()).hexdigest() == read_back_sha256:
            dropped = await _supersede(account, pend)
            if dropped:
                return dropped
            pend = None
    if pend:
        resumed = await _resume(account, pend, where)
        if "move" not in resumed:
            return resumed
        return await _moved(account, resumed["move"], where)
    cur = await current(account)
    if (not cur or not cur["rows"]) and await _all_booked(account):   # Sasha 220 · paid and booked already: never a second charge
        return {"already_paid": True}
    if not cur or not cur["rows"]:
        return {"why": "there's nothing in this trip to book — ask me to price it again"}
    lines = lines_of(cur["rows"], cur["party"])
    sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    if sha != read_back_sha256:
        return {"why": "the yes was to different words — prepare it again"}
    t = BK.total(cur["rows"])
    n_st, n_fl = sum(1 for r in cur["rows"] if r["kind"] == "stay"), sum(1 for r in cur["rows"] if r["kind"] == "flight")
    what = f"{n_st} hotel{'s' if n_st != 1 else ''} + {n_fl} flight{'s' if n_fl != 1 else ''}"
    # Sasha 220 · "here" is the embedded card once the page has Stripe's publishable key (SASHA_PAY_EMBEDDED=1, set with it);
    # until then Stripe's own page, opened on the SAME device — never a dead end
    import os as _os
    got = await TD.checkout(f"{t['amount']:.2f}", "EUR", f"TEST — {cur['title'] or 'your trip'}: {what}", sha[:16],
                            embedded=(where == "here" and _os.getenv("SASHA_PAY_EMBEDDED", "") == "1"), where=where,
                            name=f"{cur['title'] or 'Your trip'}: {what}" if where == "here" else None)   # Sasha 222 · the pay card's line
    if "why" in got:
        return {"why": got["why"]}
    await BK.hold(account, cur["trip_id"], got["id"])
    # Sasha 215 · CR 56 #2 — PAID-NEVER-BOOKED IS IMPOSSIBLE: the restart-safe record that books it after payment is written
    # FIRST; without it no link is sent (the Stripe session is expired so it can never be paid) and she says so
    rec = await PWT.remember(account, "trip", got["id"], {"basket": cur["trip_id"], "sha256": sha},
                             f"{cur['title'] or 'Your trip'} — {what}", None, "Europe/Madrid")
    if not rec:
        log.error("[basket_book] payment record not written for %s — no link sent", got["id"])
        try:
            await TD.expire(got["id"])
        except Exception as e:
            log.error("[basket_book] the unrecorded session was not expired: %s: %s", type(e).__name__, e)
        try:
            await BK.release(account, cur["trip_id"], got["id"])
        except Exception as e:
            log.error("[basket_book] the held items were not released: %s: %s", type(e).__name__, e)
        return {"why": "I couldn't save the payment record, so I haven't sent a payment link — nothing was charged. Try me again in a minute.",
                "unrecorded": True}
    if where == "here":   # Sasha 220 · the card on the page they're on; nothing to their phone
        return {"where": "here", "session_id": got["id"], "client_secret": got.get("client_secret"), "url": got.get("url"), "eur": t["amount"]}
    phone = await GW.tap_to_pay(account, f"€{t['amount']:.2f}", f"{cur['title'] or 'your trip'} — {what} (TEST)", got["url"])
    return {"url": got["url"], "session_id": got["id"], "phone": phone, "eur": t["amount"], "where": "phone"}


async def _moved(account: str, mv: Dict[str, Any], where: str) -> Dict[str, Any]:
    """Sasha 220 · the same payment, moved here ↔ phone: the SAME rows, the SAME amount (refused if it would differ)."""
    from . import guest_whatsapp as GW, test_deposit as TD, paid_watch as PWT, plan_store as PS
    rows = [{**r, "state": "chosen"} for r in mv["rows"]]
    amount = round(sum(float(r["price_amount"]) for r in rows if r.get("price_amount") is not None), 2)
    if mv.get("amount") is not None and abs(amount - float(mv["amount"])) > 0.01:
        log.error("[basket_book] a moved payment would change its amount (%.2f → %.2f) — refused", mv["amount"], amount)
        return {"why": "the payment's total would change if I moved it, so I haven't — ask me to read it back again"}
    p = await PS.latest(account)
    party = max(1, min(9, int(((p or {}).get("plan") or {}).get("party") or 2)))
    title = (p or {}).get("title")
    sha = hashlib.sha256("\n".join(lines_of(rows, party)).encode()).hexdigest()
    n_st, n_fl = sum(1 for r in rows if r["kind"] == "stay"), sum(1 for r in rows if r["kind"] == "flight")
    what = f"{n_st} hotel{'s' if n_st != 1 else ''} + {n_fl} flight{'s' if n_fl != 1 else ''}"
    import os as _os
    got = await TD.checkout(f"{amount:.2f}", "EUR", f"TEST — {title or 'your trip'}: {what}", sha[:16],
                            embedded=(where == "here" and _os.getenv("SASHA_PAY_EMBEDDED", "") == "1"), where=where,
                            name=f"{title or 'Your trip'}: {what}" if where == "here" else None)   # Sasha 222 · the pay card's line
    if "why" in got:
        return {"why": got["why"]}
    await BK.hold_ids(account, mv["trip_id"], [r["id"] for r in rows], got["id"])
    rec = await PWT.remember(account, "trip", got["id"], {"basket": mv["trip_id"], "sha256": sha}, f"{title or 'Your trip'} — {what}",
                             None, "Europe/Madrid")
    if not rec:
        await TD.expire(got["id"])
        await BK.release(account, mv["trip_id"], got["id"])
        return {"why": "I couldn't save the payment record, so I haven't moved the payment — nothing was charged.", "unrecorded": True}
    if where == "here":
        return {"where": "here", "session_id": got["id"], "client_secret": got.get("client_secret"), "url": got.get("url"), "eur": amount, "moved": True}
    phone = await GW.tap_to_pay(account, f"€{amount:.2f}", f"{title or 'your trip'} — {what} (TEST)", got["url"])
    return {"where": "phone", "url": got["url"], "session_id": got["id"], "phone": phone, "eur": amount, "moved": True}


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
    from . import test_deposit as TD
    TD.note(sid, bool(done), say.split("\n")[0])   # Stripe's return page says what happened
    return {"status": "booked" if done else "failed", "say": say, "booked": [r["status_line"] for r in done],
            "failed": [r["status_line"] for r in bad]}


__all__ = ["quote", "current", "pay", "book_paid", "lines_of"]
