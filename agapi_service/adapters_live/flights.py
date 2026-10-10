"""CR 70 · FLIGHTS (Duffel), live: the sandbox's own flight functions (providers.find_flights / recheck_flight / order_flight → Sasha's
booking_signer.travel) on Duffel's REAL transport — with Sasha's TEST token. Decision 2 (Tyler's CR 70): no real money, so an order is
refused unless the token is a duffel_test_ one. Sasha has no Duffel order-cancel call (cancellations arrive by webhook): cancel is refused
as not_cancellable, said plainly, until one is built and tested."""
from __future__ import annotations

from .. import providers as PV
from ..adapters import Flights
from ..registry import AgapiError


def _err(j, s) -> str:
    return ((j or {}).get("errors") or [{}])[0].get("message") or f"HTTP {s}"


def _test_token() -> bool:
    from booking_signer import travel as T
    return (T.token() or "").startswith("duffel_test_")


class LiveFlights(Flights):
    async def search(self, inp, up):
        return await PV.find_flights(inp, up)

    async def recheck(self, offer, up, passengers):
        return await PV.recheck_flight(offer, up, passengers)

    async def order(self, offer, travellers, up):
        if not _test_token():
            raise AgapiError("upstream_refused", "Live flight orders run on Duffel TEST only for now (no real money); the token isn't a test one.",
                             {"service": "duffel", "reason": "test_mode_only"})
        return await PV.order_flight(offer, travellers, up)

    async def cancel_quote(self, order_id: str) -> dict:
        """CR 71 · Duffel's own cancellation QUOTE for the order (nothing is cancelled yet): the refund it will give, until when."""
        from booking_signer import travel as T
        if not _test_token():
            raise AgapiError("upstream_refused", "Flight cancellations run on Duffel TEST only for now.", {"service": "duffel", "reason": "test_mode_only"})
        st, j = await T.HTTP("POST", "/air/order_cancellations", {"data": {"order_id": order_id}})
        d = (j or {}).get("data") or {}
        if st not in (200, 201) or not d.get("id") or d.get("live_mode"):
            raise AgapiError("not_cancellable", f"The airline won't quote a cancellation for this order ({_err(j, st)}).", {"service": "duffel"})
        return {"quote_id": d["id"], "order_id": order_id, "refund": {"amount_minor": PV._minor(str(d.get("refund_amount") or "0")),
                "currency": d.get("refund_currency") or "EUR"}, "refund_to": d.get("refund_to"), "expires_at": d.get("expires_at")}

    async def cancel(self, service, act_id, up, prep=None, approval=None):
        """CR 71 · after the cancellation's yes: Duffel confirms ITS quote (the refund the person approved) → evidence from its answer."""
        import hashlib
        import json
        import time
        from booking_signer import travel as T
        if not prep or not prep.get("quote_id"):
            raise AgapiError("not_cancellable", "No airline cancellation quote for this flight; ask to cancel again.", {"service": "duffel"})
        if not _test_token():
            raise AgapiError("upstream_refused", "Flight cancellations run on Duffel TEST only for now.", {"service": "duffel", "reason": "test_mode_only"})
        t0 = time.perf_counter()
        st, j = await T.HTTP("POST", f"/air/order_cancellations/{prep['quote_id']}/actions/confirm", None)
        d = (j or {}).get("data") or {}
        if st not in (200, 201) or not d.get("confirmed_at") or d.get("live_mode"):
            up.add("duffel", t0, False, "upstream_refused")
            raise AgapiError("upstream_refused", f"The airline didn't confirm the cancellation ({_err(j, st)}); nothing changed.", {"service": "duffel"})
        up.add("duffel", t0, True)
        amount = f"{d.get('refund_currency') or ''} {d.get('refund_amount') or '0'}".strip()
        return {"reference": d["id"], "service": "duffel", "outcome_kind": "CONFIRMED",
                "words": f"Cancelled by the airline (Duffel TEST) — refund {amount} to {d.get('refund_to') or 'the original payment'}.",
                "sha256": hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()}

    async def smoke(self) -> dict:
        """Spends nothing, contacts nobody: one airline from Duffel's reference data (no offer request, no order)."""
        from booking_signer import travel as T
        st, j = await T.HTTP("GET", "/air/airlines", params={"limit": 1})
        return {"ok": st == 200 and bool((j or {}).get("data")), "status": st, "token": "test" if _test_token() else "NOT a test token"}

    async def smoke_cancel(self) -> dict:
        """CR 71 · the live cancellation, end to end, on a Duffel TEST order made HERE for this check (balance payment, test mode:
        nothing real is booked, paid or refunded) → Duffel's own answers, for the recorded tests. Refused unless the token is a test one."""
        from datetime import date, timedelta
        from booking_signer import travel as T
        if not _test_token():
            return {"ok": False, "why": "not a Duffel TEST token — refused"}
        day = (date.today() + timedelta(days=45)).isoformat()
        got = await T.search("MAD", "LHR", day, adults=1, limit=8)
        cards = got.get("cards") or []
        if not cards:
            return {"ok": False, "why": "no test offers", "search": {k: v for k, v in got.items() if k != "cards"}}
        pick = next((c for c in cards if "duffel airways" in str(c.get("owner") or "").lower()), None)   # Duffel's own test airline:
        if not pick:                                                                                    # the one that cancels through the API
            return {"ok": False, "why": "no Duffel Airways test offer on this route", "owners": sorted({str(c.get("owner")) for c in cards})}
        made = await T.order(pick, "Smoke Check", "smoke-check@agapi.kanoe.example", None)
        if not made.get("order_id"):
            return {"ok": False, "why": made.get("why") or "no order"}
        st, q = await T.HTTP("POST", "/air/order_cancellations", {"data": {"order_id": made["order_id"]}})
        quote = (q or {}).get("data") or {}
        if st not in (200, 201) or not quote.get("id"):
            return {"ok": False, "why": f"quote: {_err(q, st)}", "order_id": made["order_id"]}
        st2, c = await T.HTTP("POST", f"/air/order_cancellations/{quote['id']}/actions/confirm", None)
        conf = (c or {}).get("data") or {}
        keep = ("id", "order_id", "refund_amount", "refund_currency", "refund_to", "expires_at", "confirmed_at", "live_mode", "created_at")
        return {"ok": st2 in (200, 201) and bool(conf.get("confirmed_at")) and conf.get("live_mode") is False, "order_id": made["order_id"],
                "booking_reference": made.get("booking_reference"), "quote_status": st, "confirm_status": st2,
                "quote": {k: quote.get(k) for k in keep}, "confirmed": {k: conf.get(k) for k in keep}}
