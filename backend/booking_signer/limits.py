"""Sasha 120 · PER-GUEST limits, and the per-guest calls switch — before guest sign-up opens.

Limits (per account, sliding windows, the founder's account exempt):
  · venue search  — each is a paid Google Places request:       SASHA_FINDS_PER_HOUR (30), SASHA_FINDS_PER_DAY (150)
  · venue reads   — the venue's own site and its listing:        SASHA_READS_PER_HOUR (60)
  · form sends    — a real submission to a venue's booking form: SASHA_FORMS_PER_DAY (10)
Over a limit: 429 with the plain reason; nothing is contacted. Held in this server's memory: a redeploy starts the
windows again (a cap on abuse, not an audit; the call and email caps stay in the database).

Calls for guests: OFF unless the founder switches them on for that account (SASHA_CALLS_ACCOUNTS, a comma-separated
list of account ids) — until the confirmation rate is proven. The founder's own account is always on (when calls are).
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

from fastapi.responses import JSONResponse

_HOUR, _DAY = 3600, 86400
_HITS: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
LIMITS = {"find": (("SASHA_FINDS_PER_HOUR", 30, _HOUR), ("SASHA_FINDS_PER_DAY", 150, _DAY)),
          "read": (("SASHA_READS_PER_HOUR", 60, _HOUR),),
          "form_send": (("SASHA_FORMS_PER_DAY", 10, _DAY),)}
WORDS = {"find": "searches", "read": "venue look-ups", "form_send": "booking forms sent"}
NOW = time.monotonic


def _n(env: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(env, str(default))))
    except ValueError:
        return default


def exempt(account: str) -> bool:
    from .identity import founder_account
    return account == founder_account()


def check(account: str, kind: str) -> Optional[JSONResponse]:
    """None (counted) or the 429. Counted only when allowed."""
    if exempt(account):
        return None
    q, now = _HITS[(account, kind)], NOW()
    while q and now - q[0] > _DAY:
        q.popleft()
    for env, default, window in LIMITS[kind]:
        cap = _n(env, default)
        if sum(1 for t in q if now - t <= window) >= cap:
            per = "hour" if window == _HOUR else "day"
            return JSONResponse({"ok": False, "rule": "account_rate_limit",
                                 "message": f"you've reached {cap} {WORDS[kind]} this {per} — try again later; nothing was contacted"},
                                status_code=429)
    q.append(now)
    return None


def calls_on(account: Optional[str]) -> bool:
    """May THIS account have Sasha phone venues? The founder's: yes. A guest's: only once the founder lists it."""
    if account is None:
        return True
    from .identity import founder_account
    listed = {a.strip().lower() for a in os.getenv("SASHA_CALLS_ACCOUNTS", "").split(",") if a.strip()}
    return account == founder_account() or account.lower() in listed


CALLS_OFF_FOR_ACCOUNT = "phone calls aren't switched on for your account yet — Sasha can use their booking form or email instead"


def reset() -> None:
    _HITS.clear()


__all__ = ["check", "calls_on", "CALLS_OFF_FOR_ACCOUNT", "reset", "LIMITS"]
