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


HELD = ("pending_payment", "booked")   # Sasha 249 · rows already paid for (or being paid): still the trip's, still in its total


def counted(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sasha 249 · the rows the trip's total counts: what "book it" would book, AND what is held or booked already — so the Trip tab
    keeps the same figure after payment (before, the rows left to_book() and the tab fell back to the planner's $ estimate)."""
    return to_book([r for r in rows if r.get("state") in ("suggested", "chosen")]) + [r for r in rows if r.get("state") in HELD]


def eur_of(r: Dict[str, Any]) -> Optional[float]:
    """Sasha 249 · a row's price in euros — fx.py's one dated rate for a row stored in another currency; None when unpriced or
    there's no rate (never a guess). Rows are stored in euros since 249 (converted at ingestion); this keeps an older row honest."""
    if r.get("price_amount") is None:
        return None
    from . import fx as FX
    return FX.to_eur(r["price_amount"], r.get("price_currency") or "EUR")


def total(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """ONE total over what would be booked — said with where each price comes from (an estimate is never called a price).
    Sasha 249 · in EUROS always (fx.py's one rate; a price with no rate is `unpriced`, never added in its own currency), and it
    counts held / booked rows too (counted()) — the same figure before and after payment."""
    rs = counted(rows)
    eur = [(r, eur_of(r)) for r in rs]
    priced = [e for _, e in eur if e is not None]
    return {"amount": round(sum(priced), 2), "currency": "EUR" if priced else None,
            "unpriced": [r.get("id") for r, e in eur if e is None],
            "sources": sorted({r.get("price_source") or "unpriced" for r in rs}), "count": len(rs)}


def breakdown(rows: List[Dict[str, Any]], amount: float) -> Dict[str, Any]:
    """Sasha 212 · ONE TOTAL, its parts on the card only: the flights (quoted) and the stays (an estimate or a test rate).
    Sasha 249 · moved here from agapi/v0 (it re-exports it) so the Trip tab and the chat build it from the same rows, in euros."""
    rs = counted(rows)
    fl = round(sum(eur_of(r) or 0 for r in rs if r["kind"] == "flight"), 2)
    st = round(sum(eur_of(r) or 0 for r in rs if r["kind"] == "stay"), 2)
    srcs = {r.get("price_source") for r in rs if r["kind"] == "stay"}
    return {"total_eur": amount, "flights_eur": fl, "flights_are": "quoted", "stays_eur": st,
            "stays_are": "estimates" if "estimate" in srcs else "test rate" if "placeholder" in srcs else "quoted"}


def _party_of(plan: Optional[Dict[str, Any]], rows: List[Dict[str, Any]]) -> Optional[int]:
    """Sasha 249 · ONE PARTY: the plan's (how many they said), else its basket rows', else None — the caller ASKS; never a silent 1 or 2."""
    pl = (plan or {}).get("plan") if isinstance((plan or {}).get("plan"), dict) else (plan or {})
    for v in (pl.get("party"), pl.get("travellers"), pl.get("travelers")):
        try:
            if v is not None and 1 <= int(v) <= 9:
                return int(v)
        except (TypeError, ValueError):
            continue
    parties = [int(r["party"]) for r in rows if str(r.get("party") or "").isdigit() and 1 <= int(r["party"]) <= 9]
    return max(parties) if parties else None


def _what(r: Dict[str, Any]) -> str:
    s = r.get("snapshot") or {}
    if r.get("kind") == "flight":
        return " ".join(str(x) for x in (s.get("owner"), s.get("flights"), f"{s.get('from') or ''}→{s.get('to') or ''}") if x).strip()
    if r.get("kind") == "stay":
        return f"{s.get('name') or 'Stay'}" + (f", {s['nights']} night{'s' if s['nights'] != 1 else ''}" if s.get("nights") else "")
    return str(s.get("name") or r.get("kind") or "")


def figures_of(rows: List[Dict[str, Any]], trip_id: Optional[str], plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Sasha 249 · THE TRIP'S FIGURES, pure (no read, no write, no re-price): the one total the chat, the Trip tab and the read-back
    all say — {total_eur, to_pay_eur, lines, party, currency: "EUR", estimate_lines, unpriced, trip_id, breakdown}. `to_pay_eur` is
    what a yes would pay now (the read-back's figure); it equals total_eur until something is paid."""
    rs = counted(rows)
    t = total(rows)
    pay = total([r for r in rows if r.get("state") in ("suggested", "chosen")])
    lines = []
    for r in rs:
        e = eur_of(r)
        line = {"id": r.get("id"), "kind": r.get("kind"), "state": r.get("state"), "what": _what(r), "day": r.get("day"),
                "eur": e, "source": r.get("price_source") or ("unpriced" if e is None else None)}
        if e is not None and (r.get("price_currency") or "EUR").upper() != "EUR":
            from . import fx as FX
            line["fx"] = FX.stamp(r.get("price_currency"))
        fx_in = (r.get("snapshot") or {}).get("fx")
        if isinstance(fx_in, dict):   # converted at ingestion: the airline's own currency, said beside the euros
            line["fx"] = fx_in
        lines.append(line)
    party = _party_of(plan, rows)
    # total_eur None: nothing priced yet (never "€0")
    return {"total_eur": t["amount"] if t["currency"] else None, "to_pay_eur": pay["amount"], "currency": "EUR", "lines": lines,
            "estimate_lines": [l for l in lines if l["source"] == "estimate"], "unpriced": t["unpriced"],
            "party": party, **({} if party else {"ask_party": "how many are travelling isn't on the trip — ask once"}),
            "trip_id": trip_id, "breakdown": breakdown(rows, t["amount"])}


async def trip_figures(account: str, trip_id: Optional[str] = None, plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Sasha 249 · ONE TOTAL: the trip's figures from the basket as its rows stand — READ ONLY (it never re-searches, re-prices or
    chooses: that is refresh(), and only hold_booking calls it). `plan` the plan store's row when the caller has it; else the
    account's latest plan (or the trip named). No trip → figures with no lines."""
    if plan is None:
        from . import plan_store as PS
        plan = await (PS.by_id(account, trip_id) if trip_id else PS.latest(account))
    trip_id = trip_id or (plan or {}).get("trip_id")
    if not trip_id:
        return figures_of([], None, plan)
    rows = await items(account, trip_id, ("suggested", "chosen") + HELD)
    return figures_of(rows, trip_id, plan)


# ── Magellan · search ────────────────────────────────────────────────────────────────────────────────────────────────────

async def suggest(account: str, trip_id: str, kind: str, found: List[Dict[str, Any]], *, slice_key: Optional[str] = None,
                  replace: bool = True) -> List[str]:
    """What a search found, as `suggested` rows. A new search of the same slice (or the same kind, for stays) replaces the
    previous SUGGESTIONS only — a chosen, held or booked row is never touched by a search."""
    if kind not in ("flight", "stay", "venue"):
        raise BasketError(f"unknown kind {kind}")
    if kind == "flight":   # Sasha 249 · OFFERED == BOOKABLE: a flight search APPENDS — what she showed before stays choosable
        found = [ingest_flight(f) for f in found]
        found = [f for f in found if f is not None]

    async def fn(conn):
        async with conn.transaction():
            if replace and kind == "flight":   # Sasha 249 · never a delete of what was just shown: the older options are marked
                await _supersede(conn, account, trip_id, slice_key, [f.get("provider_ref") for f in found])   # superseded
            elif replace:
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


SUPERSEDED_KEEP_S = 3600   # Sasha 249 · a superseded option stays choosable this long (never deleted in the turn that superseded it)


def card_eur(c: Dict[str, Any]) -> Optional[float]:
    """Sasha 249 · a flight card's price in euros: its own when in EUR, else fx.py's one dated rate; None when there's no rate."""
    if c.get("price_eur") is not None:
        try:
            return round(float(c["price_eur"]), 2)
        except (TypeError, ValueError):
            pass
    from . import fx as FX
    return FX.to_eur(c.get("amount"), c.get("currency") or "EUR")


def in_eur(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sasha 249 · CONVERTED AT INGESTION: every offer priced in euros (a non-EUR offer converted at the one dated rate and said so
    in its `fx`), never dropped to the planner's $ estimate. The airline's own amount and currency stay on the card — the order and
    the re-check are made in them. An offer in a currency with no rate can't join a euro trip: left out."""
    out = []
    from . import fx as FX
    for c in cards or []:
        e = card_eur(c)
        if e is None:
            continue
        cur = (c.get("currency") or "EUR").upper()
        out.append({**c, "price_eur": e, **({"fx": {**FX.stamp(cur), "amount": c.get("amount")}} if cur != "EUR" else {})})
    return out


def ingest_flight(f: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sasha 249 · a flight row on its way into the basket, in euros: price_amount / price_currency EUR, the airline's own price kept
    in the snapshot's `fx`. → None when it can't be priced in euros (no rate)."""
    cur = (f.get("price_currency") or "EUR").upper()
    if f.get("price_amount") is None or cur == "EUR":
        return f
    from . import fx as FX
    e = FX.to_eur(f["price_amount"], cur)
    if e is None:
        return None
    snap = dict(f.get("snapshot") or {})
    snap.setdefault("fx", {**FX.stamp(cur), "amount": f["price_amount"]})
    snap["price_eur"] = e
    return {**f, "price_amount": e, "price_currency": "EUR", "snapshot": snap}


def supersede_plan(existing: List[Dict[str, Any]], new_refs: List[Optional[str]], now: datetime) -> Dict[str, List[str]]:
    """Sasha 249 · what a new search of a slice does to its earlier SUGGESTED rows, decided in plain Python: the same offer shown
    again → its old row goes (the new row is the same option); a row superseded over SUPERSEDED_KEEP_S ago (an earlier turn) →
    goes; every other row stays, marked superseded now. Nothing just shown is ever deleted."""
    refs = {r for r in new_refs if r}
    drop, mark = [], []
    for r in existing:
        snap = r.get("snapshot") or {}
        if isinstance(snap, str):
            snap = json.loads(snap)
        if r.get("provider_ref") and r["provider_ref"] in refs:
            drop.append(str(r["id"]))
            continue
        at = snap.get("superseded_at")
        if at:
            try:
                old = (now - datetime.fromisoformat(str(at).replace("Z", "+00:00"))).total_seconds() > SUPERSEDED_KEEP_S
            except ValueError:
                old = False
            if old:
                drop.append(str(r["id"]))
            continue
        mark.append(str(r["id"]))
    return {"drop": drop, "mark": mark}


async def _supersede(conn, account: str, trip_id: str, slice_key: Optional[str], new_refs: List[Optional[str]]) -> None:
    from datetime import timezone
    rows = await conn.fetch("select id, provider_ref, snapshot from trip_basket_items where account_id = $1 and trip_id = $2 "
                            "and kind = 'flight' and state = 'suggested' and coalesce(slice_key, '') = coalesce($3, '')",
                            uuid.UUID(account), uuid.UUID(trip_id), slice_key)
    now = datetime.now(timezone.utc)
    plan = supersede_plan([dict(r) for r in rows], new_refs, now)
    if plan["drop"]:
        await conn.execute("delete from trip_basket_items where account_id = $1 and id = any($2::uuid[]) and state = 'suggested'",
                           uuid.UUID(account), [uuid.UUID(i) for i in plan["drop"]])
    if plan["mark"]:
        await conn.execute("update trip_basket_items set snapshot = snapshot || jsonb_build_object('superseded_at', $3::text), "
                           "updated_at = now() where account_id = $1 and id = any($2::uuid[]) and state = 'suggested'",
                           uuid.UUID(account), [uuid.UUID(i) for i in plan["mark"]], now.isoformat())


def superseded(r: Dict[str, Any]) -> bool:
    return bool((r.get("snapshot") or {}).get("superseded_at"))


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


async def cancel_held(account: str, trip_id: str, session_id: str) -> int:
    """Sasha 221b · a payment SUPERSEDED by a new read-back (its Stripe session already expired): the items it held are cancelled —
    never paid, never booked, and never back in the read-back."""
    async def fn(conn):
        return await conn.execute("update trip_basket_items set state = 'cancelled', paid_session = null, updated_at = now() "
                                  "where account_id = $1 and trip_id = $2 and paid_session = $3 and state = 'pending_payment'",
                                  uuid.UUID(account), uuid.UUID(trip_id), session_id)
    n = int(str(await _go(fn)).split()[-1] or 0)
    _log(AUSTEN, "%d item(s) cancelled with superseded payment %s", n, session_id[:14])
    return n


async def drop_planned(account: str, trip_id: str) -> int:
    """Sasha 246 · CANCEL A PLANNED TRIP (read back, never paid): its suggested / chosen items cancelled — never held, never booked;
    a held or booked item is untouched."""
    async def fn(conn):
        return await conn.execute("update trip_basket_items set state = 'cancelled', updated_at = now() "
                                  "where account_id = $1 and trip_id = $2 and state in ('suggested', 'chosen')",
                                  uuid.UUID(account), uuid.UUID(trip_id))
    n = int(str(await _go(fn)).split()[-1] or 0)
    _log(AUSTEN, "%d planned item(s) dropped from trip %s", n, trip_id[:8])
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


async def add_to_record(account: str, item_id: str, extra: Dict[str, Any]) -> bool:
    """Sasha 235 · PACIOLI · facts added to a booked item's record (its snapshot), e.g. the loyalty programme it was booked with —
    the number's MASK only, never the number (that goes to the provider, not into this table)."""
    async def fn(conn):   # read, merge, write back — the snapshot is written as refresh() writes it (json.dumps; _row reads both shapes)
        async with conn.transaction():
            cur = await conn.fetchval("select snapshot from trip_basket_items where account_id = $1 and id = $2 for update",
                                      uuid.UUID(account), uuid.UUID(item_id))
            if cur is None and not await conn.fetchval("select 1 from trip_basket_items where account_id = $1 and id = $2",
                                                       uuid.UUID(account), uuid.UUID(item_id)):
                return None
            snap = json.loads(cur) if isinstance(cur, str) else dict(cur or {})
            return await conn.fetchval("update trip_basket_items set snapshot = $3::jsonb, updated_at = now() where account_id = $1 and id = $2 "
                                       "returning id", uuid.UUID(account), uuid.UUID(item_id), json.dumps({**snap, **extra}))
    try:
        ok = bool(await _go(fn))
    except Exception as e:
        _log(PACIOLI, "item %s record not added (%s)", item_id[:8], type(e).__name__)
        return False
    _log(PACIOLI, "item %s record %s", item_id[:8], "added" if ok else "not found")
    return ok


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
    from datetime import timedelta
    from . import fx as FX
    usd_eur = FX.rate("USD") or 0.0   # Sasha 249 · ONE RATE (fx.py, dated) — the plan's hotel estimates are in USD
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
    stays = sorted([r for r in rows if r["kind"] == "stay"], key=lambda r: r["state"] not in DONE)   # Sasha 230 · a booked stay wins its night
    for d in plan.get("days") or []:
        on_day = d.get("date")
        hit = next((r for r in stays if on_day and r.get("day") and r["day"] <= on_day < (r["snapshot"].get("checkout") or r["day"])), None)
        if hit:
            d["stay"] = {"id": hit["id"], "name": hit["snapshot"].get("name"), "state": hit["state"], "words": words(hit),
                         "first_night": hit["day"] == on_day, "price_eur": hit.get("price_amount"), "price_source": hit.get("price_source")}
    plan["basket"] = {"flights": [{"id": r["id"], "state": r["state"], "words": words(r), "day": r.get("day"), **{
        k: r["snapshot"].get(k) for k in ("owner", "flights", "from", "to", "dep")}} for r in shown_flights(rows)], "total": total(rows)}
    if not plan.get("party"):   # Sasha 246 · the Trip tab's TRAVELLERS: a plan saved without its party takes its basket's (the rows carry it)
        parties = [int(r["party"]) for r in rows if str(r.get("party") or "").isdigit() and int(r["party"]) >= 1]
        if parties:
            plan["party"] = max(parties)
    return plan


DONE = ("booked", "pending_payment")


def _leg(r: Dict[str, Any]) -> str:
    return str(r.get("slice_key") or "").split(":", 1)[0] or "?"


def shown_flights(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sasha 230 · the Trip board's flights: once a leg is booked (or being paid for), ONLY that — the options chosen before it
    are not shown beside it (found live in 228: easyJet "chosen" next to the booked Iberia, both ways). Before any booking, as before."""
    flights = [r for r in rows if r["kind"] == "flight" and r["state"] != "suggested"]
    done = {_leg(r) for r in flights if r["state"] in DONE}
    return [r for r in flights if r["state"] in DONE or r["state"] in ("failed", "cancelled") or _leg(r) not in done]


__all__ = ["MAGELLAN", "SHERLOCK", "AUSTEN", "PACIOLI", "BasketError", "items", "item", "by_ref", "by_session", "to_book", "total",
           "suggest", "refresh", "choose", "unchoose_flights", "hold", "remove", "status_line", "booked", "failed", "cancelled", "event", "on", "sync_stays", "words", "overlay", "shown_flights",
           # Sasha 249 · one total, one currency, one party; offered == bookable
           "counted", "eur_of", "breakdown", "figures_of", "trip_figures", "card_eur", "in_eur", "ingest_flight", "supersede_plan", "superseded"]
