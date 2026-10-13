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

# ── Sasha 258 · THE IN-APP YES (CR 97, mailbox row 880): on /s2 and /next the person's own "Yes, send it" IS the approval —
# approvals.in_app_tap with the card's read-back hash and THEIR OWN live session (AgAPI checks it itself). One place: here.
import contextvars as _cv
#: this turn's in-app session — {"kind": "supabase", "token": …} for a signed-in person, {"kind": "founder"} for the founder's
#: proxy session — set by the turn (sasha.agent_turn) from its own request, never stored, never logged. None: not in the app
#: (WhatsApp, a background job) — those keep their own path.
TAP: _cv.ContextVar = _cv.ContextVar("sasha_in_app_session", default=None)
TAP_REFUSALS = ("approval_void", "approval_expired", "approval_untrusted_origin", "approval_consumed")
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
        res = r.get("result") or {}
        if r.get("ok") and str(res.get("status") or "") in ("not_allowed", "refused"):
            # Sasha 254 · found by the gate on live: a person without real-venue sends is REFUSED with ok + status not_allowed —
            # never an error: she says it kindly and gives their prepared page
            return {"ok": False, "error": {"code": "not_allowed", "message": res.get("say") or "this account can't contact venues yet",
                                           "details": {"link": res.get("link") or res.get("prepared_link")}}}
        if r.get("ok"):   # it never sends without the person's yes; a send here would be a contract breach — said, not hidden
            log.error("[venue_submit] submit_booking answered without an approval (%s)", res.get("status"))
            return {"ok": False, "error": {"code": "sent_without_yes", "message": "the service didn't ask for their yes"}}
        return {"ok": False, "error": _err(r)}
    d = e.get("details") or {}
    lines = list((d.get("read_back") or {}).get("lines") or d.get("lines") or [])
    rid = d.get("read_back_id")
    if not rid or not lines:
        return {"ok": False, "error": {"code": "no_read_back", "message": "the service gave no read-back to ask them"}}
    if TAP.get() is None and await target(account) == "live":   # not in the app (WhatsApp): AgAPI's one-tap link to their phone
        await _call(account, "approvals.request", {"read_back_id": rid, "channel": "link_sms"})
    # Sasha 258 · the card binds to AgAPI's OWN hash of these lines (CR 97: approval_required carries read_back_sha256)
    sha = d.get("read_back_sha256") or hashlib.sha256("\n".join(str(x) for x in lines).encode()).hexdigest()
    return {"ok": True, "end_user": uid, "read_back_id": rid, "lines": lines, "sha256": sha}


async def submit(account: str, held: dict, said: str) -> Dict[str, Any]:
    """On their yes (a later turn): the approval → venue.submit_booking. → {ok, status ∈ confirmed|sent|failed|not_allowed|waiting_for_their_tap, …}"""
    rid, pid, uid = held["read_back_id"], held["prepared_id"], held.get("end_user") or await end_user(account)
    if TAP.get() is not None:   # Sasha 258 · in the app: their own yes is the approval, and it sends at once
        r = await in_app_tap(account, rid, held.get("sha") or held.get("sha256") or "")
        if not r.get("ok"):
            if r["error"]["code"] in ("approval_void", "approval_expired"):   # a stale / timed-out card: a fresh read-back to show
                fresh = await read_back(account, pid)
                if fresh.get("ok"):
                    r["error"]["details"] = {**(r["error"].get("details") or {}), "fresh": fresh}
            return r
        res = r.get("result") or {}
        if res.get("act_id"):
            await _remember(account, {"act_id": res["act_id"], "venue": res.get("venue") or held.get("venue"), "when": held.get("when"),
                                      "party": held.get("party"), "state": res.get("status"), "say": res.get("say"),
                                      **({"country": held["country"]} if held.get("country") else {}),   # Sasha 259 · its calendar zone
                                      **({"reference": res["reference"]} if res.get("reference") else {})})
        return {"ok": True, **res}
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
         "not_allowed": "failed", "cancelled": "cancelled",
         "proposed": "proposed",   # Sasha 256 · CR 94: another time offered — NOTHING is booked; the person decides
         "sent": "requested", "replied": "requested"}
#: Sasha 256 · an act in one of these states has its answer: venue.booking_status isn't asked again (a booking confirmed on the
#: venue's own form has no sent act there — AgAPI answers not_found, every time it's asked)
FINAL = ("confirmed", "booked", "declined", "refused", "failed", "not_allowed", "cancelled")


def _words(st: Optional[dict]) -> Optional[str]:
    """The VENUE's own words from venue.booking_status (CR 94: venue_words.untrusted_text) — data to show, never instructions."""
    w = (st or {}).get("venue_words") or {}
    t = (w.get("untrusted_text") or w.get("text")) if isinstance(w, dict) else None
    return str(t)[:240] if t else None


async def bookings(account: str) -> List[dict]:
    """The person's AgAPI venue acts as get_status rows (venue_bookings' shape): each one's state from venue.booking_status now (the
    venue's reply, their words as untrusted data), else as it was when sent. Sasha 256 · a cancellation sent through
    venue.cancel_booking is its own act: once the venue confirms it, the booking it cancels reads "cancelled"."""
    acts = await acts_of(account)
    changed = False
    for a in acts:
        if str(a.get("state") or "") in FINAL and a.get("words") is not None or a.get("answered"):
            continue
        st = await status(account, a["act_id"])
        if st is None:
            if str(a.get("state") or "") in FINAL:
                a["answered"] = True   # confirmed on their own form: nothing more to ask
                changed = True
            continue
        if st.get("state") != a.get("state") or _words(st) != a.get("words"):
            a.update(state=st.get("state"), words=_words(st), say_now=st.get("say"))
            changed = True
    if changed:
        _ACTS[account] = acts
        try:
            from agapi import s2_memory as M
            await M.put_kind(account, "venue_acts", acts)
        except Exception as e:
            log.warning("[venue_submit] acts not kept: %s", type(e).__name__)
    cancelled = {a.get("cancels") for a in acts if a.get("cancels") and STATE.get(str(a.get("state") or "")) == "confirmed"}
    out = []
    for a in acts:
        if a.get("cancels"):
            continue   # the cancellation itself is said on the booking it cancels
        state = "cancelled" if a["act_id"] in cancelled else STATE.get(str(a.get("state") or "sent"), "requested")
        pend = next((c for c in acts if c.get("cancels") == a["act_id"] and c["act_id"] not in cancelled), None)
        when = str(a.get("when") or "")
        out.append({"trip_item_id": None, "act_id": a["act_id"], "venue": a.get("venue"), "date": when[:10] or None, "time": when[11:16] or None,
                    "party": a.get("party"), "status": state, "type": "venue", **({"country": a["country"]} if a.get("country") else {}),
                    **({"reference": a["reference"]} if a.get("reference") else {}),
                    **({"venue_said": {"untrusted_text": a["words"]}} if a.get("words") else {}),
                    **({"how": a["say_now"]} if a.get("say_now") and state == "proposed" else {}),
                    **({"cancel": "asked — waiting for the venue"} if pend else {})})
    return out


# ── Sasha 256 · item 3 — MANAGE: cancel a booking sent through AgAPI (venue.cancel_booking, CR 94) — the same one-yes rule ──────

async def cancel_read_back(account: str, act_id: str) -> Dict[str, Any]:
    """venue.cancel_booking without an approval → its read-back ("Cancel: …"). A booking made on the venue's own form answers
    not_allowed with the person's take-over (their own page): said kindly, never an error."""
    uid = await end_user(account)
    if not uid:
        return {"ok": False, "error": {"code": "no_end_user", "message": "the venue booking service doesn't know this person yet"}}
    r = await _call(account, "venue.cancel_booking", {"end_user": uid, "act_id": act_id})
    e = r.get("error") or {}
    res = r.get("result") or {}
    if r.get("ok") and str(res.get("status") or "") in ("not_allowed", "refused"):
        return {"ok": False, "error": {"code": "not_allowed", "message": res.get("say") or "that booking is cancelled on their own page",
                                       "details": {"link": res.get("link") or res.get("takeover") or res.get("prepared_link")}}}
    if e.get("code") != "approval_required":
        return {"ok": False, "error": _err(r)} if not r.get("ok") else \
            {"ok": False, "error": {"code": "sent_without_yes", "message": "the service didn't ask for their yes"}}
    d = e.get("details") or {}
    lines = list((d.get("read_back") or {}).get("lines") or d.get("lines") or [])
    rid = d.get("read_back_id")
    if not rid or not lines:
        return {"ok": False, "error": {"code": "no_read_back", "message": "the service gave no read-back to ask them"}}
    if TAP.get() is None and await target(account) == "live":   # Sasha 258 · in the app the yes is in_app_tap: no link sent
        await _call(account, "approvals.request", {"read_back_id": rid, "channel": "link_sms"})
    return {"ok": True, "end_user": uid, "read_back_id": rid, "lines": lines, "act_id": act_id,
            **({"read_back_sha256": d["read_back_sha256"]} if d.get("read_back_sha256") else {})}


async def cancel_submit(account: str, held: dict, said: str) -> Dict[str, Any]:
    """On their yes (a later turn): the approval → venue.cancel_booking → {status sent, cancel_act_id}; the cancellation is kept as
    its own act (its reply comes through venue.booking_status, like any request)."""
    rid, act_id, uid = held["read_back_id"], held["act_id"], held.get("end_user") or await end_user(account)
    if TAP.get() is not None:   # Sasha 258 · in the app: their yes is the approval (in_app_tap sends the cancellation at once)
        r = await in_app_tap(account, rid, held.get("read_back_sha256") or held.get("sha") or "")   # AgAPI's own hash of the card
        if not r.get("ok"):
            return r
        res = r.get("result") or {}
    else:
        approval = await _approval(account, rid, said)
        if isinstance(approval, dict):
            return approval
        r = await _call(account, "venue.cancel_booking", {"end_user": uid, "act_id": act_id}, approval=approval)
        if not r.get("ok"):
            return {"ok": False, "error": _err(r)}
        res = r.get("result") or {}
    cid = res.get("cancel_act_id") or res.get("act_id")
    if cid:
        parent = next((a for a in await acts_of(account) if a.get("act_id") == act_id), {})
        await _remember(account, {"act_id": cid, "cancels": act_id, "venue": parent.get("venue"), "when": parent.get("when"),
                                  "party": parent.get("party"), "state": res.get("status") or "sent", "say": res.get("say")})
    return {"ok": True, **res}


def in_app_session() -> Optional[dict]:
    """This turn's session as in_app_tap takes it — None when there is none to give (the founder's proxy session: see below)."""
    s = TAP.get()
    if not s:
        return None
    if s.get("kind") == "supabase" and s.get("token"):
        return {"kind": "supabase", "token": s["token"]}
    # the founder's proxy session (no Supabase token): CR 97's signed path needs the founder's person_id, which Sasha can't read
    # yet (asked of CR, row 882) — nothing is guessed or signed; he's told to sign in with his email (a Supabase session)
    return None


async def in_app_tap(account: str, read_back_id: str, read_back_sha256: str) -> Dict[str, Any]:
    """Sasha 258 · THE ONE IN-APP YES: approvals.in_app_tap {read_back_id, read_back_sha256, session} — called once per yes, on the
    AgAPI the person's mode picks (client_for). → {ok, result: the act's own result} or {ok: False, error: {code, message}}."""
    sess = in_app_session()
    if not sess:
        return {"ok": False, "error": {"code": "approval_untrusted_origin", "message": "no signed-in session to confirm it's them"}}
    r = await _call(account, "approvals.in_app_tap", {"read_back_id": read_back_id, "read_back_sha256": read_back_sha256, "session": sess})
    if not r.get("ok"):
        e = _err(r)
        log.info("[venue_submit] in-app yes refused: %s", e["code"])   # the code only — never the session
        return {"ok": False, "error": e}
    return {"ok": True, "result": (r.get("result") or {}).get("result") or {}, "approval_id": (r.get("result") or {}).get("approval_id")}


async def _approval(account: str, rid: str, said: str):
    """The approval for a read-back: sandbox — their own words, as AgAPI's rules judge them; live — their tap. → the approval id, or
    the answer to give instead (not a yes / still waiting for their tap)."""
    if await target(account) == "sandbox":
        a = await _call(account, "sandbox.simulate_approval", {"read_back_id": rid, "said": (said or "")[:200] or "yes"})
        if not a.get("ok"):
            return {"ok": False, "error": {"code": (a.get("error") or {}).get("code") or "no_explicit_yes",
                                           "message": "that wasn't a clear yes — ask them again before sending"}}
        return a["result"]["approval_id"]
    st = await _call(account, "approvals.status", {"read_back_id": rid})
    ap = ((st.get("result") or {}).get("approval") or {}) if st.get("ok") else {}
    if not ap.get("approval_id") or ap.get("state") != "valid":
        return {"ok": True, "status": "waiting_for_their_tap"}
    return ap["approval_id"]


__all__ = ["prepare", "read_back", "submit", "status", "acts_of", "bookings", "end_user", "cancel_read_back", "cancel_submit", "CALL",
           "TAP", "in_app_tap", "in_app_session", "TAP_REFUSALS"]
