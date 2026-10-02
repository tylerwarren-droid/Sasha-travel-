"""Sasha 90 · AFTER EVERY BOOKING, THE GUEST GETS THE RECEIPT — whatever the outcome, from Sasha's own address
(sasha@booking.kanoe.ai), never depending on the venue having an email.

Sent once, when the call's reading is recorded (call_routes._follow_up, awaited — never fire-and-forget): the venue by
its name, what, when, for whom, the status in plain words, BOTH references, their words verbatim, and where the whole
call and the yes are kept. It restates only what the receipt (receipt.py) holds — nothing new is claimed in an email.

To whom: the account's own verified address (Supabase Auth). The founder's session still runs as the demo account
until FOUNDER_ACCOUNT_ID is set, so for that account SASHA_FOUNDER_EMAIL is used. No address → not sent, and said.
SMS / WhatsApp to the guest: added once Sasha's own number is live (S-70); until then the email is the receipt's channel.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Mapping, Optional

from . import emailing as E

log = logging.getLogger("booking_signer.guest_receipt")

_UNIT_ONE = {"people": "person", "sessions": "session", "pieces": "piece", "places": "place"}


def compose(rc: Mapping[str, Any], to: str) -> dict:
    """The receipt email, from a receipt (receipt.build)."""
    v = rc["venue"]["name"]
    refs = rc.get("references") or {}
    n, unit = rc.get("count"), rc.get("unit") or "people"
    what = f"{rc.get('what') or 'a booking'}" + (f" · {n} {_UNIT_ONE.get(unit, unit) if n == 1 else unit}" if n else "")
    when = " at ".join(x for x in (rc.get("date"), rc.get("time")) if x) or "no time set yet"
    words = rc.get("their_words")
    why = (rc.get("reading") or {}).get("why")
    subject = f"Your booking at {v}: {rc.get('status_words') or 'see the receipt'}" + (f" · Ref. {refs['sasha']}" if refs.get("sasha") else "")
    lines = [
        "Here is the receipt for the booking Sasha made for you.", "",
        v, what, f"When: {when}" + (f" ({rc['timezone']} time)" if rc.get("timezone") else ""),
        f"Under the name: {rc.get('for_whom') or '—'}",
        f"Status: {rc.get('status_words') or '—'}",
        f"Their reference: {refs.get('venue') or 'they gave none'}",
        f"Sasha's reference: {refs.get('sasha') or 'none'}", "",
    ]
    if words:
        lines += [f"What they said, word for word: \"{words}\""]
    wp = rc.get("written_promise") or {}
    if wp.get("asked"):
        lines += [f"Asked to confirm in writing, they said: \"{wp['their_answer']}\"" if wp.get("their_answer")
                  else "Asked to confirm in writing, they didn't answer."]
    for w in rc.get("written") or []:
        if w.get("text"):
            lines += [f"They wrote ({w.get('channel')}): \"{w['text'][:500]}\""]
    if why:
        lines += [f"How it was read: {why}"]
    lines += ["", "The whole call, word for word, and the yes it rests on are on this booking's receipt in your itinerary.",
              "Nothing in this email is new: it restates what the venue said.", "",
              "— Sasha (AI concierge, Kanoe Technologies SL)"]
    return {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": to, "subject": subject, "text": "\n".join(lines)}


async def address_of(account: str) -> Optional[str]:
    from . import ladder_routes as LR
    from .account import DEMO_ACCOUNT_ID
    addr = await LR.LADDER_STORE.account_email(account)
    if not addr and account == DEMO_ACCOUNT_ID:
        addr = os.getenv("SASHA_FOUNDER_EMAIL", "").strip() or None
    return addr


def compose_cancel(brief: Mapping[str, Any], venue: str, outcome: Optional[str], words: Optional[str], to: str) -> dict:
    """Sasha 96 · the guest's copy of a cancellation: done or not, with the venue's words as the proof."""
    done = outcome == "yes"
    when = " at ".join(x for x in (brief.get("date"), brief.get("time")) if x)
    lines = [("Your reservation is cancelled." if done else "Your reservation is NOT cancelled yet — read their words below."), "",
             venue, f"Was: {when}, for {brief.get('party') or '—'}, under {brief.get('name') or '—'}"
             + (f" · their reference {brief['reference']}" if brief.get("reference") else ""), ""]
    if words:
        lines += [f"What they said on the call, word for word: \"{words}\""]
    lines += ["", "The call is kept, word for word, on the booking's receipt in your itinerary.", "",
              "— Sasha (AI concierge, Kanoe Technologies SL)"]
    return {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": to,
            "subject": f"{'Cancelled' if done else 'Not cancelled yet'}: your booking at {venue}", "text": "\n".join(lines)}


async def send_sms(to: Optional[str], body: str) -> str:
    """Sasha 96 · a text to the guest FROM Sasha's own number (S-70). Off unless SASHA_SMS_TO_GUEST=1; never fakes a send."""
    import base64
    import urllib.parse
    from . import calls as C, ladder_routes as LR
    if os.getenv("SASHA_SMS_TO_GUEST", "").strip() != "1":
        return "sms not sent: texts to guests are off (SASHA_SMS_TO_GUEST is not 1)"
    sid, token, frm = os.getenv("TWILIO_ACCOUNT_SID", "").strip(), os.getenv("TWILIO_AUTH_TOKEN", "").strip(), C.sasha_number()
    if not (sid and token and frm and to):
        return "sms not sent: no Twilio account, no Sasha number, or no guest mobile"
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            r = await client.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                                  headers={"authorization": f"Basic {auth}"}, data={"From": frm, "To": to, "Body": body[:600]})
        ok = r.status_code in (200, 201) and (r.json() or {}).get("sid")
        if not ok:
            log.error("[guest_receipt] SMS to the guest not accepted: HTTP %s %s", r.status_code, r.text[:200])
        return "sms sent" if ok else f"sms not sent: Twilio answered HTTP {r.status_code}"
    except Exception as e:
        log.error("[guest_receipt] SMS to the guest failed: %s: %s", type(e).__name__, e)
        return f"sms not sent: {type(e).__name__}"


async def send_after_call(call: Mapping[str, Any]) -> str:
    """Once a booking call's reading is recorded. Returns what happened, in words (logged; the tests read it)."""
    from . import call_routes as CRT, ladder_routes as LR, receipt as RC
    from .ladder import emails_ready
    brief = call.get("brief") or {}
    if (brief.get("purpose") or "book") == "cancel":
        return await send_after_cancel(call)
    if (brief.get("purpose") or "book") != "book":
        return "not a booking call"
    why = emails_ready()
    if why:
        return f"not sent: {why}"
    account = str(call["account_id"])
    to = await address_of(account)
    if not to:
        return "not sent: the guest has no email address on their account"
    rows = await CRT.CALL_STORE.receipt_rows(account, str(call["trip_item_id"]))
    if rows is None:
        return "not sent: no receipt for that reservation"
    read = await CRT._read_of(account, rows["call"].get("brief") or {})
    listed = (((read or {}).get("listing") or {}).get("name") or "").strip()
    stored = (rows["call"].get("brief") or {}).get("venue_name") or rows["item"].get("provider_name") or "the venue"
    rc = RC.build(rows["call"], rows["item"], rows["written"], {"name": listed or stored, "source": ""})
    sent = await E.send(LR.HTTP, compose(rc, to))
    if not sent.sent:
        log.error("[guest_receipt] call %s: the receipt email was not sent: %s", call.get("call_id"), sent.why)
        return f"not sent: {sent.why}"
    log.info("[guest_receipt] call %s: receipt sent to the guest (%s)", call.get("call_id"), sent.provider_id)
    refs = rc.get("references") or {}
    sms = await send_sms(rc.get("phone_given_if_asked"),
                         f"Sasha: {rc['venue']['name']}, {rc.get('date')} {rc.get('time') or ''}, {rc.get('count') or ''} — "
                         f"{rc.get('status_words')}." + (f" Ref. {refs['sasha']}." if refs.get("sasha") else "") + " Receipt in your email.")
    log.info("[guest_receipt] call %s: %s", call.get("call_id"), sms)
    return "sent"


async def send_after_cancel(call: Mapping[str, Any]) -> str:
    """Sasha 96 · after a CANCEL call's reading: the guest's copy by email (and a text, when texts are on)."""
    from . import call_routes as CRT, ladder_routes as LR
    from .ladder import emails_ready
    why = emails_ready()
    if why:
        return f"not sent: {why}"
    account = str(call["account_id"])
    to = await address_of(account)
    if not to:
        return "not sent: the guest has no email address on their account"
    brief = call.get("brief") or {}
    read = await CRT._read_of(account, brief)
    venue = (((read or {}).get("listing") or {}).get("name") or "").strip() or brief.get("venue_name") or "the venue"
    fresh = await CRT.CALL_STORE.get_call(account, str(call["call_id"])) or dict(call)
    sent = await E.send(LR.HTTP, compose_cancel(brief, venue, fresh.get("outcome"), fresh.get("venue_words"), to))
    if not sent.sent:
        log.error("[guest_receipt] cancel call %s: the guest's copy was not sent: %s", call.get("call_id"), sent.why)
        return f"not sent: {sent.why}"
    done = fresh.get("outcome") == "yes"
    log.info("[guest_receipt] cancel call %s: %s", call.get("call_id"), await send_sms(
        brief.get("phone"), f"Sasha: your booking at {venue}, {brief.get('date')} {brief.get('time')} — "
                            + ("cancelled." if done else "NOT cancelled yet; details in your email.")))
    return "sent"


__all__ = ["compose", "compose_cancel", "send_after_call", "send_after_cancel", "send_sms", "address_of"]
