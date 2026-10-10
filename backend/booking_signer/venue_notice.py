"""Sasha 226 · TELLING A VENUE SOMETHING ABOUT A BOOKING SASHA MADE — "I'm running late" and "change the time / party".

    GET  /api/booking/reservations/{trip_item_id}/notice?kind=late&arrive=HH:MM          → the route, its read-back, its hash
    GET  /api/booking/reservations/{trip_item_id}/notice?kind=change&time=HH:MM&party=N
    POST /api/booking/reservations/{trip_item_id}/notice {kind, …, read_back_sha256, approval}  → done once, after the yes

The routes (the founder's order for each):
  LATE    1. CALL  — a short call in the venue's language (calls.build_notice_call), placed through /calls/{id}/place after the
                    yes; if nobody answers, the EMAIL below goes instead — named in the same read-back, covered by the same yes.
          2. EMAIL — to the address on their site, from Sasha's own.
  CHANGE  1. EMAIL — a written request (their reply is the confirmation), else 2. CALL.
Their words decide: "held" / "changed" only when the venue says so (the call's reading, their reply). A WhatsApp to a venue
isn't possible yet (WhatsApp's first-contact rule), and the read-back never offers it.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from datetime import datetime, time, timezone
from typing import Any, Dict, List, Mapping, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import yes as YS
from .account import account_for
from .store import StorageUnavailable

log = logging.getLogger("booking_signer.venue_notice")
router = APIRouter(prefix="/reservations", tags=["booking-notice"])
NOW = lambda: datetime.now(timezone.utc)   # noqa: E731
KINDS = ("late", "change")
_HM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

_EMAIL = {
    "late": {"es": ("Llegaremos un poco tarde — reserva a nombre de {name}",
                    "Hola, soy Sasha, una concierge de inteligencia artificial de Kanoe Technologies SL. Escribo de parte de {name}: "
                    "{core}. Llegarán con un poco de retraso, sobre las {arrive}. ¿Podrían mantenerles la mesa? Gracias.\n\n"
                    "Sasha (concierge de IA, Kanoe Technologies SL), en nombre de {name}"),
             "en": ("Running a little late — booking under {name}",
                    "Hello, this is Sasha, an AI concierge with Kanoe Technologies SL, writing on behalf of {name}: {core}. They're "
                    "running a little late and will arrive at about {arrive}. Could you hold the table for them? Thank you.\n\n"
                    "Sasha (AI concierge, Kanoe Technologies SL), for {name}")},
    "change": {"es": ("Cambio de la reserva a nombre de {name}",
                      "Hola, soy Sasha, una concierge de inteligencia artificial de Kanoe Technologies SL. Escribo de parte de {name}: "
                      "{core}. ¿Sería posible cambiarla a {party} personas a las {time}? Si no es posible, la reserva se queda como está. "
                      "¿Nos lo confirman respondiendo a este correo? Gracias.\n\nSasha (concierge de IA, Kanoe Technologies SL), en nombre de {name}"),
               "en": ("Changing the booking under {name}",
                      "Hello, this is Sasha, an AI concierge with Kanoe Technologies SL, writing on behalf of {name}: {core}. Could it "
                      "be changed to {party} people at {time}? If that isn't possible, the booking stays as it is. Could you confirm by "
                      "replying to this email? Thank you.\n\nSasha (AI concierge, Kanoe Technologies SL), for {name}")},
}


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def _sha(lines: List[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _hm(v: Any) -> Optional[time]:
    m = _HM.match(str(v or "").strip())
    return time(int(m.group(1)), int(m.group(2))) if m else None


def particulars(o: Mapping[str, Any]) -> Optional[dict]:
    """The booking's own particulars (reservation/1): its day, time, party and name — never re-typed."""
    at = str(((o.get("when") or {}).get("at")) or "")
    if len(at) < 16:
        return None
    return {"date": at[:10], "time": at[11:16], "party": int(((o.get("how_many") or {}).get("count")) or 2),
            "name": ((o.get("who") or {}).get("name")) or "the guest"}


def _email_route(b: Mapping[str, Any]) -> Optional[dict]:
    from .followup import own_email
    from .ladder import best_email, emails_ready
    em = best_email(((b.get("read") or {}).get("facts")) or [])
    if em and not emails_ready() and own_email():
        return {"to": em[1]["value"], "source_label": em[1]["source_label"]}
    return None


def _lang(read: Mapping[str, Any]) -> str:
    return "es" if (read or {}).get("country") in ("ES", "MX", "AR", "CO", "CL", "PE") else "en"


def _our_test_venue(b: Mapping[str, Any]) -> bool:
    """The S2 demo setting's stand-in (its read is of OUR test venue): by its marked name, or the page it was read from."""
    from .ladder_routes import STANDIN_MARK
    read, row = b.get("read") or {}, b.get("read_row") or {}
    return (STANDIN_MARK in str(read.get("name") or "") or STANDIN_MARK in str(row.get("venue_name") or "")
            or "/api/booking/test-venue/" in str(read.get("sources") or ""))


async def plan(account: str, b: Mapping[str, Any], kind: str, args: Mapping[str, Any]) -> Dict[str, Any]:
    """The route, the read-back the yes binds to, and (for a call) the prepared call. Nothing is sent."""
    from . import calls as C, followup as FU, ladder as L, ladder_routes as LR, call_routes as CRT
    o, venue = b.get("request") or {}, b["venue"]
    pp = particulars(o)
    if not pp:
        return {"route": None, "lines": [f"I can't tell when that booking at {venue} is, so I can't tell them anything about it."]}
    arrive, new_time = _hm(args.get("arrive")), _hm(args.get("time"))
    new_party = int(args["party"]) if str(args.get("party") or "").isdigit() else None
    if kind == "late" and not arrive:
        return {"route": None, "lines": ["What time will you get there?"], "ask": "arrive"}
    if kind == "change" and not (new_time or new_party):
        return {"route": None, "lines": ["What should it change to — a new time, or a different number of people?"], "ask": "change"}
    surname = C.surname_of(pp["name"])
    head = (f"I'll call {venue} and say the {surname} table for {pp['party']} at {pp['time']} will arrive about {arrive.strftime('%H:%M')}."
            if kind == "late" else
            f"I'll ask {venue} to change the {surname} table for {pp['party']} at {pp['time']} to "
            f"{new_party or pp['party']} people at {(new_time or _hm(pp['time'])).strftime('%H:%M')}.")
    em = _email_route(b)
    lang = _lang(b.get("read"))
    core = FU.restatement(lang, o) if o.get("what") else "their reservation"
    mail = None
    if em:
        subj, text = _EMAIL[kind][lang]
        mail = {"to": em["to"], "subject": subj.format(name=pp["name"]),
                "text": text.format(name=pp["name"], core=core, arrive=arrive.strftime("%H:%M") if arrive else "",
                                    party=new_party or pp["party"], time=(new_time or _hm(pp["time"])).strftime("%H:%M"))}
    call = None
    read_row = b.get("read_row")
    if read_row and L.calls_ready(account) is None and (kind == "late" or not mail):
        try:
            if _our_test_venue(b):   # the S2 demo setting's stand-in: OUR test venue's phone is the test line (never a real venue)
                import dataclasses
                venue_c = dataclasses.replace(C.test_line(), name=venue)
            else:
                venue_c = await LR.call_venue_from_read(account, read_row["read_id"])
            p = C.parse_call_particulars({**pp, "phone": ""})
            built = C.build_notice_call(venue_c, p, NOW(), kind, reference=((b.get("item") or {}).get("booking_reference")),
                                        arrive=arrive, new_time=new_time, new_party=new_party)
            call = {"venue": venue_c, "built": built, "particulars": p}
        except C.CallRefused as e:
            log.info("[venue_notice] no call: %s", e)
    if kind == "late" and call:
        lines = [head] + call["built"]["read_back_lines"][1:3] + \
                ([f"If nobody answers, I'll email them at {mail['to']} instead."] if mail else ["If nobody answers, I'll tell you — I can't reach them another way."]) + ["OK?"]
        return {"route": "call", "lines": lines, "call": call, "email": mail}
    if mail:
        verb = "email" if kind == "change" else "email"
        lines = [head.replace("I'll call", f"I'll {verb}"), f"To {mail['to']} (the address on {em['source_label']}), from my own address:",
                 f"\"{mail['subject']}\" — {mail['text'][:300]}",
                 ("It's held only once they reply to say so." if kind == "late" else "It's changed only once they reply to say so; until then your booking stays as it is."),
                 "OK?"]
        return {"route": "email", "lines": lines, "email": mail}
    if call:   # change, no email: by phone
        lines = [head] + call["built"]["read_back_lines"][1:3] + ["It's changed only if they say so on the call.", "OK?"]
        return {"route": "call", "lines": lines, "call": call}
    why = L.calls_ready(account) or "no phone number was read for them"
    return {"route": None, "lines": [f"I can't reach {venue} for that right now: calls aren't possible ({why}) and they publish no email address."]}


async def _booking(account: str, trip_item_id: str) -> Optional[dict]:
    from . import cancel_routes as CR
    return await CR._booking(account, trip_item_id)


@router.get("/{trip_item_id}/notice")
async def notice_plan(trip_item_id: str, request: Request):
    account = account_for(request)
    kind = request.query_params.get("kind") or ""
    if kind not in KINDS:
        return _refuse(400, "kind_invalid", "kind is late or change")
    try:
        b = await _booking(account, trip_item_id)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if b is None:
        return _refuse(404, "booking_unknown", "no booking of yours with that id")
    p = await plan(account, b, kind, dict(request.query_params))
    return {"route": p["route"], "venue": b["venue"], "ask": p.get("ask"),
            "read_back": {"lines": p["lines"], "sha256": _sha(p["lines"])}}


@router.post("/{trip_item_id}/notice")
async def notice_go(trip_item_id: str, request: Request):
    from . import call_routes as CRT, emailing as E, ladder_routes as LR
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("approval"), dict) or body.get("kind") not in KINDS:
        return _refuse(400, "approval_void", "send {kind, …, read_back_sha256, approval: {how, said}}")
    if not YS.approval_ok(body["approval"]):
        return _refuse(422, "approval_void", YS.APPROVAL_VOID)
    account = account_for(request)
    b = await _booking(account, trip_item_id)
    if b is None:
        return _refuse(404, "booking_unknown", "no booking of yours with that id")
    kind = body["kind"]
    p = await plan(account, b, kind, body)
    if body.get("read_back_sha256") != _sha(p["lines"]):
        return _refuse(422, "read_back_mismatch", "what I'd do has changed since you said yes; look at it again")
    if p["route"] is None:
        return _refuse(422, "no_route", p["lines"][0])
    now = NOW()
    if p["route"] == "call":
        c = p["call"]
        row = {"request": None, "call_id": str(uuid.uuid4()), "account_id": account, "venue_key": c["venue"].key,
               "dialled_number": c["built"]["brief"]["number"], "language": c["built"]["brief"]["language"], "guest_name": c["particulars"].name,
               "guest_phone": c["particulars"].phone, "brief": {**c["built"]["brief"], "notice_trip_item_id": trip_item_id,
                                                                **({"fallback_email": p["email"]} if p.get("email") else {})},
               "read_back_lines": c["built"]["read_back_lines"], "read_back_sha256": c["built"]["read_back_sha256"], "created_at": now}
        from . import calls as C
        row["brief_sha256"] = C._sha256hex(C._canonical(row["brief"]))   # the brief as stored (with its trip item and fallback)
        try:
            await CRT.CALL_STORE.put_cancel_call(row, trip_item_id)   # a notice call sits on the SAME reservation (as a cancel call does)
        except StorageUnavailable as e:
            return _refuse(503, e.rule, e.detail)
        return {"status": "call_prepared", "call_id": row["call_id"], "call_read_back_sha256": row["read_back_sha256"]}
    # email
    mail = p["email"]
    email_id = str(uuid.uuid4())
    email = {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": mail["to"], "reply_to": E.act_address(email_id),
             "subject": mail["subject"], "text": mail["text"]}
    row = {"email_id": email_id, "account_id": account, "read_id": (b.get("read_row") or {}).get("read_id"), "email": email,
           "email_sha256": E.email_sha256(email), "read_back_lines": p["lines"], "read_back_sha256": _sha(p["lines"]), "created_at": now}
    await LR.LADDER_STORE.put_followup_email(row, trip_item_id)
    claimed = await LR.LADDER_STORE.claim_email(account, email_id, {"how": body["approval"].get("how"), "kind": kind,
                                                                      "read_back_sha256": row["read_back_sha256"], "at": now.isoformat()},
                                                now, now - LR.APPROVAL_WINDOW, LR.email_cap(), LR.cap_window(now), LR.account_email_cap())
    if claimed != "claimed":
        return _refuse(429 if "cap" in claimed else 409, f"email_{claimed}", "the email was not sent")
    sent = await E.send(LR.HTTP, email)
    await LR.LADDER_STORE.mark_sent(email_id, sent, now)
    if not sent.sent:
        return {"status": "not_done", "say": f"I couldn't send it: {sent.why}"}
    return {"status": "requested", "email_id": sent.email_id if hasattr(sent, "email_id") else None,
            "say": f"Emailed {b['venue']} at {mail['to']}. " + ("It's held once they reply to say so." if kind == "late" else
                                                                 "It's changed once their reply says so; until then it stays as it was.")}


async def after_call(account: str, call: Mapping[str, Any], reading) -> None:
    """call_routes._follow_up, for a LATE or CHANGE call: the outcome told on their page in the venue's own words; nobody
    answered → the email named in the same read-back goes instead (covered by that yes)."""
    from . import calls as C, emailing as E, live_events as LE, ladder_routes as LR
    brief = call.get("brief") or {}
    purpose, venue = brief.get("purpose"), brief.get("venue_name") or "the venue"
    say = C.say_for(venue, reading, purpose)
    lines = [say]
    fb = brief.get("fallback_email")
    if reading.state == "not_reached" and fb:
        email = {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": fb["to"], "subject": fb["subject"], "text": fb["text"]}
        try:
            sent = await E.send(LR.HTTP, email)
            lines.append(f"So I emailed them at {fb['to']} instead." if sent.sent else f"I couldn't email them either: {sent.why}")
        except Exception as e:
            lines.append(f"I couldn't email them either ({type(e).__name__}).")
    LE.publish(account, {"type": "venue_notice", "purpose": purpose, "venue": venue, "state": reading.state, "outcome": reading.outcome,
                         "say": " ".join(lines), "lines": lines, "trip_item_id": brief.get("notice_trip_item_id")})


__all__ = ["router", "plan", "particulars", "after_call", "KINDS"]
