"""Sasha 226 · CANCEL OR CHANGE A BOOKED FLIGHT — Duffel TEST orders only, each in two steps: QUOTE, then CONFIRM.

The flow, for both:
  1. QUOTE — nothing is changed and no money moves. The order is read first (GET /air/orders/{id}): if the airline doesn't
     offer the action through Duffel ("cancel"/"change" missing from `available_actions`, or the fare conditions say no),
     the answer is {"possible": False, "say": ...} in plain words. Otherwise Duffel is asked for its own quote:
       cancel → POST /air/order_cancellations            (a PENDING cancellation: refund amount, where it goes, expiry)
       change → POST /air/order_change_requests           (then its offers, embedded or GET /air/order_change_offers)
                → the cheapest change offer                (change total, penalty, the new flight and times)
     The quote comes back with exact read-back `lines` for the person to say yes to.
  2. CONFIRM — called by the caller ONLY after the person's yes, with the quote's id:
       cancel → POST /air/order_cancellations/{id}/actions/confirm
       change → POST /air/order_changes {selected_order_change_offer} → POST /air/order_changes/{id}/actions/confirm
                (paid from Duffel's TEST balance)

Every function returns a dict and never raises for the provider: a refusal is {"why": "<Duffel's own words>"}, an outage
is {"why", "outage": True}. A live token or a live-mode answer is refused, always. Nothing here writes the basket — the
caller settles the basket row (order_id / booking_reference) from what CONFIRM returns.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import travel as TR

log = logging.getLogger("booking_signer.flight_manage")

HTTP = None   # Sasha 226 · tests replace it; None → travel.HTTP (the Duffel client)
TEST_LINE = "This is a TEST booking — no money moves."
SYMBOL = {"EUR": "€", "GBP": "£", "USD": "$"}
REFUND_TO = {"original_form_of_payment": "to your original payment", "balance": "to the Duffel test balance",
             "voucher": "as a voucher", "airline_credits": "as airline credit", "awaiting_payment": "— the order was never paid, so nothing"}


# ── Sasha 226 · plumbing: one call, never a raise ─────────────────────────────────────────────────────────────────────

async def _call(method: str, path: str, body: Optional[dict] = None, params: Optional[dict] = None) -> Tuple[int, Any]:
    fn = HTTP or TR.HTTP
    try:
        if params is not None:
            return await fn(method, path, body, params)
        return await fn(method, path, body)
    except Exception as e:   # timeout, connection refused, DNS — an outage, never "not allowed"
        log.warning("[flight_manage] Duffel unreachable on %s %s: %s", method, path, type(e).__name__)
        return 0, {"errors": [{"message": f"no answer ({type(e).__name__})"}]}


def _why(what: str, s: int, j: Any) -> Dict[str, Any]:
    if TR.down_status(s):
        return {"why": f"the airline's booking system (Duffel) isn't answering right now — {what} wasn't done", "outage": True,
                "provider_words": TR._err(j if isinstance(j, dict) else {}, s)}
    words = TR._err(j if isinstance(j, dict) else {}, s)
    return {"why": f"Duffel (test) refused {what}: {words}", "provider_words": words}


def _data(j: Any) -> Any:
    return (j or {}).get("data") if isinstance(j, dict) else None


def _live(d: Any) -> bool:
    return isinstance(d, dict) and bool(d.get("live_mode"))


LIVE_REFUSED = {"why": "Duffel answered in LIVE mode — refused"}
NO_TOKEN = {"why": "managing flights needs a Duffel TEST token (duffel_test_…), and none is set"}


def _amount(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def money(amount: Any, currency: Optional[str]) -> str:
    """'76.41','EUR' → '€76.41'; an unknown currency → 'CHF 76.41'."""
    a = _amount(amount)
    txt = f"{abs(a):.2f}" if a is not None else str(amount)
    sym = SYMBOL.get((currency or "").upper())
    return f"{sym}{txt}" if sym else f"{currency or ''} {txt}".strip()


def _day(iso: Optional[str]) -> str:
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00")).strftime("%a %d %b")
    except ValueError:
        return iso or "an unknown date"


def _clock(iso: Optional[str]) -> str:
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        return ""


def _until(expires_at: Optional[str]) -> str:
    """Duffel's expiry is UTC — said as such, never as local time."""
    t = _clock(expires_at)
    return f", valid until {t} UTC" if t else ""


def _segments(sl: dict) -> List[dict]:
    return [s for s in (sl or {}).get("segments") or [] if isinstance(s, dict)]


def _flights(segs: List[dict]) -> str:
    out = []
    for s in segs:
        c = s.get("marketing_carrier") or s.get("operating_carrier") or {}
        n = s.get("marketing_carrier_flight_number") or s.get("operating_carrier_flight_number") or ""
        out.append(f"{c.get('iata_code') or ''} {n}".strip())
    return " + ".join(x for x in out if x) or "flight"


def _code(place: Any) -> Optional[str]:
    if isinstance(place, dict):
        return place.get("iata_code") or place.get("iata_city_code")
    return place if isinstance(place, str) else None


def _ends(sl: dict) -> Tuple[Optional[str], Optional[str]]:
    segs = _segments(sl)
    o = _code(sl.get("origin")) or (_code(segs[0].get("origin")) if segs else None)
    d = _code(sl.get("destination")) or (_code(segs[-1].get("destination")) if segs else None)
    return o, d


def _owner(order: dict) -> str:
    return ((order or {}).get("owner") or {}).get("name") or "The airline"


def _slice_line(sl: dict) -> Dict[str, Any]:
    segs = _segments(sl)
    o, d = _ends(sl)
    dep = segs[0].get("departing_at") if segs else None
    arr = segs[-1].get("arriving_at") if segs else None
    times = f"{_day(dep)} {_clock(dep)} {o or ''} → {_clock(arr)} {d or ''}".replace("  ", " ").strip() if dep else ""
    return {"flights": _flights(segs), "departs": dep, "arrives": arr, "from": o, "to": d, "times": times}


async def _order(order_id: str) -> Tuple[Optional[dict], Optional[Dict[str, Any]]]:
    s, j = await _call("GET", f"/air/orders/{order_id}")
    if s != 200:
        return None, _why("to read the booking", s, j)
    d = _data(j)
    if not isinstance(d, dict):
        return None, {"why": "Duffel (test) returned no booking for that order"}
    if _live(d):
        return None, dict(LIVE_REFUSED)
    return d, None


def _actions(order: dict) -> List[str]:
    return [str(a).lower() for a in order.get("available_actions") or []]


# ── Sasha 226 · CANCEL ────────────────────────────────────────────────────────────────────────────────────────────────

async def cancel_quote(order_id: str) -> Dict[str, Any]:
    """QUOTE only — a pending cancellation; nothing is cancelled until cancel_confirm(quote_id).
    {possible, quote_id, refund_amount, refund_currency, refund_to, expires_at, lines, say} | {possible: False, say} | {why}."""
    if not TR.token():
        return dict(NO_TOKEN)
    try:
        order, bad = await _order(order_id)
        if bad:
            return bad
        owner, ref = _owner(order), order.get("booking_reference") or "—"
        slices = [sl for sl in order.get("slices") or [] if isinstance(sl, dict)]
        first = _slice_line(slices[0]) if slices else {"flights": "flight", "departs": None}
        if order.get("cancelled_at"):
            say = f"Your {owner} booking {ref} is already cancelled — there's nothing left to cancel."
            return {"possible": False, "say": say, "lines": [say]}
        if "cancel" not in _actions(order):
            say = (f"{owner} doesn't allow cancelling this booking through our booking system (Duffel) — it would have to be "
                   f"cancelled with {owner} directly (booking {ref}).")
            return {"possible": False, "say": say, "lines": [say]}
        s, j = await _call("POST", "/air/order_cancellations", {"data": {"order_id": order_id}})
        if s not in (200, 201):
            return _why("to quote the cancellation", s, j)
        c = _data(j) or {}
        if _live(c):
            return dict(LIVE_REFUSED)
        amt, cur, to = c.get("refund_amount"), c.get("refund_currency"), c.get("refund_to")
        legs = " and ".join(f"{_slice_line(sl)['flights']} on {_day(_slice_line(sl)['departs'])}" for sl in slices) or \
            f"{first['flights']} on {_day(first['departs'])}"
        lines = [f"I'll cancel your {owner} flight {legs} (booking {ref})."]
        a = _amount(amt)
        if amt is None or a is None:
            lines.append(f"Duffel's quote doesn't give a refund amount{_until(c.get('expires_at'))} — I can't promise any refund.")
        elif a <= 0:
            lines.append(f"There is no refund (Duffel's own quote{_until(c.get('expires_at'))}).")
        else:
            where = REFUND_TO.get(str(to or ""), f"via {to}" if to else "")
            lines.append(f"The airline refunds {money(amt, cur)}{(' ' + where) if where else ''} "
                         f"(Duffel's own quote{_until(c.get('expires_at'))}).")
        lines.append(TEST_LINE)
        return {"possible": True, "quote_id": c.get("id"), "order_id": order_id, "refund_amount": amt, "refund_currency": cur,
                "refund_to": to, "expires_at": c.get("expires_at"), "lines": lines, "say": " ".join(lines)}
    except Exception as e:   # a shape Duffel never promised — said, never raised
        log.exception("[flight_manage] cancel_quote")
        return {"why": f"the cancellation quote couldn't be read ({type(e).__name__})"}


async def cancel_confirm(quote_id: str) -> Dict[str, Any]:
    """CONFIRM — only after the person's yes. {status: cancelled|not_cancelled, cancellation_id, refund_amount,
    refund_currency, provider_words} (+ why/outage when not cancelled)."""
    out: Dict[str, Any] = {"status": "not_cancelled", "cancellation_id": quote_id, "refund_amount": None, "refund_currency": None,
                           "provider_words": None}
    if not TR.token():
        return {**out, **NO_TOKEN}
    try:
        s, j = await _call("POST", f"/air/order_cancellations/{quote_id}/actions/confirm")
        if s not in (200, 201):
            w = _why("the cancellation", s, j)
            return {**out, **w}
        c = _data(j) or {}
        if _live(c):
            return {**out, **LIVE_REFUSED}
        if not c.get("confirmed_at"):   # Sasha 226 · accepted but not confirmed is never said as cancelled
            return {**out, "why": "Duffel (test) answered without confirming the cancellation", "provider_words": "no confirmed_at"}
        return {"status": "cancelled", "cancellation_id": c.get("id") or quote_id,
                "order_id": c.get("order_id"), "refund_amount": c.get("refund_amount"), "refund_currency": c.get("refund_currency"),
                "refund_to": c.get("refund_to"), "confirmed_at": c.get("confirmed_at"),
                "provider_words": f"confirmed_at {c['confirmed_at']}"}
    except Exception as e:
        log.exception("[flight_manage] cancel_confirm")
        return {**out, "why": f"the cancellation answer couldn't be read ({type(e).__name__})"}


# ── Sasha 226 · CHANGE ────────────────────────────────────────────────────────────────────────────────────────────────

def _pick_slice(slices: List[dict], leg: Optional[str]) -> Tuple[Optional[dict], Optional[Dict[str, Any]]]:
    if not slices:
        return None, {"why": "Duffel's booking has no flights on it to change"}
    if leg in (None, ""):
        if len(slices) == 1:
            return slices[0], None
        return None, {"why": "this booking has an outbound and a return flight — which one should move, out or back?", "ask": "leg"}
    if leg == "out":
        return slices[0], None
    if leg == "back":
        if len(slices) < 2:
            return None, {"why": "this booking has no return flight — only the outbound can be changed"}
        return slices[-1], None
    return None, {"why": f"I don't know the leg '{leg}' — it's out or back"}


async def _offers(req: dict) -> Tuple[List[dict], Optional[Dict[str, Any]]]:
    got = [o for o in req.get("order_change_offers") or [] if isinstance(o, dict)]
    if got or not req.get("id"):
        return got, None
    s, j = await _call("GET", "/air/order_change_offers", None, {"order_change_request_id": req["id"]})
    if s != 200:
        return [], _why("to list the change options", s, j)
    d = _data(j)
    return [o for o in (d if isinstance(d, list) else []) if isinstance(o, dict)], None


def _new_slices(offer: dict) -> List[dict]:
    sl = offer.get("slices") or {}
    add = sl.get("add") if isinstance(sl, dict) else None
    return [x for x in add or [] if isinstance(x, dict)]


async def change_quote(order_id: str, new_date: str, leg: Optional[str] = None) -> Dict[str, Any]:
    """QUOTE only — Duffel's change options for one leg moved to `new_date`; the cheapest is offered. Nothing is changed and
    nothing is paid until change_confirm(change_offer_id). {possible, change_offer_id, change_total_amount,
    change_total_currency, penalty_amount, new_flights, departs, lines, say} | {possible: False, say} | {why}."""
    if not TR.token():
        return dict(NO_TOKEN)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", new_date or ""):
        return {"why": f"the new date must be YYYY-MM-DD, not '{new_date}'"}
    try:
        order, bad = await _order(order_id)
        if bad:
            return bad
        owner, ref = _owner(order), order.get("booking_reference") or "—"
        if order.get("cancelled_at"):
            say = f"Your {owner} booking {ref} is cancelled — there's no flight left to change."
            return {"possible": False, "say": say, "lines": [say]}
        cond = (order.get("conditions") or {}).get("change_before_departure")
        if "change" not in _actions(order) or (isinstance(cond, dict) and cond.get("allowed") is False):
            why = "the fare doesn't allow changes" if isinstance(cond, dict) and cond.get("allowed") is False else \
                "the airline doesn't offer changes on it"
            say = (f"{owner} doesn't allow changing this booking through our booking system (Duffel) — {why}. "
                   f"Any change would have to be made with {owner} directly (booking {ref}).")
            return {"possible": False, "say": say, "lines": [say]}
        slices = [sl for sl in order.get("slices") or [] if isinstance(sl, dict)]
        sl, bad = _pick_slice(slices, leg)
        if bad:
            return bad
        o, d = _ends(sl)
        if not sl.get("id") or not o or not d:
            return {"why": "Duffel's booking doesn't say which flight this is (no slice id or airports) — I can't ask for a change"}
        old = _slice_line(sl)
        s, j = await _call("POST", "/air/order_change_requests", {"data": {"order_id": order_id, "slices": {
            "remove": [{"slice_id": sl["id"]}],
            "add": [{"origin": o, "destination": d, "departure_date": new_date, "cabin_class": "economy"}]}}})
        if s not in (200, 201):
            return _why("to look for a change", s, j)
        req = _data(j) or {}
        if _live(req):
            return dict(LIVE_REFUSED)
        offers, bad = await _offers(req)
        if bad:
            return bad
        offers = [x for x in offers if _amount(x.get("change_total_amount")) is not None and not _live(x)]
        if not offers:
            say = f"{owner} has no flight from {o} to {d} on {_day(new_date)} that this booking can be changed to."
            return {"possible": False, "say": say, "lines": [say], "change_request_id": req.get("id")}
        best = min(offers, key=lambda x: _amount(x["change_total_amount"]))
        news = [_slice_line(x) for x in _new_slices(best)]
        new_flights = " + ".join(n["flights"] for n in news) if news else None
        departs = news[0]["departs"] if news else None
        cur = best.get("change_total_currency")
        tot, pen = _amount(best.get("change_total_amount")), best.get("penalty_total_amount")
        target = f"to {new_flights}, {news[0]['times']}" if news and news[0]["times"] else f"to {_day(new_date)}"
        lines = [f"I'll move your {owner} flight {old['flights']} on {_day(old['departs'])} {target} (booking {ref})."]
        quote = f"Duffel's own quote{_until(best.get('expires_at'))}"
        pen_txt = f", including the airline's {money(pen, best.get('penalty_total_currency') or cur)} change fee" \
            if _amount(pen) else ""
        if tot is not None and tot > 0:
            lines.append(f"The change costs {money(tot, cur)} in total{pen_txt} ({quote}).")
        elif tot is not None and tot < 0:
            lines.append(f"The new fare is lower: Duffel's quote shows {money(tot, cur)} back{pen_txt} ({quote}"
                         f"{', refunded ' + REFUND_TO[best['refund_to']] if best.get('refund_to') in REFUND_TO else ''}).")
        else:
            lines.append(f"The change costs nothing{pen_txt} ({quote}).")
        lines.append(TEST_LINE)
        return {"possible": True, "change_offer_id": best.get("id"), "change_request_id": req.get("id"), "order_id": order_id,
                "change_total_amount": best.get("change_total_amount"), "change_total_currency": cur,
                "new_total_amount": best.get("new_total_amount"), "new_total_currency": best.get("new_total_currency"),
                "penalty_amount": pen, "penalty_currency": best.get("penalty_total_currency"),
                "new_flights": new_flights, "departs": departs, "expires_at": best.get("expires_at"),
                "lines": lines, "say": " ".join(lines)}
    except Exception as e:
        log.exception("[flight_manage] change_quote")
        return {"why": f"the change quote couldn't be read ({type(e).__name__})"}


async def change_confirm(change_offer_id: str) -> Dict[str, Any]:
    """CONFIRM — only after the person's yes: the order change is created from the chosen offer, then confirmed and paid
    from Duffel's TEST balance. {status: changed|not_changed, order_change_id, booking_reference, provider_words}."""
    out: Dict[str, Any] = {"status": "not_changed", "order_change_id": None, "booking_reference": None, "provider_words": None}
    if not TR.token():
        return {**out, **NO_TOKEN}
    try:
        s, j = await _call("POST", "/air/order_changes", {"data": {"selected_order_change_offer": change_offer_id}})
        if s not in (200, 201):
            return {**out, **_why("the change", s, j)}
        ch = _data(j) or {}
        if _live(ch):
            return {**out, **LIVE_REFUSED}
        cid = ch.get("id")
        if not cid:
            return {**out, "why": "Duffel (test) made no order change from that offer"}
        out["order_change_id"] = cid
        amt, cur = ch.get("change_total_amount"), ch.get("change_total_currency")
        a = _amount(amt)
        # Sasha 226 · a change that costs something is paid from the TEST balance; nothing to pay → no payment sent
        body = {"data": {"payment": {"type": "balance", "amount": amt, "currency": cur}}} if a is not None and a > 0 else {"data": {}}
        s, j = await _call("POST", f"/air/order_changes/{cid}/actions/confirm", body)
        if s not in (200, 201):
            return {**out, **_why("to confirm the change", s, j)}
        done = _data(j) or {}
        if _live(done):
            return {**out, **LIVE_REFUSED}
        if not done.get("confirmed_at"):   # Sasha 226 · accepted but not confirmed is never said as changed
            return {**out, "why": "Duffel (test) answered without confirming the change", "provider_words": "no confirmed_at"}
        ref, oid = None, done.get("order_id") or ch.get("order_id")
        if oid:   # the order's reference after the change (airlines may issue a new one)
            s2, j2 = await _call("GET", f"/air/orders/{oid}")
            if s2 == 200 and isinstance(_data(j2), dict):
                ref = _data(j2).get("booking_reference")
        return {"status": "changed", "order_change_id": cid, "order_id": oid, "booking_reference": ref,
                "change_total_amount": done.get("change_total_amount", amt), "change_total_currency": done.get("change_total_currency", cur),
                "confirmed_at": done.get("confirmed_at"),
                "provider_words": f"confirmed_at {done['confirmed_at']}"}
    except Exception as e:
        log.exception("[flight_manage] change_confirm")
        return {**out, "why": f"the change answer couldn't be read ({type(e).__name__})"}


__all__ = ["cancel_quote", "cancel_confirm", "change_quote", "change_confirm", "money", "HTTP"]
