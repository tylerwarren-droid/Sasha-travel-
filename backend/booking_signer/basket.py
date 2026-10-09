"""Sasha 198 · R2 · THE TRIP BASKET — one row per thing in a trip, whatever its state (docs/sasha/trip-basket-design.md §2, §5).

    suggested → chosen → pending_payment → booked | failed | cancelled

Every write names its AgAPI role, and only that role may make it:
    MAGELLAN  search                 suggest()             offers shown, the plan's stays
    SHERLOCK  details / validation   refresh()             snapshot, expiry, price re-checked; a re-search keeps the choice
    AUSTEN    booking after the yes  choose(), hold()      the guest's pick; the Stripe session the yes created
    PACIOLI   proof and truth        booked(), failed(), cancelled(), event()
                                     — the ONLY writer of a booked/paid status line; the model never writes one.

Persisted in public.trip_basket_items / basket_events (033_trip_basket.sql) — nothing about a quote or a choice lives in memory.
Every read and write is scoped to the account (the service role bypasses RLS, so the check is here). Never raises to a caller
that only reads; writes raise BasketError with the reason (the caller says it — never a fake success).
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

MAGELLAN, SHERLOCK, AUSTEN, PACIOLI = "Magellan", "Sherlock", "Austen", "Pacioli"
LIVE = ("suggested", "chosen", "pending_payment", "booked")
STORE_RUN = None   # tests set it; otherwise the ladder store's runner


class BasketError(Exception):
    pass


def _run():
    if STORE_RUN is not None:
        return STORE_RUN
    from . import plan_store as PS
    return PS._run()


def _row(r) -> Dict[str, Any]:
    d = dict(r)
    for k, v in list(d.items()):
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
        elif k == "snapshot" and isinstance(v, str):
            d[k] = json.loads(v)
        elif hasattr(v, "as_tuple"):   # Decimal
            d[k] = float(v)
    return d


async def _go(fn):
    run = _run()
    if run is None:
        raise BasketError("no database")
    return await run(fn)


def _log(role: str, what: str, *args) -> None:
    log.info("[basket] %s · " + what, role, *args)


# ── reads ────────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def items(account: str, trip_id: str, states=LIVE) -> List[Dict[str, Any]]:
    async def fn(conn):
        return await conn.fetch("select * from trip_basket_items where account_id = $1 and trip_id = $2 and state = any($3::text[]) "
                                "order by kind, coalesce(day, '9999-12-31'), created_at", uuid.UUID(account), uuid.UUID(trip_id), list(states))
    try:
        return [_row(r) for r in await _go(fn)]
    except Exception as e:
        log.warning("[basket] not read: %s: %s", type(e).__name__, e)
        return []


async def item(account: str, item_id: str) -> Optional[Dict[str, Any]]:
    async def fn(conn):
        return await conn.fetchrow("select * from trip_basket_items where account_id = $1 and id = $2", uuid.UUID(account), uuid.UUID(item_id))
    r = await _go(fn)
    return _row(r) if r else None


async def by_ref(account: str, trip_id: str, provider_ref: str) -> Optional[Dict[str, Any]]:
    """The live item a provider id names (a shown offer → its basket row)."""
    async def fn(conn):
        return await conn.fetchrow("select * from trip_basket_items where account_id = $1 and trip_id = $2 and provider_ref = $3 "
                                   "and state = any($4::text[]) order by created_at desc limit 1",
                                   uuid.UUID(account), uuid.UUID(trip_id), provider_ref, list(LIVE))
    r = await _go(fn)
    return _row(r) if r else None


async def by_session(session_id: str) -> List[Dict[str, Any]]:
    async def fn(conn):
        return await conn.fetch("select * from trip_basket_items where paid_session = $1 order by kind, created_at", session_id)
    return [_row(r) for r in await _go(fn)]


def to_book(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What "book it" books: every chosen item, and the stays the guest kept (a suggested stay is in the plan until removed)."""
    return [r for r in rows if r["state"] == "chosen" or (r["kind"] == "stay" and r["state"] == "suggested")]


def total(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """ONE total over what would be booked — said with where each price comes from (an estimate is never called a price)."""
    rs = to_book(rows)
    cur = {r.get("price_currency") for r in rs if r.get("price_amount") is not None}
    return {"amount": round(sum(float(r["price_amount"]) for r in rs if r.get("price_amount") is not None), 2),
            "currency": cur.pop() if len(cur) == 1 else ("mixed" if cur else None),
            "unpriced": [r["id"] for r in rs if r.get("price_amount") is None],
            "sources": sorted({r.get("price_source") or "unpriced" for r in rs}), "count": len(rs)}


# ── Magellan · search ────────────────────────────────────────────────────────────────────────────────────────────────────

async def suggest(account: str, trip_id: str, kind: str, found: List[Dict[str, Any]], *, slice_key: Optional[str] = None,
                  replace: bool = True) -> List[str]:
    """What a search found, as `suggested` rows. A new search of the same slice (or the same kind, for stays) replaces the
    previous SUGGESTIONS only — a chosen, held or booked row is never touched by a search."""
    if kind not in ("flight", "stay", "venue"):
        raise BasketError(f"unknown kind {kind}")

    async def fn(conn):
        async with conn.transaction():
            if replace:
                await conn.execute("delete from trip_basket_items where account_id = $1 and trip_id = $2 and kind = $3 and state = 'suggested' "
                                   "and coalesce(slice_key, '') = coalesce($4, '')", uuid.UUID(account), uuid.UUID(trip_id), kind, slice_key)
            ids = []
            for f in found:
                ids.append(await conn.fetchval(
                    "insert into trip_basket_items (trip_id, account_id, kind, state, slice_key, day, starts_at, ends_at, party, provider, "
                    "provider_ref, offer_request_id, snapshot, expires_at, price_amount, price_currency, price_source, is_test) "
                    "values ($1,$2,$3,'suggested',$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13,$14,$15,$16,$17) returning id",
                    uuid.UUID(trip_id), uuid.UUID(account), kind, slice_key or f.get("slice_key"), _d(f.get("day")), _t(f.get("starts_at")),
                    _t(f.get("ends_at")), f.get("party"), f["provider"], f.get("provider_ref"), f.get("offer_request_id"),
                    json.dumps(f.get("snapshot") or {}), _t(f.get("expires_at")), f.get("price_amount"), f.get("price_currency"),
                    f.get("price_source"), f.get("is_test", True)))
            return [str(i) for i in ids]
    ids = await _go(fn)
    _log(MAGELLAN, "%d %s suggested on trip %s", len(ids), kind, trip_id[:8])
    return ids


def _d(v):
    return date.fromisoformat(v) if isinstance(v, str) and v else v


def _t(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if isinstance(v, str) and v else v


# ── Sherlock · details and validation ────────────────────────────────────────────────────────────────────────────────────

async def refresh(account: str, item_id: str, *, provider_ref: Optional[str] = None, snapshot: Optional[dict] = None,
                  expires_at=None, price_amount=None, price_currency: Optional[str] = None) -> Dict[str, Any]:
    """The item re-checked at its source: still there, this price, this expiry — or the same flight found again (a new offer
    id, the guest's choice kept). Never changes the state."""
    async def fn(conn):
        return await conn.fetchrow(
            "update trip_basket_items set provider_ref = coalesce($3, provider_ref), snapshot = coalesce($4::jsonb, snapshot), "
            "expires_at = coalesce($5, expires_at), price_amount = coalesce($6, price_amount), price_currency = coalesce($7, price_currency), "
            "updated_at = now() where account_id = $1 and id = $2 and state in ('suggested','chosen') returning *",
            uuid.UUID(account), uuid.UUID(item_id), provider_ref, json.dumps(snapshot) if snapshot is not None else None,
            _t(expires_at), price_amount, price_currency)
    r = await _go(fn)
    if not r:
        raise BasketError("that item is not in this basket, or is already held or booked")
    _log(SHERLOCK, "item %s re-checked", item_id[:8])
    return _row(r)


# ── Austen · the guest's choice, and the booking after the yes ───────────────────────────────────────────────────────────

async def choose(account: str, item_id: str) -> Dict[str, Any]:
    """The guest's pick. A flight replaces the flight chosen on the same slice (it goes back to suggested) — never a second."""
    async def fn(conn):
        async with conn.transaction():
            r = await conn.fetchrow("select * from trip_basket_items where account_id = $1 and id = $2 for update",
                                    uuid.UUID(account), uuid.UUID(item_id))
            if not r:
                return None
            if r["state"] not in ("suggested", "chosen"):
                return r
            if r["kind"] == "flight":
                await conn.execute("update trip_basket_items set state = 'suggested', updated_at = now() where trip_id = $1 and account_id = $2 "
                                   "and kind = 'flight' and state = 'chosen' and coalesce(slice_key,'') = coalesce($3,'') and id <> $4",
                                   r["trip_id"], r["account_id"], r["slice_key"], r["id"])
            return await conn.fetchrow("update trip_basket_items set state = 'chosen', updated_at = now() where id = $1 returning *", r["id"])
    r = await _go(fn)
    if not r:
        raise BasketError("that item is not in this basket")
    if r["state"] != "chosen":
        raise BasketError(f"that item is already {r['state'].replace('_', ' ')}")
    _log(AUSTEN, "item %s chosen", item_id[:8])
    return _row(r)


async def unchoose_flights(account: str, trip_id: str) -> int:
    """Sasha 202 · a NEW proposal replaces the trip's flights: any chosen flight (another leg, another origin) goes back to
    suggested — never two outbound flights booked. Held or booked rows are never touched."""
    async def fn(conn):
        return await conn.execute("update trip_basket_items set state = 'suggested', updated_at = now() where account_id = $1 "
                                  "and trip_id = $2 and kind = 'flight' and state = 'chosen'", uuid.UUID(account), uuid.UUID(trip_id))
    n = int(str(await _go(fn)).split()[-1])
    if n:
        _log(MAGELLAN, "%d earlier chosen flight(s) set back to suggested on trip %s (a new proposal)", n, trip_id[:8])
    return n


async def hold(account: str, trip_id: str, session_id: str) -> List[Dict[str, Any]]:
    """The yes: everything "book it" books moves to pending_payment, carrying the Stripe session (in the rows, not in memory)."""
    rows = to_book(await items(account, trip_id, ("suggested", "chosen")))
    if not rows:
        raise BasketError("nothing in this trip to book")

    async def fn(conn):
        return await conn.fetch("update trip_basket_items set state = 'pending_payment', paid_session = $3, updated_at = now() "
                                "where account_id = $1 and id = any($2::uuid[]) and state in ('suggested','chosen') returning *",
                                uuid.UUID(account), [uuid.UUID(r["id"]) for r in rows], session_id)
    out = [_row(r) for r in await _go(fn)]
    _log(AUSTEN, "%d item(s) held for payment %s", len(out), session_id[:14])
    return out


async def hold_ids(account: str, trip_id: str, ids: List[str], session_id: str) -> List[Dict[str, Any]]:
    """Sasha 220 · a payment MOVED (here ↔ phone): exactly these items held with the new session — never re-chosen from the basket."""
    async def fn(conn):
        return await conn.fetch("update trip_basket_items set state = 'pending_payment', paid_session = $4, updated_at = now() "
                                "where account_id = $1 and trip_id = $2 and id = any($3::uuid[]) and state in ('suggested','chosen') returning *",
                                uuid.UUID(account), uuid.UUID(trip_id), [uuid.UUID(i) for i in ids], session_id)
    out = [_row(r) for r in await _go(fn)]
    _log(AUSTEN, "%d item(s) moved to payment %s", len(out), session_id[:14])
    return out


async def release(account: str, trip_id: str, session_id: str) -> int:
    """Sasha 215 · a payment that was never offered (its record failed): the items it held go back to chosen."""
    async def fn(conn):
        return await conn.execute("update trip_basket_items set state = 'chosen', paid_session = null, updated_at = now() "
                                  "where account_id = $1 and trip_id = $2 and paid_session = $3 and state = 'pending_payment'",
                                  uuid.UUID(account), uuid.UUID(trip_id), session_id)
    n = int(str(await _go(fn)).split()[-1] or 0)
    _log(AUSTEN, "%d item(s) released from unoffered payment %s", n, session_id[:14])
    return n


async def remove(account: str, item_id: str) -> bool:
    """The ✕: one row, and only one not yet held or booked."""
    async def fn(conn):
        return await conn.execute("delete from trip_basket_items where account_id = $1 and id = $2 and state in ('suggested','chosen')",
                                  uuid.UUID(account), uuid.UUID(item_id))
    return str(await _go(fn)).endswith(" 1")


# ── Pacioli · proof and truth ────────────────────────────────────────────────────────────────────────────────────────────

def status_line(r: Dict[str, Any]) -> str:
    """The words for a booked/failed/cancelled item, built from the record alone — never from the model."""
    s, test = r.get("snapshot") or {}, " (TEST)" if r.get("is_test") else ""
    what = (f"✈️ {s.get('owner') or ''} {s.get('flights') or ''} {s.get('from') or ''}→{s.get('to') or ''}" if r["kind"] == "flight"
            else f"🏨 {s.get('name') or s.get('hotel') or 'Hotel'}" if r["kind"] == "stay" else f"📍 {s.get('name') or 'Booking'}")
    when = f" · {r['day']}" if r.get("day") else ""
    what = " ".join(what.split())
    if r["state"] == "booked":
        return f"{what}{when} · booked · ref {r.get('booking_reference') or '—'}{test}"
    if r["state"] == "failed":
        return f"{what}{when} · NOT booked: {r.get('failed_why') or 'refused'}{test}"
    if r["state"] == "cancelled":
        return f"{what}{when} · cancelled{test}"
    return f"{what}{when} · {r['state'].replace('_', ' ')}"


async def _settle(account: str, item_id: str, state: str, **f) -> Dict[str, Any]:
    async def fn(conn):
        async with conn.transaction():
            r = await conn.fetchrow("update trip_basket_items set state = $3, booking_reference = coalesce($4, booking_reference), "
                                    "order_id = coalesce($5, order_id), failed_why = $6, trip_item_id = coalesce($7, trip_item_id), "
                                    "updated_at = now() where account_id = $1 and id = $2 returning *",
                                    uuid.UUID(account), uuid.UUID(item_id), state, f.get("booking_reference"), f.get("order_id"),
                                    f.get("failed_why"), uuid.UUID(f["trip_item_id"]) if f.get("trip_item_id") else None)
            if not r:
                return None
            line = status_line(_row(r))
            return await conn.fetchrow("update trip_basket_items set status_line = $2 where id = $1 returning *", r["id"], line)
    r = await _go(fn)
    if not r:
        raise BasketError("that item is not in this basket")
    _log(PACIOLI, "item %s %s", item_id[:8], state)
    return _row(r)


async def booked(account: str, item_id: str, *, booking_reference: str, order_id: Optional[str] = None,
                 trip_item_id: Optional[str] = None) -> Dict[str, Any]:
    return await _settle(account, item_id, "booked", booking_reference=booking_reference, order_id=order_id, trip_item_id=trip_item_id)


async def failed(account: str, item_id: str, why: str) -> Dict[str, Any]:
    return await _settle(account, item_id, "failed", failed_why=why[:300])


async def cancelled(account: str, item_id: str) -> Dict[str, Any]:
    return await _settle(account, item_id, "cancelled")


async def event(source: str, event_id: str, event_type: str, payload: Any, *, verified: bool, item_id: Optional[str] = None) -> bool:
    """Every provider event, once: True when new, False when it was already recorded (a redelivery)."""
    raw = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload, sort_keys=True, default=str).encode()

    async def fn(conn):
        return await conn.fetchval("insert into basket_events (source, event_id, event_type, item_id, payload_sha256, verified) "
                                   "values ($1,$2,$3,$4,$5,$6) on conflict (source, event_id) do nothing returning id",
                                   source, event_id, event_type, uuid.UUID(item_id) if item_id else None,
                                   hashlib.sha256(raw).hexdigest(), verified)
    new = await _go(fn)
    _log(PACIOLI, "event %s %s %s", source, event_type, "recorded" if new else "already recorded")
    return new is not None


async def unclaim(source: str, event_id: str) -> None:
    """Sasha 215 · a claim taken for an act that was then refused BEFORE anything was sent (no yes, the API said no): released,
    so the person's next yes can act. A claim whose act ran, or may have run, is never released."""
    async def fn(conn):
        await conn.execute("delete from basket_events where source = $1 and event_id = $2 and event_type = 'claim'", source, event_id)
    await _go(fn)


async def count_events(source: str, prefix: str) -> int:
    """Sasha 215 · how many events of a source start with this id (the agent's turns per account per day)."""
    async def fn(conn):
        return await conn.fetchval("select count(*) from basket_events where source = $1 and starts_with(event_id, $2)", source, prefix)
    return int(await _go(fn) or 0)


# ── R3 · the plan's stays in the basket, and the view rendered from it ─────────────────────────────────────────────────────

ON = None   # Sasha 198 R10 · the basket is THE path (the SASHA_BASKET switch is gone); a test may set False to read a plan alone


def on() -> bool:
    return ON is not False


async def sync_stays(account: str, trip_id: str, days: List[dict], start: Optional[date], party: Optional[int]) -> List[str]:
    """Magellan: the plan's hotels as `suggested` stays — one per run of nights at the same hotel, priced as the plan's ESTIMATE
    (said so). A revision replaces the suggestions; a stay already chosen, held or booked is kept and not suggested twice."""
    if not start or not days:
        return []
    import os
    from datetime import timedelta
    usd_eur = float(os.getenv("SASHA_USD_EUR", "0.92") or 0.92)
    runs: List[dict] = []
    for i, d in enumerate(days[:-1] if len(days) > 1 else days):   # the last day is the way home: no night
        h = d.get("hotel")
        name = (h.get("name") if isinstance(h, dict) else h) or ""
        if not name:
            if runs:
                runs[-1]["nights"] += 1   # a day without its own hotel continues the stay (as the panel shows it)
            continue
        on_day = str(d.get("date") or "")[:10] or (start + timedelta(days=i)).isoformat()
        rate = float((h or {}).get("price_from") or 0) if isinstance(h, dict) else 0.0
        if runs and runs[-1]["name"] == name:
            runs[-1]["nights"] += 1
        else:
            runs.append({"name": name, "city": d.get("city") or "", "day": on_day, "nights": 1, "rate": rate,
                         "est": bool(isinstance(h, dict) and h.get("est"))})
    kept = {(r["snapshot"].get("name"), r["day"]) for r in await items(account, trip_id, ("chosen", "pending_payment", "booked"))
            if r["kind"] == "stay"}
    found = []
    for r in runs:
        if (r["name"], r["day"]) in kept:
            continue
        end = (date.fromisoformat(r["day"]) + timedelta(days=r["nights"])).isoformat()
        found.append({"provider": "plan", "day": r["day"], "party": party,
                      "starts_at": r["day"] + "T15:00:00+00:00", "ends_at": end + "T11:00:00+00:00",
                      "price_amount": round(r["rate"] * r["nights"] * usd_eur, 2) if r["rate"] else None,
                      "price_currency": "EUR" if r["rate"] else None, "price_source": "estimate" if r["rate"] else None,
                      "snapshot": {"name": r["name"], "city": r["city"], "nights": r["nights"], "checkout": end,
                                   **({"est": True} if r.get("est") else {})}})
    return await suggest(account, trip_id, "stay", found)


def words(r: Dict[str, Any]) -> str:
    """An item's state in the guest's words. Booked / failed / cancelled are Pacioli's line, never composed here."""
    if r["state"] in ("booked", "failed", "cancelled"):
        return r.get("status_line") or status_line(r)
    return {"suggested": "in your plan — not booked", "chosen": "chosen — not booked yet",
            "pending_payment": "waiting for your payment"}.get(r["state"], r["state"])


def overlay(plan: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The merged plan with the basket on it: each day's `stay` (the stay covering that night), and the trip's flights."""
    stays = [r for r in rows if r["kind"] == "stay"]
    for d in plan.get("days") or []:
        on_day = d.get("date")
        hit = next((r for r in stays if on_day and r.get("day") and r["day"] <= on_day < (r["snapshot"].get("checkout") or r["day"])), None)
        if hit:
            d["stay"] = {"id": hit["id"], "name": hit["snapshot"].get("name"), "state": hit["state"], "words": words(hit),
                         "first_night": hit["day"] == on_day, "price_eur": hit.get("price_amount"), "price_source": hit.get("price_source")}
    plan["basket"] = {"flights": [{"id": r["id"], "state": r["state"], "words": words(r), "day": r.get("day"), **{
        k: r["snapshot"].get(k) for k in ("owner", "flights", "from", "to", "dep")}} for r in rows
        if r["kind"] == "flight" and r["state"] != "suggested"], "total": total(rows)}
    return plan


__all__ = ["MAGELLAN", "SHERLOCK", "AUSTEN", "PACIOLI", "BasketError", "items", "item", "by_ref", "by_session", "to_book", "total",
           "suggest", "refresh", "choose", "unchoose_flights", "hold", "remove", "status_line", "booked", "failed", "cancelled", "event", "on", "sync_stays", "words", "overlay"]
