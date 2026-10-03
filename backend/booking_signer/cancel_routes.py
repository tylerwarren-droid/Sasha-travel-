"""Sasha 99 · CANCELLING, BY THE BEST ROUTE THERE IS — the venue's own cancel link, else an email, else a text, else a call.

    GET  /api/booking/reservations/{trip_item_id}/cancel   → the route she'll use, its read-back and its hash
    POST /api/booking/reservations/{trip_item_id}/cancel   {read_back_sha256, approval} → done, once, after the yes

The order (the founder's):
  1. LINK — a cancel link in what the venue sent Sasha about this booking (an email or text to her, on the receipt).
     On the venue's own site she opens it and keeps its page word for word; on a booking PLATFORM she never opens it
     (S-35) — the guest presses it, as with a slot link.
  2. EMAIL — to the venue's address (read on their site), from Sasha's own, asking them to confirm in a reply.
  3. TEXT — from Sasha's number to a venue MOBILE (a Spanish 6xx/7xx read on their site), when texts are on.
  4. CALL — the existing cancel call (calls.py), for a booking Sasha made by phone.
"Reservation cancelled" ONLY once the venue's own words say so — their page, their reply, their text or the call. Until
then the reservation keeps its status and the guest is told it is asked, not done. Stateless: the plan and its read-back
are recomputed at the yes, and the yes must match their hash.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import sentences as SN
from . import venue_read as V
from . import yes as YS
from .account import account_for
from .store import StorageUnavailable

log = logging.getLogger("booking_signer.cancel_routes")
router = APIRouter(prefix="/reservations", tags=["booking-cancel"])
NOW = lambda: datetime.now(timezone.utc)

#: how a pending cancellation is marked on the booking's attempts — a reply on that channel is read as an answer to IT
CANCEL_REQUESTED = "cancel request:"

_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
_CANCEL_WORD = re.compile(r"cancel|anula|annul|storn|disdic", re.I)
#: their words that say it IS cancelled — and the words that undo it
_CANCELLED = re.compile(r"\b(cancelad[ao]s?|anulad[ao]s?|queda(?:n)? (?:cancelad|anulad)|cancel+ed|annul[ée]e?s?|storniert|"
                        r"cancellat[ao]|disdett[ao]|cancelada com sucesso|reserva cancelada|booking cancel+ed)\b", re.I)
_NOT = re.compile(r"\b(no (?:se )?(?:puede|ha podido|podemos)|not (?:been )?cancel|cannot|can't|no pudimos|impossible|imposible)\b", re.I)


def cancel_reading(text: Optional[str]) -> Dict[str, str]:
    """Deterministic: their words confirm the cancellation, or they don't. Nothing inferred."""
    t = text or ""
    if _CANCELLED.search(t) and not _NOT.search(t):
        return {"result": "cancelled", "why": f"their words say it is cancelled: \"{_CANCELLED.search(t).group(0)}\""}
    return {"result": "not_confirmed", "why": "their words don't say it is cancelled — shown as written"}


def _sha(lines: List[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def cancel_links(texts: List[str]) -> List[str]:
    out = []
    for t in texts:
        for u in _URL.findall(t or ""):
            u = u.rstrip(".,;")
            if _CANCEL_WORD.search(u) and u not in out:
                out.append(u)
    return out


def _mobile(facts: List[dict]) -> Optional[str]:
    """A Spanish MOBILE the venue publishes (only a mobile takes a text)."""
    return next((f["value"] for f in facts if f.get("kind") == "phone" and re.fullmatch(r"\+34[67]\d{8}", f.get("value") or "")), None)


async def _booking(account: str, trip_item_id: str) -> Optional[dict]:
    """The booking as everything that made it holds it: its object, its venue read, what the venue wrote, its call."""
    from . import call_routes as CRT, form_rung as FR, ladder_routes as LR
    rows = await CRT.CALL_STORE.receipt_rows(account, trip_item_id)
    form = await FR.STORE.for_item(account, trip_item_id) if hasattr(FR.STORE, "for_item") else None
    if rows is None and form is None:
        return None
    item = (rows or {}).get("item") or {}
    request = item.get("request") or (await FR._request_of(form) if form else None) or {}
    read_id = ((rows or {}).get("call", {}).get("brief") or {}).get("venue_key", "")[5:] or (form or {}).get("read_id")
    read_row = await LR.LADDER_STORE.get_read(account, str(read_id)) if read_id else None
    read = await LR.PT.hydrate_read(LR.HTTP, read_row["read"], NOW()) if read_row else {}
    texts = [w.get("body_text") for w in (rows or {}).get("written") or []] + ([form.get("response_text")] if form else [])
    return {"request": request, "read": read, "read_row": read_row, "texts": [t for t in texts if t], "form": form,
            "item": item,
            "call": (rows or {}).get("call"), "venue": ((read.get("listing") or {}).get("name") or (read_row or {}).get("venue_name") or "the venue")}


def plan(b: Mapping[str, Any]) -> Dict[str, Any]:
    """The first route that exists, in the founder's order, with every route's reason it was or wasn't used."""
    from . import calls as C
    from .followup import own_email
    from .ladder import best_email, emails_ready
    facts = (b.get("read") or {}).get("facts") or []
    tried = []
    links = cancel_links(b["texts"])
    if links:
        return {"route": "link", "url": links[0], "platform": V.platform_of(links[0]), "tried": tried}
    tried.append("no cancel link in anything they sent Sasha")
    em = best_email(facts)
    if em and not emails_ready() and own_email():
        return {"route": "email", "to": em[1]["value"], "source_label": em[1]["source_label"], "tried": tried}
    tried.append("no email address published by them" if not em else f"emails are off ({emails_ready() or 'no address of her own'})")
    mob = _mobile(facts)
    if mob and os.getenv("SASHA_SMS_TO_VENUES", "").strip() == "1" and C.sasha_number():
        return {"route": "sms", "to": mob, "tried": tried}
    tried.append("no mobile published by them" if not mob else "texts to venues are off (SASHA_SMS_TO_VENUES is not 1)")
    if b.get("call") and C.calls_enabled():
        return {"route": "call", "call_id": str(b["call"]["call_id"]), "tried": tried}
    tried.append("no booking call to undo" if not b.get("call") else "phone calls are off")
    return {"route": None, "tried": tried}


_EMAIL = {"es": ("Cancelación de la reserva a nombre de {name}",
                 "Hola, soy Sasha, una concierge de inteligencia artificial de Kanoe Technologies SL. Escribo de parte de {name} para "
                 "cancelar su reserva:\n\n{core}.\n\n¿Podrían confirmarnos la cancelación respondiendo a este correo? Muchas gracias.\n\n"
                 "Sasha (concierge de IA, Kanoe Technologies SL), en nombre de {name}"),
          "en": ("Cancelling the booking under the name {name}",
                 "Hello, this is Sasha, an AI concierge with Kanoe Technologies SL. I'm writing on behalf of {name} to cancel their "
                 "booking:\n\n{core}.\n\nCould you confirm the cancellation by replying to this email? Thank you.\n\n"
                 "Sasha (AI concierge, Kanoe Technologies SL), for {name}")}
_SMS = {"es": "Hola, soy Sasha, concierge de IA de Kanoe. Cancelo la reserva de {name}: {core}. ¿Nos lo confirman respondiendo a este SMS? Gracias.",
        "en": "Hi, this is Sasha, an AI concierge with Kanoe. Cancelling {name}'s booking: {core}. Could you confirm by replying to this text? Thanks."}


_MADE = {"es": {"call": "por teléfono", "form": "con el formulario de su web", "dias": ["lunes", "martes", "miércoles", "jueves",
               "viernes", "sábado", "domingo"], "meses": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"], "ref": "Referencia", "made": "La reserva se hizo {how} el {day}."},
         "en": {"call": "by phone", "form": "with the form on your website", "ref": "Reference", "made": "It was made {how} on {day}."}}


def identifies(b: Mapping[str, Any], lang: str) -> str:
    """Sasha 119 · what lets the venue FIND the booking: its references (theirs, then Sasha's K-…), and how and when it was
    made — "La reserva se hizo por teléfono el jueves 1 de octubre." — every one only when it is known."""
    from . import sentences as SN
    w = _MADE.get(lang, _MADE["en"])
    item, call, form = b.get("item") or {}, b.get("call") or {}, b.get("form") or {}
    refs = [r for r in (item.get("booking_reference"), (call.get("brief") or {}).get("own_reference")) if r]
    out = [f"{w['ref']}: {' / '.join(refs)}."] if refs else []
    how, at = ("call", call.get("created_at")) if call.get("created_at") else ("form", form.get("created_at")) if form.get("created_at") else (None, None)
    if how and at is not None:
        at = datetime.fromisoformat(at) if isinstance(at, str) else at
        d = at.astimezone(ZoneInfo("Europe/Madrid")).date()
        day = f"{w['dias'][d.weekday()]} {d.day} de {w['meses'][d.month - 1]}" if lang == "es" else SN.day_words(d.isoformat())
        out.append(w["made"].format(how=w[how], day=day))
    return " ".join(out)


def _lang(read: Mapping[str, Any]) -> str:
    return "es" if (read or {}).get("country") in ("ES", "MX", "AR", "CO", "CL", "PE") else "en"


def words(b: Mapping[str, Any], p: Mapping[str, Any]) -> Dict[str, Any]:
    """Exactly what she'll do and send — the read-back the yes binds to."""
    from . import followup as FU
    o, venue = b["request"], b["venue"]
    name = (o.get("who") or {}).get("name") or "the guest"
    lang = _lang(b.get("read"))
    core = FU.restatement(lang, o) if o.get("what") else "their reservation"
    out: Dict[str, Any] = {"lang": lang, "name": name}
    if p["route"] == "link":
        out["lines"] = ([f"{venue} sent a cancel link: {p['url']}.",
                         f"It is on {p['platform']}, so I won't open it — you press it, and {p['platform']} confirms to you."] if p["platform"] else
                        [f"{venue} sent a cancel link on their own website: {p['url']}.",
                         "I'll open it once and keep their page word for word. It's cancelled only if their page says so."])
    elif p["route"] == "email":
        subj, body = _EMAIL[lang]
        ident = identifies(b, lang)
        out["email"] = {"subject": subj.format(name=name), "text": body.format(name=name, core=core + (f".\n{ident[:-1]}" if ident else ""))}
        out["lines"] = [f"I'll email {venue} at {p['to']} (the address on {p['source_label']}), from my own address:",
                        f"\"{out['email']['subject']}\" — {out['email']['text'][:400]}",
                        "It's cancelled only once their reply says so; their reply comes onto this booking."]
    elif p["route"] == "sms":
        out["sms"] = _SMS[lang].format(name=name, core=core)[:600]
        out["lines"] = [f"I'll text {venue} on {p['to']} from my own number: \"{out['sms']}\"",
                        "It's cancelled only once their reply says so; their reply comes onto this booking."]
    elif p["route"] == "call":
        out["lines"] = [f"I'll phone {venue} to cancel it — the call you'll see read back next."]
    else:
        out["lines"] = ["I can't reach them to cancel it right now: " + "; ".join(p["tried"]) + "."]
    out["sha256"] = _sha(out["lines"])
    return out


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


@router.get("/{trip_item_id}/cancel")
async def cancel_plan(trip_item_id: str, request: Request):
    account = account_for(request)
    try:
        b = await _booking(account, trip_item_id)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if b is None:
        return _refuse(404, "booking_unknown", "no booking of yours with that id")
    p = plan(b)
    w = words(b, p)
    return {"route": p["route"], "venue": b["venue"], "tried": p["tried"], "url": p.get("url"), "platform": p.get("platform"),
            "call_id": p.get("call_id"), "read_back": {"lines": w["lines"], "sha256": w["sha256"]},
            "sentence": SN.cancel_sentence(b["request"] or {}, b["venue"])}   # S-75 step 1 · one owner of the words


@router.post("/{trip_item_id}/cancel")
async def cancel_go(trip_item_id: str, request: Request):
    from . import call_routes as CRT, emailing as E, followup as FU, guest_receipt as GR, ladder_routes as LR
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("approval"), dict):
        return _refuse(400, "approval_void", "send {read_back_sha256, approval: {how, said}}")
    if not YS.approval_ok(body["approval"]):   # S-75 step 2 · the same rule as a call's yes (yes.py)
        return _refuse(422, "approval_void", YS.APPROVAL_VOID)
    account = account_for(request)
    b = await _booking(account, trip_item_id)
    if b is None:
        return _refuse(404, "booking_unknown", "no booking of yours with that id")
    p = plan(b)
    w = words(b, p)
    if body.get("read_back_sha256") != w["sha256"]:
        return _refuse(422, "read_back_mismatch", "what I'd do has changed since you said yes; look at it again")
    now = NOW()
    if p["route"] is None:
        return _refuse(422, "no_cancel_route", w["lines"][0])
    if p["route"] == "call":
        return {"status": "call", "call_id": p["call_id"], "say": "I'll phone them — here is the call to approve."}
    if p["route"] == "link" and p["platform"]:
        return {"status": "guest_presses", "url": p["url"], "say": f"Press their {p['platform']} cancel link; {p['platform']} confirms to you."}
    if p["route"] == "link":
        try:
            if not await V._allowed(LR.HTTP, p["url"], LR.RESOLVE):
                return {"status": "not_done", "say": "Their site's robots.txt doesn't let me open that link — press it yourself."}
            final, r = await V._get(LR.HTTP, p["url"], LR.RESOLVE)
        except Exception as e:
            return {"status": "not_done", "say": f"I couldn't open their cancel link ({type(e).__name__}) — press it yourself."}
        from .form_rung import _LiveForm_text
        text = " ".join(" ".join(_LiveForm_text(r.text or "")).split())[:4000]
        reading = cancel_reading(text)
        await _record(account, trip_item_id, "web_form", reading, text, "their cancel link, opened by Sasha after your yes", now)
        done = reading["result"] == "cancelled"
        await GR.send_for_route(account, b["venue"], "their own cancel link", "Cancelled by the venue" if done else "Not cancelled yet",
                                {"their_words": text[:1500]})
        return {"status": "cancelled" if done else "not_confirmed", "say": "Reservation cancelled." if done else
                "Their page doesn't say it's cancelled — their words are below.", "their_words": text, "reading": reading}
    if p["route"] == "email":
        email_id = str(uuid.uuid4())
        email = {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": p["to"], "reply_to": E.act_address(email_id),
                 "subject": w["email"]["subject"], "text": w["email"]["text"]}
        row = {"email_id": email_id, "account_id": account, "read_id": (b["read_row"] or {}).get("read_id"), "email": email,
               "email_sha256": E.email_sha256(email), "read_back_lines": w["lines"], "read_back_sha256": w["sha256"], "created_at": now}
        await LR.LADDER_STORE.put_followup_email(row, trip_item_id)
        claimed = await LR.LADDER_STORE.claim_email(account, email_id, {"how": body["approval"].get("how"), "kind": "cancel",
                                                                          "read_back_sha256": w["sha256"], "at": now.isoformat()},
                                                    now, now - LR.APPROVAL_WINDOW, LR.email_cap(), LR.cap_window(now), LR.account_email_cap())
        if claimed != "claimed":
            return _refuse(429 if "cap" in claimed else 409, f"email_{claimed}", "the cancellation email was not sent")
        sent = await E.send(LR.HTTP, email)
        await LR.LADDER_STORE.mark_sent(email_id, sent, now)
        if not sent.sent:
            return {"status": "not_done", "say": f"I couldn't send it: {sent.why}"}
        await GR.send_for_route(account, b["venue"], f"an email from Sasha to {p['to']}", "Cancellation requested — waiting for their reply",
                                {"their_words": None})
        return {"status": "requested", "say": f"Sent to {p['to']}. It's cancelled once their reply says so — I'll show it the moment it arrives."}
    if p["route"] == "sms":
        sent = await GR.send_sms(p["to"], w["sms"], switch="SASHA_SMS_TO_VENUES")
        if not sent.startswith("sms sent"):
            return {"status": "not_done", "say": f"I couldn't text them: {sent}"}
        await _record(account, trip_item_id, "phone", {"result": "requested"}, w["sms"], CANCEL_REQUESTED + " Sasha's text to their mobile", now)
        return {"status": "requested", "say": "Texted. It's cancelled once their reply says so."}
    return _refuse(422, "no_cancel_route", "no route")


async def _record(account: str, trip_item_id: str, method: str, reading: Mapping[str, Any], text: str, observed: str, now) -> None:
    """The attempt, and the reservation moved ONLY to 'cancelled' when their words say so."""
    from . import call_routes as CRT
    store = CRT.CALL_STORE
    cancelled = reading.get("result") == "cancelled"
    if hasattr(store, "trip_items"):   # memory (tests)
        if cancelled and trip_item_id in store.trip_items:
            store.trip_items[trip_item_id]["status"] = "cancelled"
        store.attempts.append({"trip_item_id": trip_item_id, "method": method, "status": "confirmed" if cancelled else "requested",
                               "response_received": text, "observed_by": observed})
        return

    async def fn(conn):
        async with conn.transaction():
            if cancelled:
                await conn.execute("update trip_items set status = 'cancelled', updated_at = now() where id = $1", uuid.UUID(trip_item_id))
            await conn.execute("insert into booking_attempts (trip_item_id, method, attempted_at, status, response_received, response_at, observed_by) "
                               "values ($1, $2, $3, $4, $5, $3, $6)", uuid.UUID(trip_item_id), method, now,
                               "confirmed" if cancelled else "requested", text[:4000], observed)
    await store._run(fn)


__all__ = ["router", "plan", "words", "cancel_reading", "cancel_links"]
