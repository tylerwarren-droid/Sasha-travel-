"""DIVE · CR 67 · WHAT COMES BACK ON THE REAL CHANNELS — two signed webhooks, OFF (404) unless their variables are present:
  /hooks/twilio/whatsapp   Twilio (DIVE's OWN account): X-Twilio-Signature checked against DIVE_TWILIO_AUTH_TOKEN; only an
                           allow-listed sender is read; a reply → the supplier-reply classifier → the waiting verification or leg.
  /hooks/resend/inbound    Resend (DIVE's OWN account): the svix signature checked against DIVE_RESEND_WEBHOOK_SECRET; only mail
                           TO DIVE's domain FROM an allow-listed address is read; only the text above the quoted request counts.
A STOP is 'no more messages to me', never a supplier's no: the leg is not declined (the operator asks by phone).
Everything else is ignored and stored nowhere. Nothing here imports agapi_service, booking_signer or Sasha."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from typing import Mapping, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from . import bundles as BN, channels as CH, config, model as M, ops as OPS, rules as R
from .store import dumps, loads, ts

SVIX_TOLERANCE_S = 300
_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def twilio_signature_ok(url: str, params: Mapping[str, str], signature: Optional[str], token: str) -> bool:
    """Twilio's scheme: base64(HMAC-SHA1(auth token, url + every POST field name+value, sorted by name))."""
    if not (token and signature):
        return False
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    want = base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(want, signature)


def svix_ok(secret: str, headers: Mapping[str, str], body: bytes, now: Optional[float] = None) -> bool:
    """Svix's scheme (Resend's webhooks): HMAC-SHA256 over "{id}.{timestamp}.{body}" with the base64 key after `whsec_`;
    space-separated "v1,<base64>" entries; the timestamp within five minutes."""
    sid, stamp, sig = headers.get("svix-id"), headers.get("svix-timestamp"), headers.get("svix-signature")
    if not (secret and sid and stamp and sig):
        return False
    try:
        if abs((now if now is not None else time.time()) - int(stamp)) > SVIX_TOLERANCE_S:
            return False
        key = base64.b64decode(secret.removeprefix("whsec_"))
    except Exception:
        return False
    want = base64.b64encode(hmac.new(key, f"{sid}.{stamp}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(want, part.split(",", 1)[1]) for part in sig.split() if part.startswith("v1,"))


def _address(v) -> str:
    m = re.search(r"[^\s<>\"']+@[^\s<>\"']+", str(v or ""))
    return m.group(0).strip(".,;").lower() if m else ""


def _channels(s, o: dict, kind: str, address: str):
    return [c for c in s.q("select c.* from channels c join suppliers x on x.id = c.supplier_id where x.operator_id = ? and c.kind = ?", o["id"], kind)
            if (config.norm_number(c["address"]) if kind == "whatsapp" else c["address"].strip().lower()) == address]


def _who(s, o: dict, kind: str, address: str) -> str:
    cs = _channels(s, o, kind, address)
    return s.one("select name from suppliers where id = ?", cs[0]["supplier_id"])["name"] if cs else "A supplier"


def _stop_or_start(s, o: dict, kind: str, address: str, text: str) -> bool:
    if CH.is_stop(text):
        s.x("insert or replace into opt_outs (channel, address, at, said) values (?, ?, ?, ?)", kind, address, ts(), text[:40])
        M.event(s, o["id"], "opted_out", f"{_who(s, o, kind, address)} sent STOP: no more {'WhatsApp' if kind == 'whatsapp' else 'email'} "
                                         "to them. Not a no: ask them by phone.")
        return True
    if CH.is_start(text):
        if s.x("delete from opt_outs where channel = ? and address = ?", kind, address):
            M.event(s, o["id"], "opted_in", f"{_who(s, o, kind, address)} sent START: messages to them are back on.")
        return True
    return False


async def handle_whatsapp(s, number: str, provider_id: str, text: str) -> str:
    o = OPS.operator(s)
    if _stop_or_start(s, o, "whatsapp", number, text):
        return "opt"
    if s.one("select 1 from inbound where provider_id = ?", provider_id):
        return "duplicate"
    was_open = CH.window_open(s, number)
    s.x("insert into inbound (channel, address, provider_id, text, received_at) values ('whatsapp', ?, ?, ?, ?)", number, provider_id, text[:2000], ts())
    if not was_open:
        M.event(s, o["id"], "window", f"{_who(s, o, 'whatsapp', number)} wrote on WhatsApp: the 24-hour window is open")
    await OPS.check_verifications(s, o)                  # a waiting verification takes their YES (the same path as the test drawer's)
    for b in s.q("select id from bundles where operator_id = ? and state = 'in_progress'", o["id"]):
        await BN.sync(s, o, b["id"])                     # a waiting leg takes their answer → the classifier → the bundle
    return "read"


async def handle_email(s, sender: str, provider_id: str, subject: str, text: str) -> str:
    o = OPS.operator(s)
    if _stop_or_start(s, o, "email", sender, text):
        return "opt"
    if s.one("select 1 from inbound where provider_id = ?", provider_id):
        return "duplicate"
    s.x("insert into inbound (channel, address, provider_id, text, subject, received_at) values ('email', ?, ?, ?, ?, ?)", sender, provider_id,
        text[:2000], (subject or "")[:200], ts())
    words = R.wrap(text, "email_supplier", ts()[:19] + "Z")
    ref = (re.search(r"\[(BK-[A-Z0-9]{3})\]", subject or "") or [None, None])[1]
    for ch in _channels(s, o, "email", sender):
        legs = s.q("select l.* from legs l join bundles b on b.id = l.bundle_id where l.channel_id = ? and l.state = 'requested' "
                   "and b.state = 'in_progress' order by l.requested_at desc", ch["id"])
        legs = [l for l in legs if not ref or BN._ref(s.one("select * from bundles where id = ?", l["bundle_id"])) == ref] or legs
        if legs:
            leg = legs[0]
            b = s.one("select * from bundles where id = ?", leg["bundle_id"])
            BN._apply_reply(s, o, b, leg, s.one("select * from suppliers where id = ?", leg["supplier_id"]), ch, "email:" + provider_id, words, ts())
            await BN.sync(s, o, b["id"])
            return "leg"
        if not ch["verified"] and '"sent"' in (ch["verify_state"] or ""):
            x = s.one("select * from suppliers where id = ?", ch["supplier_id"])
            p = R.supplier_reply(text)["parse"]
            if p == "yes":
                OPS._verified(s, o, ch, x, f"they replied YES by email ({provider_id})")
            else:
                s.x("update channels set verify_state = ? where id = ?", dumps({**loads(ch["verify_state"]), "state": p, "reply": text[:200]}), ch["id"])
                M.event(s, o["id"], "verify", f"{x['name']} replied by email — {p}: for you to read")
            return "verification"
    M.event(s, o["id"], "inbound", f"An email from {_who(s, o, 'email', sender)} matched nothing waiting; kept, not acted on")
    return "unmatched"


def bind(app, db):
    @app.post("/hooks/twilio/whatsapp")
    async def twilio_whatsapp(req: Request):
        if not (config.TWILIO_TOKEN and config.WHATSAPP_ALLOW):
            return JSONResponse({"error": "not_switched_on"}, 404)
        form = {k: str(v) for k, v in (await req.form()).items()}
        if not twilio_signature_ok(config.PUBLIC_URL + "/hooks/twilio/whatsapp", form, req.headers.get("x-twilio-signature"), config.TWILIO_TOKEN):
            return JSONResponse({"error": "signature_invalid"}, 403)
        frm = form.get("From", "")
        num = config.norm_number(frm.removeprefix("whatsapp:"))
        sid = form.get("MessageSid") or form.get("SmsMessageSid") or ""
        if frm.startswith("whatsapp:") and num in config.WHATSAPP_ALLOW and sid:
            await handle_whatsapp(db(), num, sid, form.get("Body", ""))
        return Response(_TWIML, media_type="text/xml")      # anything else: ignored, stored nowhere

    @app.post("/hooks/resend/inbound")
    async def resend_inbound(req: Request):
        if not (config.RESEND_WEBHOOK_SECRET and config.EMAIL_ALLOW and config.email_domain()):
            return JSONResponse({"error": "not_switched_on"}, 404)
        raw = await req.body()
        if not svix_ok(config.RESEND_WEBHOOK_SECRET, {k.lower(): v for k, v in req.headers.items()}, raw):
            return JSONResponse({"error": "signature_invalid"}, 401)
        try:
            event = json.loads(raw)
        except ValueError:
            return JSONResponse({"error": "event_malformed"}, 400)
        if event.get("type") != "email.received":
            return {"ok": True, "ignored": "not an email.received event"}
        data = event.get("data") or {}
        pid = data.get("email_id") or data.get("id")
        to = data.get("to") if isinstance(data.get("to"), list) else [data.get("to")]
        sender = _address(data.get("from"))
        if not isinstance(pid, str) or not pid:
            return JSONResponse({"error": "event_malformed"}, 400)
        if not any(_address(a).endswith("@" + config.email_domain()) for a in to):
            return {"ok": True, "ignored": "not addressed to DIVE's domain"}   # Resend's webhooks are account-wide
        if sender not in config.EMAIL_ALLOW:
            return {"ok": True, "ignored": "not an allow-listed sender"}
        if db().one("select 1 from inbound where provider_id = ?", pid):
            return {"ok": True, "duplicate": True}
        text = await CH.email_received_text(pid)
        if text is None:
            return JSONResponse({"error": "body_unreadable"}, 503)           # Resend retries; nothing guessed meanwhile
        return {"ok": True, "result": await handle_email(db(), sender, pid, str(data.get("subject") or ""), CH.top_reply(text))}
