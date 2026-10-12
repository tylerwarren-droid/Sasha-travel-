"""Sasha 244 · WHICH AgAPI, PER OPERATION FAMILY — live (agapi-live) or the sandbox (agapi-sandbox, test mode: Example Air, captured
messages, the fake inbox). One place decides; the fine-print and subscription modules ask it for every call.

    SASHA_AGAPI_ROUTE = "activities=live,entry=live,cards=live,subscriptions=live,money=live"   (production, Tyler's go, 11 Oct)

  · a family not named there keeps its old switch (SASHA_FINE_PRINT_VIA / SASHA_SUBSCRIPTIONS_VIA), whose default is the sandbox —
    so with nothing set, nothing changes. "all=sandbox" sends everything back to the sandbox in one line.
  · money.* is decided PER FLIGHT, not per family: a claim about TEST INVENTORY always goes to the sandbox, whatever the table says.
    Sasha's flights are Duffel TEST inventory by design (travel.token() refuses a live token) and they carry REAL airline codes
    ("UX 1153 · Air Europa"), so a flight in the person's own Sasha basket is test inventory — filing it on live would email a real
    airline about a flight that was never flown. Example Air (EX) and Duffel Airways (ZZ) are test carriers everywhere.
  · the end user, approvals and the sandbox's simulated yes all follow the target of the call they belong to (each AgAPI has its own
    end users and read-backs).

Sasha 249 · ONE ROUTE (EU 245 step 8): client_for(family, account, flight) → (url, key) is the ONLY place an AgAPI URL and key are
chosen. Fine print, subscriptions, the outcomes ledger, /s2's reads (via_agapi) and the venue engine (venue_truth) all ask it; the
five copied URL/key blocks are gone. Two families joined the table:
  · outcomes   the booking outcomes ledger. Its old switch SASHA_OUTCOMES_VIA is its legacy switch here (production: live), so
               nothing changes until the table names it.
  · s2_reads   /s2's AgAPI reads (SASHA_S2_VIA_AGAPI still says WHETHER /s2 asks AgAPI; this says WHICH one). Live by default, as
               via_agapi._url() always was; "all=…" never moves it (a sandbox's flights must never reach a real /s2 search) — only
               "s2_reads=sandbox" by name does."""
from __future__ import annotations

import contextvars
import logging
import os
import re
import uuid
from typing import Dict, Optional, Tuple

log = logging.getLogger("agapi.route")

FAMILIES = ("activities", "entry", "cards", "subscriptions", "money", "venues")   # Sasha 248 · venues: the venue engine (dive.onboard → venue.profile)
FAMILIES = FAMILIES + ("outcomes",)             # Sasha 249 · the outcomes ledger joins the one table
PINNED = ("s2_reads",)                           # Sasha 249 · /s2's AgAPI reads: live by default, moved only by its own name, never by "all"
ROUTED = FAMILIES + PINNED                       # every family the table can name
#: Sasha 249 · each family's old switch (its default is the sandbox), read only when the table doesn't name the family
_LEGACY = {"subscriptions": "SASHA_SUBSCRIPTIONS_VIA", "outcomes": "SASHA_OUTCOMES_VIA"}
_LEGACY_FIXED = {"s2_reads": "live"}             # via_agapi had no switch: its _url() was always live
#: Sasha 249 · target → (URL variable, its default, key variable). The one copy of what was copied five times.
ENDPOINTS = {"live": ("SASHA_AGAPI_URL", "https://agapi-live-production.up.railway.app", "SASHA_AGAPI_KEY"),
             "sandbox": ("SASHA_AGAPI_TEST_URL", "https://agapi-sandbox-production.up.railway.app", "SASHA_AGAPI_TEST_KEY")}
TEST_AIRLINES = {"EX", "ZZ"}   # Example Air (AgAPI's test fixture) · Duffel Airways (Duffel's test carrier)
_TARGET: contextvars.ContextVar = contextvars.ContextVar("agapi_target", default=None)


def table() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in os.getenv("SASHA_AGAPI_ROUTE", "").split(","):
        k, _, v = part.partition("=")
        k, v = k.strip().lower(), v.strip().lower()
        if v not in ("live", "sandbox"):
            continue
        if k == "all":
            out.update({f: v for f in FAMILIES})
        elif k in ROUTED:   # Sasha 249 · a pinned family by its own name
            out[k] = v
    return out


def _legacy(family: str) -> str:
    if family in _LEGACY_FIXED:   # Sasha 249
        return _LEGACY_FIXED[family]
    var = _LEGACY.get(family, "SASHA_FINE_PRINT_VIA")
    return "live" if os.getenv(var, "sandbox").strip().lower() == "live" else "sandbox"


def route(family: str) -> str:
    """live | sandbox for a family, from the table, else its old switch."""
    return table().get(family) or _legacy(family)


def current(family: str) -> str:
    """The target of the call in progress (set by `using`), else the family's route."""
    return _TARGET.get() or route(family)


class using:
    """with using("live"): … — every AgAPI call inside goes there."""

    def __init__(self, target: str):
        self.target, self.tok = target, None

    def __enter__(self):
        self.tok = _TARGET.set(self.target)
        return self.target

    def __exit__(self, *exc):
        _TARGET.reset(self.tok)
        return False


def _norm_number(airline: str, number: str) -> str:
    n = re.sub(r"\s+", "", str(number or "")).upper()
    return n[len(airline):] if airline and n.startswith(airline) else n


async def _in_their_basket(account: str, airline: str, number: str, date: str, booking_reference: str) -> bool:
    """The flight is one of THIS person's Sasha flights (Duffel test inventory): its booking reference, or its carrier + number (and day)."""
    try:
        from booking_signer import basket as BK
    except Exception:
        return False

    async def fn(conn):
        return await conn.fetch("select snapshot, booking_reference from trip_basket_items where account_id = $1 and kind = 'flight'",
                                uuid.UUID(account))
    try:
        rows = await BK._go(fn)
    except Exception as e:
        log.warning("[route] basket not read (treated as test inventory): %s", type(e).__name__)
        return True   # when in doubt, never file on live
    import json
    for r in rows or []:
        if booking_reference and (r["booking_reference"] or "").upper() == booking_reference.upper():
            return True
        s = r["snapshot"]
        try:
            while isinstance(s, str):
                s = json.loads(s)
        except Exception:
            continue
        flights = re.sub(r"\s+", "", str((s or {}).get("flights") or "")).upper()
        if airline and number and f"{airline}{number}" in flights.split(","):
            if not date or str((s or {}).get("departs") or "")[:10] == date[:10]:
                return True
    return False


async def money_target(account: str, flight: Optional[dict], booking_reference: Optional[str] = None) -> str:
    """A money-back claim's AgAPI: the sandbox for test inventory (Example Air / Duffel Airways, or a flight in their own Sasha
    basket), the money family's route for a real airline."""
    f = flight or {}
    airline = str(f.get("airline") or "").strip().upper()
    if airline in TEST_AIRLINES:
        return "sandbox"
    if route("money") == "sandbox":
        return "sandbox"
    number = _norm_number(airline, f.get("number") or "")
    if await _in_their_basket(account, airline, number, str(f.get("date") or ""), str(booking_reference or "")):
        return "sandbox"
    return "live"


def endpoint(target: str) -> Tuple[str, str]:
    """Sasha 249 · a target ("live" | "sandbox") → (its URL, its key). Never logged, never printed."""
    url_var, url_default, key_var = ENDPOINTS["live" if target == "live" else "sandbox"]
    return os.getenv(url_var, url_default).rstrip("/"), os.getenv(key_var, "").strip()


async def target_for(family: str, account: Optional[str] = None, flight: Optional[dict] = None,
                     booking_reference: Optional[str] = None) -> str:
    """Sasha 249 · live | sandbox for ONE call: the call in progress (`using`), else a money claim by its flight (money_target),
    else the family's route."""
    if _TARGET.get():
        return _TARGET.get()
    if family == "money" and flight is not None and account:
        return await money_target(account, flight, booking_reference)
    return route(family)


async def client_for(family: str, account: Optional[str] = None, flight: Optional[dict] = None,
                     booking_reference: Optional[str] = None) -> Tuple[str, str]:
    """Sasha 249 · ONE ROUTE: the (url, key) an AgAPI call of this family uses — the only place either is chosen (T12)."""
    return endpoint(await target_for(family, account, flight, booking_reference))


def key_name(target: str) -> str:
    """Sasha 249 · the key's variable NAME, for a 'not configured' line (never its value)."""
    return ENDPOINTS["live" if target == "live" else "sandbox"][2]


def ctx_mode() -> str:
    """Sasha 249 · the mode of sasha.turn's agapi.v0 Ctx. v0 runs Sasha's OWN engine on Duffel TEST inventory only (travel.token()
    refuses a live token; v0.call refuses any other mode), whatever AgAPI a family is routed to — so it is "test" for every family.
    It is said here so the route is the one place that decides it; any other value would stop every v0 tool (bookings, payments)."""
    return "test"


__all__ = ["FAMILIES", "PINNED", "ROUTED", "TEST_AIRLINES", "table", "route", "current", "using", "money_target", "endpoint", "target_for", "client_for",
           "key_name", "ctx_mode"]
