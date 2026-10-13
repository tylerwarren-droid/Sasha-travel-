"""Sasha 254 · item 5 — ACCESS FROM THE ONE RECORD (CR 92, mailbox row 823): who may do what is AgAPI's person_access record,
read through access.get on agapi-LIVE (the record lives there, whatever a person's mode routes their calls to). This module is
the ONE reader; every founder / calls / mailbox / demo / real-venue / mode decision in Sasha reads it (app.services.accounts,
booking_decide.access_of, agapi_route.person_mode, guest_accounts, s2_tools, outlook).

  get(account)      async: users.register (external_ref "sasha:<account>", the end user cached) → access.get → the record,
                    cached per account for TTL_S (≤ 60 s). ANY failure (no key, unreachable, an error, a malformed answer) →
                    CLOSED, not cached (retried after FAILED_TTL_S, 10 s).
  cached(account)   sync: the record last read (≤ 60 s old), else CLOSED — for the sync checks (is_founder, calls_on, …).
  warm(account)     async get that never raises — called wherever an account is resolved (chat_account, the WhatsApp turn,
                    the inner booking app, voice_turn, sasha.turn, the proactive sweep), so the sync checks read a fresh record.
  install({account: record}) / uninstall / records(...)   THE TEST HOOK: records put in place with no network and no expiry
                    (unit tests, and the gate's suites for their scratch guests, in-process only — never a real grant).

A person with no row (every guest session) reads CLOSED: test, everything off. The shape (normalised here, once):
  {mode: live|test, calls: on|off, real_venue_sends: on|off, mailboxes: [gmail, outlook…], demo: s2_demo|founder_rehearsal|None,
   founder: bool, real_money: on|off, email: str|None, source: person_access|closed|installed|…}
The key is never logged or printed."""
from __future__ import annotations

import contextlib
import json
import logging
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, Iterator, Optional, Tuple

log = logging.getLogger("agapi.person_access")

TTL_S = 60.0
FAILED_TTL_S = 10.0   # a failed read is closed and retried after this (not cached long: a down AgAPI never adds its timeout to every turn)
TIMEOUT_S = 5.0
CLOSED: Dict[str, Any] = {"mode": "test", "calls": "off", "real_venue_sends": "off", "mailboxes": [], "demo": None,
                          "founder": False, "real_money": "off", "email": None, "source": "closed"}

_CACHE: Dict[str, Tuple[Dict[str, Any], float]] = {}   # account → (record, read at)
_USERS: Dict[str, str] = {}                            # account → agapi-live end user
_FAILED: Dict[str, float] = {}                         # account → when its last read failed
_INSTALLED: Dict[str, Dict[str, Any]] = {}             # the test hook: account → record (no network, no expiry)
#: the test hook's fallback (tests/founder_fixture): account → record or None. Never set by the serving process.
RESOLVER: Optional[Callable[[str], Optional[dict]]] = None


def closed() -> Dict[str, Any]:
    return {**CLOSED, "mailboxes": []}


def _on(v: Any) -> str:
    return "on" if v is True or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 1) \
        or str(v).strip().lower() in ("on", "true", "yes", "1") else "off"


def _mailboxes(r: dict) -> list:
    v = r.get("mailboxes", r.get("mailbox"))
    if isinstance(v, str):
        v = [p for p in v.replace(";", ",").split(",")]
    if not isinstance(v, (list, tuple)):
        return []
    return sorted({str(p).strip().lower() for p in v if str(p).strip()})


def normalise(r: Optional[dict], source: Optional[str] = None) -> Dict[str, Any]:
    """Any record (access.get's result, or a test's) → the one shape. Unknown values read closed."""
    if not isinstance(r, dict):
        return closed()
    demo = r.get("demo")
    demo = str(demo).strip().lower() if demo not in (None, False, "", "off", "none") else None
    f = r.get("founder")
    return {"mode": "live" if str(r.get("mode") or "").strip().lower() == "live" else "test",
            "calls": _on(r.get("calls")), "real_venue_sends": _on(r.get("real_venue_sends")), "mailboxes": _mailboxes(r),
            "demo": demo, "founder": f is True or _on(f) == "on", "real_money": _on(r.get("real_money")),
            "email": (str(r.get("email")).strip().lower() or None) if r.get("email") else None,
            "source": str(source or r.get("source") or "person_access")}


def _key(account: Optional[str]) -> str:
    return str(account or "").strip().lower()


# ── the transport (agapi-live, its own key; tests replace CALL) ─────────────────────────────────────────────────────────────

async def _agapi(op: str, body: dict) -> Dict[str, Any]:
    from agapi import agapi_route as AR
    url, key = AR.endpoint("live")
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "the access record isn't readable here (no key)"}}
    import httpx
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": "s2pa_" + secrets.token_hex(12)}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S)) as c:
            r = await c.post(f"{url}/v1/{op}", headers=h, content=json.dumps(body))
        return r.json()
    except Exception as e:
        return {"ok": False, "error": {"code": "unreachable", "message": type(e).__name__}}


CALL: Callable[[str, dict], Awaitable[Dict[str, Any]]] = _agapi


def _local(k: str) -> Optional[Dict[str, Any]]:
    if k in _INSTALLED:
        return _INSTALLED[k]
    if RESOLVER is not None:
        r = RESOLVER(k)
        if r is not None:
            return normalise(r, r.get("source") or "installed")
    return None


async def _end_user(k: str) -> Optional[str]:
    if k in _USERS:
        return _USERS[k]
    r = await CALL("users.register", {"external_ref": f"sasha:{k}"})
    uid = ((r or {}).get("result") or {}).get("end_user_id") if (r or {}).get("ok") else None
    if uid:
        _USERS[k] = str(uid)
    else:
        log.warning("[person_access] no end user: %s", ((r or {}).get("error") or {}).get("code"))
    return _USERS.get(k)


async def get(account: Optional[str]) -> Dict[str, Any]:
    """The person's record (≤ 60 s old); CLOSED on any failure (not cached)."""
    k = _key(account)
    if not k:
        return closed()
    local = _local(k)
    if local is not None:
        return dict(local)
    hit = _CACHE.get(k)
    if hit and time.time() - hit[1] < TTL_S:
        return dict(hit[0])
    if time.time() - _FAILED.get(k, -1e18) < FAILED_TTL_S:
        return closed()
    try:
        uid = await _end_user(k)
        if not uid:
            _FAILED[k] = time.time()
            return closed()
        r = await CALL("access.get", {"end_user": uid})
        if not (r or {}).get("ok") or not isinstance(r.get("result"), dict):
            log.warning("[person_access] access not read (closed): %s", ((r or {}).get("error") or {}).get("code"))
            _FAILED[k] = time.time()
            return closed()
        rec = normalise(r["result"])
    except Exception as e:
        log.warning("[person_access] access not read (closed): %s", type(e).__name__)
        _FAILED[k] = time.time()
        return closed()
    _FAILED.pop(k, None)
    _CACHE[k] = (rec, time.time())
    return dict(rec)


def cached(account: Optional[str]) -> Dict[str, Any]:
    """SYNC: the record last read for this account (≤ 60 s), else CLOSED."""
    k = _key(account)
    if not k:
        return closed()
    local = _local(k)
    if local is not None:
        return dict(local)
    hit = _CACHE.get(k)
    if hit and time.time() - hit[1] < TTL_S:
        return dict(hit[0])
    return closed()


async def warm(account: Optional[str]) -> Dict[str, Any]:
    """get(), never raising: at every place an account is resolved."""
    try:
        return await get(account)
    except Exception as e:   # get() already closes on failure; this is the belt
        log.warning("[person_access] warm failed: %s", type(e).__name__)
        return closed()


# ── the test hook ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def install(records: Dict[str, dict]) -> None:
    """Put records in place (no network, no expiry): {account: {mode, calls, real_venue_sends, mailboxes, demo, founder, …}}."""
    for a, r in (records or {}).items():
        _INSTALLED[_key(a)] = normalise(r, (r or {}).get("source") or "installed")


def uninstall(*accounts: str) -> None:
    for a in accounts:
        _INSTALLED.pop(_key(a), None)


def clear() -> None:
    """Forget everything read or installed (tests)."""
    _CACHE.clear()
    _USERS.clear()
    _FAILED.clear()
    _INSTALLED.clear()


@contextlib.contextmanager
def records(recs: Dict[str, dict]) -> Iterator[None]:
    """with records({account: record}): … — installed for the block, the previous state restored after."""
    before = {k: _INSTALLED.get(k) for k in (_key(a) for a in recs)}
    install(recs)
    try:
        yield
    finally:
        for k, v in before.items():
            if v is None:
                _INSTALLED.pop(k, None)
            else:
                _INSTALLED[k] = v


#: the records CR's list (row 823) describes, as the tests and the gate's suites install them
LIVE_PERSON = {"mode": "live", "calls": "on", "real_venue_sends": "on", "mailboxes": ["gmail", "outlook"], "real_money": "off",
               "source": "installed"}
FOUNDER_PERSON = {**LIVE_PERSON, "founder": True}

__all__ = ["get", "cached", "warm", "install", "uninstall", "clear", "records", "normalise", "closed", "CLOSED", "TTL_S",
           "LIVE_PERSON", "FOUNDER_PERSON", "CALL", "RESOLVER"]
