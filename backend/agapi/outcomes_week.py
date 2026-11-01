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


async def week(days: int = 7, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # AgAPI's report groups by its own fields only (rung · sector · city — "by":["channel"] was refused at /by/0, 3c3a70e's log): per
    # channel = per rung (AgAPI's channel family: request_reply · phone · zero_touch · human_tap · api), per kind = per sector
    rep = await CALL("outcomes.report", {"from": since, "by": ["kind", "channel", "rung", "sector"]})   # CR 155 · kind and channel too
    if not rep.get("ok"):
        return {"ok": False, "why": (rep.get("error") or {}).get("message") or "the outcomes ledger didn't answer",
                "say": "I couldn't read this week's bookings — " + ((rep.get("error") or {}).get("message") or "the ledger didn't answer") + "."}
    r = rep["result"]
    lst = await CALL("outcomes.list", {"from": since, "limit": 1000})
    rows = [x for x in ((lst.get("result") or {}).get("outcomes") or []) if not x.get("test")] if lst.get("ok") else []
    outcomes: Dict[str, int] = {}
    for x in rows:
        k = classify(x, now)
        outcomes[k] = outcomes.get(k, 0) + 1
    un = await CALL("venue.unhandled", {"since": since[:10]})
    unhandled = (un.get("result") or {}) if un.get("ok") else {}
    items = unhandled.get("items") or []   # AgAPI's shape: {count, items: [{kind_guess, request, why, at}], table}
    by_kind: Dict[str, int] = {}
    for it in items:
        k = str(it.get("kind_guess") or "unknown")
        by_kind[k] = by_kind.get(k, 0) + 1
    o = r.get("overall") or {}
    out = {"ok": True, "window": {"from": since, "days": days}, "count": int(o.get("attempts") or 0), "overall": o,
           "outcomes": outcomes, "no_answer": outcomes.get("no_answer", 0), "handed_to_tyler": int(o.get("handed_to_person") or 0),
           "by_kind_of_attempt": r.get("by_kind") or [], "by_rung": r.get("by_rung") or [],
           "by_channel": r.get("by_channel") or [], "by_kind": r.get("by_sector") or [], "excluded_test": r.get("excluded_test", 0),
           "unhandled": {"count": unhandled.get("count", sum(by_kind.values())), "by_kind": by_kind,
                         "items": [{k: it.get(k) for k in ("kind_guess", "request", "why", "at") if it.get(k) is not None} for it in items[:20]]}}
    out["say"] = line(out)
    return out


def line(w: Dict[str, Any]) -> str:
    """The week in one line, numbers only — every figure from AgAPI's ledger (CR 155: hand-offs and changes / cancels are its own rows)."""
    if not w.get("ok"):
        return w.get("say") or "This week's bookings couldn't be read."
    kinds = {str(k.get("kind")): k for k in w.get("by_kind_of_attempt") or []}
    bk = kinds.get("booking") or w.get("overall") or {}
    rate = f"{round(bk['success_rate'] * 100)}% of those decided confirmed" if bk.get("success_rate") is not None else "none decided yet"
    ch = "; ".join(f"{c.get('channel')}: {c.get('confirmed', 0)}/{c.get('attempts', 0)}" for c in (w.get("by_channel") or [])[:8])
    other = "; ".join(f"{n} {k.get('attempts', 0)} ({k.get('confirmed', 0)} done, {k.get('handed_to_person', 0)} handed to Tyler, "
                      f"{k.get('open', 0)} open)" for n, k in (("changes", kinds.get("change")), ("late notices", kinds.get("late")),
                                                               ("cancels", kinds.get("cancel"))) if k)
    return (f"{bk.get('attempts', 0)} real booking(s) in the last {w['window']['days']} days — {bk.get('confirmed', 0)} confirmed, "
            f"{bk.get('declined', 0)} declined, {bk.get('failed', 0)} failed, {bk.get('handed_to_person', 0)} handed to Tyler, "
            f"{w.get('no_answer', 0)} no answer yet, {bk.get('open', 0)} still open; {rate}."
            + (f" Changes and cancels: {other}." if other else " No changes or cancels.")
            + (f" By channel (confirmed/asked, every kind): {ch}." if ch else "")
            + f" Couldn't handle: {w['unhandled']['count']}." + (f" ({w['excluded_test']} test attempt(s) left out.)" if w.get("excluded_test") else ""))


__all__ = ["WAIT_H", "classify", "week", "line"]
