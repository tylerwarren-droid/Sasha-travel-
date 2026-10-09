"""CR 70 · EMAIL (Resend), live — ALLOW-LISTED ADDRESSES ONLY (AGAPI_EMAIL_ALLOW): Sasha's own booking_signer.emailing.send (her sending
key SASHA_RESEND_API_KEY, her from address), unchanged. An address that isn't allow-listed is refused BEFORE anything is approved or consumed
(adapters.precheck_live) and again here at send time. 'Sent' only when Resend answered with an email id. Replies are not taken over: they keep
landing in Sasha's own inbound (one Resend webhook per account) until the forward is built."""
from __future__ import annotations

import re
from typing import Optional

from .. import config
from ..adapters import Messenger
from ..registry import AgapiError
from ..store import ts


def allowed(address: str) -> bool:
    return (address or "").strip().lower() in config.EMAIL_ALLOW


def refuse(address: str) -> AgapiError:
    return AgapiError("upstream_refused", "AgAPI live emails only allow-listed addresses for now; nothing was sent.",
                      {"service": "email", "reason": "not_allow_listed"})


def _split(body: str, link: Optional[str]) -> dict:
    """The sandbox's message text → Resend's fields. messages.send_email's text carries its headers; the others are one paragraph."""
    m = re.match(r"From: (.*)\nReply-To: (.*)\nSubject: (.*)\n\n", body)
    if m:
        return {"subject": m.group(3)[:200], "text": body[m.end():]}
    subject = "Please review and approve" if link else "Your Kanoe verification code" if "verification code" in body else "From Kanoe"
    return {"subject": subject, "text": body}


class LiveEmail(Messenger):
    def deliver(self, store, account, end_user, to, channel, body, link):
        raise AgapiError("internal", "use adeliver")   # (the engine calls adeliver on live; a sync send could block)

    async def adeliver(self, store, account, end_user, to, channel, body, link):
        from booking_signer import emailing as EM
        from . import http
        if not allowed(to):
            raise refuse(to)
        frm = config.EMAIL_FROM
        got = await EM.send(http, {"from": frm, "to": to, **_split(body, link)})
        if not got.sent:
            raise AgapiError("upstream_unreachable" if got.http_status is None else "upstream_failed",
                             f"The mail service didn't accept it; nothing was sent ({(got.why or '')[:120]}).", {"service": "email"})
        store.x("insert into messages (account, end_user, to_, channel, sent_at, body, approval_link) values (?, ?, ?, ?, ?, ?, ?)",
                account, end_user, to, "email", ts(), f"[sent · {got.provider_id}] " + body[:2000], link)
        return got.provider_id

    async def smoke(self) -> dict:
        """Sends nothing: an EMPTY request to Resend — a validation error (422) proves the key is accepted; 401/403 says it isn't."""
        from booking_signer import emailing as EM
        from . import http
        r = await http("POST", EM.RESEND_SEND_URL, headers={"authorization": f"Bearer {EM._env(EM.KEY_VAR)}", "content-type": "application/json"}, json={})
        return {"ok": r.status_code in (400, 422), "status": r.status_code, "sent": False, "allow_listed": len(config.EMAIL_ALLOW),
                "from": config.EMAIL_FROM.split("<")[-1].rstrip(">") if config.EMAIL_FROM else None}
