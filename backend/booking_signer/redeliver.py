"""Sasha 394 · CR 206 · DELIVER AGAIN — a WhatsApp message AgAPI couldn't decide is never answered by Sasha; Sasha delivers it again.

CR 206 (agapi-live b8ea1634): messages.whatsapp_inbound decides the owner ONCE; when it can't (AD unreachable for a message that needs AD,
or AgAPI itself not answering) it answers an error, releases its claim and records nothing — "an error from messages.whatsapp_inbound is
'deliver again', never 'no role'". Twilio is answered at once (Sasha 379a: AD took ~19 s against Twilio's 15 s), and its webhook carries no
retry policy (measured 20 Nov: both WhatsApp senders' URLs have no #rp=, so a non-2xx would never be redelivered) — Tyler, 20 Nov: Sasha
redelivers. THE ONE REDELIVERER: the same message (its MessageSid, as Twilio gave it) through the same path (inbound_phone._whatsapp), on
a backoff, until AgAPI decides — at most a day (WhatsApp's own reply window); nothing is ever composed for it meanwhile. Kept durably
(wa_redeliver, sql/061) so a restart doesn't lose it; the row goes the moment AgAPI decides (it holds the person's words).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("booking_signer.redeliver")

BACKOFF_S = (30, 120, 600, 1800, 3600, 7200, 14400, 28800)   # then every 8 h, until MAX_AGE_S
MAX_AGE_S = 24 * 3600
SWEEP_EVERY_S = 15
_MEM: Dict[str, dict] = {}   # message_sid → {payload, attempts, why, next_at, created_at} — no database, or the table not there yet


def _run():
    from . import guest_whatsapp as GW
    return getattr(GW.STORE, "_run", None)


def _next(attempts: int, now: float) -> float:
    return now + BACKOFF_S[min(attempts, len(BACKOFF_S) - 1)]


async def hold(sid: str, p: Dict[str, Any], why: Optional[str]) -> None:
    """AgAPI didn't decide this message: delivered again later (its attempts counted). Never an answer."""
    now = time.time()
    payload = {k: v for k, v in (p or {}).items() if isinstance(v, (str, int, float, bool)) or v is None}
    run = _run()
    if run is not None:
        try:
            await run(lambda c: c.execute(
                "insert into wa_redeliver (message_sid, payload, attempts, why, next_at) values ($1, $2, 0, $3, to_timestamp($4)) "
                "on conflict (message_sid) do update set attempts = wa_redeliver.attempts + 1, why = excluded.why, "
                "next_at = to_timestamp($5 + (array[30,120,600,1800,3600,7200,14400,28800])[least(wa_redeliver.attempts + 1, 8)])",
                sid, payload, str(why or "")[:80], _next(0, now), now))
            log.warning("[redeliver] …%s undecided by AgAPI (%s): delivered again later — nothing answered", sid[-8:], why)
            return
        except Exception as e:   # the table isn't there (sql/061 not applied) or the database failed: kept in this process — NAMED
            log.error("[redeliver] …%s not kept durably (%s) — kept in this process only", sid[-8:], type(e).__name__)
    r = _MEM.get(sid)
    attempts = (r["attempts"] + 1) if r else 0
    _MEM[sid] = {"payload": payload, "attempts": attempts, "why": why, "next_at": _next(attempts, now),
                 "created_at": (r or {}).get("created_at", now)}
    log.warning("[redeliver] …%s undecided by AgAPI (%s): delivered again later — nothing answered", sid[-8:], why)


async def done(sid: str) -> None:
    """AgAPI decided this message (its owner answers it): nothing more to deliver."""
    _MEM.pop(sid, None)
    run = _run()
    if run is not None:
        try:
            await run(lambda c: c.execute("delete from wa_redeliver where message_sid = $1", sid))
        except Exception as e:
            log.info("[redeliver] …%s not cleared durably (%s)", sid[-8:], type(e).__name__)


async def due(now: Optional[float] = None) -> List[dict]:
    """→ [{sid, payload, attempts, age_s}] whose time has come."""
    now = time.time() if now is None else now
    out = [{"sid": s, "payload": r["payload"], "attempts": r["attempts"], "age_s": now - r["created_at"]}
           for s, r in _MEM.items() if r["next_at"] <= now]
    run = _run()
    if run is not None:
        try:
            rows = await run(lambda c: c.fetch(
                "select message_sid, payload, attempts, extract(epoch from (now() - created_at)) as age_s from wa_redeliver "
                "where next_at <= now() order by next_at limit 20"))
            out += [{"sid": r["message_sid"], "payload": json.loads(r["payload"]) if isinstance(r["payload"], str) else dict(r["payload"]),
                     "attempts": r["attempts"], "age_s": float(r["age_s"])} for r in rows]
        except Exception as e:
            log.info("[redeliver] the durable list wasn't read (%s)", type(e).__name__)
    return out


async def sweep_once(now: Optional[float] = None) -> int:
    """Each due message through the ONE inbound path again (AgAPI asked afresh). Past a day: given up — logged, never answered."""
    from . import inbound_phone as IP
    n = 0
    for d in await due(now):
        p = d["payload"]
        if d["age_s"] > MAX_AGE_S:
            log.error("[redeliver] …%s: AgAPI never decided whose message it was in %d attempts over a day — not answered (FOR CR)",
                      d["sid"][-8:], d["attempts"] + 1)
            await done(d["sid"])
            continue
        channel, sender = IP._channel_and_number(p.get("From", ""))
        await IP._whatsapp(p, channel, sender, p.get("Body", ""), d["sid"], None)
        n += 1
    return n


_task: Optional[asyncio.Task] = None


async def _forever() -> None:
    while True:
        try:
            n = await sweep_once()
            if n:
                log.info("[redeliver] %d message(s) delivered again to AgAPI", n)
        except Exception as e:
            log.error("[redeliver] sweep failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(SWEEP_EVERY_S)


def start() -> None:
    global _task
    if os.getenv("SASHA_REDELIVER_LOOP", "1") == "1" and _task is None and os.getenv("DATABASE_URL", "").strip():
        _task = asyncio.ensure_future(_forever())


__all__ = ["hold", "done", "due", "sweep_once", "start", "BACKOFF_S", "MAX_AGE_S"]
