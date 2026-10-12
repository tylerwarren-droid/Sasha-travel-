"""CR 87 · THE BOOKING OUTCOMES LEDGER, Sasha's side — every real booking attempt goes to AgAPI's outcomes.record, and is updated when
the venue's reply lands (outcomes.update). "We get any booking done", measured by outcomes.

  when         book_venue acts (after the person's yes): the attempt is recorded with the rung it used —
                 form → zero_touch (web_form) · handover / page → human_tap (page_handover) · draft → request_reply (whatsapp /
                 instagram) · email → request_reply (email) · call → phone (phone)
               and what happened at once: confirmed (the venue's page said so), sent (a request is out / the page is on their phone),
               or failed (with the reason).
  then         the reservation's own status, read from Sasha's records (each time her bookings are read, and every 10 minutes for the
               attempts still open): confirmed / guest_booked → confirmed (the venue's words quoted), declined → declined, failed /
               unreachable → failed, cancelled before any answer → failed ("cancelled before the venue answered").
  the key      ref = "sasha:<trip_item_id>" — the reservation's own id, so the update needs no table of its own.
  never        the customer's name, phone, email or card: only the venue, its sector and city, the rung, the channel and the times.

Where: SASHA_OUTCOMES_VIA = sandbox (default) | live. Keys: SASHA_AGAPI_TEST_KEY / SASHA_AGAPI_KEY. Never printed. A ledger that
doesn't answer never stops a booking: it is logged and skipped."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from typing import Any, Awaitable, Callable, Dict, Optional, Set, Tuple

log = logging.getLogger(__name__)

RUNG = {"form": ("zero_touch", "web_form"), "handover": ("human_tap", "page_handover"), "page": ("human_tap", "page_handover"),
        "draft": ("request_reply", "whatsapp"), "email": ("request_reply", "email"), "call": ("phone", "phone"),
        "prepared": ("human_tap", "page_handover")}   # Sasha 248 · "fill it now": their page + every detail, they confirm there
NOW_STATE = {"confirmed": "confirmed", "requested": "sent", "tap_to_finish": "sent", "page_on_phone": "sent", "page_link": "sent",
             "draft_on_phone": "sent", "draft_message": "sent", "scheduled": "sent", "placed": "sent", "calling": "sent", "not_sent": "failed"}
LATER = {"confirmed": "confirmed", "guest_booked": "confirmed", "declined": "declined", "failed": "failed", "unreachable": "failed"}
SWEEP_EVERY_S = 600

_OPEN: Dict[str, Set[str]] = {}          # account → trip_item ids whose outcome is still open (this process)
_DONE: Set[Tuple[str, str]] = set()      # (ref, state) already sent — never sent twice
_task: Optional[asyncio.Task] = None


def via() -> str:
    return "live" if os.getenv("SASHA_OUTCOMES_VIA", "sandbox").strip().lower() == "live" else "sandbox"


async def _agapi(op: str, body: dict) -> Dict[str, Any]:
    import httpx
    live = via() == "live"
    url = (os.getenv("SASHA_AGAPI_URL", "https://agapi-live-production.up.railway.app") if live
           else os.getenv("SASHA_AGAPI_TEST_URL", "https://agapi-sandbox-production.up.railway.app")).rstrip("/")
    key = os.getenv("SASHA_AGAPI_KEY" if live else "SASHA_AGAPI_TEST_KEY", "").strip()
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "the outcomes ledger isn't switched on"}}
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": "s2out_" + secrets.token_hex(12)}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as c:
            r = await c.post(f"{url}/v1/{op}", headers=h, content=json.dumps(body))
        return r.json()
    except Exception as e:
        return {"ok": False, "error": {"code": "unreachable", "message": type(e).__name__}}


CALL: Callable[..., Awaitable[Dict[str, Any]]] = _agapi   # tests replace it


def ref_of(held: dict) -> str:
    return "sasha:" + str(held.get("trip_item_id") or f"{held.get('rung')}:{held.get('id')}")


async def _send(op: str, body: dict) -> Optional[dict]:
    try:
        r = await CALL(op, body)
    except Exception as e:
        log.warning("[outcomes] %s not recorded: %s", op, type(e).__name__)
        return None
    if not r.get("ok"):
        code = (r.get("error") or {}).get("code")
        if code not in ("not_found", "already_completed"):
            log.warning("[outcomes] %s not recorded: %s", op, code)
        return None
    return r["result"]


async def booked(account: str, held: dict, venue: str, city: Optional[str], result: Optional[dict] = None, error: Optional[str] = None) -> None:
    """book_venue acted: record the attempt and what happened at once. Never raises."""
    rung, channel = RUNG.get(held.get("rung") or "", ("phone", "phone"))
    if held.get("rung") == "draft" and held.get("channel") == "instagram":
        channel = "instagram"
    st = "failed" if error else NOW_STATE.get(str((result or {}).get("status") or ""), "sent")
    ref = ref_of(held)
    body: Dict[str, Any] = {"ref": ref, "venue": venue[:120], "rung": rung, "channel": channel, "state": st,
                            **({"sector": str(held["sector"])[:40]} if held.get("sector") else {}), **({"city": city[:80]} if city else {}),
                            **({"asked_at": held["at"].strftime("%Y-%m-%dT%H:%M:%SZ")} if hasattr(held.get("at"), "strftime") else {})}
    if st == "confirmed":
        body["confirmation_quote"] = (f"Their reference: {result['reference']}" if (result or {}).get("reference") else (result or {}).get("line") or "confirmed")
    if st == "failed":
        body["failure_reason"] = (error or (result or {}).get("status") or "not sent")[:300]
    out = await _send("outcomes.record", body)
    if out:
        _DONE.add((ref, st))
        if st not in ("confirmed", "declined", "failed") and held.get("trip_item_id"):
            _OPEN.setdefault(account, set()).add(str(held["trip_item_id"]))
            start()


async def sync(account: str, reservations: list) -> int:
    """The reservations as Sasha's records have them now → each decided one updates its outcome (once). Never raises."""
    n = 0
    for r in reservations or []:
        tid, status = str(r.get("id") or r.get("trip_item_id") or ""), str(r.get("status") or "")
        st = LATER.get(status)
        if status == "cancelled" and tid in _OPEN.get(account, set()):
            st = "failed"
        if not tid or not st:
            continue
        ref = f"sasha:{tid}"
        if (ref, st) in _DONE:
            continue
        words = r.get("status_words") or (f"Their reference: {r['booking_reference']}" if r.get("booking_reference") else None)
        body: Dict[str, Any] = {"ref": ref, "state": st}
        if st == "confirmed" and words:
            body["confirmation_quote"] = str(words)[:2000]
        if st in ("declined", "failed"):
            body["failure_reason"] = ("cancelled before the venue answered" if status == "cancelled" else str(words or status))[:600]
        _DONE.add((ref, st))
        if await _send("outcomes.update", body):
            n += 1
        _OPEN.get(account, set()).discard(tid)
    return n


async def _sweep_once() -> None:
    from agapi.venues import _API
    GW = _API()
    for account in list(_OPEN):
        if not _OPEN.get(account):
            _OPEN.pop(account, None)
            continue
        try:
            status, j = await GW.api(account, "GET", "/api/booking/reservations")
        except Exception as e:
            log.warning("[outcomes] the sweep couldn't read the reservations: %s", type(e).__name__)
            continue
        if status == 200:
            await sync(account, (j or {}).get("reservations") or [])


async def _forever() -> None:
    while _OPEN:
        await asyncio.sleep(SWEEP_EVERY_S)
        try:
            await _sweep_once()
        except Exception as e:
            log.warning("[outcomes] sweep failed: %s", type(e).__name__)


def start() -> None:
    global _task
    if _task is None or _task.done():
        try:
            _task = asyncio.get_running_loop().create_task(_forever())
        except RuntimeError:
            _task = None


__all__ = ["booked", "sync", "ref_of", "via", "RUNG", "LATER"]
