"""CR 62 · THE ACTIVITY VIEW — everything Sasha did for this person, newest first, from Pacioli's records only:
  · venue bookings (trip_items: the ladder's own status and the venue's reference),
  · flights and stays (trip_basket_items, with the provider's verified events in basket_events),
  · S2's emails, WhatsApps and calendar adds (s2_acts, each with its proof), and the WhatsApp replies (s2_wa_replies).
Each row: our own one-line words (powers.ACTIVITY_LINES), a green/red/amber check, what it's about (their words, shown as text),
and a Proof: the provider reference, the time, what the person approved, and whether it verifies. A source that can't be read
is listed in `unavailable` — never a silently shorter list.

    get_activity [Pacioli]  "what have you done for me today?" — answered from this, never from memory.
    GET /api/agent/activity  the /activity screen (signed in; the account's own rows only).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from agapi import powers as P, s2_records as REC

log = logging.getLogger("agapi.activity")
router = APIRouter()   # included into the agent router (prefix /api/agent) by the wiring note → /api/agent/activity

VENUE = {"confirmed": ("booking", "done"), "guest_booked": ("booking", "done"), "requested": ("booking", "requested"),
         "attempting": ("booking", "requested"), "link_sent": ("booking", "requested"), "unclear": ("booking", "requested"),
         "declined": ("booking", "failed"), "failed": ("booking", "failed"), "unreachable": ("booking", "failed"),
         "escalated": ("booking", "failed"), "cancelled": ("cancellation", "done")}   # 'prepared' / 'pending': nothing was sent
BASKET = {"booked": ("booking", "done"), "pending_payment": ("booking", "waiting"), "failed": ("booking", "failed"),
          "cancelled": ("cancellation", "done")}
S2_KIND = {"email": "email", "whatsapp": "whatsapp", "calendar": "calendar",
           "keep_save": "keep_save", "keep_use": "keep_use", "keep_show": "keep_show", "keep_delete": "keep_delete",   # CR 63
           "venue_late": "venue_late", "booking_change": "booking_change"}   # Sasha 226


def _run():
    from booking_signer import plan_store as PS
    return REC.RUN if REC.RUN is not None else PS._run()


def _proof(reference: Optional[str], at: str, *, said: Optional[str] = None, fingerprint: Optional[str] = None,
           ok: bool = False, source: str) -> dict:
    return {"reference": reference, "at": at, "approved": said, "fingerprint": fingerprint, "verified": ok, "source": source}


async def _venues(account: str) -> List[dict]:
    async def q(conn):
        return await conn.fetch("select t.id, t.status, t.provider_name, t.booking_reference, t.type, t.updated_at, t.request_sha256 "
                                "from trip_items t join trips p on p.id = t.trip_id where p.owner_id = $1::uuid "
                                "and t.status not in ('pending', 'prepared') and t.id not in "
                                "(select trip_item_id from trip_basket_items where account_id = $1::uuid and trip_item_id is not null) "
                                "order by t.updated_at desc limit 200", account)
    out = []
    for r in await _run()(q):
        kind_state = VENUE.get(r["status"])
        if not kind_state:
            continue
        at = r["updated_at"].isoformat()
        ref = r["booking_reference"]
        row = P.activity_entry(*kind_state, at, ref=str(r["id"]))
        out.append({**row, "about": r["provider_name"], "proof": _proof(ref, at, fingerprint=r["request_sha256"],
                                                                        ok=bool(ref) and kind_state[1] == "done", source="venue")})
    return out


async def _basket(account: str) -> List[dict]:
    async def q(conn):
        return await conn.fetch(
            "select b.id, b.kind, b.state, b.snapshot, b.booking_reference, b.order_id, b.paid_session, b.updated_at, "
            "(select bool_or(e.verified) from basket_events e where e.item_id = b.id) as verified, "
            "(select e.payload_sha256 from basket_events e where e.item_id = b.id and e.verified order by e.received_at desc limit 1) as fp "
            "from trip_basket_items b where b.account_id = $1::uuid and b.state in ('booked', 'pending_payment', 'failed', 'cancelled') "
            "order by b.updated_at desc limit 200", account)
    out = []
    for r in await _run()(q):
        kind, state = BASKET[r["state"]]
        snap = r["snapshot"] if isinstance(r["snapshot"], dict) else __import__("json").loads(r["snapshot"] or "{}")
        about = (f"{snap.get('owner') or ''} {snap.get('flights') or ''} {snap.get('from') or ''} → {snap.get('to') or ''}".strip()
                 if r["kind"] == "flight" else snap.get("name") or snap.get("hotel") or "Your stay")
        at, ok = r["updated_at"].isoformat(), bool(r["verified"])
        ref = r["booking_reference"] or r["order_id"]
        out.append({**P.activity_entry(kind, state, at, ref=str(r["id"])), "about": about,
                    "proof": _proof(ref, at, fingerprint=r["fp"] and "sha256:" + r["fp"], ok=ok and bool(ref), source=r["kind"])})
        if r["state"] == "booked" and r["paid_session"]:
            out.append({**P.activity_entry("payment", "done", at, ref=f"{r['id']}:payment"), "about": about,
                        "proof": _proof("Stripe payment", at, fingerprint=r["fp"] and "sha256:" + r["fp"], ok=ok, source="stripe")})
    return out


async def _s2(account: str, since: Optional[str]) -> List[dict]:
    out = []
    for r in await REC.acts(account, since):
        pr = r["proof"]
        if r["kind"] == "calendar" and r["state"] != "done":
            continue
        out.append({**P.activity_entry(S2_KIND[r["kind"]], r["state"], r["at"], ref=r["id"]), "about": r.get("about"),
                    "proof": _proof(pr.get("reference"), pr.get("at") or r["at"], said=pr.get("said") or None,
                                    fingerprint=pr.get("body_sha256") or pr.get("event_sha256"), ok=REC.verified(r), source=r["kind"])})
    for r in await REC.replies(account, since):
        out.append({**P.activity_entry("whatsapp_reply", "done", r["received_at"], ref=r["id"]), "about": r.get("name") or r["number_e164"]})
    return out


async def collect(account: str, since: Optional[str] = None, limit: int = 50) -> dict:
    """→ {"items": [...newest first], "unavailable": [source, ...]}. Every source tried; a failure is named, never hidden."""
    items, unavailable = [], []
    for name, fn in (("venues", lambda: _venues(account)), ("flights_and_stays", lambda: _basket(account)), ("s2", lambda: _s2(account, since))):
        if name != "s2" and _run() is None:
            unavailable.append(name)
            continue
        try:
            items += await fn()
        except Exception as e:
            log.warning("[activity] %s unreadable: %s", name, type(e).__name__)
            unavailable.append(name)
    items = [i for i in P.activity_sorted(items) if not since or i["at"] >= since][:limit]
    return {"items": items, "unavailable": unavailable}


def since_of(when: Optional[str], tz: str = "Europe/Madrid") -> Optional[str]:
    """'today' → midnight in the person's zone, as UTC ISO; a YYYY-MM-DD → that day's midnight; None/'' → everything."""
    if not when:
        return None
    try:
        z = ZoneInfo(tz)
    except Exception:
        z = ZoneInfo("Europe/Madrid")
    if when == "today":
        d = datetime.now(z).date()
    else:
        try:
            d = datetime.fromisoformat(when[:10]).date()
        except ValueError:
            return None
    return datetime(d.year, d.month, d.day, tzinfo=z).astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def get_activity(ctx, a: dict) -> dict:
    got = await collect(ctx.account, since_of(a.get("since"), a.get("timezone") or "Europe/Madrid"), int(a.get("limit") or 20))
    rows = [{"line": i["line"], "check": i["check"], "about": i.get("about"), "at": i["at"],
             "verified": bool((i.get("proof") or {}).get("verified"))} for i in got["items"]]
    out = {"activity": rows, "anything": bool(rows), "screen": "/activity"}
    if got["unavailable"]:
        out["unavailable"] = got["unavailable"]
        out["say"] = "Part of the record couldn't be read just now — say that plainly; never 'nothing'."
    return out


def tools() -> List[dict]:
    from agapi.v0 import _t
    return [_t("get_activity", "Pacioli", get_activity, "What Sasha has done for the person — bookings, payments, emails, WhatsApps, "
               "calendar adds, cancellations — newest first, from the records (never from memory). For 'what have you done for me "
               "today?' use since='today'. Say each in a few words; the full list with proof is on the Activity screen (/activity).",
               {"since": {"type": "string", "description": "'today', a date YYYY-MM-DD, or empty for everything"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, [],
               {"type": "object", "properties": {"activity": {"type": "array"}, "anything": {"type": "boolean"}}}, [])]


@router.get("/activity")
async def activity_route(request: Request):
    """The /activity screen's data: the signed-in account's own rows only."""
    from app.services.chat_account import chat_account, signed_in
    account = await chat_account(request)
    if not signed_in(account):
        return JSONResponse({"ok": False, "rule": "sign_in"}, status_code=403)
    got = await collect(account, since_of(request.query_params.get("since")), 100)
    return JSONResponse({"ok": True, **got}, headers={"Cache-Control": "no-store"})
