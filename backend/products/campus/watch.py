"""CR 1 · "Yale hasn't published April yet — I'll tell you the day it opens."

Once a day (CAMPUSME_WATCH_LOOP=1; off in tests and by default) each open watch reads its schools' calendars for the
month — one request per school, paced like every read — and when the month has dates, the family is told on WhatsApp
and the watch closes. ⚠ WhatsApp lets us write first only inside 24 hours of their last message (no approved template
in the sandbox), so outside that window the news waits: it's sent in reply to their next message instead, and the
health route reports it as held.
"""
from __future__ import annotations

import asyncio
import calendar
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from .. import store as ST
from . import schools as SC
from . import slate as SL

log = logging.getLogger("products.campus.watch")
EVERY = timedelta(hours=24)
_TASK: Optional[asyncio.Task] = None


def running() -> bool:
    return bool(_TASK and not _TASK.done())


async def check(case: dict, reader: Optional[SL.Reader] = None) -> List[str]:
    """The names of the watched schools whose month is now published (empty: still waiting)."""
    w = case["state"]["watch"]
    y, m = w["month"]
    start, end = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    opened = []
    for k in w["schools"]:
        s = SC.SCHOOLS.get(k)
        if not s or not s.get("proven"):
            continue
        try:
            ds, _ = await SL.dates(s, start, end, reader)
        except SL.ReadRefused as e:
            log.info("[campus.watch] %s not read: %s", k, e)
            continue
        if any(ok and start.isoformat() <= d <= end.isoformat() for d, ok in ds):   # only the watched month counts
            opened.append(s["name"])
    return opened


async def tick(now: Optional[datetime] = None, reader: Optional[SL.Reader] = None) -> int:
    from booking_signer import guest_whatsapp as GW
    told = 0
    for case in await ST.STORE.watching():
        opened = await check(case, reader)
        if not opened:
            continue
        w = case["state"]["watch"]
        y, m = w["month"]
        month = date(y, m, 1).strftime("%B %Y")
        text = (f"🎓 CampusMe: {' and '.join(opened)} just published {month} visit dates. Say \"campus "
                f"{' and '.join(opened)} {date(y, m, 1).strftime('%B')}\" and I'll show you the sessions.")
        from .. import whatsapp as PW
        ch, wkey, frm = await PW.reach(w["wa"], w["number_from"], case.get("account_id"))   # CR 20
        st = await GW.STORE.get_state(wkey) if ch else {}
        sent = await GW.deliver(ch, frm, GW.Out().text(text), st.get("last_inbound_at")) if ch else ["no channel"]
        state = case["state"]
        if sent and all(r == "sent" for r in sent):
            state["watch"]["open"] = False
            state["watch"]["told_at"] = (now or datetime.now(timezone.utc)).isoformat()
            told += 1
        else:
            state["watch"]["held"] = sent
        await ST.STORE.update(case["id"], state)
    return told


async def _forever() -> None:
    while True:
        try:
            await tick()
        except Exception as e:
            log.error("[campus.watch] tick failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(EVERY.total_seconds())


def start() -> None:
    global _TASK
    if os.getenv("CAMPUSME_WATCH_LOOP", "").strip() == "1" and not running():
        _TASK = asyncio.ensure_future(_forever())
