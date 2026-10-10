"""Sasha 227 · PROACTIVE "DAY BEFORE PICKUP" — CR 75's fine-print moment, on Sasha's proactive loop (S-83), for car rentals.

Sasha keeps no rental bookings of her own, so a rental is what the person TOLD her on /s2 (`note_rental`: company, country, where,
the pickup day and time). The evening before pickup (18:00 in the rental country's time, never in quiet hours) the loop asks AgAPI
`cards.moment` (FP.moment, kind pickup_tomorrow); only when it says speak is ONE line sent — to their WhatsApp inside the 24-hour
window, and to /s2 if it's open (the counter card). AT MOST ONE per rental: claimed here before asking (`moment_at`), and AgAPI
keeps one per event too. FOUNDER ONLY, and only with SASHA_PROACTIVE_RENTALS=1 (off by default; flip back = unset).

    note(account, rental) → the saved rental · rentals(account) → the upcoming ones · tick(now) → what was done
Stored in s2_rentals (sql/040_s2_rentals.sql); until it's applied, this process's memory (a restart forgets; nothing fails).
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger("booking_signer.rental_moments")
NOW = lambda: datetime.now(timezone.utc)   # noqa: E731
AT = dtime(18, 0)
_MEM: Dict[str, dict] = {}   # id → rental, until 040 is applied
RUN = "auto"                 # tests: None → memory


def on() -> bool:
    return os.getenv("SASHA_PROACTIVE_RENTALS", "").strip() == "1"


def _run():
    if RUN != "auto":
        return RUN
    from . import plan_store as PS
    return PS._run()


def _tz(country: str) -> ZoneInfo:
    from . import venue_read as V
    try:
        return ZoneInfo(V.COUNTRIES[country][3]) if country in V.COUNTRIES else ZoneInfo("Europe/Madrid")
    except Exception:
        return ZoneInfo("Europe/Madrid")


def clean(r: dict) -> dict:
    day, at = str(r.get("pickup_date") or "")[:10], str(r.get("pickup_time") or "")[:5]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("pickup_date is YYYY-MM-DD")
    if at and not re.fullmatch(r"\d{2}:\d{2}", at):
        raise ValueError("pickup_time is HH:MM")
    return {"rental_company": str(r.get("rental_company") or "").strip()[:80], "country": str(r.get("country") or "").upper()[:2],
            "place": str(r.get("place") or "").strip()[:120], "pickup_date": day, "pickup_time": at or None,
            "days": int(r["days"]) if str(r.get("days") or "").isdigit() else None}


async def note(account: str, r: dict) -> dict:
    row = {"id": str(uuid.uuid4()), "account_id": account, **clean(r), "created_at": NOW(), "moment_at": None, "moment_outcome": None}
    run = _run()
    if run is not None:
        try:
            await run(lambda c: c.execute(
                "insert into s2_rentals (id, account_id, rental_company, country, place, pickup_date, pickup_time, days, created_at) "
                "values ($1, $2, $3, $4, $5, $6, $7, $8, $9)", uuid.UUID(row["id"]), uuid.UUID(account), row["rental_company"], row["country"],
                row["place"], date.fromisoformat(row["pickup_date"]), row["pickup_time"], row["days"], row["created_at"]))
            return row
        except Exception as e:
            log.info("[rentals] not stored (%s) — kept in memory", type(e).__name__)
    _MEM[row["id"]] = row
    return row


async def _all(account: Optional[str] = None) -> List[dict]:
    run = _run()
    if run is not None:
        try:
            rows = await run(lambda c: c.fetch("select * from s2_rentals where pickup_date >= current_date - 1"
                                               + (" and account_id = $1" if account else ""), *( [uuid.UUID(account)] if account else [])))
            return [{**dict(r), "id": str(r["id"]), "account_id": str(r["account_id"]), "pickup_date": str(r["pickup_date"])} for r in rows]
        except Exception as e:
            log.info("[rentals] not read (%s) — memory", type(e).__name__)
    return [r for r in _MEM.values() if not account or r["account_id"] == account]


async def rentals(account: str) -> List[dict]:
    today = date.today().isoformat()
    return sorted([r for r in await _all(account) if r["pickup_date"] >= today], key=lambda r: (r["pickup_date"], r.get("pickup_time") or ""))


async def _claim(r: dict, now: datetime) -> bool:
    """One moment per rental, ever: claimed BEFORE AgAPI is asked."""
    run = _run()
    if run is not None and r["id"] not in _MEM:
        try:
            got = await run(lambda c: c.fetchval("update s2_rentals set moment_at = $2 where id = $1 and moment_at is null returning id",
                                                 uuid.UUID(r["id"]), now))
            return got is not None
        except Exception:
            return False
    m = _MEM.get(r["id"])
    if not m or m.get("moment_at"):
        return False
    m["moment_at"] = now
    return True


async def _outcome(r: dict, outcome: str) -> None:
    run = _run()
    if run is not None and r["id"] not in _MEM:
        try:
            await run(lambda c: c.execute("update s2_rentals set moment_outcome = $2 where id = $1", uuid.UUID(r["id"]), outcome[:200]))
        except Exception:
            pass
    elif r["id"] in _MEM:
        _MEM[r["id"]]["moment_outcome"] = outcome


def due(r: dict, now: datetime) -> bool:
    """The evening before pickup (18:00 local or later that evening, before quiet hours)."""
    tz = _tz(r["country"])
    local = now.astimezone(tz)
    pickup = date.fromisoformat(r["pickup_date"])
    return local.date() == pickup - timedelta(days=1) and AT <= local.time() < dtime(22, 0)


async def _whatsapp(account: str, text: str) -> str:
    from . import guest_whatsapp as GW
    if GW.STORE is None:
        return "not sent: no WhatsApp store"
    ch = next((c for c in await GW.STORE.all_channels() if c["account_id"] == account), None)
    if ch is None:
        return "not sent: no WhatsApp linked"
    st = await GW.STORE.get_state(ch["wa_id_sha256"])
    last = st.get("last_inbound_at")
    frm = sorted(GW.guest_numbers())[0] if GW.guest_numbers() else None
    if not frm:
        return "not sent: WhatsApp for guests is off"
    if not (last and NOW() - last <= GW.SESSION_WINDOW):
        return "not sent: outside the 24-hour window (no approved template for this)"
    return ", ".join(await GW.deliver(ch, frm, GW.Out().text(text), last))


async def tick(now: datetime) -> List[dict]:
    """The proactive loop's rental moments — the founder's account only, behind SASHA_PROACTIVE_RENTALS."""
    if not on():
        return []
    from .identity import founder_account
    from . import live_events as LE
    from agapi import s2_fine_print as FP
    founder, done = founder_account(), []
    for r in await _all(founder):
        if r.get("moment_at") or not due(r, now) or not await _claim(r, now):
            continue
        m = await FP.moment(founder, {"id": r["id"], "kind": "pickup_tomorrow", "country": r["country"], "rental_company": r["rental_company"],
                                      "pickup_time": r.get("pickup_time") or "", "place": r.get("place") or ""})
        if not m.get("speak"):
            outcome = f"silent: {m.get('why_silent') or 'AgAPI said not to'}"
        else:
            wa = await _whatsapp(founder, m.get("line") or "")
            LE.publish(founder, {"type": "proactive", "kind": "pickup_tomorrow", "say": m.get("line"),
                                 **({"render": {"kind": "counter_card", "card": (m.get("card") or {}).get("card") or m.get("card")}} if m.get("card") else {})})
            outcome = f"said: whatsapp {wa}; /s2 if open"
        await _outcome(r, outcome)
        done.append({"kind": "pickup_tomorrow", "rental": r["id"], "outcome": outcome})
    return done


__all__ = ["note", "rentals", "tick", "due", "on", "clean"]
