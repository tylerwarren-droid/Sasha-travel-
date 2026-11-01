"""CR 62 · WhatsApp to someone the person names, from Sasha's number — the SAME contract and logic as the AgAPI sandbox's
messages.send_whatsapp (agapi/powers.py). Wiring is the Sasha tab's (docs/sasha/s2-powers-2-wiring.md).

    send_whatsapp [Austen]  First call: the exact message read back (awaiting_yes). A LATER turn, their explicit yes, the SAME
                  message, within 15 minutes → sent once. WhatsApp's rule decides WHICH message:
                    · the recipient wrote to Sasha in the last 24 hours → the person's own words;
                    · otherwise ONLY the approved first-contact template, which asks the recipient whether they want the message
                      (needs on_behalf_of: the person's name). Their note waits for the reply and a new yes. Until Tyler's template
                      is approved and its ContentSid set (SASHA_WA_ONBEHALF_SID), she says plainly it isn't possible yet.
                  REAL sending only for the founder and Jon's allow-listed account (s2_tools.live_for); everyone else: captured,
                  "not sent", said so. A STOP from the recipient is final.
    on_contact_message      the inbound hook (one call in guest_whatsapp.dispatch): a reply from a number Sasha wrote to FOR
                  someone is kept as THEIR words (untrusted) for that person, opens the window, and is never answered by the model.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from agapi import powers as P, s2_records as REC

log = logging.getLogger("agapi.s2.whatsapp")
YES_WINDOW = timedelta(minutes=15)
_HELD: Dict[str, dict] = {}                                 # account → the WhatsApp read back (sha, when, the message)
OUTBOX: List[dict] = []                                     # captured (not the founder / Jon): never sent
_STOP = re.compile(r"^\s*(stop|parar|baja|unsubscribe|arr[eê]t)\s*[.!]?\s*$", re.I)
REPLY_KEEP = timedelta(days=30)                             # a reply counts as "to Sasha's message" for 30 days after it
THANKS = "Thank you — I've passed your reply on to {who}."
STOPPED = "OK — I won't write to you again."


def template_sid() -> str:
    """Tyler's approved first-contact template (Twilio Content API), once Meta approves it. Empty: not possible yet."""
    return os.getenv("SASHA_WA_ONBEHALF_SID", "").strip()


def _from() -> str:
    """Sasha's number that serves guests — replies come back through the guest pipeline, where on_contact_message sits."""
    from booking_signer import guest_whatsapp as GW
    return GW.sender_for(None) if GW.guest_numbers() else ""


async def send_whatsapp(ctx, a: dict) -> dict:
    from agapi.v0 import ToolError
    to = a.get("to") or {}
    try:
        number = P._phone(to.get("number", ""))
    except P.Refused as e:
        raise ToolError("invalid_input", e.message)
    c = await REC.contact(ctx.account, number)
    if c and c.get("opted_out_at"):
        raise ToolError("recipient_opted_out", "they replied STOP to Sasha — she never writes to them again. Nothing was sent.")
    # Sasha 285 · CR 118 (c) · ONE WHATSAPP PATH: a WhatsApp to a third party leaves Kanoe's number only through AgAPI (messages.send_whatsapp,
    # its send gate — and CR 121 refuses a venue's number there). Sasha 319: old S1's own Twilio send is deleted too — every surface: the
    # message in THEIR OWN WhatsApp, pre-filled; they send it.
    return _in_their_whatsapp(number, to.get("name"), a.get("text"), "agapi_only")


WHY_THEIRS = {
    "no_window": "WhatsApp only lets me write first to someone who's messaged my number in the last 24 hours — so it's ready in "
                 "your WhatsApp: press send.",
    "not_live": "In this beta I only send from my own number for a few accounts — so it's ready in your WhatsApp: press send.",
    # Sasha 285 · CR 118: a third party is never written to from Kanoe's number except through AgAPI's one send path
    "agapi_only": "I don't send WhatsApps to other people from my number — so it's ready in your WhatsApp: press send.",
}


def _in_their_whatsapp(number: str, name: Optional[str], text: Optional[str], why: str) -> dict:
    """/s2 · the drafted message in the person's OWN WhatsApp (a wa.me link, pre-filled to that number): they press send. Sasha
    sends nothing, so there's no yes to bind — the tap on Send in their WhatsApp is theirs."""
    from urllib.parse import quote
    from agapi.v0 import ToolError
    body = (text or "").strip()
    if not body:
        raise ToolError("invalid_input", "draft the message first (text) — it opens in their WhatsApp, pre-filled, for them to send")
    link = f"https://wa.me/{re.sub(r'[^0-9]', '', number)}?text={quote(body[:1500])}"
    return {"status": "open_in_their_whatsapp", "sent_by_sasha": False, "to": {"name": name, "number": number}, "text": body[:1500],
            "open": link, "why": WHY_THEIRS[why],
            "say": f"Say this one line, word for word: \"{WHY_THEIRS[why]}\" The card has the message and an Open in WhatsApp button. "
                   "Never say it was sent: they send it."}


async def on_contact_message(sender: str, body: str) -> Optional[str]:
    """The inbound hook. None: not a reply to someone Sasha wrote to — the guest pipeline runs as before. Otherwise the reply
    is kept (their words) for the person Sasha wrote for, and a fixed sentence is the answer (never the model)."""
    try:
        number = P._phone(sender)
    except P.Refused:
        return None
    now = datetime.now(timezone.utc)
    cs = [c for c in await REC.contacts_for_number(number)
          if datetime.fromisoformat(str(c["first_contact_at"]).replace("Z", "+00:00")) > now - REPLY_KEEP]
    if not cs:
        return None
    stop = bool(_STOP.match(body or ""))
    if stop:   # final, for EVERY account that wrote to them
        for c in cs:
            await REC.replied(c["account_id"], number, body or "", True)
        return STOPPED
    c = cs[0]                                              # the most recent person Sasha wrote to them for
    if c.get("opted_out_at"):
        return ""
    await REC.replied(c["account_id"], number, body or "", False)
    log.info("[s2] a WhatsApp reply kept for its account (%s chars)", len(body or ""))
    return THANKS.format(who=c.get("on_behalf_of") or "them")


def tools() -> List[dict]:
    from agapi.v0 import _t
    props = {"to": {"type": "object", "additionalProperties": False, "required": ["number"],
                    "properties": {"number": {"type": "string", "maxLength": 24, "description": "full international, e.g. +44 7700 900123"},
                                   "name": {"type": "string", "maxLength": 120}}},
             "text": {"type": "string", "minLength": 1, "maxLength": 1000},
             "on_behalf_of": {"type": "string", "maxLength": 60, "description": "the person's name, for WhatsApp's first message"},
             "approval": {"type": "object", "properties": {"said": {"type": "string"}},
                          "description": "the person's own words (filled by the caller from the real message)"}}
    return [_t("send_whatsapp", "Austen", send_whatsapp, "WhatsApp someone the person names, FROM SASHA'S NUMBER (never their phone). "
               "The first call returns the exact message to read back; say it, ask 'shall I send it?', and call again with the SAME "
               "message after their yes in a later turn. If the recipient hasn't written to Sasha in 24 hours, WhatsApp only allows "
               "an approved first message that asks them first (needs on_behalf_of); say that plainly. A question is never a yes.",
               props, ["to"], {"type": "object", "properties": {"status": {"enum": ["awaiting_yes", "sent", "not_sent", "needs_first_contact",
                                                                                  "not_possible_yet"]}}},
               ["invalid_input", "no_explicit_yes", "recipient_opted_out", "upstream_refused", "upstream_unreachable", "already_done"],
               austen=True)]
