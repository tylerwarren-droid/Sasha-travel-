"""CR 70 · WHATSAPP + SMS (Twilio), live — ALLOW-LISTED NUMBERS ONLY (AGAPI_WHATSAPP_ALLOW). Sasha's own senders, unchanged:
booking_signer.guest_whatsapp.Sender (from the number sender_for() picks, Sasha's guest number) and guest_receipt.send_sms (from Sasha's
own number; its switch SASHA_SMS_TO_GUEST). A number off the list is refused before anything (adapters.precheck_live) and again here.
The 24-hour window is read from TWILIO'S OWN RECORD (the person's last message to that sender, read-only) — AgAPI doesn't hold the inbound
(replies keep landing in Sasha's one webhook). First contact outside the window needs Meta's approved template (AGAPI_WA_ONBEHALF_SID): not
configured → refused before any read-back. Sasha's Sender says only 'sent' (no message id), so the evidence says 'accepted by Twilio'."""
from __future__ import annotations

import base64
import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from .. import config
from ..adapters import Messenger
from ..registry import AgapiError
from ..store import ts


def norm(n: str) -> str:
    return "".join(c for c in (n or "") if c.isdigit() or c == "+")


def allowed(number: str) -> bool:
    return norm(number) in config.WHATSAPP_ALLOW


def _auth():
    sid, tok = os.getenv("TWILIO_ACCOUNT_SID", "").strip(), os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    return (sid, base64.b64encode(f"{sid}:{tok}".encode()).decode()) if sid and tok else None


def sender() -> str:
    from booking_signer import guest_whatsapp as GW
    return GW.sender_for(None)


class LiveWhatsApp(Messenger):
    def deliver(self, store, account, end_user, to, channel, body, link):
        raise AgapiError("internal", "use adeliver")

    async def window_open(self, number: str) -> bool:
        """Twilio's own record: did this person write to our WhatsApp sender in the last 24 h? (read-only; spends nothing)"""
        from . import http
        a = _auth()
        if not a:
            return False
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        r = await http("GET", f"https://api.twilio.com/2010-04-01/Accounts/{a[0]}/Messages.json?From=whatsapp:{norm(number)}"
                              f"&To=whatsapp:{sender()}&DateSent%3E={since.date().isoformat()}&PageSize=20",
                       headers={"authorization": f"Basic {a[1]}"})
        if r.status_code != 200:
            return False
        for m in (r.json() or {}).get("messages") or []:
            try:
                when = datetime.strptime(m.get("date_sent") or "", "%a, %d %b %Y %H:%M:%S %z")
            except ValueError:
                continue
            if when >= since and m.get("direction") == "inbound":
                return True
        return False

    async def adeliver(self, store, account, end_user, to, channel, body, link):
        if not allowed(to):
            raise AgapiError("upstream_refused", "AgAPI live sends messages only to allow-listed numbers for now; nothing was sent.",
                             {"service": channel, "reason": "not_allow_listed"})
        if channel == "sms":
            from booking_signer import guest_receipt as GR
            got = await GR.send_sms(norm(to), body)
            if got != "sms sent":
                raise AgapiError("upstream_failed", f"The SMS wasn't accepted; nothing was sent ({got[:120]}).", {"service": "twilio_sms"})
        else:
            from booking_signer import guest_whatsapp as GW
            if not body:
                raise AgapiError("upstream_refused", "A first WhatsApp outside the 24-hour window needs Meta's approved template, which isn't "
                                 "configured for live yet; nothing was sent.", {"service": "whatsapp", "reason": "template_not_configured"})
            got = await GW.Sender().send(sender(), norm(to), body=body)
            if got != "sent":
                raise AgapiError("upstream_failed", f"WhatsApp's provider didn't accept it; nothing was sent ({got[:120]}).", {"service": "whatsapp"})
        ref = "twilio_" + hashlib.sha256(f"{to}|{ts()}".encode()).hexdigest()[:16]
        store.x("insert into messages (account, end_user, to_, channel, sent_at, body, approval_link) values (?, ?, ?, ?, ?, ?, ?)",
                account, end_user, norm(to), channel, ts(), f"[sent · accepted by Twilio] " + (body or "")[:2000], link)
        return ref

    async def smoke(self) -> dict:
        """Sends nothing: Twilio's account record (status only)."""
        from . import http
        a = _auth()
        if not a:
            return {"ok": False, "why": "no Twilio account on agapi-live"}
        r = await http("GET", f"https://api.twilio.com/2010-04-01/Accounts/{a[0]}.json", headers={"authorization": f"Basic {a[1]}"})
        st = (r.json() or {}).get("status") if r.status_code == 200 else None
        return {"ok": st == "active", "status": r.status_code, "account": st, "sent": False, "allow_listed": len(config.WHATSAPP_ALLOW),
                "template": bool(config.WA_ONBEHALF_SID)}
