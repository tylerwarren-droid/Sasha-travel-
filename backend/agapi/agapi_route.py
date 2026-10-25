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


# Sasha 253 · THE PERSON'S MODE (test → the sandbox, every family): who a call is FOR, set once around it (`acting`) — the outcomes
# ledger sets it on every write, so a booking finished later by the server (a payment watcher, a webhook) is routed by the same rule
_ACCOUNT: contextvars.ContextVar = contextvars.ContextVar("agapi_account", default=None)


class acting:
    """with acting(account): … — every AgAPI call inside is for this person (their mode decides live or the sandbox)."""

    def __init__(self, account: Optional[str]):
        self.account, self.tok = account, None

    def __enter__(self):
        self.tok = _ACCOUNT.set(self.account)
        return self.account

    def __exit__(self, *exc):
        _ACCOUNT.reset(self.tok)
        return False


# Sasha 287 · a run that is a TEST (a harness, a live proof) says so on every AgAPI call: `AgAPI-Lane: background` (CR 116 / CR 118c —
# AgAPI charges it to the background lane, never the people's). Unset: no header (a person's own call: their key's lane).
_LANE: contextvars.ContextVar = contextvars.ContextVar("agapi_lane", default=None)


class lane:
    """with lane("background"): … — every AgAPI call inside carries AgAPI-Lane: background."""

    def __init__(self, name: str):
        self.name, self.tok = name, None

    def __enter__(self):
        self.tok = _LANE.set(self.name)
        return self.name

    def __exit__(self, *exc):
        _LANE.reset(self.tok)
        return False


async def person_mode(account: Optional[str]) -> str:
    """Sasha 253 · "test" | "live" for a person. Sasha 254 item 5: the person's record (agapi.person_access — AgAPI's person_access,
    through access.get; ≤ 60 s). No row (every guest our suites and scratch scripts make, every guest session) or a failed read →
    "test": the sandbox. No person at all → "live" (the family's route decides). Until 254: app_metadata.kanoe_test."""
    if not account:
        return "live"
    from agapi import person_access as PA
    rec = await PA.get(account)
    if rec.get("source") in ("person_access", "installed"):   # a person WITH a row: the record decides
        return "live" if rec.get("mode") == "live" else "test"
    # No row (a public guest) or an unreadable record: closed for POWERS, but the sandbox is not the safe side for a real guest's
    # paid flows (subscriptions, money, activities would land on test inventory). Their mode is the guest's own marker — every
    # suite and scratch guest carries kanoe_test (guest_accounts.create_guest) — and unreadable → live, as in 253.
    return await _marker_mode(account)


_MODE: Dict[str, Tuple[str, float]] = {}   # account → (mode, read at) — the guest marker, read once per 10 minutes
MODE_TTL_S = 600


async def _marker_mode(account: str) -> str:
    import time as _time
    hit = _MODE.get(account)
    if hit and _time.time() - hit[1] < MODE_TTL_S:
        return hit[0]
    mode = "live"
    try:
        from booking_signer import ops
        st, u = await ops.ADMIN("GET", f"/admin/users/{account}", None)
        if st == 200 and ((u or {}).get("app_metadata") or {}).get("kanoe_test"):
            mode = "test"
    except Exception as e:
        log.warning("[route] the guest's marker not read (live): %s", type(e).__name__)
        return "live"   # not cached: read again next time
    _MODE[account] = (mode, _time.time())
    return mode


async def target_for(family: str, account: Optional[str] = None, flight: Optional[dict] = None,
                     booking_reference: Optional[str] = None) -> str:
    """Sasha 249 · live | sandbox for ONE call: the call in progress (`using`), else a TEST person → the sandbox (Sasha 253), else a
    money claim by its flight (money_target), else the family's route."""
    if _TARGET.get():
        return _TARGET.get()
    if await person_mode(account or _ACCOUNT.get()) == "test":   # Sasha 253 · the gate and every scratch guest never touch live
        return "sandbox"
    if family == "money" and flight is not None and account:
        return await money_target(account, flight, booking_reference)
    return route(family)


async def client_for(family: str, account: Optional[str] = None, flight: Optional[dict] = None,
                     booking_reference: Optional[str] = None) -> Tuple[str, str]:
    """Sasha 249 · ONE ROUTE: the (url, key) an AgAPI call of this family uses — the only place either is chosen (T12)."""
    return endpoint(await target_for(family, account, flight, booking_reference))


def failed_why(env: dict) -> str:
    """Sasha 261 (row 901) · what an AgAPI failure may say in a log: the exception CLASS AgAPI names in parentheses ("…couldn't be read
    (RuntimeError); nothing was kept") and its details' service / stop — never the message's other words (they can carry a merchant
    or a venue's text)."""
    e = (env or {}).get("error") or {}
    m = re.search(r"\(([A-Za-z_][A-Za-z0-9_.]{0,60})\)", str(e.get("message") or ""))
    d = e.get("details") if isinstance(e.get("details"), dict) else {}
    parts = ([f"cause {m.group(1)}"] if m else []) + [f"{k} {d[k]}" for k in ("service", "stop_reason") if isinstance(d.get(k), str)]
    return (" · " + ", ".join(parts)) if parts else ""


async def post(url: str, key: str, op: str, body: dict, headers: Dict[str, str], timeout: float) -> Dict:
    """Sasha 261 · THE ONE TRANSPORT every family's client sends through: AgAPI's envelope, or the transport's own (timeout /
    unreachable). An AgAPI outage (402/429, a timeout, unreachable) is noted once here — on the tool call in progress, and the
    founder told (agapi_health) — so every surface and family says it the same way."""
    import json
    import time
    import httpx
    from agapi import agapi_health as AH
    t0, status, version = time.perf_counter(), None, None
    if _LANE.get():   # Sasha 287 · a test run's lane, said on every call
        headers = {**headers, "AgAPI-Lane": _LANE.get()}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as c:
            r = await c.post(f"{url}/v1/{op}", headers=headers, content=json.dumps(body))
        status = r.status_code
        try:   # Sasha 275 · which AgAPI served it, when it says — read apart, so it can never change the answer
            hv = getattr(r, "headers", None) or {}
            version = hv.get("agapi-version") or hv.get("x-agapi-version")
        except Exception:
            version = None
        try:
            env = r.json()
        except Exception:   # not AgAPI's envelope (a proxy's error page): AgAPI didn't answer
            env = {"ok": False, "error": {"code": "unreachable", "message": f"HTTP {r.status_code}"}}
    except httpx.TimeoutException as e:
        env = {"ok": False, "error": {"code": "timeout", "message": type(e).__name__}}
    except Exception as e:
        env = {"ok": False, "error": {"code": "unreachable", "message": type(e).__name__}}
    if isinstance(env, dict) and not env.get("ok"):   # row 901: AgAPI's 502 carried its cause and nothing kept it — one line, no contents
        log.warning("[agapi] %s → HTTP %s %s in %d ms%s", op, status, (env.get("error") or {}).get("code"), (time.perf_counter() - t0) * 1000,
                    failed_why(env))
    kind = AH.kind_of(env)
    if kind:
        await AH.note(kind, op, url, key)
    from agapi import measure as MS   # Sasha 275 · S1 measure — observation only (an act's events, as Sasha received them)
    MS.agapi_op(op, body, env, int((time.perf_counter() - t0) * 1000), url, version)
    return env


def key_name(target: str) -> str:
    """Sasha 249 · the key's variable NAME, for a 'not configured' line (never its value)."""
    return ENDPOINTS["live" if target == "live" else "sandbox"][2]


def ctx_mode() -> str:
    """Sasha 249 · the mode of sasha.turn's agapi.v0 Ctx. v0 runs Sasha's OWN engine on Duffel TEST inventory only (travel.token()
    refuses a live token; v0.call refuses any other mode), whatever AgAPI a family is routed to — so it is "test" for every family.
    It is said here so the route is the one place that decides it; any other value would stop every v0 tool (bookings, payments)."""
    return "test"


__all__ = ["acting", "lane", "person_mode", "FAMILIES", "PINNED", "ROUTED", "TEST_AIRLINES", "table", "route", "current", "using", "money_target", "endpoint", "target_for", "client_for",
           "post", "key_name", "ctx_mode"]
