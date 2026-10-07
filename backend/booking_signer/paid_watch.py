"""Sasha 183 · A PAID BOOKING ALWAYS LANDS. Live 7 Oct: the founder paid a TEST flight on WhatsApp (Apple Pay) and it never
reached his itinerary — the booking after the payment was done by a watcher held in the server's memory, and a deploy
restarted the server a moment after he paid. Any restart (a deploy, a crash) lost the booking, silently.

Now the payment is written down BEFORE the guest is sent to pay: a row on the account's own list, "… (TEST — waiting for your
payment)", holding what was paid for. Whoever sees the payment first books it — the watcher, the web card's status poll, any
view of the itinerary (web, WhatsApp, avatar), or the 15-second loop — and only once: the row is claimed in one UPDATE. The row
then BECOMES the booking (a flight) or is replaced by the bookings it made (the whole trip). An expired TEST offer is priced
again on the same route and day and booked only if it costs no more than 1.5× (TEST) — and said so.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

log = logging.getLogger("booking_signer.paid_watch")

MARK = "Sasha 183 · awaiting payment "
CLAIM = "Sasha 183 · booking "
DONE = "Sasha 183 · paid and booked "


def _run():
    from . import ladder_routes as LR
    return getattr(LR.LADDER_STORE, "_run", None)


async def remember(account: str, kind: str, sid: str, payload: dict, label: str, when: Optional[str], tz: str) -> Optional[str]:
    """Written before the guest pays. `payload` is everything needed to book it after (the card / the bundle, the contact)."""
    run = _run()
    if not account or run is None:
        return None
    from .store import BOOKINGS_TRIP_TITLE
    try:
        dt = datetime.fromisoformat(when).replace(tzinfo=ZoneInfo(tz)) if when else None
    except ValueError:
        dt = None

    async def go(c):
        a = uuid.UUID(account)
        trip = await c.fetchval("select id from trips where owner_id = $1 and title = $2 limit 1", a, BOOKINGS_TRIP_TITLE)
        if trip is None:
            trip = await c.fetchval("insert into trips (owner_id, title) values ($1,$2) returning id", a, BOOKINGS_TRIP_TITLE)
        return await c.fetchval(
            "insert into trip_items (trip_id, type, status, provider_name, date_time, local_timezone, escalation_notes) "
            "values ($1,$2,'pending',$3,$4,$5,$6) returning id",
            trip, "flight" if kind == "flight" else "other", f"{label} (TEST — waiting for your payment)"[:200], dt, tz,
            MARK + json.dumps({"kind": kind, "sid": sid, "account": account, **payload}, default=str))
    try:
        return str(await run(go))
    except Exception as e:
        log.error("[paid_watch] not remembered: %s: %s", type(e).__name__, e)
        return None


async def _claim(row_id) -> Optional[dict]:
    """The row, if THIS caller won it (one UPDATE): the payload. None: someone else is booking it, or did."""
    run = _run()
    r = await run(lambda c: c.fetchrow("update trip_items set escalation_notes = $2 || substr(escalation_notes, $3) where id = $1 "
                                       "and escalation_notes like $4 returning escalation_notes",
                                       row_id, CLAIM, len(MARK) + 1, MARK + "%"))
    return json.loads(r["escalation_notes"][len(CLAIM):]) if r else None


async def _release(row_id, payload: dict) -> None:
    run = _run()
    await run(lambda c: c.execute("update trip_items set escalation_notes = $2 where id = $1", row_id, MARK + json.dumps(payload, default=str)))


async def fulfil(row_id, payload: dict) -> dict:
    """Paid: book it. {status: booked|failed, say}."""
    from . import travel as T, trip_book as TB
    run = _run()
    sid, account = payload["sid"], payload["account"]
    if payload["kind"] == "flight":
        c = payload["card"]
        o = await T.order(c, payload.get("name") or "Guest Test", payload.get("email") or "", payload.get("phone"))
        note = ""
        if "why" in o:   # a TEST offer expires: the same route and day, priced again — said
            alt = await TB._same_or_cheaper(c, int(c.get("party") or 1))
            if alt is not None:
                o2 = await T.order(alt, payload.get("name") or "Guest Test", payload.get("email") or "", payload.get("phone"))
                if "why" not in o2:
                    note = f" (the offer priced had expired; booked the same route and day at {alt['currency']} {alt['amount']}, TEST)"
                    c, o = alt, o2
        if "why" in o:
            await run(lambda x: x.execute("update trip_items set status = 'failed', provider_name = $2, escalation_notes = $3, updated_at = now() "
                                          "where id = $1", row_id, f"Flight {c['flights']} {c['from']} → {c['to']} (TEST — paid, not booked)"[:200],
                                          DONE + json.dumps({"sid": sid, "why": o["why"]})))
            return {"status": "failed", "say": f"Your TEST payment went through, but the test flight wasn't booked: {o['why']}."}
        T.mark_used(payload["card"]["id"]); T.mark_used(c["id"])   # one booking per search list
        tz = c.get("from_tz") or "Europe/Madrid"
        dep = datetime.fromisoformat(c["departs"])
        dt = dep.replace(tzinfo=ZoneInfo(tz)) if dep.tzinfo is None else dep
        ref = o["booking_reference"] or ""
        await run(lambda x: x.execute(
            "update trip_items set type = 'flight', status = 'confirmed', booking_reference = $2, provider_name = $3, date_time = $4, "
            "duration_minutes = $5, local_timezone = $6, location_name = $7, escalation_notes = $8, updated_at = now() where id = $1",
            row_id, ref, f"Flight {c['flights']} {c['from_city']} → {c['to_city']} (TEST booking)", dt, c.get("minutes") or 120, tz,
            f"{c['from']} → {c['to']}", DONE + json.dumps({"sid": sid, "order": o.get("order_id")})))
        from . import journeys as JN
        try:
            await JN.file(account)
        except Exception as e:
            log.info("[paid_watch] not filed yet: %s", type(e).__name__)
        tab = await _tab(account, row_id)
        return {"status": "booked", "booking_reference": ref, "card": c,
                "say": f"✅ Booked: {c['owner']} {c['flights']} · {T.card_line(c).split(' · ', 2)[1] if ' · ' in T.card_line(c) else ''} · ref {ref}{note}. "
                       f"It's in your {tab} on the platform itinerary. ({T.LABEL})"}   # no email is sent for a flight: never said
    if payload["kind"] == "trip":
        TB._QUOTES[sid] = payload["bundle"]
        r = await TB.book_paid(account, sid)
        await run(lambda x: x.execute("update trip_items set status = 'cancelled', provider_name = $2, escalation_notes = $3, updated_at = now() "
                                      "where id = $1", row_id, "Whole-trip TEST payment (booked as its own items)",
                                      DONE + json.dumps({"sid": sid, "status": r.get("status")})))
        return r
    return {"status": "failed", "say": "unknown payment kind"}


async def _tab(account: str, row_id) -> str:
    from . import journeys as JN
    run = _run()
    try:
        trip = await run(lambda c: c.fetchrow("select t.id, t.title, t.depart_date from trip_items ti join trips t on t.id = ti.trip_id "
                                              "where ti.id = $1", row_id))
        from .store import BOOKINGS_TRIP_TITLE
        if trip and trip["title"] != BOOKINGS_TRIP_TITLE:
            return f"{JN.label({'title': trip['title'], 'start': trip['depart_date']})} trip"
    except Exception:
        pass
    return "Everything list"


async def settle(sid: str) -> Optional[dict]:
    """The one entry for a session: paid → booked once (whoever asks first); unpaid → None. Already booked → its result."""
    from . import test_deposit as TD
    run = _run()
    if run is None or not sid:
        return None
    try:
        row = await run(lambda c: c.fetchrow("select id, status, provider_name, booking_reference, escalation_notes from trip_items "
                                             "where escalation_notes like $1 order by created_at desc limit 1",
                                             f"Sasha 183 · %\"sid\": \"{sid}\"%"))
    except Exception as e:   # no database (tests, an outage): the caller's own path books it, as before
        log.info("[paid_watch] unread: %s", type(e).__name__)
        return None
    if not row:
        return None
    notes = row["escalation_notes"] or ""
    if notes.startswith(DONE) and str(row["provider_name"] or "").startswith("Whole-trip"):
        return {"status": "booked", "say": "✅ Booked (TEST) — every hotel and both flights are in your trip, each with its reference."}
    if notes.startswith(DONE):
        return {"status": "booked" if row["status"] == "confirmed" else ("booked" if "booked" in notes else "failed"),
                "booking_reference": row["booking_reference"], "say": f"✅ Booked: {row['provider_name']} · ref {row['booking_reference']}"
                if row["status"] == "confirmed" else str(row["provider_name"])}
    if notes.startswith(CLAIM):
        return {"status": "booking"}
    if not await TD.session_paid(sid):
        return None
    payload = await _claim(row["id"])
    if payload is None:
        return {"status": "booking"}
    try:
        r = await fulfil(row["id"], payload)
    except Exception as e:
        log.error("[paid_watch] booking after payment failed: %s: %s", type(e).__name__, e)
        await _release(row["id"], payload)   # the next look tries again
        return {"status": "booking"}
    TD.note(sid, r.get("status") == "booked", str(r.get("say") or "")[:300])
    await _tell(payload["account"], r)
    return r


async def _tell(account: str, r: dict) -> None:
    """Said once on WhatsApp, whichever device paid (the phone pays; the laptop shows it too)."""
    from . import guest_whatsapp as GW
    try:
        ch = await GW.STORE.channel_of_account(account) if GW.STORE else None
        if ch:
            st = await GW.STORE.get_state(ch["wa_id_sha256"])
            if st.get("last_to"):
                await GW.deliver(ch, st["last_to"], GW.Out().text(str(r.get("say") or "")), st.get("last_inbound_at"))
    except Exception as e:
        log.info("[paid_watch] not told on WhatsApp: %s", type(e).__name__)


async def sweep(account: Optional[str] = None) -> int:
    """Every payment still waiting (an account's, or all of them): settled if paid. → how many were booked."""
    run = _run()
    if run is None:
        return 0
    q = ("select ti.escalation_notes from trip_items ti join trips t on t.id = ti.trip_id where ti.escalation_notes like $1 "
         "and ti.created_at > now() - interval '6 hours'" + (" and t.owner_id = $2" if account else ""))
    try:
        rows = await run(lambda c: c.fetch(q, MARK + "%", *( [uuid.UUID(account)] if account else [])))
    except Exception as e:
        log.info("[paid_watch] sweep unread: %s", type(e).__name__)
        return 0
    n = 0
    for r in rows:
        try:
            sid = json.loads(r["escalation_notes"][len(MARK):]).get("sid")
            got = await settle(sid)
            n += 1 if (got or {}).get("status") == "booked" else 0
        except Exception as e:
            log.warning("[paid_watch] sweep item failed: %s: %s", type(e).__name__, e)
    return n


_task: Optional[asyncio.Task] = None


async def _forever() -> None:
    while True:
        await asyncio.sleep(15)
        try:
            await sweep()
        except Exception as e:
            log.warning("[paid_watch] loop: %s", type(e).__name__)


def start() -> None:
    """The 15-second loop (SASHA_PAID_LOOP=0 turns it off; tests never start it)."""
    global _task
    if _task is None and os.getenv("SASHA_PAID_LOOP", "1") == "1" and os.getenv("DATABASE_URL", "").strip():
        _task = asyncio.create_task(_forever())


__all__ = ["remember", "settle", "sweep", "start", "MARK"]
