"""Part 4 §4 webhooks: notifications, never proof ("booked" only from acts.status / Evidence).
  W2  {webhook_id, event, created_at, account, mode, data} — data holds ids and states only (no personal data, no upstream text)
  W3  AgAPI-Signature: t=<unix>,v1=<hex HMAC-SHA256(secret, "<t>.<raw body>")>; receivers reject a t older than 5 minutes
  W4  at least once (dedupe on webhook_id), no ordering, exponential back-off for 24 h, then failed
Endpoints are set by hand in the private phase (admin.py). In test mode only test events exist (mode: "test")."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import timedelta
from typing import Optional
from urllib.parse import urlsplit

from . import config, rules as R
from .store import Store, now, parse_ts, ts

log = logging.getLogger("agapi.webhooks")
_DATA_KEYS = ("intent_id", "read_back_id", "approval_id", "act_id", "evidence_id", "outcome_kind", "void_reason", "reference")


def emit(store: Store, account: str, event: str, data: dict) -> None:
    eps = store.q("select * from webhook_endpoints where account = ? and state = 'active'", account)
    if not eps:
        return
    payload = {"webhook_id": R.new_id("whk"), "event": event, "created_at": ts()[:19] + "Z", "account": account, "mode": config.MODE,
               "data": {k: v for k, v in data.items() if k in _DATA_KEYS and v is not None}}
    for ep in eps:   # one delivery (and one webhook_id) per endpoint
        body = json.dumps({**payload, "webhook_id": R.new_id("whk")}, separators=(",", ":"), ensure_ascii=False)
        store.x("insert into webhook_deliveries (id, account, endpoint_id, event, body, created_at, next_at, state) values (?, ?, ?, ?, ?, ?, ?, 'pending')",
                json.loads(body)["webhook_id"], account, ep["id"], event, body, ts(), ts())


async def deliver_due(store: Store) -> int:
    """One pass: every pending delivery that is due, signed over its raw body. 2xx → delivered; else back-off; after 24 h → failed."""
    import httpx
    n = 0
    for d in store.q("select * from webhook_deliveries where state = 'pending' and next_at <= ? order by created_at limit 50", ts()):
        ep = store.one("select * from webhook_endpoints where account = ? and id = ?", d["account"], d["endpoint_id"])
        if not ep or ep["state"] != "active":
            store.x("update webhook_deliveries set state = 'failed' where id = ?", d["id"])
            continue
        t = int(time.time())
        status = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.post(ep["url"], content=d["body"].encode(), headers={"Content-Type": "application/json",
                                                                                 "AgAPI-Signature": R.webhook_signature(ep["secret"], t, d["body"])})
                status = r.status_code
        except Exception as e:
            log.info("[webhooks] %s: %s", d["id"], type(e).__name__)
        attempts = d["attempts"] + 1
        if status and 200 <= status < 300:
            store.x("update webhook_deliveries set state = 'delivered', attempts = ?, last_status = ? where id = ?", attempts, status, d["id"])
        elif now() - parse_ts(d["created_at"]) > timedelta(hours=24):
            store.x("update webhook_deliveries set state = 'failed', attempts = ?, last_status = ? where id = ?", attempts, status, d["id"])
        else:
            nxt = now() + timedelta(seconds=min(3600, 10 * 2 ** min(attempts, 9)))
            store.x("update webhook_deliveries set attempts = ?, last_status = ?, next_at = ? where id = ?", attempts, status, ts(nxt), d["id"])
        n += 1
    return n


def allow_endpoint_hosts(store: Store) -> None:
    from . import providers as PV
    for ep in store.q("select url from webhook_endpoints where state = 'active'"):
        PV.ALLOWED_HOSTS.add((urlsplit(ep["url"]).hostname or "").lower())


async def loop(get_store) -> None:
    while True:
        try:
            store = get_store()
            allow_endpoint_hosts(store)
            await deliver_due(store)
        except Exception as e:   # the loop never dies
            log.warning("[webhooks] pass failed: %s", type(e).__name__)
        await asyncio.sleep(5)


def add_endpoint(store: Store, account: str, url: str) -> tuple:
    """→ (endpoint id, the secret — shown ONCE)."""
    import secrets
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1") and not url.startswith("http://localhost"):
        raise ValueError("a webhook endpoint is https")
    eid, secret = R.new_id("whk").replace("whk_", "wep_"), "whsec_" + secrets.token_urlsafe(32)
    store.x("insert into webhook_endpoints (account, id, url, secret, state, created_at) values (?, ?, ?, ?, 'active', ?)",
            account, eid, url, secret, ts())
    allow_endpoint_hosts(store)
    return eid, secret
