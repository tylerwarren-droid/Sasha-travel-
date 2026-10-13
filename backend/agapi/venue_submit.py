"""Sasha 254 · item 3 — "I'LL HANDLE IT", LIVE: when the booking rules decide that Sasha sends it (fill_form_zero_touch — the answer
"Handle it" to the ONE question — or a request, request_email / request_whatsapp), the send is AgAPI's (agapi-live v1.8.0, CR 90), through
the ONE route (agapi_route.client_for("venues", account) inside agapi_route.acting(account): a test person reaches the sandbox).

  prepare(...)        venue.prepare_booking (person, date, time, party) → prepared_id (vpr_…), their prepared link, zero_touch_allowed
  read_back(...)      venue.submit_booking WITHOUT an approval → approval_required + read_back_id + the read-back lines (CR 90: "the
                      read-back first"). Live: approvals.request sends AgAPI's one-tap link to their phone (as s2_subscriptions does)
  submit(...)         on their yes, in a LATER turn (book_venue — the one-yes rule): the approval (sandbox: sandbox.simulate_approval with
                      their own words; live: approvals.status — their tap) → venue.submit_booking with AgAPI-Approval-Id
                      → confirmed / sent / failed / not_allowed (Tyler and Jon reach real venues; everyone else: not_allowed)
  status(...)         venue.booking_status (act_id) → the venue's reply, for get_status (agapi.s2_status, the one status)
  acts_of(account)    the person's acts (kept in s2_memory, kind "venue_acts"), each with what get_status shows

Never the person's card; their name / phone / email only to prepare_booking (AgAPI keeps them 24 h, for that booking only)."""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

log = logging.getLogger("agapi.venue_submit")

FAMILY = "venues"
TIMEOUT_S = 75.0
_USERS: Dict[str, str] = {}             # target|account → AgAPI end_user
_ACTS: Dict[str, List[dict]] = {}       # account → [{act_id, venue, date, time, party, state, say, at}]
ACTS_KEEP = 30


async def _agapi(op: str, body: dict, approval: Optional[str] = None, account: Optional[str] = None) -> Dict[str, Any]:
    """The transport: the venues family's AgAPI, its own key (never printed). A person's mode picks live or the sandbox."""
    import httpx
    from agapi import agapi_route as AR
    url, key = await AR.client_for(FAMILY, account)
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "the venue booking service isn't switched on here"}}
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": "s2vs_" + secrets.token_hex(12)}
    if approval:
        h["AgAPI-Approval-Id"] = approval
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S)) as c:
            r = await c.post(f"{url}/v1/{op}", headers=h, content=json.dumps(body))
        return r.json()
    except Exception as e:
        return {"ok": False, "error": {"code": "unreachable", "message": type(e).__name__}}


CALL: Callable[..., Awaitable[Dict[str, Any]]] = _agapi   # tests replace it


async def _call(account: str, op: str, body: dict, approval: Optional[str] = None) -> Dict[str, Any]:
    from agapi import agapi_route as AR
    with AR.acting(account):
        return await CALL(op, body, approval=approval, account=account)


async def target(account: str) -> str:
    from agapi import agapi_route as AR
    with AR.acting(account):
        return await AR.target_for(FAMILY, account)


async def end_user(account: str) -> Optional[str]:
    k = f"{await target(account)}|{account}"   # each AgAPI has its own end users
    if k in _USERS:
        return _USERS[k]
    r = await _call(account, "users.register", {"external_ref": f"sasha:{account}"})
    if r.get("ok"):
        _USERS[k] = r["result"]["end_user_id"]
        return _USERS[k]
    log.warning("[venue_submit] no end user: %s", (r.get("error") or {}).get("code"))
    return None


def _err(r: dict) -> dict:
    e = r.get("error") or {}
    return {"code": e.get("code") or "unavailable", "message": e.get("message") or "the venue booking service didn't answer",
            "details": e.get("details") or {}}


async def prepare(account: str, place: dict, person: dict, date: str, time_: str, party: int, notes: Optional[str] = None) -> Dict[str, Any]:
    """venue.prepare_booking → {ok, prepared_id, link, zero_touch_allowed, say, …} or {ok: False, error}. Nothing is submitted."""
    body = {"place": {k: v for k, v in place.items() if v and k in ("name", "website", "place_id", "city", "category")},
            "person": {k: v for k, v in person.items() if v}, "date": date, "time": time_, "party": int(party),
            **({"notes": notes[:500]} if notes else {})}
    r = await _call(account, "venue.prepare_booking", body)
    if not r.get("ok"):
        return {"ok": False, "error": _err(r)}
    res = r.get("result") or {}
    if res.get("submitted"):   # never a booking that went out by itself
        return {"ok": False, "error": {"code": "submitted_unasked", "message": "it went out without the person's yes — stopped here"}}
    if not str(res.get("prepared_id") or "").startswith("vpr_"):
        return {"ok": False, "error": {"code": "not_prepared", "message": res.get("say") or "their booking couldn't be prepared"}}
    return {"ok": True, **res}


async def read_back(account: str, prepared_id: str) -> Dict[str, Any]:
    """CR 90 · the read-back first: submit_booking with no approval → approval_required + read_back_id + its lines."""
    uid = await end_user(account)
    if not uid:
        return {"ok": False, "error": {"code": "no_end_user", "message": "the venue booking service doesn't know this person yet"}}
    r = await _call(account, "venue.submit_booking", {"end_user": uid, "prepared_id": prepared_id})
    e = r.get("error") or {}
    if e.get("code") != "approval_required":
        if r.get("ok"):   # it never sends without the person's yes; a send here would be a contract breach — said, not hidden
            log.error("[venue_submit] submit_booking answered without an approval (%s)", (r.get("result") or {}).get("status"))
            return {"ok": False, "error": {"code": "sent_without_yes", "message": "the service didn't ask for their yes"}}
        return {"ok": False, "error": _err(r)}
    d = e.get("details") or {}
    lines = list((d.get("read_back") or {}).get("lines") or d.get("lines") or [])
    rid = d.get("read_back_id")
    if not rid or not lines:
        return {"ok": False, "error": {"code": "no_read_back", "message": "the service gave no read-back to ask them"}}
    if await target(account) == "live":   # live: AgAPI's one-tap link to their phone (the approval is their tap)
        await _call(account, "approvals.request", {"read_back_id": rid, "channel": "link_sms"})
    sha = hashlib.sha256("\n".join(str(x) for x in lines).encode()).hexdigest()
    return {"ok": True, "end_user": uid, "read_back_id": rid, "lines": lines, "sha256": sha}


async def submit(account: str, held: dict, said: str) -> Dict[str, Any]:
    """On their yes (a later turn): the approval → venue.submit_booking. → {ok, status ∈ confirmed|sent|failed|not_allowed|waiting_for_their_tap, …}"""
    rid, pid, uid = held["read_back_id"], held["prepared_id"], held.get("end_user") or await end_user(account)
    if await target(account) == "sandbox":
        a = await _call(account, "sandbox.simulate_approval", {"read_back_id": rid, "said": (said or "")[:200] or "yes"})
        if not a.get("ok"):
            return {"ok": False, "error": {"code": (a.get("error") or {}).get("code") or "no_explicit_yes",
                                           "message": "that wasn't a clear yes — ask them again before sending"}}
        approval = a["result"]["approval_id"]
    else:
        st = await _call(account, "approvals.status", {"read_back_id": rid})
        ap = ((st.get("result") or {}).get("approval") or {}) if st.get("ok") else {}
        if not ap.get("approval_id") or ap.get("state") != "valid":
            return {"ok": True, "status": "waiting_for_their_tap"}
        approval = ap["approval_id"]
    r = await _call(account, "venue.submit_booking", {"end_user": uid, "prepared_id": pid}, approval=approval)
    if not r.get("ok"):
        return {"ok": False, "error": _err(r)}
    res = r.get("result") or {}
    if res.get("act_id"):
        await _remember(account, {"act_id": res["act_id"], "venue": res.get("venue") or held.get("venue"), "when": held.get("when"),
                                  "party": held.get("party"), "state": res.get("status"), "say": res.get("say"),
                                  **({"reference": res["reference"]} if res.get("reference") else {})})
    return {"ok": True, **res}


async def status(account: str, act_id: str) -> Optional[dict]:
    """venue.booking_status → the venue's reply (state + its words), or None when the service doesn't answer."""
    r = await _call(account, "venue.booking_status", {"act_id": act_id})
    return r.get("result") if r.get("ok") else None


# ── the person's acts, kept (s2_memory kind "venue_acts") so get_status still finds them after a restart ─────────────────────

async def _remember(account: str, act: dict) -> None:
    acts = [a for a in await acts_of(account) if a.get("act_id") != act["act_id"]] + [{**act, "at": time.time()}]
    _ACTS[account] = acts[-ACTS_KEEP:]
    try:
        from agapi import s2_memory as M
        await M.put_kind(account, "venue_acts", _ACTS[account])
    except Exception as e:
        log.warning("[venue_submit] acts not kept: %s", type(e).__name__)


async def acts_of(account: str) -> List[dict]:
    if account not in _ACTS:
        try:
            from agapi import s2_memory as M
            kept = await M.kind(account, "venue_acts")
        except Exception as e:
            log.info("[venue_submit] acts not read: %s", type(e).__name__)
            kept = None
        _ACTS[account] = list(kept or [])
    return list(_ACTS.get(account) or [])


STATE = {"confirmed": "confirmed", "booked": "confirmed", "declined": "declined", "refused": "declined", "failed": "failed",
         "not_allowed": "failed", "cancelled": "cancelled"}


async def bookings(account: str) -> List[dict]:
    """The person's AgAPI venue acts as get_status rows (venue_bookings' shape): each one's state from venue.booking_status now (the
    venue's reply, their words as untrusted data), else as it was when sent."""
    out = []
    for a in await acts_of(account):
        st = await status(account, a["act_id"])
        state = str((st or {}).get("state") or a.get("state") or "sent")
        if st and st.get("state") != a.get("state"):
            a["state"] = st.get("state")
        words = (st or {}).get("venue_words") or {}
        text = words.get("text") if isinstance(words, dict) else None
        when = str(a.get("when") or "")
        out.append({"trip_item_id": None, "act_id": a["act_id"], "venue": a.get("venue"), "date": when[:10] or None, "time": when[11:16] or None,
                    "party": a.get("party"), "status": STATE.get(state, "requested"), "type": "venue",
                    **({"reference": a["reference"]} if a.get("reference") else {}),
                    **({"venue_said": {"untrusted_text": str(text)[:160]}} if text else {})})
    return out


__all__ = ["prepare", "read_back", "submit", "status", "acts_of", "bookings", "end_user", "CALL"]
