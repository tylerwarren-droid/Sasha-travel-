"""CR 70 · FLIGHTS (Duffel), live: the sandbox's own flight functions (providers.find_flights / recheck_flight / order_flight → Sasha's
booking_signer.travel) on Duffel's REAL transport — with Sasha's TEST token. Decision 2 (Tyler's CR 70): no real money, so an order is
refused unless the token is a duffel_test_ one. Sasha has no Duffel order-cancel call (cancellations arrive by webhook): cancel is refused
as not_cancellable, said plainly, until one is built and tested."""
from __future__ import annotations

from .. import providers as PV
from ..adapters import Flights
from ..registry import AgapiError


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

    async def cancel(self, service, act_id, up):
        raise AgapiError("not_cancellable", "A flight can't be cancelled through AgAPI yet: Sasha has no Duffel cancel call (cancellations "
                         "arrive by Duffel's webhook). Cancel with the airline.", {"service": "duffel", "reason": "no_cancel_call"})

    async def smoke(self) -> dict:
        """Spends nothing, contacts nobody: one airline from Duffel's reference data (no offer request, no order)."""
        from booking_signer import travel as T
        st, j = await T.HTTP("GET", "/air/airlines", params={"limit": 1})
        return {"ok": st == 200 and bool((j or {}).get("data")), "status": st, "token": "test" if _test_token() else "NOT a test token"}
