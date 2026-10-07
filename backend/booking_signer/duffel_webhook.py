"""Sasha 198 · R8 · DUFFEL WEBHOOKS → PACIOLI. POST /api/booking/travel/duffel/webhook (open path; the signature is the key).

Duffel signs each event: X-Duffel-Signature: t=<timestamp>,v1=<hex HMAC-SHA256 of "<t>.<raw body>" with the webhook's secret>
(DUFFEL_WEBHOOK_SECRET on Railway — Duffel shows it once, when the webhook is created). No secret set → 503, nothing read.
A bad or stale (> 5 min) signature → 401, nothing recorded. A verified event is recorded once (basket_events, by Duffel's
event id: a redelivery is not a second), then:
    order cancelled (order_cancellation.confirmed, or an order.updated whose order carries cancelled_at)
                                              → the basket row cancelled + its trip_items row cancelled; the guest told
    order.airline_initiated_change_detected   → the row's line says the airline changed the schedule; the guest told
    anything else (order.created, order.updated, ping.triggered)  → recorded only
Pacioli writes every line; the model never sees an event.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import basket as BK

log = logging.getLogger(__name__)
router = APIRouter(prefix="/travel", tags=["travel"])
PATH = "/api/booking/travel/duffel/webhook"
TELL = None   # tests replace it: (account, words) → None


def verify(secret: str, header: str, body: bytes, now: Optional[float] = None) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in (header or "").split(","))
        t, sig = parts["t"], parts["v1"]
    except (ValueError, KeyError):
        return False
    if abs((now or time.time()) - int(t)) > 300:
        return False
    want = hmac.new(secret.encode(), t.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, sig)


async def _rows_of_order(order_id: str):
    async def fn(conn):
        return await conn.fetch("select * from trip_basket_items where order_id = $1", order_id)
    return [BK._row(r) for r in await BK._go(fn)]


async def _tell(account: str, words: str) -> None:
    if TELL is not None:
        return await TELL(account, words)
    from . import paid_watch as PW
    await PW._tell(account, {"say": words})


async def handle(event: Dict[str, Any]) -> Dict[str, Any]:
    """A VERIFIED event → what Pacioli did."""
    etype = str(event.get("type") or "")
    obj = ((event.get("data") or {}).get("object")) or {}
    new = await BK.event("duffel_webhook", str(event.get("id") or ""), etype, event, verified=True)
    if not new:
        return {"done": "already recorded"}
    order_id = obj.get("order_id") if etype.startswith("order_cancellation") else obj.get("id")
    rows = await _rows_of_order(order_id) if order_id else []
    if not rows:
        return {"done": "recorded (no basket item for this order)"}
    cancelled = etype == "order_cancellation.confirmed" or (etype == "order.updated" and obj.get("cancelled_at"))
    out = []
    for r in rows:
        if cancelled and r["state"] != "cancelled":
            x = await BK.cancelled(r["account_id"], r["id"])
            if r.get("trip_item_id"):
                async def fn(conn, tid=r["trip_item_id"]):
                    await conn.execute("update trip_items set status = 'cancelled', updated_at = now() where id = $1", uuid.UUID(tid))
                await BK._go(fn)
            await _tell(r["account_id"], f"Your airline cancelled this booking: {x['status_line']}. I'll help you rebook — just ask.")
            out.append("cancelled")
        elif etype == "order.airline_initiated_change_detected":
            line = (r.get("status_line") or BK.status_line(r)) + " · the airline changed the schedule — check the new times"

            async def fn(conn, iid=r["id"], line=line):
                await conn.execute("update trip_basket_items set status_line = $2, updated_at = now() where id = $1", uuid.UUID(iid), line)
            await BK._go(fn)
            await _tell(r["account_id"], f"The airline changed your flight's schedule: {line}.")
            out.append("schedule change")
    return {"done": ", ".join(out) or "recorded"}


@router.post("/duffel/webhook")
async def webhook(request: Request):
    secret = os.getenv("DUFFEL_WEBHOOK_SECRET", "").strip()
    if not secret:
        return JSONResponse({"ok": False, "rule": "webhook_not_configured"}, status_code=503)
    body = await request.body()
    if not verify(secret, request.headers.get("x-duffel-signature", ""), body):
        log.warning("[duffel_webhook] refused: bad or stale signature")
        return JSONResponse({"ok": False, "rule": "bad_signature"}, status_code=401)
    try:
        event = json.loads(body)
    except ValueError:
        return JSONResponse({"ok": False, "rule": "not_json"}, status_code=400)
    try:
        r = await handle(event)
    except Exception as e:
        log.error("[duffel_webhook] %s not handled: %s: %s", event.get("type"), type(e).__name__, e)
        return JSONResponse({"ok": False, "rule": "not_handled"}, status_code=500)   # Duffel retries
    log.info("[duffel_webhook] %s %s → %s", event.get("type"), event.get("id"), r["done"])
    return {"ok": True, **r}


__all__ = ["verify", "handle", "router", "PATH"]
