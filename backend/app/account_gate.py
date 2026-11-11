"""Sasha 370 · NO ROUTE ACTS ON A BOOKING, TRIP, PERSON OR PAYMENT WITHOUT THE ONE ACCOUNT RESOLVER AT ITS ROUTER.

Found (CR's finding #20): /bookings/create, /bookings/{id} and /bookings/cancel had no account at all — only the shared browser
key in front of them — and tenant.py said "individual routes decide". Every handler resolved WHO by itself, or didn't.

ONE source: app.services.chat_account.require_account, declared on the ROUTER (booking_signer.gate.require_booking_key for
/api/booking/*, which ends in the same resolver). Handlers read the result (chat_account.acting / booking_signer.account.account_for)
and check the owner (own_session, own_itinerary, own_offer, …).

  unguarded(app)         every mounted route whose dependencies hold neither door and that is not PUBLIC (by name, with a reason)
  refuse_unguarded(app)  called at the end of app/main.py: the server does not start while unguarded() is not empty

    cd backend && python -m unittest tests.test_s370_one_resolver_at_the_router -v
"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Set, Tuple

# (method, path) → why it carries no account. Nothing here reads or writes a booking, trip, person or payment.
PUBLIC: Dict[Tuple[str, str], str] = {
    ("GET", "/"): "the API's hello — no data",
    ("GET", "/health"): "Railway's liveness probe — no data",
    ("GET", "/openapi.json"): "FastAPI's schema — routes, no data",
    ("GET", "/docs"): "FastAPI's docs page — no data",
    ("GET", "/docs/oauth2-redirect"): "FastAPI's docs page — no data",
    ("GET", "/redoc"): "FastAPI's docs page — no data",
    ("POST", "/api/photos/search"): "Unsplash photos of a place — the public picture catalogue, no person (rate-limited)",
    ("POST", "/api/photos/context"): "Unsplash photos of a place — the public picture catalogue, no person (rate-limited)",
    ("GET", "/api/photos/destinations"): "the list of places with photos — public catalogue, no person",
    ("GET", "/api/cards"): "the credit-card benefits catalogue — public reference data, no person",
    ("GET", "/api/cards/{card_id}"): "one card's published benefits — public reference data, no person",
    ("GET", "/api/cards/{card_id}/rental"): "one card's published rental cover — public reference data, no person",
}


def _doors() -> Set[Callable]:
    from app.services.chat_account import require_account
    from booking_signer.gate import require_booking_key
    return {require_account, require_booking_key}


def _calls(dependant) -> Iterable[Callable]:
    for d in dependant.dependencies:
        if d.call is not None:
            yield d.call
        yield from _calls(d)


def routes(app) -> List[Tuple[str, str, object]]:
    """Every mounted (method, path, route) — HEAD folded into GET."""
    out = []
    for r in app.routes:
        methods = sorted(m for m in (getattr(r, "methods", None) or ()) if m != "HEAD")
        for m in methods:
            out.append((m, r.path, r))
    return out


def guarded(route) -> bool:
    dependant = getattr(route, "dependant", None)
    return dependant is not None and bool(_doors() & set(_calls(dependant)))


def unguarded(app) -> List[str]:
    return [f"{m} {p}" for m, p, r in routes(app) if (m, p) not in PUBLIC and not guarded(r)]


def refuse_unguarded(app) -> None:
    bad = unguarded(app)
    if bad:
        raise RuntimeError("Sasha 370 · these routes have no account resolver at their router (declare "
                           "dependencies=[Depends(require_account)] on the router, or name them in app/account_gate.PUBLIC "
                           "with a reason): " + ", ".join(bad))


__all__ = ["PUBLIC", "routes", "guarded", "unguarded", "refuse_unguarded"]
