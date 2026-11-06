"""Sasha 350 · EVERY WhatsApp message Kanoe receives, for ANY tool, shows it's being worked on from its arrival until its reply lands.

ONE place: inbound_phone.sms, where every WhatsApp message first arrives, starts a HOLD on its MessageSid at once — AgAPI's one typing
sender (CR 174: messages.typing {message_id}, Twilio's Typing Indicators; only on a message this account's inbound op has seen; the dots
last until a reply or 25 s, and AgAPI keeps no timer). The hold refreshes every REFRESH_S, tied to THAT message, and ends when its reply
leaves:
  · the webhook's own answer (a TwiML reply, AgAPI having answered in its op, nothing to say) → settle(sid) as the webhook returns;
  · a guest's turn running in the background → keep(key) marks it, and its reply leaving (guest_whatsapp.deliver — every reply, its failure
    told too) → stop_for(key);
  · never longer than CAP_S (a lost reply never leaves dots forever).
No typing call anywhere else, no second sender, no "working on it…" text. Every call is logged with Twilio's status.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

log = logging.getLogger("booking_signer.wa_working")


def _trail(msg: str, *a) -> None:
    """Every call, said where production shows it (the service's log prints warnings and print lines only — found closing Sasha 350:
    the info lines never reached Railway's log); and to the logger, for tests."""
    line = msg % a if a else msg
    print(line, flush=True)
    log.info(line)

REFRESH_S = 20.0                       # Twilio's dots last 25 s: refreshed before they lapse
FIRST_TRIES = (0.0, 0.3, 0.6, 1.0, 2.0, 3.5)   # until AgAPI's inbound op has recorded the message (it does so first thing)
CAP_S = 300.0                          # a reply that never comes: the dots stop anyway
CALL: Any = None                       # tests replace it: async (message_id) -> {"ok", "status", "error"?}

_HOLDS: Dict[str, Dict[str, Any]] = {}  # MessageSid → {"key", "task", "kept", "at"}


async def _typing(sid: str) -> Dict[str, Any]:
    """AgAPI's ONE typing sender (CR 174), logged with Twilio's status — never a second sender."""
    try:
        if CALL is not None:
            r = await CALL(sid)
        else:
            from agapi import venue_submit as VS
            r = await VS._call(None, "messages.typing", {"message_id": sid})
            r = {"ok": bool(r.get("ok")), **(r.get("result") or {}), **({"error": r["error"]} if r.get("error") else {})}
    except Exception as e:
        r = {"ok": False, "error": {"code": type(e).__name__}}
    err = r.get("error") or {}
    _trail("[wa_working] typing on …%s → %s%s", sid[-8:], r.get("status") if r.get("ok") else "refused",
             f" ({err.get('code')}: {str(err.get('message') or '')[:120]})" if err else "")
    return r


async def _hold(sid: str) -> None:
    t0 = time.monotonic()
    shown = False
    for wait in FIRST_TRIES:   # at once — and again while AgAPI's inbound op records the message
        if wait:
            await asyncio.sleep(wait)
        r = await _typing(sid)
        if r.get("ok"):
            shown = True
            break
        if (r.get("error") or {}).get("code") != "not_found":
            break
    if not shown:
        _trail("[wa_working] …%s: no dots (AgAPI never saw this message, or refused it)", sid[-8:])
        return
    while time.monotonic() - t0 < CAP_S:
        await asyncio.sleep(REFRESH_S)
        if sid not in _HOLDS:
            return
        await _typing(sid)
    _trail("[wa_working] …%s: no reply after %ds — the dots stop", sid[-8:], int(CAP_S))


def start(key: str, sid: str) -> bool:
    """A message arrived: its hold, at once. A Twilio retry of the same message is the same hold (False). A newer message from the same
    person supersedes the older's hold (Twilio shows the dots on the last message; the reply answers them all)."""
    if not sid or sid in _HOLDS:
        return False
    for old in [s for s, h in _HOLDS.items() if h["key"] == key]:
        _end(old, "a newer message")
    try:
        task = asyncio.get_running_loop().create_task(_hold(sid))
    except RuntimeError:
        return False
    _HOLDS[sid] = {"key": key, "task": task, "kept": False, "at": time.monotonic()}
    task.add_done_callback(lambda _t, s=sid: _HOLDS.pop(s, None) if _HOLDS.get(s, {}).get("task") is _t else None)
    return True


def keep(key: str) -> None:
    """A guest's turn answers in the background: the hold stays until that reply leaves (stop_for)."""
    for h in _HOLDS.values():
        if h["key"] == key:
            h["kept"] = True


def settle(sid: str) -> None:
    """The webhook returns: its reply has left with it (or AgAPI's, in its op) — unless a background turn answers it (kept)."""
    h = _HOLDS.get(sid)
    if h and not h["kept"]:
        _end(sid, "answered")


def stop_for(key: str) -> None:
    """A reply to this person is leaving (guest_whatsapp.deliver): every hold of theirs ends."""
    for sid in [s for s, h in _HOLDS.items() if h["key"] == key]:
        _end(sid, "the reply left")


def _end(sid: str, why: str) -> None:
    h = _HOLDS.pop(sid, None)
    if h:
        h["task"].cancel()
        _trail("[wa_working] …%s: dots stopped (%s, after %.1fs)", sid[-8:], why, time.monotonic() - h["at"])


def holding(key: Optional[str] = None) -> int:
    return sum(1 for h in _HOLDS.values() if key is None or h["key"] == key)


__all__ = ["start", "keep", "settle", "stop_for", "holding", "REFRESH_S", "CAP_S"]
