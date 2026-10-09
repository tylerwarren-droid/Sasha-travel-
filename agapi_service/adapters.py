"""CR 69 · THE LIVE-MODE SCAFFOLD: one adapter interface per provider kind, so the engine never calls a provider directly.
  test keys  → the Simulated adapters = today's sandbox behaviour, unchanged (recorded fixtures; messages captured, never sent)
  live keys  → NotConnected: "live provider not connected yet" (mode_not_available) — refused BEFORE anything happens (execute()
               checks OP_PROVIDERS first; NotConnected refuses again if reached). Phase 2 (docs/agapi/engine/phase-2.md) puts Sasha's
               real providers behind these same interfaces and adds each kind to CONNECTED_LIVE. No real provider is called in phase 1.
Kinds: flights · places · venue_ladder · payments · email · whatsapp · calendar."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import config, providers as PV
from .registry import AgapiError
from .store import Store

KINDS = ("flights", "places", "venue_ladder", "payments", "email", "whatsapp", "calendar", "stays")
# phase 2 (CR 70): a kind is connected only on agapi-live (AGAPI_CONNECTED_LIVE) and only once its live adapter passed its tests.
# The sandbox never sets it, so a live key there is always refused. "stays" (priced hotels) has no real provider in Sasha: never connected.
CONNECTED_LIVE: set = set(config.CONNECTED_LIVE) if config.LIVE_SERVICE else set()

# which provider kinds each operation can reach (a live key is refused if any of them isn't connected)
OP_PROVIDERS: Dict[str, Tuple[str, ...]] = {
    "travel.find_flights": ("flights",), "travel.find_stays": ("stays",), "venues.find_venues": ("places",),
    "trip.hold": ("flights", "venue_ladder"), "trip.complete": ("flights", "venue_ladder", "payments"),
    "trip.cancel": ("flights", "venue_ladder"), "approvals.request": ("email", "whatsapp"), "users.register": ("email", "whatsapp"),
    "messages.send_email": ("email",), "messages.send_whatsapp": ("whatsapp",), "messages.replies": ("whatsapp",),
    "calendar.add_event": ("calendar",), "keep.use": ("email", "whatsapp"),
}


# ── the interfaces ─────────────────────────────────────────────────────────────────────────────────────────────────────

class Flights:
    async def search(self, inp: dict, up: PV.Upstream) -> List[dict]: raise NotImplementedError
    async def recheck(self, offer: dict, up: PV.Upstream, passengers: int) -> Tuple[dict, str]: raise NotImplementedError
    async def order(self, offer: dict, travellers: List[dict], up: PV.Upstream) -> Dict[str, Any]: raise NotImplementedError
    async def cancel(self, service: str, act_id: str, up: PV.Upstream) -> Dict[str, Any]: raise NotImplementedError


class Places:
    async def find_stays(self, inp: dict, up: PV.Upstream) -> List[dict]: raise NotImplementedError
    async def find_venues(self, inp: dict, up: PV.Upstream) -> List[dict]: raise NotImplementedError


class VenueLadder:
    async def book(self, kind: str, item: dict, up: PV.Upstream) -> Dict[str, Any]: raise NotImplementedError
    async def cancel(self, service: str, act_id: str, up: PV.Upstream) -> Dict[str, Any]: raise NotImplementedError


class Payments:
    def payment_link(self, token: str) -> str: raise NotImplementedError

    async def link_for(self, store: Store, account: str, act_id: str, token: str, total: dict, label: str) -> str:   # CR 70
        return self.payment_link(token)


class Messenger:
    def deliver(self, store: Store, account: str, end_user: Optional[str], to: str, channel: str, body: str, link: Optional[str]) -> None:
        raise NotImplementedError


class Calendar:
    def publish(self, store: Store, account: str, act_id: str, ics: str, token: str, token_hash: str) -> str: raise NotImplementedError


# ── test mode: today's simulated providers, delegated to exactly as before ─────────────────────────────────────────────

class SimFlights(Flights):
    async def search(self, inp, up): return await PV.find_flights(inp, up)
    async def recheck(self, offer, up, passengers): return await PV.recheck_flight(offer, up, passengers)
    async def order(self, offer, travellers, up): return await PV.order_flight(offer, travellers, up)
    async def cancel(self, service, act_id, up): return await PV.cancel_fixture(service, act_id, up)


class SimPlaces(Places):
    async def find_stays(self, inp, up): return await PV.find_stays(inp, up)
    async def find_venues(self, inp, up): return await PV.find_venues(inp, up)


class SimVenueLadder(VenueLadder):
    async def book(self, kind, item, up): return await PV.book_fixture(kind, item, up)
    async def cancel(self, service, act_id, up): return await PV.cancel_fixture(service, act_id, up)


class SimPayments(Payments):
    def payment_link(self, token): return f"{config.PUBLIC_URL}/pay/{token}"    # the sandbox's own Stripe-test page (no Stripe call)


class SimMessenger(Messenger):
    """Captured in the sandbox's outbox (sandbox.messages), never sent."""

    def deliver(self, store, account, end_user, to, channel, body, link):
        from .store import ts
        store.x("insert into messages (account, end_user, to_, channel, sent_at, body, approval_link) values (?, ?, ?, ?, ?, ?, ?)",
                account, end_user, to, channel, ts(), body, link)


class SimCalendar(Calendar):
    def publish(self, store, account, act_id, ics, token, token_hash):
        from .store import ts
        store.x("insert into calendar_files (token_hash, account, act_id, ics, created_at) values (?, ?, ?, ?, ?)", token_hash, account, act_id, ics, ts())
        return f"{config.PUBLIC_URL}/ics/{token}.ics"


# ── live mode, phase 1: nothing is connected ───────────────────────────────────────────────────────────────────────────

class NotConnected:
    def __init__(self, kind: str):
        self.kind = kind

    def __getattr__(self, name):
        raise not_connected(self.kind)


def not_connected(kind: str) -> AgapiError:
    return AgapiError("mode_not_available", f"Live provider not connected yet ({kind}). Live keys work once phase 2 connects it.",
                      {"provider": kind, "phase": 2})


_SIM = {"flights": SimFlights(), "places": SimPlaces(), "stays": SimPlaces(), "venue_ladder": SimVenueLadder(), "payments": SimPayments(),
        "email": SimMessenger(), "whatsapp": SimMessenger(), "calendar": SimCalendar()}
_LIVE: Dict[str, Any] = {}           # phase 2: filled by adapters_live (each kind once its adapter exists)


def _load_live() -> None:
    try:
        from . import adapters_live
        _LIVE.update(adapters_live.ADAPTERS)
    except ImportError:
        pass


def get(kind: str, mode: str):
    if kind not in KINDS:
        raise ValueError(kind)
    if mode == "test":
        return _SIM[kind]
    if not _LIVE:
        _load_live()
    return _LIVE[kind] if kind in CONNECTED_LIVE and kind in _LIVE else NotConnected(kind)


def messenger(channel: str, mode: str) -> Messenger:
    """Email goes through the email adapter; SMS and WhatsApp through the WhatsApp/SMS adapter (one provider in Sasha: Twilio)."""
    return get("email" if channel == "email" else "whatsapp", mode)


_ITEM_KIND = {"flight": "flights", "venue": "venue_ladder", "stay": "stays"}


def kinds_for(op_name: str, inp: Optional[dict] = None, store: Optional[Store] = None, account: Optional[str] = None) -> Tuple[str, ...]:
    """CR 70 · item-aware: a flight-only hold needs flights, not the venue ladder too. trip.complete/cancel read the hold/act's items;
    anything unknown falls back to every kind the operation can reach."""
    full = OP_PROVIDERS.get(op_name, ())
    try:
        items = None
        if op_name == "users.register":                     # a code is sent only to destinations given
            return tuple(sorted({"email" if d.get("channel") == "email" else "whatsapp" for d in (inp or {}).get("destinations") or []})) if inp is not None else full
        if op_name == "trip.hold":
            items = [i.get("kind") for i in (inp or {}).get("items") or []]
        elif op_name == "trip.complete" and store is not None:
            from .store import loads
            h = store.one("select items from holds where account = ? and id = ?", account, (inp or {}).get("hold_id"))
            held = loads(h["items"]) if h else None
            items = [i.get("kind") for i in (held.get("items") if isinstance(held, dict) else held) or []] if held else None
        if items:
            ks = tuple(sorted({_ITEM_KIND.get(k, "venue_ladder") for k in items}))
            return ks + (("payments",) if op_name == "trip.complete" else ())
    except Exception:
        pass
    return full


def require_live(op_name: str, inp: Optional[dict] = None, store: Optional[Store] = None, account: Optional[str] = None) -> None:
    """A live key: refused before anything happens if the operation can reach a provider that isn't connected."""
    for kind in kinds_for(op_name, inp, store, account):
        if kind not in CONNECTED_LIVE:
            raise not_connected(kind)


def status() -> Dict[str, str]:
    return {k: ("live connected" if k in CONNECTED_LIVE else "test: simulated · live: not connected yet") for k in KINDS}
