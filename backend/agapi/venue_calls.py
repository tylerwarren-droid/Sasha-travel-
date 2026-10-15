"""Sasha 265 · item 4 (CR 99 §4c) — A CALL IS PLACED ONLY FROM ITS ACT. ONE TRUTH = the AgAPI act (venue.submit_booking route "call"):
its read-back, the person's tap as its approval, and every attempt reported to it. Sasha only dials what the act's call_plan says.
Sasha 269 (CR 100, booking-rules/2.1) — EVERY call is an act's, first or follow-up: Sasha keeps NO retry loop, timer or call decision of
its own. A follow-up ("try once more", R3/R5/R6) is venue.call_again → Sasha dials ONLY its call_plan → venue.call_attempt.

  dial(account, result, held)   an act's open call (status "calling", act_id, call_plan) → nothing dialled (simulate: the sandbox),
                                or ONE booking_calls row per call_plan.call_id (asking twice = the same call, never a second row),
                                built from call_plan alone — Bland gets call_plan.phone, its opening (the AI disclosure first, R7), its
                                rules (R8/R9) and its payload (no voicemail, no recording, 4 minutes) — placed at call_plan.when (closed
                                now: when they open), never before next_call.allowed_at. A number from their Google listing
                                (call_plan.source "listing") is dialled and never stored: the row keeps its hash (places_terms).
  after_call(call, reading)     after EVERY call it placed: venue.call_attempt {act_id, outcome, venue_words, answered_by} and its words
                                told to the person — `say`, then the ONE question (`ask`, its `choices` as the card) after the first
                                no-answer, or their page after the second. NOTHING is redialled here: only the person's "try once more".
  again(account, act_id, why)   venue.call_again (person_asked | R3 | R5 | R6) → dial(its call_plan). No new read-back, no new approval.
  ACT_KEY                       booking_calls keeps act_id in its brief: call_routes refuses to place a booking call without one (the
                                second path, retired). Its own caps stay as the server's net.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

log = logging.getLogger("agapi.venue_calls")

ACT_KEY = "act_id"
PLAN_KEY = "call_plan_id"   # Sasha 269 · the act's open call this row dials (CR 100: call_plan.call_id) — one row per call


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


def row_id(act_id: str, plan: dict) -> str:
    """Sasha 269 · the booking_calls row for an act's open call: the SAME id however often it is asked for (call_plan.call_id)."""
    cid = str(plan.get("call_id") or "")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"agapi-call:{act_id}:{cid}")) if cid else str(uuid.uuid4())


def number_ref(phone: str, place_id: Optional[str]) -> Dict[str, Any]:
    """A listing number as Sasha may keep it (Sasha 64 / CR 100 §D): its place and its hash — never its digits."""
    return {"source": "places", "place_id": place_id, "sha256": hashlib.sha256(phone.encode()).hexdigest()}


def brief_of(act_id: str, plan: dict, held: dict) -> Dict[str, Any]:
    """The call's brief, from the act's call_plan ONLY (its number, its opening, its rules) — nothing Sasha adds to what is said.
    A listing number (source "listing") is not in it: number_ref (its place and hash), re-read at a scheduled dial."""
    rules = [str(r) for r in plan.get("rules") or []]
    task = (f"You are calling {held.get('venue') or 'the venue'} to book {held.get('summary') or 'a table'}. "
            + " ".join(rules))[:2000]
    listing = plan.get("source") == "listing"
    return {ACT_KEY: act_id, PLAN_KEY: plan.get("call_id"), "purpose": "book", "number": None if listing else plan["phone"],
            **({"number_ref": number_ref(plan["phone"], held.get("place_id")), "number_source_kind": "places"} if listing else {}),
            "first_sentence": str(plan.get("opening") or ""), "task": task, "language": "en", "venue_key": f"act:{act_id}",
            "venue_name": held.get("venue"), "timezone": held.get("timezone") or "Europe/Madrid", "payload": dict(plan.get("payload") or {}),
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
    """The act's open call → {dialled, simulated?, status, why?}. Never a call without an act; never before the act allows it; never
    twice for the same call_plan.call_id."""
    from booking_signer import call_routes as CRT, calls as C
    act_id, plan = str(result.get("act_id") or ""), result.get("call_plan") or {}
    if not act_id or not plan.get("phone"):
        log.error("[venue_calls] an approved call with no act or no number — nothing dialled")
        return {"dialled": False, "status": "no_act", "why": "no act to call from"}
    await _keep(account, act_id, plan, held)
    if plan.get("simulate"):   # the sandbox (a TEST person, Kanoe's own test venue): the act is real, nothing is dialled
        log.info("[venue_calls] act %s: simulate — nothing dialled", act_id[-8:])
        return {"dialled": False, "simulated": True, "status": "simulated", "call_plan_id": plan.get("call_id")}
    if CRT.CALL_STORE is None or not C.calls_enabled() or not C.bland_key():
        log.warning("[venue_calls] act %s: calls are off on this server — nothing dialled", act_id[-8:])
        return {"dialled": False, "status": "calls_off", "why": "phone calls are off on this server"}
    now = NOW()
    cid = row_id(act_id, plan)
    if await CRT.CALL_STORE.get_call(account, cid):   # Sasha 269 · asked twice: the SAME open call — one row, one dial
        log.info("[venue_calls] act %s: call %s is already open — not a second one", act_id[-8:], str(plan.get("call_id"))[-8:])
        return {"dialled": False, "status": "already_open", "call_id": cid}
    brief = brief_of(act_id, plan, held)
    listing = plan.get("source") == "listing"
    dialled_number = ("sha256:" + brief["number_ref"]["sha256"]) if listing else plan["phone"]
    lines = [str(x) for x in held.get("lines") or held.get("read_back") or []] or [f"Call {held.get('venue')} for {held.get('summary')}"]
    when = str(held.get("when") or "")
    row = {"request": None, "call_id": cid, "account_id": account, "venue_key": brief["venue_key"],
           "dialled_number": dialled_number, "language": "en", "guest_name": held.get("name"), "guest_phone": None,
           "brief": brief, "brief_sha256": C._sha256hex(C._canonical(brief)), "read_back_lines": lines,
           "read_back_sha256": C._sha256hex("\n".join(lines)), "created_at": now, "venue_name": held.get("venue") or "the venue",
           "local_date": when[:10] or None, "local_time": when[11:16] or None, "local_timezone": brief["timezone"],
           "party_size": held.get("party")}
    if held.get("trip_item_id"):   # a follow-up call: the SAME reservation (no new trip item)
        await CRT.CALL_STORE.put_cancel_call(row, str(held["trip_item_id"]))
    else:
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
    import dataclasses
    from booking_signer import places_terms as PT
    sent = {**brief, "number": plan["phone"]}   # the number for THIS dial only (a listing's: from the act, never stored)
    payload = {**C.bland_payload(sent, row["call_id"]), **{k: v for k, v in {"voicemail": (plan.get("payload") or {}).get("voicemail"),
                                                                             "record": (plan.get("payload") or {}).get("record")}.items() if v is not None}}
    placed = await C.place_call(CRT.HTTP, C.bland_key(), payload)
    placed = dataclasses.replace(placed, answer=PT.scrub_bland(placed.answer, brief))
    await CRT.CALL_STORE.mark_placed(row["call_id"], placed, NOW())
    return {"dialled": bool(placed.placed or placed.uncertain), "status": "placed" if placed.placed else "uncertain" if placed.uncertain else "not_placed",
            "call_id": row["call_id"], **({"why": placed.why} if not placed.placed else {})}


async def _keep(account: str, act_id: str, plan: dict, held: dict) -> None:
    """What a later "try once more" needs to dial the same act — the venue, its zone, its read-back lines, and how its number is found
    again (the venue's own: AgAPI keeps it; a listing's: its place and hash only, re-read then). Never a listing's digits."""
    from agapi import venue_submit as VS
    keep = {"venue": held.get("venue"), "timezone": held.get("timezone"), "lines": list(held.get("lines") or [])[:12],
            "name": held.get("name"), "summary": held.get("summary"), "place_id": held.get("place_id"),
            "call_ref": ({**number_ref(plan["phone"], held.get("place_id")), "source": "listing"} if plan.get("source") == "listing"
                         else {"source": plan.get("source") or "venue"})}
    for a in await VS.acts_of(account):
        if a.get("act_id") == act_id:
            if a.get("call") != keep:
                await VS._remember(account, {**a, "call": keep})
            return


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


def card_of(act_id: str, res: dict) -> Optional[Dict[str, Any]]:
    """Sasha 269 · the no-answer as their page draws it: AgAPI's `ask` with its `choices` (the first time), or their page alone (the
    second) — the labels, the page and the question exactly as the engine gave them."""
    step = res.get("next_step") or {}
    page = step.get("page") if str(step.get("page") or "").startswith("https://") else None
    choices = [{"id": str(c.get("id") or ""), "label": str(c.get("label") or ""), **({"page": c["page"]} if c.get("page") else {})}
               for c in res.get("choices") or [] if c.get("id") in ("call_again", "their_page")]
    if not res.get("ask") and not page:
        return None
    return {"kind": "no_answer", "act_id": act_id, "say": res.get("say"), "ask": res.get("ask") or None, "choices": choices if res.get("ask") else [],
            **({"page": page} if page else {}), **({"phone": step["phone"]} if step.get("phone") and not page else {})}


async def tell(account: str, text: str, card: Optional[dict] = None, wa_text: Optional[str] = None) -> str:
    """Her words for the act's answer: on their open page (/s2, /next — the live channel, with its card) and on their WhatsApp when it's
    linked (no card there: wa_text says the question in words)."""
    from booking_signer import live_events as LE
    LE.publish(account, {"type": "proactive", "say": text, **({"render": card} if card else {})})
    try:
        from booking_signer import guest_whatsapp as GW
        ch = await GW.STORE.channel_of_account(account) if GW.STORE is not None else None
        return (await GW._tell(ch, wa_text or text)) if ch else "page only (no WhatsApp linked)"
    except Exception as e:
        log.warning("[venue_calls] not told on WhatsApp: %s", type(e).__name__)
        return f"page only ({type(e).__name__})"


async def after_call(call: dict, reading) -> Dict[str, Any]:
    """After EVERY call placed for an act: venue.call_attempt, and its answer said. Returns what happened (the tests read it).
    Sasha 269 · NOTHING is redialled from here (the act's 2.1: no automatic "I'll try again") — after a no-answer the person is asked."""
    from agapi import venue_submit as VS
    from app.agent import voice as V
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
    if res.get("status") == "refused":   # R10 / not_asked, from the act's own record: the dialler placed a call it wasn't allowed to
        log.error("[venue_calls] act %s: the act REFUSED a call Sasha placed (%s) — a bug here; it counts for nothing",
                  act_id[-8:], res.get("reason"))
        return {"reported": True, "refused": res.get("reason")}
    if call.get("trip_item_id"):   # a "try once more" keeps the same reservation
        for a in await VS.acts_of(account):
            if a.get("act_id") == act_id and a.get("trip_item_id") != str(call["trip_item_id"]):
                await VS._remember(account, {**a, "trip_item_id": str(call["trip_item_id"])})
    no_answer = o["outcome"] == "no_answer"
    said = V.no_answer_words(res) if no_answer else str(res.get("say") or "")
    card = card_of(act_id, res) if no_answer else None
    told = await tell(account, said, card, V.no_answer_words(res, "whatsapp") if no_answer else None) if said else "nothing to say"
    log.info("[venue_calls] act %s: %s → %s (no answers %s); told: %s", act_id[-8:], o["outcome"], res.get("state"), res.get("no_answers"), told)
    return {"reported": True, "state": res.get("state"), "say": said, "told": told, "card": card}


async def again(account: str, act_id: str, reason: str = "person_asked") -> Dict[str, Any]:
    """Sasha 269 · "try once more" (or R3/R5/R6): venue.call_again under the booking's ONE approval → dial ONLY its call_plan. → {status,
    say, dial} — said: the act's own `say` ("On it — I'll try them again in 30 minutes."). A listing number is re-read for it (Places),
    checked against the hash the person approved, and passed to the act for that one call."""
    from agapi import venue_submit as VS
    from app.agent import voice as V
    act = next((a for a in await VS.acts_of(account) if a.get("act_id") == act_id), None)
    if not act:
        return {"status": "no_act", "say": V.NO_CALL_OPEN}
    ref = (act.get("call") or {}).get("call_ref") or act.get("listing_ref") or {}
    call = None
    if not act.get("call") and act.get("venue_phone"):   # an email / WhatsApp request act (R5/R6): their own number, the first time
        call = {"phone": act["venue_phone"], "source": "venue"}
    elif ref.get("source") in ("listing", "places"):   # its place and hash only: re-read now, checked against the hash, passed for this one call
        from booking_signer import call_routes as CRT, places_terms as PT
        try:
            call = {"phone": await PT.listing_number(CRT.HTTP, ref, NOW()), "source": "listing"}
        except PT.ListingUnavailable as e:
            return {"status": "not_allowed", "say": str(e)[:1].upper() + str(e)[1:] + "."}
    r = await VS.call_again(account, act_id, reason, call)
    if not r.get("ok"):
        return {"status": "error", "code": r["error"]["code"], "say": r["error"]["message"]}
    res = r["result"]
    if res.get("status") != "calling":   # not allowed (the cap, test mode): said in the act's words, nothing dialled
        return {"status": res.get("status"), "say": res.get("say") or "", "next_call": res.get("next_call")}
    held = {"venue": act.get("venue"), "place_id": ref.get("place_id"), **(act.get("call") or {}), "when": act.get("when"),
            "party": act.get("party"), "trip_item_id": act.get("trip_item_id")}
    dialled = await dial(account, res, held)
    return {"status": "calling", "say": res.get("say") or "", "dial": dialled.get("status"), "call_id": (res.get("call_plan") or {}).get("call_id"),
            "approval": res.get("approval")}


__all__ = ["dial", "after_call", "again", "act_of", "brief_of", "due_at", "outcome_of", "tell", "card_of", "row_id", "ACT_KEY", "PLAN_KEY"]
