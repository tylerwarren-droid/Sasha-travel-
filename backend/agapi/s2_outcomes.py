"""CR 87 · THE BOOKING OUTCOMES LEDGER, Sasha's side — every real booking attempt goes to AgAPI's outcomes.record, and is updated when
the venue's reply lands (outcomes.update). "We get any booking done", measured by outcomes.

  when         book_venue acts (after the person's yes): the attempt is recorded with the rung it used —
                 form → zero_touch (web_form) · handover / page → human_tap (page_handover) · draft → request_reply (whatsapp /
                 instagram) · email → request_reply (email) · call → phone (phone)
               and what happened at once: confirmed (the venue's page said so), sent (a request is out / the page is on their phone),
               or failed (with the reason).
  then         the reservation's own status, read from Sasha's records (each time her bookings are read, and every 10 minutes for the
               attempts still open): confirmed / guest_booked → confirmed (the venue's words quoted), declined → declined, failed /
               unreachable → failed, cancelled before any answer → failed ("cancelled before the venue answered").
  basket       Sasha 249 · a paid trip's flights and hotels too (basket_booked, from basket_book.book_paid): rung api, decided at once
  the key      ref = "sasha:<trip_item_id>" — the reservation's own id, so the update needs no table of its own.
  never        the customer's name, phone, email or card: only the venue, its sector and city, the rung, the channel and the times.

Where: SASHA_OUTCOMES_VIA = sandbox (default) | live. Keys: SASHA_AGAPI_TEST_KEY / SASHA_AGAPI_KEY. Never printed. A ledger that
doesn't answer never stops a booking: it is logged and skipped.
Sasha 249 · where is now agapi_route's "outcomes" family (SASHA_AGAPI_ROUTE; SASHA_OUTCOMES_VIA is its legacy switch), URL + key from
agapi_route.client_for. The OPEN set is kept in s2_memory too (kind "outcomes_open"): after a restart the sweep picks the open
attempts back up (restore(), at start-up) instead of forgetting them."""
from __future__ import annotations
from kanoe_contract import ERR, OP  # Sasha 374 · THE ONE generated contract (CR 186)

import asyncio
import logging
import os
import secrets
from typing import Any, Awaitable, Callable, Dict, Optional, Set, Tuple

log = logging.getLogger(__name__)

RUNG = {"form": ("zero_touch", "web_form"), "handover": ("human_tap", "page_handover"), "page": ("human_tap", "page_handover"),
        "draft": ("request_reply", "whatsapp"), "email": ("request_reply", "email"), "call": ("phone", "phone"),
        "prepared": ("human_tap", "page_handover")}   # Sasha 248 · "fill it now": their page + every detail, they confirm there
NOW_STATE = {"confirmed": "confirmed", "requested": "sent", "tap_to_finish": "sent", "page_on_phone": "sent", "page_link": "sent",
             "draft_on_phone": "sent", "draft_message": "sent", "scheduled": "sent", "placed": "sent", "calling": "sent", "not_sent": "failed",
             "not_allowed": "failed", "stopped": "failed"}   # Sasha 254 · AgAPI's "not allowed"; a call the rules stopped
LATER = {"confirmed": "confirmed", "guest_booked": "confirmed", "declined": "declined", "failed": "failed", "unreachable": "failed"}
SWEEP_EVERY_S = 600

_OPEN: Dict[str, Set[str]] = {}          # account → trip_item ids whose outcome is still open (this process)
_DONE: Set[Tuple[str, str]] = set()      # (ref, state) already sent — never sent twice
_task: Optional[asyncio.Task] = None


def via() -> str:
    """Sasha 249 · the outcomes family's AgAPI, from the one route table (agapi_route). SASHA_OUTCOMES_VIA is that family's legacy
    switch there — read only when SASHA_AGAPI_ROUTE doesn't name "outcomes" — so production (SASHA_OUTCOMES_VIA=live) stays live."""
    from agapi import agapi_route as AR
    return AR.current("outcomes")   # Sasha 256 · the call in progress, else the family's route — agapi_route decides


async def _agapi(op: str, body: dict) -> Dict[str, Any]:
    from agapi import agapi_route as AR
    url, key = await AR.client_for("outcomes")   # Sasha 249 · ONE ROUTE (the copied URL/key block is gone)
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "the outcomes ledger isn't switched on"}}
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": "s2out_" + secrets.token_hex(12)}
    return await AR.post(url, key, op, body, h, 15.0)   # Sasha 261 · the one transport (agapi_route.post): an AgAPI outage is named there, once, for every family


CALL: Callable[..., Awaitable[Dict[str, Any]]] = _agapi   # tests replace it


def ref_of(held: dict) -> str:
    return "sasha:" + str(held.get("trip_item_id") or f"{held.get('rung')}:{held.get('id')}")


async def _send(op: str, body: dict, account: Optional[str] = None) -> Optional[dict]:
    from agapi import agapi_route as AR
    try:
        with AR.acting(account):   # Sasha 253 · for whom: a test person's outcome goes to the sandbox ledger (client_for decides)
            r = await CALL(op, body)
    except Exception as e:
        log.warning("[outcomes] %s not recorded: %s", op, type(e).__name__)
        return None
    if not r.get("ok"):
        code = (r.get("error") or {}).get("code")
        if code not in (ERR.NOT_FOUND, ERR.ALREADY_COMPLETED):
            log.warning("[outcomes] %s not recorded: %s", op, code)
        return None
    return r["result"]


async def booked(account: str, held: dict, venue: str, city: Optional[str], result: Optional[dict] = None, error: Optional[str] = None) -> None:
    """book_venue acted: record the attempt and what happened at once. Never raises.
    Sasha 324 · NEVER an AgAPI act: AgAPI records its own act in this ledger (agapi:<act_id>, at venue.submit_booking) — recording it here
    too counted every AgAPI booking twice since 319. Only an attempt AgAPI never saw is Sasha's to record."""
    if held.get("rung") in ("agapi", "agapi_call"):
        return
    rung, channel = RUNG.get(held.get("rung") or "", ("phone", "phone"))
    if held.get("rung") == "agapi":   # Sasha 254 · AgAPI's send: the rung the booking rules chose (agapi.venues.AGAPI_RUNG)
        from agapi.venues import AGAPI_RUNG
        rung, channel = AGAPI_RUNG.get(str(held.get("agapi_action") or ""), ("request_reply", "email"))
    if held.get("rung") == "draft" and held.get("channel") == "instagram":
        channel = "instagram"
    st = "failed" if error else NOW_STATE.get(str((result or {}).get("status") or ""), "sent")
    ref = ref_of(held)
    body: Dict[str, Any] = {"ref": ref, "venue": venue[:120], "rung": rung, "channel": channel, "state": st,
                            **({"sector": str(held["sector"])[:40]} if held.get("sector") else {}), **({"city": city[:80]} if city else {}),
                            **({"asked_at": held["at"].strftime("%Y-%m-%dT%H:%M:%SZ")} if hasattr(held.get("at"), "strftime") else {})}
    if st == "confirmed":
        body["confirmation_quote"] = (f"Their reference: {result['reference']}" if (result or {}).get("reference") else (result or {}).get("line") or "confirmed")
    if st == "failed":
        body["failure_reason"] = (error or (result or {}).get("status") or "not sent")[:300]
    out = await _send(OP.OUTCOMES_RECORD, body, account)
    if out:
        _DONE.add((ref, st))
        if st not in ("confirmed", "declined", "failed") and held.get("trip_item_id"):
            await _open_of(account)
            _OPEN.setdefault(account, set()).add(str(held["trip_item_id"]))
            await _keep_open(account)
            start()


_LATER: Set["asyncio.Task"] = set()   # CR 130 · ledger writes in flight after her answer (held: a task can't be collected mid-write)


def booked_later(account: str, held: dict, venue: str, city: Optional[str], result: Optional[dict] = None, error: Optional[str] = None) -> None:
    """CR 130 · A RECORD OF WHAT HAPPENED NEVER HOLDS UP THE PERSON'S ANSWER. Sasha 299 (4), La Mi Venta's tap: outcomes.record took 8.9 s
    and she said nothing until it was back. The answer's path (venues._finish) hands the write here: started now, on this loop, written
    after — the same booked(), the same once-only bookkeeping. Never raises. (A process restart inside its ~0.2 s loses that one row;
    the person's answer no longer waits for the ledger.)"""
    try:
        t = asyncio.get_running_loop().create_task(booked(account, dict(held), venue, city, result=result, error=error))
    except RuntimeError:   # no running loop: nothing to write after
        return
    _LATER.add(t)
    t.add_done_callback(_LATER.discard)


async def settle(timeout: float = 5.0) -> int:
    """CR 130 · the ledger writes still in flight, finished (tests; a clean shutdown). → how many were waited for."""
    pending = list(_LATER)
    if pending:
        await asyncio.wait(pending, timeout=timeout)
    return len(pending)


# ── Sasha 324 · an attempt that ENDED BEFORE any act (handed to Tyler, refused, not prepared): its outcome, on the one ledger ────────
#: the tools that book, change or cancel — an outcome ends one of these
ACTING = {"book_venue", "hold_venue", "cancel_venue", "change_booking", "cancel_booking", "running_late", "book"}
#: a result that ends the attempt with nothing sent (its status → the reason said on the ledger)
NO_ACT = {"to_tyler": "handed to Tyler", "not_sent": "handed to Tyler — not sent", "not_contacted": "not allowed to contact venues",
          "not_called": "not called", "not_possible": "not possible from here", "not_cancelled": "not cancelled"}
#: errors that END an attempt (a question back to the person — a missing detail, a yes still to come — does not)
ENDS = {"not_prepared", "no_route", "not_bookable", "payments_unreachable", "airline_unreachable", "store_unreachable", "booking_unknown"}


def ended_without_act(tool: str, ok: bool, out: Any, code: Optional[str]) -> Optional[str]:
    """→ why, when this tool call ENDED a booking / change / cancel with no act of AgAPI's (its outcome is then Sasha's to record); else
    None (an act exists — AgAPI records it — or the attempt goes on)."""
    if tool not in ACTING:
        return None
    if not ok:
        return f"failed: {code}" if code in ENDS else None
    st = str((out or {}).get("status") or "") if isinstance(out, dict) else ""
    if (out or {}).get("act_id") if isinstance(out, dict) else False:
        return None
    return NO_ACT.get(st)


#: the endings that are a hand-off to Tyler (a person of Kanoe's) — every other ending before an act is a failure
HANDED = ("handed to Tyler",)
KIND_OF = {"cancel_venue": "cancel", "cancel_booking": "cancel", "change_booking": "change", "running_late": "late"}


async def no_act(account: Optional[str], tool: str, why: str, out: Any = None, args: Optional[dict] = None) -> None:
    """The ending of an attempt that never became an act, on AgAPI's ledger as what it IS (CR 155, AgAPI v1.54.0 — outcomes.honest):
    a hand-off to Tyler → rung person · channel none · state handed_to_person · failure_reason why; any other (refused, not prepared, not
    possible) → channel none (nothing reached a venue) · state failed · why. Its kind: booking / change / late / cancel. Never raises."""
    if not account:
        return
    o = out if isinstance(out, dict) else {}
    a = args or {}
    handed = why.startswith(HANDED)
    body = {"ref": f"sasha:noact:{secrets.token_hex(8)}", "venue": str(o.get("venue") or a.get("name") or a.get("venue") or "unknown")[:120],
            "kind": KIND_OF.get(tool, "booking"), "rung": "person" if handed else "api", "channel": "none",
            "state": "handed_to_person" if handed else "failed", "failure_reason": why[:300],
            **({"sector": str(a.get("what") or a.get("category") or "")[:40]} if (a.get("what") or a.get("category")) else {}),
            **({"city": str(a.get("city"))[:80]} if a.get("city") else {})}
    await _send(OP.OUTCOMES_RECORD, body, account)


async def basket_booked(account: str, rows: list) -> int:
    """Sasha 249 · basket bookings (a trip's flights and hotels, booked by their provider's API after the payment) go in the ledger
    too (EU 245 §1.16): rung "api", channel "api", sector flight / hotel, the provider's name and the destination city — never the
    person's details. Decided at once (booked → confirmed with its reference, failed → failed with Pacioli's reason); once per row.
    Never raises; a ledger that doesn't answer is logged and skipped. → how many were recorded."""
    n = 0
    for r in rows or []:
        state = {"booked": "confirmed", "failed": "failed"}.get(str(r.get("state") or ""))
        if not state or not r.get("id"):
            continue
        ref = f"sasha:basket:{r['id']}"
        if (ref, state) in _DONE:
            continue
        s = r.get("snapshot") or {}
        flight = r.get("kind") == "flight"
        venue = (" ".join(f"{s.get('owner') or ''} {s.get('flights') or ''}".split()) if flight else str(s.get("name") or s.get("hotel") or "")) \
            or ("Flight" if flight else "Hotel")
        city = (s.get("to_city") or s.get("to")) if flight else s.get("city")
        body: Dict[str, Any] = {"ref": ref, "venue": venue[:120], "rung": "api", "channel": "api", "state": state,
                                "sector": "flight" if flight else "hotel", **({"city": str(city)[:80]} if city else {})}
        if state == "confirmed":
            body["confirmation_quote"] = f"Their reference: {r['booking_reference']}" if r.get("booking_reference") else "booked"
        else:
            body["failure_reason"] = str(r.get("failed_why") or "refused")[:300]
        if await _send(OP.OUTCOMES_RECORD, body, account):
            _DONE.add((ref, state))
            n += 1
    return n


async def sync(account: str, reservations: list) -> int:
    """The reservations as Sasha's records have them now → each decided one updates its outcome (once). Never raises."""
    n = 0
    was = set(await _open_of(account))
    for r in reservations or []:
        tid, status = str(r.get("id") or r.get("trip_item_id") or ""), str(r.get("status") or "")
        st = LATER.get(status)
        if status == "cancelled" and tid in _OPEN.get(account, set()):
            st = "failed"
        if not tid or not st:
            continue
        if tid not in was:   # Sasha 325 · only an attempt still OPEN (the durable open set) is updated — a settled one never again: after
            continue         # every restart this re-sent every decided reservation (~45 outcomes.update in 10 s on 2 Nov, all 404)
        ref = f"sasha:{tid}"
        if (ref, st) in _DONE:
            continue
        words = r.get("status_words") or (f"Their reference: {r['booking_reference']}" if r.get("booking_reference") else None)
        body: Dict[str, Any] = {"ref": ref, "state": st}
        if st == "confirmed" and words:
            body["confirmation_quote"] = str(words)[:2000]
        if st in ("declined", "failed"):
            body["failure_reason"] = ("cancelled before the venue answered" if status == "cancelled" else str(words or status))[:600]
        _DONE.add((ref, st))
        if await _send(OP.OUTCOMES_UPDATE, body, account):
            n += 1
        _OPEN.get(account, set()).discard(tid)
    if set(_OPEN.get(account, set())) != was:
        await _keep_open(account)
    return n


# ── Sasha 249 · THE OPEN SET, DURABLE (T14): kept in s2_memory (kind outcomes_open) beside this process's _OPEN; restore() at start-up
# picks every open attempt back up and starts the sweep, so a restart no longer forgets the outcomes still waiting for a venue.

async def _open_of(account: str) -> Set[str]:
    """This account's open attempts — this process's, else (after a restart) the ones kept in s2_memory."""
    if account not in _OPEN:
        try:
            from agapi import s2_memory as M
            kept = await M.kind(account, "outcomes_open")
        except Exception as e:
            log.warning("[outcomes] open set not read: %s", type(e).__name__)
            kept = None
        if kept:
            _OPEN[account] = {str(x) for x in kept}
    return _OPEN.get(account, set())


async def _keep_open(account: str) -> None:
    try:
        from agapi import s2_memory as M
        await M.put_kind(account, "outcomes_open", sorted(_OPEN.get(account) or []) or None)
    except Exception as e:
        log.warning("[outcomes] open set not kept: %s", type(e).__name__)


async def restore() -> int:
    """At start-up: every account's open attempts back into _OPEN, and the sweep started if any. → how many accounts."""
    from agapi import s2_memory as M
    n = 0
    for account, ids in await M.accounts_with("outcomes_open"):
        if ids and account not in _OPEN:
            _OPEN[account] = {str(x) for x in ids}
            n += 1
    if _OPEN:
        start()
    return n


async def _sweep_once() -> None:
    from agapi.venues import _API
    GW = _API()
    for account in list(_OPEN):
        if not _OPEN.get(account):
            _OPEN.pop(account, None)
            continue
        try:
            status, j = await GW.api(account, "GET", "/api/booking/reservations")
        except Exception as e:
            log.warning("[outcomes] the sweep couldn't read the reservations: %s", type(e).__name__)
            continue
        if status == 200:
            await sync(account, (j or {}).get("reservations") or [])


async def _forever() -> None:
    while _OPEN:
        await asyncio.sleep(SWEEP_EVERY_S)
        try:
            await _sweep_once()
        except Exception as e:
            log.warning("[outcomes] sweep failed: %s", type(e).__name__)


def start() -> None:
    global _task
    if _task is None or _task.done():
        try:
            _task = asyncio.get_running_loop().create_task(_forever())
        except RuntimeError:
            _task = None


__all__ = ["booked", "basket_booked", "sync", "ref_of", "via", "restore", "RUNG", "LATER"]   # Sasha 249 · + basket_booked, restore


# Sasha 374 · CR 186 · a test double on CALL may never answer a field AgAPI doesn't publish (agapi/contract_shape.py)
from agapi import contract_shape as _CONTRACT_SHAPE  # noqa: E402
_CONTRACT_SHAPE.guard(__name__, 'CALL')
