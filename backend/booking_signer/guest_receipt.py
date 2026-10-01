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


async def send_after_call(call: Mapping[str, Any]) -> str:
    """Once a booking call's reading is recorded. Returns what happened, in words (logged; the tests read it)."""
    from . import call_routes as CRT, ladder_routes as LR, receipt as RC
    from .ladder import emails_ready
    if ((call.get("brief") or {}).get("purpose") or "book") != "book":
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
    return "sent"


__all__ = ["compose", "send_after_call", "address_of"]
