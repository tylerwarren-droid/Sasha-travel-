"""Sasha 324 · THE WEEK, READ-ONLY — real bookings and their outcomes, from the ONE ledger (AgAPI's: each act records its own outcome; Sasha
adds only the attempts that ended before an act — docs/sasha/S-324-outcomes.md). Nothing here writes.

  WAIT_H            each channel's expected wait for an answer (one table): past it, an open attempt is "no answer" — read from the
                    ledger's own times, never stored
  classify(row,…)   one ledger row → confirmed · declined · failed (+why) · handed_to_tyler · no_answer · open
  week(days)        the outcomes family's AgAPI — LIVE in production (real people only: a test person's bookings go to the sandbox; AgAPI leaves out attempts marked test):
                    outcomes.report by channel and by kind (sector), outcomes.list for the "no answer" count, venue.unhandled with its
                    counts → {count, by_channel, by_kind, no_answer, unhandled, say}
  line(w)           the week in one line, numbers only (the log, the founder's tool)
"""
from __future__ import annotations
from kanoe_contract import OP  # Sasha 374 · THE ONE generated contract (CR 186)

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("agapi.outcomes_week")

#: each channel's expected wait for the venue's answer, in hours — None: his to finish (a page handed over), never "no answer"
WAIT_H: Dict[str, Optional[float]] = {"email": 24, "whatsapp": 12, "instagram": 24, "phone": 2, "web_form": 24, "api": 1,
                                      "page_handover": None, "handover": None}
#: the ledger's rung → its channel, when a row carries only the rung (outcomes.list)
RUNG_WAIT_H: Dict[str, Optional[float]] = {"request_reply": 24, "phone": 2, "zero_touch": 24, "api": 1, "human_tap": None}
OPEN = ("asked", "sent")


def _t(s: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def classify(row: Dict[str, Any], now: Optional[datetime] = None) -> str:
    """One ledger row → its outcome. "no answer": still open past its channel's (else its rung's) expected wait."""
    now = now or datetime.now(timezone.utc)
    st = str(row.get("state") or "")
    if st in ("confirmed", "declined"):
        return st
    if st == "handed_to_person":   # CR 155 · its own ending (a person of Kanoe's took it — Tyler)
        return "handed_to_tyler"
    if st == "failed":
        return "failed"
    if st in OPEN:
        wait = WAIT_H.get(str(row.get("channel") or ""), RUNG_WAIT_H.get(str(row.get("rung") or ""), 24))
        asked = _t(row.get("asked_at") or row.get("created_at"))
        if wait is not None and asked and now - asked > timedelta(hours=wait):
            return "no_answer"
    return "open"


async def _live(op: str, body: dict) -> Dict[str, Any]:
    """The outcomes family's AgAPI, as agapi_route routes it (production: LIVE — real people's bookings; the gate: the sandbox). Never a
    target chosen here (the one route table decides)."""
    from agapi import agapi_route as AR
    url, key = await AR.client_for("outcomes")
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "the outcomes ledger isn't switched on here"}}
    import secrets
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": "s2week_" + secrets.token_hex(12)}
    return await AR.post(url, key, op, body, h, 20.0)


CALL = _live   # tests replace it

#: the founder's record kind holding the day the real count began (Tyler says go: the start_count tool)
START_KIND = "real_count_from"
LIST_MAX = 500   # AgAPI's outcomes.list limit (its schema: 1–500) — 1,000 was refused, and "no answer yet" silently read 0


async def count_from() -> Optional[str]:
    """The day the real count began (YYYY-MM-DD), kept on the founder's record — None until Tyler starts it."""
    from app.services.accounts import founder_account
    from agapi import s2_memory as M
    acct = founder_account()
    v = await M.kind(acct, START_KIND) if acct else None
    return str(v)[:10] if v else None


async def start_count(day: str) -> str:
    from app.services.accounts import founder_account
    from agapi import s2_memory as M
    acct = founder_account()
    if not acct:
        raise RuntimeError("FOUNDER_ACCOUNT_ID isn't set")
    await M.put_kind(acct, START_KIND, day[:10])
    return day[:10]


async def _rows(since: str) -> tuple:
    """Every attempt from `since`, newest first, paged at AgAPI's own limit → (rows, None) or (rows so far, why it couldn't read)."""
    out: List[dict] = []
    until = None
    for _ in range(20):
        r = await CALL(OP.OUTCOMES_LIST, {"from": since, "limit": LIST_MAX, **({"to": until} if until else {})})
        if not r.get("ok"):
            return out, (r.get("error") or {}).get("message") or "outcomes.list didn't answer"
        page = (r.get("result") or {}).get("outcomes") or []
        out += page
        if len(page) < LIST_MAX:
            return out, None
        until = page[-1].get("created_at")
    return out, None


async def week(days: Optional[int] = None, now: Optional[datetime] = None, before_count: bool = False) -> Dict[str, Any]:
    """The REAL count, from its start (Tyler's go — start_count) to now; `days` narrows it to the last N days. Not started → {started: False,
    say: "count not started"}. before_count=True: the last `days` (default 7) regardless of the start — a diagnosis, never the count."""
    now = now or datetime.now(timezone.utc)
    start = None if before_count else await count_from()
    if not start and not before_count:
        return {"ok": True, "started": False, "say": "Real-booking count not started — Tyler says when (start_count)."}
    recent = (now - timedelta(days=days or 7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    since = recent if before_count else (max(f"{start}T00:00:00Z", recent) if days else f"{start}T00:00:00Z")
    rep = await CALL(OP.OUTCOMES_REPORT, {"from": since, "by": ["kind", "channel", "rung", "sector"]})   # CR 155 · kind and channel too
    if not rep.get("ok"):
        return {"ok": False, "started": True, "why": (rep.get("error") or {}).get("message") or "the outcomes ledger didn't answer",
                "say": "I couldn't read the real bookings — " + ((rep.get("error") or {}).get("message") or "the ledger didn't answer") + "."}
    r = rep["result"]
    rows, unread = await _rows(since)
    rows = [x for x in rows if not x.get("test")]
    outcomes: Dict[str, int] = {}
    for x in rows:
        k = classify(x, now)
        outcomes[k] = outcomes.get(k, 0) + 1
    un = await CALL(OP.VENUE_UNHANDLED, {"since": since[:10]})
    unhandled = (un.get("result") or {}) if un.get("ok") else {}
    items = unhandled.get("items") or []   # AgAPI's shape: {count, items: [{kind_guess, request, why, at}], table}
    by_kind: Dict[str, int] = {}
    for it in items:
        k = str(it.get("kind_guess") or "unknown")
        by_kind[k] = by_kind.get(k, 0) + 1
    o = r.get("overall") or {}
    out = {"ok": True, "started": True, "since": since, "window": {"from": since, "days": days}, "count": int(o.get("attempts") or 0), "overall": o,
           "outcomes": outcomes, "no_answer": outcomes.get("no_answer", 0), "no_answer_unread": unread,
           "handed_to_tyler": int(o.get("handed_to_person") or 0),
           "by_kind_of_attempt": r.get("by_kind") or [], "by_rung": r.get("by_rung") or [],
           "by_channel": r.get("by_channel") or [], "by_kind": r.get("by_sector") or [], "excluded_test": r.get("excluded_test", 0),
           "unhandled": {"count": unhandled.get("count", sum(by_kind.values())), "by_kind": by_kind,
                         "items": [{k: it.get(k) for k in ("kind_guess", "request", "why", "at") if it.get(k) is not None} for it in items[:20]]}}
    out["say"] = line(out)
    return out


def line(w: Dict[str, Any]) -> str:
    """The week in one line, numbers only — every figure from AgAPI's ledger (CR 155: hand-offs and changes / cancels are its own rows)."""
    if not w.get("ok") or not w.get("started"):
        return w.get("say") or "This week's bookings couldn't be read."
    kinds = {str(k.get("kind")): k for k in w.get("by_kind_of_attempt") or []}
    bk = kinds.get("booking") or w.get("overall") or {}
    rate = f"{round(bk['success_rate'] * 100)}% of those decided confirmed" if bk.get("success_rate") is not None else "none decided yet"
    ch = "; ".join(f"{c.get('channel')}: {c.get('confirmed', 0)}/{c.get('attempts', 0)}" for c in (w.get("by_channel") or [])[:8])
    other = "; ".join(f"{n} {k.get('attempts', 0)} ({k.get('confirmed', 0)} done, {k.get('handed_to_person', 0)} handed to Tyler, "
                      f"{k.get('open', 0)} open)" for n, k in (("changes", kinds.get("change")), ("late notices", kinds.get("late")),
                                                               ("cancels", kinds.get("cancel"))) if k)
    return (f"{bk.get('attempts', 0)} real booking(s) since {w['since'][:10]} — {bk.get('confirmed', 0)} confirmed, "
            f"{bk.get('declined', 0)} declined, {bk.get('failed', 0)} failed, {bk.get('handed_to_person', 0)} handed to Tyler, "
            + (f"no answer: not read ({w['no_answer_unread']}), " if w.get("no_answer_unread") else f"{w.get('no_answer', 0)} no answer yet, ")
            + f"{bk.get('open', 0)} still open; {rate}."
            + (f" Changes and cancels: {other}." if other else " No changes or cancels.")
            + (f" By channel (confirmed/asked, every kind): {ch}." if ch else "")
            + f" Couldn't handle: {w['unhandled']['count']}." + (f" ({w['excluded_test']} test attempt(s) left out.)" if w.get("excluded_test") else ""))


__all__ = ["WAIT_H", "classify", "week", "line", "count_from", "start_count"]


# Sasha 374 · CR 186 · a test double on CALL may never answer a field AgAPI doesn't publish (agapi/contract_shape.py)
from agapi import contract_shape as _CONTRACT_SHAPE  # noqa: E402
_CONTRACT_SHAPE.guard(__name__, 'CALL')
