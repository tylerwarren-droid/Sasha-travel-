"""Sasha 265 · item 4 (CR 99 §4c) — A CALL IS PLACED ONLY FROM ITS ACT. ONE TRUTH = the AgAPI act (venue.submit_booking route "call"):
its read-back, the person's tap as its approval, and every attempt reported to it. Sasha only dials what the act's call_plan says.

  dial(account, result, held)   the act's approved result (status "calling", act_id, call_plan) → nothing dialled (simulate: the sandbox),
                                or a booking_calls row KEYED BY ITS act_id (brief.act_id), built from call_plan alone — Bland gets
                                call_plan.phone, its opening (the AI disclosure first, R7), its rules (R8/R9) and its payload (no voicemail,
                                no recording, 4 minutes) — placed at call_plan.when (closed now: when they open), never before
                                next_call.allowed_at.
  after_call(call, reading)     after EVERY call it placed: venue.call_attempt {act_id, outcome, venue_words, answered_by} and its `say`
                                told to the person (their open page; their WhatsApp when linked). "refused" = the dialler broke R10 (logged
                                as the bug it is, nothing told as booked); "calling" with next_call → the next call, scheduled at
                                next_call.allowed_at; "no_answer" → the act's next_step (their page, or their number) told.
  ACT_KEY                       booking_calls keeps act_id in its brief: call_routes refuses to place a booking call without one (the
                                second path, retired). Its own caps stay as the server's net.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

log = logging.getLogger("agapi.venue_calls")

ACT_KEY = "act_id"


def NOW() -> datetime:
    return datetime.now(timezone.utc)


def act_of(call: Optional[dict]) -> Optional[str]:
    """The act a booking_calls row belongs to (its brief's act_id) — None: a call no act approved (never placed)."""
    return str(((call or {}).get("brief") or {}).get(ACT_KEY) or "") or None


def _iso(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def brief_of(act_id: str, plan: dict, held: dict) -> Dict[str, Any]:
    """The call's brief, from the act's call_plan ONLY (its number, its opening, its rules) — nothing Sasha adds to what is said."""
    rules = [str(r) for r in plan.get("rules") or []]
    task = (f"You are calling {held.get('venue') or 'the venue'} to book {held.get('summary') or 'a table'}. "
            + " ".join(rules))[:2000]
    return {ACT_KEY: act_id, "purpose": "book", "number": plan["phone"], "first_sentence": str(plan.get("opening") or ""),
            "task": task, "language": "en", "venue_key": f"act:{act_id}", "venue_name": held.get("venue"),
            "timezone": held.get("timezone") or "Europe/Madrid", "payload": dict(plan.get("payload") or {}),
            "when": plan.get("when"), "opens_at": plan.get("opens_at")}


def due_at(plan: dict, held: dict, now: Optional[datetime] = None) -> datetime:
    """When the act lets this call be made: "when they open at HH:MM" (+ 10 minutes, as every scheduled call) and never before
    next_call.allowed_at."""
    now = now or NOW()
    at = now
    nc = plan.get("next_call") or {}
    allowed = _iso(nc.get("allowed_at"))
    if allowed and allowed > at:
        at = allowed
    if plan.get("opens_at") and str(plan.get("when") or "").startswith("when they open"):
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(held.get("timezone") or "Europe/Madrid")
            local = now.astimezone(tz)
            hh, mm = (int(x) for x in str(plan["opens_at"]).split(":"))
            opens = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if opens <= local:
                opens += timedelta(days=1)
            opens = (opens + timedelta(minutes=10)).astimezone(timezone.utc)
            if opens > at:
                at = opens
        except Exception as e:
            log.info("[venue_calls] opening not read (%s): the call is due now", type(e).__name__)
    return at


async def dial(account: str, result: dict, held: dict) -> Dict[str, Any]:
    """The approved call act → {dialled, simulated?, status, why?}. Never a call without an act; never before the act allows it."""
    from booking_signer import call_routes as CRT, calls as C
    act_id, plan = str(result.get("act_id") or ""), result.get("call_plan") or {}
    if not act_id or not plan.get("phone"):
        log.error("[venue_calls] an approved call with no act or no number — nothing dialled")
        return {"dialled": False, "status": "no_act", "why": "no act to call from"}
    if plan.get("simulate"):   # the sandbox (a TEST person, Kanoe's own test venue): the act is real, nothing is dialled
        log.info("[venue_calls] act %s: simulate — nothing dialled", act_id[-8:])
        return {"dialled": False, "simulated": True, "status": "simulated"}
    if CRT.CALL_STORE is None or not C.calls_enabled() or not C.bland_key():
        log.warning("[venue_calls] act %s: calls are off on this server — nothing dialled", act_id[-8:])
        return {"dialled": False, "status": "calls_off", "why": "phone calls are off on this server"}
    now = NOW()
    brief = brief_of(act_id, plan, held)
    lines = [str(x) for x in held.get("lines") or held.get("read_back") or []] or [f"Call {held.get('venue')} for {held.get('summary')}"]
    when = str(held.get("when") or "")
    row = {"request": None, "call_id": str(uuid.uuid4()), "account_id": account, "venue_key": brief["venue_key"],
           "dialled_number": plan["phone"], "language": "en", "guest_name": held.get("name"), "guest_phone": None,
           "brief": brief, "brief_sha256": C._sha256hex(C._canonical(brief)), "read_back_lines": lines,
           "read_back_sha256": C._sha256hex("\n".join(lines)), "created_at": now, "venue_name": held.get("venue") or "the venue",
           "local_date": when[:10] or None, "local_time": when[11:16] or None, "local_timezone": brief["timezone"],
           "party_size": held.get("party")}
    await CRT.CALL_STORE.put_call(row, None)
    approval = {"by": account, "how": "agapi_act", ACT_KEY: act_id, "said": None, "at": now.isoformat(),
                "read_back_sha256": row["read_back_sha256"], "brief_sha256": row["brief_sha256"]}
    at = due_at(plan, held, now)
    if at > now + timedelta(minutes=1):   # closed now, or the act's 30 minutes: scheduled — place_due dials it when due
        r = await CRT.CALL_STORE.schedule(account, row["call_id"], {**approval, "scheduled_for": at.isoformat(), "opens_at": at.isoformat(),
                                                                    "hours_basis": f"the act's call_plan: {plan.get('when')}", "hours_notes": []},
                                          now, now - CRT.APPROVAL_WINDOW)
        return {"dialled": False, "status": "scheduled" if r == "scheduled" else r, "scheduled_for": at.isoformat(), "call_id": row["call_id"]}
    claimed = await CRT.CALL_STORE.claim(account, row["call_id"], approval, now, now - CRT.APPROVAL_WINDOW, CRT.cap(),
                                         __import__("booking_signer.call_store", fromlist=["x"]).cap_window(now), CRT.account_cap())
    if claimed != "claimed":   # the server's own net (its caps) — the act is told nothing happened
        log.warning("[venue_calls] act %s: not dialled (%s)", act_id[-8:], claimed)
        return {"dialled": False, "status": claimed}
    payload = {**C.bland_payload(brief, row["call_id"]), **{k: v for k, v in {"voicemail": (plan.get("payload") or {}).get("voicemail"),
                                                                              "record": (plan.get("payload") or {}).get("record")}.items() if v is not None}}
    import dataclasses
    from booking_signer import places_terms as PT
    placed = await C.place_call(CRT.HTTP, C.bland_key(), payload)
    placed = dataclasses.replace(placed, answer=PT.scrub_bland(placed.answer, brief))
    await CRT.CALL_STORE.mark_placed(row["call_id"], placed, NOW())
    return {"dialled": bool(placed.placed or placed.uncertain), "status": "placed" if placed.placed else "uncertain" if placed.uncertain else "not_placed",
            "call_id": row["call_id"], **({"why": placed.why} if not placed.placed else {})}


def outcome_of(reading) -> Dict[str, Optional[str]]:
    """A finished call's reading → the act's outcome (confirmed | proposed | declined | no_answer) and who answered."""
    state, outcome = getattr(reading, "state", None), getattr(reading, "outcome", None)
    words = (getattr(reading, "venue_words", None) or "").strip() or None
    if state == "not_reached":
        machine = "voicemail" in (getattr(reading, "why", "") or "").lower() or "machine" in (getattr(reading, "why", "") or "").lower()
        return {"outcome": "no_answer", "answered_by": "machine" if machine else "none", "venue_words": None}
    if outcome == "yes":
        return {"outcome": "confirmed", "answered_by": "human", "venue_words": words}
    if outcome == "no":
        return {"outcome": "declined", "answered_by": "human", "venue_words": words}
    # unclear, another time offered, a question back: NOTHING is booked — the person decides (the act says it as "proposed")
    return {"outcome": "proposed", "answered_by": "human", "venue_words": words}


async def tell(account: str, text: str) -> str:
    """Her words for the act's answer: on their open page (/s2, /next — the live channel) and on their WhatsApp when it's linked."""
    from booking_signer import live_events as LE
    LE.publish(account, {"type": "proactive", "say": text})
    try:
        from booking_signer import guest_whatsapp as GW
        ch = await GW.STORE.channel_of_account(account) if GW.STORE is not None else None
        return (await GW._tell(ch, text)) if ch else "page only (no WhatsApp linked)"
    except Exception as e:
        log.warning("[venue_calls] not told on WhatsApp: %s", type(e).__name__)
        return f"page only ({type(e).__name__})"


async def after_call(call: dict, reading) -> Dict[str, Any]:
    """After EVERY call placed for an act: venue.call_attempt, and its answer said. Returns what happened (the tests read it)."""
    from agapi import venue_submit as VS
    account, act_id = str(call.get("account_id") or ""), act_of(call)
    if not act_id:
        return {"reported": False, "why": "not an act's call"}
    o = outcome_of(reading)
    r = await VS.call_attempt(account, act_id, o["outcome"], o["venue_words"], o["answered_by"])
    if not r.get("ok"):
        log.error("[venue_calls] act %s: the attempt was not recorded (%s) — the call's answer is not said as the act's",
                  act_id[-8:], r["error"]["code"])
        return {"reported": False, "why": r["error"]["code"]}
    res = r["result"]
    if res.get("status") == "refused":   # R10, from the act's own record: the dialler placed a call it wasn't allowed to — a bug here
        log.error("[venue_calls] act %s: R10 REFUSED a call Sasha placed (%s) — the scheduler is wrong; it counts for nothing",
                  act_id[-8:], res.get("reason"))
        return {"reported": True, "refused": res.get("reason")}
    said = str(res.get("say") or "")
    step = res.get("next_step") or {}
    if res.get("state") == "no_answer" and step:   # the last unanswered call: their page, else their number — said with it
        said = f"{said} {step.get('page') or step.get('phone') or ''}".strip()
    told = await tell(account, said) if said else "nothing to say"
    nxt = None
    if res.get("state") == "calling" and (res.get("next_call") or {}).get("allowed_at"):   # no answer, calls left: the next one, when allowed
        held = {"venue": (call.get("brief") or {}).get("venue_name"), "timezone": (call.get("brief") or {}).get("timezone"),
                "summary": None, "lines": call.get("read_back_lines"), "party": None, "when": None}
        plan = {"phone": call.get("dialled_number"), "opening": (call.get("brief") or {}).get("first_sentence"),
                "rules": [], "payload": (call.get("brief") or {}).get("payload") or {}, "next_call": res["next_call"], "simulate": False}
        b = dict(call.get("brief") or {})
        nxt = await _again(account, act_id, b, call, plan, held)
    log.info("[venue_calls] act %s: %s → %s; told: %s; next: %s", act_id[-8:], o["outcome"], res.get("state"), told, nxt)
    return {"reported": True, "state": res.get("state"), "say": said, "told": told, "next": nxt}


async def _again(account: str, act_id: str, brief: dict, call: dict, plan: dict, held: dict) -> str:
    """The act's next call (no answer, calls left): the SAME brief, scheduled at next_call.allowed_at — never sooner."""
    from booking_signer import call_routes as CRT, calls as C
    now = NOW()
    at = due_at(plan, held, now)
    row = {"call_id": str(uuid.uuid4()), "account_id": account, "venue_key": call["venue_key"], "dialled_number": call["dialled_number"],
           "language": call.get("language") or "en", "guest_name": call.get("guest_name"), "guest_phone": call.get("guest_phone"),
           "brief": brief, "brief_sha256": C._sha256hex(C._canonical(brief)), "read_back_lines": call["read_back_lines"],
           "read_back_sha256": call["read_back_sha256"], "created_at": now, "request": None}
    await CRT.CALL_STORE.put_cancel_call(row, str(call["trip_item_id"]))   # the SAME reservation (no new trip item)
    r = await CRT.CALL_STORE.schedule(account, row["call_id"], {"by": account, "how": "agapi_act", ACT_KEY: act_id, "said": None,
                                                                "at": now.isoformat(), "read_back_sha256": row["read_back_sha256"],
                                                                "brief_sha256": row["brief_sha256"], "scheduled_for": at.isoformat(),
                                                                "opens_at": at.isoformat(), "hours_basis": "the act's next_call.allowed_at",
                                                                "hours_notes": []}, now, now - CRT.APPROVAL_WINDOW)
    return f"scheduled for {at.isoformat()[:16]}Z" if r == "scheduled" else f"not scheduled: {r}"


__all__ = ["dial", "after_call", "act_of", "brief_of", "due_at", "outcome_of", "tell", "ACT_KEY"]
