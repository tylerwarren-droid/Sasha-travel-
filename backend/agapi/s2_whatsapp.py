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

import hashlib
import logging
import os
import re
import secrets
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


async def _twilio(frm: str, to: str, *, body: Optional[str] = None, content_sid: Optional[str] = None,
                  variables: Optional[dict] = None) -> dict:
    """→ {"sid": "SM…"} or {"why": …}. The provider's own message id is the proof; Sasha 162's Sender doesn't return it."""
    from booking_signer import guest_whatsapp as GW
    auth = GW.SENDER._auth()
    if not auth:
        return {"why": "no Twilio account"}
    data = {"From": f"whatsapp:{frm}", "To": f"whatsapp:{to}"}
    if content_sid:
        data["ContentSid"] = content_sid
        data["ContentVariables"] = __import__("json").dumps({str(k): str(v) for k, v in (variables or {}).items()})
    else:
        data["Body"] = (body or "")[:1500]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            r = await client.post(f"https://api.twilio.com/2010-04-01/Accounts/{auth[0]}/Messages.json",
                                  headers={"authorization": f"Basic {auth[1]}"}, data=data)
        sid = (r.json() or {}).get("sid") if r.status_code in (200, 201) else None
        return {"sid": sid} if sid else {"why": f"Twilio answered HTTP {r.status_code}", "http_status": r.status_code}
    except Exception as e:
        return {"why": type(e).__name__}


async def send_whatsapp(ctx, a: dict) -> dict:
    from agapi.v0 import ToolError, claim
    from agapi.s2_tools import live_for, strict_yes
    to = a.get("to") or {}
    try:
        number = P._phone(to.get("number", ""))
    except P.Refused as e:
        raise ToolError("invalid_input", e.message)
    c = await REC.contact(ctx.account, number)
    if c and c.get("opted_out_at"):
        raise ToolError("recipient_opted_out", "they replied STOP to Sasha — she never writes to them again. Nothing was sent.")
    now = datetime.now(timezone.utc)
    live, frm = live_for(ctx.account), _from() or "Sasha's WhatsApp"
    free = bool(c) and P.window_open(c.get("last_inbound_at"), now.isoformat())
    try:
        if free:
            if not a.get("text"):
                raise ToolError("invalid_input", "they wrote to Sasha in the last 24 hours: send the person's own words (text)")
            msg = P.whatsapp_message(frm, number, to.get("name"), text=a["text"])
        else:
            if live and not template_sid():
                return {"status": "not_possible_yet", "say": P.NO_TEMPLATE_YET}
            if not a.get("on_behalf_of"):
                return {"status": "needs_first_contact", "say": P.NO_FREE_TEXT + " Ask what name to sign it with, then call again "
                        "with on_behalf_of.", "template": P.ON_BEHALF["body"]}
            msg = P.whatsapp_message(frm, number, to.get("name"), template=P.ON_BEHALF["name"], on_behalf_of=a["on_behalf_of"])
    except P.Refused as e:
        raise ToolError("invalid_input", e.message)
    sha, lines = P.sha256(msg), P.whatsapp_read_back(msg)
    held = _HELD.get(ctx.account)
    said = ((a.get("approval") or {}).get("said")) or ""
    fresh = held and held["sha"] == sha and now - held["at"] <= YES_WINDOW
    if not fresh or held["at"] >= ctx.started:
        if not fresh:   # a new message, or the last read-back went stale: read THIS one back; nothing is sent
            _HELD[ctx.account] = {"sha": sha, "at": now, "msg": msg}
        return {"status": "awaiting_yes", "read_back": lines, "read_back_sha256": sha, "kind": msg["kind"], "live": live,
                "say": "Read it back exactly, then ask: shall I send it?"}
    if not strict_yes(said):
        raise ToolError("no_explicit_yes", "sending needs their explicit yes to exactly this message — a question isn't a yes")
    await claim(ctx)   # durable: this message is sent once, across restarts and workers
    _HELD.pop(ctx.account, None)
    body_sha, sent_at = P.whatsapp_body_sha256(msg), now.isoformat(timespec="seconds").replace("+00:00", "Z")
    about = msg["to"].get("name") or number
    proof = {"reference": None, "at": sent_at, "said": said[:300], "read_back_sha256": sha, "body_sha256": body_sha, "kind": msg["kind"],
             **({"template": msg["template"]["name"]} if msg["kind"] == "template" else {})}
    if not live:   # not the founder / Jon: captured, and SAID so (never "sent" for a message that didn't leave)
        OUTBOX.append({"account": ctx.account, "message": msg, "at": sent_at})
        await REC.record(ctx.account, "whatsapp", "not_sent", {**proof, "captured": True}, about)
        return {"status": "not_sent", "outcome": {"kind": "NOT_SENT", "target_words": "Not sent: real WhatsApp isn't open on this account yet. "
                                                  "Nothing left Sasha."},
                "say": "Tell them plainly it was NOT sent — nothing has left Sasha.", "message": {"to": msg["to"], "body_sha256": body_sha}}
    if msg["kind"] == "template":
        got = await _twilio(msg["from"], number, content_sid=template_sid(),
                            variables={"1": msg["template"]["params"][0], "2": msg["template"]["params"][1]})
    else:
        got = await _twilio(msg["from"], number, body=msg["text"])
    if not got.get("sid"):
        await REC.record(ctx.account, "whatsapp", "failed", {**proof, "why": got.get("why")}, about)
        raise ToolError("upstream_refused" if got.get("http_status") else "upstream_unreachable",
                        f"WhatsApp didn't accept it ({got.get('why')}) — nothing was sent")
    await REC.wrote_to(ctx.account, number, msg["to"].get("name"), a.get("on_behalf_of"))
    await REC.record(ctx.account, "whatsapp", "done", {**proof, "reference": got["sid"]}, about)
    return {"status": "sent", "outcome": {"kind": "CONFIRMED", "reference": got["sid"], "target_words": "Accepted by WhatsApp's provider."},
            "message": {"to": msg["to"], "kind": msg["kind"], "body_sha256": body_sha, "sent_at": sent_at},
            **({"say": "Only the approved first message went. Their note goes after they reply — and their yes again."}
               if msg["kind"] == "template" else {})}


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
