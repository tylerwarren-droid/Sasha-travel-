"""Sasha 303 · THE ONE GATE for her live face (HeyGen LiveAvatar, billed by the minute) — docs/sasha/s303-avatar-gate.md.

Every avatar session is opened, held and closed HERE, and nowhere else:
  open(account, surface, why)   the only yes: a REAL signed-in person (never a guest, a test or scratch account, the demo account),
                                pressing to talk on /s2 (why "tap"), under his minutes today and Kanoe's — or a refusal ({rule, say})
  opened(account, sid, token)   the session token minted for that yes (frontend/lib/avatar-mint.ts, the one minting function, called
                                only after open) is handed here at once; a token for a sid this gate didn't open is STOPPED
  beat / touch                  the page says it is open, visible, talking (his mic, her lines); his turn (/api/agent/turn) touches it
  close(account, sid, why)      camera off, leaving, hidden — POST /v1/sessions/stop with the session's own token
  reap()                        every REAP_S on the server: quiet (QUIET_S with nobody talking), lost (no beat for LOST_S: the tab
                                closed), a mint that never came, a cap reached — the page keeps no timer of its own
The caps are Railway settings (SASHA_AVATAR_PERSON_MIN_DAY, SASHA_AVATAR_KANOE_MIN_DAY, minutes); unset → 0 → no avatar.
The day's seconds are the gate's own ledger (sasha_avatar_day, SQL 045; this process's copy while the table isn't there) — the
measures row (kind avatar) is the LOG, written at close, never read here (S275: measures are never an authority).
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("app.avatar_gate")

QUIET_S = 60          # nobody talking this long → closed (Sasha 303 item 2)
LOST_S = 30           # no beat from the page this long → its tab is gone
MINT_S = 20           # a yes whose token never arrived → dropped
REAP_S = 5
SURFACES = {"s2": ("tap",)}   # the only surface and reason that open a session
STOP_URL = "https://api.liveavatar.com/v1/sessions/stop"
CAP_LINE = "I've turned my video off for today, but I'm still here by voice and text."
TZ = ZoneInfo("Europe/Madrid")
try:
    from app.services.accounts import DEMO_ACCOUNT_ID as DEMO
except Exception:   # pragma: no cover
    DEMO = "00000000-0000-0000-0000-000000000000"

_OPEN: Dict[str, Dict[str, Any]] = {}    # sid → the session: account, surface, why, opened, last_talk, last_beat, token, session_id
_DAY: Dict[str, float] = {}             # "day|account" and "day|*" → closed seconds (this process's copy of the ledger)
_LOADED: set = set()


def NOW() -> float:   # tests replace it
    return time.time()


async def _stop(token: str) -> bool:
    from booking_signer.http_pool import request
    try:
        r = await request("POST", STOP_URL, timeout=8.0, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        return r.status_code < 300
    except Exception as e:
        log.warning("[avatar] stop not confirmed: %s", type(e).__name__)
        return False


async def _meta(account: str) -> Optional[dict]:
    """The account's app_metadata (None: no such user / unreadable — then it isn't a person the gate knows)."""
    from booking_signer import ops
    try:
        st, u = await ops.ADMIN("GET", f"/admin/users/{account}", None)
    except Exception as e:
        log.warning("[avatar] account not read: %s", type(e).__name__)
        return None
    return ((u or {}).get("app_metadata") or {}) if st == 200 else None


async def _log(row: dict) -> None:
    from agapi import measure as MS
    MS.avatar(row)


async def _ledger_load(day: str) -> Dict[str, float]:
    from agapi import s2_memory as M
    run = M._run()
    if run is None:
        return {}
    try:
        rows = await run(lambda c: c.fetch("select account, seconds from sasha_avatar_day where day = $1::date",
                                           datetime.strptime(day, "%Y-%m-%d").date()))
        return {f"{day}|{r['account']}": float(r["seconds"]) for r in rows}
    except Exception as e:   # before SQL 045: this process's copy only
        log.info("[avatar] ledger not read: %s", type(e).__name__)
        return {}


async def _ledger_save(day: str, key: str, seconds: float) -> None:
    from agapi import s2_memory as M
    run = M._run()
    if run is None:
        return
    try:
        await run(lambda c: c.execute(
            "insert into sasha_avatar_day (day, account, seconds) values ($1::date, $2, $3) "
            "on conflict (day, account) do update set seconds = sasha_avatar_day.seconds + excluded.seconds",
            datetime.strptime(day, "%Y-%m-%d").date(), key, int(round(seconds))))
    except Exception as e:
        log.info("[avatar] ledger not written: %s", type(e).__name__)


STOP: Callable[[str], Awaitable[bool]] = _stop
META: Callable[[str], Awaitable[Optional[dict]]] = _meta
LOG: Callable[[dict], Awaitable[None]] = _log
LEDGER_LOAD: Callable[[str], Awaitable[Dict[str, float]]] = _ledger_load
LEDGER_SAVE: Callable[[str, str, float], Awaitable[None]] = _ledger_save


def reset() -> None:
    _OPEN.clear()
    _DAY.clear()
    _LOADED.clear()


def open_count() -> int:
    return len(_OPEN)


def _day(t: Optional[float] = None) -> str:
    return datetime.fromtimestamp(NOW() if t is None else t, timezone.utc).astimezone(TZ).strftime("%Y-%m-%d")


def caps() -> Dict[str, float]:
    """Seconds a day: his, and Kanoe's — from the server's settings; unset or unreadable → 0 (no avatar)."""
    def minutes(name: str) -> float:
        try:
            return max(0.0, float((os.getenv(name) or "").strip()))
        except ValueError:
            return 0.0
    return {"person": minutes("SASHA_AVATAR_PERSON_MIN_DAY") * 60.0, "kanoe": minutes("SASHA_AVATAR_KANOE_MIN_DAY") * 60.0}


def _who(account: str) -> str:
    from agapi import measure as MS
    return MS.h(account) or ""


async def _ledger(day: str) -> None:
    if day not in _LOADED:
        _LOADED.add(day)
        for k, v in (await LEDGER_LOAD(day)).items():
            _DAY[k] = max(_DAY.get(k, 0.0), v)


def _used(day: str, key: str) -> float:
    """Seconds today: closed (the ledger) + the open sessions' running time."""
    now = NOW()
    running = sum(now - s["opened"] for s in _OPEN.values() if s.get("token") and (key == "*" or s["account"] == key))
    return _DAY.get(f"{day}|{key}", 0.0) + running


def _over(day: str, account: str) -> Optional[str]:
    c = caps()
    if _used(day, "*") >= c["kanoe"]:
        return "cap_kanoe"
    if _used(day, account) >= c["person"]:
        return "cap_person"
    return None


async def is_person(account: Optional[str]) -> bool:
    """A real signed-in person: an account (never the demo / anonymous one) whose record carries no guest or test marker."""
    if not account or account == DEMO:
        return False
    meta = await META(account)
    return meta is not None and not meta.get("kanoe_guest") and not meta.get("kanoe_test")


async def open(account: Optional[str], surface: str, why: str) -> Dict[str, Any]:
    if surface not in SURFACES or why not in SURFACES[surface]:
        return {"ok": False, "rule": "not_a_tap"}
    if not await is_person(account):
        return {"ok": False, "rule": "not_a_person"}
    day = _day()
    await _ledger(day)
    over = _over(day, account)
    if over:
        return {"ok": False, "rule": over, "say": CAP_LINE}
    for sid, s in list(_OPEN.items()):   # one live face per person: a new tap replaces the old one
        if s["account"] == account:
            await _close(sid, "replaced")
    sid = "av_" + secrets.token_hex(8)
    now = NOW()
    _OPEN[sid] = {"account": account, "surface": surface, "why": why, "opened": now, "last_talk": now, "last_beat": now,
                  "token": None, "session_id": None}
    return {"ok": True, "sid": sid}


async def opened(account: Optional[str], sid: str, token: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    s = _OPEN.get(sid)
    if not s or s["account"] != account or s.get("token"):
        if token:
            await STOP(token)   # a session the gate didn't open never runs
        log.warning("[avatar] a session token for a sid the gate didn't open — stopped")
        return {"ok": False, "rule": "not_opened_here"}
    now = NOW()
    s.update({"token": token, "session_id": session_id, "opened": now, "last_talk": now, "last_beat": now})
    return {"ok": True, "sid": sid, "quiet_s": QUIET_S}


async def beat(account: Optional[str], sid: str, talking: bool = False, visible: bool = True) -> Dict[str, Any]:
    s = _OPEN.get(sid)
    if not s or s["account"] != account:
        return {"ok": False, "rule": "closed"}
    if not visible:
        await _close(sid, "hidden")
        return {"ok": False, "rule": "closed", "why": "hidden"}
    now = NOW()
    s["last_beat"] = now
    if talking:
        s["last_talk"] = now
    return {"ok": True}


def touch(account: Optional[str]) -> None:
    """His turn reached the server: he is talking (and here)."""
    now = NOW()
    for s in _OPEN.values():
        if s["account"] == account:
            s["last_talk"] = s["last_beat"] = now


async def close(account: Optional[str], sid: str, why: str) -> Dict[str, Any]:
    s = _OPEN.get(sid)
    if not s or s["account"] != account:
        return {"ok": True, "already": True}
    await _close(sid, str(why or "closed")[:24])
    return {"ok": True}


async def _close(sid: str, why: str) -> None:
    s = _OPEN.pop(sid, None)
    if not s:
        return
    now = NOW()
    secs = (now - s["opened"]) if s.get("token") else 0.0
    if s.get("token"):
        await STOP(s["token"])
        day = _day(s["opened"])
        for key in (s["account"], "*"):
            _DAY[f"{day}|{key}"] = _DAY.get(f"{day}|{key}", 0.0) + secs
            await LEDGER_SAVE(day, key, secs)
    row = {"who": _who(s["account"]), "surface": s["surface"], "opened_why": s["why"],
           "opened_at": datetime.fromtimestamp(s["opened"], timezone.utc).isoformat(),
           "closed_at": datetime.fromtimestamp(now, timezone.utc).isoformat(), "seconds": int(round(secs)),
           "closed_why": why if s.get("token") else "never_started"}
    log.info("[avatar] closed (%s) after %ss", row["closed_why"], row["seconds"])
    try:
        await LOG(row)
    except Exception as e:
        log.warning("[avatar] not logged: %s", type(e).__name__)


async def reap() -> None:
    now = NOW()
    day = _day()
    for sid, s in list(_OPEN.items()):
        if not s.get("token"):
            if now - s["opened"] > MINT_S:
                await _close(sid, "never_started")
            continue
        why = ("quiet" if now - s["last_talk"] > QUIET_S else "lost" if now - s["last_beat"] > LOST_S else _over(day, s["account"]))
        if why:
            await _close(sid, why)


def today() -> Dict[str, Any]:
    day = _day()
    c = caps()
    return {"day": day, "seconds": int(round(_used(day, "*"))), "open": sum(1 for s in _OPEN.values() if s.get("token")),
            "cap_person_min": c["person"] / 60.0, "cap_kanoe_min": c["kanoe"] / 60.0}


async def reaper_forever() -> None:
    while True:
        await asyncio.sleep(REAP_S)
        try:
            await reap()
        except Exception as e:   # never dies: a missed pass is caught on the next
            log.warning("[avatar] reap failed: %s", type(e).__name__)


# ── the routes: /api/avatar/* — called by the frontend's server routes only (agentHeaders: the person's own sign-in) ──────────
router = APIRouter(prefix="/api/avatar", tags=["avatar"])


async def _account(request: Request) -> Optional[str]:
    from app.services.chat_account import chat_account
    return await chat_account(request, anonymous=None)


async def _body(request: Request) -> dict:
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


@router.post("/open")
async def r_open(request: Request):
    b = await _body(request)
    r = await open(await _account(request), str(b.get("surface") or ""), str(b.get("why") or ""))
    return r if r["ok"] else JSONResponse(r, status_code=403)


@router.post("/opened")
async def r_opened(request: Request):
    b = await _body(request)
    r = await opened(await _account(request), str(b.get("sid") or ""), str(b.get("token") or ""), b.get("session_id"))
    return r if r["ok"] else JSONResponse(r, status_code=409)


@router.post("/beat")
async def r_beat(request: Request):
    b = await _body(request)
    return await beat(await _account(request), str(b.get("sid") or ""), bool(b.get("talking")), b.get("visible") is not False)


@router.post("/close")
async def r_close(request: Request):
    b = await _body(request)
    return await close(await _account(request), str(b.get("sid") or ""), str(b.get("why") or "closed"))


@router.get("/today")
async def r_today(request: Request):
    from booking_signer import guest_accounts as GA
    if not GA.founder(await _account(request)):
        return JSONResponse({"ok": False, "rule": "founder_only"}, status_code=403)
    return {"ok": True, **today()}


@router.on_event("startup")
async def _start() -> None:
    asyncio.create_task(reaper_forever())
